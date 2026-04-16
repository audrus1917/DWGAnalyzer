"""add entity_text tsvector

Revision ID: 0007_entity_text_tsvector
Revises: 0006_entity_is_table
Create Date: 2026-04-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007_entity_text_tsvector"
down_revision: Union[str, Sequence[str], None] = "0006_entity_is_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "entity",
        sa.Column("entity_text", postgresql.TSVECTOR(), nullable=True),
    )
    op.execute(
        """
        UPDATE entity
        SET entity_text = to_tsvector('russian', coalesce(description, ''))
        WHERE description IS NOT NULL AND btrim(description) <> ''
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_entity_entity_text_gin
        ON entity
        USING GIN (entity_text)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_entity_entity_text_gin")
    op.drop_column("entity", "entity_text")