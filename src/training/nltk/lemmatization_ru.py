"""
Example of Russian word lemmatization with pymorphy3.

The lemmatizer returns canonical dictionary forms (lemmas), not truncated
stems, for example: "этажа" -> "этаж", "вентиляции" -> "вентиляция".

NLTK does not include a built-in morphological analyzer for Russian, so this
script uses pymorphy3, the maintained fork of pymorphy2 for Python 3.10+.

Run:
    PYTHONPATH=src .venv/bin/python src/training/nltk/lemmatization_ru.py

Install first, if needed:
    .venv/bin/pip install pymorphy3

To compare the result with NLTK SnowballStemmer, run stemming_ru.py.
"""
from __future__ import annotations

import argsparse

try:
    import pymorphy3  # type: ignore[import-untyped]
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Установите pymorphy3: .venv/bin/pip install pymorphy3"
    ) from exc

MORPH = pymorphy3.MorphAnalyzer()

# The same words as in stemming_ru.py, which makes result comparison easier.
WORDS: list[str] = [
    # Different inflected forms of the same word should map to one lemma.
    "этаж",
    "этажа",
    "этажей",
    "этажном",
    # Construction-related terms.
    "вентиляция",
    "вентиляции",
    "вентиляционный",
    "кондиционирование",
    "кондиционирования",
    "водоснабжение",
    "водоснабжения",
    "пожаротушение",
    "пожаротушения",
    "автоматизация",
    "автоматизированный",
    # Miscellaneous examples.
    "кровля",
    "кровле",
    "кровли",
    "крыша",
    "крыше",
    "крыши",
]


def lemmatize(word: str) -> str:
    """Return the most likely (first) lemma for a word."""
    parsed = MORPH.parse(word)
    if not parsed:
        return word
    return parsed[0].normal_form


def main() -> None:

    args_parser = argsparse.ArgumentParser(
        description="Лемматизация русских слов через pymorphy3"
    )
    args_parser.add_argument(
        "text",
        
        nargs="*",
        default=WORDS,
        help="Слова для лемматизации (по умолчанию — примеры из кода)",
    )

    col_w = max(len(w) for w in WORDS) + 2
    tag_w = 40
    print(f"{'Слово':<{col_w}} {'Лемма':<{col_w}} {'Грам. тег'}")
    print("-" * (col_w * 2 + tag_w))
    for word in WORDS:
        parsed = MORPH.parse(word)
        best = parsed[0] if parsed else None
        lemma = best.normal_form if best else word
        tag = str(best.tag) if best else "—"
        print(f"{word:<{col_w}} {lemma:<{col_w}} {tag}")


if __name__ == "__main__":
    main()
