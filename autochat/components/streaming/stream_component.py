from injector import inject, singleton

from autochat.components.streaming.providers.stream_service import StreamService
from autochat.components.streaming.registry import _PROVIDERS, register_stream
from autochat.settings.settings import Settings

__all__ = ["StreamComponent", "register_stream"]


@singleton
class StreamComponent:
    stream: StreamService

    @inject
    def __init__(self, settings: Settings) -> None:
        provider = _PROVIDERS.get(settings.stream.broker)
        if provider is None:
            raise ValueError(
                f"Unsupported streaming provider: {settings.stream.broker}"
            )
        self.stream = provider(settings)
