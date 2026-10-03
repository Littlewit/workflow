"""性能压测脚本（M7）：流转延迟 + 并发发起吞吐。

对应非功能需求（需求文档 §4）：单节点流转 < 50ms；1000+ QPS 流程发起。
说明：默认 SQLite 为单文件开发库，QPS 数字仅作本地基线；达成 1000+ QPS
指标需 PostgreSQL + 多 worker 部署（压测工具与场景不变）。

用法：
  .venv\\Scripts\\python.exe scripts/benchmark.py            # 默认 200 流 / 并发 50
  .venv\\Scripts\\python.exe scripts/benchmark.py 500 100

场景：
  A. 流转延迟——串行跑 N 个完整周期（发起+审批），统计 p50/p95/p99；
  B. 并发发起——信号量限流的并发发起，统计吞吐 QPS。
"""

import asyncio
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["PYTHONUTF8"] = "1"

import httpx  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


def percentile(sorted_values: list[float], p: float) -> float:
    """计算百分位数（线性插值）。"""
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, int(round(p / 100 * (len(sorted_values) - 1))))
    return sorted_values[idx]


async def main(n_flows: int = 200, concurrency: int = 50) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.api.container import get_definition_service, get_workflow_service
    from app.application.definition_service import DefinitionService
    from app.application.workflow_service import WorkflowService
    from app.main import create_app
    from tests.engine.conftest import simple_serial_dsl

    # ---------- 环境：独立 SQLite + 迁移 + 发布定义 ----------
    db_path = Path(tempfile.mkdtemp()) / "bench.db"
    url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    subprocess.run(
        [str(BACKEND_DIR / ".venv/Scripts/alembic.exe"), "upgrade", "head"],
        cwd=BACKEND_DIR, env={**os.environ, "WF_DATABASE_URL": url},
        check=True, capture_output=True,
    )
    factory = async_sessionmaker(create_async_engine(url), expire_on_commit=False)
    dsl = simple_serial_dsl()
    dsl.code = f"wf_bench_{int(time.time())}"
    def_service = DefinitionService(factory)
    draft = await def_service.create_draft("admin-1", "", dsl.name, dsl.model_dump(mode="json"))
    await def_service.publish("admin-1", draft["definitionId"])

    app = create_app()
    app.dependency_overrides[get_workflow_service] = lambda: WorkflowService(factory, admin_ids=["admin-1"])
    app.dependency_overrides[get_definition_service] = lambda: DefinitionService(factory)

    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://bench") as client:
        login = await client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
        headers = {"Authorization": f"Bearer {login.json()['data']['token']}"}

        # ---------- 场景 A：流转延迟（串行完整周期） ----------
        latencies: list[float] = []
        for i in range(n_flows):
            t0 = time.perf_counter()
            start = await client.post(
                "/api/v1/instances",
                json={"definitionCode": dsl.code, "formData": {"days": 1}, "title": f"bench-{i}"},
                headers=headers,
            )
            task_id = start.json()["data"]["tasks"][0]["taskId"]
            await client.post(
                f"/api/v1/tasks/{task_id}/approve", json={"opinion": "ok"}, headers=headers
            )
            latencies.append((time.perf_counter() - t0) * 1000)
        latencies.sort()

        print("=" * 60)
        print(f"场景 A 流转延迟（完整周期 × {n_flows}）")
        print(f"  p50 = {percentile(latencies, 50):8.1f} ms   目标 < 50 ms")
        print(f"  p95 = {percentile(latencies, 95):8.1f} ms")
        print(f"  p99 = {percentile(latencies, 99):8.1f} ms")
        print(f"  max = {latencies[-1]:8.1f} ms")

        # ---------- 场景 B：并发发起吞吐 ----------
        semaphore = asyncio.Semaphore(concurrency)
        errors = 0
        error_samples: list[str] = []

        async def one_start(idx: int) -> None:
            nonlocal errors
            async with semaphore:
                try:
                    resp = await client.post(
                        "/api/v1/instances",
                        json={"definitionCode": dsl.code, "formData": {"days": 1}, "title": f"conc-{idx}"},
                        headers=headers,
                    )
                    if resp.status_code != 200:
                        errors += 1
                        if len(error_samples) < 3:
                            error_samples.append(f"{resp.status_code}: {resp.text[:80]}")
                except Exception as exc:  # noqa: BLE001 —— 压测需统计全部失败样本
                    errors += 1
                    if len(error_samples) < 3:
                        error_samples.append(str(exc)[:120])

        t0 = time.perf_counter()
        await asyncio.gather(*(one_start(i) for i in range(1000)))
        elapsed = time.perf_counter() - t0
        qps = 1000 / elapsed

        print("=" * 60)
        print(f"场景 B 并发发起（1000 次，并发上限 {concurrency}）")
        print(f"  耗时 = {elapsed:6.2f} s   吞吐 = {qps:7.0f} QPS   错误 = {errors}")
        for sample in error_samples:
            print(f"  错误样本: {sample}")
        print("  （1000+ QPS 目标：PostgreSQL + 多 worker 部署下达成；")
        print("    SQLite 单文件库并发写有锁冲突，为本机基线参考）")
        print("=" * 60)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    c = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    asyncio.run(main(n, c))
