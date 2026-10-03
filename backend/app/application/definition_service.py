"""流程定义应用服务：草稿 CRUD / 发布 / 停用（T4.2）。

发布为权威校验入口：parser 六项规则全过才允许生成新版本快照。
"""

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.errors import ApplicationError
from app.domain.dsl import NodeType, WorkflowDSL
from app.engine.parser import ValidationIssue, ValidationResult, validate_dsl
from app.infra.models.definition import WorkflowDefinition, WorkflowDefinitionVersion


class DefinitionService:
    """流程定义用例服务。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """注入会话工厂。"""
        self._sessions = session_factory

    async def create_draft(
        self, user_id: str, code: str, name: str, dsl_data: dict,
        category: str = "default", description: str = "",
    ) -> dict:
        """创建草稿（允许带校验错误保存，但返回 validation 供前端展示）。

        Raises:
            ApplicationError: 41004 编码已存在 / 41001 DSL 结构非法（Pydantic 级）。
        """
        try:
            dsl = WorkflowDSL.model_validate(dsl_data)
        except Exception as exc:
            raise ApplicationError(41001, f"DSL 结构非法: {exc}") from exc

        async with self._sessions() as session:
            dup = await session.execute(
                select(WorkflowDefinition.id).where(WorkflowDefinition.code == dsl.code)
            )
            if dup.scalar_one_or_none() is not None:
                raise ApplicationError(41004, f"流程编码已存在: {dsl.code}")

            validation = validate_dsl(dsl)
            definition = WorkflowDefinition(
                id=uuid4().hex, code=code or dsl.code, name=name or dsl.name,
                description=description, category=category,
                draft_dsl=dsl.model_dump(mode="json"),
            )
            session.add(definition)
            await session.commit()
            return {
                "definitionId": definition.id,
                "validation": self._validation_dto(validation),
            }

    async def update_draft(
        self, user_id: str, definition_id: str, dsl_data: dict, name: str | None = None
    ) -> dict:
        """更新草稿（仅 draft 状态可改；published 需先停用或另存副本）。"""
        try:
            dsl = WorkflowDSL.model_validate(dsl_data)
        except Exception as exc:
            raise ApplicationError(41001, f"DSL 结构非法: {exc}") from exc

        async with self._sessions() as session:
            definition = await self._get_or_404(session, definition_id)
            if definition.status != "draft":
                raise ApplicationError(41005, "已发布的定义不可直接修改，请先停用或另存副本")
            validation = validate_dsl(dsl)
            definition.draft_dsl = dsl.model_dump(mode="json")
            if name:
                definition.name = name
            await session.commit()
            return {"definitionId": definition.id, "validation": self._validation_dto(validation)}

    async def publish(self, user_id: str, definition_id: str) -> dict:
        """发布：权威校验 → 生成不可变版本快照 → 更新 current_version。

        Raises:
            ApplicationError: 41001 权威校验失败（details 携带逐条错误定位）。
        """
        async with self._sessions() as session:
            definition = await self._get_or_404(session, definition_id)
            if not definition.draft_dsl:
                raise ApplicationError(41006, "草稿为空，无法发布")
            dsl = WorkflowDSL.model_validate(definition.draft_dsl)

            validation = validate_dsl(dsl)
            if not validation.ok:
                raise ApplicationError(
                    41001, "DSL 校验失败",
                    details=[{"nodeKey": e.node_key, "message": e.message} for e in validation.errors],
                )

            new_version = definition.current_version + 1
            dsl.version = new_version
            dumped = dsl.model_dump(mode="json")
            session.add(
                WorkflowDefinitionVersion(
                    id=uuid4().hex, definition_id=definition.id, version=new_version,
                    dsl=dumped,
                    # 规范化 JSON 的哈希，用于完整性校验
                    dsl_hash=hashlib.sha256(json.dumps(dumped, sort_keys=True).encode()).hexdigest(),
                    form_schema=self._extract_form_schema(dsl),
                    published_at=datetime.now(timezone.utc),
                    published_by=user_id,
                )
            )
            definition.current_version = new_version
            definition.status = "published"
            await session.commit()
            return {"version": new_version}

    async def disable(self, user_id: str, definition_id: str) -> None:
        """停用定义：running 实例不受影响，新发起将被拒绝（41002）。"""
        async with self._sessions() as session:
            definition = await self._get_or_404(session, definition_id)
            definition.status = "disabled"
            await session.commit()

    async def get_detail(self, definition_id: str) -> dict:
        """定义详情（草稿态返回 draft_dsl；已发布返回当前版本 DSL）。"""
        async with self._sessions() as session:
            definition = await self._get_or_404(session, definition_id)
            dsl = definition.draft_dsl
            if definition.status == "published" and definition.current_version > 0:
                version = (await session.execute(
                    select(WorkflowDefinitionVersion).where(
                        WorkflowDefinitionVersion.definition_id == definition.id,
                        WorkflowDefinitionVersion.version == definition.current_version,
                    )
                )).scalar_one()
                dsl = version.dsl
            return {
                "definitionId": definition.id, "code": definition.code, "name": definition.name,
                "status": definition.status, "currentVersion": definition.current_version,
                "dsl": dsl,
            }

    async def list_definitions(self, keyword: str = "") -> list[dict]:
        """定义列表（管理页用；MVP 不分页，数量可控）。"""
        async with self._sessions() as session:
            stmt = select(WorkflowDefinition).order_by(WorkflowDefinition.name)
            if keyword:
                stmt = stmt.where(WorkflowDefinition.name.contains(keyword))
            rows = (await session.execute(stmt)).scalars().all()
            return [
                {
                    "definitionId": r.id, "code": r.code, "name": r.name,
                    "category": r.category, "status": r.status,
                    "currentVersion": r.current_version,
                }
                for r in rows
            ]

    # ---------- 内部 ----------

    @staticmethod
    def _validation_dto(validation: ValidationResult) -> dict:
        """校验结果转 DTO。"""
        def issue(i: ValidationIssue) -> dict:
            return {"severity": i.severity, "nodeKey": i.node_key, "message": i.message}

        return {
            "ok": validation.ok,
            "errors": [issue(e) for e in validation.errors],
            "warnings": [issue(w) for w in validation.warnings],
        }

    @staticmethod
    def _extract_form_schema(dsl: WorkflowDSL) -> dict:
        """提取 start 节点的发起表单 Schema（冗余存储，发起页免解析全量 DSL）。"""
        for node in dsl.nodes.values():
            if node.type == NodeType.START and node.form_schema:
                return node.form_schema
        return {}

    @staticmethod
    async def _get_or_404(session: AsyncSession, definition_id: str) -> WorkflowDefinition:
        """加载定义，不存在抛 404 语义错误。"""
        definition = await session.get(WorkflowDefinition, definition_id)
        if definition is None:
            raise ApplicationError(41003, f"流程定义不存在: {definition_id}")
        return definition
