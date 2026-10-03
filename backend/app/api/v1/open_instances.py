"""开放接口路由（M5-T5.4）：第三方发起/查询流程。"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.container import get_workflow_service
from app.api.open import verify_open_request
from app.api.response import ok
from app.application.workflow_service import WorkflowService

router = APIRouter(prefix="/open", tags=["open"])


class OpenStartRequest(BaseModel):
    """开放发起请求体（代发起场景需传 initiatorId）。"""

    definitionCode: str
    initiatorId: str
    businessKey: str | None = None
    title: str = ""
    formData: dict = Field(default_factory=dict)


async def _verified(request: Request) -> str:
    """签名校验依赖（错误统一 40005）。"""
    return await verify_open_request(request)


@router.post("/instances")
async def open_start_instance(
    request: Request,
    body: OpenStartRequest,
    service: WorkflowService = Depends(get_workflow_service),
) -> dict:
    """第三方发起流程（需开放签名；支持代发起）。"""
    await _verified(request)
    data = await service.start_instance(
        definition_code=body.definitionCode,
        initiator_id=body.initiatorId,
        form_data=body.formData,
        business_key=body.businessKey,
        title=body.title,
    )
    return ok(data)


@router.get("/instances/{instance_id}")
async def open_get_instance(
    instance_id: str,
    request: Request,
    service: WorkflowService = Depends(get_workflow_service),
) -> dict:
    """第三方查询实例状态。"""
    await _verified(request)
    return ok(await service.get_instance_detail(instance_id))
