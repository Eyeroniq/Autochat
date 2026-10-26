from autochat.arq.settings import get_queue_name as build_queue_name
from autochat.settings.settings import Settings

START_CHAT_TASK_NAME = "autochat.chat.start"
RESUME_ITERATION_TASK_NAME = "autochat.chat.resume_iteration"
TOOL_RESUME_TASK_NAME = "autochat.tool.resume"
TOOL_TIMEOUT_TASK_NAME = "autochat.tool.timeout"


def get_queue_name(settings: Settings) -> str:
    return build_queue_name(settings.scheduler.chat.celery_queue)
