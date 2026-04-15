"""Тесты для гибридного поиска (BM25 + vector)."""


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
