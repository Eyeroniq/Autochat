from collections.abc import Sequence

from autochat.worker.modes import register_autochat_worker_modes
from autochat.worker.registry import register_worker_mode, run_worker


def run_autochat_worker(args: Sequence[str] = ()) -> None:
    register_autochat_worker_modes()
    run_worker(args)


__all__ = ["register_worker_mode", "run_autochat_worker", "run_worker"]
