"""监控看板统计 API 测试（M7）。"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.container import get_definition_service, get_stats_service, get_workflow_service
from app.application.definition_service import DefinitionService
from app.application.stats_service import StatsService
from app.application.workflow_service import WorkflowService
from app.main import create_app
from tests.engine.conftest import simple_serial_dsl


@pytest.fixture()
def app_and_client(sqlite_db):
    """应用 + 客户端 + 服务工厂。"""
    application = create_app()
    factory = async_sessionmaker(create_async_engine(sqlite_db), expire_on_commit=False)
    application.dependency_overrides[get_workflow_service] = lambda: WorkflowService(
        factory, admin_ids=["admin-1"]
    )
    application.dependency_overrides[get_definition_service] = lambda: DefinitionService(factory)
    application.dependency_overrides[get_stats_service] = lambda: StatsService(factory)
    return application, factory, factory


async def login(client: AsyncClient, username: str, password: str) -> str:
    """登录拿 token。"""
    resp = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    return resp.json()["data"]["token"]


@pytest.mark.asyncio
async def test_overview_and_bottlenecks(app_and_client) -> None:
    """跑通两个实例后：总览计数正确、瓶颈表有数据、非管理员被拒。"""
    application, factory, _ = app_and_client
    # 前置：发布定义 + 发起并完成 1 个实例 + 1 个运行中实例
    dsl = simple_serial_dsl()
    from app.infra.models.definition import WorkflowDefinition, WorkflowDefinitionVersion

    async with factory() as s:
        s.add_all([
            WorkflowDefinition(id="d1", code=dsl.code, name="t", status="published", current_version=1),
            WorkflowDefinitionVersion(
                id="v1", definition_id="d1", version=1,
                dsl=dsl.model_dump(mode="json"), dsl_hash="x",
            ),
        ])
        await s.commit()

    service = WorkflowService(factory, admin_ids=["admin-1"])
    done = await service.start_instance(definition_code=dsl.code, initiator_id="boss-1")
    await service.approve(done["tasks"][0]["taskId"], "user-of-approve_1")
    await service.start_instance(definition_code=dsl.code, initiator_id="boss-1")

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        token = await login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {token}"}

        overview = (await client.get("/api/v1/stats/overview", headers=headers)).json()["data"]
        assert overview["instanceCounts"]["completed"] == 1
        assert overview["instanceCounts"]["running"] == 1
        assert overview["taskCounts"]["approved"] == 1
        assert overview["activeInstances"] == 1
        assert overview["avgInstanceDurationMs"] is not None

        bottlenecks = (await client.get("/api/v1/stats/bottlenecks", headers=headers)).json()["data"]
        assert len(bottlenecks) >= 1
        assert {"nodeName", "count", "avgStayMs"} <= set(bottlenecks[0])

        # 非管理员访问 → 403
        bob = await login(client, "bob", "bob123")
        resp = await client.get("/api/v1/stats/overview", headers={"Authorization": f"Bearer {bob}"})
        assert resp.status_code == 403
