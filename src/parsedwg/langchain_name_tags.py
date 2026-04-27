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
_TOKEN_TAGS_SCORED_SYSTEM_PROMPT = (
    "Ты анализируешь токены из имен CAD-слоев, файлов и блоков. "
    "Верни только JSON-объект, где ключ это исходный токен, а значение это список "
    "объектов вида {{\"meaning\": \"...\", \"score\": 0.0}}. "
    "score это уверенность от 0 до 1. "
    "Список отсортируй по убыванию score. "
    "Без пояснений, без markdown, без текста вне JSON."
)
_TOKEN_TAGS_SCORED_HUMAN_PROMPT = (
    "Токены: {tokens}\n"
    "Для каждого токена определи возможный инженерный смысл и верни JSON-словарь "
    "вида {{\"TOKEN\": [{{\"meaning\": \"смысл1\", \"score\": 0.95}}, "
    "{{\"meaning\": \"смысл2\", \"score\": 0.42}}]}}."
)


@dataclass(frozen=True)
class LangChainAgentConfig:
    model: str
    base_url: str
    api_key: str
    timeout_seconds: float = 60.0


class LangChainNameTagsExtractor:
    """Извлекает смысловые теги через LLM, завернутый в LangChain."""

    def __init__(self, chain, token_tags_chain=None, scored_token_tags_chain=None):
        self._chain = chain
        self._token_tags_chain = token_tags_chain or chain
        self._scored_token_tags_chain = scored_token_tags_chain or self._token_tags_chain

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
        scored_token_tags_prompt = _build_scored_token_tags_prompt_template(ChatPromptTemplate)

        chain = prompt | model | StrOutputParser()
        token_tags_chain = token_tags_prompt | model | StrOutputParser()
        scored_token_tags_chain = scored_token_tags_prompt | model | StrOutputParser()
        return cls(
            chain,
            token_tags_chain=token_tags_chain,
            scored_token_tags_chain=scored_token_tags_chain,
        )

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

    def extract_token_meanings_scored(
        self, 
        tokens: list[str]
    ) -> dict[str, list[dict[str, object]]]:
        """Возвращает словарь token -> list[{"meaning": str, "score": float | None}]."""
        
        cleaned_tokens = [token.strip() for token in tokens if isinstance(token, str) and token.strip()]
        if not cleaned_tokens:
            return {}

        joined_tokens = ", ".join(cleaned_tokens)
        logger.debug("LLM input scored tokens: %s", joined_tokens)
        raw = self._scored_token_tags_chain.invoke({"tokens": joined_tokens})
        logger.debug("LLM raw scored token-tags response: %s", raw)
        return self._parse_scored_token_meanings(raw, cleaned_tokens)

    def extract_token_meanings_scored_json(self, tokens: list[str]) -> str:
        return json.dumps(self.extract_token_meanings_scored(tokens), ensure_ascii=False, indent=2)

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

    @classmethod
    def _parse_scored_token_meanings(
        cls,
        raw: str,
        requested_tokens: list[str],
    ) -> dict[str, list[dict[str, object]]]:
        raw = raw.strip()
        if not raw:
            return {token: [] for token in requested_tokens}

        payload = cls._parse_json(raw)
        result: dict[str, list[dict[str, object]]] = {token: [] for token in requested_tokens}
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
                result[requested_token] = cls._normalize_scored_tags(value)
            elif isinstance(value, str):
                normalized = cls._normalize_tags([item for item in value.split(",")])
                result[requested_token] = [
                    {"meaning": item, "score": None} for item in normalized
                ]
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

    @classmethod
    def _normalize_scored_tags(cls, items: list[object]) -> list[dict[str, object]]:
        scored_by_meaning: dict[str, dict[str, object]] = {}

        for item in items:
            if isinstance(item, str):
                for normalized in cls._normalize_tags([item]):
                    lowered = normalized.lower()
                    if lowered not in scored_by_meaning:
                        scored_by_meaning[lowered] = {"meaning": normalized, "score": None}
                continue

            if not isinstance(item, dict):
                continue

            meaning = item.get("meaning")
            if not isinstance(meaning, str):
                meaning = item.get("label")
            if not isinstance(meaning, str):
                meaning = item.get("tag")
            if not isinstance(meaning, str):
                continue

            normalized_meanings = cls._normalize_tags([meaning])
            if not normalized_meanings:
                continue
            normalized_meaning = normalized_meanings[0]
            lowered = normalized_meaning.lower()

            score = item.get("score")
            if score is None:
                score = item.get("confidence")
            if score is None:
                score = item.get("weight")

            normalized_score = cls._normalize_score(score)
            existing = scored_by_meaning.get(lowered)
            if existing is None:
                scored_by_meaning[lowered] = {
                    "meaning": normalized_meaning,
                    "score": normalized_score,
                }
                continue

            existing_score = existing.get("score")
            if cls._score_rank(normalized_score) > cls._score_rank(existing_score):
                scored_by_meaning[lowered] = {
                    "meaning": normalized_meaning,
                    "score": normalized_score,
                }

        return sorted(
            scored_by_meaning.values(),
            key=lambda item: (
                -cls._score_sort_value(item.get("score")),
                str(item.get("meaning", "")).lower(),
            ),
        )

    @staticmethod
    def _normalize_score(value: object) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            numeric = float(value)
        elif isinstance(value, str):
            try:
                numeric = float(value.strip().replace(",", "."))
            except ValueError:
                return None
        else:
            return None
        numeric = max(0.0, min(1.0, numeric))
        return round(numeric, 4)

    @staticmethod
    def _score_sort_value(value: object) -> float:
        return float(value) if isinstance(value, (int, float)) else -1.0

    @staticmethod
    def _score_rank(value: object) -> tuple[int, float]:
        if isinstance(value, (int, float)):
            return (1, float(value))
        return (0, -1.0)


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


def _build_scored_token_tags_prompt_template(chat_prompt_template_cls):
    return chat_prompt_template_cls.from_messages(
        [
            ("system", _TOKEN_TAGS_SCORED_SYSTEM_PROMPT),
            ("human", _TOKEN_TAGS_SCORED_HUMAN_PROMPT),
        ]
    )
