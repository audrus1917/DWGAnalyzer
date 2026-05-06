"""Database operations."""

from typing import Any, cast

import tempfile

from collections.abc import AsyncGenerator, Sequence
from pathlib import Path

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import aliased, selectinload

from .settings import settings
from .orm import Category, Entity, EntityEmbedding, EntityToEntity, EntityType, Project

engine = create_async_engine(settings.database_url, echo=settings.database_echo)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, expire_on_commit=False
)


def _parse_id(raw_id: str | int) -> int:
    """Normalize external id input to integer primary key."""

    if isinstance(raw_id, int):
        return raw_id
    try:
        return int(raw_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Некорректный id: {raw_id}") from exc


def _get_short_interpretation(value: object) -> str | None:
    embedding_data = getattr(value, "embedding_data", None)
    if embedding_data is not None:
        interpretation = getattr(embedding_data, "short_interpretation", None)
        if interpretation is not None:
            return str(interpretation)

    interpretation = getattr(value, "short_interpretation", None)
    if interpretation is None:
        return None
    return str(interpretation)


def _get_full_interpretation(value: object) -> str | None:
    embedding_data = getattr(value, "embedding_data", None)
    if embedding_data is not None:
        interpretation = getattr(embedding_data, "full_interpretation", None)
        if interpretation is not None:
            return str(interpretation)

    interpretation = getattr(value, "full_interpretation", None)
    if interpretation is None:
        return None
    return str(interpretation)


def _ensure_embedding(entity: Entity) -> EntityEmbedding:
    embedding_data = entity.embedding_data
    if embedding_data is None:
        embedding_data = EntityEmbedding(entity=entity)
        entity.embedding_data = embedding_data
    return embedding_data


def _row_value(row: object, index: int, attr_name: str) -> object:
    if isinstance(row, tuple):
        return row[index] if len(row) > index else None
    return getattr(row, attr_name, None)


async def _get_entity_with_embedding(session: AsyncSession, entity_id: str | int) -> Entity | None:
    stmt = (
        select(Entity)
        .options(selectinload(Entity.embedding_data))
        .where(Entity.id == _parse_id(entity_id))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_file_id_by_source(source_ref: str) -> str | None:
    """Return the id of a file entity by its source_ref path."""
    stmt = (
        select(Entity.id)
        .where(Entity.entity_type == EntityType.FILE)
        .where(Entity.data["source_ref"].astext == source_ref)
        .order_by(Entity.created_at.desc())
        .limit(1)
    )
    async with async_session_factory() as session:
        result = await session.execute(stmt)
        row = result.first()
    return str(row[0]) if row else None


async def get_entity_name_by_id(entity_id: str) -> str | None:
    """Return the entity name by id, or None if it is missing."""
    async with async_session_factory() as session:
        entity = await session.get(Entity, _parse_id(entity_id))
    return entity.name if entity is not None else None


async def save_short_interpretation(entity_id: str, text: str) -> None:
    """Persist short_interpretation for an entity identified by id."""
    async with async_session_factory() as session:
        entity = await _get_entity_with_embedding(session, entity_id)
        if entity is None:
            raise LookupError(f"Сущность {entity_id} не найдена.")
        embedding_data = _ensure_embedding(entity)
        embedding_data.short_interpretation = text
        session.add(embedding_data)
        await session.commit()


async def save_block_description(block_id: str, description: str) -> None:
    """Persist a block description by id."""
    async with async_session_factory() as session:
        entity = await session.get(Entity, _parse_id(block_id))
        if entity is None:
            raise LookupError(f"Блок {block_id} не найден.")
        entity.description = description
        await session.commit()


async def save_block_interpretations(
    block_id: str,
    short_interpretation: str,
    full_interpretation: str,
    description: str,
) -> None:
    """Persist block interpretations by id."""
    async with async_session_factory() as session:
        entity = await _get_entity_with_embedding(session, block_id)
        if entity is None:
            raise LookupError(f"Блок {block_id} не найден.")
        entity.description = description
        embedding_data = _ensure_embedding(entity)
        embedding_data.short_interpretation = short_interpretation
        embedding_data.full_interpretation = full_interpretation
        session.add(embedding_data)
        await session.commit()


async def list_blocks_for_interpretation(
    block_ids: list[str] | None = None,
    file_id: str | None = None,
) -> list[dict[str, str]]:
    """Return blocks prepared for batch interpretation."""

    if bool(block_ids) == bool(file_id):
        raise ValueError("Нужно указать либо block_ids, либо file_id.")

    stmt = (
        select(Entity.id, Entity.name, Entity.description, Entity.file_id)
        .where(Entity.entity_type == EntityType.BLOCK)
    )
    id_order: dict[int, int] = {}

    if block_ids:
        parsed_ids = [_parse_id(block_id) for block_id in block_ids]
        id_order = {block_id: index for index, block_id in enumerate(parsed_ids)}
        stmt = stmt.where(Entity.id.in_(parsed_ids))
    else:
        file_entity_id = _parse_id(file_id)
        stmt = stmt.where(Entity.parent_id == file_entity_id).order_by(Entity.name.asc(), Entity.id.asc())

    async with async_session_factory() as session:
        result = await session.execute(stmt)
        rows = result.mappings().all()

    payload = [
        {
            "id": str(row["id"]),
            "name": row["name"],
            "description": row["description"] or "",
            "file_id": str(row["file_id"]) if row["file_id"] is not None else "",
        }
        for row in rows
    ]
    if id_order:
        payload.sort(key=lambda item: id_order[_parse_id(item["id"])])
    return payload


async def list_multileaders_for_nearest_lookup(
    file_id: str | None = None,
) -> list[dict[str, str]]:
    """Return MULTILEADER entities together with the source_ref of the source file."""

    file_entity = aliased(Entity)
    stmt = (
        select(
            Entity.id,
            Entity.file_id,
            Entity.name,
            Entity.data,
            Entity.created_at,
            file_entity.data["source_ref"].astext.label("source_ref"),
        )
        .join(file_entity, Entity.file_id == file_entity.id)
        .where(Entity.entity_type == "MULTILEADER")
        .order_by(
            Entity.file_id.asc(),
            Entity.created_at.asc(),
            Entity.id.asc(),
        )
    )
    if file_id is not None:
        stmt = stmt.where(Entity.file_id == _parse_id(file_id))

    async with async_session_factory() as session:
        result = await session.execute(stmt)
        rows = result.mappings().all()

    payload: list[dict[str, str]] = []
    for row in rows:
        data = row["data"] if isinstance(row["data"], dict) else {}
        payload.append(
            {
                "id": str(row["id"]),
                "file_id": str(row["file_id"]) if row["file_id"] is not None else "",
                "name": str(row["name"] or ""),
                "source_ref": str(row["source_ref"] or ""),
                "block": str(data.get("block") or ""),
                "layer": str(data.get("layer") or ""),
            }
        )
    return payload


def _collect_annotation_texts_from_rows(rows: Sequence[Sequence[object]]) -> list[str]:
    seen: set[str] = set()
    annotation_texts: list[str] = []

    for row_description, row_data in rows:
        text_candidates: list[str] = []
        if isinstance(row_data, dict):
            for key in ("annotation_text", "text"):
                value = str(row_data.get(key, "") or "").strip()
                if value:
                    text_candidates.append(value)
        description_value = str(row_description or "").strip()
        if description_value:
            text_candidates.append(description_value)

        for value in text_candidates:
            if value in seen:
                continue
            seen.add(value)
            annotation_texts.append(value)

    return annotation_texts


def _resolve_source_ref_to_drawing_path(source_ref: str, temp_dir: Path) -> Path:
    from .process_tree import DWGTreeProcessor

    if "::" not in source_ref:
        return Path(source_ref)

    archive_path_str, member_name = source_ref.split("::", 1)
    return DWGTreeProcessor.extract_from_zip(Path(archive_path_str), member_name, temp_dir)


def _get_block_layout_by_name(doc, block_name: str):
    for layout in doc.layouts:
        if str(layout.name) == block_name:
            return layout
    for block in doc.blocks:
        if str(block.name) == block_name:
            return block
    if block_name == "Model" or block_name.startswith("*Model_Space"):
        return doc.modelspace()
    return None


def _collect_block_annotation_texts_from_source(block_name: str, source_ref: str) -> list[str]:
    from .process_tree import DWGTreeProcessor
    from .utils import get_mleader_annotation_text

    if not source_ref.strip():
        return []

    try:
        with tempfile.TemporaryDirectory(prefix="parsedwg-block-annotations-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            drawing_path = _resolve_source_ref_to_drawing_path(source_ref, temp_dir)
            doc = DWGTreeProcessor.read_drawing(drawing_path)
            layout = _get_block_layout_by_name(doc, block_name)
            if layout is None:
                return []

            seen: set[str] = set()
            annotation_texts: list[str] = []
            for entity in layout:
                if str(entity.dxftype()) != "MULTILEADER":
                    continue
                text = get_mleader_annotation_text(entity)
                if not text or text in seen:
                    continue
                seen.add(text)
                annotation_texts.append(text)
            return annotation_texts
    except (FileNotFoundError, OSError, RuntimeError, ValueError):
        return []


async def get_full_description(
    block_name: str,
    file_id: str | None = None,
) -> dict[str, object] | None:
    """Return the full description of a BLOCK entity.

    Includes its name, layers (name + short_interpretation), attributes of
    INSERT primitives, and INSERT entities whose name matches the block name.
    """
    async with async_session_factory() as session:
        block_stmt = (
            select(Entity)
            .options(selectinload(Entity.embedding_data))
            .where(Entity.entity_type == EntityType.BLOCK)
            .where(Entity.name == block_name)
        )
        if file_id is not None:
            block_stmt = block_stmt.where(Entity.file_id == _parse_id(file_id))
        block_stmt = block_stmt.limit(1)
        block_result = await session.execute(block_stmt)
        block = block_result.scalar_one_or_none()
        if block is None:
            return None

        layer_stmt = (
            select(Entity.name, EntityEmbedding.short_interpretation)
            .select_from(Entity)
            .outerjoin(EntityEmbedding, EntityEmbedding.entity_id == Entity.id)
            .where(Entity.entity_type == EntityType.LAYER)
        )
        if block.file_id is not None:
            layer_stmt = layer_stmt.where(Entity.file_id == block.file_id)
        elif getattr(block, "parent_id", None) is not None:
            layer_stmt = layer_stmt.where(Entity.parent_id == block.parent_id)
        layer_stmt = layer_stmt.order_by(Entity.name.asc(), Entity.id.asc())
        layer_rows = await session.execute(layer_stmt)
        layers = []
        for row in layer_rows:
            name = _row_value(row, 0, "name")
            short_interpretation = _row_value(row, 1, "short_interpretation")
            layers.append(
                {
                    "name": str(name),
                    "short_interpretation": (
                        str(short_interpretation) if short_interpretation is not None else None
                    ),
                }
            )

        attrib_stmt = select(Entity.data).where(Entity.data["block"].astext == block_name)
        if block.file_id is not None:
            attrib_stmt = attrib_stmt.where(Entity.file_id == block.file_id)
        attrib_rows = await session.execute(attrib_stmt)
        attributes: dict[str, object] = {}
        for row in attrib_rows:
            row_data = _row_value(row, 0, "data")
            if not isinstance(row_data, dict):
                continue
            row_attribs = row_data.get("attribs")
            if isinstance(row_attribs, dict):
                attributes.update(row_attribs)

        inserts_stmt = (
            select(Entity.id, Entity.parent_id, Entity.file_id, Entity.data)
            .where(Entity.name == block_name)
        )
        if block.file_id is not None:
            inserts_stmt = inserts_stmt.where(Entity.file_id == block.file_id)
        insert_rows = await session.execute(inserts_stmt)
        inserts = []
        for row in insert_rows:
            row_id = _row_value(row, 0, "id")
            row_parent_id = _row_value(row, 1, "parent_id")
            row_file_id = _row_value(row, 2, "file_id")
            row_data = _row_value(row, 3, "data")
            if row_id == block.id:
                continue
            inserts.append(
                {
                    "id": str(row_id),
                    "parent_id": str(row_parent_id) if row_parent_id is not None else None,
                    "file_id": str(row_file_id) if row_file_id is not None else None,
                    "data": row_data if isinstance(row_data, dict) else {},
                }
            )

        multileader_stmt = (
            select(Entity.description, Entity.data)
            .where(Entity.file_id == block.file_id)
            .where(Entity.entity_type == EntityType.MLEADER)
        )
        multileader_rows = await session.execute(multileader_stmt)
        annotation_texts = _collect_annotation_texts_from_rows(multileader_rows)

        if not annotation_texts and block.file_id is not None:
            source_ref_stmt = (
                select(Entity.data["source_ref"].astext)
                .where(Entity.id == block.file_id)
                .limit(1)
            )
            source_ref_result = await session.execute(source_ref_stmt)
            source_ref_row = source_ref_result.first()
            source_ref = str(source_ref_row[0] or "") if source_ref_row else ""
            if source_ref:
                annotation_texts = _collect_block_annotation_texts_from_source(block_name, source_ref)

    return {
        "id": str(block.id),
        "name": block.name,
        "description": block.description,
        "short_interpretation": _get_short_interpretation(block),
        "full_interpretation": _get_full_interpretation(block),
        "layers": layers,
        "attributes": attributes,
        "inserts": inserts,
        "insert_count": len(inserts),
        "annotation_texts": annotation_texts,
    }


async def get_full_description_by_id(block_id: str) -> dict[str, object] | None:
    """Return the full block description by id."""

    async with async_session_factory() as session:
        block = await session.get(Entity, _parse_id(block_id))
        if block is None:
            return None
    return await get_full_description(block.name, file_id=str(block.file_id) if block.file_id else None)


async def list_blocks_for_export(file_id: str) -> list[dict[str, object]]:
    """Return BLOCK entity data for XLSX export."""
    file_entity_id = _parse_id(file_id)
    stmt = (
        select(Entity.name)
        .where(Entity.entity_type == EntityType.BLOCK)
        .where(Entity.parent_id == file_entity_id)
        .order_by(Entity.name.asc())
    )

    async with async_session_factory() as session:
        result = await session.execute(stmt)
        block_names = [str(row[0]) for row in result.all()]

    payload: list[dict[str, object]] = []
    for block_name in block_names:
        block_data = await get_full_description(block_name, file_id=file_id)
        if block_data is not None:
            payload.append(block_data)
    return payload


async def get_table_blocks_by_file_id(file_id: str) -> list[dict[str, object]]:
    """Return table blocks from the DB whose parent_id equals file_id."""
    stmt = (
        select(Entity.name, Entity.data)
        .where(Entity.entity_type == EntityType.BLOCK)
        .where(Entity.is_table.is_(True))
        .where(Entity.parent_id == _parse_id(file_id))
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
    """Run full-text search on entity_text with fallback to name and description.

    Uses PostgreSQL websearch_to_tsquery, which supports quotes, minus, and OR,
    together with to_tsvector configured for Russian.
    """

    tsquery = func.websearch_to_tsquery("russian", query)
    fallback_tsvector = func.to_tsvector(
        "russian",
        func.concat_ws(" ", Entity.name, Entity.description),
    )
    entity_text = EntityEmbedding.entity_text
    entity_match = entity_text.op("@@")(tsquery)
    fallback_match = fallback_tsvector.op("@@")(tsquery)
    entity_rank = cast(Any, func.coalesce(func.ts_rank(entity_text, tsquery), 0.0))
    fallback_rank = cast(Any, func.coalesce(func.ts_rank(fallback_tsvector, tsquery), 0.0))
    priority = case((entity_match, 1), else_=0)

    stmt = (
        select(
            Entity.id,
            Entity.name,
            Entity.description,
            Entity.entity_type,
        )
        .join(EntityEmbedding, EntityEmbedding.entity_id == Entity.id, isouter=True)
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
        stmt = stmt.where(Entity.parent_id == _parse_id(parent_id))

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
    """Create a project and return its main fields."""

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


def _normalize_scored_meanings(meanings: list[dict[str, object]]) -> list[dict[str, object]]:
    normalized_by_meaning: dict[str, dict[str, object]] = {}

    for item in meanings:
        meaning = item.get("meaning")
        if not isinstance(meaning, str):
            continue

        normalized_meaning = " ".join(meaning.strip().split())
        if not normalized_meaning:
            continue

        score = item.get("score")
        normalized_score = float(score) if isinstance(score, (int, float)) else None
        lowered = normalized_meaning.lower()
        existing = normalized_by_meaning.get(lowered)
        if existing is None:
            normalized_by_meaning[lowered] = {
                "meaning": normalized_meaning,
                "score": normalized_score,
            }
            continue

        existing_score = existing.get("score")
        if not isinstance(existing_score, (int, float)) or (
            normalized_score is not None and normalized_score > float(existing_score)
        ):
            normalized_by_meaning[lowered] = {
                "meaning": normalized_meaning,
                "score": normalized_score,
            }

    def _score_key(item: dict[str, object]) -> float:
        score = item.get("score")
        return float(score) if isinstance(score, (int, float)) else -1.0

    return sorted(
        normalized_by_meaning.values(),
        key=lambda item: (-_score_key(item), str(item["meaning"]).lower()),
    )


def _build_category_lookup(categories: Sequence[Category]) -> dict[str, Category]:
    lookup: dict[str, Category] = {}

    for category in categories:
        category_name = " ".join(category.name.strip().split()).lower()
        if category_name and category_name not in lookup:
            lookup[category_name] = category

        for alias in category.aliases or []:
            normalized_alias = " ".join(alias.strip().split()).lower()
            if normalized_alias and normalized_alias not in lookup:
                lookup[normalized_alias] = category

    return lookup


def _get_category_payload(meanings: list[dict[str, object]]) -> tuple[str | None, list[str]]:
    normalized = _normalize_scored_meanings(meanings)
    if not normalized:
        return None, []

    name = str(normalized[0]["meaning"])
    aliases: list[str] = []
    seen: set[str] = {name.lower()}

    for item in normalized[1:]:
        alias = str(item["meaning"])
        lowered = alias.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        aliases.append(alias)

    return name, aliases


async def list_entities_for_semantic_categorization(
    entity_ids: list[str] | None = None,
    entity_type: str | None = None,
) -> list[dict[str, str]]:
    """Return entities for AI categorization by id or entity_type."""

    if bool(entity_ids) == bool(entity_type):
        raise ValueError("Нужно указать либо entity_ids, либо entity_type.")

    stmt = select(Entity.id, Entity.name, Entity.description, Entity.entity_type)
    order_by_name = False
    id_order: dict[int, int] = {}

    if entity_ids:
        parsed_ids = [_parse_id(entity_id) for entity_id in entity_ids]
        id_order = {entity_id: index for index, entity_id in enumerate(parsed_ids)}
        stmt = stmt.where(Entity.id.in_(parsed_ids))
    else:
        stmt = stmt.where(Entity.entity_type == entity_type)
        order_by_name = True

    if order_by_name:
        stmt = stmt.order_by(Entity.name.asc(), Entity.id.asc())

    async with async_session_factory() as session:
        result = await session.execute(stmt)
        rows = result.mappings().all()

    payload = [
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

    if id_order:
        payload.sort(key=lambda item: id_order[_parse_id(item["id"])])

    return payload


async def assign_semantic_category(
    entity_id: str,
    meanings: list[dict[str, object]],
) -> dict[str, object]:
    """Create or find a category from AI meanings and link it to the entity."""

    entity_pk = _parse_id(entity_id)

    async with async_session_factory() as session:
        entity_result = await session.execute(
            select(Entity)
            .options(selectinload(Entity.categories))
            .where(Entity.id == entity_pk)
        )
        entity = entity_result.scalar_one_or_none()
        if entity is None:
            raise LookupError(f"Сущность {entity_pk} не найдена.")

        category_result = await session.execute(select(Category).order_by(Category.name.asc()))
        categories = category_result.scalars().all()
        category_lookup = _build_category_lookup(categories)

        normalized_meanings = _normalize_scored_meanings(meanings)
        category_name, aliases = _get_category_payload(normalized_meanings)
        meaning_names = [str(value["meaning"]) for value in normalized_meanings]

        if category_name is None:
            return {
                "entity_id": str(entity.id),
                "entity_name": entity.name,
                "entity_type": str(entity.entity_type),
                "category_id": "",
                "category_name": "",
                "matched_meaning": "",
                "status": "no-tags",
                "meanings": meaning_names,
            }

        category = None
        matched_meaning = ""
        for meaning in meaning_names:
            category = category_lookup.get(meaning.lower())
            if category is not None:
                matched_meaning = meaning
                break

        category_created = False
        if category is None:
            category = Category(name=category_name, aliases=aliases or None)
            session.add(category)
            await session.flush()
            category_created = True
            matched_meaning = category_name

        already_linked = any(existing.id == category.id for existing in entity.categories)
        if not already_linked:
            entity.categories.append(category)

        await session.commit()

        status = "created" if category_created else "linked-existing"
        if already_linked:
            status = "already-linked"

        return {
            "entity_id": str(entity.id),
            "entity_name": entity.name,
            "entity_type": str(entity.entity_type),
            "category_id": str(category.id),
            "category_name": category.name,
            "matched_meaning": matched_meaning,
            "status": status,
            "meanings": meaning_names,
        }


async def assign_semantic_categories(
    categorizations: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Create or find categories from AI meanings and link them to entities."""

    if not categorizations:
        return []

    results: list[dict[str, object]] = []
    for item in categorizations:
        raw_meanings = item.get("meanings", [])
        normalized_meanings = (
            [value for value in raw_meanings if isinstance(value, dict)]
            if isinstance(raw_meanings, list)
            else []
        )
        results.append(
            await assign_semantic_category(
                entity_id=str(item["entity_id"]),
                meanings=normalized_meanings,
            )
        )
    return results


async def create_category(
    name: str,
    description: str | None = None,
    parent_id: str | None = None,
) -> dict[str, str]:
    """Create a category and return its main fields."""

    parent_entity_id = _parse_id(parent_id) if parent_id is not None else None

    async with async_session_factory() as session:
        category = Category(
            name=name,
            description=description,
            parent_id=parent_entity_id,
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
    """Update a category by id. Return None if the category is not found."""

    category_entity_id = _parse_id(category_id)
    parent_entity_id = _parse_id(parent_id) if parent_id is not None else None

    async with async_session_factory() as session:
        category = await session.get(Category, category_entity_id)
        if category is None:
            return None

        if name is not None:
            category.name = name
        if description is not None:
            category.description = description
        if parent_id is not None:
            category.parent_id = parent_entity_id

        await session.commit()

        return {
            "id": str(category.id),
            "name": category.name,
            "description": category.description or "",
            "parent_id": str(category.parent_id) if category.parent_id is not None else "",
        }


async def delete_category(category_id: str) -> bool:
    """Delete a category by id. Return True if deletion happened."""

    category_entity_id = _parse_id(category_id)

    async with async_session_factory() as session:
        category = await session.get(Category, category_entity_id)
        if category is None:
            return False

        await session.delete(category)
        await session.commit()
        return True


async def list_categories(parent_id: str | None = None) -> list[dict[str, str]]:
    """Return categories, optionally filtered by parent_id."""

    stmt = select(Category).order_by(Category.name.asc())
    if parent_id is not None:
        stmt = stmt.where(Category.parent_id == _parse_id(parent_id))

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
    """Update a project by id. Return None if the project is not found."""
    async with async_session_factory() as session:
        project = await session.get(Project, _parse_id(project_id))
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
    """Delete a project by id. Return True if deletion happened."""
    async with async_session_factory() as session:
        project = await session.get(Project, _parse_id(project_id))
        if project is None:
            return False

        await session.delete(project)
        await session.commit()
        return True


async def get_table_blocks_for_source(source_ref: str) -> list[dict[str, object]]:
    """Return table blocks from the DB for the given file source_ref."""
    file_id_subquery = (
        select(Entity.id)
        .where(Entity.entity_type == EntityType.FILE)
        .where(Entity.data["source_ref"].astext == source_ref)
        .order_by(Entity.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    stmt = (
        select(Entity.name, Entity.data)
        .where(Entity.entity_type == EntityType.BLOCK)
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


def get_block_full_description(block: dict[str, object]) -> str:
    """Generate a text description of a block for AI based on its data."""

    name = str(block.get("name", "") or "")
    description = str(block.get("description", "") or "")
    layers = block.get("layers", [])
    attributes = block.get("attributes", {})
    inserts = block.get("inserts", [])
    insert_count = block.get("insert_count", 0)
    annotation_texts = block.get("annotation_texts", [])

    lines: list[str] = []
    if name:
        lines.append(f"Имя блока: {name}")
    if description:
        lines.append(f"Описание: {description}")

    if isinstance(layers, list) and layers:
        layer_parts: list[str] = []
        for layer in layers:
            if not isinstance(layer, dict):
                continue
            layer_name = str(layer.get("name", "") or "").strip()
            if not layer_name:
                continue
            layer_meaning = str(layer.get("short_interpretation", "") or "").strip()
            if layer_meaning:
                layer_parts.append(f"{layer_name} ({layer_meaning})")
            else:
                layer_parts.append(layer_name)
        if layer_parts:
            lines.append("Связанные слои: " + "; ".join(layer_parts))

    if isinstance(attributes, dict) and attributes:
        attribute_parts = [f"{key}={attributes[key]}" for key in sorted(attributes)]
        lines.append("Атрибуты: " + "; ".join(attribute_parts))

    if isinstance(insert_count, int):
        lines.append(f"Количество вставок: {insert_count}")

    if isinstance(annotation_texts, list) and annotation_texts:
        annotation_parts = [str(value).strip() for value in annotation_texts if str(value).strip()]
        if annotation_parts:
            lines.append("Тексты аннотаций: " + "; ".join(annotation_parts))

    if isinstance(inserts, list) and inserts:
        insert_parts: list[str] = []
        for insert in inserts[:5]:
            if not isinstance(insert, dict):
                continue
            insert_data = insert.get("data", {})
            if not isinstance(insert_data, dict):
                insert_data = {}
            fragment: list[str] = []
            block_name = str(insert_data.get("block", "") or "").strip()
            if block_name:
                fragment.append(f"block={block_name}")
            layer_name = str(insert_data.get("layer", "") or "").strip()
            if layer_name:
                fragment.append(f"layer={layer_name}")
            attribs = insert_data.get("attribs", {})
            if isinstance(attribs, dict) and attribs:
                fragment.append(
                    "attribs=" + ", ".join(f"{key}={attribs[key]}" for key in sorted(attribs))
                )
            if fragment:
                insert_parts.append("{" + "; ".join(fragment) + "}")
        if insert_parts:
            lines.append("Примеры вставок: " + "; ".join(insert_parts))

    return "\n".join(lines).strip()