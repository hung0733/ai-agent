"""change llm_group.name from BigInteger to String(80)

Revision ID: 002
Revises: 001
Create Date: 2026-04-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'llm_group',
        'name',
        existing_type=sa.BigInteger(),
        type_=sa.String(length=80),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'llm_group',
        'name',
        existing_type=sa.String(length=80),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )
