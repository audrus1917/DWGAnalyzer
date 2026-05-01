"""
Example of Russian stemming with NLTK SnowballStemmer.

The stemmer removes endings by heuristic rules, so the result may not be a
true dictionary form, but it is usually sufficient for fuzzy search and clustering.

Run:
    PYTHONPATH=src .venv/bin/python src/training/nltk/stemming_ru.py

Dependencies (already listed in pyproject.toml):
    nltk>=3.9
"""
from __future__ import annotations

from nltk.stem import SnowballStemmer

STEMMER = SnowballStemmer("russian")

# Domain examples: project section names and floor-related terms.
WORDS: list[str] = [
    # Inflected forms of the same word should map to one stem.
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


def main() -> None:
    col_w = max(len(w) for w in WORDS) + 2
    print(f"{'Слово':<{col_w}} {'Основа (стем)'}")
    print("-" * (col_w + 20))
    for word in WORDS:
        stem = STEMMER.stem(word)
        print(f"{word:<{col_w}} {stem}")


if __name__ == "__main__":
    main()
