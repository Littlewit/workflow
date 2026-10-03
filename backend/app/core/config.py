"""应用配置模块。

通过 pydantic-settings 从环境变量 / .env 加载配置，
开发阶段默认使用 SQLite（aiosqlite），生产环境通过环境变量切换 PostgreSQL。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置项（均可被环境变量覆盖，前缀 WF_）。"""

    model_config = SettingsConfigDict(env_prefix="WF_", env_file=".env", extra="ignore")

    app_name: str = "common-workflow"
    debug: bool = True

    # 开发阶段 SQLite；生产用 WF_DATABASE_URL 切换，如 postgresql+asyncpg://...
    database_url: str = "sqlite+aiosqlite:///./workflow.db"

    # Redis（幂等存储/分布式锁/ARQ 队列）；开发环境可不启动，服务自动用内存实现
    redis_url: str = "redis://localhost:6379"

    # JWT 认证：默认密钥仅用于本地开发（≥32 字节满足 HS256 要求），生产必须覆盖
    jwt_secret: str = "dev-only-secret-0123456789abcdef0123456789abcdef"
    jwt_expire_minutes: int = 720


@lru_cache
def get_settings() -> Settings:
    """返回全局单例配置（lru_cache 保证进程内只解析一次环境变量）。"""
    return Settings()
