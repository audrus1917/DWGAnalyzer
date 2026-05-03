from __future__ import annotations

import os
from dataclasses import dataclass

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
    ollama_base_url: str
    ollama_embed_model: str
    ollama_llm_model: str
    ollama_timeout_seconds: float
    ollama_api_key: str


load_dotenv()

settings = Settings(
    database_url=os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres@localhost:5432/parsedwg_db"),
    database_echo=_as_bool(os.getenv("DATABASE_ECHO"), default=False),
    ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"),
    ollama_embed_model=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
    ollama_llm_model=os.getenv("OLLAMA_LLM_MODEL", "llama3.1:8b"),
    ollama_timeout_seconds=_as_float(os.getenv("OLLAMA_TIMEOUT_SECONDS"), default=120.0),
    ollama_api_key=os.getenv("OLLAMA_API_KEY", "ollama")
)


__all__ = ["Settings", "settings"]