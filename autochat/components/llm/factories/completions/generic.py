from llama_index.core.llms import LLM

from autochat.components.llm.factories.base import LLMFactory
from autochat.components.llm.tokenizers.tokenizer_base import TokenizerBase
from autochat.components.model_discovery.url_utils import is_openai_api_base
from autochat.settings.settings import LLMModelConfig, Settings


class OpenAIGenericCompletionsFactory(LLMFactory):
    """Chat Completions router.

    Routes to OpenAICompletionsFactory for api.openai.com,
    otherwise delegates to OpenAILikeCompletionsFactory.
    """

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.openai_settings = settings.openai

    def _create_llm(
        self, model_config: LLMModelConfig, tokenizer: TokenizerBase | None = None
    ) -> tuple[LLM, str | None]:
        if is_openai_api_base(self.openai_settings.api_base):
            from autochat.components.llm.factories.completions.openai import (
                OpenAICompletionsFactory,
            )

            return OpenAICompletionsFactory(self.settings)._create_llm(
                model_config,
                tokenizer=tokenizer,
            )

        from autochat.components.llm.factories.completions.openailike import (
            OpenAILikeCompletionsFactory,
        )

        return OpenAILikeCompletionsFactory(self.settings)._create_llm(
            model_config,
            tokenizer=tokenizer,
        )
