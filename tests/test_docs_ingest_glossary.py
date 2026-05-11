from parsedwg.docs_ingest import _extract_glossary_terms_from_pages


def test_extract_glossary_terms_from_pages_splits_articles() -> None:
    pages = [
        (
            5,
            """
            ГОСТ Р 58033—2017
            3.1.1 объект (капитального) строительства (construction works): Здание,
            строение, сооружение.
            3.1.2 сооружение (civil engineering works): Объекты завершенного строительства.
            """,
        )
    ]

    terms = _extract_glossary_terms_from_pages(pages)

    assert [term.article_no for term in terms] == ["3.1.1", "3.1.2"]
    assert terms[0].term == "объект (капитального) строительства"
    assert terms[0].english_term == "construction works"
    assert terms[0].definition == "Здание, строение, сооружение."
    assert terms[0].page == 5


def test_extract_glossary_terms_from_pages_ignores_headings_and_appends_multiline_text() -> None:
    pages = [
        (
            5,
            """
            3 Типы зданий и гражданских сооружений
            3.1 Основные термины
            3.1.3 здание (building): Объект, предназначенный для постоянного
            или временного пребывания в нем людей.
            3.2 Сооружения
            """,
        ),
        (
            6,
            """
            3.2.1 работы земляные (earthworks): Комплекс строительных работ,
            включающий выемку грунта.
            """,
        ),
    ]

    terms = _extract_glossary_terms_from_pages(pages)

    assert [term.article_no for term in terms] == ["3.1.3", "3.2.1"]
    assert terms[0].definition == (
        "Объект, предназначенный для постоянного или временного пребывания в нем людей."
    )
    assert terms[1].definition == "Комплекс строительных работ, включающий выемку грунта."