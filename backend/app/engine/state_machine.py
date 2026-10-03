"""状态机执行器：集中校验实例/任务状态迁移。

对应详细设计文档第三部分 §1.2：所有写路径必须经此校验。
"""

from app.domain.enums import (
    INSTANCE_TRANSITIONS,
    TASK_TRANSITIONS,
    InstanceStatus,
    TaskStatus,
)
from app.engine.exceptions import IllegalTransitionError


def ensure_instance_transition(source: InstanceStatus, target: InstanceStatus) -> None:
    """校验实例状态迁移，非法迁移抛 IllegalTransitionError。

    Raises:
        IllegalTransitionError: 迁移不在 INSTANCE_TRANSITIONS 表中。
    """
    if target not in INSTANCE_TRANSITIONS[source]:
        raise IllegalTransitionError(
            f"实例状态不允许从 {source.value} 迁移到 {target.value}"
        )


def ensure_task_transition(source: TaskStatus, target: TaskStatus) -> None:
    """校验任务状态迁移，非法迁移抛 IllegalTransitionError。

    Raises:
        IllegalTransitionError: 迁移不在 TASK_TRANSITIONS 表中。
    """
    if target not in TASK_TRANSITIONS[source]:
        raise IllegalTransitionError(
            f"任务状态不允许从 {source.value} 迁移到 {target.value}"
        )
