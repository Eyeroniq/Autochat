from typing import Any

from llama_index.core.llms import LLM

from autochat.components.llm.factories.base import LLMFactory
from autochat.components.llm.tokenizers.tokenizer_base import TokenizerBase
from autochat.components.model_discovery.url_utils import is_openai_api_base
from autochat.settings.settings import LLMModelConfig, Settings
from autochat.utils.dependencies import format_missing_dependency_message


class OpenAIResponsesLLMLoader:
    """Mixin providing lazy-loaded access to PatchedOpenAIResponsesLLM."""

    @staticmethod
    def _load_patched_openai_responses() -> type[Any]:
        try:
            from autochat.components.llm.custom.openairesponses import (
                PatchedOpenAIResponsesLLM,
            )

            return PatchedOpenAIResponsesLLM
        except ImportError as e:
            raise ImportError(
                format_missing_dependency_message(
                    "OpenAI Responses LLM",
                    extras="llm-openai",
                )
            ) from e


class OpenAIGenericResponsesFactory(LLMFactory):
    """Responses API router.

    Routes to OpenAIResponsesFactory for api.openai.com,
    otherwise delegates to OpenAILikeResponsesFactory.
    """

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.openai_settings = settings.openai

    def _create_llm(
        self, model_config: LLMModelConfig, tokenizer: TokenizerBase | None = None
    ) -> tuple[LLM, str | None]:
        if is_openai_api_base(self.openai_settings.api_base):
            from autochat.components.llm.factories.responses.openai import (
                OpenAIResponsesFactory,
            )

            return OpenAIResponsesFactory(self.settings)._create_llm(
                model_config,
                tokenizer=tokenizer,
            )

        from autochat.components.llm.factories.responses.openailike import (
            OpenAILikeResponsesFactory,
        )

        return OpenAILikeResponsesFactory(self.settings)._create_llm(
            model_config,
            tokenizer=tokenizer,
        )
