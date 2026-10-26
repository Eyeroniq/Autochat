from unittest.mock import MagicMock

import pytest

from autochat.arq.runner import (
    _keep_result_seconds,
    _poll_delay,
    _queue_name,
    _task_packages,
)


def test_task_packages_are_loaded_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AUTOCHAT_ARQ_TASK_PACKAGES",
        "autochat.arq.tasks.chat, custom.tasks ",
    )

    assert _task_packages() == (
        "autochat.arq.tasks.chat",
        "custom.tasks",
    )


def test_task_packages_are_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTOCHAT_ARQ_TASK_PACKAGES", raising=False)

    with pytest.raises(ValueError, match="AUTOCHAT_ARQ_TASK_PACKAGES"):
        _task_packages()


def test_queue_is_loaded_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOCHAT_ARQ_QUEUE", "chat")

    assert _queue_name() == "autochat:arq:queue:chat"


def test_queue_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTOCHAT_ARQ_QUEUE", raising=False)

    with pytest.raises(ValueError, match="AUTOCHAT_ARQ_QUEUE"):
        _queue_name()


def test_queue_must_match_scheduler_for_worker_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTOCHAT_ARQ_QUEUE", "wrong-chat")
    monkeypatch.setenv("AUTOCHAT_STATEFUL_WORKER_TYPE", "chat")
    current_settings = MagicMock()
    current_settings.scheduler.chat.celery_queue = "chat"

    with pytest.raises(ValueError, match="does not match scheduler queue"):
        _queue_name(current_settings)


def test_queue_matches_scheduler_for_worker_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTOCHAT_ARQ_QUEUE", "chat")
    monkeypatch.setenv("AUTOCHAT_STATEFUL_WORKER_TYPE", "chat")
    current_settings = MagicMock()
    current_settings.scheduler.chat.celery_queue = "chat"

    assert _queue_name(current_settings) == "autochat:arq:queue:chat"


def test_keep_result_outlives_tool_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTOCHAT_ARQ_KEEP_RESULT", raising=False)
    current_settings = MagicMock()
    current_settings.scheduler.chat.callback_timeout_seconds = 120

    assert _keep_result_seconds(current_settings) == 420


def test_keep_result_can_be_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOCHAT_ARQ_KEEP_RESULT", "900")

    assert _keep_result_seconds(MagicMock()) == 900


def test_poll_delay_defaults_below_arq_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTOCHAT_ARQ_POLL_DELAY", raising=False)

    assert _poll_delay() == 0.05


def test_poll_delay_can_be_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOCHAT_ARQ_POLL_DELAY", "0.2")

    assert _poll_delay() == 0.2
