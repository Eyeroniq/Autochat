import uuid

import pytest
from fastapi.testclient import TestClient

from autochat.server.ingest import google_sheets
from autochat.server.ingest.google_sheets import (
    SheetLinkError,
    SheetRef,
    download_sheet_csv,
    parse_sheet_url,
)

SHEET_ID = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"


@pytest.mark.parametrize(
    ("url", "gid"),
    [
        (f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid=0", "0"),
        (f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?usp=sharing", "0"),
        (f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?gid=42#gid=42", "42"),
        (
            f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid=1234567",
            "1234567",
        ),
        (f"https://docs.google.com/spreadsheets/d/{SHEET_ID}", "0"),
        (f"  https://docs.google.com/spreadsheets/d/{SHEET_ID}/  ", "0"),
    ],
)
def test_parse_sheet_url(url: str, gid: str) -> None:
    ref = parse_sheet_url(url)

    assert ref == SheetRef(spreadsheet_id=SHEET_ID, gid=gid)
    assert ref.export_url == (
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
    )


@pytest.mark.parametrize(
    "url",
    [
        f"http://docs.google.com/spreadsheets/d/{SHEET_ID}/edit",  # not https
        f"https://evil.example/spreadsheets/d/{SHEET_ID}/edit",
        f"https://docs.google.com.evil.example/spreadsheets/d/{SHEET_ID}/edit",
        "https://docs.google.com/document/d/abcdefghijklmnopqrstuvwxyz/edit",
        "https://docs.google.com/spreadsheets/d/short/edit",
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?gid=abc",
        "file:///etc/passwd",
        "not a url",
    ],
)
def test_parse_sheet_url_rejects(url: str) -> None:
    with pytest.raises(SheetLinkError):
        parse_sheet_url(url)


class FakeResponse:
    def __init__(self, status: int, content_type: str, body: bytes) -> None:
        self.status_code = status
        self.headers = {"content-type": content_type}
        self._body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size: int):
        for start in range(0, len(self._body), chunk_size):
            yield self._body[start : start + chunk_size]


def _fake_get(monkeypatch, response: FakeResponse) -> list[str]:
    calls: list[str] = []

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        calls.append(url)
        return response

    monkeypatch.setattr("requests.get", fake_get)
    return calls


REF = SheetRef(spreadsheet_id=SHEET_ID, gid="0")


def test_download_returns_csv(monkeypatch) -> None:
    calls = _fake_get(
        monkeypatch, FakeResponse(200, "text/csv; charset=utf-8", b"a,b\n1,2\n")
    )

    assert download_sheet_csv(REF, max_bytes=1000) == b"a,b\n1,2\n"
    assert calls == [REF.export_url]


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (
            FakeResponse(200, "text/html; charset=utf-8", b"<html>Sign in</html>"),
            "not public",
        ),
        (FakeResponse(404, "text/html", b"Not found"), "refused"),
        (FakeResponse(200, "text/csv", b"  \n"), "empty"),
        (FakeResponse(200, "text/csv", b"x" * 2000), "larger"),
    ],
)
def test_download_errors(monkeypatch, response: FakeResponse, message: str) -> None:
    _fake_get(monkeypatch, response)

    with pytest.raises(SheetLinkError, match=message):
        download_sheet_csv(REF, max_bytes=1000)


def test_ingest_google_sheet_route(test_client: TestClient, monkeypatch) -> None:
    collection = str(uuid.uuid4())
    monkeypatch.setattr(
        google_sheets,
        "download_sheet_csv",
        lambda ref, max_bytes: b"name,role\nAda,engineer\nGrace,admiral\n",
    )

    response = test_client.post(
        "/v1/artifacts/ingest/google-sheet",
        json={
            "url": f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid=7",
            "collection": collection,
            "name": "crew",
        },
    )

    assert response.status_code == 200, response.text
    doc = response.json()["data"][0]
    assert doc["artifact"] == f"gsheet-{SHEET_ID}-7"
    assert doc["doc_metadata"]["file_name"] == "crew.csv"
    assert doc["doc_metadata"]["source"] == "google_sheets"
    listed = test_client.get(f"/v1/artifacts/list?collection={collection}").json()
    assert any(item["artifact"] == f"gsheet-{SHEET_ID}-7" for item in listed["data"])


def test_ingest_google_sheet_rejects_bad_link(test_client: TestClient) -> None:
    response = test_client.post(
        "/v1/artifacts/ingest/google-sheet",
        json={"url": "https://example.com/sheet.csv"},
    )

    assert response.status_code == 400
    assert "docs.google.com" in response.json()["detail"]
