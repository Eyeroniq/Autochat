"""FastAPI app creation, logger configuration and main API routes."""

from autochat.di import get_global_injector
from autochat.launcher import create_app

app = create_app(get_global_injector())
