import importlib


def test_ollama_base_url_from_env(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:18080/")
    monkeypatch.setenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    monkeypatch.setenv("OLLAMA_LLM_MODEL", "llama3.2")

    import parsedwg.settings as settings_module
    importlib.reload(settings_module)
    import parsedwg.rag as rag

    importlib.reload(rag)
    assert rag.OLLAMA_BASE_URL == "http://127.0.0.1:18080"


def test_database_url_from_env(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/custom_db")
    monkeypatch.setenv("DATABASE_ECHO", "true")

    import parsedwg.settings as settings_module

    importlib.reload(settings_module)
    assert settings_module.settings.database_url == "postgresql+asyncpg://u:p@localhost:5432/custom_db"
    assert settings_module.settings.database_echo is True
