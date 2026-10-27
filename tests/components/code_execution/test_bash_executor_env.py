import sys
from pathlib import Path

import pytest

from autochat.components.code_execution.bash_executor import LocalBashExecutor

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Unix shell")


async def test_commands_cannot_read_server_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("AUTOCHAT_AUTH_SECRET", "Basic should-not-leak")
    monkeypatch.setenv("SOME_SERVICE_TOKEN", "should-not-leak")
    monkeypatch.setenv("MY_PLAIN_SETTING", "visible")

    # RLIMIT_NPROC counts all of the user's processes; a busy dev machine can
    # already exceed the default 50, which would make the fork itself fail.
    executor = LocalBashExecutor(nproc_limit=100_000)
    result = await executor.run("env", cwd=tmp_path, timeout=10)

    assert result.success
    assert "should-not-leak" not in result.stdout
    assert "MY_PLAIN_SETTING=visible" in result.stdout
    assert "PATH=" in result.stdout
