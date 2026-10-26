import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from autochat.server.usage.usage_store import UsageStore, UsageSummary
from autochat.server.utils.auth import authenticated

usage_router = APIRouter(
    prefix="/v1/usage",
    dependencies=[Depends(authenticated)],
    tags=["Usage"],
    responses={401: {"description": "Unauthorized"}},
)


@usage_router.get("/summary", response_model=UsageSummary)
async def usage_summary(
    request: Request,
    days: Annotated[int, Query(ge=1, le=90, description="Window in days")] = 7,
) -> UsageSummary:
    """Latency, first-token time and token usage of recent `/v1/messages` calls."""
    store = request.state.injector.get(UsageStore)
    return await asyncio.to_thread(store.summary, days)
