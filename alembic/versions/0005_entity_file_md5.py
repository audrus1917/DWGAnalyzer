"""add file_md5 to entity

Revision ID: 0005_entity_file_md5
Revises: 0004_entity_parent_id
Create Date: 2026-04-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0005_entity_file_md5"
down_revision: Union[str, Sequence[str], None] = "0004_entity_parent_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("entity", sa.Column("file_md5", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("entity", "file_md5")
