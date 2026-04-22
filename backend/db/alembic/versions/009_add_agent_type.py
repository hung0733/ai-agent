"""add agent_type column to agent table

Revision ID: 009
Revises: 008
Create Date: 2026-04-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add agent_type column with default 'agent'
    op.add_column(
        "agent",
        sa.Column("agent_type", sa.String(20), nullable=False, server_default="agent"),
    )

    # Update agent id 3 to 'supervisor'
    op.execute(
        sa.text("UPDATE agent SET agent_type = 'supervisor' WHERE id = 3")
    )


def downgrade() -> None:
    op.drop_column("agent", "agent_type")
