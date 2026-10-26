from injector import inject, singleton

from autochat.components.chat.models.chat_config_models import ResolvedChatRequest
from autochat.components.code_execution.base import CodeExecutionSessionConfig
from autochat.components.tools.builders.bash_tool_builder import BashToolBuilder
from autochat.components.tools.processors.base import (
    ToolProcessor,
    _is_unresolved_tool,
    _replace_tool,
    _tool_matches,
    session_id_for,
)
from autochat.components.tools.tool_names import (
    BASH_CODE_EXECUTION_TOOL_NAME,
    BASH_TOOL_NAME,
)
from autochat.server.principal import Principal
from autochat.settings.settings import Settings


@singleton
class BashProcessor(ToolProcessor):
    @inject
    def __init__(
        self,
        bash_tool_builder: BashToolBuilder,
        settings: Settings,
    ) -> None:
        self._bash_builder = bash_tool_builder
        self._enabled = settings.code_execution.tools.bash.enabled

    async def intercept(self, request: ResolvedChatRequest) -> bool:
        for tool in request.tool_config.tools:
            if not _tool_matches(
                tool, BASH_TOOL_NAME, BASH_CODE_EXECUTION_TOOL_NAME
            ) or not _is_unresolved_tool(tool):
                continue
            if not self._enabled:
                return _replace_tool(request, tool, [])

            config = CodeExecutionSessionConfig(
                session_id=session_id_for(request),
                env=Principal.current().as_env() or {},
                mounts=request.context.mounts or [],
            )
            resolved = await self._bash_builder.build_tool(
                config,
                name=tool.name or BASH_CODE_EXECUTION_TOOL_NAME,
                type=tool.type or BASH_CODE_EXECUTION_TOOL_NAME + "_v1",
            )
            return _replace_tool(request, tool, [resolved])
        return False
