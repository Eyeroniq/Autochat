"""Authentication mechanism for the API.

Define a simple mechanism to authenticate requests.
More complex authentication mechanisms can be defined here, and be placed in the
`authenticated` method (being a 'bean' injected in fastapi routers).

Authorization can also be made after the authentication, and depends on
the authentication. Authorization should not be implemented in this file.

Authorization can be done by following fastapi's guides:
* https://fastapi.tiangolo.com/advanced/security/oauth2-scopes/
* https://fastapi.tiangolo.com/tutorial/security/
* https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-in-path-operation-decorators/
"""

# mypy: ignore-errors
# Disabled mypy error: All conditional function variants must have identical signatures
# We are changing the implementation of the authenticated method, based on
# the config. If the auth is not enabled, we are not defining the complex method
# with its dependencies.
import logging
import secrets
from typing import Annotated

from fastapi import Header, HTTPException, Request

from autochat.server.guest.guest_policy import (
    CHAT_ROUTE,
    GUEST_ALLOWED_ROUTES,
    guest_chat_violation,
    route_key,
)
from autochat.server.guest.guest_sessions import (
    GuestLimitError,
    GuestSessionManager,
)
from autochat.settings.settings import settings

# 401 signify that the request requires authentication.
# 403 signify that the authenticated user is not authorized to perform the operation.
NOT_AUTHENTICATED = HTTPException(
    status_code=401,
    detail="Not authenticated",
    headers={"WWW-Authenticate": 'Basic realm="All the API", charset="UTF-8"'},
)


async def _authorize_guest(request: Request, authorization: str) -> None:
    """Accept a valid guest token for the routes and requests guests may use."""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        raise NOT_AUTHENTICATED
    manager = request.state.injector.get(GuestSessionManager)
    session = manager.verify(token.strip())
    if session is None:
        raise NOT_AUTHENTICATED

    key = route_key(request)
    if key not in GUEST_ALLOWED_ROUTES:
        raise HTTPException(status_code=403, detail="Guests cannot use this endpoint.")
    if key != CHAT_ROUTE:
        return

    try:
        body = await request.json()
    except ValueError:
        body = None
    reason = guest_chat_violation(body, manager.settings.max_tokens)
    if reason:
        raise HTTPException(status_code=403, detail=reason)
    try:
        manager.consume_message(session)
    except GuestLimitError as error:
        headers = {"Retry-After": str(error.retry_after)} if error.retry_after else None
        raise HTTPException(
            status_code=429, detail=str(error), headers=headers
        ) from error


async def secret_or_guest_authentication(
    request: Request,
    authorization: Annotated[str, Header()] = "",
) -> bool:
    """Accept the configured secret, or a guest token when guest mode is on."""
    # Compare bytes: `compare_digest` raises on non-ASCII `str` input.
    if secrets.compare_digest(
        authorization.encode(), settings().server.auth.secret.encode()
    ):
        return True
    if settings().server.guest.enabled:
        await _authorize_guest(request, authorization)
        return True
    raise NOT_AUTHENTICATED


logger = logging.getLogger(__name__)


def _simple_authentication(authorization: Annotated[str, Header()] = "") -> bool:
    """Check if the request is authenticated."""
    if not secrets.compare_digest(authorization, settings().server.auth.secret):
        # If the "Authorization" header is not the expected one, raise an exception.
        raise NOT_AUTHENTICATED
    return True


if not settings().server.auth.enabled:
    logger.debug(
        "Defining a dummy authentication mechanism for fastapi, always authenticating requests"
    )

    # Define a dummy authentication method that always returns True.
    def authenticated() -> bool:
        """Check if the request is authenticated."""
        return True

else:
    logger.info("Defining the given authentication mechanism for the API")

    # Method to be used as a dependency to check if the request is authenticated.
    async def authenticated(
        request: Request,
        authorization: Annotated[str, Header()] = "",
    ) -> bool:
        """Check if the request is authenticated."""
        if not settings().server.auth.enabled:
            # Auth could be disabled at runtime after the module was imported.
            # Never use `assert` here: it is stripped under `python -O` and
            # would raise AssertionError (500) instead of a proper 401.
            raise NOT_AUTHENTICATED
        return await secret_or_guest_authentication(request, authorization)
