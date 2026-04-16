"""add is_table to entity

Revision ID: 0006_entity_is_table
Revises: 0005_entity_file_md5
Create Date: 2026-04-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0006_entity_is_table"
down_revision: Union[str, Sequence[str], None] = "0005_entity_file_md5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("entity", sa.Column("is_table", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("entity", "is_table")
