from pathlib import Path
from types import SimpleNamespace

from autochat.server.usage.usage_store import UsageRecord, UsageStore
from autochat.settings.settings import UsageSettings

DAY = 86400
NOW = 1_700_006_400.0  # 2023-11-15T00:00:00Z


def _store(tmp_path: Path, enabled: bool = True, max_records: int = 100) -> UsageStore:
    settings = SimpleNamespace(
        usage=UsageSettings(
            enabled=enabled,
            database_path=str(tmp_path / "usage.sqlite"),
            max_records=max_records,
        ),
        data=SimpleNamespace(local_data_folder=str(tmp_path)),
    )
    return UsageStore(settings)


def _record(ts: float, latency: float, **overrides) -> UsageRecord:
    values = {
        "ts": ts,
        "role": "owner",
        "model": "llama",
        "status": 200,
        "stream": True,
        "latency_ms": latency,
        "first_token_ms": latency / 4,
        "input_tokens": 100,
        "output_tokens": 20,
    }
    values.update(overrides)
    return UsageRecord(**values)


def test_disabled_store_records_nothing(tmp_path: Path) -> None:
    store = _store(tmp_path, enabled=False)
    store.record(_record(NOW, 100))

    assert store.summary(7, now=NOW).enabled is False
    assert not (tmp_path / "usage.sqlite").exists()


def test_summary_statistics(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for latency in (100, 200, 300, 400, 1000):
        store.record(_record(NOW - 60, latency))
    store.record(_record(NOW - 30, 50, status=429, role="guest", output_tokens=None))

    summary = store.summary(7, now=NOW)

    assert summary.requests == 6
    assert summary.errors == 1
    assert summary.guest_requests == 1
    # Errors are excluded from latency and token statistics.
    assert summary.latency_ms.p50 == 300
    assert summary.latency_ms.p95 == 1000
    assert summary.latency_ms.avg == 400
    assert summary.first_token_ms.p50 == 75
    assert summary.tokens.output_total == 100
    assert summary.tokens.input_avg == 100
    assert summary.recent[0].status == 429  # newest first


def test_summary_window_and_days(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.record(_record(NOW - 10 * DAY, 999))  # outside a 7-day window
    store.record(_record(NOW - 2 * DAY + 60, 100))
    store.record(_record(NOW - DAY + 60, 300))
    store.record(_record(NOW - DAY + 120, 500))

    summary = store.summary(7, now=NOW)

    assert summary.requests == 3
    assert [(d.date, d.requests) for d in summary.per_day] == [
        ("2023-11-13", 1),
        ("2023-11-14", 2),
    ]
    assert summary.per_day[1].latency_p50_ms == 300
    assert summary.per_day[1].output_tokens == 40


def test_old_records_are_pruned(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("autochat.server.usage.usage_store._PRUNE_EVERY", 10)
    store = _store(tmp_path, max_records=100)
    for i in range(150):
        store.record(_record(NOW - 150 + i, 100))

    assert 100 <= store.summary(7, now=NOW).requests < 150
