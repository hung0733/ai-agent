"""add agent status column

Revision ID: 005
Revises: 004
Create Date: 2026-04-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="idle"),
    )


def downgrade() -> None:
    op.drop_column("agent", "status")
