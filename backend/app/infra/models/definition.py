"""流程定义相关 ORM 模型。

对应详细设计文档 §2.1 / §2.2：
- workflow_definition：定义元信息（code 唯一，current_version 指向已发布版本）
- workflow_definition_version：版本快照，只追加不可变
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.db import Base


class WorkflowDefinition(Base):
    """流程定义元信息（draft / published / disabled）。"""

    __tablename__ = "workflow_definition"

    # 统一主键策略：应用层生成 UUID 字符串（跨 SQLite/PG 兼容）
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(64), default="default", index=True)
    # 0 表示从未发布；发布时 +1 并写入对应 version 快照
    current_version: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="draft")

    versions: Mapped[list["WorkflowDefinitionVersion"]] = relationship(
        back_populates="definition", order_by="WorkflowDefinitionVersion.version"
    )

    def __repr__(self) -> str:  # 调试用
        return f"<WorkflowDefinition {self.code} v{self.current_version} {self.status}>"


class WorkflowDefinitionVersion(Base):
    """流程定义版本快照：发布时冻结完整 DSL，运行中实例按 version 引用，永不变更。"""

    __tablename__ = "workflow_definition_version"
    # uk_def_version：同一 definition 下版本号唯一
    __table_args__ = (UniqueConstraint("definition_id", "version", name="uk_def_version"),)

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    definition_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_definition.id"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    dsl: Mapped[dict] = mapped_column(JSON)  # 完整 DSL
    dsl_hash: Mapped[str] = mapped_column(String(64))  # 规范化 JSON 的 SHA-256
    form_schema: Mapped[dict] = mapped_column(JSON, default=dict)  # 冗余发起表单 Schema
    status: Mapped[str] = mapped_column(String(16), default="published")  # published/archived
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[str | None] = mapped_column(String(64))

    definition: Mapped[WorkflowDefinition] = relationship(back_populates="versions")
