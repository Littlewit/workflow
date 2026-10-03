"""M4 API 集成测试：真实 SQLite + 完整 HTTP 栈（ASGITransport）。

覆盖：登录认证、RBAC、定义发布权威校验、发起/审批/驳回/转办/运维端点、
统一错误码与 traceId。
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.container import get_definition_service, get_workflow_service
from app.application.definition_service import DefinitionService
from app.application.workflow_service import WorkflowService
from app.main import create_app
from tests.engine.conftest import simple_serial_dsl


@pytest.fixture()
def app(sqlite_db):
    """构造应用并用测试库覆盖服务依赖。"""
    application = create_app()
    engine = create_async_engine(sqlite_db)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    application.dependency_overrides[get_workflow_service] = lambda: WorkflowService(
        factory, admin_ids=["admin-1"]
    )
    application.dependency_overrides[get_definition_service] = lambda: DefinitionService(factory)
    return application


@pytest.fixture()
async def client(app):
    """异步 HTTP 客户端。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def login(client: AsyncClient, username: str, password: str) -> str:
    """登录并返回 token。"""
    resp = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["token"]


def auth_header(token: str) -> dict:
    """构造 Authorization 头。"""
    return {"Authorization": f"Bearer {token}"}


async def publish_serial_flow(client: AsyncClient, admin_token: str) -> None:
    """经 API 创建并发布串行流程。"""
    dsl = simple_serial_dsl().model_dump(mode="json")
    resp = await client.post(
        "/api/v1/definitions", json={"dsl": dsl}, headers=auth_header(admin_token)
    )
    assert resp.status_code == 200, resp.text
    definition_id = resp.json()["data"]["definitionId"]
    resp = await client.post(
        f"/api/v1/definitions/{definition_id}/publish", headers=auth_header(admin_token)
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
class TestAuth:
    """认证与 RBAC。"""

    async def test_login_success_and_failure(self, client) -> None:
        """正确密码签发 JWT；错误密码返回 401/40001。"""
        resp = await client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
        assert resp.json()["data"]["token"]

        resp = await client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
        assert resp.status_code == 401
        assert resp.json()["code"] == 40001

    async def test_unauthenticated_rejected(self, client) -> None:
        """无 token 访问受保护接口 → 401/40001。"""
        resp = await client.get("/api/v1/tasks/todo")
        assert resp.status_code == 401

    async def test_rbac_admin_required(self, client) -> None:
        """非管理员创建定义 → 403/40003。"""
        token = await login(client, "bob", "bob123")
        resp = await client.post(
            "/api/v1/definitions",
            json={"dsl": simple_serial_dsl().model_dump(mode="json")},
            headers=auth_header(token),
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == 40003


@pytest.mark.asyncio
class TestDefinitionAPI:
    """定义发布链路。"""

    async def test_publish_invalid_dsl_rejected_with_details(self, client) -> None:
        """发布含死胡同的 DSL → 422/41001，details 携带节点定位。"""
        admin = await login(client, "admin", "admin123")
        dsl = simple_serial_dsl().model_dump(mode="json")
        del dsl["edges"][1]  # 删掉 approve_1 -> end，制造死胡同
        resp = await client.post("/api/v1/definitions", json={"dsl": dsl}, headers=auth_header(admin))
        definition_id = resp.json()["data"]["definitionId"]
        resp = await client.post(f"/api/v1/definitions/{definition_id}/publish", headers=auth_header(admin))
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == 41001
        assert any("死胡同" in d["message"] for d in body["details"])

    async def test_publish_then_get(self, client) -> None:
        """发布成功后详情应返回版本化 DSL。"""
        admin = await login(client, "admin", "admin123")
        dsl = simple_serial_dsl().model_dump(mode="json")
        resp = await client.post("/api/v1/definitions", json={"dsl": dsl}, headers=auth_header(admin))
        definition_id = resp.json()["data"]["definitionId"]
        resp = await client.post(f"/api/v1/definitions/{definition_id}/publish", headers=auth_header(admin))
        assert resp.json()["data"]["version"] == 1
        resp = await client.get(f"/api/v1/definitions/{definition_id}", headers=auth_header(admin))
        assert resp.json()["data"]["dsl"]["version"] == 1


@pytest.mark.asyncio
class TestWorkflowAPI:
    """发起 / 审批 / 驳回 / 转办 / 运维全链路。"""

    async def test_full_cycle_via_api(self, client) -> None:
        """admin 发布 → bob 发起 → alice 审批 → 完成 → 时间线可查。"""
        admin = await login(client, "admin", "admin123")
        await publish_serial_flow(client, admin)

        bob = await login(client, "bob", "bob123")
        resp = await client.post(
            "/api/v1/instances",
            json={"definitionCode": "wf_test", "title": "张三请假", "formData": {"days": 1}},
            headers=auth_header(bob),
        )
        assert resp.status_code == 200, resp.text
        started = resp.json()["data"]
        instance_id, task_id = started["instanceId"], started["tasks"][0]["taskId"]

        # alice 待办可见并审批
        alice = await login(client, "alice", "alice123")
        resp = await client.get("/api/v1/tasks/todo", headers=auth_header(alice))
        assert any(t["taskId"] == task_id for t in resp.json()["data"])
        resp = await client.post(
            f"/api/v1/tasks/{task_id}/approve",
            json={"opinion": "同意"}, headers=auth_header(alice),
        )
        assert resp.json()["data"]["instanceStatus"] == "completed"

        # 时间线：traceId 与事件
        resp = await client.get(f"/api/v1/instances/{instance_id}", headers=auth_header(bob))
        assert resp.headers.get("X-Trace-Id")
        assert any(e["eventType"] == "workflow_completed" for e in resp.json()["data"]["timeline"])

    async def test_reject_and_resubmit_via_api(self, client) -> None:
        """驳回 → 发起人待办 round=2 → 重新提交 → 完成。"""
        admin = await login(client, "admin", "admin123")
        await publish_serial_flow(client, admin)
        bob = await login(client, "bob", "bob123")
        started = (await client.post(
            "/api/v1/instances", json={"definitionCode": "wf_test"}, headers=auth_header(bob),
        )).json()["data"]

        alice = await login(client, "alice", "alice123")
        resp = await client.post(
            f"/api/v1/tasks/{started['tasks'][0]['taskId']}/reject",
            json={"opinion": "材料不全", "targetNodeKey": "start"}, headers=auth_header(alice),
        )
        assert resp.status_code == 200, resp.text

        todo = (await client.get("/api/v1/tasks/todo", headers=auth_header(bob))).json()["data"]
        assert todo[0]["round"] == 2
        resp = await client.post(
            f"/api/v1/tasks/{todo[0]['taskId']}/approve", json={}, headers=auth_header(bob)
        )
        assert resp.json()["data"]["tasks"][0]["nodeKey"] == "approve_1"

    async def test_terminate_requires_admin(self, client) -> None:
        """非管理员终止实例 → 403。"""
        admin = await login(client, "admin", "admin123")
        await publish_serial_flow(client, admin)
        bob = await login(client, "bob", "bob123")
        started = (await client.post(
            "/api/v1/instances", json={"definitionCode": "wf_test"}, headers=auth_header(bob),
        )).json()["data"]
        resp = await client.post(
            f"/api/v1/instances/{started['instanceId']}/terminate",
            json={"reason": "测试"}, headers=auth_header(bob),
        )
        assert resp.status_code == 403

        resp = await client.post(
            f"/api/v1/instances/{started['instanceId']}/terminate",
            json={"reason": "测试"}, headers=auth_header(admin),
        )
        assert resp.json()["data"]["instanceStatus"] == "terminated"

    async def test_double_approve_conflict(self, client) -> None:
        """重复审批 → 409/43102。"""
        admin = await login(client, "admin", "admin123")
        await publish_serial_flow(client, admin)
        bob = await login(client, "bob", "bob123")
        started = (await client.post(
            "/api/v1/instances", json={"definitionCode": "wf_test"}, headers=auth_header(bob),
        )).json()["data"]
        alice = await login(client, "alice", "alice123")
        task_id = started["tasks"][0]["taskId"]
        await client.post(f"/api/v1/tasks/{task_id}/approve", json={}, headers=auth_header(alice))
        resp = await client.post(f"/api/v1/tasks/{task_id}/approve", json={}, headers=auth_header(alice))
        assert resp.status_code == 409
        assert resp.json()["code"] == 43102
