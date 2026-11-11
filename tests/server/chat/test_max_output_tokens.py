from types import SimpleNamespace
from typing import Any, cast

import pytest

from autochat.server.chat.chat_models import ChatBody
from autochat.server.chat.chat_request_mapper import ChatRequestMapper


def _mapper(cap: int | None) -> ChatRequestMapper:
    settings = SimpleNamespace(chat=SimpleNamespace(max_output_tokens=cap))
    return ChatRequestMapper(
        settings=cast("Any", settings),
        tool_pipeline=cast("Any", None),
        mount_resolver=cast("Any", None),
    )


def _body(max_tokens: int) -> ChatBody:
    return ChatBody.model_validate(
        {"max_tokens": max_tokens, "messages": [{"role": "user", "content": "hi"}]}
    )


@pytest.mark.parametrize(
    ("cap", "requested", "sent"),
    [(2048, 4096, 2048), (2048, 1024, 1024), (None, 4096, 4096), (0, 4096, 4096)],
)
async def test_max_tokens_is_capped_by_settings(
    cap: int | None, requested: int, sent: int
) -> None:
    params = await _mapper(cap)._collect_sampling_params(_body(requested))
    assert params["max_tokens"] == sent
