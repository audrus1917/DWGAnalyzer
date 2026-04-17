"""Тесты для гибридного поиска (BM25 + vector)."""

import asyncio
import uuid

import pytest


def test_hybrid_search_function_exists() -> None:
    """Проверить, что функция гибридного поиска существует."""
    from parsedwg.rag import hybrid_search

    assert callable(hybrid_search)
    assert hybrid_search.__doc__ is not None
    assert "BM25" in hybrid_search.__doc__


def test_hybrid_search_alpha_parameter_doc() -> None:
    """Проверить, что параметр alpha задокументирован.

    alpha=0.5 → 50% BM25 + 50% вектор
    """
    from parsedwg.rag import hybrid_search

    doc = hybrid_search.__doc__
    assert doc is not None
    assert "alpha" in doc
    assert "0.5" in doc


def test_ask_includes_table_rows_in_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """Проверить, что ask добавляет в контекст строки таблицы для block-таблиц."""
    from parsedwg.rag import ask

    source_id = "11111111-1111-1111-1111-111111111111"

    async def fake_hybrid_search(query, entity_type=None, top_k=5):
        return [
            {
                "id": source_id,
                "name": "TABLE_BLOCK",
                "description": "Таблица спецификации",
                "entity_type": "block",
                "start_from": "sample.dxf",
            }
        ]

    captured_context: list[list[str]] = []

    async def fake_generate(prompt: str, context_docs: list[str]) -> str:
        captured_context.append(context_docs)
        return "ok"

    class _FakeMappings:
        def all(self):
            return [
                {
                    "id": uuid.UUID(source_id),
                    "data": {"table": {"rows": [["Код", "Наименование"], ["1", "Насос"]]}},
                    "is_table": True,
                }
            ]

    class _FakeExecuteResult:
        def mappings(self):
            return _FakeMappings()

    class _FakeSession:
        async def execute(self, _stmt):
            return _FakeExecuteResult()

    class _FakeSessionContext:
        async def __aenter__(self):
            return _FakeSession()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    def fake_async_session_factory():
        return _FakeSessionContext()

    monkeypatch.setattr("parsedwg.rag.hybrid_search", fake_hybrid_search)
    monkeypatch.setattr("parsedwg.rag._generate", fake_generate)
    monkeypatch.setattr("parsedwg.rag.async_session_factory", fake_async_session_factory)

    result = asyncio.run(ask("Что в таблице?"))

    assert result["answer"] == "ok"
    assert captured_context
    context_text = captured_context[0][0]
    assert "Таблица:" in context_text
    assert "Код | Наименование" in context_text
    assert "1 | Насос" in context_text
