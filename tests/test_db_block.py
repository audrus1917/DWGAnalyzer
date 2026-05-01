"""Tests for db.get_full_description."""
import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from parsedwg.db import get_block_full_description, get_full_description


def _make_block(
    block_name: str,
    block_id: uuid.UUID | None = None,
    file_id: uuid.UUID | None = None,
) -> SimpleNamespace:
    bid = block_id or uuid.uuid4()
    return SimpleNamespace(
        id=bid,
        name=block_name,
        description=f"Block {block_name}",
        short_interpretation="Насос подачи воды",
        full_interpretation=None,
        file_id=file_id,
        entity_type="BLOCK",
    )


def _make_session_side_effect(
    block,
    layer_rows,
    attrib_data_rows,
    insert_rows,
    multileader_rows=None,
    source_ref_row=None,
):
    """Return session.execute() side effects in call order."""
    # Call 1: SELECT block.
    r0 = MagicMock()
    r0.scalar_one_or_none.return_value = block

    # Call 2: SELECT layers (iterable).
    r1 = MagicMock()
    r1.__iter__ = lambda s: iter(layer_rows)

    # Call 3: SELECT attribs (iterable of tuples).
    r2 = MagicMock()
    r2.__iter__ = lambda s: iter(attrib_data_rows)

    # Call 4: SELECT inserts (iterable).
    r3 = MagicMock()
    r3.__iter__ = lambda s: iter(insert_rows)

    # Call 5: SELECT child MULTILEADER rows.
    r4 = MagicMock()
    r4.__iter__ = lambda s: iter(multileader_rows or [])

    side_effect = [r0, r1, r2, r3, r4]

    if source_ref_row is not None:
        r5 = MagicMock()
        r5.first.return_value = source_ref_row
        side_effect.append(r5)

    return side_effect


def _make_fake_session_factory(
    block,
    layer_rows,
    attrib_data_rows,
    insert_rows,
    multileader_rows=None,
    source_ref_row=None,
):
    side_effect = _make_session_side_effect(
        block,
        layer_rows,
        attrib_data_rows,
        insert_rows,
        multileader_rows=multileader_rows,
        source_ref_row=source_ref_row,
    )
    session = AsyncMock()
    session.execute.side_effect = side_effect

    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock(return_value=context)
    return factory


def test_get_block_full_description_returns_none_when_not_found(monkeypatch) -> None:
    r0 = MagicMock()
    r0.scalar_one_or_none.return_value = None

    session = AsyncMock()
    session.execute.return_value = r0

    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr("parsedwg.db.async_session_factory", MagicMock(return_value=context))

    result = asyncio.run(get_full_description("НESУЩЕСТВУЮЩИЙ"))

    assert result is None


def test_get_block_full_description_returns_structure(monkeypatch) -> None:
    block_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    block = _make_block("НС-01", block_id)

    layer_rows = [
        SimpleNamespace(name="0-ВК-ТРУБЫ", short_interpretation="Трубопроводы ВК"),
        SimpleNamespace(name="0-ВК-ОБОРУДОВАНИЕ", short_interpretation=None),
    ]
    # attribs: one INSERT with two attributes.
    attrib_data_rows = [
        ({"block": "НС-01", "attribs": {"ДИАМЕТР": "DN50", "НАПОР": "20м"}},),
    ]
    insert_parent_id = uuid.uuid4()
    insert_rows = [
        SimpleNamespace(
            id=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            parent_id=insert_parent_id,
            file_id=None,
            data={"block": "КОРПУС", "layer": "0-ВК-ОБОРУДОВАНИЕ"},
        ),
    ]

    factory = _make_fake_session_factory(block, layer_rows, attrib_data_rows, insert_rows)
    monkeypatch.setattr("parsedwg.db.async_session_factory", factory)

    result = asyncio.run(get_full_description("НС-01"))

    assert result is not None
    assert result["id"] == str(block_id)
    assert result["name"] == "НС-01"
    assert result["short_interpretation"] == "Насос подачи воды"

    layers = result["layers"]
    assert len(layers) == 2
    assert layers[0]["name"] == "0-ВК-ТРУБЫ"
    assert layers[0]["short_interpretation"] == "Трубопроводы ВК"
    assert layers[1]["name"] == "0-ВК-ОБОРУДОВАНИЕ"
    assert layers[1]["short_interpretation"] is None

    assert result["attributes"] == {"ДИАМЕТР": "DN50", "НАПОР": "20м"}
    assert result["annotation_texts"] == []

    inserts = result["inserts"]
    assert len(inserts) == 1
    assert inserts[0]["id"] == "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    assert inserts[0]["parent_id"] == str(insert_parent_id)
    assert inserts[0]["file_id"] is None


def test_get_block_full_description_merges_attribs_from_multiple_inserts(monkeypatch) -> None:
    block = _make_block("КЛ-03")
    layer_rows: list = []
    attrib_data_rows = [
        ({"attribs": {"TAG_A": "val1"}},),
        ({"attribs": {"TAG_B": "val2"}},),
        ({"нет": "attribs"},),          # No attribs field, should be skipped.
    ]
    insert_rows: list = []

    factory = _make_fake_session_factory(block, layer_rows, attrib_data_rows, insert_rows)
    monkeypatch.setattr("parsedwg.db.async_session_factory", factory)

    result = asyncio.run(get_full_description("КЛ-03"))

    assert result is not None
    assert result["attributes"] == {"TAG_A": "val1", "TAG_B": "val2"}
    assert result["layers"] == []
    assert result["inserts"] == []


def test_get_block_full_description_empty_inserts_and_layers(monkeypatch) -> None:
    block = _make_block("ПУСТОЙ")

    factory = _make_fake_session_factory(block, [], [], [])
    monkeypatch.setattr("parsedwg.db.async_session_factory", factory)

    result = asyncio.run(get_full_description("ПУСТОЙ"))

    assert result is not None
    assert result["layers"] == []
    assert result["attributes"] == {}
    assert result["inserts"] == []
    assert result["annotation_texts"] == []


def test_get_block_full_description_collects_annotation_texts_from_child_multileaders(monkeypatch) -> None:
    block = _make_block("МЛ-01")
    multileader_rows = [
        ("Помещение 101", {}),
        ("", {"annotation_text": "Ог.1"}),
        ("", {"text": "Ог.1"}),
    ]

    factory = _make_fake_session_factory(
        block,
        [],
        [],
        [],
        multileader_rows=multileader_rows,
    )
    monkeypatch.setattr("parsedwg.db.async_session_factory", factory)

    result = asyncio.run(get_full_description("МЛ-01"))

    assert result is not None
    assert result["annotation_texts"] == ["Помещение 101", "Ог.1"]


def test_get_block_full_description_collects_annotation_texts_from_source_when_db_empty(monkeypatch) -> None:
    file_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    block = _make_block("МЛ-02", file_id=file_id)

    factory = _make_fake_session_factory(
        block,
        [],
        [],
        [],
        multileader_rows=[],
        source_ref_row=("/tmp/source.dxf",),
    )
    monkeypatch.setattr("parsedwg.db.async_session_factory", factory)
    monkeypatch.setattr(
        "parsedwg.db._collect_block_annotation_texts_from_source",
        lambda block_name, source_ref: [f"{block_name}@{source_ref}"],
    )

    result = asyncio.run(get_full_description("МЛ-02"))

    assert result is not None
    assert result["annotation_texts"] == ["МЛ-02@/tmp/source.dxf"]


def test_get_block_full_description_builds_readable_text() -> None:
    description = get_block_full_description(
        {
            "name": "НС-01",
            "description": "Насосная станция",
            "layers": [
                {"name": "0-ВК-ТРУБЫ", "short_interpretation": "Трубопроводы"},
                {"name": "0-ВК-ОБОР", "short_interpretation": None},
            ],
            "attributes": {"A": "1", "B": "2"},
            "annotation_texts": ["Помещение 101", "Ог.1"],
            "insert_count": 3,
            "inserts": [
                {
                    "data": {
                        "block": "НС-01",
                        "layer": "0-ВК-ОБОР",
                        "attribs": {"TAG": "VALUE"},
                    }
                }
            ],
        }
    )

    assert "Имя блока: НС-01" in description
    assert "Описание: Насосная станция" in description
    assert "Связанные слои: 0-ВК-ТРУБЫ (Трубопроводы); 0-ВК-ОБОР" in description
    assert "Атрибуты: A=1; B=2" in description
    assert "Количество вставок: 3" in description
    assert "Тексты аннотаций: Помещение 101; Ог.1" in description
    assert "Примеры вставок: {block=НС-01; layer=0-ВК-ОБОР; attribs=TAG=VALUE}" in description
