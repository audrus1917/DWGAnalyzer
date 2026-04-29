import pytest

from parsedwg.langchain_name_tags import LangChainNameTagsExtractor
from parsedwg.langchain_name_tags import _build_prompt_template
from parsedwg.langchain_name_tags import _build_scored_text_tags_prompt_template
from parsedwg.langchain_name_tags import _build_scored_token_tags_prompt_template
from parsedwg.langchain_name_tags import _build_token_tags_prompt_template


def test_prompt_template_uses_only_text_variable() -> None:
    prompts = pytest.importorskip("langchain_core.prompts")
    chat_prompt_template_cls = getattr(prompts, "ChatPromptTemplate")

    prompt = _build_prompt_template(chat_prompt_template_cls)

    assert prompt.input_variables == ["text"]


def test_token_tags_prompt_template_uses_only_tokens_variable() -> None:
    prompts = pytest.importorskip("langchain_core.prompts")
    chat_prompt_template_cls = getattr(prompts, "ChatPromptTemplate")

    prompt = _build_token_tags_prompt_template(chat_prompt_template_cls)

    assert prompt.input_variables == ["context", "tokens"]


def test_scored_token_tags_prompt_template_uses_only_tokens_variable() -> None:
    prompts = pytest.importorskip("langchain_core.prompts")
    chat_prompt_template_cls = getattr(prompts, "ChatPromptTemplate")

    prompt = _build_scored_token_tags_prompt_template(chat_prompt_template_cls)

    assert prompt.input_variables == ["context", "tokens"]


def test_scored_text_tags_prompt_template_uses_only_text_variable() -> None:
    prompts = pytest.importorskip("langchain_core.prompts")
    chat_prompt_template_cls = getattr(prompts, "ChatPromptTemplate")

    prompt = _build_scored_text_tags_prompt_template(chat_prompt_template_cls)

    assert prompt.input_variables == ["context", "text"]


def test_extract_token_meanings_parses_json_and_removes_duplicates() -> None:
    captured_payloads: list[dict[str, str]] = []

    class StubChain:
        def invoke(self, payload):
            captured_payloads.append(payload)
            return '{"M_Doors": ["двери", "проемы", "двери"], "M_Wall_Glass": ["стекло"]}'

    extractor = LangChainNameTagsExtractor(chain=StubChain(), token_tags_chain=StubChain())

    meanings = extractor.extract_token_meanings(
        ["M_Doors", "M_Wall_Glass"],
        extra_context="строительство, чертеж",
    )

    assert meanings == {
        "M_Doors": ["двери", "проемы"],
        "M_Wall_Glass": ["стекло"],
    }
    assert captured_payloads == [
        {
            "tokens": "M_Doors, M_Wall_Glass",
            "context": "строительство, чертеж",
        }
    ]


def test_extract_token_meanings_json_returns_json_object() -> None:
    class StubChain:
        def invoke(self, _payload):
            return '{"M_Doors": ["двери", "проемы", "архитектура"]}'

    extractor = LangChainNameTagsExtractor(chain=StubChain(), token_tags_chain=StubChain())

    meanings_json = extractor.extract_token_meanings_json(["M_Doors"])

    assert meanings_json == '{\n  "M_Doors": [\n    "двери",\n    "проемы",\n    "архитектура"\n  ]\n}'


def test_extract_token_meanings_scored_parses_json_and_keeps_max_score() -> None:
    captured_payloads: list[dict[str, str]] = []

    class StubChain:
        def invoke(self, payload):
            captured_payloads.append(payload)
            return (
                '{"M_Doors": ['
                '{"meaning": "двери", "score": 0.91}, '
                '{"meaning": "двери", "score": 0.73}, '
                '{"label": "проемы", "confidence": "0.42"}, '
                '{"tag": "вход", "weight": 1.4}]}'
            )

    extractor = LangChainNameTagsExtractor(
        chain=StubChain(),
        token_tags_chain=StubChain(),
        scored_token_tags_chain=StubChain(),
    )

    meanings = extractor.extract_token_meanings_scored(
        ["M_Doors"],
        extra_context="строительство, чертеж",
    )

    assert meanings == {
        "M_Doors": [
            {"meaning": "вход", "score": 1.0},
            {"meaning": "двери", "score": 0.91},
            {"meaning": "проемы", "score": 0.42},
        ]
    }
    assert captured_payloads == [
        {
            "tokens": "M_Doors",
            "context": "строительство, чертеж",
        }
    ]


def test_extract_token_meanings_scored_json_accepts_plain_strings_fallback() -> None:
    class StubChain:
        def invoke(self, _payload):
            return '{"M_Doors": ["двери", "проемы"]}'

    extractor = LangChainNameTagsExtractor(
        chain=StubChain(),
        token_tags_chain=StubChain(),
        scored_token_tags_chain=StubChain(),
    )

    meanings_json = extractor.extract_token_meanings_scored_json(["M_Doors"])

    assert meanings_json == (
        '{\n'
        '  "M_Doors": [\n'
        '    {\n'
        '      "meaning": "двери",\n'
        '      "score": null\n'
        '    },\n'
        '    {\n'
        '      "meaning": "проемы",\n'
        '      "score": null\n'
        '    }\n'
        '  ]\n'
        '}'
    )


def test_extract_scored_tags_parses_json_and_keeps_max_score() -> None:
    captured_payloads: list[dict[str, str]] = []

    class StubChain:
        def invoke(self, payload):
            captured_payloads.append(payload)
            return (
                '{"tags": ['
                '{"meaning": "насос", "score": 0.84}, '
                '{"tag": "насос", "weight": 0.42}, '
                '{"label": "пожаротушение", "confidence": "0.57"}]}'
            )

    extractor = LangChainNameTagsExtractor(
        chain=StubChain(),
        scored_text_tags_chain=StubChain(),
    )

    meanings = extractor.extract_scored_tags(
        "Насос пожаротушения",
        extra_context="строительство, чертеж",
    )

    assert meanings == [
        {"meaning": "насос", "score": 0.84},
        {"meaning": "пожаротушение", "score": 0.57},
    ]
    assert captured_payloads == [
        {
            "text": "Насос пожаротушения",
            "context": "строительство, чертеж",
        }
    ]


def test_extract_name_meanings_json_returns_json_array() -> None:
    captured_payloads: list[dict[str, str]] = []

    class StubChain:
        def invoke(self, payload):
            captured_payloads.append(payload)
            return '{"tags": [{"meaning": "насос", "score": 0.84}]}'

    extractor = LangChainNameTagsExtractor(
        chain=StubChain(),
        scored_text_tags_chain=StubChain(),
    )

    payload = extractor.extract_name_meanings_json(
        "Насос пожаротушения",
        extra_context="пожарная система",
    )

    assert payload == (
        '[\n'
        '  {\n'
        '    "meaning": "насос",\n'
        '    "score": 0.84\n'
        '  }\n'
        ']'
    )
    assert captured_payloads == [
        {
            "text": "Насос пожаротушения",
            "context": "пожарная система",
        }
    ]


def test_call_ollama_name_meaning_sends_prompt_and_returns_text() -> None:
    import json
    from unittest.mock import MagicMock, patch

    from parsedwg.langchain_name_tags import call_ollama_name_meaning

    body = json.dumps({
        "message": {"role": "assistant", "content": "1. Насос\n2. Этаж: 4"}
    }).encode()

    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        result = call_ollama_name_meaning(
            name="Насос 4 этаж",
            chat_url="http://localhost:11434/api/chat",
            model="llama3.1:8b",
            extra_context="раздел ВК",
        )

    assert result == "1. Насос\n2. Этаж: 4"
    req = mock_urlopen.call_args[0][0]
    req_body = json.loads(req.data.decode())
    assert req_body["model"] == "llama3.1:8b"
    assert req_body["stream"] is False
    content = req_body["messages"][0]["content"]
    assert "Насос 4 этаж" in content
    assert "раздел ВК" in content
    assert "эксперт по обработке данных DXF и BIM" in content


def test_call_ollama_name_meaning_raises_on_connection_error() -> None:
    import urllib.error
    from unittest.mock import patch

    from parsedwg.langchain_name_tags import call_ollama_name_meaning

    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("connection refused"),
    ):
        try:
            call_ollama_name_meaning(
                name="Насос",
                chat_url="http://localhost:11434/api/chat",
                model="llama3.1:8b",
            )
            assert False, "ожидался RuntimeError"
        except RuntimeError as exc:
            assert "Ошибка соединения" in str(exc)


def test_call_openai_chat_completions_name_meaning_sends_prompt_and_returns_text() -> None:
    import json
    from unittest.mock import MagicMock, patch

    from parsedwg.langchain_name_tags import call_openai_chat_completions_name_meaning

    body = json.dumps({
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Насос пожаротушения. 4-й этаж."
                }
            }
        ]
    }).encode()

    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        result = call_openai_chat_completions_name_meaning(
            name="Насос 4 этаж",
            completions_url="http://localhost:11434/v1/chat/completions",
            model="llama3.1:8b",
            extra_context="раздел ВК",
            api_key="ollama",
        )

    assert result == "Насос пожаротушения. 4-й этаж."
    req = mock_urlopen.call_args[0][0]
    req_body = json.loads(req.data.decode())
    assert req_body["model"] == "llama3.1:8b"
    assert req_body["stream"] is False
    assert req.headers["Authorization"] == "Bearer ollama"
    assert req_body["messages"][0]["role"] == "system"
    assert "эксперт по обработке данных DXF и BIM" in req_body["messages"][0]["content"]
    assert req_body["messages"][1]["role"] == "user"
    content = req_body["messages"][1]["content"]
    assert "Насос 4 этаж" in content
    assert "раздел ВК" in content


def test_call_openai_chat_completions_name_meaning_raises_on_connection_error() -> None:
    import urllib.error
    from unittest.mock import patch

    from parsedwg.langchain_name_tags import call_openai_chat_completions_name_meaning

    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("connection refused"),
    ):
        try:
            call_openai_chat_completions_name_meaning(
                name="Насос",
                completions_url="http://localhost:11434/v1/chat/completions",
                model="llama3.1:8b",
            )
            assert False, "ожидался RuntimeError"
        except RuntimeError as exc:
            assert "Ошибка соединения" in str(exc)
