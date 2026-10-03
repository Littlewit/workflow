"""集成测试夹具：真实 SQLite 文件库 + 完整迁移链。"""

import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.workflow_service import WorkflowService

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture()
def sqlite_db(tmp_path) -> str:
    """创建独立 SQLite 文件库并跑完整迁移（每个测试隔离）。"""
    db_path = tmp_path / "test.db"
    url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    env = {**os.environ, "WF_DATABASE_URL": url, "PYTHONUTF8": "1"}
    # 迁移通过 alembic 子进程执行，保证与真实部署路径一致
    for cmd in (["upgrade", "head"],):
        subprocess.run(
            [str(BACKEND_DIR / ".venv/Scripts/alembic.exe"), *cmd],
            cwd=BACKEND_DIR, check=True, env=env, capture_output=True,
        )
    return url


@pytest.fixture()
async def service(sqlite_db) -> WorkflowService:
    """基于隔离库构造应用服务。"""
    engine = create_async_engine(sqlite_db)
    return WorkflowService(async_sessionmaker(engine, expire_on_commit=False), admin_ids=["admin-1"])
