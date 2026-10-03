"""Outbox 补偿：扫描未投递事件并分发。

对应详细设计 §3.2：事务提交后事件先落 instance_event（dispatched=False），
本模块由定时任务驱动（M5 接入 ARQ cron，测试中直接调用），实现
at-least-once 投递；接收方按 operationId/eventId 幂等。
"""

import logging
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infra.repositories import EventRepository

logger = logging.getLogger(__name__)


class EventDispatcher(Protocol):
    """事件分发器协议：通知渠道 / Webhook 均实现此接口。"""

    async def dispatch(self, event_type: str, payload: dict, node_key: str | None) -> bool:
        """投递单条事件；返回是否成功（失败保留待下轮重试）。"""
        ...


class LoggingDispatcher:
    """默认分发器：仅记录日志（M5 替换为通知渠道 + Webhook 实现）。"""

    async def dispatch(self, event_type: str, payload: dict, node_key: str | None) -> bool:
        """记录日志并视为成功。"""
        logger.info("outbox dispatch event=%s node=%s payload=%s", event_type, node_key, payload)
        return True


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
                if await dispatcher.dispatch(e.event_type, e.payload, e.node_key):
                    succeeded.append(e)
                    dispatched += 1
            except Exception:  # noqa: BLE001 —— 单条失败不影响整批
                logger.exception("outbox dispatch failed event_id=%s", e.id)
        await EventRepository(session).mark_dispatched(succeeded)
        await session.commit()
    return dispatched
