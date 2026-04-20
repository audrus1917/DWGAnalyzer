import json
from typing import cast

from parsedwg.name_tags import collect_name_tags


def test_collect_name_tags_extracts_floor_numbers_and_roof_forms(tmp_path) -> None:
    floor_file = tmp_path / "Этаж_2-4 и 7_кровля.dxf"
    floor_file.write_text("stub", encoding="utf-8")

    rows = collect_name_tags(floor_file)

    assert len(rows) == 1
    row = rows[0]
    tags = cast(list[str], row["tags"])
    assert "этаж" in tags
    assert "этаж:2" in tags
    assert "этаж:4" in tags
    assert "этаж:7" in tags
    assert "кровля" in tags


def test_collect_name_tags_supports_short_floor_form_with_punctuation(tmp_path) -> None:
    source = tmp_path / "план_эт.3_крыша.dxf"
    source.write_text("stub", encoding="utf-8")

    rows = collect_name_tags(source)
    row = rows[0]
    tags = cast(list[str], row["tags"])

    assert "этаж" in tags
    assert "этаж:3" in tags
    assert "кровля" in tags


def test_collect_name_tags_recurses_directory_and_adds_ai_tags(tmp_path) -> None:
    source_dir = tmp_path / "tower"
    source_dir.mkdir(parents=True)
    (source_dir / "Кровля_эт_10.dxf").write_text("stub", encoding="utf-8")

    class StubExtractor:
        def extract(self, text: str) -> list[str]:
            assert text == "Кровля_эт_10"
            return ["раздел", "раздел", "чертеж"]

    rows = collect_name_tags(source_dir, ai_extractor=StubExtractor())

    assert len(rows) == 1
    assert rows[0]["ai_tags"] == ["раздел", "чертеж"]
    ai_details = cast(list[dict[str, object]], rows[0]["ai_tag_details"])
    assert len(ai_details) == 2
    assert ai_details[0]["tag"] == "раздел"
    assert ai_details[0]["confidence"] is None
    assert ai_details[0]["source"] == "ai"
    assert "LLM" in str(ai_details[0]["reason"])


def test_collect_name_tags_json_serializable(tmp_path) -> None:
    source = tmp_path / "Крыша_этаж_1.dxf"
    source.write_text("stub", encoding="utf-8")

    rows = collect_name_tags(source)
    payload = json.dumps(rows, ensure_ascii=False)

    assert "Крыша_этаж_1.dxf" in payload


def test_collect_name_tags_includes_tag_details_with_reasons_and_confidence(tmp_path) -> None:
    source = tmp_path / "Этаж_3_кровля.dxf"
    source.write_text("stub", encoding="utf-8")

    rows = collect_name_tags(source)
    details = cast(list[dict[str, object]], rows[0]["tag_details"])

    by_tag = {str(item["tag"]): item for item in details}
    assert set(by_tag) == {"кровля", "этаж", "этаж:3"}
    assert by_tag["кровля"]["confidence"] == 0.99
    assert by_tag["этаж"]["confidence"] == 0.97
    assert by_tag["этаж:3"]["confidence"] == 0.95
    assert "словоформы" in str(by_tag["кровля"]["reason"])
