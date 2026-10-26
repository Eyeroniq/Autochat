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
from autochat.server.chat.interceptors.null_tool_values_interceptor import (
    NullToolValuesRequestInterceptor,
)
from autochat.server.chat.interceptors.schema_coercing_tool_interceptor import (
    SchemaCoercingToolInterceptor,
)


@singleton
class ConfigureToolRequestInterceptor(ChatRequestLoopInterceptor):
    """Aggregate tool-configuration sub-interceptors into a single step."""

    @inject
    def __init__(
        self,
        null_tool_values_interceptor: NullToolValuesRequestInterceptor,
        schema_coercing_interceptor: SchemaCoercingToolInterceptor,
    ) -> None:
        self._interceptors: list[ChatRequestLoopInterceptor] = [
            null_tool_values_interceptor,
            schema_coercing_interceptor,
        ]

    async def intercept(self, context: ChatInterceptorContext) -> None:
        """Run all tool-configuration interceptors in order."""
        if context.phase != InterceptorPhase.BEFORE_TOOL:
            return

        for interceptor in self._interceptors:
            await interceptor.intercept(context)
