"""add msg_idx column to agent_msg_hist

Revision ID: 012_add_msg_idx
Revises: 011_refactor_msg_hist
Create Date: 2026-04-23

新增 msg_idx BigInteger 字段，預設值 0。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "012_add_msg_idx"
down_revision: Union[str, None] = "011_refactor_msg_hist"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_msg_hist",
        sa.Column("msg_idx", sa.BigInteger(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("agent_msg_hist", "msg_idx")
