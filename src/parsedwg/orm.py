from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Table, Text, Column
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from geoalchemy2 import Geometry

class Base(DeclarativeBase):
    pass


category_to_entity = Table(
    "category_to_entity",
    Base.metadata,
    Column("category_id", UUID(as_uuid=True), ForeignKey("category.id", ondelete="CASCADE"),
           primary_key=True),
    Column("entity_id", UUID(as_uuid=True), ForeignKey("entity.id", ondelete="CASCADE"),
           primary_key=True),
)

class EntityType(str, enum.Enum):
    folder = "FOLDER"
    file = "FILE"
    zipfile = "ZIPFILE"
    zipped_file = "ZIPPED_FILE"
    block = "BLOCK"
    layout = "LAYOUT"
    layer = "LAYER"
 

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "project"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    entities: Mapped[list[Entity]] = relationship("Entity", back_populates="project")


class Category(Base):
    __tablename__ = "category"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("category.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    aliases: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True) 
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    parent: Mapped[Category | None] = relationship(
        "Category",
        remote_side="Category.id",
        back_populates="children",
        foreign_keys=[parent_id],
    )
    children: Mapped[list[Category]] = relationship(
        "Category",
        back_populates="parent",
        foreign_keys=[parent_id],
    )
    entities: Mapped[list[Entity]] = relationship(
        "Entity",
        secondary=category_to_entity,
        back_populates="categories",
    )


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
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entity.id", ondelete="SET NULL"),
        nullable=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project.id", ondelete="SET NULL"),
        nullable=True,
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_interpretation: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_interpretation: Mapped[str | None] = mapped_column(Text, nullable=True)
    data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_table: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_primitive: Mapped[bool | None] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
        index=True
    )

    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
    entity_text: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)

    file_md5: Mapped[str | None] = mapped_column(String(32), nullable=True)
    geom: Mapped[str | None] = mapped_column(Geometry("GEOMETRY", srid=4326),
                                             nullable=True, index=True)

    parent: Mapped[Entity | None] = relationship(
        "Entity",
        remote_side="Entity.id",
        back_populates="children",
        foreign_keys=[parent_id],
    )
    project: Mapped[Project | None] = relationship("Project", back_populates="entities")
    children: Mapped[list[Entity]] = relationship(
        "Entity",
        back_populates="parent",
        foreign_keys=[parent_id],
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
    categories: Mapped[list[Category]] = relationship(
        "Category",
        secondary=category_to_entity,
        back_populates="entities",
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
