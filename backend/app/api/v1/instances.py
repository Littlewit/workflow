"""流程实例接口（T4.3）：发起 / 详情 / 我发起的 / 运维操作。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.container import get_workflow_service
from app.api.deps import CurrentUser, get_current_user, require_admin
from app.api.response import ok
from app.application.workflow_service import WorkflowService

router = APIRouter(prefix="/instances", tags=["instances"])


class StartInstanceRequest(BaseModel):
    """发起流程请求体。"""

    definitionCode: str
    businessKey: str | None = None
    title: str = ""
    formData: dict = Field(default_factory=dict)
    operationId: str | None = None


class ReasonRequest(BaseModel):
    """运维操作请求体（终止/暂停/撤回原因）。"""

    reason: str = ""


@router.post("")
async def start_instance(
    body: StartInstanceRequest,
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
) -> dict:
    """发起流程实例（发起人为当前用户）。"""
    data = await service.start_instance(
        definition_code=body.definitionCode,
        initiator_id=user.user_id,
        form_data=body.formData,
        business_key=body.businessKey,
        title=body.title,
        operation_id=body.operationId,
    )
    return ok(data)


@router.get("/mine")
async def my_instances(
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
) -> dict:
    """我发起的实例列表。"""
    return ok(await service.list_my_instances(user.user_id))


@router.get("/{instance_id}")
async def get_instance(
    instance_id: str,
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
) -> dict:
    """实例详情 + 任务 + 事件时间线。"""
    return ok(await service.get_instance_detail(instance_id))


@router.post("/{instance_id}/terminate")
async def terminate(
    instance_id: str,
    body: ReasonRequest,
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
) -> dict:
    """管理员强制终止。"""
    return ok(await service.terminate_instance(instance_id, user.user_id, body.reason))


@router.post("/{instance_id}/suspend")
async def suspend(
    instance_id: str,
    body: ReasonRequest,
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
) -> dict:
    """暂停实例。"""
    return ok(await service.suspend_instance(instance_id, user.user_id, body.reason))


@router.post("/{instance_id}/resume")
async def resume(
    instance_id: str,
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
) -> dict:
    """恢复实例。"""
    return ok(await service.resume_instance(instance_id, user.user_id))


@router.post("/{instance_id}/cancel")
async def cancel(
    instance_id: str,
    body: ReasonRequest,
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
) -> dict:
    """发起人撤回（仅尚无任务被处理时）。"""
    return ok(await service.cancel_instance(instance_id, user.user_id, body.reason))
