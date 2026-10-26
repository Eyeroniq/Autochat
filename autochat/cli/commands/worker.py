from autochat.worker import run_autochat_worker


def worker_command() -> None:
    """Start the worker mode selected by ``AUTOCHAT_WORKER_MODE``."""
    run_autochat_worker()
