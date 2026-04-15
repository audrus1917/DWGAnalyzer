"""
Пример лемматизации русских слов через pymorphy2.

Лемматизатор возвращает канонические словарные формы (leммы), а не обрезанные
стемы — «этажа» → «этаж», «вентиляции» → «вентиляция».

NLTK не содержит встроенного морфологического анализатора для русского языка,
поэтому используется pymorphy3 — поддерживаемый форк pymorphy2 для Python 3.10+.

Запуск:
    PYTHONPATH=src .venv/bin/python src/training/nltk/lemmatization_ru.py

Установка (если ещё не установлено):
    .venv/bin/pip install pymorphy3

При желании сравнить с NLTK SnowballStemmer — запустите stemming_ru.py.
"""
from __future__ import annotations

import argparse

try:
    import pymorphy3  # type: ignore[import-untyped]
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Установите pymorphy3: .venv/bin/pip install pymorphy3"
    ) from exc

MORPH = pymorphy3.MorphAnalyzer()

# Те же слова, что в stemming_ru.py — удобно сравнивать результаты.
WORDS: list[str] = [
    # Словоформы одного слова — лемматизатор должен давать одну лемму
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


def lemmatize(word: str) -> str:
    """Возвращает наиболее вероятную (первую) лемму слова."""
    parsed = MORPH.parse(word)
    if not parsed:
        return word
    return parsed[0].normal_form


def main() -> None:

    parser = argparse.ArgumentParser(
        description="Лемматизация русских слов через pymorphy3"
    )
    parser.add_argument(
        "text",
        type=str,
        help="Текст для лемматизации",
    )

    

    # col_w = max(len(w) for w in WORDS) + 2
    # tag_w = 40
    # print(f"{'Слово':<{col_w}} {'Лемма':<{col_w}} {'Грам. тег'}")
    # print("-" * (col_w * 2 + tag_w))
    # for word in WORDS:
    #     parsed = MORPH.parse(word)
    #     best = parsed[0] if parsed else None
    #     lemma = best.normal_form if best else word
    #     tag = str(best.tag) if best else "—"
    #     print(f"{word:<{col_w}} {lemma:<{col_w}} {tag}")


if __name__ == "__main__":
    main()
