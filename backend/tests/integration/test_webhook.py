"""Webhook 出站投递测试（M5-T5.3）：引擎事件 + 签名 + 重试/死信。"""


import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.webhook import WebhookOutbound
from app.domain.enums import TaskStatus
from app.engine.executor import WorkflowEngine
from tests.engine.conftest import simple_serial_dsl


def webhook_dsl() -> dict:
    """串行流程插入一个发后即忘的 Webhook 节点。"""
    dsl = simple_serial_dsl().model_dump(mode="json")
    dsl["nodes"]["notify_hook"] = {
        "key": "notify_hook", "name": "回调业务", "type": "webhook",
        "url": "https://biz.example.com/hook", "secret": "s3cret",
        "payload_template": {"bizKey": "B-1"}, "wait_callback": False,
        "max_retries": 2,
    }
    dsl["edges"].insert(1, {"source": "approve_1", "target": "notify_hook", "edge_type": "normal"})
    dsl["edges"].append({"source": "notify_hook", "target": "end", "edge_type": "normal"})
    # 修正：原 approve_1->end 边仍存在，会破坏单出边语义，删除之
    dsl["edges"] = [
        e for e in dsl["edges"]
        if not (e["source"] == "approve_1" and e["target"] == "end")
    ]
    return dsl


class TestEngineWebhookNode:
    """引擎对 Webhook 节点的处理。"""

    def test_webhook_node_emits_event_and_continues(self) -> None:
        """发后即忘：审批通过后进入 webhook 节点，登记事件并继续到 end。"""
        from app.domain.dsl import WorkflowDSL

        dsl = WorkflowDSL.model_validate(webhook_dsl())
        engine = WorkflowEngine(dsl)
        state = engine.start(initiator_id="u0")
        task_id = next(t.id for t in state.tasks.values() if t.status == TaskStatus.PENDING)
        engine.approve(state, task_id)
        assert any(e.event_type == "webhook_invoked" for e in state.events)
        assert state.status == "completed"


class TestWebhookOutbound:
    """出站投递：签名头、重试、死信。"""

    def _factory(self, sqlite_db: str):
        return async_sessionmaker(create_async_engine(sqlite_db), expire_on_commit=False)

    @pytest.mark.asyncio
    async def test_success_first_try(self, sqlite_db) -> None:
        """首试成功：记录 success 与响应码。"""
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200)

        factory = self._factory(sqlite_db)
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        outbound = WebhookOutbound(factory, client=client, base_backoff_seconds=0.001)
        outcome = await outbound.send("inst-1", "webhook_invoked", "https://x/hook", {"a": 1}, "s3cret")

        assert outcome.status == "success"
        assert outcome.retries == 0
        assert calls[0].headers["X-WF-Event"] == "webhook_invoked"
        assert calls[0].headers["X-WF-Sign"]  # 签名头存在

    @pytest.mark.asyncio
    async def test_retries_then_dead(self, sqlite_db) -> None:
        """持续失败：按 max_retries 重试后置 dead。"""
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        factory = self._factory(sqlite_db)
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        outbound = WebhookOutbound(factory, client=client, base_backoff_seconds=0.001)
        outcome = await outbound.send("inst-1", "webhook_invoked", "https://x/hook", {}, "s", max_retries=2)

        assert outcome.status == "dead"
        assert outcome.retries == 2

        # 投递记录已落库
        from app.infra.models.instance import WebhookDelivery

        async with factory() as session:
            row = (await session.execute(select(WebhookDelivery))).scalar_one()
            assert row.status == "dead"
            assert row.response_code == 500
            assert row.retry_count == 2

    @pytest.mark.asyncio
    async def test_retry_until_success(self, sqlite_db) -> None:
        """前次 500 后次成功：最终 success 且 retry_count=1。"""
        state = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            state["n"] += 1
            return httpx.Response(200 if state["n"] >= 2 else 500)

        factory = self._factory(sqlite_db)
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        outbound = WebhookOutbound(factory, client=client, base_backoff_seconds=0.001)
        outcome = await outbound.send("inst-1", "webhook_invoked", "https://x/hook", {}, "s", max_retries=3)

        assert outcome.status == "success"
        assert outcome.retries == 1
