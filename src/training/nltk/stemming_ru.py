"""
Пример стемминга русских слов через NLTK SnowballStemmer.

Стеммер отсекает окончания по правилам — результат может не быть настоящей
словарной формой, но достаточен для fuzzy-поиска и кластеризации.

Запуск:
    PYTHONPATH=src .venv/bin/python src/training/nltk/stemming_ru.py

Зависимости (уже в pyproject.toml):
    nltk>=3.9
"""
from __future__ import annotations

from nltk.stem import SnowballStemmer

STEMMER = SnowballStemmer("russian")

# Примеры из предметной области: наименования разделов проекта и этажей.
WORDS: list[str] = [
    # Словоформы одного слова — стеммер должен давать одну основу
    "этаж",
    "этажа",
    "этажей",
    "этажном",
    # Строительные термины
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
    # Прочие
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
