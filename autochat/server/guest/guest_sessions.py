"""Signed guest tokens and the in-memory limits attached to them.

A guest token is ``autochat_guest_<session_id>.<expires_at>.<signature>``, where the
signature is an HMAC over the session id and expiry keyed from the server's
auth secret. Tokens are stateless; only the usage counters live in memory, so
they reset on restart and are not shared between worker processes.
"""

import hashlib
import hmac
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from injector import inject, singleton

from autochat.settings.settings import GuestSettings, Settings

GUEST_TOKEN_PREFIX = "autochat_guest_"


class GuestLimitError(Exception):
    """A guest limit was reached. ``retry_after`` is in seconds when known."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


@dataclass(frozen=True)
class GuestSession:
    session_id: str
    expires_at: int


class SlidingWindowLimiter:
    """Allow at most ``limit`` hits per key within ``window_seconds``."""

    def __init__(
        self, limit: int, window_seconds: int, clock: Callable[[], float]
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> int | None:
        """Record a hit; return ``None`` if allowed, else seconds until a slot frees."""
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - self._window:
                hits.popleft()
            if len(hits) >= self._limit:
                return max(1, int(hits[0] + self._window - now))
            hits.append(now)
            return None


@singleton
class GuestSessionManager:
    @inject
    def __init__(self, settings: Settings) -> None:
        self._settings = settings.server.guest
        self._key = hashlib.sha256(
            b"autochat-guest:" + settings.server.auth.secret.encode()
        ).digest()
        # Replaceable in tests.
        self.clock: Callable[[], float] = time.time
        self._session_limiter = SlidingWindowLimiter(
            self._settings.sessions_per_ip_per_hour, 3600, lambda: self.clock()
        )
        self._lock = threading.Lock()
        # session_id -> (messages used, expires_at)
        self._messages_used: dict[str, tuple[int, int]] = {}
        self._day = ""
        self._day_count = 0

    @property
    def settings(self) -> GuestSettings:
        return self._settings

    def create_session(self, client_ip: str) -> tuple[str, GuestSession]:
        retry_after = self._session_limiter.hit(client_ip)
        if retry_after is not None:
            raise GuestLimitError(
                "Too many guest sessions from this address. Try again later.",
                retry_after,
            )
        session = GuestSession(
            session_id=secrets.token_urlsafe(12),
            expires_at=int(self.clock()) + self._settings.session_ttl_minutes * 60,
        )
        self._prune_expired()
        token = (
            f"{GUEST_TOKEN_PREFIX}{session.session_id}.{session.expires_at}."
            f"{self._sign(session.session_id, session.expires_at)}"
        )
        return token, session

    def verify(self, token: str) -> GuestSession | None:
        """Return the session for a valid, unexpired token, else ``None``."""
        if not token.startswith(GUEST_TOKEN_PREFIX):
            return None
        try:
            session_id, expires_raw, signature = token[len(GUEST_TOKEN_PREFIX) :].split(
                "."
            )
            expires_at = int(expires_raw)
        except ValueError:
            return None
        if not hmac.compare_digest(signature, self._sign(session_id, expires_at)):
            return None
        if expires_at <= self.clock():
            return None
        return GuestSession(session_id=session_id, expires_at=expires_at)

    def messages_remaining(self, session: GuestSession) -> int:
        with self._lock:
            used, _ = self._messages_used.get(session.session_id, (0, 0))
        return max(0, self._settings.messages_per_session - used)

    def consume_message(self, session: GuestSession) -> int:
        """Count one chat message; return how many the session has left."""
        with self._lock:
            now = datetime.fromtimestamp(self.clock(), tz=UTC)
            today = now.strftime("%Y-%m-%d")
            if today != self._day:
                self._day, self._day_count = today, 0
            used, _ = self._messages_used.get(session.session_id, (0, 0))
            if used >= self._settings.messages_per_session:
                raise GuestLimitError(
                    "This guest session has used all of its messages. "
                    "Reload the page to start a new one."
                )
            if self._day_count >= self._settings.daily_message_limit:
                midnight = (now + timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                raise GuestLimitError(
                    "The demo has reached today's guest message limit. "
                    "Please come back tomorrow.",
                    int((midnight - now).total_seconds()),
                )
            self._day_count += 1
            self._messages_used[session.session_id] = (used + 1, session.expires_at)
            return self._settings.messages_per_session - used - 1

    def _sign(self, session_id: str, expires_at: int) -> str:
        message = f"{session_id}.{expires_at}".encode()
        return hmac.new(self._key, message, hashlib.sha256).hexdigest()

    def _prune_expired(self) -> None:
        now = self.clock()
        with self._lock:
            for session_id, (_, expires_at) in list(self._messages_used.items()):
                if expires_at <= now:
                    del self._messages_used[session_id]
