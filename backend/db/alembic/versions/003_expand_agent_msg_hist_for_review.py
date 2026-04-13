"""expand agent_msg_hist for review workflow

Revision ID: 003
Revises: 002
Create Date: 2026-04-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_msg_hist",
        sa.Column("thread_id", sa.String(length=200), nullable=False, server_default=""),
    )
    op.add_column(
        "agent_msg_hist",
        sa.Column(
            "checkpoint_id",
            sa.String(length=200),
            nullable=False,
            server_default="",
        ),
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
    op.alter_column(
        "agent_msg_hist",
        "is_summary",
        new_column_name="is_stm_summary",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        existing_server_default="false",
    )
    op.add_column(
        "agent_msg_hist",
        sa.Column(
            "is_ltm_summary",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.drop_column("agent_msg_hist", "step_id")


def downgrade() -> None:
    op.add_column(
        "agent_msg_hist",
        sa.Column("step_id", sa.String(length=200), nullable=False, server_default=""),
    )
    op.drop_column("agent_msg_hist", "is_ltm_summary")
    op.alter_column(
        "agent_msg_hist",
        "is_stm_summary",
        new_column_name="is_summary",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        existing_server_default="false",
    )
    op.drop_column("agent_msg_hist", "payload_json")
    op.drop_column("agent_msg_hist", "tool_name")
    op.drop_column("agent_msg_hist", "tool_call_id")
    op.drop_column("agent_msg_hist", "message_idx")
    op.drop_column("agent_msg_hist", "checkpoint_id")
    op.drop_column("agent_msg_hist", "thread_id")
