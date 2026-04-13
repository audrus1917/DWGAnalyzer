"""init entity schema

Revision ID: 0001_init_entity_schema
Revises:
Create Date: 2026-04-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_init_entity_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


entity_type_enum = sa.Enum(
    "folder",
    "file",
    "zipfile",
    "zipped_file",
    "block",
    "layout",
    "layer",
    "primitive",
    name="entity_type_enum",
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "entity",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("entity_type", entity_type_enum, nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=256), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.String(length=256), nullable=True),
        sa.Column("start_from", sa.Text(), nullable=True),
    )

    op.create_table(
        "entity_to_entity",
        sa.Column("src_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dst_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("link", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["src_id"], ["entity.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dst_id"], ["entity.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("src_id", "dst_id", "link"),
    )


def downgrade() -> None:
    op.drop_table("entity_to_entity")
    op.drop_table("entity")
    entity_type_enum.drop(op.get_bind(), checkfirst=True)
