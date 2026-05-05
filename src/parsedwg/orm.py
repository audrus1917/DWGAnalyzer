"""The main models."""

from __future__ import annotations

from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Table, Text, Column, Integer, Enum
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from geoalchemy2 import Geometry

from .constants import EntityType


class Base(DeclarativeBase):
    pass


category_to_entity = Table(
    "category_to_entity",
    Base.metadata,
    Column("category_id", Integer, ForeignKey("category.id", ondelete="CASCADE"),
           primary_key=True),
    Column("entity_id", Integer, ForeignKey("entity.id", ondelete="CASCADE"),
           primary_key=True),
)



def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "project"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    entities: Mapped[list[Entity]] = relationship("Entity", back_populates="project")


class Category(Base):
    __tablename__ = "category"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_id: Mapped[int | None] = mapped_column(
        Integer,
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

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("entity.id", ondelete="SET NULL"),
        nullable=True,
    )
    file_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("entity.id", ondelete="SET NULL"),
        nullable=True,
    )
    project_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("project.id", ondelete="SET NULL"),
        nullable=True,
    )
    entity_type: Mapped[EntityType] = mapped_column(Enum(EntityType), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_table: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_primitive: Mapped[bool | None] = mapped_column(Boolean, default=True, index=True)
    entity_md5: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
        index=True
    )

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
    embedding_data: Mapped[EntityEmbedding | None] = relationship(
        "EntityEmbedding",
        back_populates="entity",
        cascade="all, delete-orphan",
        uselist=False,
    )
    geom_data: Mapped[EntityGeom | None] = relationship(
        "EntityGeom",
        back_populates="entity",
        cascade="all, delete-orphan",
        uselist=False,
    )


class EntityEmbedding(Base):
    """Embeddings and AI interpretations for an entity."""
    __tablename__ = "entity_embedding"

    entity_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("entity.id", ondelete="CASCADE"),
        primary_key=True,
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
    entity_text: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)
    full_interpretation: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_interpretation: Mapped[str | None] = mapped_column(Text, nullable=True)

    entity: Mapped[Entity] = relationship("Entity", back_populates="embedding_data")


class EntityGeom(Base):
    __tablename__ = "entity_geom"

    entity_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("entity.id", ondelete="CASCADE"),
        primary_key=True,
    )
    geom: Mapped[str | None] = mapped_column(
        Geometry("GEOMETRY", srid=4326),
        nullable=True,
        index=True,
    )

    entity: Mapped[Entity] = relationship("Entity", back_populates="geom_data")


class EntityToEntity(Base):
    __tablename__ = "entity_to_entity"

    src_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("entity.id", ondelete="CASCADE"),
        primary_key=True,
    )
    dst_id: Mapped[int] = mapped_column(
        Integer,
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
