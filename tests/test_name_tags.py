from parsedwg.name_tags import extract_file_name_tags, extract_floor_entities, extract_meaningful_tokens


def test_extract_floor_entities_supports_short_floor_form() -> None:
    entities = extract_floor_entities("ПЛАН_ЭО_6-9 эт.")

    assert entities == ["6-й этаж", "7-й этаж", "8-й этаж", "9-й этаж"]


def test_extract_file_name_tags_includes_roof_and_floors() -> None:
    tags = extract_file_name_tags("Кровля 4 и 5 этажа от-2026-03-24.dwg")

    assert tags["entities"] == ["Кровля", "4-й этаж", "5-й этаж"]


def test_extract_meaningful_tokens_filters_noise() -> None:
    tokens = extract_meaningful_tokens("3-0005 22-Р-АПС3 Экспликация- 16-25 этаж (типовой).dwg")

    assert "апс3" in tokens
    assert "экспликация" in tokens
    assert "этаж" not in tokens
