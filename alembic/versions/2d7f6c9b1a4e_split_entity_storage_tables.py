"""split entity storage tables

Revision ID: 2d7f6c9b1a4e
Revises: fd23c20c1714
Create Date: 2026-05-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import geoalchemy2
from pgvector.sqlalchemy import Vector

from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "2d7f6c9b1a4e"
down_revision: Union[str, Sequence[str], None] = "fd23c20c1714"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("entity", "file_md5", new_column_name="entity_md5")

    op.create_table(
        "entity_embedding",
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("embedding", Vector(dim=768), nullable=True),
        sa.Column("entity_text", postgresql.TSVECTOR(), nullable=True),
        sa.ForeignKeyConstraint(["entity_id"], ["entity.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("entity_id"),
    )
    op.create_table(
        "entity_geom",
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                srid=4326,
                dimension=2,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["entity.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("entity_id"),
    )
    op.create_index(
        op.f("ix_entity_geom_geom"),
        "entity_geom",
        ["geom"],
        unique=False,
        postgresql_using="gist",
    )

    op.execute(
        """
        INSERT INTO entity_embedding (entity_id, embedding, entity_text)
        SELECT id, embedding, entity_text
        FROM entity
        WHERE embedding IS NOT NULL OR entity_text IS NOT NULL
        """
    )
    op.execute(
        """
        INSERT INTO entity_geom (entity_id, geom)
        SELECT id, geom
        FROM entity
        WHERE geom IS NOT NULL
        """
    )

    op.drop_index(op.f("ix_entity_geom"), table_name="entity")
    op.drop_column("entity", "geom")
    op.drop_column("entity", "entity_text")
    op.drop_column("entity", "embedding")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "entity",
        sa.Column(
            "embedding",
            Vector(dim=768),
            nullable=True,
        ),
    )
    op.add_column(
        "entity",
        sa.Column("entity_text", postgresql.TSVECTOR(), nullable=True),
    )
    op.add_column(
        "entity",
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                srid=4326,
                dimension=2,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
    )
    op.create_index(op.f("ix_entity_geom"), "entity", ["geom"], unique=False)

    op.execute(
        """
        UPDATE entity AS e
        SET embedding = ee.embedding,
            entity_text = ee.entity_text
        FROM entity_embedding AS ee
        WHERE ee.entity_id = e.id
        """
    )
    op.execute(
        """
        UPDATE entity AS e
        SET geom = eg.geom
        FROM entity_geom AS eg
        WHERE eg.entity_id = e.id
        """
    )

    op.drop_index(op.f("ix_entity_geom_geom"), table_name="entity_geom")
    op.drop_table("entity_geom")
    op.drop_table("entity_embedding")
    op.alter_column("entity", "entity_md5", new_column_name="file_md5")
