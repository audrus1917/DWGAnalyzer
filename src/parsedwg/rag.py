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


async def ask(
    question: str,
    entity_type: str | None = None,
    top_k: int = 5,
) -> dict:
    """RAG-запрос: найти релевантные сущности и сгенерировать ответ.

    Returns:
        {"answer": str, "sources": list[dict]}
    """
    sources = await similarity_search(question, entity_type=entity_type, top_k=top_k)
    context_docs = [
        f"{s['name']}: {s['description']}" if s["description"] else s["name"]
        for s in sources
    ]
    answer = await _generate(question, context_docs)
    return {"answer": answer, "sources": sources}
