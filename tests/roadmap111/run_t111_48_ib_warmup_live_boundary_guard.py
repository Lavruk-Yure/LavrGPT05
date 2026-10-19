"""T111-48 — IB Warm-up/Live Boundary Guard, TEST_ONLY.

Досліджує кандидат часової межі на production Alligator.
Не модифікує production, Replay, брокерський адаптер або CSV.
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.algorithm_workspace import WORKSPACE_DATA_MODE_BROKER  # noqa: E402
from core.workspace_algorithm import WorkspaceAlgorithmError  # noqa: E402
from core.workspace_alligator import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
    WorkspaceAlligatorFilter,
)
from core.workspace_broker_market import (  # noqa: E402
    WorkspaceBrokerBinding,
    WorkspaceLiveBarAggregator,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402

CSV_NAME = "2026-10-16_2026-10-19_IB_EURUSD_M15.csv"
ERROR = "Alligator bars must be strictly ordered and unique"


@dataclass
class BoundaryGuard:
    """Тестовий кандидат: останній переданий завершений бар."""

    latest_completed: datetime | None = None
    dropped: int = 0
    accepted: int = 0

    def dispatch(
        self, event: WorkspaceMarketEvent, sink: WorkspaceAlligatorFilter
    ) -> bool:
        stamp = event.timestamp.astimezone(UTC)
        if self.latest_completed is not None and stamp <= self.latest_completed:
            self.dropped += 1
            return False
        sink.on_market_event(event)
        self.latest_completed = stamp
        self.accepted += 1
        return True


def find_csv() -> Path:
    options = (
        ROOT / "data/history/IB/EURUSD/M15" / CSV_NAME,
        ROOT / "data/history/IB/EURUSDM15" / CSV_NAME,
        ROOT / CSV_NAME,
        Path(__file__).resolve().parent / CSV_NAME,
        Path(r"D:\LGE\data\history\IB\EURUSD\M15") / CSV_NAME,
        Path(r"D:\LGE\data\history\IB\EURUSDM15") / CSV_NAME,
    )
    for path in options:
        if path.is_file():
            return path
    raise FileNotFoundError(f"CSV не знайдено: {CSV_NAME}")


def read_events(path: Path) -> list[WorkspaceMarketEvent]:
    events = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        assert required.issubset(reader.fieldnames or [])
        for row in reader:
            stamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            assert stamp.tzinfo is not None
            close = float(row["close"])
            events.append(
                WorkspaceMarketEvent(
                    timestamp=stamp.astimezone(UTC),
                    broker="IB",
                    symbol="EURUSD",
                    timeframe="M15",
                    bid=close,
                    ask=close + 0.00003,
                    spread=0.00003,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=close,
                    volume=float(row["volume"]),
                    source_mode=WORKSPACE_DATA_MODE_BROKER,
                )
            )
    assert len(events) == 126
    assert all(
        left.timestamp < right.timestamp for left, right in zip(events, events[1:])
    )
    return events


def make_filter() -> WorkspaceAlligatorFilter:
    return WorkspaceAlligatorFilter(
        enabled=True,
        confirmation_mode=WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
        timeframe="M15",
    )


def make_aggregator() -> WorkspaceLiveBarAggregator:
    binding = WorkspaceBrokerBinding(
        workspace_uid="T111-48-TEST_ONLY",
        broker="IB",
        account_id="TEST_PAPER",
        symbol="EURUSD",
        timeframe="M15",
    )
    return WorkspaceLiveBarAggregator(binding)


def quote(aggregator: WorkspaceLiveBarAggregator, stamp: datetime):
    return aggregator.update(timestamp=stamp, bid=1.123, ask=1.12303, volume=0.0)


def warmup(events: list[WorkspaceMarketEvent], guarded: bool):
    indicator = make_filter()
    gate = BoundaryGuard()
    for event in events:
        if guarded:
            assert gate.dispatch(event, indicator)
        else:
            indicator.on_market_event(event)
    return indicator, gate


def main() -> None:
    events = read_events(find_csv())
    last = events[-1].timestamp
    assert last == datetime(2026, 10, 19, 7, 30, tzinfo=UTC)

    baseline, _ = warmup(events, guarded=False)
    candidate, gate = warmup(events, guarded=True)
    assert baseline.latest_observation.timestamp == last
    assert candidate.latest_observation.timestamp == last
    assert gate.accepted == len(events)

    # Однакові контрольні live quotes створюють той самий завершений M15.
    aggregate = make_aggregator()
    assert quote(aggregate, last + timedelta(minutes=5)) is None
    duplicate = quote(aggregate, last + timedelta(minutes=15, seconds=1))
    assert duplicate is not None and duplicate.timestamp == last

    baseline_rejects_duplicate = False
    try:
        baseline.on_market_event(duplicate)
    except WorkspaceAlgorithmError as exc:
        baseline_rejects_duplicate = str(exc) == ERROR
    assert baseline_rejects_duplicate
    assert not gate.dispatch(duplicate, candidate)
    assert candidate.latest_observation.timestamp == last
    assert gate.dropped == 1

    # Після дубля той самий агрегатор формує наступний завершений bucket.
    fresh = quote(aggregate, last + timedelta(minutes=30, seconds=1))
    assert fresh is not None
    assert fresh.timestamp == last + timedelta(minutes=15)
    baseline_fresh, _ = warmup(events, guarded=False)
    baseline_fresh.on_market_event(fresh)
    assert gate.dispatch(fresh, candidate)
    assert candidate.latest_observation.timestamp == fresh.timestamp
    assert baseline_fresh.latest_observation.timestamp == fresh.timestamp

    # Старіший бар не повинен повертати стан Alligator назад.
    assert not gate.dispatch(events[-2], candidate)
    assert gate.dropped == 2
    assert gate.accepted == len(events) + 1
    assert candidate.latest_observation.timestamp == fresh.timestamp

    print("T111-48 TEST_ONLY")
    print("verdict=IB_WARMUP_LIVE_BOUNDARY_GUARD_CANDIDATE_GREEN")
    print(f"csv_rows={len(events)}")
    print("baseline_duplicate_rejected=True")
    print("candidate_duplicate_skipped=True")
    print("candidate_older_timestamp_skipped=True")
    print("candidate_newer_completed_bar_accepted=True")
    print("baseline_and_candidate_newer_timestamp_equal=True")
    print("candidate_skipped_bars=2")
    print("observed_server_root_cause=UNRESOLVED")
    print("TEST_ONLY=True")
    print("broker_requests=0")
    print("broker_execution_attempted=False")
    print("production_logic_changed=False")


if __name__ == "__main__":
    main()
