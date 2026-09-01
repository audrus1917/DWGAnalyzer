"""Centralized GNU gettext configuration for DWGAnalyzer."""

from __future__ import annotations

import gettext
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path

DOMAIN = "dwganalyzer"
LOCALE_DIR = Path(__file__).resolve().parent / "locale"

_language: ContextVar[str | None] = ContextVar("dwganalyzer_language", default=None)


@lru_cache(maxsize=None)
def get_translation(language: str | None = None) -> gettext.NullTranslations:
    """Return the translation catalog for a language.

    Args:
        language: Locale name such as ``ru`` or ``ru_RU``. When omitted,
            gettext uses the process locale environment.

    Returns:
        A translation object with English fallback behavior.
    """

    languages = [language] if language else None
    return gettext.translation(
        DOMAIN,
        localedir=LOCALE_DIR,
        languages=languages,
        fallback=True,
    )


def _(message: str) -> str:
    """Translate a user-facing message in the active language."""

    return get_translation(_language.get()).gettext(message)


def ngettext(singular: str, plural: str, count: int) -> str:
    """Translate a singular or plural user-facing message."""

    return get_translation(_language.get()).ngettext(singular, plural, count)


@contextmanager
def using_language(language: str | None) -> Iterator[None]:
    """Temporarily select a language for the current execution context.

    Args:
        language: Locale name, or ``None`` to use the process locale.

    Yields:
        Control while the requested language is active.
    """

    token = _language.set(language)
    try:
        yield
    finally:
        _language.reset(token)


__all__ = [
    "_",
    "DOMAIN",
    "LOCALE_DIR",
    "get_translation",
    "ngettext",
    "using_language",
]
