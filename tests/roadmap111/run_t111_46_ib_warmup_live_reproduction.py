"""T111-46 IB warm-up/live ordering на реальній історії, TEST_ONLY.

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


def main() -> None:
    csv_path = _find_csv()
    events = _read_events(csv_path)
    timestamps = [event.timestamp for event in events]
    assert len(events) == 126, f"Очікували 126 барів, є {len(events)}"
    assert all(a < b for a, b in zip(timestamps, timestamps[1:]))
    assert timestamps[-1] == datetime(2026, 10, 19, 7, 30, tzinfo=UTC)

    # Реальні CSV-бари проходять через незмінений production Alligator.
    ordered = _filter()
    _feed(ordered, events)
    assert ordered.latest_observation is not None
    assert ordered.latest_observation.timestamp == timestamps[-1]

    # Повтор останнього завершеного timestamp — контрольна гілка відмови.
    overlap = _filter()
    _feed(overlap, events)
    duplicate_error = None
    try:
        overlap.on_market_event(events[-1])
    except WorkspaceAlgorithmError as exc:
        duplicate_error = str(exc)
    assert duplicate_error == "Alligator bars must be strictly ordered and unique"

    # Наступний timestamp: синтетичний event із тим самим OHLC, не котирування.
    next_event = WorkspaceMarketEvent(
        timestamp=timestamps[-1] + timedelta(minutes=15),
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        bid=events[-1].bid,
        ask=events[-1].ask,
        spread=events[-1].spread,
        open=events[-1].open,
        high=events[-1].high,
        low=events[-1].low,
        close=events[-1].close,
        volume=events[-1].volume,
        source_mode=WORKSPACE_DATA_MODE_BROKER,
    )
    newer = _filter()
    _feed(newer, events)
    observation = newer.on_market_event(next_event)
    assert observation.timestamp == datetime(2026, 10, 19, 7, 45, tzinfo=UTC)

    print("T111-47 TEST_ONLY")
    print("verdict=IB_WARMUP_LIVE_DUPLICATE_REPRODUCED")
    print(f"csv_rows={len(events)}")
    print("csv_order_strict=True")
    print("real_csv_warmup_passes=True")
    print("duplicate_0730_rejected=True")
    print("synthetic_0745_accepted=True")
    print("observed_server_root_cause=UNRESOLVED")
    print("broker_requests=0")
    print("broker_execution_attempted=False")
    print("production_logic_changed=False")


if __name__ == "__main__":
    main()
