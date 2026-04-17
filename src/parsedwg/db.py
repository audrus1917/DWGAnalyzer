from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, cast

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .settings import settings

engine = create_async_engine(settings.database_url, echo=settings.database_echo)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, expire_on_commit=False
)


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
    from .orm import Entity  # local import to avoid circular deps

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
            Entity.start_from,
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
        import uuid as _uuid
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
            "start_from": row["start_from"] or "",
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
    from .orm import Project

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


async def update_project(
    project_id: str,
    name: str | None = None,
    description: str | None = None,
    created_by: str | None = None,
) -> dict[str, str] | None:
    """Обновляет проект по id. Возвращает None, если проект не найден."""
    import uuid as _uuid

    from .orm import Project

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
    import uuid as _uuid

    from .orm import Project

    async with async_session_factory() as session:
        project = await session.get(Project, _uuid.UUID(project_id))
        if project is None:
            return False

        await session.delete(project)
        await session.commit()
        return True
