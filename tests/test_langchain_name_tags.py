import pytest

from parsedwg.langchain_name_tags import _build_prompt_template


def test_prompt_template_uses_only_text_variable() -> None:
    prompts = pytest.importorskip("langchain_core.prompts")
    chat_prompt_template_cls = getattr(prompts, "ChatPromptTemplate")

    prompt = _build_prompt_template(chat_prompt_template_cls)

    assert prompt.input_variables == ["text"]
