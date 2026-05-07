"""The main models."""

from __future__ import annotations

from datetime import datetime

from geoalchemy2 import Geometry
from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Table, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .constants import EntityType
from .settings import settings


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


def _get_now() -> datetime:
    return datetime.now((settings.tz))


class Project(Base):
    """A project is a collection of entities, typically representing a single document or data source."""

    __tablename__ = "project"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_get_now
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
    """An entity represents a piece of information extracted from documents."""

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
    is_table: Mapped[bool | None] = mapped_column(nullable=True)
    entity_md5: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_get_now,
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
    primitives: Mapped[list[Primitive]] = relationship(
        "Primitive",
        back_populates="parent",
        cascade="all, delete-orphan",
        foreign_keys="Primitive.parent_id",
    )


class Primitive(Base):
    __tablename__ = "primitives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("entity.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("entity.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("project.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    layer_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("entity.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entity_type: Mapped[EntityType] = mapped_column(Enum(EntityType), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(512), nullable=True, index=True)
    data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    geom: Mapped[str | None] = mapped_column(
        Geometry("GEOMETRY", srid=4326),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_get_now,
        index=True,
    )

    parent: Mapped[Entity] = relationship(
        "Entity",
        back_populates="primitives",
        foreign_keys=[parent_id],
    )
    file: Mapped[Entity] = relationship("Entity", foreign_keys=[file_id])
    project: Mapped[Project | None] = relationship("Project")
    layer: Mapped[Entity | None] = relationship("Entity", foreign_keys=[layer_id])



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
