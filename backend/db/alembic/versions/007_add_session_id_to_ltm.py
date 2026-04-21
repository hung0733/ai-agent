"""Add session_id column to long_term_mem.

Revision ID: 007
Revises: 006
Create Date: 2026-04-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("long_term_mem", sa.Column("session_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key("fk_long_term_mem_session", "long_term_mem", "session", ["session_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_long_term_mem_session", "long_term_mem", type_="foreignkey")
    op.drop_column("long_term_mem", "session_id")
