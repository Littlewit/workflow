"""ARQ Worker：定时任务入口（M5-T5.1）。

启动方式（需本地 Redis）：`.venv\\Scripts\\arq app.worker.WorkerSettings`

职责（对应详细设计 §6.5/§3.2）：
- outbox_dispatch：每 30s 扫描 instance_event 未投递事件 → 通知/Webhook
- timeout_scan：每 30s 扫描超时任务 → 执行 SLA 策略
"""

from arq import cron
from arq.connections import RedisSettings

from app.api.container import get_session_factory
from app.application.outbox import dispatch_pending_events
from app.application.workflow_service import WorkflowService
from app.core.config import get_settings


async def outbox_dispatch(ctx: dict) -> None:
    """投递未派发事件（at-least-once，接收方幂等）。"""
    count = await dispatch_pending_events(get_session_factory())
    if count:
        ctx["logger"].info("outbox dispatched %s events", count)


async def timeout_scan(ctx: dict) -> None:
    """扫描超时任务并执行 SLA 策略。"""
    service = WorkflowService(get_session_factory(), admin_ids=["admin-1"])
    processed = await service.scan_overdue_tasks()
    if processed:
        ctx["logger"].info("timeout processed %s tasks", processed)


async def startup(ctx: dict) -> None:
    """worker 启动钩子。"""
    ctx["logger"].info("workflow worker started")


class WorkerSettings:
    """ARQ Worker 配置：函数注册与定时策略。"""

    functions = [outbox_dispatch, timeout_scan]
    cron_jobs = [
        cron(outbox_dispatch, second={0, 30}, run_at_startup=True),
        cron(timeout_scan, second={15, 45}, run_at_startup=True),
    ]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    on_startup = startup
    max_jobs = 10
