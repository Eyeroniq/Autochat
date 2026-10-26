from collections.abc import Callable

from autochat.components.embedding.factories.base import EmbeddingFactory
from autochat.components.embedding.factories.mock import MockEmbeddingFactory
from autochat.components.embedding.factories.openai import OpenAIEmbeddingFactory
from autochat.settings.settings import Settings

EmbeddingProvider = type[EmbeddingFactory] | Callable[[Settings], EmbeddingFactory]

_PROVIDERS: dict[str, EmbeddingProvider] = {
    "openai": OpenAIEmbeddingFactory,
    "mock": MockEmbeddingFactory,
}


def register_embedding(mode: str, provider: EmbeddingProvider) -> None:
    _PROVIDERS[mode] = provider


class EmbeddingFactoryRegistry:
    """Registry of embedding factories by mode."""

    def __init__(self, settings: Settings):
        self._factories: dict[str, EmbeddingFactory] = {
            mode: provider(settings) for mode, provider in _PROVIDERS.items()
        }

    def get_factory(self, mode: str) -> EmbeddingFactory:
        if mode not in self._factories:
            available = ", ".join(sorted(self._factories)) or "none"
            raise ValueError(
                f"Embedding mode '{mode}' is not supported. Available: {available}"
            )
        return self._factories[mode]
