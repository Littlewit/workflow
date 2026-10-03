"""Outbox 补偿：扫描未投递事件并分发。

对应详细设计 §3.2：事务提交后事件先落 instance_event（dispatched=False），
本模块由定时任务驱动（worker.py cron / 测试直接调用），实现
at-least-once 投递；接收方按 deliveryId/operationId 幂等。

事件路由：
- webhook_invoked → WebhookOutbound（HTTP 出站 + 重试）
- 其余事件 → LoggingDispatcher（通知渠道 M6+ 实装后接入）
"""

import logging
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.webhook import WebhookOutbound
from app.infra.repositories import EventRepository

logger = logging.getLogger(__name__)


class EventDispatcher(Protocol):
    """事件分发器协议：通知渠道 / Webhook 均实现此接口。"""

    async def dispatch(
        self, event_type: str, payload: dict, node_key: str | None,
        instance_id: str, event_id: str,
    ) -> bool:
        """投递单条事件；返回是否成功（失败保留待下轮重试）。"""
        ...


class LoggingDispatcher:
    """默认分发器：仅记录日志。"""

    async def dispatch(
        self, event_type: str, payload: dict, node_key: str | None,
        instance_id: str, event_id: str,
    ) -> bool:
        """记录日志并视为成功。"""
        logger.info("outbox dispatch event=%s node=%s payload=%s", event_type, node_key, payload)
        return True


class EventRouter:
    """按事件类型路由到具体分发器。

    webhook_invoked 采用"单次投递 + Outbox 循环重试"模式：
    投递器内部不做长退避 sleep，避免一条慢 Webhook 卡住整批扫描。
    """

    def __init__(self, webhook: WebhookOutbound | None = None) -> None:
        """注入 Webhook 投递器（缺省用日志桩）。"""
        self._webhook = webhook

    async def dispatch(
        self, event_type: str, payload: dict, node_key: str | None,
        instance_id: str, event_id: str,
    ) -> bool:
        """路由分发：webhook_invoked 走 HTTP 出站，其余走日志。"""
        if event_type == "webhook_invoked":
            url = payload.get("url")
            if self._webhook is None or not url:
                logger.warning("webhook_invoked 跳过（无投递器或 url 缺失）: %s", payload)
                return True  # 视为已处理，避免无限重试
            outcome = await self._webhook.send(
                instance_id=instance_id,
                event_type=event_type,
                event_id=event_id,
                url=url,
                body=payload.get("payload", {}),
                secret=payload.get("secret", ""),
                max_retries=0,  # 单次投递，重试交给 Outbox 下一轮
            )
            return outcome.status == "success"
        return await LoggingDispatcher().dispatch(event_type, payload, node_key, instance_id, event_id)


async def dispatch_pending_events(
    session_factory: async_sessionmaker[AsyncSession],
    dispatcher: EventDispatcher | None = None,
    limit: int = 100,
) -> int:
    """投递一批未派发事件，返回成功条数（供定时任务与测试调用）。

    单条失败不阻塞其余事件（重试交给下一轮扫描）。
    """
    dispatcher = dispatcher or LoggingDispatcher()
    dispatched = 0
    async with session_factory() as session:
        events = await EventRepository(session).list_undispatched(limit)
        succeeded = []
        for e in events:
            try:
                ok = await dispatcher.dispatch(
                    e.event_type, e.payload, e.node_key, e.instance_id, e.id
                )
                if ok:
                    succeeded.append(e)
                    dispatched += 1
            except Exception:  # noqa: BLE001 —— 单条失败不影响整批
                logger.exception("outbox dispatch failed event_id=%s", e.id)
        await EventRepository(session).mark_dispatched(succeeded)
        await session.commit()
    return dispatched
