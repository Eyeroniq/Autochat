"""Ingest a public Google Sheet tab as a CSV document.

The sheet is downloaded through Google's CSV export URL and then handed to the
regular ingestion pipeline as a ``.csv`` file, so it is chunked, embedded and
queried exactly like an uploaded CSV. Only ``docs.google.com`` links are
accepted, which keeps the server from being pointed at arbitrary hosts.
"""

import asyncio
import base64
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from autochat.components.ingestion.ingestion_scheduler import (
    IngestionSchedulerFactory,
)
from autochat.server.ingest.ingest_router import IngestBody, IngestResponse
from autochat.server.utils.artifact_input import FileArtifact
from autochat.server.utils.auth import authenticated
from autochat.server.utils.http_disconnect import cancel_on_http_disconnect
from autochat.settings.settings import Settings

_SHEET_PATH = re.compile(r"^/spreadsheets/d/([A-Za-z0-9_-]{20,})(?:/|$)")
_GID = re.compile(r"gid=(\d+)")
DOWNLOAD_TIMEOUT_SECONDS: tuple[float, float] = (10.0, 60.0)

google_sheets_router = APIRouter(
    prefix="/v1/artifacts",
    dependencies=[Depends(authenticated)],
    tags=["Artifacts"],
    responses={401: {"description": "Unauthorized"}},
)


class SheetLinkError(ValueError):
    """The link is not a usable Google Sheets link, or the sheet is not public."""


@dataclass(frozen=True)
class SheetRef:
    spreadsheet_id: str
    gid: str

    @property
    def export_url(self) -> str:
        return (
            f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}"
            f"/export?format=csv&gid={self.gid}"
        )

    @property
    def sheet_url(self) -> str:
        return (
            f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}"
            f"/edit#gid={self.gid}"
        )


def parse_sheet_url(url: str) -> SheetRef:
    """Read the spreadsheet id and tab (``gid``) from a Google Sheets link."""
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or parsed.hostname != "docs.google.com":
        raise SheetLinkError("Use a https://docs.google.com/spreadsheets/... link.")
    match = _SHEET_PATH.match(parsed.path)
    if not match:
        raise SheetLinkError("That link does not point to a Google Sheet.")
    gid = parse_qs(parsed.query).get("gid", [None])[0]
    if gid is None:
        fragment_gid = _GID.search(parsed.fragment)
        gid = fragment_gid.group(1) if fragment_gid else "0"
    if not gid.isdigit():
        raise SheetLinkError("The sheet tab id (gid) in the link is not valid.")
    return SheetRef(spreadsheet_id=match.group(1), gid=gid)


def download_sheet_csv(ref: SheetRef, max_bytes: int) -> bytes:
    import requests

    with requests.get(
        ref.export_url,
        allow_redirects=True,
        timeout=DOWNLOAD_TIMEOUT_SECONDS,
        stream=True,
    ) as response:
        if response.status_code in (401, 403, 404):
            raise SheetLinkError(
                "Google refused the download. Share the sheet as "
                "'Anyone with the link can view' and check the link."
            )
        response.raise_for_status()
        # A private sheet redirects to the Google sign-in page instead of a CSV.
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("text/csv"):
            raise SheetLinkError(
                "This sheet is not public. Share it as "
                "'Anyone with the link can view' and try again."
            )
        data = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            data += chunk
            if len(data) > max_bytes:
                raise SheetLinkError(
                    f"The sheet is larger than the {max_bytes} byte limit."
                )
    if not data.strip():
        raise SheetLinkError("The sheet tab is empty.")
    return bytes(data)


class GoogleSheetIngestBody(BaseModel):
    url: str = Field(
        ...,
        description="Link to a Google Sheet shared as 'Anyone with the link can view'. "
        "The tab in the link (gid) is imported; the first tab if there is none.",
        examples=["https://docs.google.com/spreadsheets/d/<id>/edit#gid=0"],
    )
    collection: str = Field(default="autochat_collection", min_length=1, max_length=255)
    artifact: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Artifact id. Defaults to one derived from the sheet and tab, "
        "so importing the same tab again targets the same artifact.",
    )
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Display name for the document (without extension).",
    )


@google_sheets_router.post(
    "/ingest/google-sheet",
    response_model=IngestResponse,
    summary="Ingest Google Sheet",
    responses={400: {"description": "Invalid, private or empty sheet"}},
)
async def ingest_google_sheet(
    request: Request, body: GoogleSheetIngestBody
) -> IngestResponse:
    """Import one tab of a public Google Sheet and ingest it as a CSV document."""
    settings = request.state.injector.get(Settings)
    try:
        ref = parse_sheet_url(body.url)
        csv_bytes = await asyncio.to_thread(
            download_sheet_csv, ref, settings.chat.maximum_blob_size
        )
    except SheetLinkError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    name = body.name or f"google-sheet-{ref.spreadsheet_id[:8]}-{ref.gid}"
    ingest_body = IngestBody(
        artifact=body.artifact or f"gsheet-{ref.spreadsheet_id}-{ref.gid}",
        collection=body.collection,
        input=FileArtifact(value=base64.b64encode(csv_bytes).decode("ascii")),
        metadata={
            "file_name": f"{name}.csv",
            "source": "google_sheets",
            "source_url": ref.sheet_url,
        },
    )
    scheduler = request.state.injector.get(IngestionSchedulerFactory).get()
    result: IngestResponse = await cancel_on_http_disconnect(
        request, scheduler.ingest_for_request(ingest_body)
    )
    return result
