from collections.abc import Iterator

import pytest

from dwganalyzer.i18n import using_language


@pytest.fixture(autouse=True)
def english_language() -> Iterator[None]:
    """Keep tests independent from the developer machine locale."""

    with using_language("en"):
        yield
