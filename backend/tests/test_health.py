"""健康检查接口冒烟测试。"""

from fastapi.testclient import TestClient

from app.main import create_app


def test_healthz_returns_ok() -> None:
    """/healthz 应返回 200 与 status=ok。"""
    client = TestClient(create_app())
    resp = client.get("/api/v1/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
