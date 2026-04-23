"""add metadata JSON column to agent_msg_hist

Revision ID: 013_add_metadata
Revises: 012_add_msg_idx
Create Date: 2026-04-23

新增 metadata JSON 字段，預設空 object。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "013_add_metadata"
down_revision: Union[str, None] = "012_add_msg_idx"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_msg_hist",
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("agent_msg_hist", "metadata")
