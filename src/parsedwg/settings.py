"""Настройки приложения ParsedWG."""

from __future__ import annotations

import os
from dataclasses import dataclass

import pytz

from dotenv import load_dotenv


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    database_echo: bool
    ai_base_url: str
    ai_embed_model: str
    ai_model: str
    ai_timeout_seconds: float
    ai_api_key: str
    tz_name: str = "UTC"

    @property
    def tz(self) -> pytz.BaseTzInfo:
        return pytz.timezone(self.tz_name)


def get_ai_settings(
    enabled: bool,
    model: str,
    base_url: str,
    api_key: str,
) -> dict | None:
    """Возвращает конфигурацию AI для извлечения тегов из имён или None."""

    if not enabled:
        return None

    from src.parsedwg.langchain_name_tags import ensure_langchain_available

    ensure_langchain_available()
    return {
        "model": model,
        "base_url": base_url,
        "api_key": api_key,
    }


load_dotenv()

settings = Settings(
    database_url=os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres@localhost:5432/parsedwg_db"),
    database_echo=_as_bool(os.getenv("DATABASE_ECHO"), default=False),
    ai_base_url=os.getenv("AI_BASE_URL", "http://localhost:11434").rstrip("/"),
    ai_embed_model=os.getenv("AI_EMBED_MODEL", "nomic-embed-text"),
    ai_model=os.getenv("AI_MODEL", "llama3.1:8b"),
    ai_timeout_seconds=_as_float(os.getenv("AI_TIMEOUT_SECONDS"), default=120.0),
    ai_api_key=os.getenv("AI_API_KEY", "ollama")
)


__all__ = ["Settings", "settings", "get_ai_settings"]