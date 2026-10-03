"""应用层业务异常：带错误码，供 M4 API 层映射 HTTP 状态。"""

from app.engine.exceptions import EngineError


class ApplicationError(Exception):
    """应用层异常基类。

    Attributes:
        code: 错误码（详细设计 §3.1 错误码总表）。
        message: 人读信息。
        details: 附加明细（如 DSL 校验逐条错误）。
    """

    def __init__(self, code: int, message: str, details: list | dict | None = None) -> None:
        """初始化错误码、信息与明细。"""
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


class DefinitionNotPublishedError(ApplicationError):
    """流程未发布/已停用（41002）。"""

    def __init__(self, code: str) -> None:
        """构造 41002。"""
        super().__init__(41002, f"流程定义未发布或已停用: {code}")


class BusinessKeyDuplicateError(ApplicationError):
    """businessKey 重复发起（42001）。"""

    def __init__(self, business_key: str) -> None:
        """构造 42001。"""
        super().__init__(42001, f"该业务单据已发起过流程: {business_key}")


class InstanceNotFoundError(ApplicationError):
    """实例不存在（42003）。"""

    def __init__(self, instance_id: str) -> None:
        """构造 42003。"""
        super().__init__(42003, f"流程实例不存在: {instance_id}")


class TaskNotFoundError(ApplicationError):
    """任务不存在（43001）。"""

    def __init__(self, task_id: str) -> None:
        """构造 43001。"""
        super().__init__(43001, f"任务不存在: {task_id}")


class NotAssigneeError(ApplicationError):
    """非处理人（43101）。"""

    def __init__(self, user_id: str) -> None:
        """构造 43101。"""
        super().__init__(43101, f"用户 {user_id} 不是该任务的处理人")


class TaskConflictError(ApplicationError):
    """任务状态已变化/实例流转冲突（43102/42100）。"""

    def __init__(self, code: int, message: str) -> None:
        """构造 43102 或 42100。"""
        super().__init__(code, message)


class DuplicateOperationError(ApplicationError):
    """operationId 重复提交（42103），携带首次结果由调用方决定返回。"""

    def __init__(self, operation_id: str) -> None:
        """构造 42103。"""
        super().__init__(42103, f"重复的操作请求: {operation_id}")


class EngineRuntimeError(ApplicationError):
    """引擎内核错误透传（50010）。"""

    def __init__(self, err: EngineError) -> None:
        """包装引擎异常。"""
        super().__init__(50010, str(err))
