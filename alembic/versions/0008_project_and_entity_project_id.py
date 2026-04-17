"""add project model and entity.project_id

Revision ID: 0008_project_and_entity_project_id
Revises: 0007_entity_text_tsvector
Create Date: 2026-04-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008_project_and_entity_project_id"
down_revision: Union[str, Sequence[str], None] = "0007_entity_text_tsvector"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=256), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("timezone('utc', now())"),
        ),
    )

    op.add_column(
        "entity",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_entity_project_id_project",
        "entity",
        "project",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_entity_project_id", "entity", ["project_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_entity_project_id", table_name="entity")
    op.drop_constraint("fk_entity_project_id_project", "entity", type_="foreignkey")
    op.drop_column("entity", "project_id")
    op.drop_table("project")
