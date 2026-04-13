"""add indexes for entity search and links

Revision ID: 0002_entity_indexes
Revises: 0001_init_entity_schema
Create Date: 2026-04-13 00:15:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_entity_indexes"
down_revision: Union[str, Sequence[str], None] = "0001_init_entity_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_entity_entity_type", "entity", ["entity_type"], unique=False)
    op.create_index(
        "ix_entity_to_entity_src_id",
        "entity_to_entity",
        ["src_id"],
        unique=False,
    )
    op.create_index(
        "ix_entity_to_entity_dst_id",
        "entity_to_entity",
        ["dst_id"],
        unique=False,
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_entity_fts_name_description
        ON entity
        USING GIN (
            to_tsvector(
                'russian',
                coalesce(name, '') || ' ' || coalesce(description, '')
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_entity_embedding_ivfflat
        ON entity
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_entity_embedding_ivfflat")
    op.execute("DROP INDEX IF EXISTS ix_entity_fts_name_description")

    op.drop_index("ix_entity_to_entity_dst_id", table_name="entity_to_entity")
    op.drop_index("ix_entity_to_entity_src_id", table_name="entity_to_entity")
    op.drop_index("ix_entity_entity_type", table_name="entity")
