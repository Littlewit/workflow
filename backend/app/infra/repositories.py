"""仓储层：引擎/应用服务访问持久化的唯一入口。

设计要点（对应系统设计文档 §6.6）：
- 引擎内核不接触 ORM，应用层通过本模块读写；
- 所有方法接收 AsyncSession，事务边界由调用方（Application 层）控制；
- 查询统一附加 tenant 条件的位置已预留（MVP 单租户暂不启用）。
"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.models.definition import WorkflowDefinition, WorkflowDefinitionVersion
from app.infra.models.instance import InstanceEvent, TaskInstance, WorkflowInstance


class DefinitionRepository:
    """流程定义与版本快照读写。"""

    def __init__(self, session: AsyncSession) -> None:
        """绑定请求级会话。"""
        self._session = session

    async def get_published_version(self, code: str) -> tuple[WorkflowDefinition, WorkflowDefinitionVersion]:
        """按业务编码取当前已发布版本。

        Raises:
            KeyError: 定义不存在。
            ValueError: 定义未发布或已停用。
        """
        stmt = select(WorkflowDefinition).where(WorkflowDefinition.code == code)
        definition = (await self._session.execute(stmt)).scalar_one_or_none()
        if definition is None:
            raise KeyError(f"流程定义不存在: {code}")
        if definition.status != "published" or definition.current_version == 0:
            raise ValueError(f"流程定义未发布或已停用: {code}")
        version_stmt = select(WorkflowDefinitionVersion).where(
            WorkflowDefinitionVersion.definition_id == definition.id,
            WorkflowDefinitionVersion.version == definition.current_version,
        )
        version = (await self._session.execute(version_stmt)).scalar_one()
        return definition, version


class InstanceRepository:
    """流程实例读写（含引擎状态快照）。"""

    def __init__(self, session: AsyncSession) -> None:
        """绑定请求级会话。"""
        self._session = session

    async def create(self, instance: WorkflowInstance) -> WorkflowInstance:
        """新增实例。"""
        self._session.add(instance)
        await self._session.flush()
        return instance

    async def get(self, instance_id: str) -> WorkflowInstance | None:
        """按 ID 加载实例。"""
        return await self._session.get(WorkflowInstance, instance_id)

    async def get_for_update(self, instance_id: str) -> WorkflowInstance:
        """加行锁加载实例（SQLite 忽略 FOR UPDATE，PG 生效；乐观锁 state_version 兜底）。

        Raises:
            KeyError: 实例不存在。
        """
        stmt = select(WorkflowInstance).where(WorkflowInstance.id == instance_id).with_for_update()
        instance = (await self._session.execute(stmt)).scalar_one_or_none()
        if instance is None:
            raise KeyError(f"流程实例不存在: {instance_id}")
        return instance


class TaskRepository:
    """任务读写：待办列表与镜像同步。"""

    def __init__(self, session: AsyncSession) -> None:
        """绑定请求级会话。"""
        self._session = session

    async def bulk_upsert_mirror(self, instance_id: str, tasks: list[dict]) -> None:
        """将引擎状态中的任务镜像到 task_instance 表（全量对齐，MVP 简化策略）。

        以引擎状态为事实源：先删后插会导致任务 ID 漂移，因此按任务 ID
        逐个 get-or-create，再对齐状态/动作字段。
        """
        for t in tasks:
            row = await self._session.get(TaskInstance, t["id"])
            if row is None:
                row = TaskInstance(
                    id=t["id"],
                    instance_id=instance_id,
                    created_at=datetime.now(timezone.utc),
                )
                self._session.add(row)
            row.node_key = t["node_key"]
            row.node_name = t["node_name"]
            row.node_type = t["node_type"]
            row.round = t["round"]
            row.assignee_id = t["assignee_id"]
            row.status = t["status"]
            row.action = t["action"]
            row.counter_sign_group_id = t.get("counter_sign_group_id")

    async def list_todo(self, assignee_id: str) -> list[TaskInstance]:
        """某人的全部待办任务。"""
        stmt = (
            select(TaskInstance)
            .where(TaskInstance.assignee_id == assignee_id, TaskInstance.status == "pending")
            .order_by(TaskInstance.created_at.desc())
        )
        return list((await self._session.execute(stmt)).scalars())

    async def list_done(self, assignee_id: str) -> list[TaskInstance]:
        """某人的全部已办任务（终态）。"""
        stmt = (
            select(TaskInstance)
            .where(
                TaskInstance.assignee_id == assignee_id,
                TaskInstance.status.in_(["approved", "rejected", "transferred", "timeout_auto"]),
            )
            .order_by(TaskInstance.finished_at.desc())
        )
        return list((await self._session.execute(stmt)).scalars())


class EventRepository:
    """事件流水（Outbox 持久层）读写。"""

    def __init__(self, session: AsyncSession) -> None:
        """绑定请求级会话。"""
        self._session = session

    async def append_all(self, instance_id: str, events: list[dict], operation_id: str | None) -> None:
        """将引擎产生的事件批量落库（dispatched=False，等待 Outbox 投递）。"""
        for e in events:
            self._session.add(
                InstanceEvent(
                    id=uuid4().hex,
                    instance_id=instance_id,
                    event_type=e["event_type"],
                    node_key=e.get("node_key"),
                    task_id=e.get("payload", {}).get("taskId"),
                    payload=e.get("payload", {}),
                    operation_id=operation_id,
                )
            )
        await self._session.flush()

    async def list_undispatched(self, limit: int = 100) -> list[InstanceEvent]:
        """Outbox 扫描：取未投递事件。"""
        stmt = select(InstanceEvent).where(InstanceEvent.dispatched.is_(False)).limit(limit)
        return list((await self._session.execute(stmt)).scalars())

    async def mark_dispatched(self, events: list[InstanceEvent]) -> None:
        """投递成功后标记（幂等：重复标记无害）。"""
        now = datetime.now(timezone.utc)
        for e in events:
            e.dispatched = True
            e.dispatched_at = now
        await self._session.flush()
