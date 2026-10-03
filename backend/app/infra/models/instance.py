"""流程实例相关 ORM 模型。

对应详细设计文档 §2.3–§2.8、§2.10：
- workflow_instance：实例聚合根（engine_state 为引擎内存状态的 JSONB 快照，
  M3 采用"状态快照 + 行锁/乐观锁"的简单持久化策略）
- task_instance / task_opinion / task_substitute：任务与审批记录（供待办查询）
- workflow_variable：变量快照
- instance_event：事件审计流水（同时充当 Outbox）
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base


class WorkflowInstance(Base):
    """流程实例。"""

    __tablename__ = "workflow_instance"
    __table_args__ = (
        # 防重复发起：同定义同租户下 business_key 唯一（仅对非空 business_key 生效）
        Index(
            "uk_business",
            "definition_id",
            "tenant_id",
            "business_key",
            unique=True,
            sqlite_where=text("business_key IS NOT NULL"),
            postgresql_where=text("business_key IS NOT NULL"),
        ),
        Index("idx_initiator_status", "initiator_id", "status", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    definition_id: Mapped[str] = mapped_column(ForeignKey("workflow_definition.id"))
    definition_version: Mapped[int] = mapped_column(Integer)  # 启动时锁定版本
    business_key: Mapped[str | None] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(256), default="")
    initiator_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="running")
    current_node_keys: Mapped[list] = mapped_column(JSON, default=list)  # 活跃节点
    # 引擎内存状态快照（tasks/tokens/variables），由 engine_codec 序列化
    engine_state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # 乐观锁版本号：并发保存时冲突检测（Redis 锁的兜底防线）
    state_version: Mapped[int] = mapped_column(Integer, default=1)
    start_form_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tenant_id: Mapped[str] = mapped_column(String(32), default="default")


class TaskInstance(Base):
    """任务实例（审批待办/已办），与 engine_state 中的任务镜像同步。"""

    __tablename__ = "workflow_instance_task"
    __table_args__ = (
        Index("idx_assignee_status", "assignee_id", "status", "created_at"),
        Index("idx_task_instance", "instance_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    instance_id: Mapped[str] = mapped_column(ForeignKey("workflow_instance.id"))
    node_key: Mapped[str] = mapped_column(String(64))
    node_name: Mapped[str] = mapped_column(String(128))
    node_type: Mapped[str] = mapped_column(String(32))
    round: Mapped[int] = mapped_column(Integer, default=1)  # 驳回重走轮次
    assignee_id: Mapped[str] = mapped_column(String(64))
    assignee_source: Mapped[str] = mapped_column(String(32), default="")  # 解析来源快照
    status: Mapped[str] = mapped_column(String(16), default="pending")
    action: Mapped[str | None] = mapped_column(String(16))
    counter_sign_group_id: Mapped[str | None] = mapped_column(String(64))
    form_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    tenant_id: Mapped[str] = mapped_column(String(32), default="default")


class TaskOpinion(Base):
    """审批意见/附件。"""

    __tablename__ = "task_opinion"
    __table_args__ = (Index("idx_opinion_instance", "instance_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("workflow_instance_task.id"))
    instance_id: Mapped[str] = mapped_column(String(64), index=True)  # 冗余，时间线直查
    content: Mapped[str] = mapped_column(Text, default="")
    attachments: Mapped[list] = mapped_column(JSON, default=list)
    author_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))


class TaskSubstitute(Base):
    """转办/委托/加签流水。"""

    __tablename__ = "task_substitute"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("workflow_instance_task.id"))
    from_user_id: Mapped[str] = mapped_column(String(64))
    to_user_id: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(16))  # transfer/delegate/add_sign_before/add_sign_after
    comment: Mapped[str] = mapped_column(String(256), default="")
    effective: Mapped[bool] = mapped_column(Boolean, default=True)


class WorkflowVariable(Base):
    """流程变量快照（scope: global / node:<key>）。"""

    __tablename__ = "workflow_variable"
    __table_args__ = (UniqueConstraint("instance_id", "scope", "key", name="uk_var"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    instance_id: Mapped[str] = mapped_column(ForeignKey("workflow_instance.id"))
    scope: Mapped[str] = mapped_column(String(80), default="global")
    key: Mapped[str] = mapped_column(String(64))
    value: Mapped[Any] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)


class InstanceEvent(Base):
    """事件审计流水（只追加），dispatched=False 即 Outbox 待投递。"""

    __tablename__ = "instance_event"
    __table_args__ = (
        Index("idx_event_inst_time", "instance_id", "created_at"),
        Index("idx_outbox", "dispatched", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    instance_id: Mapped[str] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(48))
    node_key: Mapped[str | None] = mapped_column(String(64))
    task_id: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    actor_id: Mapped[str | None] = mapped_column(String(64))
    operation_id: Mapped[str | None] = mapped_column(String(64))
    dispatched: Mapped[bool] = mapped_column(Boolean, default=False)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
