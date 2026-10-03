"""Webhook 出站投递（M5-T5.3）。

对应详细设计 §5.3 出站协议与重试策略：
- 头部：X-WF-Event / X-WF-Instance / X-WF-Delivery / X-WF-Sign
- 签名：HMAC-SHA256(secret, instanceId + deliveryId + body)
- 重试：最多 max_retries 次重试，指数退避（base * 2^n，生产 base=60s）；
  重试耗尽置 dead 并记录（告警由 worker 日志/监控承接）。

httpx AsyncClient 可注入（测试用 MockTransport 替换真实网络）。
"""

import asyncio
import hashlib
import hmac
import json
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infra.models.instance import WebhookDelivery


class WebhookOutcome:
    """单次投递任务的结果摘要。"""

    def __init__(self, delivery_id: str, status: str, response_code: int | None, retries: int) -> None:
        """初始化结果。"""
        self.delivery_id = delivery_id
        self.status = status  # success / dead（重试耗尽）
        self.response_code = response_code
        self.retries = retries


class WebhookOutbound:
    """出站 Webhook 投递器：签名、重试、落库。"""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        client: httpx.AsyncClient | None = None,
        base_backoff_seconds: float = 60.0,
    ) -> None:
        """注入会话工厂与 HTTP 客户端。

        Args:
            session_factory: 会话工厂（投递记录落库）。
            client: httpx 客户端（缺省新建；测试注入 MockTransport）。
            base_backoff_seconds: 退避基数（生产 60s；测试调小）。
        """
        self._sessions = session_factory
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._base_backoff = base_backoff_seconds

    async def aclose(self) -> None:
        """释放底层 HTTP 连接池（worker 任务结束时调用，防连接泄漏）。"""
        await self._client.aclose()

    async def send(
        self, instance_id: str, event_type: str, url: str,
        body: dict, secret: str = "", max_retries: int = 3,
        event_id: str | None = None,
    ) -> WebhookOutcome:
        """执行投递（含重试循环），并写 webhook_delivery 记录。

        max_retries=0 时为单次投递（Outbox 循环承担重试节奏），
        失败状态记为 failed（可重试）而非 dead（死信）。
        """
        delivery_id = uuid4().hex
        payload = json.dumps(body, ensure_ascii=False, default=str)
        last_code: int | None = None
        last_error: str | None = None
        attempts = max_retries + 1  # 首次 + 重试

        for attempt in range(attempts):
            sign = hmac.new(
                secret.encode(), f"{instance_id}{delivery_id}{payload}".encode(), hashlib.sha256
            ).hexdigest()
            headers = {
                "X-WF-Event": event_type,
                "X-WF-Instance": instance_id,
                "X-WF-Delivery": delivery_id,
                "X-WF-Sign": sign,
                "Content-Type": "application/json",
            }
            try:
                resp = await self._client.post(url, content=payload, headers=headers)
                last_code = resp.status_code
                if 200 <= resp.status_code < 300:
                    await self._record(
                        instance_id, delivery_id, event_id, url, body, "success", last_code, attempt, None
                    )
                    return WebhookOutcome(delivery_id, "success", last_code, attempt)
                last_error = f"HTTP {resp.status_code}"
            except httpx.HTTPError as exc:  # 网络类错误：连接拒绝/超时等
                last_error = str(exc)[:500]
                last_code = None

            if attempt < attempts - 1:
                # 指数退避（事件循环内 sleep，测试可把 base 调到毫秒级）
                await asyncio.sleep(self._base_backoff * (2**attempt))

        # 重试耗尽置死信；单次投递（max_retries=0）失败记 failed，交由 Outbox 循环重试
        status = "failed" if max_retries == 0 else "dead"
        await self._record(
            instance_id, delivery_id, event_id, url, body, status, last_code, attempts - 1, last_error
        )
        return WebhookOutcome(delivery_id, status, last_code, attempts - 1)

    async def _record(
        self, instance_id: str, delivery_id: str, event_id: str | None, url: str, body: dict,
        status: str, code: int | None, retries: int, error: str | None,
    ) -> None:
        """落库投递记录。"""
        async with self._sessions() as session:
            session.add(
                WebhookDelivery(
                    id=delivery_id, instance_id=instance_id, event_id=event_id, url=url,
                    request_body=body, status=status, response_code=code,
                    retry_count=retries, error_message=error,
                    created_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
