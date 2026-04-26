"""add category model

Revision ID: 0b1f7e2c9c41
Revises: 8624e9d2be66
Create Date: 2026-04-25 19:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0b1f7e2c9c41'
down_revision: Union[str, Sequence[str], None] = '8624e9d2be66'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'category',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('parent_id', sa.UUID(), nullable=True),
        sa.Column('name', sa.String(length=512), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['parent_id'], ['category.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_category_name'), 'category', ['name'], unique=False)

    op.create_table(
        'category_to_entity',
        sa.Column('category_id', sa.UUID(), nullable=False),
        sa.Column('entity_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['category.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['entity_id'], ['entity.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('category_id', 'entity_id'),
    )


def downgrade() -> None:
    op.drop_table('category_to_entity')
    op.drop_index(op.f('ix_category_name'), table_name='category')
    op.drop_table('category')