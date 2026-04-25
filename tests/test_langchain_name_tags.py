import pytest

from parsedwg.langchain_name_tags import LangChainNameTagsExtractor
from parsedwg.langchain_name_tags import _build_prompt_template
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

    assert prompt.input_variables == ["tokens"]


def test_extract_token_meanings_parses_json_and_removes_duplicates() -> None:
    class StubChain:
        def invoke(self, _payload):
            return '{"M_Doors": ["двери", "проемы", "двери"], "M_Wall_Glass": ["стекло"]}'

    extractor = LangChainNameTagsExtractor(chain=StubChain(), token_tags_chain=StubChain())

    meanings = extractor.extract_token_meanings(["M_Doors", "M_Wall_Glass"])

    assert meanings == {
        "M_Doors": ["двери", "проемы"],
        "M_Wall_Glass": ["стекло"],
    }


def test_extract_token_meanings_json_returns_json_object() -> None:
    class StubChain:
        def invoke(self, _payload):
            return '{"M_Doors": ["двери", "проемы", "архитектура"]}'

    extractor = LangChainNameTagsExtractor(chain=StubChain(), token_tags_chain=StubChain())

    meanings_json = extractor.extract_token_meanings_json(["M_Doors"])

    assert meanings_json == '{\n  "M_Doors": [\n    "двери",\n    "проемы",\n    "архитектура"\n  ]\n}'
