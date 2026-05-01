from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

WordNetLemmatizer = None
SnowballStemmer = None

try:
    from nltk.stem import SnowballStemmer as _SnowballStemmer
    from nltk.stem import WordNetLemmatizer as _WordNetLemmatizer

    WordNetLemmatizer = _WordNetLemmatizer
    SnowballStemmer = _SnowballStemmer
except ImportError:
    pass

_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+")


def _iter_entries(source_path: Path) -> list[Path]:
    if not source_path.exists():
        raise FileNotFoundError(f"Путь {source_path} не найден.")

    if source_path.is_file():
        return [source_path]

    return sorted(source_path.rglob("*"))


def _tokenize_name(path: Path) -> list[str]:
    text = path.stem if path.is_file() else path.name
    return [token.lower() for token in _TOKEN_RE.findall(text)]


def _lemmatize_token(token: str, wordnet: object | None, russian_stemmer: object | None) -> str:
    if token.isdigit() or not token:
        return token

    if re.search(r"[а-яё]", token):
        if russian_stemmer is None:
            return token
        # NLTK does not provide a full Russian lemmatizer without external dictionaries,
        # so for Cyrillic text we fall back to the closest Snowball normalization.
        return russian_stemmer.stem(token)

    if wordnet is None:
        return token

    try:
        lemma = wordnet.lemmatize(token)
        return lemma if lemma else token
    except LookupError:
        # If the WordNet corpus is missing, keep the token unchanged.
        return token


def _build_name_record(
    path: Path,
    root: Path,
    wordnet: object | None,
    russian_stemmer: object | None,
) -> dict[str, object]:
    tokens = _tokenize_name(path)

    lemmas = [_lemmatize_token(token, wordnet, russian_stemmer) for token in tokens]

    return {
        "path": str(path),
        "relative_path": str(path.relative_to(root)) if root.is_dir() else path.name,
        "kind": "file" if path.is_file() else "dir",
        "name": path.name,
        "tokens": tokens,
        "lemmas": lemmas,
    }


def collect_name_lemmas(source_path: Path) -> list[dict[str, object]]:
    source = source_path.resolve()
    entries = _iter_entries(source)
    wordnet = WordNetLemmatizer() if WordNetLemmatizer is not None else None
    russian_stemmer = SnowballStemmer("russian") if SnowballStemmer is not None else None

    if source.is_file():
        return [_build_name_record(source, source, wordnet, russian_stemmer)]

    rows: list[dict[str, object]] = []
    for entry in entries:
        rows.append(_build_name_record(entry, source, wordnet, russian_stemmer))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="parsedwg-name-lemmas",
        description="Рекурсивный обход каталога и лемматизация имен файлов/папок через NLTK.",
    )
    parser.add_argument("path", help="Путь к каталогу или файлу")
    parser.add_argument("-o", "--output", help="Путь к JSON-файлу для сохранения результата")
    args = parser.parse_args(argv)

    rows = collect_name_lemmas(Path(args.path))

    payload = json.dumps(rows, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding="utf-8")
    else:
        print(payload)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
