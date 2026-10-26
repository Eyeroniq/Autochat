from types import SimpleNamespace

import pytest

from autochat.server.guest.guest_policy import client_ip, guest_chat_violation

# What the Workbench UI sends for a document-backed chat.
UI_BODY = {
    "model": "mock",
    "messages": [{"role": "user", "content": "hi"}],
    "tools": [
        {"name": "semantic_search", "type": "semantic_search_v1"},
        {"name": "tabular_analysis", "type": "tabular_analysis_v1"},
        {"name": "lookup", "description": "client tool", "inputSchema": {}},
    ],
    "tool_context": [
        {
            "type": "ingested_artifact",
            "context_filter": {"collection": "demo", "artifacts": []},
        }
    ],
    "mcp_servers": [],
    "stream": True,
    "max_tokens": 1024,
}


def test_ui_document_chat_is_allowed() -> None:
    assert guest_chat_violation(UI_BODY, max_tokens=2048) is None


def test_non_dict_body_is_left_to_endpoint_validation() -> None:
    assert guest_chat_violation(None, max_tokens=2048) is None


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"mcp_servers": [{"url": "http://internal"}]}, "MCP"),
        ({"container": "abc"}, "sandbox"),
        ({"mounts": [{"path": "/"}]}, "sandbox"),
        ({"max_tokens": 4096}, "2048"),
        ({"tool_context": [{"type": "uri", "value": "/etc/passwd"}]}, "'uri'"),
        (
            {"tool_context": [{"type": "sql_database", "connection_string": "x"}]},
            "'sql_database'",
        ),
        ({"tools": ["code_execution"]}, "'code_execution'"),
        ({"tools": [{"type": "bash_code_execution_v1"}]}, "'bash_code_execution'"),
        ({"tools": [{"type": "web_fetch_v1"}]}, "'web_fetch'"),
        ({"tools": [{"type": "web_extract"}]}, "'web_fetch'"),
        ({"tools": [{"type": "database_query_v1"}]}, "'database_query'"),
        (
            {
                "tools": [
                    {
                        "type": "semantic_search_v1",
                        "context": [{"type": "uri", "value": "http://x"}],
                    }
                ]
            },
            "'uri'",
        ),
    ],
)
def test_guest_restrictions(change: dict, expected: str) -> None:
    reason = guest_chat_violation({**UI_BODY, **change}, max_tokens=2048)

    assert reason is not None
    assert expected in reason


def _request(host: str, forwarded: str | None = None) -> SimpleNamespace:
    headers = {"x-forwarded-for": forwarded} if forwarded else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))


def test_client_ip_ignores_forwarded_for_unless_trusted() -> None:
    request = _request("172.18.0.5", "1.1.1.1, 203.0.113.7")

    assert client_ip(request, trust_forwarded_for=False) == "172.18.0.5"
    # Only the entry our proxy appended counts; the rest is client-supplied.
    assert client_ip(request, trust_forwarded_for=True) == "203.0.113.7"
    assert client_ip(_request("172.18.0.5"), trust_forwarded_for=True) == "172.18.0.5"
