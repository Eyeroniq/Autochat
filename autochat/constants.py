import os
from pathlib import Path

PROJECT_ROOT_PATH: Path = (
    Path(os.environ.get("AUTOCHAT_PROJECT_ROOT", str(Path(__file__).parents[1])))
    .expanduser()
    .resolve()
)


def _default_autochat_home() -> str:
    if os.name == "nt":  # Windows
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = (
            Path(local_app_data)
            if local_app_data
            else Path.home() / "AppData" / "Local"
        )
        return str(base / "autochat")
    return str(Path.home() / ".local" / "share" / "autochat")


AUTOCHAT_HOME: Path = (
    Path(os.environ.get("AUTOCHAT_HOME", _default_autochat_home()))
    .expanduser()
    .resolve()
)
