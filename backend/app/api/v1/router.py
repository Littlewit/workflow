"""API v1 路由汇总。"""

from fastapi import APIRouter

from app.api.v1 import auth, definitions, health, instances, open_instances, tasks

api_router = APIRouter()
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(health.router, tags=["health"])
api_router.include_router(definitions.router)
api_router.include_router(instances.router)
api_router.include_router(tasks.router)
api_router.include_router(open_instances.router)
