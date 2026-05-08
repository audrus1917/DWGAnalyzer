"""Извлекает семантические теги из имён файлов и каталогов."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
import json
import re
from typing import Protocol


_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+")
_ROOF_RE = re.compile(r"кровл(?:я|е|и)|крыш(?:а|е|и)", re.IGNORECASE)
_FLOOR_CONTEXT_RE = re.compile(
    r"(?:этаж(?:а|ей)?|эт\.?)(?:\s*[:._-]?\s*(?P<nums>[0-9]+(?:\s*(?:-|–|,|и)\s*[0-9]+)*))?",
    re.IGNORECASE,
)


class _TagsExtractorLike(Protocol):
    def extract(self, text: str) -> list[str]: ...


type _TagMeta = tuple[float, str]


def _iter_entries(source_path: Path) -> list[Path]:
    if not source_path.exists():
        raise FileNotFoundError(f"Путь {source_path} не найден.")

    if source_path.is_file():
        return [source_path]

    return sorted(source_path.rglob("*"))


def _tokenize_name(path: Path) -> list[str]:
    text = path.stem if path.is_file() else path.name
    return [token.lower() for token in _TOKEN_RE.findall(text)]


def _parse_numbers(raw_numbers: str) -> list[int]:
    chunks = re.split(r"\s*(?:-|–|,|и)\s*", raw_numbers)
    numbers: list[int] = []
    for chunk in chunks:
        if chunk.isdigit():
            numbers.append(int(chunk))
    return numbers


def _extract_rule_tags(name_text: str) -> tuple[list[dict[str, str]], list[str], list[dict[str, object]]]:
    text = name_text.lower()
    entities: list[dict[str, str]] = []
    tags_meta: dict[str, _TagMeta] = {}

    def _add_tag(tag: str, confidence: float, reason: str) -> None:
        current = tags_meta.get(tag)
        if current is None or confidence > current[0]:
            tags_meta[tag] = (confidence, reason)

    if _ROOF_RE.search(text):
        entities.append({"type": "Кровля"})
        _add_tag("кровля", 0.99, "Совпадение словоформы кровля/крыша.")

    floor_numbers: list[int] = []
    for match in _FLOOR_CONTEXT_RE.finditer(text):
        entities.append({"type": "Этаж"})
        _add_tag("этаж", 0.97, "Обнаружен контекст этаж/эт.")
        raw_numbers = match.group("nums")
        if raw_numbers:
            floor_numbers.extend(_parse_numbers(raw_numbers))

    unique_floor_numbers = sorted(set(floor_numbers))
    for number in unique_floor_numbers:
        _add_tag(
            f"этаж:{number}",
            0.95,
            "Номер этажа извлечен из контекста этаж/эт и списка чисел.",
        )
        entities.append({"type": "Этаж", "value": str(number)})

    tags = sorted(tags_meta.keys())
    tag_details = [
        {
            "tag": tag,
            "confidence": tags_meta[tag][0],
            "reason": tags_meta[tag][1],
        }
        for tag in tags
    ]
    return entities, tags, tag_details


def _build_record(
    path: Path,
    root: Path,
    ai_extractor: _TagsExtractorLike | None = None,
) -> dict[str, object]:
    name = path.name
    base_text = path.stem if path.is_file() else path.name
    entities, rule_tags, tag_details = _extract_rule_tags(base_text)
    tokens = _tokenize_name(path)

    result: dict[str, object] = {
        "path": str(path),
        "relative_path": str(path.relative_to(root)) if root.is_dir() else path.name,
        "kind": "file" if path.is_file() else "dir",
        "name": name,
        "tokens": tokens,
        "entities": entities,
        "tags": rule_tags,
        "tag_details": tag_details,
    }

    if ai_extractor is not None:
        extracted = ai_extractor.extract(base_text)
        ai_tags = sorted({item.strip() for item in extracted if isinstance(item, str) and item.strip()})
        if ai_tags:
            result["ai_tags"] = ai_tags
            result["ai_tag_details"] = [
                {
                    "tag": tag,
                    "confidence": None,
                    "reason": "Тег извлечен LLM (LangChain).",
                    "source": "ai",
                }
                for tag in ai_tags
            ]

    return result


def collect_name_tags(
    source_path: Path,
    ai_extractor: _TagsExtractorLike | None = None,
) -> list[dict[str, object]]:
    source = source_path.resolve()
    entries = _iter_entries(source)

    if source.is_file():
        return [_build_record(source, source, ai_extractor=ai_extractor)]

    rows: list[dict[str, object]] = []
    for entry in entries:
        rows.append(_build_record(entry, source, ai_extractor=ai_extractor))
    return rows


def save_name_tags_json(output_path: Path, rows: Iterable[dict[str, object]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [dict(item) for item in rows]
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
