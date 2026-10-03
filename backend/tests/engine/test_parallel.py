"""并行网关测试（M5-T5.5）：AND 汇合 / OR 汇合 / 分支互不影响。"""

from app.domain.enums import InstanceStatus, TaskStatus
from app.engine.executor import WorkflowEngine
from tests.engine.conftest import parallel_dsl


def _pending(state) -> list:
    """取全部 pending 任务。"""
    return [t for t in state.tasks.values() if t.status == TaskStatus.PENDING]


class TestParallelGateway:
    """并行分叉与汇合。"""

    def test_split_creates_both_branch_tasks(self) -> None:
        """分叉后两支各产生一个待办任务。"""
        state = WorkflowEngine(parallel_dsl()).start(initiator_id="u0")
        pending = _pending(state)
        assert {t.node_key for t in pending} == {"pa", "pb"}
        assert state.status == InstanceStatus.RUNNING

    def test_and_join_waits_all_branches(self) -> None:
        """AND 汇合：一支通过后等待，两支全通过才完成。"""
        engine = WorkflowEngine(parallel_dsl("AND"))
        state = engine.start(initiator_id="u0")
        tasks = {t.node_key: t.id for t in state.tasks.values()}

        engine.approve(state, tasks["pa"])
        assert state.status == InstanceStatus.RUNNING  # 1/2，等待另一支

        engine.approve(state, tasks["pb"])
        assert state.status == InstanceStatus.COMPLETED  # 汇合放行 → end

    def test_or_join_releases_on_first_arrival(self) -> None:
        """OR 汇合：任一支到达即放行，其余分支任务被取消。"""
        engine = WorkflowEngine(parallel_dsl("OR"))
        state = engine.start(initiator_id="u0")
        tasks = {t.node_key: t.id for t in state.tasks.values()}

        engine.approve(state, tasks["pa"])
        assert state.status == InstanceStatus.COMPLETED
        # 其余分支的 pending 任务应被取消
        assert all(t.status != TaskStatus.PENDING for t in state.tasks.values())

    def test_one_branch_does_not_affect_other(self) -> None:
        """驳回场景之外的隔离性：分支A的 token 与B独立（两任务无共享会签组）。"""
        state = WorkflowEngine(parallel_dsl()).start(initiator_id="u0")
        tasks = _pending(state)
        assert tasks[0].counter_sign_group_id is None
        assert tasks[0].token_id != tasks[1].token_id
