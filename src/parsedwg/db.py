"""Опеарции с БД."""

from typing import Any, cast

import uuid as _uuid

from collections.abc import AsyncGenerator

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .settings import settings
from .orm import Category, Entity, EntityType, Project

engine = create_async_engine(settings.database_url, echo=settings.database_echo)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, expire_on_commit=False
)


async def get_file_id_by_source(source_ref: str) -> str | None:
    """Возвращает UUID file-сущности по source_ref (пути к файлу)."""
    stmt = (
        select(Entity.id)
        .where(Entity.entity_type == EntityType.file)
        .where(Entity.data["source_ref"].astext == source_ref)
        .order_by(Entity.created_at.desc())
        .limit(1)
    )
    async with async_session_factory() as session:
        result = await session.execute(stmt)
        row = result.first()
    return str(row[0]) if row else None


async def get_table_blocks_by_file_id(file_id: str) -> list[dict[str, object]]:
    """Возвращает блоки-таблицы из БД, у которых parent_id = file_id."""
    stmt = (
        select(Entity.name, Entity.data)
        .where(Entity.entity_type == EntityType.block)
        .where(Entity.is_table.is_(True))
        .where(Entity.parent_id == _uuid.UUID(file_id))
        .order_by(Entity.name.asc())
    )
    async with async_session_factory() as session:
        result = await session.execute(stmt)
        rows = result.all()
    payload: list[dict[str, object]] = []
    for block_name, data in rows:
        data_dict = data if isinstance(data, dict) else {}
        table = data_dict.get("table") if isinstance(data_dict.get("table"), dict) else {}
        payload.append(
            {
                "block_name": str(block_name),
                "table": table,
            }
        )
    return payload


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI / dependency-injection compatible session provider."""
    async with async_session_factory() as session:
        yield session


async def search_entities(
    query: str,
    entity_type: str | None = None,
    limit: int = 20,
    parent_id: str | None = None,
) -> list[dict]:
    """Полнотекстовый поиск по entity_text с fallback на name и description.

    Использует PostgreSQL websearch_to_tsquery (поддерживает кавычки, минус, OR)
    и to_tsvector с конфигурацией 'russian'.
    """

    tsquery = func.websearch_to_tsquery("russian", query)
    fallback_tsvector = func.to_tsvector(
        "russian",
        func.concat_ws(" ", Entity.name, Entity.description),
    )
    entity_match = Entity.entity_text.op("@@")(tsquery)
    fallback_match = fallback_tsvector.op("@@")(tsquery)
    entity_rank = cast(Any, func.coalesce(func.ts_rank(Entity.entity_text, tsquery), 0.0))
    fallback_rank = cast(Any, func.coalesce(func.ts_rank(fallback_tsvector, tsquery), 0.0))
    priority = case((entity_match, 1), else_=0)

    stmt = (
        select(
            Entity.id,
            Entity.name,
            Entity.description,
            Entity.entity_type,
        )
        .where(
            or_(
                entity_match,
                fallback_match,
            )
        )
        .order_by(priority.desc(), entity_rank.desc(), fallback_rank.desc())
        .limit(limit)
    )
    if entity_type is not None:
        stmt = stmt.where(Entity.entity_type == entity_type)
    if parent_id is not None:
        stmt = stmt.where(Entity.parent_id == _uuid.UUID(parent_id))

    async with async_session_factory() as session:
        result = await session.execute(stmt)
        rows = result.mappings().all()

    return [
        {
            "id": str(row["id"]),
            "name": row["name"],
            "description": row["description"] or "",
            "entity_type": row["entity_type"].value
            if hasattr(row["entity_type"], "value")
            else str(row["entity_type"]),
        }
        for row in rows
    ]


async def create_all() -> None:
    """Create all tables (dev/test helper; prefer Alembic for production)."""
    from .orm import Base  # local import to avoid circular deps

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def create_project(
    name: str,
    description: str | None = None,
    created_by: str | None = None,
) -> dict[str, str]:
    """Создаёт проект и возвращает его основные поля."""

    async with async_session_factory() as session:
        project = Project(
            name=name,
            description=description,
            created_by=created_by,
        )
        session.add(project)
        await session.flush()
        await session.commit()

        return {
            "id": str(project.id),
            "name": project.name,
            "description": project.description or "",
            "created_by": project.created_by or "",
        }


async def create_category(
    name: str,
    description: str | None = None,
    parent_id: str | None = None,
) -> dict[str, str]:
    """Создаёт категорию и возвращает её основные поля."""

    parent_uuid = _uuid.UUID(parent_id) if parent_id is not None else None

    async with async_session_factory() as session:
        category = Category(
            name=name,
            description=description,
            parent_id=parent_uuid,
        )
        session.add(category)
        await session.flush()
        await session.commit()

        return {
            "id": str(category.id),
            "name": category.name,
            "description": category.description or "",
            "parent_id": str(category.parent_id) if category.parent_id is not None else "",
        }


async def update_category(
    category_id: str,
    name: str | None = None,
    description: str | None = None,
    parent_id: str | None = None,
) -> dict[str, str] | None:
    """Обновляет категорию по id. Возвращает None, если категория не найдена."""

    category_uuid = _uuid.UUID(category_id)
    parent_uuid = _uuid.UUID(parent_id) if parent_id is not None else None

    async with async_session_factory() as session:
        category = await session.get(Category, category_uuid)
        if category is None:
            return None

        if name is not None:
            category.name = name
        if description is not None:
            category.description = description
        if parent_id is not None:
            category.parent_id = parent_uuid

        await session.commit()

        return {
            "id": str(category.id),
            "name": category.name,
            "description": category.description or "",
            "parent_id": str(category.parent_id) if category.parent_id is not None else "",
        }


async def delete_category(category_id: str) -> bool:
    """Удаляет категорию по id. Возвращает True, если удаление произошло."""

    category_uuid = _uuid.UUID(category_id)

    async with async_session_factory() as session:
        category = await session.get(Category, category_uuid)
        if category is None:
            return False

        await session.delete(category)
        await session.commit()
        return True


async def list_categories(parent_id: str | None = None) -> list[dict[str, str]]:
    """Возвращает список категорий, опционально отфильтрованный по parent_id."""

    stmt = select(Category).order_by(Category.name.asc())
    if parent_id is not None:
        stmt = stmt.where(Category.parent_id == _uuid.UUID(parent_id))

    async with async_session_factory() as session:
        result = await session.execute(stmt)
        categories = result.scalars().all()

    return [
        {
            "id": str(category.id),
            "name": category.name,
            "description": category.description or "",
            "parent_id": str(category.parent_id) if category.parent_id is not None else "",
        }
        for category in categories
    ]


async def update_project(
    project_id: str,
    name: str | None = None,
    description: str | None = None,
    created_by: str | None = None,
) -> dict[str, str] | None:
    """Обновляет проект по id. Возвращает None, если проект не найден."""
    async with async_session_factory() as session:
        project = await session.get(Project, _uuid.UUID(project_id))
        if project is None:
            return None

        if name is not None:
            project.name = name
        if description is not None:
            project.description = description
        if created_by is not None:
            project.created_by = created_by

        await session.commit()

        return {
            "id": str(project.id),
            "name": project.name,
            "description": project.description or "",
            "created_by": project.created_by or "",
        }


async def delete_project(project_id: str) -> bool:
    """Удаляет проект по id. Возвращает True, если удаление произошло."""
    async with async_session_factory() as session:
        project = await session.get(Project, _uuid.UUID(project_id))
        if project is None:
            return False

        await session.delete(project)
        await session.commit()
        return True


async def get_table_blocks_for_source(source_ref: str) -> list[dict[str, object]]:
    """Возвращает блоки-таблицы из БД для заданного source_ref файла."""
    file_id_subquery = (
        select(Entity.id)
        .where(Entity.entity_type == EntityType.file)
        .where(Entity.data["source_ref"].astext == source_ref)
        .order_by(Entity.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    stmt = (
        select(Entity.name, Entity.data)
        .where(Entity.entity_type == EntityType.block)
        .where(Entity.is_table.is_(True))
        .where(Entity.parent_id == file_id_subquery)
        .order_by(Entity.name.asc())
    )

    async with async_session_factory() as session:
        result = await session.execute(stmt)
        rows = result.all()

    payload: list[dict[str, object]] = []
    for block_name, data in rows:
        data_dict = data if isinstance(data, dict) else {}
        table = data_dict.get("table") if isinstance(data_dict.get("table"), dict) else {}
        payload.append(
            {
                "block_name": str(block_name),
                "table": table,
            }
        )
    return payload
