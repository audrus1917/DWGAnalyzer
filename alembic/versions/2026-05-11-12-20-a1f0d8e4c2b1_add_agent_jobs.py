"""add agent jobs

Revision ID: a1f0d8e4c2b1
Revises: 422b25e62394
Create Date: 2026-05-11 12:20:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'a1f0d8e4c2b1'
down_revision: Union[str, Sequence[str], None] = '422b25e62394'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'agent_job',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('status', sa.String(length=64), nullable=False),
        sa.Column('profile', sa.String(length=64), nullable=False),
        sa.Column('input_ref', sa.Text(), nullable=False),
        sa.Column('file_id', sa.Integer(), sa.ForeignKey('entity.id', ondelete='SET NULL'), nullable=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('project.id', ondelete='SET NULL'), nullable=True),
        sa.Column('options_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f('ix_agent_job_status'), 'agent_job', ['status'], unique=False)

    op.create_table(
        'agent_job_step',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('job_id', sa.Integer(), sa.ForeignKey('agent_job.id', ondelete='CASCADE'), nullable=False),
        sa.Column('step_kind', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=64), nullable=False),
        sa.Column('step_order', sa.Integer(), nullable=False),
        sa.Column('target_file_id', sa.Integer(), sa.ForeignKey('entity.id', ondelete='SET NULL'), nullable=True),
        sa.Column('input_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('result_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f('ix_agent_job_step_job_id'), 'agent_job_step', ['job_id'], unique=False)
    op.create_index(op.f('ix_agent_job_step_status'), 'agent_job_step', ['status'], unique=False)
    op.create_index('ix_agent_job_step_job_id_step_order', 'agent_job_step', ['job_id', 'step_order'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_agent_job_step_job_id_step_order', table_name='agent_job_step')
    op.drop_index(op.f('ix_agent_job_step_status'), table_name='agent_job_step')
    op.drop_index(op.f('ix_agent_job_step_job_id'), table_name='agent_job_step')
    op.drop_table('agent_job_step')
    op.drop_index(op.f('ix_agent_job_status'), table_name='agent_job')
    op.drop_table('agent_job')