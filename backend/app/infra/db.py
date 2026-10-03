"""数据库引擎与 Session 工厂（异步）。

跨库兼容：开发 SQLite(aiosqlite) / 生产 PostgreSQL(asyncpg)。
SQLAlchemy 2.0 的 Uuid/JSON/DateTime 类型在两种后端上均可工作。
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    """全部 ORM 模型的声明基类。"""


# engine 延迟到首次调用时创建，避免导入期副作用（便于测试替换连接串）
_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    """获取（惰性创建的）全局异步引擎。"""
    global _engine
    if _engine is None:
        # pool_pre_ping：借出连接前探测，规避 SQLite/PG 长连接失效
        _engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """获取 Session 工厂；expire_on_commit=False 便于提交后仍可读取属性。"""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_db() -> AsyncSession:
    """FastAPI 依赖：请求级 Session，随请求结束自动关闭。"""
    async with get_session_factory()() as session:
        yield session
