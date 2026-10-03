"""集成测试夹具：基于全局 sqlite_db 构造应用服务。"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.workflow_service import WorkflowService


@pytest.fixture()
async def service(sqlite_db) -> WorkflowService:
    """基于隔离库构造应用服务。"""
    engine = create_async_engine(sqlite_db)
    return WorkflowService(async_sessionmaker(engine, expire_on_commit=False), admin_ids=["admin-1"])
