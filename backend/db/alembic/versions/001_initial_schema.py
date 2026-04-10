"""initial schema - create all 10 tables

Revision ID: 001
Revises: 
Create Date: 2026-04-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # user_acc
    op.create_table(
        'user_acc',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.String(length=200), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('phoneno', sa.String(length=20), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )

    # llm_group
    op.create_table(
        'llm_group',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['user_acc.id'], ),
    )

    # llm_endpoint
    op.create_table(
        'llm_endpoint',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('endpoint', sa.String(length=400), nullable=False),
        sa.Column('enc_key', sa.String(length=200), nullable=True),
        sa.Column('model_name', sa.String(length=200), nullable=False),
        sa.Column('max_token', sa.BigInteger(), nullable=False, server_default='4096'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['user_acc.id'], ),
    )

    # agent
    op.create_table(
        'agent',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('agent_id', sa.String(length=200), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('llm_group_id', sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('agent_id'),
        sa.ForeignKeyConstraint(['user_id'], ['user_acc.id'], ),
        sa.ForeignKeyConstraint(['llm_group_id'], ['llm_group.id'], ),
    )

    # llm_level
    op.create_table(
        'llm_level',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('llm_group_id', sa.BigInteger(), nullable=False),
        sa.Column('llm_endpoint_id', sa.BigInteger(), nullable=False),
        sa.Column('level', sa.BigInteger(), nullable=False, server_default='1'),
        sa.Column('is_confidential', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('seq_no', sa.BigInteger(), nullable=False, server_default='1'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['llm_group_id'], ['llm_group.id'], ),
        sa.ForeignKeyConstraint(['llm_endpoint_id'], ['llm_endpoint.id'], ),
    )

    # session
    op.create_table(
        'session',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('recv_agent_id', sa.BigInteger(), nullable=False),
        sa.Column('session_id', sa.String(length=200), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False, server_default='預設對話'),
        sa.Column('session_type', sa.String(length=20), nullable=False),
        sa.Column('sender_agent_id', sa.BigInteger(), nullable=True),
        sa.Column('is_confidential', sa.Boolean(), nullable=False, server_default='false'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id'),
        sa.ForeignKeyConstraint(['recv_agent_id'], ['agent.id'], ),
        sa.ForeignKeyConstraint(['sender_agent_id'], ['agent.id'], ),
    )

    # agent_msg_hist
    op.create_table(
        'agent_msg_hist',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.BigInteger(), nullable=False),
        sa.Column('step_id', sa.String(length=200), nullable=False),
        sa.Column('sender', sa.String(length=80), nullable=False),
        sa.Column('msg_type', sa.String(length=20), nullable=False),
        sa.Column('create_dt', sa.DateTime(timezone=True), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('token', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('is_summary', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_analyst', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['session_id'], ['session.id'], ),
    )

    # short_term_mem
    op.create_table(
        'short_term_mem',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.BigInteger(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('create_dt', sa.DateTime(timezone=True), nullable=False),
        sa.Column('token', sa.BigInteger(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['session_id'], ['session.id'], ),
    )

    # long_term_mem
    op.create_table(
        'long_term_mem',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('agent_id', sa.BigInteger(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('create_dt', sa.DateTime(timezone=True), nullable=False),
        sa.Column('token', sa.BigInteger(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['agent_id'], ['agent.id'], ),
    )

    # memory_block
    op.create_table(
        'memory_block',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('agent_id', sa.BigInteger(), nullable=False),
        sa.Column('memory_type', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('last_upd_dt', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['agent_id'], ['agent.id'], ),
    )


def downgrade() -> None:
    op.drop_table('memory_block')
    op.drop_table('long_term_mem')
    op.drop_table('short_term_mem')
    op.drop_table('agent_msg_hist')
    op.drop_table('session')
    op.drop_table('llm_level')
    op.drop_table('agent')
    op.drop_table('llm_endpoint')
    op.drop_table('llm_group')
    op.drop_table('user_acc')
