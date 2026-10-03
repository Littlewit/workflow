"""统一响应包裹与 traceId 上下文。"""

from contextvars import ContextVar
from uuid import uuid4

# 请求级 traceId（中间件设置，异常处理器与响应包裹共用）
_trace_id: ContextVar[str] = ContextVar("trace_id", default="")


def new_trace_id() -> str:
    """生成并写入上下文的新 traceId。"""
    tid = uuid4().hex[:16]
    _trace_id.set(tid)
    return tid


def current_trace_id() -> str:
    """读取当前 traceId（可能为空串）。"""
    return _trace_id.get()


def ok(data=None) -> dict:
    """成功响应包裹：{code:0, message:'ok', data, traceId}。"""
    return {"code": 0, "message": "ok", "data": data, "traceId": current_trace_id()}
