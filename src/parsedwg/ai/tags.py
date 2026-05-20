"""LangChain-based tag extractor for names and texts.

This module is imported only when AI mode is explicitly enabled.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import json
import logging
import re

from src.parsedwg.settings import settings

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
    "Дополнительный контекст: {context}\n"
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
    "Дополнительный контекст: {context}\n"
    "Для каждого токена определи возможный инженерный смысл и верни JSON-словарь "
    "вида {{\"TOKEN\": [{{\"meaning\": \"смысл1\", \"score\": score}}, "
    "{{\"meaning\": \"смысл2\", \"score\": score}}]}}."
)
_TEXT_TAGS_SCORED_SYSTEM_PROMPT = (
    "Ты анализируешь наименование сущности. "
    "Верни только JSON-объект вида {{\"tags\": [{{\"meaning\": \"...\", \"score\": 0.0}}]}}. "
    "score это уверенность от 0 до 1. "
    "Список отсортируй по убыванию score. "
    "Без пояснений, без markdown, без текста вне JSON."
)
_TEXT_TAGS_SCORED_HUMAN_PROMPT = (
    "Наименование сущности: {text}\n"
    "Дополнительный контекст: {context}\n"
    "Определи 0..3 коротких инженерных смыслов на русском и верни JSON-объект вида "
    "Если в названии есть важные числа или отметки, сохраняй их в смысле, "
    "например: 4-й этаж, отметка +2 м. "
    "{{\"tags\": [{{\"meaning\": \"смысл1\", \"score\": score}}, "
    "{{\"meaning\": \"смысл2\", \"score\": score}}]}}."
)


# Optimized system prompt for Llama 3.1 8B.
NAME_MEANING_SYSTEM_PROMPT = (
    "Ты — эксперт по обработке данных DXF и BIM. Твоя задача: определять категории объекта по его техническому имени или описанию. "
    "ПРАВИЛО: Ответ строго в одну строку по шаблону: Категории: [тип, тип, тип, тип, тип]. Описание: [суть]. "
    "Никаких вводных слов и пояснений. Список категорий до 5 эелементов. Примитивы (HATCH, LINE) переводи технически (Штриховка, Линия)."
)

# Optimized request template.
NAME_MEANING_HUMAN_PROMPT_TEMPLATE = (
    "Проанализируй название объекта.\n\n"
    "ПРИМЕРЫ:\n"
    "Вход: \"HATCH, Парапет\"\n"
    "Ответ: Категории: Кровля, Ограждение, Штриховка.\n\n"
    "ДАННЫЕ:\n"
    "Название сущности: \"{name}\"\n"
    "Дополнительный контекст: {context_line}\n\n"
    "Инструкция:\n"
    "- Игнорируй префиксы (RECOVER, COPY), даты, ID и одиночные символы.\n"
    "- Сфокусируйся на материале и назначении.\n"
    "- Ответ строго в одну строку.\n\n"
    "Ответ:"
)


def get_interpretation_categories(text: str) -> list[str]:
    categories: list[str] = []
    if text:
        _m = re.compile(r"^Категории:\s*(.*?)\.\s*Описание:\s*(.*)$", re.IGNORECASE).match(text.strip())
        if _m:
            categories = _m.group(1).split(",")
            categories = [c.strip() for c in categories]
    return categories

@dataclass(frozen=True)
class AgentConfig:
    model: str
    base_url: str
    api_key: str
    timeout_seconds: float = 60.0


class TagsExtractor:
    """Извлекает семантические теги через LLM, обёрнутую в LangChain."""

    def __init__(
        self,
        chain,
        token_tags_chain=None,
        scored_token_tags_chain=None,
        scored_text_tags_chain=None,
    ):
        self._chain = chain
        self._token_tags_chain = token_tags_chain or chain
        self._scored_token_tags_chain = scored_token_tags_chain or self._token_tags_chain
        self._scored_text_tags_chain = scored_text_tags_chain or chain

    @classmethod
    def from_config(cls, config: AgentConfig) -> "TagsExtractor":
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
        scored_text_tags_prompt = _build_scored_text_tags_prompt_template(ChatPromptTemplate)

        chain = prompt | model | StrOutputParser()
        token_tags_chain = token_tags_prompt | model | StrOutputParser()
        scored_token_tags_chain = scored_token_tags_prompt | model | StrOutputParser()
        scored_text_tags_chain = scored_text_tags_prompt | model | StrOutputParser()
        return cls(
            chain,
            token_tags_chain=token_tags_chain,
            scored_token_tags_chain=scored_token_tags_chain,
            scored_text_tags_chain=scored_text_tags_chain,
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

        # Keep a stable order without duplicates.
        return sorted(set(normalized))

    def extract_token_meanings(
        self,
        tokens: list[str],
        extra_context: str = "",
    ) -> dict[str, list[str]]:
        cleaned_tokens = [token.strip() for token in tokens if isinstance(token, str) and token.strip()]
        if not cleaned_tokens:
            return {}

        joined_tokens = ", ".join(cleaned_tokens)
        logger.debug("LLM input tokens: %s", joined_tokens)
        raw = self._token_tags_chain.invoke(
            {"tokens": joined_tokens, "context": extra_context.strip()}
        )
        logger.debug("LLM raw token-tags response: %s", raw)
        return self._parse_token_meanings(raw, cleaned_tokens)

    def extract_token_meanings_json(
        self,
        tokens: list[str],
        extra_context: str = "",
    ) -> str:
        return json.dumps(
            self.extract_token_meanings(tokens, extra_context=extra_context),
            ensure_ascii=False,
            indent=2,
        )

    def extract_scored_tags(
        self,
        text: str,
        extra_context: str = "",
    ) -> list[dict[str, object]]:
        cleaned_text = " ".join(text.split())
        if not cleaned_text:
            return []

        logger.debug("LLM input scored text: %s", cleaned_text)
        raw = self._scored_text_tags_chain.invoke(
            {"text": cleaned_text, "context": extra_context.strip()}
        )
        logger.debug("LLM raw scored text-tags response: %s", raw)

        payload = self._parse_json(raw)
        tags = payload.get("tags", []) if isinstance(payload, dict) else []
        if not isinstance(tags, list):
            return []
        return self._normalize_scored_tags(tags)

    def extract_scored_tags_json(
        self,
        text: str,
        extra_context: str = "",
    ) -> str:
        return json.dumps(
            self.extract_scored_tags(text, extra_context=extra_context),
            ensure_ascii=False,
            indent=2,
        )

    def extract_name_meanings(
        self,
        name: str,
        extra_context: str = "",
    ) -> list[dict[str, object]]:
        return self.extract_scored_tags(name, extra_context=extra_context)

    def extract_name_meanings_json(
        self,
        name: str,
        extra_context: str = "",
    ) -> str:
        return json.dumps(
            self.extract_name_meanings(name, extra_context=extra_context),
            ensure_ascii=False,
            indent=2,
        )

    def extract_token_meanings_scored(
        self, 
        tokens: list[str],
        extra_context: str = "",
    ) -> dict[str, list[dict[str, object]]]:
        """Возвращает отображение token -> list[{"meaning": str, "score": float | None}]."""
        
        cleaned_tokens = [token.strip() for token in tokens if isinstance(token, str) and token.strip()]
        if not cleaned_tokens:
            return {}

        joined_tokens = ", ".join(cleaned_tokens)
        logger.debug("LLM input scored tokens: %s", joined_tokens)
        raw = self._scored_token_tags_chain.invoke(
            {"tokens": joined_tokens, "context": extra_context.strip()}
        )
        logger.debug("LLM raw scored token-tags response: %s", raw)
        return self._parse_scored_token_meanings(raw, cleaned_tokens)

    def extract_token_meanings_scored_json(
        self,
        tokens: list[str],
        extra_context: str = "",
    ) -> str:
        return json.dumps(
            self.extract_token_meanings_scored(tokens, extra_context=extra_context),
            ensure_ascii=False,
            indent=2,
        )

    @staticmethod
    def _parse_json(raw: str) -> dict[str, object]:
        raw = raw.strip()
        if not raw:
            return {}

        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            # Support a response wrapped in a fenced Markdown block.
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


def extract_semantic_token_meanings_json(tokens: list[str], config: AgentConfig) -> str:
    """Возвращает JSON-отображение token -> list[str] для переданных токенов."""

    extractor = TagsExtractor.from_config(config)
    return extractor.extract_token_meanings_json(tokens)


def ensure_langchain_available() -> None:
    """Проверяет наличие зависимостей LangChain для AI-режима.

    Raises:
        RuntimeError: Если обязательные пакеты LangChain не установлены.
    """
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


def _build_scored_text_tags_prompt_template(chat_prompt_template_cls):
    return chat_prompt_template_cls.from_messages(
        [
            ("system", _TEXT_TAGS_SCORED_SYSTEM_PROMPT),
            ("human", _TEXT_TAGS_SCORED_HUMAN_PROMPT),
        ]
    )



# def clean_cad_name(name):
#     # 1. Remove service words at the beginning (RECOVER, COPY, etc.).
#     name = re.sub(r'^(RECOVER|COPY|TMP|TEMP)_+', '', name, flags=re.IGNORECASE)
    
#     # 2. Remove long digit sequences and timestamps (6+ digits).
#     # Removes fragments such as 171212140632-1.
#     name = re.sub(r'[_\-]?\d{6,}[_\-]?\d*', '', name)
    
#     # 3. Remove dangling separators left at the start or end after cleanup.
#     name = name.strip('_ -')
    
#     return name

def _clean_cad_name_legacy(name):
    # 1. Remove service words (RECOVER, COPY, etc.).
    name = re.sub(r'^(RECOVER|COPY|TMP|TEMP)_+', '', name, flags=re.IGNORECASE)
    
    # 2. Remove special symbols: $, #, @, %, &, *.
    # Keep only letters, digits, spaces, underscores, and hyphens.
    name = re.sub(r'[$\#@%&*]', '', name)
    
    # 3. Remove long IDs and timestamps (6+ digits).
    name = re.sub(r'[_\-]?\d{6,}[_\-]?\d*', '', name)
    
    # 4. Remove redundant underscores/spaces that may have appeared.
    name = re.sub(r'[_\-\s]{2,}', '_', name)
    
    # 5. Final trim of surrounding separators.
    cleaned_name = name.strip('_ -')
    # logger.debug(f"Cleaned CAD name: '{cleaned_name}' from original '{name}'")
    return cleaned_name


def clean_cad_name(name):
    """Cleans CAD names by removing service noise, decoding mojibake, and 
    normalizing separators.
    """
    
    # if any(c in name for c in "РЎР"):
    #     name = name.encode(
    #         'cp1252', errors='ignore'
    #     ).decode('cp1251', errors='ignore')

    name = re.sub(r'^(RECOVER|COPY|TMP|TEMP)_+', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[$\#@%&*^!]', '', name)

    name = re.sub(r'[_\-]?\d{6,}[_\-]?\d*', '', name)

    name = re.sub(r'[_\-\s]+', ' ', name).strip()

    cleaned_name = name
    return cleaned_name



def build_system_prompt() -> str:
    return NAME_MEANING_SYSTEM_PROMPT


def build_human_prompt(
    name: str,
    extra_context: str = "",
) -> str:
    """Строит пользовательский prompt для анализа имени сущности."""
    context_line = (
        f"{extra_context.strip()}\n"
        if extra_context.strip()
        else ""
    )
    name  = clean_cad_name(name)
    return NAME_MEANING_HUMAN_PROMPT_TEMPLATE.format(
        name=name,
        context_line=context_line,
    )


def build_prompt(
    name: str,
    extra_context: str = "",
) -> str:
    """Строит полный текст prompt для обратной совместимости."""

    logger.debug(f"{extra_context}")
    return (
        f"{build_system_prompt()}\n\n"
        f"{build_human_prompt(name=name, extra_context=extra_context)}"
    )


def _derive_openai_chat_completions_url(base_url: str) -> str:
    """Build an OpenAI-compatible /v1/chat/completions URL from a base URL."""

    stripped = base_url.rstrip("/")
    if stripped.endswith("/chat/completions"):
        return stripped
    if stripped.endswith("/v1"):
        return stripped + "/chat/completions"
    return stripped + "/v1/chat/completions"


def _resolve_name_meaning_endpoint(url: str) -> tuple[str, str]:
    """Resolve the actual endpoint and protocol for name-meaning calls.

    Returns:
        Tuple of (kind, resolved_url), where kind is either "ollama" or "openai".
    """

    stripped = url.strip().rstrip("/")
    if not stripped:
        raise ValueError("LLM URL must not be empty.")
    if stripped.endswith("/api/chat"):
        return "ollama", stripped
    if stripped.endswith("/chat/completions"):
        return "openai", stripped
    if stripped.endswith("/v1"):
        return "openai", _derive_openai_chat_completions_url(stripped)
    if stripped.startswith("https://api.openai.com"):
        return "openai", _derive_openai_chat_completions_url(stripped)
    if stripped.startswith("https://") and "/v1" not in stripped:
        return "openai", _derive_openai_chat_completions_url(stripped)
    if stripped.startswith("http://localhost") or stripped.startswith("http://127.0.0.1"):
        return "ollama", stripped + "/api/chat"
    return "openai", _derive_openai_chat_completions_url(stripped)


def get_name_meaning(
    name: str,
    chat_url: str,
    model: str,
    extra_context: str = "",
    timeout_seconds: float = 60.0,
) -> str:
    """Возвращает свободную интерпретацию имени через Ollama или OpenAI-compatible chat.

    Raises:
        RuntimeError: Если сервис недоступен или вернул неожиданный либо пустой ответ.
    """
    endpoint_kind, resolved_url = _resolve_name_meaning_endpoint(chat_url)
    if endpoint_kind == "openai":
        return call_openai_chat_completions_name_meaning(
            name=name,
            completions_url=resolved_url,
            model=model,
            extra_context=extra_context,
            timeout_seconds=timeout_seconds,
            api_key=settings.ai_api_key,
        )

    import urllib.error
    import urllib.request

    prompt_text = build_prompt(name=name, extra_context=extra_context)
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt_text}],
        "stream": False,
    }).encode()

    api_key = settings.ai_api_key

    req = urllib.request.Request(
        resolved_url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key.strip()}" if api_key.strip() else "",},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            body = json.loads(response.read().decode())
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ошибка соединения с LLM ({resolved_url}): {exc}") from exc

    message = body.get("message", {})
    if not isinstance(message, dict):
        raise RuntimeError(f"Неожиданный формат ответа от LLM: {body}")
    text = message.get("content", "")
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError(f"LLM вернул пустой ответ: {body}")
    return text.strip()


def call_openai_chat_completions_name_meaning(
    name: str,
    completions_url: str,
    model: str,
    extra_context: str = "",
    timeout_seconds: float = 60.0,
    api_key: str = "",
) -> str:
    """Вызывает OpenAI-совместимый endpoint v1/chat/completions и возвращает текстовую интерпретацию.

    Raises:
        RuntimeError: Если сервис недоступен или вернул неожиданный либо пустой ответ.
    """
    import urllib.error
    import urllib.request

    system_prompt = build_system_prompt()
    human_prompt = build_human_prompt(name=name, extra_context=extra_context)
    logger.debug(
        "Prompts for OpenAI chat completions: system=%s human=%s",
        system_prompt,
        human_prompt,
    )
    
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": human_prompt},
        ],
        "stream": False,
    }).encode()

    headers = {"Content-Type": "application/json"}
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    req = urllib.request.Request(
        completions_url,
        data=payload,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            body = json.loads(response.read().decode())
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ошибка соединения с LLM ({completions_url}): {exc}") from exc

    choices = body.get("choices", [])
    if not isinstance(choices, list) or not choices:
        raise RuntimeError(f"Неожиданный формат ответа от LLM: {body}")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise RuntimeError(f"Неожиданный формат ответа от LLM: {body}")
    message = first_choice.get("message", {})
    if not isinstance(message, dict):
        raise RuntimeError(f"Неожиданный формат ответа от LLM: {body}")
    text = message.get("content", "")
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError(f"LLM вернул пустой ответ: {body}")
    return text.strip()
