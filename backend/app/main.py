"""FastAPI 应用入口。

装配中间件、统一异常处理、路由与生命周期；保持薄层，业务逻辑收敛在
application/engine 层（T4.5：错误码映射 + traceId）。
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.response import current_trace_id, new_trace_id
from app.api.v1.router import api_router
from app.application.errors import ApplicationError
from app.core.config import get_settings
from app.engine.exceptions import (
    AssigneeResolveError,
    IllegalTransitionError,
    WorkflowConfigError,
)

# 应用错误码 → HTTP 状态映射（详细设计 §3.1）
_HTTP_STATUS: dict[int, int] = {
    40001: 401, 40003: 403, 40005: 401,
    41001: 422, 41002: 409, 41003: 404, 41004: 409, 41005: 409, 41006: 422,
    42001: 409, 42002: 422, 42003: 404,
    42100: 423, 42101: 409, 42102: 409, 42103: 409,
    43001: 404, 43101: 403, 43102: 409, 43103: 422,
    44001: 502, 50000: 500, 50010: 500,
}


def _http_status(code: int) -> int:
    """错误码转 HTTP 状态（未登记的 42xxx/43xxx 默认 400）。"""
    return _HTTP_STATUS.get(code, 400)


def _error_body(code: int, message: str, details=None) -> dict:
    """统一错误响应体。"""
    return {"code": code, "message": message, "details": details, "traceId": current_trace_id()}


def create_app() -> FastAPI:
    """应用工厂：便于测试时创建独立实例（不依赖模块级全局状态）。"""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        # OpenAPI 文档自动生成，作为前后端类型同构的事实源
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    @app.middleware("http")
    async def trace_middleware(request: Request, call_next):
        """为每个请求生成 traceId 并回写响应头，便于全链路追踪。"""
        new_trace_id()
        response = await call_next(request)
        response.headers["X-Trace-Id"] = current_trace_id()
        return response

    @app.exception_handler(ApplicationError)
    async def app_error_handler(request: Request, exc: ApplicationError) -> JSONResponse:
        """应用层异常 → 统一错误体。"""
        return JSONResponse(
            status_code=_http_status(exc.code),
            content=_error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(IllegalTransitionError)
    async def transition_error_handler(request: Request, exc: IllegalTransitionError) -> JSONResponse:
        """非法状态迁移 → 43102（409）。"""
        return JSONResponse(status_code=409, content=_error_body(43102, str(exc)))

    @app.exception_handler(AssigneeResolveError)
    async def assignee_error_handler(request: Request, exc: AssigneeResolveError) -> JSONResponse:
        """审批人解析失败 → 43103（422）。"""
        return JSONResponse(status_code=422, content=_error_body(43103, str(exc)))

    @app.exception_handler(WorkflowConfigError)
    async def config_error_handler(request: Request, exc: WorkflowConfigError) -> JSONResponse:
        """DSL 配置缺陷 → 50010（500），需管理员修复定义。"""
        return JSONResponse(status_code=500, content=_error_body(50010, str(exc)))

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
