from typing import Any
from unittest.mock import MagicMock

import pytest
from llama_index.core.base.llms.types import LLMMetadata
from llama_index.core.llms import LLM
from llama_index.core.multi_modal_llms import MultiModalLLMMetadata

from autochat.components.llm.custom.base import AutoChatLLM
from autochat.components.workflows.others.summary_query_engine import (
    SummaryQueryEngine,
)


@pytest.fixture
def mock_llm() -> LLM:
    llm = MagicMock(spec=LLM)
    llm.metadata.context_window = 1024
    llm.metadata.num_output = 256
    return llm


class CustomAutoChatLLM(AutoChatLLM):
    def __init__(self, **kwargs) -> None:
        super().__init__(
            message_to_input=MagicMock(),
            completion_to_input=MagicMock(),
        )

    def get_metadata(self, **kwargs: Any) -> LLMMetadata | MultiModalLLMMetadata:
        return LLMMetadata(
            context_window=1024,
            num_output=kwargs.get("max_tokens") or 256,
        )


@pytest.fixture
def mock_autochat_llm() -> AutoChatLLM:
    return CustomAutoChatLLM()


def test_prompt_helper(mock_llm: LLM) -> None:
    prompt_helper = SummaryQueryEngine._get_prompt_helper(llm=mock_llm)
    assert prompt_helper.context_window == 1024
    assert prompt_helper.num_output == 256


def test_prompt_helper_with_triton_llm(mock_autochat_llm: AutoChatLLM) -> None:
    prompt_helper = SummaryQueryEngine._get_prompt_helper(
        llm=mock_autochat_llm,
    )
    assert prompt_helper.context_window == 1024
    assert prompt_helper.num_output == 256


def test_prompt_helper_with_triton_llm_with_kwargs(
    mock_autochat_llm: AutoChatLLM,
) -> None:
    prompt_helper = SummaryQueryEngine._get_prompt_helper(
        llm=mock_autochat_llm,
        max_tokens=2048,
    )
    assert prompt_helper.context_window == 1024
    assert prompt_helper.num_output == 2048


def test_prompt_helper_with_triton_llm_with_invalid_kwargs(
    mock_autochat_llm: AutoChatLLM,
) -> None:
    prompt_helper = SummaryQueryEngine._get_prompt_helper(
        llm=mock_autochat_llm,
        max_tokens=None,
    )
    assert prompt_helper.context_window == 1024
    assert prompt_helper.num_output == 256
