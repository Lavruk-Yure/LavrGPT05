"""T111-47 — Runtime aggregator warm-up/live boundary, TEST_ONLY.

Запуск не підключається до брокерів, не змінює production і Replay.
Синтетичний бар 07:45 — лише контроль межі, не ринкові дані.
"""

from __future__ import annotations

import csv
import sys
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
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402

CSV_NAME = "2026-10-16_2026-10-19_IB_EURUSD_M15.csv"


def _find_csv() -> Path:
    """Шукати переданий CSV, не змінюючи його та не завантажуючи дані."""
    options = (
        ROOT / "data" / "history" / "IB" / "EURUSD" / "M15" / CSV_NAME,
        ROOT / "data" / "history" / "IB" / "EURUSDM15" / CSV_NAME,
        ROOT / CSV_NAME,
        Path(__file__).resolve().parent / CSV_NAME,
        Path(r"D:\LGE\data\history\IB\EURUSD\M15") / CSV_NAME,
        Path(r"D:\LGE\data\history\IB\EURUSDM15") / CSV_NAME,
    )
    for path in options:
        if path.is_file():
            return path
    raise FileNotFoundError(
        "Скопіюй CSV поряд із тестом або в корінь LavrGPT05: " + CSV_NAME
    )


def _read_events(path: Path) -> list[WorkspaceMarketEvent]:
    """Прочитати брокерські M15-бари в оригінальному порядку CSV."""
    events = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        expected = {"timestamp", "open", "high", "low", "close", "volume"}
        if not expected.issubset(reader.fieldnames or []):
            raise AssertionError("Неочікувані колонки CSV")
        for row in reader:
            timestamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise AssertionError("CSV timestamp без UTC")
            close = float(row["close"])
            events.append(
                WorkspaceMarketEvent(
                    timestamp=timestamp.astimezone(UTC),
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
    if not events:
        raise AssertionError("CSV порожній")
    return events


def _filter() -> WorkspaceAlligatorFilter:
    return WorkspaceAlligatorFilter(
        enabled=True,
        confirmation_mode=WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
        timeframe="M15",
    )


def _feed(
    filter_instance: WorkspaceAlligatorFilter,
    events: list[WorkspaceMarketEvent],
) -> None:
    for event in events:
        filter_instance.on_market_event(event)


from core.workspace_broker_market import (  # noqa: E402
    WorkspaceBrokerBinding,
    WorkspaceLiveBarAggregator,
)


def _make_aggregator() -> WorkspaceLiveBarAggregator:
    binding = WorkspaceBrokerBinding(
        workspace_uid="T111-47-TEST_ONLY",
        broker="IB",
        account_id="TEST_PAPER",
        symbol="EURUSD",
        timeframe="M15",
    )
    return WorkspaceLiveBarAggregator(binding)


def _quote(aggregator: WorkspaceLiveBarAggregator, timestamp: datetime):
    return aggregator.update(
        timestamp=timestamp,
        bid=1.12300,
        ask=1.12303,
        volume=0.0,
    )


def main() -> None:
    events = _read_events(_find_csv())
    assert len(events) == 126
    assert all(a.timestamp < b.timestamp for a, b in zip(events, events[1:]))
    last = events[-1].timestamp
    assert last == datetime(2026, 10, 19, 7, 30, tzinfo=UTC)

    # Warm-up подає завершені CSV-бари без звернення до брокера.
    alligator = _filter()
    _feed(alligator, events)
    assert alligator.latest_observation.timestamp == last

    # Агрегатор не отримує останній timestamp warm-up.
    live = _make_aggregator()

    # Перший live quote може належати вже обробленому 07:30 bucket.
    assert _quote(live, last + timedelta(minutes=5)) is None
    repeated = _quote(live, last + timedelta(minutes=15, seconds=1))
    assert repeated is not None
    assert repeated.timestamp == last
    duplicate_rejected = False
    try:
        alligator.on_market_event(repeated)
    except WorkspaceAlgorithmError as exc:
        duplicate_rejected = (
            str(exc) == "Alligator bars must be strictly ordered and unique"
        )
    assert duplicate_rejected

    # Пізніший live bucket приймається, коли немає перекриття.
    non_overlap = _filter()
    _feed(non_overlap, events)
    fresh_live = _make_aggregator()
    assert _quote(fresh_live, last + timedelta(minutes=15, seconds=1)) is None
    fresh = _quote(fresh_live, last + timedelta(minutes=30, seconds=1))
    assert fresh is not None and fresh.timestamp == last + timedelta(minutes=15)
    non_overlap.on_market_event(fresh)
    assert non_overlap.latest_observation.timestamp == fresh.timestamp

    # Це відтворена можливість, не доказ конкретного серверного trace.
    print("T111-47 TEST_ONLY")
    print("verdict=IB_RUNTIME_WARMUP_LIVE_OVERLAP_PATH_REPRODUCED")
    print(f"csv_rows={len(events)}")
    print("csv_order_strict=True")
    print("aggregator_independent_from_warmup_timestamp=True")
    print("warmup_last_timestamp=2026-10-19T07:30:00+00:00")
    print("live_completed_same_timestamp=True")
    print("production_alligator_rejects_overlap=True")
    print("next_live_bucket_accepted=True")
    print("observed_server_root_cause=UNRESOLVED")
    print("TEST_ONLY=True")
    print("broker_requests=0")
    print("broker_execution_attempted=False")
    print("production_logic_changed=False")


if __name__ == "__main__":
    main()
