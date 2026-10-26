"""What a guest session may do.

Guests can read models, documents and skills and chat over them. Anything that
changes server state, or makes the server reach out to a host or file the
guest chooses (URIs, SQL connections, MCP servers, web and code tools), is
reserved for the authenticated owner.
"""

from typing import Any

from starlette.requests import Request

from autochat.components.tools.tool_names import (
    SEMANTIC_SEARCH_TOOL_NAME,
    SKILL_MANAGEMENT_TOOLS,
    SUMMARIZE_TOOL_NAME,
    TABULAR_DATA_ANALYSIS,
    resolve_internal_tool_name,
)

CHAT_ROUTE = ("POST", "/v1/messages")

GUEST_ALLOWED_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/v1/models"),
        ("GET", "/v1/models/{model_id}"),
        CHAT_ROUTE,
        ("POST", "/v1/messages/count_tokens"),
        ("GET", "/v1/artifacts/list"),
        ("GET", "/v1/skills"),
        ("GET", "/v1/skills/{skill_id}"),
        ("GET", "/v1/skills/{skill_id}/versions"),
    }
)

GUEST_CONTEXT_TYPES = frozenset({"ingested_artifact", "text", "skill"})

GUEST_INTERNAL_TOOLS = frozenset(
    {
        SEMANTIC_SEARCH_TOOL_NAME,
        TABULAR_DATA_ANALYSIS,
        SUMMARIZE_TOOL_NAME,
        *SKILL_MANAGEMENT_TOOLS,
    }
)


def route_key(request: Request) -> tuple[str, str]:
    """``(method, path template)`` of the matched route.

    For example ``("GET", "/v1/skills/{skill_id}")``.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None) or request.url.path
    return request.method.upper(), path


def guest_chat_violation(body: Any, max_tokens: int) -> str | None:
    """Return why a guest chat body is rejected, or ``None`` if it is allowed."""
    if not isinstance(body, dict):
        return None  # Let the endpoint's own validation report the error.
    if body.get("mcp_servers"):
        return "Guests cannot attach MCP servers."
    if body.get("container") or body.get("mounts"):
        return "Guests cannot use sandbox containers or mounts."
    requested_tokens = body.get("max_tokens")
    if isinstance(requested_tokens, int) and requested_tokens > max_tokens:
        return f"Guests can request at most {max_tokens} output tokens."

    reason = _context_violation(body.get("tool_context"))
    if reason:
        return reason
    for tool in body.get("tools") or []:
        reason = _tool_violation(tool)
        if reason:
            return reason
    return None


def _context_violation(context: Any) -> str | None:
    for item in context or []:
        item_type = item.get("type") if isinstance(item, dict) else None
        if item_type not in GUEST_CONTEXT_TYPES:
            return f"Guests cannot use '{item_type}' context."
    return None


def _tool_violation(tool: Any) -> str | None:
    if isinstance(tool, str):
        tool_type = tool
    elif isinstance(tool, dict):
        tool_type = tool.get("type") or "custom"
        reason = _context_violation(tool.get("context"))
        if reason:
            return reason
    else:
        return None
    internal = resolve_internal_tool_name(tool_type)
    if internal is not None and internal not in GUEST_INTERNAL_TOOLS:
        return f"Guests cannot use the '{internal}' tool."
    return None


def client_ip(request: Request, trust_forwarded_for: bool) -> str:
    if trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for", "")
        # The last entry is the one our own proxy appended; earlier ones are
        # whatever the client sent and can be spoofed.
        last = forwarded.split(",")[-1].strip()
        if last:
            return last
    return request.client.host if request.client else "unknown"
