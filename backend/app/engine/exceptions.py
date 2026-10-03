"""引擎内核异常体系。

约定：
- IllegalTransitionError / AssigneeResolveError 等属于可预期运行时错误，API 层映射为 4xx；
- WorkflowConfigError 属于 DSL 配置缺陷（如网关无命中分支），引擎将其上报为
  实例 suspended + 告警（详细设计 §3.2 故障场景）。
"""


class EngineError(Exception):
    """引擎异常基类。"""


class IllegalTransitionError(EngineError):
    """非法状态迁移：违反状态机迁移表。"""


class WorkflowConfigError(EngineError):
    """DSL 配置缺陷导致流转无法继续（网关无命中分支等）。"""


class AssigneeResolveError(EngineError):
    """审批人解析失败（mode 未注册 / 解析结果为空且 fallback=error）。"""


class ExpressionError(EngineError):
    """条件表达式求值失败（语法错误 / 超时 / 引用未定义变量）。"""
