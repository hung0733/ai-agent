"""add wing and room columns to long_term_mem

Revision ID: 006
Revises: 005
Create Date: 2026-04-17
"""

from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("long_term_mem", sa.Column("wing", sa.String(80), nullable=True))
    op.add_column("long_term_mem", sa.Column("room", sa.String(80), nullable=True))


def downgrade() -> None:
    op.drop_column("long_term_mem", "room")
    op.drop_column("long_term_mem", "wing")
