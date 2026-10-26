"""SQLite-backed record of chat latency and token usage."""

import logging
import math
import sqlite3
import threading
import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import astuple, dataclass
from datetime import UTC, datetime
from pathlib import Path

from injector import inject, singleton
from pydantic import BaseModel

from autochat.paths import resolve_data_path
from autochat.settings.settings import Settings

logger = logging.getLogger(__name__)

_PRUNE_EVERY = 500
_RECENT_LIMIT = 20


@dataclass(frozen=True)
class UsageRecord:
    ts: float
    role: str
    model: str | None
    status: int
    stream: bool
    latency_ms: float
    first_token_ms: float | None
    input_tokens: int | None
    output_tokens: int | None


class LatencyStats(BaseModel):
    p50: float | None
    p95: float | None
    avg: float | None


class TokenStats(BaseModel):
    input_avg: float | None
    output_avg: float | None
    input_total: int
    output_total: int


class UsageDay(BaseModel):
    date: str
    requests: int
    latency_p50_ms: float | None
    output_tokens: int


class UsageEntry(BaseModel):
    ts: float
    role: str
    model: str | None
    status: int
    stream: bool
    latency_ms: float
    first_token_ms: float | None
    input_tokens: int | None
    output_tokens: int | None


class UsageSummary(BaseModel):
    enabled: bool
    window_days: int
    requests: int = 0
    errors: int = 0
    guest_requests: int = 0
    latency_ms: LatencyStats | None = None
    first_token_ms: LatencyStats | None = None
    tokens: TokenStats | None = None
    per_day: list[UsageDay] = []
    recent: list[UsageEntry] = []


def _percentile(values: list[float], pct: float) -> float | None:
    """Nearest-rank percentile; ``None`` for an empty list."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return round(ordered[rank - 1], 1)


def _stats(values: list[float]) -> LatencyStats:
    return LatencyStats(
        p50=_percentile(values, 50),
        p95=_percentile(values, 95),
        avg=round(sum(values) / len(values), 1) if values else None,
    )


def _average(values: list[int]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


@singleton
class UsageStore:
    @inject
    def __init__(self, settings: Settings) -> None:
        self.enabled = settings.usage.enabled
        self._path = (
            resolve_data_path(settings.data.local_data_folder)
            / settings.usage.database_path
        )
        self._max_records = settings.usage.max_records
        self._lock = threading.Lock()
        self._inserts = 0
        if self.enabled:
            self._initialize(self._path)

    def _initialize(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    role TEXT NOT NULL,
                    model TEXT,
                    status INTEGER NOT NULL,
                    stream INTEGER NOT NULL,
                    latency_ms REAL NOT NULL,
                    first_token_ms REAL,
                    input_tokens INTEGER,
                    output_tokens INTEGER
                )
                """
            )
            db.execute("CREATE INDEX IF NOT EXISTS chat_usage_ts ON chat_usage (ts)")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Open a connection that commits on success and is always closed."""
        db = sqlite3.connect(self._path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def record(self, record: UsageRecord) -> None:
        if not self.enabled:
            return
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO chat_usage (ts, role, model, status, stream, latency_ms,"
                " first_token_ms, input_tokens, output_tokens)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                astuple(record),
            )
            self._inserts += 1
            if self._inserts % _PRUNE_EVERY == 0:
                db.execute(
                    "DELETE FROM chat_usage WHERE id <= "
                    "(SELECT MAX(id) FROM chat_usage) - ?",
                    (self._max_records,),
                )

    def summary(self, days: int, now: float | None = None) -> UsageSummary:
        if not self.enabled:
            return UsageSummary(enabled=False, window_days=days)
        since = (now if now is not None else time.time()) - days * 86400
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT ts, role, model, status, stream, latency_ms, first_token_ms,"
                " input_tokens, output_tokens FROM chat_usage"
                " WHERE ts >= ? ORDER BY ts",
                (since,),
            ).fetchall()
        records = [
            UsageRecord(r[0], r[1], r[2], r[3], bool(r[4]), *r[5:]) for r in rows
        ]
        ok = [r for r in records if r.status < 400]
        inputs = [r.input_tokens for r in ok if r.input_tokens is not None]
        outputs = [r.output_tokens for r in ok if r.output_tokens is not None]

        by_day: dict[str, list[UsageRecord]] = defaultdict(list)
        for r in ok:
            by_day[datetime.fromtimestamp(r.ts, tz=UTC).strftime("%Y-%m-%d")].append(r)

        return UsageSummary(
            enabled=True,
            window_days=days,
            requests=len(records),
            errors=len(records) - len(ok),
            guest_requests=sum(1 for r in records if r.role == "guest"),
            latency_ms=_stats([r.latency_ms for r in ok]),
            first_token_ms=_stats(
                [r.first_token_ms for r in ok if r.first_token_ms is not None]
            ),
            tokens=TokenStats(
                input_avg=_average(inputs),
                output_avg=_average(outputs),
                input_total=sum(inputs),
                output_total=sum(outputs),
            ),
            per_day=[
                UsageDay(
                    date=day,
                    requests=len(day_records),
                    latency_p50_ms=_percentile([r.latency_ms for r in day_records], 50),
                    output_tokens=sum(r.output_tokens or 0 for r in day_records),
                )
                for day, day_records in sorted(by_day.items())
            ],
            recent=[
                UsageEntry(**r.__dict__) for r in reversed(records[-_RECENT_LIMIT:])
            ],
        )
