"""开放接口测试（M5-T5.4）：签名/时间戳/Nonce 防重放。"""

import hashlib
import hmac
import time
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.container import get_workflow_service
from app.application.workflow_service import WorkflowService
from app.main import create_app
from tests.engine.conftest import simple_serial_dsl

APP_KEY, APP_SECRET = "demo-app", "demo-secret-0123456789abcdef"


def signed_headers(method: str, path: str, body: bytes, nonce: str | None = None) -> dict:
    """构造合法签名头。"""
    ts = str(int(time.time() * 1000))
    n = nonce or uuid4().hex
    body_hash = hashlib.sha256(body).hexdigest()
    msg = f"{method}\n{path}\n{ts}\n{n}\n{body_hash}"
    sign = hmac.new(APP_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return {
        "X-App-Key": APP_KEY, "X-Timestamp": ts,
        "X-Nonce": n, "X-Sign": sign,
    }


@pytest.fixture()
def app_and_client(sqlite_db):
    """应用 + 客户端（覆盖服务依赖）。"""
    application = create_app()
    factory = async_sessionmaker(create_async_engine(sqlite_db), expire_on_commit=False)
    application.dependency_overrides[get_workflow_service] = lambda: WorkflowService(factory, admin_ids=["admin-1"])
    return application, factory


@pytest.mark.asyncio
async def test_open_start_and_query(app_and_client) -> None:
    """合法签名：代发起 → 查询实例状态。"""
    application, factory = app_and_client
    # 前置：发布定义（直写定义表，发布链路已由 DefinitionAPI 测试覆盖）
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

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        body = b'{"definitionCode": "wf_test", "initiatorId": "boss-1", "formData": {"days": 1}}'
        headers = signed_headers("POST", "/api/v1/open/instances", body)
        resp = await client.post(
            "/api/v1/open/instances", content=body,
            headers={**headers, "Content-Type": "application/json"},
        )
        assert resp.status_code == 200, resp.text
        instance_id = resp.json()["data"]["instanceId"]

        path = f"/api/v1/open/instances/{instance_id}"
        resp = await client.get(path, headers=signed_headers("GET", path, b""))
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "running"


@pytest.mark.asyncio
async def test_open_bad_sign_rejected(app_and_client) -> None:
    """签名错误 → 401/40005。"""
    application, _ = app_and_client
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        body = b'{"definitionCode": "wf_test", "initiatorId": "boss-1"}'
        headers = signed_headers("POST", "/api/v1/open/instances", body)
        headers["X-Sign"] = "0" * 64  # 篡改签名
        resp = await client.post(
            "/api/v1/open/instances", content=body,
            headers={**headers, "Content-Type": "application/json"},
        )
        assert resp.status_code == 401
        assert resp.json()["code"] == 40005


@pytest.mark.asyncio
async def test_open_replay_rejected(app_and_client) -> None:
    """同 nonce 重放 → 40005（重放请求必然失败）。"""
    application, factory = app_and_client
    dsl = simple_serial_dsl()
    from app.infra.models.definition import WorkflowDefinition, WorkflowDefinitionVersion

    async with factory() as s:
        version = WorkflowDefinitionVersion(
            id="v1", definition_id="d1", version=1,
            dsl=dsl.model_dump(mode="json"), dsl_hash="x",
        )
        s.add_all([
            WorkflowDefinition(id="d1", code=dsl.code, name="t", status="published", current_version=1),
            version,
        ])
        await s.commit()

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        body = b'{"definitionCode": "wf_test", "initiatorId": "boss-1"}'
        headers = signed_headers("POST", "/api/v1/open/instances", body)
        req_headers = {**headers, "Content-Type": "application/json"}
        await client.post("/api/v1/open/instances", content=body, headers=req_headers)
        second = await client.post("/api/v1/open/instances", content=body, headers=req_headers)
        assert second.status_code == 401
        assert second.json()["code"] == 40005
