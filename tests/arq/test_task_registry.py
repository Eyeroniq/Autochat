from autochat.arq.task_registry import get_task_packages
from autochat.arq.tasks import autodiscover_registered_tasks


def test_explicit_task_packages_replace_defaults() -> None:
    assert get_task_packages("autochat.arq.tasks.chat") == ("autochat.arq.tasks.chat",)


def test_chat_package_discovers_only_chat_tasks() -> None:
    assert {
        task.name for task in autodiscover_registered_tasks("autochat.arq.tasks.chat")
    } == {
        "autochat.chat.resume_iteration",
        "autochat.chat.start",
        "autochat.tool.resume",
        "autochat.tool.timeout",
    }
