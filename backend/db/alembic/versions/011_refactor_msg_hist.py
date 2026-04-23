"""refactor agent_msg_hist: remove thread/checkpoint columns, add step_id

Revision ID: 011_refactor_msg_hist
Revises: 010_fix_checkpoint_id
Create Date: 2026-04-23

移除 thread_id、checkpoint_id、message_idx、tool_call_id、tool_name、payload_json，
新增 step_id varchar(200)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "011_refactor_msg_hist"
down_revision: Union[str, None] = "010_fix_checkpoint_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_msg_hist",
        sa.Column("step_id", sa.String(length=200), nullable=True),
    )
    op.drop_column("agent_msg_hist", "payload_json")
    op.drop_column("agent_msg_hist", "tool_name")
    op.drop_column("agent_msg_hist", "tool_call_id")
    op.drop_column("agent_msg_hist", "message_idx")
    op.drop_column("agent_msg_hist", "checkpoint_id")
    op.drop_column("agent_msg_hist", "thread_id")


def downgrade() -> None:
    op.add_column(
        "agent_msg_hist",
        sa.Column("thread_id", sa.String(length=200), nullable=False, server_default=""),
    )
    op.add_column(
        "agent_msg_hist",
        sa.Column("checkpoint_id", sa.String(length=200), nullable=False, server_default=""),
    )
    op.add_column(
        "agent_msg_hist",
        sa.Column("message_idx", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "agent_msg_hist",
        sa.Column("tool_call_id", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "agent_msg_hist",
        sa.Column("tool_name", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "agent_msg_hist",
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.drop_column("agent_msg_hist", "step_id")
