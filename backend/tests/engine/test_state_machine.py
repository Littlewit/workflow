"""状态机迁移表测试（T2.2）：非法迁移必须被拦截。"""

import pytest

from app.domain.enums import InstanceStatus, TaskStatus
from app.engine.exceptions import IllegalTransitionError
from app.engine.state_machine import ensure_instance_transition, ensure_task_transition


class TestInstanceTransitions:
    """实例状态迁移规则。"""

    def test_running_can_complete(self) -> None:
        """running → completed 合法。"""
        ensure_instance_transition(InstanceStatus.RUNNING, InstanceStatus.COMPLETED)

    def test_terminal_states_have_no_out_edges(self) -> None:
        """三个终态（completed/terminated/canceled）不允许再迁移。"""
        for source in (InstanceStatus.COMPLETED, InstanceStatus.TERMINATED, InstanceStatus.CANCELED):
            with pytest.raises(IllegalTransitionError):
                ensure_instance_transition(source, InstanceStatus.RUNNING)

    def test_completed_cannot_suspend(self) -> None:
        """completed → suspended 非法。"""
        with pytest.raises(IllegalTransitionError, match="不允许"):
            ensure_instance_transition(InstanceStatus.COMPLETED, InstanceStatus.SUSPENDED)


class TestTaskTransitions:
    """任务状态迁移规则。"""

    def test_pending_to_approved(self) -> None:
        """pending → approved 合法。"""
        ensure_task_transition(TaskStatus.PENDING, TaskStatus.APPROVED)

    def test_approved_is_terminal(self) -> None:
        """approved 是终态，不可再迁移。"""
        with pytest.raises(IllegalTransitionError):
            ensure_task_transition(TaskStatus.APPROVED, TaskStatus.PENDING)

    def test_canceled_cannot_be_processed(self) -> None:
        """canceled → processing 非法（驳回后被取消的任务不可再操作）。"""
        with pytest.raises(IllegalTransitionError):
            ensure_task_transition(TaskStatus.CANCELED, TaskStatus.PROCESSING)
