"""RAG utilities: embeddings via nomic-embed-text and answer generation via llama3.2.

Ollama must be running locally at http://localhost:11434.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

import httpx
from sqlalchemy import select, text, cast, String, func, or_
from sqlalchemy.orm import selectinload

from .db import async_session_factory
from .orm import Entity, EntityEmbedding
from .settings import settings

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = settings.ai_base_url
EMBED_MODEL = settings.ai_embed_model
LLM_MODEL = settings.ai_model
EMBED_DIM = 768
# Timeout for Ollama requests; generation may take a while.
_TIMEOUT = httpx.Timeout(settings.ai_timeout_seconds)
_QUESTION_TERM_PATTERNS = (
    re.compile(
        (
            r"^\s*(?:что\s+такое|что\s+значит|объясни(?:\s+термин)?|"
            r"поясни(?:\s+термин)?|дай\s+определение(?:\s+термину)?|"
            r"определи)\s+(?P<body>.+?)\s*[?.!]*\s*$"
        ),
        re.IGNORECASE,
    ),
)
_TERM_CONTEXT_SPLIT_RE = re.compile(
    (
        r"^(?P<term>.+?)(?P<context>\s+(?:для|в\s+контексте|"
        r"применительно\s+к|на\s+чертеже|в\s+чертежах|в\s+документации|"
        r"по\s+проекту)\b.+)$"
    ),
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Low-level Ollama clients.
# ---------------------------------------------------------------------------


async def _embed(text_input: str) -> list[float]:
    """Get a text embedding via Ollama /api/embed."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json={"model": EMBED_MODEL, "input": text_input},
        )
        response.raise_for_status()
    data: dict[str, Any] = response.json()
    # Ollama /api/embed returns {"embeddings": [[...]], ...}.
    raw = data.get("embeddings") or data.get("embedding")
    if not raw:
        raise ValueError(f"Ollama не вернул эмбеддинг: {data}")
    first = raw[0]
    if isinstance(first, list):
        return first  # type: ignore[return-value]
    return raw  # type: ignore[return-value]


async def _generate(prompt: str, context_docs: list[str]) -> str:
    """Ask the LLM a question with context from retrieved documents."""
    full_prompt = _build_generation_prompt(prompt, context_docs)
    system = (
        "Ты — ассистент по технической документации и чертежам. "
        "Целевой термин, который нужно пояснить, передаётся отдельно от "
        "дополнительного контекста. "
        "Отвечай на основе предоставленного контекста. "
        "Если ответа в контексте нет, скажи об этом явно."
    )
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": LLM_MODEL, "prompt": full_prompt, "system": system, "stream": False},
        )
        response.raise_for_status()
    data = response.json()
    return data.get("response", "").strip()


def _extract_target_term(question: str) -> tuple[str | None, str | None]:
    """Extract the target term and additional context from a term-related question."""
    cleaned_question = question.strip()
    for pattern in _QUESTION_TERM_PATTERNS:
        match = pattern.match(cleaned_question)
        if not match:
            continue

        body = match.group("body").strip()
        quoted_match = re.search(r"[\"«](?P<term>.+?)[\"»]", body)
        if quoted_match:
            term = quoted_match.group("term").strip(" \t,;:-")
            context = re.sub(r"[\"«].+?[\"»]", " ", body, count=1).strip(" \t,;:-")
            return term or None, context or None

        context_match = _TERM_CONTEXT_SPLIT_RE.match(body)
        if context_match:
            term = context_match.group("term").strip(" \t,;:-")
            context = context_match.group("context").strip()
            return term or None, context or None

        body = body.strip(" \t\"'«».,;:-")
        return body or None, None

    return None, None


def _build_generation_prompt(question: str, context_docs: list[str]) -> str:
    """Build a prompt that separates the target term from the rest of the context."""
    target_term, extra_question_context = _extract_target_term(question)
    context = "\n\n".join(
        f"[{i + 1}] {doc}" for i, doc in enumerate(context_docs)
    ) or "Контекст не найден."

    if target_term:
        additional_context = extra_question_context or "Не указан."
        return (
            f"Целевой термин:\n{target_term}\n\n"
            f"Дополнительный контекст запроса:\n{additional_context}\n\n"
            f"Контекст из документов:\n{context}\n\n"
            "Сначала поясни именно целевой термин. Дополнительный контекст "
            "используй только для уточнения ответа.\n\n"
            "Ответ:"
        )

    return (
        f"Запрос пользователя:\n{question.strip()}\n\n"
        f"Контекст из документов:\n{context}\n\n"
        "Ответ:"
    )


# ---------------------------------------------------------------------------
# Indexing.
# ---------------------------------------------------------------------------


def _extract_table_rows_text(data: Any) -> str | None:
    print(f"Table data: {data}")
    if not isinstance(data, dict):
        return None

    table = data.get("table")
    if not isinstance(table, dict):
        return None

    rows = table.get("rows")
    if not isinstance(rows, list):
        return None

    rendered_rows: list[str] = []
    for row in rows:
        if not isinstance(row, list):
            continue
        rendered = " | ".join(str(cell) for cell in row)
        if rendered:
            rendered_rows.append(rendered)

    if not rendered_rows:
        return None

    print(f"Rendered table rows: {rendered_rows}")
    return "\n".join(rendered_rows)


def _entity_text(entity: Entity) -> str:
    """Build embedding text from entity fields."""
    parts = [entity.name]
    if entity.description:
        parts.append(entity.description)

    # For table blocks, explicitly append rows from data["table"]["rows"].
    if getattr(entity, "is_table", False):
        table_rows_text = _extract_table_rows_text(entity.data)
        if table_rows_text:
            parts.append(table_rows_text)

    if entity.data:
        try:
            parts.append(json.dumps(entity.data, ensure_ascii=False))
        except (TypeError, ValueError):
            pass
    return " ".join(parts)


async def index_entities(
    entity_type: str | None = None,
    batch_size: int = 50,
    reindex: bool = False,
) -> int:
    """Generate embeddings for DB entities and persist them.

    Args:
        entity_type: if provided, index only this entity type.
        batch_size: batch size for Ollama requests.
        reindex: rebuild embeddings even for already indexed entities.

    Returns:
        Number of indexed records.
    """
    async with async_session_factory() as session:
        stmt = select(Entity).options(selectinload(Entity.embedding_data))
        if entity_type is not None:
            stmt = stmt.where(Entity.entity_type == entity_type)
        if not reindex:
            stmt = (
                stmt.join(EntityEmbedding, EntityEmbedding.entity_id == Entity.id, isouter=True)
                .where(
                    or_(
                        EntityEmbedding.entity_id.is_(None),
                        EntityEmbedding.embedding.is_(None),
                    )
                )
            )

        result = await session.execute(stmt)
        entities = list(result.scalars().all())

    total = 0
    for i in range(0, len(entities), batch_size):
        batch = entities[i : i + batch_size]
        async with async_session_factory() as session:
            for entity in batch:
                txt = _entity_text(entity)
                try:
                    vec = await _embed(txt)
                except httpx.HTTPError as exc:
                    logger.warning("Ошибка эмбеддинга для %s: %s", entity.id, exc)
                    continue
                managed_entity = await session.get(Entity, entity.id)
                if managed_entity is None:
                    logger.warning("Сущность %s не найдена при сохранении эмбеддинга", entity.id)
                    continue
                if managed_entity.embedding_data is None:
                    managed_entity.embedding_data = EntityEmbedding(
                        embedding=vec,
                        entity_text=func.to_tsvector("russian", txt) if txt.strip() else None,
                    )
                else:
                    managed_entity.embedding_data.embedding = vec
                    if txt.strip():
                        managed_entity.embedding_data.entity_text = func.to_tsvector(
                            "russian",
                            txt,
                        )
                total += 1
            await session.commit()
        logger.info("Проиндексировано %d / %d", min(i + batch_size, len(entities)), len(entities))

    return total


# ---------------------------------------------------------------------------
# Similarity search + answer generation.
# ---------------------------------------------------------------------------


async def similarity_search(
    query: str,
    entity_type: str | None = None,
    top_k: int = 5,
) -> list[dict]:
    """Vector search for nearest entities by cosine distance.

    Requires the pgvector extension and stored embeddings.
    """
    vec = await _embed(query)
    # pgvector expects a literal like '[1.0,2.0,...]'.
    vec_str = "[" + ",".join(str(v) for v in vec) + "]"

    async with async_session_factory() as session:
        stmt = (
            select(
                Entity.id,
                Entity.name,
                Entity.description,
                Entity.entity_type,
                cast(
                    EntityEmbedding.embedding.op("<->")(text(f"'{vec_str}'::vector")),
                    String,
                ).label("distance"),
            )
            .join(EntityEmbedding, EntityEmbedding.entity_id == Entity.id)
            .where(EntityEmbedding.embedding.is_not(None))
            .order_by(text("distance"))
            .limit(top_k)
        )
        if entity_type is not None:
            stmt = stmt.where(Entity.entity_type == entity_type)

        result = await session.execute(
            stmt,
            execution_options={"compiled_cache": None},
        )
        rows = result.mappings().all()

    return [
        {
            "id": str(row["id"]),
            "name": row["name"],
            "description": row["description"] or "",
            "entity_type": row["entity_type"].value
            if hasattr(row["entity_type"], "value")
            else str(row["entity_type"]),
            "distance": round(float(row["distance"]), 4),
        }
        for row in rows
    ]


async def hybrid_search(
    query: str,
    entity_type: str | None = None,
    top_k: int = 5,
    alpha: float = 0.5,
) -> list[dict]:
    """Hybrid search: BM25 + vector search with merged ranking.

    Args:
        query: search text.
        entity_type: entity type filter.
        top_k: number of results.
        alpha: BM25 weight (0..1); vector weight = 1 - alpha. Default is 0.5.

    Returns:
        Results sorted by the combined score.
    """
    from .db import search_entities

    bm25_results = await search_entities(query, entity_type=entity_type, limit=top_k * 2)
    vector_results = await similarity_search(query, entity_type=entity_type, top_k=top_k * 2)
    logger.debug("Step 1")

    # Normalize BM25 ranks (0..1, where 1 is best based on list position).
    bm25_map: dict[str, float] = {}
    for i, doc in enumerate(bm25_results):
        # Reverse rank: the first result (i=0) gets 1.0, the last gets 0.0.
        bm25_map[doc["id"]] = 1.0 - (i / (len(bm25_results) + 1))

    logger.debug("Step 2")
    # Normalize vector scores by inverting distances.
    vector_map: dict[str, tuple[float, dict]] = {}
    if vector_results:
        max_distance = max(r.get("distance", 0) for r in vector_results)
        for doc in vector_results:
            # The smaller the distance, the higher the score.
            distance = doc.get("distance", max_distance)
            if max_distance > 0:
                score = 1.0 - (distance / max_distance)
            else:
                score = 1.0
            vector_map[doc["id"]] = (score, doc)

    logger.debug("Step 3")

    # Merge the results.
    combined: dict[str, dict] = {}
    for doc_id, bm25_score in bm25_map.items():
        vector_score, _vector_doc = vector_map.get(doc_id, (0.0, None))
        # Combined score.
        combined_score = (bm25_score * alpha) + (vector_score * (1 - alpha))
        # Use the BM25 result as the base document (could also use vector_doc).
        doc = bm25_results[[d["id"] for d in bm25_results].index(doc_id)]
        doc["hybrid_score"] = round(combined_score, 4)
        combined[doc_id] = doc

    logger.debug("Step 4")

    # Add vector results that are absent from BM25.
    # for doc_id, (vector_score, vector_doc) in vector_map.items():
    #     if doc_id not in combined:
    #         combined_score = vector_score * (1 - alpha)
    #         vector_doc["hybrid_score"] = round(combined_score, 4)
    #         combined[doc_id] = vector_doc

    logger.debug("Step 5")

    # Sort by score and return top_k.
    results = sorted(combined.values(), key=lambda x: x.get("hybrid_score", 0), reverse=True)
    return results[:top_k]


async def ask(
    question: str,
    entity_type: str | None = None,
    top_k: int = 5,
) -> dict:
    """RAG request: find relevant entities and generate an answer.

    Returns:
        {"answer": str, "sources": list[dict]}
    """
    sources = await hybrid_search(question, entity_type=entity_type, top_k=top_k)

    source_ids: list[uuid.UUID] = []
    for source in sources:
        raw_id = source.get("id")
        if not isinstance(raw_id, str):
            continue
        try:
            source_ids.append(uuid.UUID(raw_id))
        except ValueError:
            continue

    table_rows_by_id: dict[str, str] = {}
    if source_ids:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Entity.id, Entity.data, Entity.is_table).where(Entity.id.in_(source_ids))
            )
            for row in result.mappings().all():
                if not row["is_table"]:
                    continue
                table_rows_text = _extract_table_rows_text(row["data"])
                if table_rows_text:
                    table_rows_by_id[str(row["id"])] = table_rows_text

    context_docs: list[str] = []
    for source in sources:
        base = f"{source['name']}: {source['description']}" if source["description"] else source["name"]
        table_rows_text = table_rows_by_id.get(str(source.get("id")))
        if table_rows_text:
            base = f"{base}\nТаблица:\n{table_rows_text}"
        context_docs.append(base)

    answer = await _generate(question, context_docs)
    return {"answer": answer, "sources": sources}
