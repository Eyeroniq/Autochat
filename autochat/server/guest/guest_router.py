from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field

from autochat.server.guest.guest_policy import client_ip
from autochat.server.guest.guest_sessions import (
    GuestLimitError,
    GuestSessionManager,
)
from autochat.settings.settings import Settings

# Deliberately not behind `authenticated`: these endpoints are how a visitor
# without the secret gets in.
guest_router = APIRouter(prefix="/v1/guest", tags=["Guest"])


class GuestStatus(BaseModel):
    enabled: bool = Field(description="Whether visitors can start a guest session.")
    messages_per_session: int
    session_ttl_minutes: int


class GuestSessionResponse(BaseModel):
    token: str = Field(description="Send as `Authorization: Bearer <token>`.")
    expires_at: int = Field(description="Unix time when the token stops working.")
    messages_per_session: int
    max_tokens: int = Field(description="Largest `max_tokens` a guest may request.")


def _guest_mode_enabled(settings: Settings) -> bool:
    # Without auth every request is already allowed, so guest tokens mean nothing.
    return settings.server.auth.enabled and settings.server.guest.enabled


class GuestSessionRequest(BaseModel):
    """No options yet; send `{}` or no body."""


@guest_router.get("/status", response_model=GuestStatus, summary="Guest Status")
def guest_status(request: Request) -> GuestStatus:
    """Whether this server hands out guest sessions, and their limits."""
    settings = request.state.injector.get(Settings)
    guest = settings.server.guest
    return GuestStatus(
        enabled=_guest_mode_enabled(settings),
        messages_per_session=guest.messages_per_session,
        session_ttl_minutes=guest.session_ttl_minutes,
    )


@guest_router.post(
    "/session",
    response_model=GuestSessionResponse,
    summary="Start Guest Session",
    responses={
        404: {"description": "Guest mode is disabled"},
        429: {"description": "Too many guest sessions from this address"},
    },
)
def create_guest_session(
    request: Request,
    _body: Annotated[
        GuestSessionRequest | None,
        Body(description="Optional and currently empty; no fields are required."),
    ] = None,
) -> GuestSessionResponse:
    """Start a rate-limited, read-only guest session without the auth secret.

    Send the returned token as `Authorization: Bearer <token>`.
    """
    settings = request.state.injector.get(Settings)
    if not _guest_mode_enabled(settings):
        raise HTTPException(status_code=404, detail="Guest mode is disabled")
    manager = request.state.injector.get(GuestSessionManager)
    try:
        token, session = manager.create_session(
            client_ip(request, settings.server.guest.trust_forwarded_for)
        )
    except GuestLimitError as error:
        raise HTTPException(
            status_code=429,
            detail=str(error),
            headers={"Retry-After": str(error.retry_after or 3600)},
        ) from error
    return GuestSessionResponse(
        token=token,
        expires_at=session.expires_at,
        messages_per_session=settings.server.guest.messages_per_session,
        max_tokens=settings.server.guest.max_tokens,
    )
