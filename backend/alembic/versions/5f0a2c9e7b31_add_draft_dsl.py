"""add draft_dsl column

Revision ID: 5f0a2c9e7b31
Revises: 49524dde24ae
Create Date: 2026-10-03

手工迁移：workflow_definition 增加 draft_dsl 草稿列（仅 SQLite/PG 均支持的 ADD COLUMN）。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5f0a2c9e7b31"
down_revision: str | None = "49524dde24ae"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """增加 draft_dsl 列。"""
    op.add_column("workflow_definition", sa.Column("draft_dsl", sa.JSON(), nullable=True))


def downgrade() -> None:
    """移除 draft_dsl 列。"""
    op.drop_column("workflow_definition", "draft_dsl")
