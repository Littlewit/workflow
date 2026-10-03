"""工作流应用服务：发起 / 审批 / 驳回用例（事务边界所在层）。

核心编排逻辑（对应详细设计 §1.1/§1.2 时序）：
  1. 幂等检查（operationId）
  2. 实例锁（防同一实例并发流转）
  3. 事务内：加载定义/实例快照 → 引擎运算 → 回写快照 + 镜像任务表 + 事件落库 + 意见落库
  4. 提交事务 → 返回结果（通知/Webhook 由 Outbox 异步消费）

引擎内核异常在此转换为带错误码的 ApplicationError。
"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.errors import (
    BusinessKeyDuplicateError,
    DefinitionNotPublishedError,
    InstanceNotFoundError,
    NotAssigneeError,
    TaskConflictError,
    TaskNotFoundError,
)
from app.domain.dsl import WorkflowDSL
from app.domain.enums import InstanceStatus, TaskStatus
from app.engine.executor import ExecutionState, WorkflowEngine
from app.engine.resolvers import ResolverRegistry
from app.infra.engine_codec import deserialize_state, serialize_state, serialize_tasks
from app.infra.idempotency import InMemoryInstanceLock, InMemoryOperationStore
from app.infra.models.definition import WorkflowDefinitionVersion
from app.infra.models.instance import InstanceEvent, TaskInstance, TaskOpinion, WorkflowInstance
from app.infra.repositories import (
    DefinitionRepository,
    EventRepository,
    InstanceRepository,
    TaskRepository,
)


def _load_dsl(version: WorkflowDefinitionVersion) -> WorkflowDSL:
    """从版本快照还原 DSL 模型（快照不可变，可安全重建）。"""
    return WorkflowDSL.model_validate(version.dsl)


class WorkflowService:
    """工作流用例服务。

    Args:
        session_factory: 会话工厂（事务边界 = 每个用例方法）。
        operation_store: 幂等存储（默认内存实现，M5 换 Redis）。
        instance_lock: 实例锁（默认内存实现，M5 换 Redis）。
        admin_ids: 管理员 ID（审批人 fallback=to_admin 使用）。
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        operation_store: InMemoryOperationStore | None = None,
        instance_lock: InMemoryInstanceLock | None = None,
        admin_ids: list[str] | None = None,
    ) -> None:
        """注入会话工厂与基础设施组件。"""
        self._sessions = session_factory
        self._operations = operation_store or InMemoryOperationStore()
        self._locks = instance_lock or InMemoryInstanceLock()
        self._admin_ids = admin_ids or []

    # ---------- 用例：发起流程 ----------

    async def start_instance(
        self,
        definition_code: str,
        initiator_id: str,
        form_data: dict | None = None,
        business_key: str | None = None,
        title: str = "",
        operation_id: str | None = None,
    ) -> dict:
        """发起流程实例。

        Returns:
            {"instanceId", "status", "tasks"}：tasks 为当前活跃任务摘要。

        Raises:
            DuplicateOperationError: operationId 重复。
            DefinitionNotPublishedError: 定义未发布。
            BusinessKeyDuplicateError: businessKey 已发起过。
        """
        op_key = f"start:{initiator_id}:{operation_id}" if operation_id else None
        if op_key and (cached := await self._operations.get(op_key)) is not None:
            return cached  # 幂等命中：直接返回首次结果

        async with self._sessions() as session:
            definition, version = await DefinitionRepository(session).get_published_version(definition_code)
            if definition.status != "published":
                raise DefinitionNotPublishedError(definition_code)
            dsl = _load_dsl(version)

            if business_key is not None:
                # business_key 防重的友好前置检查（唯一索引为最终兜底）
                dup = await session.execute(
                    select(WorkflowInstance.id).where(
                        WorkflowInstance.definition_id == definition.id,
                        WorkflowInstance.business_key == business_key,
                    )
                )
                if dup.scalar_one_or_none() is not None:
                    raise BusinessKeyDuplicateError(business_key)

            engine = WorkflowEngine(dsl, self._build_resolvers())
            state = engine.start(initiator_id=initiator_id, variables=dict(form_data or {}))

            instance = WorkflowInstance(
                id=state.instance_id,
                definition_id=definition.id,
                definition_version=version.version,
                business_key=business_key,
                title=title,
                initiator_id=initiator_id,
                status=state.status.value,
                current_node_keys=[t.current_key for t in state.tokens.values()],
                engine_state=serialize_state(state),
                start_form_snapshot=dict(form_data or {}),
            )
            repo = InstanceRepository(session)
            try:
                await repo.create(instance)
            except Exception as exc:  # 并发双击发起时唯一索引兜底
                if business_key is not None and "UNIQUE" in str(exc).upper():
                    await session.rollback()
                    raise BusinessKeyDuplicateError(business_key) from exc
                raise

            await self._sync_derived(session, state, operation_id)
            await session.commit()

        result = {
            "instanceId": instance.id,
            "status": state.status.value,
            "tasks": self._active_task_summaries(state),
        }
        if op_key:
            await self._operations.put(op_key, result)
        return result

    # ---------- 用例：审批同意 ----------

    async def approve(
        self,
        task_id: str,
        user_id: str,
        opinion: str = "",
        variables: dict | None = None,
        operation_id: str | None = None,
    ) -> dict:
        """同意任务（含会签票数判定）。

        Raises:
            TaskNotFoundError: 任务不存在。
            NotAssigneeError: 非处理人。
            TaskConflictError: 任务状态已变化（43102）或实例流转冲突（42100）。
        """
        op_key = f"approve:{user_id}:{operation_id}" if operation_id else None
        if op_key and (cached := await self._operations.get(op_key)) is not None:
            return cached

        async with self._sessions() as session:
            instance = await self._load_instance_by_task(session, task_id)
            self._ensure_not_suspended(instance)
            if not await self._locks.acquire(instance.id):
                raise TaskConflictError(42100, "实例正在流转中，请稍后重试")
            try:
                state = await self._restore_state(session, instance)
                self._get_task(state, task_id, user_id)  # 校验任务存在 + 处理人身份

                WorkflowEngine(state.dsl, self._build_resolvers()).approve(state, task_id, variables)
                return await self._persist_and_finish(
                    session, instance, state, task_id, user_id, opinion, op_key
                )
            finally:
                await self._locks.release(instance.id)

    # ---------- 用例：驳回 ----------

    async def reject(
        self,
        task_id: str,
        user_id: str,
        opinion: str = "",
        target_node_key: str | None = None,
        operation_id: str | None = None,
    ) -> dict:
        """驳回任务：流转回退到目标节点并重建任务（round+1）。"""
        op_key = f"reject:{user_id}:{operation_id}" if operation_id else None
        if op_key and (cached := await self._operations.get(op_key)) is not None:
            return cached

        async with self._sessions() as session:
            instance = await self._load_instance_by_task(session, task_id)
            self._ensure_not_suspended(instance)
            if not await self._locks.acquire(instance.id):
                raise TaskConflictError(42100, "实例正在流转中，请稍后重试")
            try:
                state = await self._restore_state(session, instance)
                self._get_task(state, task_id, user_id)  # 校验任务存在 + 处理人身份

                WorkflowEngine(state.dsl, self._build_resolvers()).reject(state, task_id, target_node_key)
                return await self._persist_and_finish(
                    session, instance, state, task_id, user_id, opinion, op_key
                )
            finally:
                await self._locks.release(instance.id)

    # ---------- 用例：待办 ----------

    async def list_todo(self, assignee_id: str) -> list[dict]:
        """查询某人待办任务摘要。"""
        async with self._sessions() as session:
            tasks = await TaskRepository(session).list_todo(assignee_id)
            return [
                {
                    "taskId": t.id,
                    "instanceId": t.instance_id,
                    "nodeName": t.node_name,
                    "round": t.round,
                    "status": t.status,
                    "createdAt": t.created_at.isoformat() if t.created_at else None,
                }
                for t in tasks
            ]

    # ---------- 用例：转办 / 撤回 ----------

    async def transfer(
        self, task_id: str, user_id: str, to_user_id: str, opinion: str = "",
        operation_id: str | None = None,
    ) -> dict:
        """转办任务给他人（原任务终态，承接人获得新任务）。"""
        op_key = f"transfer:{user_id}:{operation_id}" if operation_id else None
        if op_key and (cached := await self._operations.get(op_key)) is not None:
            return cached

        async with self._sessions() as session:
            instance = await self._load_instance_by_task(session, task_id)
            self._ensure_not_suspended(instance)
            if not await self._locks.acquire(instance.id):
                raise TaskConflictError(42100, "实例正在流转中，请稍后重试")
            try:
                state = await self._restore_state(session, instance)
                self._get_task(state, task_id, user_id)
                WorkflowEngine(state.dsl, self._build_resolvers()).transfer(
                    state, task_id, user_id, to_user_id
                )
                return await self._persist_and_finish(
                    session, instance, state, task_id, user_id, opinion, op_key
                )
            finally:
                await self._locks.release(instance.id)

    async def recall(self, task_id: str, user_id: str, operation_id: str | None = None) -> dict:
        """撤回已提交的任务（下一节点未处理时）。"""
        op_key = f"recall:{user_id}:{operation_id}" if operation_id else None
        if op_key and (cached := await self._operations.get(op_key)) is not None:
            return cached

        async with self._sessions() as session:
            instance = await self._load_instance_by_task(session, task_id)
            if not await self._locks.acquire(instance.id):
                raise TaskConflictError(42100, "实例正在流转中，请稍后重试")
            try:
                state = await self._restore_state(session, instance)
                WorkflowEngine(state.dsl, self._build_resolvers()).recall(state, task_id, user_id)
                return await self._persist_and_finish(session, instance, state, task_id, user_id, "", op_key)
            finally:
                await self._locks.release(instance.id)

    async def list_done(self, assignee_id: str) -> list[dict]:
        """查询某人已办任务摘要。"""
        async with self._sessions() as session:
            tasks = await TaskRepository(session).list_done(assignee_id)
            return [
                {
                    "taskId": t.id,
                    "instanceId": t.instance_id,
                    "nodeName": t.node_name,
                    "status": t.status,
                    "action": t.action,
                }
                for t in tasks
            ]

    # ---------- 用例：超时/SLA 扫描（M5-T5.2） ----------

    async def scan_overdue_tasks(self) -> list[str]:
        """扫描超时任务并执行节点配置的策略（notify/transfer_to/auto_approve/auto_reject）。

        幂等：执行前二次校验任务状态与截止时间，误触发无害；
        单个失败不影响其余（由 ARQ 定时任务周期调用）。

        Returns:
            已处理的任务 ID 列表。
        """
        from datetime import datetime
        from datetime import timezone as _tz

        now = datetime.now(_tz.utc)
        async with self._sessions() as session:
            overdue = await TaskRepository(session).list_overdue(now)
            task_ids = [t.id for t in overdue]

        processed: list[str] = []
        for task_id in task_ids:
            if await self._handle_overdue(task_id, now):
                processed.append(task_id)
        return processed

    async def _handle_overdue(self, task_id: str, now: datetime) -> bool:
        """处理单个超时任务，返回是否实际执行了策略。"""
        from app.domain.enums import TaskStatus as _TS
        from app.engine.executor import EngineEvent

        async with self._sessions() as session:
            instance = await self._load_instance_by_task(session, task_id)
            if instance is None or instance.status != InstanceStatus.RUNNING.value:
                return False
            if not await self._locks.acquire(instance.id):
                return False  # 正在人工流转：下一轮再处理
            try:
                state = await self._restore_state(session, instance)
                task = state.tasks.get(task_id)
                if task is None or task.status != _TS.PENDING:
                    return False
                if task.deadline_at is None or task.deadline_at > now:
                    return False  # 已被人工处理或时间未到（幂等防线）

                node = state.dsl.nodes[task.node_key]
                policy = getattr(node, "timeout_policy", None)
                engine = WorkflowEngine(state.dsl, self._build_resolvers())
                if policy is None:
                    return False
                if policy.action == "auto_approve":
                    engine.approve(state, task_id)
                elif policy.action == "auto_reject":
                    engine.reject(state, task_id)
                elif policy.action == "transfer_to":
                    if not policy.transfer_to:
                        return False
                    # 系统代为转交：以原处理人身份执行转办
                    engine.transfer(state, task_id, task.assignee_id, policy.transfer_to)
                else:  # notify：仅记录提醒事件，由 Outbox 发送通知
                    state.events.append(
                        EngineEvent("timeout_triggered", node.key, {"taskId": task_id, "policy": "notify"})
                    )
                await self._persist_and_finish(session, instance, state, task_id, "system", "", None)
                return True
            finally:
                await self._locks.release(instance.id)

    # ---------- 用例：实例运维与查询 ----------

    async def _instance_op(self, instance_id: str, op_name: str, reason: str = "") -> dict:
        """实例级运维操作的统一模板：锁 → 引擎操作 → 落库。

        Args:
            op_name: terminate / suspend / resume / cancel。
        """
        async with self._sessions() as session:
            instance = await InstanceRepository(session).get_for_update(instance_id)
            if instance is None:
                raise InstanceNotFoundError(instance_id)
            if not await self._locks.acquire(instance_id):
                raise TaskConflictError(42100, "实例正在流转中，请稍后重试")
            try:
                state = await self._restore_state(session, instance)
                engine = WorkflowEngine(state.dsl, self._build_resolvers())
                getattr(engine, op_name)(state, reason) if op_name != "resume" else engine.resume(state)
                return await self._persist_and_finish(session, instance, state, "", "", "", None)
            finally:
                await self._locks.release(instance_id)

    async def terminate_instance(self, instance_id: str, user_id: str, reason: str = "") -> dict:
        """管理员强制终止。"""
        return await self._instance_op(instance_id, "terminate", reason)

    async def suspend_instance(self, instance_id: str, user_id: str, reason: str = "") -> dict:
        """暂停实例。"""
        return await self._instance_op(instance_id, "suspend", reason)

    async def resume_instance(self, instance_id: str, user_id: str) -> dict:
        """恢复实例。"""
        return await self._instance_op(instance_id, "resume")

    async def cancel_instance(self, instance_id: str, user_id: str, reason: str = "") -> dict:
        """发起人撤回实例。"""
        return await self._instance_op(instance_id, "cancel", reason)

    async def get_instance_detail(self, instance_id: str) -> dict:
        """实例详情：状态 + 当前节点 + 任务镜像 + 事件时间线。"""
        async with self._sessions() as session:
            instance = await InstanceRepository(session).get(instance_id)
            if instance is None:
                raise InstanceNotFoundError(instance_id)
            tasks = (await session.execute(
                select(TaskInstance).where(TaskInstance.instance_id == instance_id)
            )).scalars().all()
            events = (await session.execute(
                select(InstanceEvent)
                .where(InstanceEvent.instance_id == instance_id)
                .order_by(InstanceEvent.created_at)
            )).scalars().all()
            return {
                "instanceId": instance.id,
                "definitionId": instance.definition_id,
                "definitionVersion": instance.definition_version,
                "title": instance.title,
                "status": instance.status,
                "initiatorId": instance.initiator_id,
                "currentNodeKeys": instance.current_node_keys,
                "startedAt": instance.started_at.isoformat() if instance.started_at else None,
                "finishedAt": instance.finished_at.isoformat() if instance.finished_at else None,
                "tasks": [
                    {
                        "taskId": t.id, "nodeKey": t.node_key, "nodeName": t.node_name,
                        "assigneeId": t.assignee_id, "status": t.status, "action": t.action,
                        "round": t.round,
                    }
                    for t in tasks
                ],
                "timeline": [
                    {
                        "eventId": e.id, "eventType": e.event_type, "nodeKey": e.node_key,
                        "payload": e.payload,
                        "createdAt": e.created_at.isoformat() if e.created_at else None,
                    }
                    for e in events
                ],
            }

    async def list_my_instances(self, initiator_id: str) -> list[dict]:
        """我发起的实例列表。"""
        async with self._sessions() as session:
            rows = (await session.execute(
                select(WorkflowInstance)
                .where(WorkflowInstance.initiator_id == initiator_id)
                .order_by(WorkflowInstance.started_at.desc())
            )).scalars().all()
            return [
                {
                    "instanceId": r.id, "title": r.title, "status": r.status,
                    "businessKey": r.business_key,
                    "startedAt": r.started_at.isoformat() if r.started_at else None,
                }
                for r in rows
            ]

    # ---------- 内部：状态恢复与持久化 ----------

    def _build_resolvers(self) -> ResolverRegistry:
        """构建审批人解析注册表（自定义解析器经此注入）。"""
        return ResolverRegistry(admin_ids=self._admin_ids)

    async def _restore_state(self, session: AsyncSession, instance: WorkflowInstance) -> ExecutionState:
        """加载定义版本 DSL 并从快照恢复引擎状态。"""
        stmt = select(WorkflowDefinitionVersion).where(
            WorkflowDefinitionVersion.definition_id == instance.definition_id,
            WorkflowDefinitionVersion.version == instance.definition_version,
        )
        version = (await session.execute(stmt)).scalar_one()
        return deserialize_state(_load_dsl(version), instance.id, instance.engine_state)

    @staticmethod
    def _ensure_not_suspended(instance: WorkflowInstance) -> None:
        """暂停中的实例禁止一切任务操作（对应 42101）。"""
        if instance.status == InstanceStatus.SUSPENDED.value:
            raise TaskConflictError(42101, "实例已暂停，任务不可操作")

    @staticmethod
    def _get_task(state: ExecutionState, task_id: str, user_id: str):
        """取任务并校验处理人身份。

        Raises:
            TaskNotFoundError: 任务不存在。
            NotAssigneeError: 非处理人。
        """
        task = state.tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        if task.assignee_id != user_id:
            raise NotAssigneeError(user_id)
        return task

    async def _load_instance_by_task(self, session: AsyncSession, task_id: str) -> WorkflowInstance:
        """按任务 ID 加行锁加载所属实例。"""
        row = await session.execute(select(TaskInstance.instance_id).where(TaskInstance.id == task_id))
        instance_id = row.scalar_one_or_none()
        if instance_id is None:
            raise TaskNotFoundError(task_id)
        instance = await InstanceRepository(session).get_for_update(instance_id)
        if instance is None:
            raise InstanceNotFoundError(instance_id)
        return instance

    async def _persist_and_finish(
        self,
        session: AsyncSession,
        instance: WorkflowInstance,
        state: ExecutionState,
        task_id: str,
        user_id: str,
        opinion: str,
        op_key: str | None,
    ) -> dict:
        """统一落库：快照 + 镜像 + 事件 + 意见，提交后返回结果。"""
        instance.status = state.status.value
        instance.current_node_keys = [t.current_key for t in state.tokens.values()]
        instance.engine_state = serialize_state(state)
        instance.state_version += 1  # 乐观锁递增（Redis 锁的兜底防线）
        if state.status in (InstanceStatus.COMPLETED, InstanceStatus.TERMINATED, InstanceStatus.CANCELED):
            instance.finished_at = datetime.now(timezone.utc)

        await TaskRepository(session).bulk_upsert_mirror(instance.id, serialize_tasks(state))
        await EventRepository(session).append_all(
            instance.id,
            [
                {"event_type": e.event_type, "node_key": e.node_key, "payload": e.payload}
                for e in state.events
            ],
            operation_id=op_key,
        )
        if opinion:
            session.add(
                TaskOpinion(
                    id=uuid4().hex,
                    task_id=task_id,
                    instance_id=instance.id,
                    content=opinion,
                    author_id=user_id,
                )
            )
        await session.commit()

        result = {
            "instanceId": instance.id,
            "instanceStatus": state.status.value,
            "tasks": self._active_task_summaries(state),
        }
        if op_key:
            await self._operations.put(op_key, result)
        return result

    async def _sync_derived(self, session: AsyncSession, state: ExecutionState, operation_id: str | None) -> None:
        """发起用例的派生数据落库：镜像任务表 + 事件流水。"""
        await TaskRepository(session).bulk_upsert_mirror(state.instance_id, serialize_tasks(state))
        await EventRepository(session).append_all(
            state.instance_id,
            [
                {"event_type": e.event_type, "node_key": e.node_key, "payload": e.payload}
                for e in state.events
            ],
            operation_id=operation_id,
        )

    @staticmethod
    def _active_task_summaries(state: ExecutionState) -> list[dict]:
        """活跃任务摘要（返回给前端定位下一处理人）。"""
        return [
            {
                "taskId": t.id,
                "nodeKey": t.node_key,
                "nodeName": t.node_name,
                "assigneeId": t.assignee_id,
                "status": t.status.value,
                "round": t.round,
            }
            for t in state.tasks.values()
            if t.status == TaskStatus.PENDING
        ]
