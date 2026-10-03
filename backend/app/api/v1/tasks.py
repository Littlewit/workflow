"""任务接口（T4.4）：待办/已办列表与审批动作。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.container import get_workflow_service
from app.api.deps import CurrentUser, get_current_user
from app.api.response import ok
from app.application.workflow_service import WorkflowService

router = APIRouter(prefix="/tasks", tags=["tasks"])


class ApproveRequest(BaseModel):
    """同意请求体。"""

    opinion: str = ""
    formData: dict = Field(default_factory=dict)
    operationId: str | None = None


class RejectRequest(BaseModel):
    """驳回请求体：targetNodeKey 缺省时使用节点配置的默认驳回策略。"""

    opinion: str = ""
    targetNodeKey: str | None = None
    operationId: str | None = None


class TransferRequest(BaseModel):
    """转办请求体。"""

    toUserId: str
    opinion: str = ""
    operationId: str | None = None


@router.get("/todo")
async def todo(
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
) -> dict:
    """当前用户待办列表。"""
    return ok(await service.list_todo(user.user_id))


@router.get("/done")
async def done(
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
) -> dict:
    """当前用户已办列表。"""
    return ok(await service.list_done(user.user_id))


@router.post("/{task_id}/approve")
async def approve(
    task_id: str,
    body: ApproveRequest,
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
) -> dict:
    """同意任务。"""
    return ok(await service.approve(
        task_id, user.user_id,
        opinion=body.opinion, variables=body.formData, operation_id=body.operationId,
    ))


@router.post("/{task_id}/reject")
async def reject(
    task_id: str,
    body: RejectRequest,
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
) -> dict:
    """驳回任务（可指定目标节点）。"""
    return ok(await service.reject(
        task_id, user.user_id,
        opinion=body.opinion, target_node_key=body.targetNodeKey, operation_id=body.operationId,
    ))


@router.post("/{task_id}/transfer")
async def transfer(
    task_id: str,
    body: TransferRequest,
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
) -> dict:
    """转办任务。"""
    return ok(await service.transfer(
        task_id, user.user_id, body.toUserId,
        opinion=body.opinion, operation_id=body.operationId,
    ))
