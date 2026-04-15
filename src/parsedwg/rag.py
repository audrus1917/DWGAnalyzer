"""RAG-утилиты: эмбеддинги через nomic-embed-text и генерация ответов через llama3.2.

Ollama должен быть запущен локально: http://localhost:11434
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from sqlalchemy import select, text

from .db import async_session_factory
from .orm import Entity
from .settings import settings

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = settings.ollama_base_url
EMBED_MODEL = settings.ollama_embed_model
LLM_MODEL = settings.ollama_llm_model
EMBED_DIM = 768
# Таймаут для запросов к Ollama (генерация может быть долгой)
_TIMEOUT = httpx.Timeout(settings.ollama_timeout_seconds)


# ---------------------------------------------------------------------------
# Низкоуровневые клиенты Ollama
# ---------------------------------------------------------------------------


async def _embed(text_input: str) -> list[float]:
    """Получить эмбеддинг строки через Ollama /api/embed."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json={"model": EMBED_MODEL, "input": text_input},
        )
        response.raise_for_status()
    data: dict[str, Any] = response.json()
    # Ollama /api/embed возвращает {"embeddings": [[...]], ...}
    raw = data.get("embeddings") or data.get("embedding")
    if not raw:
        raise ValueError(f"Ollama не вернул эмбеддинг: {data}")
    first = raw[0]
    if isinstance(first, list):
        return first  # type: ignore[return-value]
    return raw  # type: ignore[return-value]


async def _generate(prompt: str, context_docs: list[str]) -> str:
    """Задать вопрос LLM с контекстом из найденных документов."""
    context = "\n\n".join(
        f"[{i + 1}] {doc}" for i, doc in enumerate(context_docs)
    )
    system = (
        "Ты — ассистент по технической документации и чертежам. "
        "Отвечай на основе предоставленного контекста. "
        "Если ответа в контексте нет, скажи об этом явно."
    )
    full_prompt = (
        f"Контекст:\n{context}\n\n"
        f"Вопрос: {prompt}\n\n"
        "Ответ:"
    )
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": LLM_MODEL, "prompt": full_prompt, "system": system, "stream": False},
        )
        response.raise_for_status()
    data = response.json()
    return data.get("response", "").strip()


# ---------------------------------------------------------------------------
# Индексация
# ---------------------------------------------------------------------------


def _entity_text(entity: Entity) -> str:
    """Формирует текст для эмбеддинга из полей сущности."""
    parts = [entity.name]
    if entity.description:
        parts.append(entity.description)
    if entity.start_from:
        parts.append(entity.start_from)
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
    """Генерирует эмбеддинги для сущностей в БД и сохраняет их.

    Args:
        entity_type: если задан — индексировать только этот тип.
        batch_size: размер батча для запросов к Ollama.
        reindex: пересоздать эмбеддинги даже для уже проиндексированных.

    Returns:
        Количество проиндексированных записей.
    """
    async with async_session_factory() as session:
        stmt = select(Entity)
        if entity_type is not None:
            stmt = stmt.where(Entity.entity_type == entity_type)
        if not reindex:
            stmt = stmt.where(Entity.embedding.is_(None))

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
                await session.merge(entity)
                entity.embedding = vec
                total += 1
            await session.commit()
        logger.info("Проиндексировано %d / %d", min(i + batch_size, len(entities)), len(entities))

    return total


# ---------------------------------------------------------------------------
# Поиск по сходству + генерация ответа
# ---------------------------------------------------------------------------


async def similarity_search(
    query: str,
    entity_type: str | None = None,
    top_k: int = 5,
) -> list[dict]:
    """Векторный поиск ближайших сущностей по косинусному расстоянию.

    Требует расширения pgvector и заполненных эмбеддингов.
    """
    vec = await _embed(query)
    # pgvector принимает литерал вида '[1.0,2.0,...]'
    vec_str = "[" + ",".join(str(v) for v in vec) + "]"

    async with async_session_factory() as session:
        stmt = (
            select(
                Entity.id,
                Entity.name,
                Entity.description,
                Entity.entity_type,
                Entity.start_from,
                (Entity.embedding.op("<->")(text(f"'{vec_str}'::vector"))).label("distance"),
            )
            .where(Entity.embedding.is_not(None))
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
            "start_from": row["start_from"] or "",
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
    """Гибридный поиск: BM25 + векторный с объединением результатов.

    Args:
        query: текст запроса.
        entity_type: фильтр по типу сущности.
        top_k: количество результатов.
        alpha: вес BM25 (0..1); вес вектора = 1 - alpha. По умолчанию 0.5 (50/50).

    Returns:
        Список результатов, отсортированный по комбинированному рейтингу.
    """
    from .db import search_entities

    # Запросить оба поиска параллельно
    bm25_results = await search_entities(query, entity_type=entity_type, limit=top_k * 2)
    vector_results = await similarity_search(query, entity_type=entity_type, top_k=top_k * 2)

    # Нормализовать BM25 ранги (0..1, где 1 лучше: индекс в списке)
    bm25_map: dict[str, float] = {}
    for i, doc in enumerate(bm25_results):
        # Обратный ранг: первый (i=0) получает 1.0, последний 0.0
        bm25_map[doc["id"]] = 1.0 - (i / (len(bm25_results) + 1))

    # Нормализовать вектор скоры (инвертировать расстояния)
    vector_map: dict[str, tuple[float, dict]] = {}
    if vector_results:
        max_distance = max(r.get("distance", 0) for r in vector_results)
        for doc in vector_results:
            # Чем меньше расстояние, тем выше скор
            distance = doc.get("distance", max_distance)
            if max_distance > 0:
                score = 1.0 - (distance / max_distance)
            else:
                score = 1.0
            vector_map[doc["id"]] = (score, doc)

    # Объединить результаты
    combined: dict[str, dict] = {}
    for doc_id, bm25_score in bm25_map.items():
        vector_score, vector_doc = vector_map.get(doc_id, (0.0, None))
        # Комбинированный скор
        combined_score = (bm25_score * alpha) + (vector_score * (1 - alpha))
        # Используем BM25 результат как основу (может быть и vector_doc)
        doc = bm25_results[[d["id"] for d in bm25_results].index(doc_id)]
        doc["hybrid_score"] = round(combined_score, 4)
        combined[doc_id] = doc

    # Добавить векторные результаты, которых нет в BM25
    for doc_id, (vector_score, vector_doc) in vector_map.items():
        if doc_id not in combined:
            combined_score = vector_score * (1 - alpha)
            vector_doc["hybrid_score"] = round(combined_score, 4)
            combined[doc_id] = vector_doc

    # Отсортировать по скору и вернуть top_k
    results = sorted(combined.values(), key=lambda x: x.get("hybrid_score", 0), reverse=True)
    return results[:top_k]


async def ask(
    question: str,
    entity_type: str | None = None,
    top_k: int = 5,
) -> dict:
    """RAG-запрос: найти релевантные сущности и сгенерировать ответ.

    Returns:
        {"answer": str, "sources": list[dict]}
    """
    sources = await hybrid_search(question, entity_type=entity_type, top_k=top_k)
    context_docs = [
        f"{s['name']}: {s['description']}" if s["description"] else s["name"]
        for s in sources
    ]
    answer = await _generate(question, context_docs)
    return {"answer": answer, "sources": sources}
