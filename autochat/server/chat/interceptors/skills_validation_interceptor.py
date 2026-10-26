from injector import inject, singleton

from autochat.components.engines.chat.interceptors.chat_interceptor import (
    ChatRequestLoopInterceptor,
)
from autochat.components.engines.chat.models.chat_interceptor_context import (
    ChatInterceptorContext,
)
from autochat.components.engines.chat.models.chat_phase import (
    InterceptorPhase,
)
from autochat.components.engines.chat.models.chat_state import (
    SkillsRuntimeCache,
)
from autochat.components.skills.services.skill_service import SkillService
from autochat.server.chat.interceptors.skills_loop_interceptor import (
    find_skill_filter,
)


@singleton
class SkillsValidationInterceptor(ChatRequestLoopInterceptor):
    """Resolve and validate skills once, then cache results in runtime state."""

    @inject
    def __init__(self, skill_service: SkillService) -> None:
        self._skill_service = skill_service

    async def intercept(self, context: ChatInterceptorContext) -> None:
        # Skill validation is request-level: resolve versions once and cache
        # them in the runtime. Resumed executions carry the runtime cache, so
        # there is no need to re-enter this on every BEFORE_ITERATION.
        if context.phase != InterceptorPhase.VALIDATION:
            return

        state = context.state
        skill_filter = find_skill_filter(
            state.input.request.tool_context,
            state.input.context_stack.all_tools(),
        )
        if skill_filter is None:
            return

        if state.runtime.cache.skill is not None:
            # Cache is already prepared for this run.
            context.set_state(state)
            return

        entries = await self._skill_service.recover_versions(skill_filter)
        resources: dict[str, list[str]] = {}
        for entry in entries:
            try:
                resources[
                    entry.skill.id
                ] = await self._skill_service.list_version_files(entry.version)
            except Exception:
                resources[entry.skill.id] = []
        state.runtime.cache.skill = SkillsRuntimeCache(
            entries=entries,
            resources=resources,
        )
        context.set_state(state)
