"""执行器闭环测试（T2.3/T2.4/T2.5）：串行、分支、驳回、会签、fallback。

不依赖任何 IO 组件，全部为纯逻辑测试。
"""

import pytest

from app.domain.dsl import CounterSignMode
from app.domain.enums import InstanceStatus, TaskStatus
from app.engine.exceptions import AssigneeResolveError
from app.engine.executor import WorkflowEngine
from app.engine.resolvers import ResolverRegistry
from tests.engine.conftest import branch_dsl, simple_serial_dsl


def _pending_tasks(state) -> list:
    """取全部 pending 任务。"""
    return [t for t in state.tasks.values() if t.status == TaskStatus.PENDING]


class TestSerialFlow:
    """串行流程闭环：start -> approval -> end。"""

    def test_start_creates_first_task(self) -> None:
        """发起后应在首个审批节点创建任务。"""
        state = WorkflowEngine(simple_serial_dsl()).start(initiator_id="u1", variables={"days": 1})
        pending = _pending_tasks(state)
        assert len(pending) == 1
        assert pending[0].node_key == "approve_1"
        assert pending[0].assignee_id == "user-of-approve_1"
        assert state.status == InstanceStatus.RUNNING

    def test_approve_completes_workflow(self) -> None:
        """审批同意后实例应到达完成终态。"""
        engine = WorkflowEngine(simple_serial_dsl())
        state = engine.start(initiator_id="u1")
        engine.approve(state, _pending_tasks(state)[0].id)
        assert state.status == InstanceStatus.COMPLETED
        # 事件流应完整记录生命周期
        types = [e.event_type for e in state.events]
        assert types[0] == "workflow_started"
        assert "node_completed" in types
        assert types[-1] == "workflow_completed"

    def test_double_approve_rejected(self) -> None:
        """重复审批同一任务应抛非法迁移（幂等防线）。"""
        engine = WorkflowEngine(simple_serial_dsl())
        state = engine.start(initiator_id="u1")
        task_id = _pending_tasks(state)[0].id
        engine.approve(state, task_id)
        with pytest.raises(Exception, match="不允许"):
            engine.approve(state, task_id)


class TestBranchFlow:
    """排他网关分支选择。"""

    def test_condition_hit_routes_vip(self) -> None:
        """days=5 命中 'days > 3'，应走 VIP 审批分支。"""
        state = WorkflowEngine(branch_dsl()).start(initiator_id="u1", variables={"days": 5})
        pending = _pending_tasks(state)
        assert len(pending) == 1
        assert pending[0].node_key == "approve_vip"

    def test_condition_miss_routes_default(self) -> None:
        """days=1 不命中条件，应走 default（普通审批）分支。"""
        state = WorkflowEngine(branch_dsl()).start(initiator_id="u1", variables={"days": 1})
        assert _pending_tasks(state)[0].node_key == "approve_normal"


class TestRejectFlow:
    """驳回与重走。"""

    def test_reject_to_initiator_recreates_start_task(self) -> None:
        """驳回到发起人：当前任务 rejected，start 节点重建任务（round=2）。"""
        engine = WorkflowEngine(simple_serial_dsl())
        state = engine.start(initiator_id="u1")
        task = _pending_tasks(state)[0]

        engine.reject(state, task.id, target_node_key="start")
        assert task.status == TaskStatus.REJECTED
        pending = _pending_tasks(state)
        assert len(pending) == 1
        assert pending[0].node_key == "start"
        assert pending[0].round == 2  # 第二轮
        assert any(e.event_type == "workflow_rejected_back" for e in state.events)

    def test_rejected_task_cannot_be_approved(self) -> None:
        """已驳回任务不可再同意（状态机兜底）。"""
        engine = WorkflowEngine(simple_serial_dsl())
        state = engine.start(initiator_id="u1")
        task = _pending_tasks(state)[0]
        engine.reject(state, task.id, target_node_key="start")
        with pytest.raises(Exception, match="不允许"):
            engine.approve(state, task.id)


class TestCounterSign:
    """会签规则判定。"""

    def _sign_all_dsl(self):
        """双人全签 DSL（保持 nodeKey 与边引用一致）。"""
        dsl = simple_serial_dsl().model_copy(deep=True)
        node = dsl.nodes["approve_1"]
        node.counter_sign = CounterSignMode.ALL
        node.assignee.params = {"user_ids": ["u1", "u2"]}
        return dsl

    def test_all_sign_requires_both(self) -> None:
        """ALL 会签：两人中一人同意后流程不推进，全部同意才完成。"""
        engine = WorkflowEngine(self._sign_all_dsl())
        state = engine.start(initiator_id="u0")
        tasks = _pending_tasks(state)
        assert len(tasks) == 2
        # 两人共享会签分组
        assert tasks[0].counter_sign_group_id == tasks[1].counter_sign_group_id

        engine.approve(state, tasks[0].id)
        assert state.status == InstanceStatus.RUNNING  # 1/2，等待
        assert tasks[1].status == TaskStatus.PENDING

        engine.approve(state, tasks[1].id)
        assert state.status == InstanceStatus.COMPLETED
        # 达成后组内无残留 pending
        assert not _pending_tasks(state)


class TestFallback:
    """审批人解析失败兜底。"""

    def test_error_fallback_raises(self) -> None:
        """fallback=error 且解析为空时应抛 AssigneeResolveError。"""
        dsl = simple_serial_dsl().model_copy(deep=True)
        dsl.nodes["approve_1"].assignee.mode = "role"  # 角色表为空 → 解析为空
        with pytest.raises(AssigneeResolveError):
            WorkflowEngine(dsl, ResolverRegistry()).start(initiator_id="u1")

    def test_auto_pass_fallback_skips_node(self) -> None:
        """fallback=auto_pass：跳过审批直达 end。"""
        dsl = simple_serial_dsl().model_copy(deep=True)
        node = dsl.nodes["approve_1"]
        node.assignee.mode = "role"
        node.assignee.fallback.action = "auto_pass"
        state = WorkflowEngine(dsl, ResolverRegistry()).start(initiator_id="u1")
        assert state.status == InstanceStatus.COMPLETED
