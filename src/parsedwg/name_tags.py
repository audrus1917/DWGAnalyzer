from __future__ import annotations

import re
from pathlib import Path

TOKEN_SPLIT_RE = re.compile(r"[\s_\-.,()]+")
FLOOR_WORD_RE = r"(?:этаж(?:а|ей)?|эт\.?)"

TOKEN_STOP_WORDS = {
    "и",
    "в",
    "на",
    "по",
    "для",
    "от",
    "изм",
    "лист",
    "план",
    "схема",
    "схемы",
    "данные",
    "общие",
    "башня",
    "башни",
    "типовой",
    "тип",
    "sheet",
    "dwg",
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "xlsm",
    "zip",
    "bak",
    "dwl",
    "dwl2",
    "tmp",
    "архив",
    "титул",
    "титульный",
    "приложение",
    "приложения",
    "обложка",
    "ред",
    "файлы",
    "с",
    "со",
    "кж",
    "од",
    "гч",
    "этаж",
    "этажа",
    "этажей",
}


def _normalize_token(token: str) -> str:
    normalized = token.strip().lower().replace("ё", "е")
    return re.sub(r"^[^\wа-я]+|[^\wа-я]+$", "", normalized)


def extract_meaningful_tokens(file_name: str) -> list[str]:
    tokens: set[str] = set()
    for part in TOKEN_SPLIT_RE.split(file_name):
        token = _normalize_token(part)
        if not token or token in TOKEN_STOP_WORDS:
            continue
        if len(token) <= 2:
            continue
        if re.fullmatch(r"\d+", token):
            continue
        if re.fullmatch(r"\d{4,}", token):
            continue
        if re.fullmatch(r"v\d+", token):
            continue
        tokens.add(token)
    return sorted(tokens)


def extract_floor_entities(file_name: str) -> list[str]:
    text = file_name.lower().replace("ё", "е")
    floors: set[int] = set()

    for match in re.finditer(
        rf"(?<!\d)(\d{{1,2}})\s*[-–]\s*(\d{{1,2}})\s*{FLOOR_WORD_RE}(?!\w)",
        text,
    ):
        start = int(match.group(1))
        end = int(match.group(2))
        for floor in range(min(start, end), max(start, end) + 1):
            floors.add(floor)

    for match in re.finditer(
        rf"(?<!\d)(\d{{1,2}})\s*[-–]\s*(\d{{1,2}})\s*,\s*(\d{{1,2}})\s*{FLOOR_WORD_RE}(?!\w)",
        text,
    ):
        start = int(match.group(1))
        end = int(match.group(2))
        tail = int(match.group(3))
        for floor in range(min(start, end), max(start, end) + 1):
            floors.add(floor)
        floors.add(tail)

    for match in re.finditer(
        rf"(?<!\d)(\d{{1,2}})\s*и\s*(\d{{1,2}})\s*{FLOOR_WORD_RE}(?!\w)",
        text,
    ):
        floors.add(int(match.group(1)))
        floors.add(int(match.group(2)))

    for match in re.finditer(rf"(?<!\d)(\d{{1,2}})\s*{FLOOR_WORD_RE}(?!\w)", text):
        floors.add(int(match.group(1)))

    return [f"{floor}-й этаж" for floor in sorted(floors)]


def has_roof_entity(file_name: str) -> bool:
    text = file_name.lower().replace("ё", "е")
    return re.search(r"\bкровл[яеи]?\b|\bкрыш[аеи]?\b", text) is not None


def extract_file_name_tags(path: Path | str) -> dict[str, object]:
    file_path = Path(path)
    file_name = file_path.stem
    floor_entities = extract_floor_entities(file_name)
    roof = has_roof_entity(file_name)

    entities: list[str] = []
    if roof:
        entities.append("Кровля")
    entities.extend(floor_entities)

    return {
        "file": str(file_path),
        "entities": entities,
        "tokens": extract_meaningful_tokens(file_name),
    }


def collect_name_tags(source_path: Path) -> list[dict[str, object]]:
    if not source_path.exists():
        raise FileNotFoundError(f"Путь {source_path} не найден.")

    if source_path.is_file():
        return [extract_file_name_tags(source_path)]

    files = sorted(path for path in source_path.rglob("*") if path.is_file())
    return [extract_file_name_tags(path) for path in files]
