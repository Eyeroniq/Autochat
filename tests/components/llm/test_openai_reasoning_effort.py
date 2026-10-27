from llama_index.core.base.llms.types import ChatMessage, MessageRole

from autochat.components.llm.custom.openailike import PatchedOpenAILikeLLM
from autochat.components.llm.models import ReasoningEffort


def _llm(model: str) -> PatchedOpenAILikeLLM:
    return PatchedOpenAILikeLLM(
        model=model,
        api_base="https://api.groq.com/openai/v1",
        api_key="test",
        is_chat_model=True,
    )


def test_gpt_oss_gets_low_instead_of_none() -> None:
    kwargs = _llm("openai/gpt-oss-120b")._get_model_kwargs(
        reasoning_effort=ReasoningEffort.NONE
    )
    assert kwargs["reasoning_effort"] == "low"


def test_gpt_oss_keeps_requested_effort() -> None:
    kwargs = _llm("openai/gpt-oss-120b")._get_model_kwargs(
        reasoning_effort=ReasoningEffort.HIGH
    )
    assert kwargs["reasoning_effort"] == "high"


def test_thinking_is_not_sent_back_but_stays_in_history() -> None:
    message = ChatMessage(
        role=MessageRole.ASSISTANT,
        content="",
        additional_kwargs={"thinking": "Let me search.", "foo": "bar"},
    )
    (sent,) = _llm("openai/gpt-oss-120b")._normalize_chat_messages([message])
    assert "thinking" not in sent.additional_kwargs
    assert sent.additional_kwargs["foo"] == "bar"
    assert message.additional_kwargs["thinking"] == "Let me search."


def test_other_models_still_disable_reasoning_with_none() -> None:
    kwargs = _llm("qwen/qwen3.8-27b")._get_model_kwargs(
        reasoning_effort=ReasoningEffort.NONE
    )
    assert kwargs["reasoning_effort"] == "none"
