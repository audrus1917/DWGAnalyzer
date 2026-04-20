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


@dataclass(frozen=True)
class LangChainAgentConfig:
    model: str
    base_url: str
    api_key: str
    timeout_seconds: float = 60.0


class LangChainNameTagsExtractor:
    """Извлекает смысловые теги через LLM, завернутый в LangChain."""

    def __init__(self, chain):
        self._chain = chain

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

        chain = prompt | model | StrOutputParser()
        return cls(chain)

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
