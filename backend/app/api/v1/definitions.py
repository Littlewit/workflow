"""流程定义接口（T4.2）：草稿 CRUD / 发布 / 停用 / 列表。

权限：写操作仅管理员；读操作需登录。
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.container import get_definition_service
from app.api.deps import CurrentUser, get_current_user, require_admin
from app.api.response import ok
from app.application.definition_service import DefinitionService

router = APIRouter(prefix="/definitions", tags=["definitions"])


class DefinitionUpsertRequest(BaseModel):
    """创建/更新草稿请求体。

    注意 code/name 以 DSL 内的为准（dsl.code/dsl.name），此处仅作展示冗余。
    """

    dsl: dict = Field(description="完整流程 DSL")
    name: str | None = None
    category: str = "default"
    description: str = ""


@router.post("")
async def create_draft(
    body: DefinitionUpsertRequest,
    user: CurrentUser = Depends(require_admin),
    service: DefinitionService = Depends(get_definition_service),
) -> dict:
    """创建流程草稿（管理员）。"""
    data = await service.create_draft(
        user.user_id, code="", name=body.name or "",
        dsl_data=body.dsl, category=body.category, description=body.description,
    )
    return ok(data)


@router.put("/{definition_id}")
async def update_draft(
    definition_id: str,
    body: DefinitionUpsertRequest,
    user: CurrentUser = Depends(require_admin),
    service: DefinitionService = Depends(get_definition_service),
) -> dict:
    """更新草稿（仅 draft 状态）。"""
    data = await service.update_draft(
        user.user_id, definition_id, body.dsl, name=body.name
    )
    return ok(data)


@router.post("/{definition_id}/publish")
async def publish(
    definition_id: str,
    user: CurrentUser = Depends(require_admin),
    service: DefinitionService = Depends(get_definition_service),
) -> dict:
    """发布定义：权威校验通过后生成新版本快照。"""
    return ok(await service.publish(user.user_id, definition_id))


@router.post("/{definition_id}/disable")
async def disable(
    definition_id: str,
    user: CurrentUser = Depends(require_admin),
    service: DefinitionService = Depends(get_definition_service),
) -> dict:
    """停用定义（运行中实例不受影响）。"""
    await service.disable(user.user_id, definition_id)
    return ok()


@router.get("")
async def list_definitions(
    keyword: str = "",
    user: CurrentUser = Depends(get_current_user),
    service: DefinitionService = Depends(get_definition_service),
) -> dict:
    """定义列表。"""
    return ok(await service.list_definitions(keyword))


@router.get("/{definition_id}")
async def get_definition(
    definition_id: str,
    user: CurrentUser = Depends(get_current_user),
    service: DefinitionService = Depends(get_definition_service),
) -> dict:
    """定义详情（含当前可用 DSL）。"""
    return ok(await service.get_detail(definition_id))
