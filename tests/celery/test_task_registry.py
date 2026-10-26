import ast
import os
import subprocess
import sys

import pytest

from autochat.celery.task_registry import get_task_packages


def test_explicit_task_packages_replace_defaults() -> None:
    assert get_task_packages("autochat.celery.tasks.tools") == (
        "autochat.celery.tasks.tools",
    )


@pytest.mark.parametrize(
    ("task_package", "expected_tasks"),
    [
        (
            "autochat.celery.tasks.ingestion",
            {
                "autochat.ingestion.delete",
                "autochat.ingestion.parse",
                "autochat.ingestion.store_vectors",
            },
        ),
        (
            "autochat.celery.tasks.tools",
            {"autochat.tools.run"},
        ),
    ],
)
def test_worker_registers_only_configured_task_package(
    task_package: str,
    expected_tasks: set[str],
) -> None:
    env = os.environ.copy()
    env["AUTOCHAT_CELERY_TASK_PACKAGES"] = task_package
    output = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "from autochat.celery.celery import celery_app; "
            "celery_app.loader.import_default_modules(); "
            "print(sorted(name for name in celery_app.tasks "
            "if name.startswith('autochat.')))",
        ],
        env=env,
        text=True,
    )

    assert set(ast.literal_eval(output.strip())) == expected_tasks
