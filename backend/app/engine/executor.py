"""内存版流程执行器（引擎内核）。

对应详细设计文档第三部分 §1.3 Token 推进通用算法。本层是纯逻辑实现：
- 不依赖 DB / Redis / FastAPI，持久化在 M3 由 Application 层按事件流落地；
- 每次操作产生事件列表（node_entered / node_completed / ...），M2 阶段
  存于 ExecutionState.events 供测试与持久化层消费；
- 会签规则判定、驳回重走（round 递增）均在此实现。

并发说明：内存版仅用于测试与逻辑验证；M3 生产实现会在调用前叠加
Redis 锁 + 数据库行锁（算法逻辑不变）。
"""

import itertools
from dataclasses import dataclass, field
from uuid import uuid4

from app.domain.dsl import (
    ApprovalNode,
    CCNode,
    CounterSignMode,
    Edge,
    EndNode,
    ExclusiveGatewayNode,
    NodeType,
    StartNode,
    WorkflowDSL,
)
from app.domain.enums import InstanceStatus, TaskAction, TaskStatus
from app.engine.exceptions import WorkflowConfigError
from app.engine.resolvers import ResolverRegistry
from app.engine.state_machine import ensure_instance_transition, ensure_task_transition


@dataclass
class EngineEvent:
    """领域事件（类型与 payload 见详细设计 §2.10 数据字典）。"""

    event_type: str
    node_key: str | None = None
    payload: dict = field(default_factory=dict)


@dataclass
class EngineTask:
    """内存任务实体（与 task_instance 表字段一一对应）。"""

    id: str
    node_key: str
    node_name: str
    assignee_id: str
    status: TaskStatus = TaskStatus.PENDING
    round: int = 1  # 驳回重走时递增
    counter_sign_group_id: str | None = None  # 会签分组
    action: TaskAction | None = None


@dataclass
class EngineToken:
    """令牌：表示一次进行中的执行路径（并行分支 = 多个 token）。

    Attributes:
        id: token 唯一标识。
        current_key: 当前停留节点（等待任务完成时停在该节点）。
        path: 已完成节点的 key 历史（驳回去重走时用于定位上一节点）。
    """

    id: str
    current_key: str
    path: list[str] = field(default_factory=list)


@dataclass
class ExecutionState:
    """一次流程运行的完整内存状态（实例聚合根）。"""

    instance_id: str
    dsl: WorkflowDSL
    status: InstanceStatus = InstanceStatus.RUNNING
    variables: dict = field(default_factory=dict)
    tasks: dict[str, EngineTask] = field(default_factory=dict)  # taskId -> task
    tokens: dict[str, EngineToken] = field(default_factory=dict)  # tokenId -> token
    events: list[EngineEvent] = field(default_factory=list)
    finished_at_reason: str | None = None  # 终态原因记录


class WorkflowEngine:
    """单实例流程引擎：解析 DSL 并驱动 token 流转。

    用法：
        engine = WorkflowEngine(dsl, resolvers)
        state = engine.start(initiator_id="u1", variables={"days": 5})
        state = engine.approve(task_id=..., variables={...})
    """

    def __init__(self, dsl: WorkflowDSL, resolvers: ResolverRegistry | None = None) -> None:
        """初始化引擎。

        Args:
            dsl: 流程定义（须为发布版快照）。
            resolvers: 审批人解析注册表；缺省使用内置注册表。
        """
        self._dsl = dsl
        self._resolvers = resolvers or ResolverRegistry()
        self._out_edges: dict[str, list[Edge]] = {}
        for e in dsl.edges:
            self._out_edges.setdefault(e.source, []).append(e)
        self._edge_seq = itertools.count(1)  # 任务/事件 ID 生成序号源

    # ---------- 对外操作 ----------

    def start(self, initiator_id: str, variables: dict | None = None) -> ExecutionState:
        """发起流程：创建实例状态并从 start 节点推进。

        Args:
            initiator_id: 发起人 ID。
            variables: 初始变量（表单数据）。

        Returns:
            执行状态（含首个待办任务或直接完成的终态）。
        """
        state = ExecutionState(
            instance_id=uuid4().hex, dsl=self._dsl, variables=dict(variables or {})
        )
        # 系统预置变量（详细设计 §2.3 变量上下文）
        state.variables["$_initiator"] = initiator_id
        state.events.append(
            EngineEvent("workflow_started", "start", {"initiatorId": initiator_id})
        )
        self._run(state)
        return state

    def approve(self, state: ExecutionState, task_id: str, variables: dict | None = None) -> None:
        """同意任务：迁移状态 → 会签判定 → 推进 token。

        Args:
            state: 当前执行状态。
            task_id: 要处理的任务 ID。
            variables: 本次提交的变量更新（如表单数据）。

        Raises:
            IllegalTransitionError: 任务状态不允许迁移（如已被他人处理）。
            KeyError: 任务不存在。
        """
        task = state.tasks[task_id]
        ensure_task_transition(task.status, TaskStatus.APPROVED)
        self._transition_task(state, task, TaskStatus.APPROVED, TaskAction.APPROVE)
        if variables:
            state.variables.update(variables)

        node = self._dsl.nodes[task.node_key]
        if not self._counter_sign_done(state, node, task):
            # 会签未达票数：事件照发，流程不推进
            return

        self._finish_node(state, node.key)
        token = self._token_of_node(state, task.node_key)
        # 先移出已完成节点再推进，否则 _advance 会在原地重复建任务
        self._walk(state, token)
        self._advance(state, token)

    def reject(self, state: ExecutionState, task_id: str, target_node_key: str | None = None) -> None:
        """驳回任务：回收当前路径 → 在目标节点重建任务（round+1）。

        Args:
            state: 当前执行状态。
            task_id: 要驳回的任务 ID。
            target_node_key: 显式驳回目标；缺省用节点配置的 default_reject_target。
                支持 "initiator"（发起人）、"previous"（上一审批节点）、"node:xxx"。

        Raises:
            WorkflowConfigError: 无法确定驳回目标或目标不在已完成路径中。
        """
        task = state.tasks[task_id]
        ensure_task_transition(task.status, TaskStatus.REJECTED)
        self._transition_task(state, task, TaskStatus.REJECTED, TaskAction.REJECT)

        node = self._dsl.nodes[task.node_key]
        # 只有审批节点/开始节点有驳回语义；default_reject_target 用 getattr 适配联合类型
        default_target = getattr(node, "default_reject_target", None)
        target = self._resolve_reject_target(state, node.key, target_node_key or default_target)
        token = self._token_of_node(state, task.node_key)

        # 定位 target 在路径中的位置；start 初次经过不产生任务故不在 path 中，视作路径起点
        start_key = next(k for k, n in self._dsl.nodes.items() if n.type == NodeType.START)
        if target in token.path:
            t_idx = token.path.index(target)
        elif target == start_key:
            t_idx = 0
        else:
            raise WorkflowConfigError(f"驳回目标 {target} 不在本实例已完成路径中")
        for t in state.tasks.values():
            # 回收 target 之后的活跃任务（它们尚未闭环，逻辑上作废）
            if t.status in (TaskStatus.PENDING, TaskStatus.PROCESSING) and t.node_key in token.path[t_idx + 1:]:
                self._transition_task(state, t, TaskStatus.CANCELED, None)

        state.events.append(
            EngineEvent("workflow_rejected_back", node.key, {"from": node.key, "to": target})
        )
        # 在目标节点重建任务；path 截断到 target（含），_enter_node 会再次 append 以递增轮次
        token.current_key = target
        token.path = token.path[:t_idx] + ([target] if target in token.path else [])
        self._enter_node(state, token)

    # ---------- 内部：推进算法 ----------

    def _run(self, state: ExecutionState) -> None:
        """从 start 节点启动唯一初始 token 并持续推进直到停驻或终态。"""
        start_key = next(k for k, n in self._dsl.nodes.items() if n.type == NodeType.START)
        token = EngineToken(id=uuid4().hex, current_key=start_key)
        state.tokens[token.id] = token
        self._advance(state, token)

    def _advance(self, state: ExecutionState, token: EngineToken) -> None:
        """沿出边推进 token，直到遇到需要人工介入的节点或终态。

        网关分支选择、并行 fork、end 终态均在此分派（§1.3 通用算法）。
        """
        while True:
            node = self._dsl.nodes[token.current_key]
            ntype = node.type

            if isinstance(node, StartNode):
                # start 无业务语义：登记路径（驳回到发起人时 round 依赖此记录）后沿出边前进
                token.path.append(node.key)
                self._walk(state, token)
                continue

            if isinstance(node, EndNode):
                # 终态：回收 token 并记录完成事件
                self._complete_instance(state, token)
                return

            if isinstance(node, ApprovalNode):
                # 停驻节点：解析审批人并建任务，等待人工操作
                self._enter_node(state, token)
                return

            if isinstance(node, CCNode):
                result = self._resolvers.resolve(node.assignee, state.variables)
                state.events.append(
                    EngineEvent("node_entered", node.key, {"assignees": result.assignee_ids, "kind": "cc"})
                )
                self._walk(state, token)
                continue

            if isinstance(node, ExclusiveGatewayNode):
                self._route_exclusive(state, token, node)
                continue

            # 其余节点类型（并行/子流程/Webhook/脚本）在 M5 分阶段实装
            raise WorkflowConfigError(f"节点类型 {ntype.value} 尚未实装: {token.current_key}")

    def _walk(self, state: ExecutionState, token: EngineToken) -> None:
        """从当前节点沿唯一的普通出边移动 token。"""
        edges = self._out_edges.get(token.current_key, [])
        if len(edges) != 1:
            raise WorkflowConfigError(
                f"节点 {token.current_key} 应有且只有一条出边，实际 {len(edges)}"
            )
        token.current_key = edges[0].target

    def _route_exclusive(self, state: ExecutionState, token: EngineToken, gw: ExclusiveGatewayNode) -> None:
        """排他网关：按 branches 顺序求值取首个命中，全不命中走 default。

        Raises:
            WorkflowConfigError: 无 default 分支且全部条件不命中。
        """
        edges_by_branch = {e.branch_key: e for e in self._out_edges.get(gw.key, []) if e.branch_key}
        selected: str | None = None
        for branch in gw.branches:
            if self._evaluate_sync(branch.condition, state):
                selected = branch.branch_key
                break
        if selected is None:
            selected = gw.default_branch_key
        if selected not in edges_by_branch:
            raise WorkflowConfigError(f"排他网关 {gw.key} 无可用分支（选中 '{selected}' 但缺少出边）")

        state.events.append(
            EngineEvent("gateway_routed", gw.key, {"branch": selected, "conditionResult": True})
        )
        token.current_key = edges_by_branch[selected].target

    def _evaluate_sync(self, expression: str, state: ExecutionState) -> bool:
        """同步求值条件表达式（内存版引擎）。

        求值失败（未定义变量/语法错误）按"不命中"处理并记录警告事件，
        与详细设计 §2.2 的降级策略一致；50ms 超时保护在 M3 接入异步运行时后启用。
        """
        import simpleeval

        try:
            # simpleeval 的变量注入在构造器上（eval 不接受 names 参数）
            evaluator = simpleeval.SimpleEval(names=state.variables)
            return bool(evaluator.eval(expression))
        except Exception as exc:  # noqa: BLE001 —— 降级语义要求吞掉具体异常
            state.events.append(
                EngineEvent("gateway_routed", None, {"warning": f"条件求值失败按不命中处理: {exc}"})
            )
            return False

    # ---------- 内部：任务与会签 ----------

    def _enter_node(self, state: ExecutionState, token: EngineToken) -> None:
        """进入停驻节点：解析审批人、建任务、登记 node_entered 事件。

        start 节点也可能成为"任务节点"——驳回到发起人时，需要给发起人
        重建 start 任务（可修改表单后重新提交）。
        """
        node = self._dsl.nodes[token.current_key]
        if not isinstance(node, (ApprovalNode, StartNode)):
            raise WorkflowConfigError(f"节点 {node.key} 类型 {node.type.value} 不产生任务")
        token.path.append(node.key)
        # round = 该节点在当前执行路径中出现的次数（第 N 次进入即第 N 轮）
        round_no = token.path.count(node.key)

        if isinstance(node, StartNode):
            # 发起人重提交任务：处理人固定为发起人
            task_id = uuid4().hex
            state.tasks[task_id] = EngineTask(
                id=task_id, node_key=node.key, node_name=node.name,
                assignee_id=str(state.variables.get("$_initiator", "")),
                round=round_no,
            )
            state.events.append(
                EngineEvent("node_entered", node.key, {"assignees": [state.variables.get("$_initiator")]})
            )
            return

        result = self._resolvers.resolve(node.assignee, state.variables)
        if result.auto_pass:
            # fallback=auto_pass：跳过人工审批，先移出本节点再推进（否则原地死循环）
            state.events.append(
                EngineEvent("node_entered", node.key, {"autoPass": True})
            )
            self._finish_node(state, node.key)
            self._walk(state, token)
            self._advance(state, token)
            return

        group_id = uuid4().hex if node.counter_sign else None
        for assignee in result.assignee_ids:
            task_id = uuid4().hex
            state.tasks[task_id] = EngineTask(
                id=task_id, node_key=node.key, node_name=node.name,
                assignee_id=assignee, counter_sign_group_id=group_id,
                round=round_no,
            )
        state.events.append(
            EngineEvent("node_entered", node.key, {"assignees": result.assignee_ids})
        )

    def _counter_sign_done(self, state: ExecutionState, node: object, task: EngineTask) -> bool:
        """检查会签规则是否达成；达成时取消组内其余 pending 任务。

        Returns:
            True=节点可推进；False=等待其余会签人。
        """
        mode = getattr(node, "counter_sign", None)  # start 节点（发起人重提交）无会签概念
        if mode is None or task.counter_sign_group_id is None:
            return True  # 非会签（单人/或签），首个明确动作即定向

        group = [
            t for t in state.tasks.values()
            if t.counter_sign_group_id == task.counter_sign_group_id
        ]
        total = len(group)
        approved = sum(1 for t in group if t.status == TaskStatus.APPROVED)
        rejected = sum(1 for t in group if t.status == TaskStatus.REJECTED)

        if mode == CounterSignMode.ALL:
            done = rejected > 0 or approved == total
            passed = rejected == 0 and approved == total
        elif mode == CounterSignMode.ANY:
            done = approved > 0 or rejected == total
            passed = approved > 0
        else:  # ratio
            import math

            need = math.ceil(total * (getattr(node, "counter_sign_ratio", None) or 1))
            done = approved >= need or rejected > total - need
            passed = approved >= need

        if done and passed:
            for t in group:  # 取消组内其余未处理任务
                if t.status == TaskStatus.PENDING:
                    self._transition_task(state, t, TaskStatus.CANCELED, None)
        return done and passed

    def _finish_node(self, state: ExecutionState, node_key: str) -> None:
        """记录节点完成事件。"""
        state.events.append(EngineEvent("node_completed", node_key))

    def _complete_instance(self, state: ExecutionState, token: EngineToken) -> None:
        """实例进入完成终态。"""
        ensure_instance_transition(state.status, InstanceStatus.COMPLETED)
        state.status = InstanceStatus.COMPLETED
        state.finished_at_reason = "normal_end"
        state.tokens.pop(token.id, None)
        state.events.append(EngineEvent("workflow_completed", "end"))

    def _transition_task(
        self, state: ExecutionState, task: EngineTask, target: TaskStatus, action: TaskAction | None
    ) -> None:
        """任务状态迁移的统一入口（含非法迁移拦截与事件记录）。"""
        ensure_task_transition(task.status, target)
        task.status = target
        if action is not None:
            task.action = action
        event_type = {
            TaskStatus.APPROVED: "task_approved",
            TaskStatus.REJECTED: "task_rejected",
            TaskStatus.TRANSFERRED: "task_transferred",
            TaskStatus.CANCELED: "task_canceled",
        }.get(target)
        if event_type:
            state.events.append(
                EngineEvent(event_type, task.node_key, {"taskId": task.id, "action": action.value if action else None})
            )

    def _token_of_node(self, state: ExecutionState, node_key: str) -> EngineToken:
        """定位停留在指定节点的 token（M2 单 token 场景；并行多 token 在 M5 扩展）。"""
        for token in state.tokens.values():
            if token.current_key == node_key:
                return token
        raise WorkflowConfigError(f"找不到停留在节点 {node_key} 的 token")

    def _resolve_reject_target(
        self, state: ExecutionState, from_key: str, policy: str | None
    ) -> str:
        """解析驳回目标节点 key。

        支持：initiator→start / previous→路径上一个审批节点 / node:xxx / 直接 key。
        """
        token = self._token_of_node(state, from_key)
        if policy in (None, "initiator"):
            return next(k for k, n in self._dsl.nodes.items() if n.type == NodeType.START)
        if policy == "previous":
            approvals = [k for k in reversed(token.path[:-1])]
            if not approvals:
                raise WorkflowConfigError("路径上没有可驳回的历史审批节点")
            return approvals[0]
        if policy.startswith("node:"):
            return policy[5:]
        return policy
