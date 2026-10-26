import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from autochat.server.usage.usage_middleware import UsageMiddleware
from autochat.server.usage.usage_store import UsageRecord, UsageStore


class FakeStore:
    enabled = True

    def __init__(self) -> None:
        self.records: list[UsageRecord] = []

    def record(self, record: UsageRecord) -> None:
        self.records.append(record)


class FakeInjector:
    def __init__(self, store: FakeStore) -> None:
        self.store = store

    def get(self, cls: type) -> Any:
        assert cls is UsageStore
        return self.store


def _sse(*events: dict) -> list[bytes]:
    return [f"data: {json.dumps(event)}\n\n".encode() for event in events]


def _app(status: int, content_type: str, chunks: list[bytes]):
    async def app(scope, receive, send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-type", content_type.encode())],
            }
        )
        for chunk in chunks:
            await send({"type": "http.response.body", "body": chunk, "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    return app


async def _call(app, path: str = "/v1/messages", method: str = "POST", headers=()):
    store = FakeStore()
    middleware = UsageMiddleware(app, root_injector=FakeInjector(store))
    sent: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    scope = {"type": "http", "method": method, "path": path, "headers": list(headers)}
    await middleware(scope, receive, send)
    return store, sent


async def test_streamed_response_usage() -> None:
    # Split one event across two chunks to exercise line buffering.
    chunks = _sse(
        {"type": "message_start", "message": {"model": "llama-3", "usage": {}}},
        {"type": "content_block_delta", "delta": {"text": "Hi"}},
        {"type": "message_delta", "usage": {"input_tokens": 432, "output_tokens": 89}},
    )
    split = chunks[2][:20], chunks[2][20:]
    app = _app(200, "text/event-stream", [chunks[0], chunks[1], *split])

    store, sent = await _call(app)

    (record,) = store.records
    assert record.stream is True
    assert record.model == "llama-3"
    assert (record.input_tokens, record.output_tokens) == (432, 89)
    assert record.first_token_ms is not None
    assert record.first_token_ms <= record.latency_ms
    assert record.role == "owner"
    # The response itself passes through unchanged.
    assert b"".join(m.get("body", b"") for m in sent[1:]) == b"".join(chunks)


async def test_json_response_usage_and_guest_role() -> None:
    body = json.dumps(
        {"model": "llama-3", "usage": {"input_tokens": 10, "output_tokens": 5}}
    ).encode()
    app = _app(200, "application/json", [body[:7], body[7:]])

    store, _ = await _call(
        app, headers=[(b"authorization", b"Bearer autochat_guest_x.1.y")]
    )

    (record,) = store.records
    assert record.stream is False
    assert (record.input_tokens, record.output_tokens) == (10, 5)
    assert record.first_token_ms == record.latency_ms
    assert record.role == "guest"


async def test_errors_are_recorded() -> None:
    app = _app(429, "application/json", [b'{"detail": "limit"}'])

    store, _ = await _call(app)

    assert store.records[0].status == 429


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/v1/messages"),
        ("POST", "/v1/messages/count_tokens"),
        ("POST", "/v1/models"),
    ],
)
async def test_other_requests_are_ignored(method: str, path: str) -> None:
    store, _ = await _call(_app(200, "application/json", [b"{}"]), path, method)

    assert store.records == []


@pytest.mark.parametrize(
    "test_client",
    [{"usage": {"enabled": True, "database_path": "usage/test-usage.sqlite"}}],
    indirect=True,
)
def test_chat_requests_show_up_in_summary(test_client: TestClient) -> None:
    before = test_client.get("/v1/usage/summary?days=1").json()["requests"]

    response = test_client.post(
        "/v1/messages",
        json={"messages": [{"role": "user", "content": "hello"}], "max_tokens": 16},
    )
    summary = test_client.get("/v1/usage/summary?days=1").json()

    assert response.status_code == 200, response.text
    assert summary["enabled"] is True
    assert summary["requests"] == before + 1
    assert summary["recent"][0]["status"] == 200
    assert summary["recent"][0]["latency_ms"] > 0
