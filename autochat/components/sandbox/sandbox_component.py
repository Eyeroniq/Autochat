from injector import inject, singleton

from autochat.components.sandbox.base import SandboxSession
from autochat.components.sandbox.mount import Mount
from autochat.components.sandbox.registry import SandboxProviderRegistry
from autochat.settings.settings import Settings


@singleton
class SandboxComponent:
    @inject
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._registry = SandboxProviderRegistry(settings)

    async def create_session(
        self,
        user_id: str | None = None,
        timeout: int | None = None,
        bundle_specs: list[Mount] | None = None,
        env: dict[str, str] | None = None,
    ) -> SandboxSession | None:
        provider_name = self._settings.sandbox.provider
        if provider_name is None:
            return None

        provider = self._registry.get_provider(provider_name)
        return await provider.create_session(
            user_id=user_id,
            timeout=timeout,
            bundle_specs=bundle_specs,
            env=env,
        )
