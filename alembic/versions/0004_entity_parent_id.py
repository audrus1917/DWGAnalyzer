"""add parent_id to entity

Revision ID: 0004_entity_parent_id
Revises: 0003_entity_constraints
Create Date: 2026-04-13 13:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004_entity_parent_id"
down_revision: Union[str, Sequence[str], None] = "0003_entity_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "entity",
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_entity_parent_id_entity",
        "entity",
        "entity",
        ["parent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_entity_parent_id", "entity", ["parent_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_entity_parent_id", table_name="entity")
    op.drop_constraint("fk_entity_parent_id_entity", "entity", type_="foreignkey")
    op.drop_column("entity", "parent_id")
