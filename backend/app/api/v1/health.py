"""健康检查接口：供负载均衡 / CI 冒烟测试使用。"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """存活探针：不依赖数据库，仅验证进程可用。"""
    return {"status": "ok"}
