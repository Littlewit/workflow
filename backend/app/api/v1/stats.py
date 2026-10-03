"""运营统计接口（M7，管理员可见）。"""

from fastapi import APIRouter, Depends

from app.api.container import get_stats_service
from app.api.deps import require_admin
from app.api.response import ok
from app.application.stats_service import StatsService

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/overview")
async def overview(
    _admin: None = Depends(require_admin),
    service: StatsService = Depends(get_stats_service),
) -> dict:
    """全局总览：实例/任务状态分布与平均流转时长。"""
    return ok(await service.overview())


@router.get("/bottlenecks")
async def bottlenecks(
    limit: int = 10,
    _admin: None = Depends(require_admin),
    service: StatsService = Depends(get_stats_service),
) -> dict:
    """节点瓶颈：平均停留时长 Top N。"""
    return ok(await service.node_bottlenecks(limit))
