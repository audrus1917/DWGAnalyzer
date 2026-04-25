"""LangChain-экстрактор тегов для имен/текстов.

Модуль импортируется только при явно включенном AI-режиме.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import json
import logging


logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = (
    "Ты извлекаешь теги из текстов чертежей. "
    "Верни только JSON вида {{\"tags\": [\"...\"]}}. "
    "Без пояснений."
)
_HUMAN_PROMPT = (
    "Текст: {text}\n"
    "Верни 0..8 коротких тегов на русском, только существительные/термины."
)
_TOKEN_TAGS_SYSTEM_PROMPT = (
    "Ты анализируешь токены из имен CAD-слоев, файлов и блоков. "
    "Верни только JSON-объект, где ключ это исходный токен, а значение это список "
    "из 1..8 коротких смыслов на русском. "
    "Без пояснений, без markdown, без текста вне JSON."
)
_TOKEN_TAGS_HUMAN_PROMPT = (
    "Токены: {tokens}\n"
    "Для каждого токена определи возможный инженерный смысл и верни JSON-словарь "
    "вида {{\"TOKEN\": [\"смысл1\", \"смысл2\"]}}."
)


@dataclass(frozen=True)
class LangChainAgentConfig:
    model: str
    base_url: str
    api_key: str
    timeout_seconds: float = 60.0


class LangChainNameTagsExtractor:
    """Извлекает смысловые теги через LLM, завернутый в LangChain."""

    def __init__(self, chain, token_tags_chain=None):
        self._chain = chain
        self._token_tags_chain = token_tags_chain or chain

    @classmethod
    def from_config(cls, config: LangChainAgentConfig) -> "LangChainNameTagsExtractor":
        ensure_langchain_available()

        output_parsers_module = importlib.import_module("langchain_core.output_parsers")
        prompts_module = importlib.import_module("langchain_core.prompts")
        openai_module = importlib.import_module("langchain_openai")

        StrOutputParser = getattr(output_parsers_module, "StrOutputParser")
        ChatPromptTemplate = getattr(prompts_module, "ChatPromptTemplate")
        ChatOpenAI = getattr(openai_module, "ChatOpenAI")

        model = ChatOpenAI(
            model=config.model,
            base_url=config.base_url,
            api_key=config.api_key,
            temperature=0,
            timeout=config.timeout_seconds,
        )

        prompt = _build_prompt_template(ChatPromptTemplate)
        token_tags_prompt = _build_token_tags_prompt_template(ChatPromptTemplate)

        chain = prompt | model | StrOutputParser()
        token_tags_chain = token_tags_prompt | model | StrOutputParser()
        return cls(chain, token_tags_chain=token_tags_chain)

    def extract(self, text: str) -> list[str]:
        logger.debug("LLM input text: %s", text)
        raw = self._chain.invoke({"text": text})
        logger.debug("LLM raw response: %s", raw)
        payload = self._parse_json(raw)
        tags = payload.get("tags", [])
        if not isinstance(tags, list):
            return []

        normalized: list[str] = []
        for item in tags:
            if not isinstance(item, str):
                continue
            value = " ".join(item.strip().split())
            if value:
                normalized.append(value)

        # Стабильный порядок без дублей
        return sorted(set(normalized))

    def extract_token_meanings(self, tokens: list[str]) -> dict[str, list[str]]:
        cleaned_tokens = [token.strip() for token in tokens if isinstance(token, str) and token.strip()]
        if not cleaned_tokens:
            return {}

        joined_tokens = ", ".join(cleaned_tokens)
        logger.debug("LLM input tokens: %s", joined_tokens)
        raw = self._token_tags_chain.invoke({"tokens": joined_tokens})
        logger.debug("LLM raw token-tags response: %s", raw)
        return self._parse_token_meanings(raw, cleaned_tokens)

    def extract_token_meanings_json(self, tokens: list[str]) -> str:
        return json.dumps(self.extract_token_meanings(tokens), ensure_ascii=False, indent=2)

    @staticmethod
    def _parse_json(raw: str) -> dict[str, object]:
        raw = raw.strip()
        if not raw:
            return {}

        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            # Поддержка ответа в markdown fenced block.
            start = raw.find("{")
            end = raw.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return {}
            fragment = raw[start : end + 1]
            try:
                value = json.loads(fragment)
                return value if isinstance(value, dict) else {}
            except json.JSONDecodeError:
                return {}

    @classmethod
    def _parse_token_meanings(
        cls,
        raw: str,
        requested_tokens: list[str],
    ) -> dict[str, list[str]]:
        raw = raw.strip()
        if not raw:
            return {token: [] for token in requested_tokens}

        payload = cls._parse_json(raw)
        result: dict[str, list[str]] = {token: [] for token in requested_tokens}
        if not payload:
            return result

        nested_payload = payload.get("meanings") if isinstance(payload.get("meanings"), dict) else payload
        if not isinstance(nested_payload, dict):
            return result

        requested_lookup = {token.lower(): token for token in requested_tokens}
        for key, value in nested_payload.items():
            if not isinstance(key, str):
                continue
            requested_token = requested_lookup.get(key.strip().lower())
            if requested_token is None:
                continue
            if isinstance(value, list):
                result[requested_token] = cls._normalize_tags(value)
            elif isinstance(value, str):
                result[requested_token] = cls._normalize_tags([item for item in value.split(",")])
        return result

    @staticmethod
    def _normalize_tags(items: list[object]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, str):
                continue
            value = " ".join(item.strip().split())
            if not value:
                continue
            lowered = value.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            result.append(value)
        return result


def extract_semantic_token_meanings_json(tokens: list[str], config: LangChainAgentConfig) -> str:
    """Возвращает JSON-словарь token -> list[str] для списка токенов."""

    extractor = LangChainNameTagsExtractor.from_config(config)
    return extractor.extract_token_meanings_json(tokens)


def ensure_langchain_available() -> None:
    try:
        importlib.import_module("langchain_core")
        importlib.import_module("langchain_openai")
    except ImportError as error:
        raise RuntimeError(
            "Для AI-режима установите зависимости: "
            "langchain-core, langchain-openai"
        ) from error


def _build_prompt_template(chat_prompt_template_cls):
    return chat_prompt_template_cls.from_messages(
        [
            ("system", _SYSTEM_PROMPT),
            ("human", _HUMAN_PROMPT),
        ]
    )


def _build_token_tags_prompt_template(chat_prompt_template_cls):
    return chat_prompt_template_cls.from_messages(
        [
            ("system", _TOKEN_TAGS_SYSTEM_PROMPT),
            ("human", _TOKEN_TAGS_HUMAN_PROMPT),
        ]
    )
