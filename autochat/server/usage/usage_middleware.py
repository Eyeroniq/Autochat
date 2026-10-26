"""Measure `POST /v1/messages` from the outside: latency, first token, tokens.

Pure ASGI (see ``RequestContextMiddleware``) so streamed responses pass through
untouched; the tracker only reads a copy of each chunk. Token counts come from
the ``usage`` the API already reports, in the JSON body or in the
``message_start`` / ``message_delta`` stream events.
"""

import asyncio
import json
import logging
import time
from typing import Any

from injector import Injector
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from autochat.server.guest.guest_sessions import GUEST_TOKEN_PREFIX
from autochat.server.usage.usage_store import UsageRecord, UsageStore

logger = logging.getLogger(__name__)

CHAT_PATH = "/v1/messages"
_MAX_JSON_BYTES = 5 * 1024 * 1024


class _ResponseTracker:
    def __init__(self) -> None:
        self.started = time.perf_counter()
        self.status = 500
        self.stream = False
        self.model: str | None = None
        self.input_tokens: int | None = None
        self.output_tokens: int | None = None
        self.first_token_at: float | None = None
        self._buffer = b""
        self._json_overflow = False

    def observe(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            self.status = message["status"]
            headers = dict(message.get("headers") or [])
            content_type = headers.get(b"content-type", b"").decode("latin-1")
            self.stream = content_type.startswith("text/event-stream")
        elif message["type"] == "http.response.body":
            chunk = message.get("body") or b""
            if self.stream:
                self._read_events(chunk)
            elif not self._json_overflow:
                self._buffer += chunk
                self._json_overflow = len(self._buffer) > _MAX_JSON_BYTES

    def _read_events(self, chunk: bytes) -> None:
        self._buffer += chunk
        *lines, self._buffer = self._buffer.split(b"\n")
        for line in lines:
            if not line.startswith(b"data:"):
                continue
            try:
                event = json.loads(line[5:])
            except ValueError:
                continue
            if isinstance(event, dict):
                self._read_event(event)

    def _read_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == "message_start":
            message = event.get("message") or {}
            self.model = message.get("model") or self.model
            self._read_usage(message.get("usage"))
        elif event_type == "content_block_delta" and self.first_token_at is None:
            self.first_token_at = time.perf_counter()
        elif event_type == "message_delta":
            self._read_usage(event.get("usage"))

    def _read_usage(self, usage: Any) -> None:
        if not isinstance(usage, dict):
            return
        if isinstance(usage.get("input_tokens"), int):
            self.input_tokens = usage["input_tokens"]
        if isinstance(usage.get("output_tokens"), int):
            self.output_tokens = usage["output_tokens"]

    def finish(self, role: str) -> UsageRecord:
        ended = time.perf_counter()
        if not self.stream and not self._json_overflow and self._buffer:
            try:
                body = json.loads(self._buffer)
            except ValueError:
                body = None
            if isinstance(body, dict):
                self.model = body.get("model") or self.model
                self._read_usage(body.get("usage"))
        first_token = self.first_token_at if self.stream else ended
        return UsageRecord(
            ts=time.time(),
            role=role,
            model=self.model,
            status=self.status,
            stream=self.stream,
            latency_ms=round((ended - self.started) * 1000, 1),
            first_token_ms=(
                round((first_token - self.started) * 1000, 1) if first_token else None
            ),
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
        )


def _role(scope: Scope) -> str:
    for name, value in scope.get("headers") or []:
        if name == b"authorization":
            _, _, token = value.decode("latin-1").partition(" ")
            return "guest" if token.strip().startswith(GUEST_TOKEN_PREFIX) else "owner"
    return "owner"


class UsageMiddleware:
    def __init__(self, app: ASGIApp, root_injector: Injector) -> None:
        self.app = app
        self.root_injector = root_injector

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or not scope.get("path", "").endswith(CHAT_PATH)
        ):
            await self.app(scope, receive, send)
            return

        app_state = getattr(scope.get("app"), "state", None)
        injector = getattr(app_state, "injector", None) or self.root_injector
        store = injector.get(UsageStore)
        if not store.enabled:
            await self.app(scope, receive, send)
            return

        tracker = _ResponseTracker()

        async def send_and_track(message: Message) -> None:
            tracker.observe(message)
            await send(message)

        try:
            await self.app(scope, receive, send_and_track)
        finally:
            try:
                await asyncio.to_thread(store.record, tracker.finish(_role(scope)))
            except Exception:
                logger.warning("Could not record chat usage", exc_info=True)
