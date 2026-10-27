from fastapi.testclient import TestClient


def test_ui_path_still_serves_bundled_ui_index(test_client: TestClient) -> None:
    response = test_client.get("/ui/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    # Same origin as the page, so it works on any host, port or domain.
    assert 'const DEFAULT_BASE_URL = window.location.origin + "";' in response.text
    assert "127.0.0.1:8080" not in response.text.split("DEFAULT_BASE_URL", 1)[1][:80]


def test_ui_path_without_trailing_slash_redirects_to_index(
    test_client: TestClient,
) -> None:
    response = test_client.get("/ui", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/ui/"
