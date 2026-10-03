"""领域枚举与状态机迁移表。

对应详细设计文档 §3 数据字典：
- 实例状态：running ⇄ suspended；running → 终态；终态不可迁移
- 任务状态：pending/processing → 各终态；终态不可迁移

任何状态变更必须经 ensure_*_transition 校验，禁止绕过状态机直接改字段
（这是并发安全与数据一致性的第一道防线）。
"""

from enum import Enum


class InstanceStatus(str, Enum):
    """流程实例状态（详细设计 §3.1）。"""

    RUNNING = "running"
    SUSPENDED = "suspended"
    COMPLETED = "completed"  # 终态
    TERMINATED = "terminated"  # 终态
    CANCELED = "canceled"  # 终态


class TaskStatus(str, Enum):
    """任务状态（详细设计 §3.2）。"""

    PENDING = "pending"
    PROCESSING = "processing"
    APPROVED = "approved"  # 终态
    REJECTED = "rejected"  # 终态
    TRANSFERRED = "transferred"  # 终态
    CANCELED = "canceled"  # 终态
    TIMEOUT_AUTO = "timeout_auto"  # 终态


class TaskAction(str, Enum):
    """任务最终动作快照（审计用，与状态正交）。"""

    APPROVE = "approve"
    REJECT = "reject"
    TRANSFER = "transfer"
    DELEGATE = "delegate"
    AUTO_APPROVE = "auto_approve"
    AUTO_REJECT = "auto_reject"


# 实例状态合法迁移表（源状态 → 允许的目标状态集合）
INSTANCE_TRANSITIONS: dict[InstanceStatus, set[InstanceStatus]] = {
    InstanceStatus.RUNNING: {
        InstanceStatus.SUSPENDED,
        InstanceStatus.COMPLETED,
        InstanceStatus.TERMINATED,
        InstanceStatus.CANCELED,
    },
    InstanceStatus.SUSPENDED: {InstanceStatus.RUNNING, InstanceStatus.TERMINATED},
    # 终态无出边
    InstanceStatus.COMPLETED: set(),
    InstanceStatus.TERMINATED: set(),
    InstanceStatus.CANCELED: set(),
}

# 任务状态合法迁移表
TASK_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {
        TaskStatus.PROCESSING,
        TaskStatus.APPROVED,
        TaskStatus.REJECTED,
        TaskStatus.TRANSFERRED,
        TaskStatus.CANCELED,
        TaskStatus.TIMEOUT_AUTO,
    },
    TaskStatus.PROCESSING: {
        TaskStatus.APPROVED,
        TaskStatus.REJECTED,
        TaskStatus.TRANSFERRED,
    },
    TaskStatus.APPROVED: set(),
    TaskStatus.REJECTED: set(),
    TaskStatus.TRANSFERRED: set(),
    TaskStatus.CANCELED: set(),
    TaskStatus.TIMEOUT_AUTO: set(),
}


def is_instance_transition_valid(source: InstanceStatus, target: InstanceStatus) -> bool:
    """判断实例状态迁移是否合法。"""
    return target in INSTANCE_TRANSITIONS[source]


def is_task_transition_valid(source: TaskStatus, target: TaskStatus) -> bool:
    """判断任务状态迁移是否合法。"""
    return target in TASK_TRANSITIONS[source]
