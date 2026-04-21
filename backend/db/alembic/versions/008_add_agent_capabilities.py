"""add agent capabilities and current_tasks columns

Revision ID: 008
Revises: 007
Create Date: 2026-04-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent",
        sa.Column("capabilities", sa.dialects.postgresql.JSONB(), server_default="{}"),
    )
    op.add_column(
        "agent",
        sa.Column("current_tasks", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("agent", "current_tasks")
    op.drop_column("agent", "capabilities")
