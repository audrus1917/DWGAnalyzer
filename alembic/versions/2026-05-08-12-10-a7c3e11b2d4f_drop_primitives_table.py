"""move primitives into entity

Revision ID: a7c3e11b2d4f
Revises: 8dd3a74ef6f6
Create Date: 2026-05-08 12:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

import geoalchemy2


# revision identifiers, used by Alembic.
revision: str = "a7c3e11b2d4f"
down_revision: Union[str, Sequence[str], None] = "8dd3a74ef6f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


STRUCTURAL_ENTITY_TYPES = (
    "FOLDER",
    "FILE",
    "ZIPFILE",
    "ZIPPED_FILE",
    "BLOCK",
    "LAYOUT",
    "LAYER",
)


def upgrade() -> None:
    """Upgrade schema."""

    op.execute(
        """
        INSERT INTO entity (
            parent_id,
            file_id,
            project_id,
            entity_type,
            name,
            description,
            data,
            is_table,
            entity_md5,
            created_at
        )
        SELECT
            p.parent_id,
            p.file_id,
            p.project_id,
            p.entity_type,
            COALESCE(NULLIF(p.name, ''), COALESCE(p.data->>'type', 'primitive')),
            NULLIF(COALESCE(p.data->>'text', p.name, ''), ''),
            jsonb_set(COALESCE(p.data, '{}'::jsonb), '{_legacy_primitive_id}', to_jsonb(p.id), true),
            NULL,
            NULL,
            p.created_at
        FROM primitives p
        """
    )

    op.execute(
        """
        INSERT INTO entity_to_entity (src_id, dst_id, link)
        SELECT
            e.id,
            p.layer_id,
            'on_layer'
        FROM entity e
        JOIN primitives p
            ON (e.data->>'_legacy_primitive_id')::int = p.id
        WHERE p.layer_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )

    op.execute(
        """
        UPDATE entity
        SET data = data - '_legacy_primitive_id'
        WHERE data ? '_legacy_primitive_id'
        """
    )

    op.execute("DROP INDEX IF EXISTS ix_primitives_project_id")
    op.execute("DROP INDEX IF EXISTS ix_primitives_parent_id")
    op.execute("DROP INDEX IF EXISTS ix_primitives_name")
    op.execute("DROP INDEX IF EXISTS ix_primitives_layer_id")
    op.execute("DROP INDEX IF EXISTS ix_primitives_geom")
    op.execute("DROP INDEX IF EXISTS ix_primitives_file_id")
    op.execute("DROP INDEX IF EXISTS ix_primitives_entity_type")
    op.execute("DROP INDEX IF EXISTS ix_primitives_created_at")
    op.execute("DROP TABLE IF EXISTS primitives")


def downgrade() -> None:
    """Downgrade schema."""

    op.create_table(
        "primitives",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("layer_id", sa.Integer(), nullable=True),
        sa.Column(
            "entity_type",
            postgresql.ENUM(name="entitytype", create_type=False),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=512), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["entity.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["layer_id"], ["entity.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_id"], ["entity.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_primitives_created_at"), "primitives", ["created_at"], unique=False)
    op.create_index(op.f("ix_primitives_entity_type"), "primitives", ["entity_type"], unique=False)
    op.create_index(op.f("ix_primitives_file_id"), "primitives", ["file_id"], unique=False)
    op.create_index(op.f("ix_primitives_geom"), "primitives", ["geom"], unique=False)
    op.create_index(op.f("ix_primitives_layer_id"), "primitives", ["layer_id"], unique=False)
    op.create_index(op.f("ix_primitives_name"), "primitives", ["name"], unique=False)
    op.create_index(op.f("ix_primitives_parent_id"), "primitives", ["parent_id"], unique=False)
    op.create_index(op.f("ix_primitives_project_id"), "primitives", ["project_id"], unique=False)

    op.execute(
        f"""
        INSERT INTO primitives (
            parent_id,
            file_id,
            project_id,
            layer_id,
            entity_type,
            name,
            data,
            geom,
            created_at
        )
        SELECT
            e.parent_id,
            e.file_id,
            e.project_id,
            layer_link.dst_id,
            e.entity_type,
            e.name,
            e.data,
            NULL,
            e.created_at
        FROM entity e
        LEFT JOIN entity_to_entity layer_link
            ON layer_link.src_id = e.id
           AND layer_link.link = 'on_layer'
        WHERE e.file_id IS NOT NULL
          AND e.entity_type NOT IN {STRUCTURAL_ENTITY_TYPES}
        """
    )

    op.execute(
        f"""
        DELETE FROM entity
        WHERE file_id IS NOT NULL
          AND entity_type NOT IN {STRUCTURAL_ENTITY_TYPES}
        """
    )

    op.execute(
        """
        DELETE FROM entity_to_entity
        WHERE link = 'on_layer'
        """
    )