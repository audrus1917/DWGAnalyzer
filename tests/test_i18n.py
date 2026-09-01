from dwganalyzer.i18n import _, using_language


SOURCE_MESSAGE = "DWG/DXF drawing analyzer"


def test_english_fallback() -> None:
    with using_language("en"):
        assert _(SOURCE_MESSAGE) == SOURCE_MESSAGE


def test_missing_catalog_fallback() -> None:
    with using_language("missing_LOCALE"):
        assert _(SOURCE_MESSAGE) == SOURCE_MESSAGE


def test_russian_translation() -> None:
    with using_language("ru"):
        assert _(SOURCE_MESSAGE) == "Анализатор чертежей DWG/DXF"


def test_language_context_is_restored() -> None:
    with using_language("en"):
        with using_language("ru"):
            assert _(SOURCE_MESSAGE) == "Анализатор чертежей DWG/DXF"
        assert _(SOURCE_MESSAGE) == SOURCE_MESSAGE
