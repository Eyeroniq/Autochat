import os
from typing import Any

from autochat.di import (
    clean_global_injector,
    get_global_injector,
    set_global_injector,
)
from autochat.eager_loading import warm
from autochat.initialize import initialize_globals, initialize_observability
from autochat.settings.settings import settings


async def startup(ctx: dict[Any, Any]) -> None:
    current_settings = settings()
    initialize_globals()
    initialize_observability(current_settings)
    injector = get_global_injector(allow_to_generate_new_injectors=True)
    set_global_injector(injector)
    warm_profile = os.environ.get("AUTOCHAT_WORKER_WARM_PROFILE", "").strip()
    if warm_profile:
        warm(injector, profile=warm_profile)
    ctx["injector"] = injector


async def shutdown(ctx: dict[Any, Any]) -> None:
    del ctx
    await clean_global_injector()
