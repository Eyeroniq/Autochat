import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    "test_client",
    [{"server": {"auth": {"enabled": True, "secret": "Basic b3duZXI6cGFzcw=="}}}],
    indirect=True,
)
def test_guest_mode_is_off_by_default(test_client: TestClient) -> None:
    assert test_client.get("/v1/guest/status").json()["enabled"] is False
    assert test_client.post("/v1/guest/session").status_code == 404


@pytest.mark.parametrize(
    "test_client", [{"server": {"guest": {"enabled": True}}}], indirect=True
)
def test_guest_mode_needs_auth(test_client: TestClient) -> None:
    # Test settings disable auth; the guest flag alone must not open sessions.
    assert test_client.get("/v1/guest/status").json()["enabled"] is False
    assert test_client.post("/v1/guest/session").status_code == 404
