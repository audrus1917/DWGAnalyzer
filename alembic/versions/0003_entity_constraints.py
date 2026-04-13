"""add entity integrity constraints

Revision ID: 0003_entity_constraints
Revises: 0002_entity_indexes
Create Date: 2026-04-13 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003_entity_constraints"
down_revision: Union[str, Sequence[str], None] = "0002_entity_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "entity",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.text("timezone('utc', now())"),
        existing_nullable=False,
    )

    op.create_check_constraint(
        "ck_entity_to_entity_src_ne_dst",
        "entity_to_entity",
        "src_id <> dst_id",
    )
    op.create_check_constraint(
        "ck_entity_to_entity_link_not_empty",
        "entity_to_entity",
        "btrim(link) <> ''",
    )


def downgrade() -> None:
    op.drop_check_constraint(
        "ck_entity_to_entity_link_not_empty",
        "entity_to_entity",
        type_="check",
    )
    op.drop_check_constraint(
        "ck_entity_to_entity_src_ne_dst",
        "entity_to_entity",
        type_="check",
    )

    op.alter_column(
        "entity",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
        existing_nullable=False,
    )
