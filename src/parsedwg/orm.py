from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class EntityType(str, enum.Enum):
    folder = "folder"
    file = "file"
    zipfile = "zipfile"
    zipped_file = "zipped_file"
    block = "block"
    layout = "layout"
    layer = "layer"
    primitive = "primitive"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Entity(Base):
    __tablename__ = "entity"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entity.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_type: Mapped[EntityType] = mapped_column(
        Enum(EntityType, name="entity_type_enum"), nullable=False
    )
    data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # pgvector embedding — nomic-embed-text (768 dims); заполняется командой index
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    created_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=_utcnow
    )
    updated_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    start_from: Mapped[str | None] = mapped_column(Text, nullable=True)

    parent: Mapped[Entity | None] = relationship(
        "Entity",
        remote_side="Entity.id",
        back_populates="children",
    )
    children: Mapped[list[Entity]] = relationship(
        "Entity",
        back_populates="parent",
    )

    src_links: Mapped[list[EntityToEntity]] = relationship(
        "EntityToEntity",
        foreign_keys="EntityToEntity.src_id",
        back_populates="src_entity",
        cascade="all, delete-orphan",
    )
    dst_links: Mapped[list[EntityToEntity]] = relationship(
        "EntityToEntity",
        foreign_keys="EntityToEntity.dst_id",
        back_populates="dst_entity",
        cascade="all, delete-orphan",
    )


class EntityToEntity(Base):
    __tablename__ = "entity_to_entity"

    src_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entity.id", ondelete="CASCADE"),
        primary_key=True,
    )
    dst_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entity.id", ondelete="CASCADE"),
        primary_key=True,
    )
    link: Mapped[str] = mapped_column(String(64), nullable=False, primary_key=True)

    src_entity: Mapped[Entity] = relationship(
        "Entity", foreign_keys=[src_id], back_populates="src_links"
    )
    dst_entity: Mapped[Entity] = relationship(
        "Entity", foreign_keys=[dst_id], back_populates="dst_links"
    )
