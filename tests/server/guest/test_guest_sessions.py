from types import SimpleNamespace

import pytest

from autochat.server.guest.guest_sessions import (
    GUEST_TOKEN_PREFIX,
    GuestLimitError,
    GuestSessionManager,
    SlidingWindowLimiter,
)
from autochat.settings.settings import AuthSettings, GuestSettings

START = 1_700_000_000.0  # 2023-11-14T22:13:20Z


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> float:
        return self.now


def _manager(
    clock: Clock, secret: str = "Basic s3cret", **guest
) -> GuestSessionManager:
    settings = SimpleNamespace(
        server=SimpleNamespace(
            auth=AuthSettings(enabled=True, secret=secret),
            guest=GuestSettings(enabled=True, **guest),
        )
    )
    manager = GuestSessionManager(settings)
    manager.clock = clock
    return manager


def test_token_round_trip() -> None:
    clock = Clock()
    manager = _manager(clock, session_ttl_minutes=30)

    token, session = manager.create_session("10.0.0.1")

    assert token.startswith(GUEST_TOKEN_PREFIX)
    assert session.expires_at == int(START) + 30 * 60
    assert manager.verify(token) == session


@pytest.mark.parametrize("part", [0, 1, 2])
def test_tampered_token_is_rejected(part: int) -> None:
    manager = _manager(Clock())
    token, _ = manager.create_session("10.0.0.1")
    pieces = token[len(GUEST_TOKEN_PREFIX) :].split(".")
    pieces[part] = pieces[part][:-1] + ("0" if pieces[part][-1] != "0" else "1")

    assert manager.verify(GUEST_TOKEN_PREFIX + ".".join(pieces)) is None


@pytest.mark.parametrize(
    "token", ["", "Basic abc", "autochat_guest_", "autochat_guest_a.b"]
)
def test_malformed_token_is_rejected(token: str) -> None:
    assert _manager(Clock()).verify(token) is None


def test_token_signed_with_another_secret_is_rejected() -> None:
    clock = Clock()
    token, _ = _manager(clock, secret="Basic one").create_session("10.0.0.1")

    assert _manager(clock, secret="Basic two").verify(token) is None


def test_expired_token_is_rejected() -> None:
    clock = Clock()
    manager = _manager(clock, session_ttl_minutes=1)
    token, _ = manager.create_session("10.0.0.1")

    clock.now += 61

    assert manager.verify(token) is None


def test_session_message_limit() -> None:
    manager = _manager(Clock(), messages_per_session=2)
    _, session = manager.create_session("10.0.0.1")

    assert manager.consume_message(session) == 1
    assert manager.consume_message(session) == 0
    with pytest.raises(GuestLimitError):
        manager.consume_message(session)
    assert manager.messages_remaining(session) == 0


def test_daily_limit_is_shared_by_all_guests_and_resets_next_day() -> None:
    clock = Clock()
    manager = _manager(clock, daily_message_limit=2, sessions_per_ip_per_hour=10)
    sessions = [manager.create_session("10.0.0.1")[1] for _ in range(3)]

    manager.consume_message(sessions[0])
    manager.consume_message(sessions[1])
    with pytest.raises(GuestLimitError) as error:
        manager.consume_message(sessions[2])
    assert error.value.retry_after is not None
    assert error.value.retry_after > 0

    clock.now += 86400
    manager.consume_message(sessions[2])


def test_sessions_per_ip_limit() -> None:
    clock = Clock()
    manager = _manager(clock, sessions_per_ip_per_hour=2)
    manager.create_session("10.0.0.1")
    manager.create_session("10.0.0.1")

    with pytest.raises(GuestLimitError) as error:
        manager.create_session("10.0.0.1")
    assert error.value.retry_after == 3600

    # Other addresses are unaffected, and the window slides.
    manager.create_session("10.0.0.2")
    clock.now += 3600
    manager.create_session("10.0.0.1")


def test_sliding_window_frees_oldest_slot_first() -> None:
    clock = Clock()
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60, clock=clock)

    assert limiter.hit("k") is None
    clock.now += 30
    assert limiter.hit("k") is None
    assert limiter.hit("k") == 30
    clock.now += 30
    assert limiter.hit("k") is None
