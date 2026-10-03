"""服务容器：API 层获取应用服务的入口（便于测试时依赖覆盖）。"""

from functools import lru_cache

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.definition_service import DefinitionService
from app.application.workflow_service import WorkflowService
from app.core.config import get_settings


@lru_cache
def get_session_factory() -> async_sessionmaker:
    """全局会话工厂（进程内单例，绑定配置中的数据库连接串）。"""
    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


def get_workflow_service() -> WorkflowService:
    """工作流用例服务（FastAPI 依赖，测试可 override）。"""
    return WorkflowService(get_session_factory(), admin_ids=["admin-1"])


def get_definition_service() -> DefinitionService:
    """流程定义用例服务（FastAPI 依赖，测试可 override）。"""
    return DefinitionService(get_session_factory())
