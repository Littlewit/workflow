"""统计服务（M7 监控看板数据源）。

时间聚合在 Python 侧完成（SQLite/PG 的 datetime 字符串直接做 SQL
减法不可移植），数据量可控（MVP 千级实例）。
"""

from statistics import mean

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infra.models.instance import TaskInstance, WorkflowInstance


class StatsService:
    """运营统计用例：总览 / 节点瓶颈。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """注入会话工厂。"""
        self._sessions = session_factory

    async def overview(self) -> dict:
        """全局总览：实例/任务状态分布 + 平均流转时长。

        Returns:
            {
              instanceCounts: {status: n},
              taskCounts: {status: n},
              activeInstances: n,
              avgInstanceDurationMs: number | null,  # 完成实例的 端到端 均值
            }
        """
        async with self._sessions() as session:
            inst_rows = (await session.execute(
                select(WorkflowInstance.status, WorkflowInstance.started_at, WorkflowInstance.finished_at)
            )).all()
            task_rows = (await session.execute(
                select(TaskInstance.status)
            )).all()

        instance_counts: dict[str, int] = {}
        durations: list[float] = []
        for status, started_at, finished_at in inst_rows:
            instance_counts[status] = instance_counts.get(status, 0) + 1
            if finished_at is not None and started_at is not None:
                durations.append((finished_at - started_at).total_seconds() * 1000)

        task_counts: dict[str, int] = {}
        for (status,) in task_rows:
            task_counts[status] = task_counts.get(status, 0) + 1

        return {
            "instanceCounts": instance_counts,
            "taskCounts": task_counts,
            "activeInstances": instance_counts.get("running", 0),
            "avgInstanceDurationMs": round(mean(durations)) if durations else None,
        }

    async def node_bottlenecks(self, limit: int = 10) -> list[dict]:
        """节点瓶颈分析：已完成任务按节点的平均停留时长 Top N。

        Returns:
            [{nodeName, count, avgStayMs}]，按平均停留时长降序。
        """
        async with self._sessions() as session:
            rows = (await session.execute(
                select(
                    TaskInstance.node_name,
                    TaskInstance.created_at,
                    TaskInstance.finished_at,
                ).where(TaskInstance.finished_at.is_not(None))
            )).all()

        agg: dict[str, list[float]] = {}
        for node_name, created_at, finished_at in rows:
            if created_at is None or finished_at is None:
                continue
            stay_ms = (finished_at - created_at).total_seconds() * 1000
            agg.setdefault(node_name, []).append(stay_ms)

        items: list[dict[str, object]] = [
            {
                "nodeName": name,
                "count": len(times),
                "avgStayMs": round(mean(times)),
            }
            for name, times in agg.items()
        ]
        items.sort(key=lambda x: float(x["avgStayMs"]), reverse=True)  # type: ignore[arg-type]
        return items[:limit]
