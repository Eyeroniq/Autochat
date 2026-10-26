from typing import cast

from llama_index.core.llms import LLM

from autochat.components.llm.factories.base import LLMFactory
from autochat.components.llm.factories.responses.generic import (
    OpenAIResponsesLLMLoader,
)
from autochat.components.llm.tokenizers.tokenizer_base import TokenizerBase
from autochat.settings.settings import LLMModelConfig, Settings


class OpenAIResponsesFactory(OpenAIResponsesLLMLoader, LLMFactory):
    """Responses API factory for the real OpenAI endpoint (api.openai.com)."""

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.openai_settings = settings.openai

    def _create_llm(
        self, model_config: LLMModelConfig, tokenizer: TokenizerBase | None = None
    ) -> tuple[LLM, str | None]:
        PatchedOpenAIResponsesLLM = self._load_patched_openai_responses()

        llm = cast(
            LLM,
            PatchedOpenAIResponsesLLM(
                model=model_config.name,
                api_key=self.openai_settings.api_key,
                api_base=self.openai_settings.api_base or "https://api.openai.com/v1",
            ),
        )

        return llm, model_config.alias
