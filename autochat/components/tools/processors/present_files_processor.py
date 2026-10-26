from injector import inject, singleton

from autochat.components.chat.models.chat_config_models import ResolvedChatRequest
from autochat.components.code_execution.base import CodeExecutionSessionConfig
from autochat.components.tools.builders.present_files_tool_builder import (
    PresentFilesToolBuilder,
)
from autochat.components.tools.processors.base import (
    ToolProcessor,
    _is_unresolved_tool,
    _replace_tool,
    _tool_matches,
    session_id_for,
)
from autochat.components.tools.tool_names import PRESENT_FILES_TOOL_NAME
from autochat.server.principal import Principal
from autochat.settings.settings import Settings


@singleton
class PresentFilesProcessor(ToolProcessor):
    @inject
    def __init__(
        self,
        present_files_tool_builder: PresentFilesToolBuilder,
        settings: Settings,
    ) -> None:
        self._builder = present_files_tool_builder
        self._enabled = settings.code_execution.tools.present_files.enabled

    async def intercept(self, request: ResolvedChatRequest) -> bool:
        for tool in request.tool_config.tools:
            if not _is_unresolved_tool(tool):
                continue
            if _tool_matches(tool, PRESENT_FILES_TOOL_NAME):
                if not self._enabled:
                    return _replace_tool(request, tool, [])
                config = CodeExecutionSessionConfig(
                    session_id=session_id_for(request),
                    env=Principal.current().as_env() or {},
                    mounts=request.context.mounts or [],
                )
                return _replace_tool(
                    request,
                    tool,
                    [
                        await self._builder.build_tool(
                            config,
                            name=tool.name or PRESENT_FILES_TOOL_NAME,
                            type=tool.type or PRESENT_FILES_TOOL_NAME + "_v1",
                        )
                    ],
                )
        return False
