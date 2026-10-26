from __future__ import annotations

from typing import TYPE_CHECKING

from injector import singleton

from autochat.components.engines.chat.interceptors.chat_interceptor import (
    ChatRequestLoopInterceptor,
)
from autochat.components.engines.chat.models.chat_phase import (
    InterceptorPhase,
)
from autochat.components.tools.remote_execution import (
    ToolExecutionInterceptor,
    ToolExecutionInterceptorContext,
)

if TYPE_CHECKING:
    from autochat.components.engines.chat.models.chat_interceptor_context import (
        ChatInterceptorContext,
    )


@singleton
class NullToolValuesRequestInterceptor(
    ChatRequestLoopInterceptor,
    ToolExecutionInterceptor,
):
    """Strip ``None``-valued kwargs before tool execution."""

    async def intercept(
        self,
        context: ChatInterceptorContext | ToolExecutionInterceptorContext,
    ) -> None:
        if not isinstance(context, ToolExecutionInterceptorContext):
            return
        if context.phase != InterceptorPhase.BEFORE_TOOL:
            return

        context.set_tool_kwargs(
            {
                key: value
                for key, value in context.tool_kwargs.items()
                if value is not None
            }
        )
