"""测试全局夹具：隔离 SQLite 库 + 完整迁移链。"""

import os
import subprocess
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture()
def sqlite_db(tmp_path) -> str:
    """创建独立 SQLite 文件库并跑完整迁移（每个测试隔离）。"""
    db_path = tmp_path / "test.db"
    url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    env = {**os.environ, "WF_DATABASE_URL": url, "PYTHONUTF8": "1"}
    # 迁移通过 alembic 子进程执行，保证与真实部署路径一致
    subprocess.run(
        [str(BACKEND_DIR / ".venv/Scripts/alembic.exe"), "upgrade", "head"],
        cwd=BACKEND_DIR, check=True, env=env, capture_output=True,
    )
    return url
