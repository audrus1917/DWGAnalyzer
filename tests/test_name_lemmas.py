from pathlib import Path

import pytest

from parsedwg import name_lemmas


class _FakeWordNetLemmatizer:
    def lemmatize(self, token: str) -> str:
        mapping = {
            "drawings": "drawing",
            "levels": "level",
        }
        return mapping.get(token, token)


class _FakeRussianStemmer:
    def __init__(self, _language: str) -> None:
        pass

    def stem(self, token: str) -> str:
        mapping = {
            "планы": "план",
            "кровли": "кровл",
        }
        return mapping.get(token, token)


def test_collect_name_lemmas_recurses_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(name_lemmas, "WordNetLemmatizer", _FakeWordNetLemmatizer)
    monkeypatch.setattr(name_lemmas, "SnowballStemmer", _FakeRussianStemmer)

    source = tmp_path / "tower_A"
    nested = source / "Кровли"
    nested.mkdir(parents=True)

    drawing = nested / "Планы_drawings_03.dwg"
    drawing.write_text("stub", encoding="utf-8")

    rows = name_lemmas.collect_name_lemmas(source)

    assert [row["relative_path"] for row in rows] == [
        "Кровли",
        "Кровли/Планы_drawings_03.dwg",
    ]

    file_row = rows[1]
    assert file_row["kind"] == "file"
    assert file_row["tokens"] == ["планы", "drawings", "03"]
    assert file_row["lemmas"] == ["план", "drawing", "03"]


def test_collect_name_lemmas_for_single_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(name_lemmas, "WordNetLemmatizer", _FakeWordNetLemmatizer)
    monkeypatch.setattr(name_lemmas, "SnowballStemmer", _FakeRussianStemmer)

    source = tmp_path / "levels_drawings.dwg"
    source.write_text("stub", encoding="utf-8")

    rows = name_lemmas.collect_name_lemmas(source)

    assert len(rows) == 1
    assert rows[0]["relative_path"] == "levels_drawings.dwg"
    assert rows[0]["lemmas"] == ["level", "drawing"]


def test_collect_name_lemmas_raises_for_missing_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        name_lemmas.collect_name_lemmas(tmp_path / "missing")
