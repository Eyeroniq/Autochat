"""Guest mode through the real app, with auth and guest sessions switched on.

Test settings disable auth, so ``authenticated`` is the always-allow variant;
like ``test_simple_auth.py``, these tests swap in the real check.
"""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from autochat.launcher import create_app
from autochat.server.utils.auth import (
    authenticated,
    secret_or_guest_authentication,
)
from tests.fixtures.fast_api_test_client import inject_global_injector
from tests.fixtures.mock_injector import MockInjector

SECRET = "Basic b3duZXI6cGFzcw=="
GUEST_SETTINGS = {
    "server": {
        "auth": {"enabled": True, "secret": SECRET},
        "guest": {
            "enabled": True,
            "messages_per_session": 2,
            "sessions_per_ip_per_hour": 3,
            "max_tokens": 512,
        },
    }
}

pytestmark = pytest.mark.parametrize(
    "applied_migrations", [GUEST_SETTINGS], indirect=True
)

CHAT_BODY = {
    "messages": [{"role": "user", "content": "hello"}],
    "max_tokens": 64,
}


@pytest.fixture
async def client(applied_migrations: MockInjector) -> AsyncIterator[AsyncClient]:
    app = create_app(applied_migrations.test_injector)
    app.middleware("http")(inject_global_injector(applied_migrations))
    app.dependency_overrides[authenticated] = secret_or_guest_authentication
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield http


async def _guest_headers(client: AsyncClient) -> dict[str, str]:
    response = await client.post("/v1/guest/session")
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


async def test_status_reports_guest_mode(client: AsyncClient) -> None:
    response = await client.get("/v1/guest/status")

    assert response.status_code == 200
    assert response.json()["enabled"] is True


async def test_session_needs_no_credentials(client: AsyncClient) -> None:
    response = await client.post("/v1/guest/session")

    assert response.status_code == 200
    body = response.json()
    assert body["token"].startswith("autochat_guest_")
    assert body["messages_per_session"] == 2
    assert body["max_tokens"] == 512


async def test_requests_without_credentials_are_rejected(client: AsyncClient) -> None:
    response = await client.get("/v1/models")

    assert response.status_code == 401


async def test_guest_can_read(client: AsyncClient) -> None:
    headers = await _guest_headers(client)

    assert (await client.get("/v1/models", headers=headers)).status_code == 200
    listed = await client.get("/v1/artifacts/list?collection=demo", headers=headers)
    assert listed.status_code == 200


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/v1/artifacts/ingest"),
        ("POST", "/v1/artifacts/ingest/google-sheet"),
        ("POST", "/v1/artifacts/delete"),
        ("GET", "/v1/usage/summary"),
        ("POST", "/v1/skills"),
    ],
)
async def test_guest_cannot_change_or_inspect(
    client: AsyncClient, method: str, path: str
) -> None:
    headers = await _guest_headers(client)

    response = await client.request(method, path, headers=headers, json={})

    assert response.status_code == 403


async def test_owner_secret_still_works(client: AsyncClient) -> None:
    response = await client.get("/v1/usage/summary", headers={"Authorization": SECRET})

    assert response.status_code == 200


async def test_forged_guest_token_is_rejected(client: AsyncClient) -> None:
    headers = {"Authorization": "Bearer autochat_guest_abc.9999999999.deadbeef"}

    assert (await client.get("/v1/models", headers=headers)).status_code == 401


async def test_guest_chat_policy_is_enforced(client: AsyncClient) -> None:
    headers = await _guest_headers(client)

    too_long = await client.post(
        "/v1/messages", headers=headers, json={**CHAT_BODY, "max_tokens": 4096}
    )
    with_mcp = await client.post(
        "/v1/messages",
        headers=headers,
        json={**CHAT_BODY, "mcp_servers": [{"url": "http://169.254.169.254"}]},
    )

    assert too_long.status_code == 403
    assert "512" in too_long.json()["detail"]
    assert with_mcp.status_code == 403


async def test_guest_message_limit(client: AsyncClient) -> None:
    headers = await _guest_headers(client)

    for _ in range(2):
        response = await client.post("/v1/messages", headers=headers, json=CHAT_BODY)
        assert response.status_code == 200, response.text
    blocked = await client.post("/v1/messages", headers=headers, json=CHAT_BODY)

    assert blocked.status_code == 429


async def test_session_creation_is_rate_limited_per_ip(client: AsyncClient) -> None:
    for _ in range(3):
        assert (await client.post("/v1/guest/session")).status_code == 200
    blocked = await client.post("/v1/guest/session")

    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
