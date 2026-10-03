"""FastAPI 应用入口。

装配中间件、路由与生命周期；保持薄层，业务逻辑收敛在 application/engine 层。
"""

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import get_settings


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
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
