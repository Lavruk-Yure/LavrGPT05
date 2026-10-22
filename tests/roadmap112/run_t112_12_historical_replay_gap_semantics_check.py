# -*- coding: utf-8 -*-
"""T112-12 — причинність Replay на розривах M15, TEST_ONLY / DATA_ONLY.

Не запускає торговий алгоритм і не змінює файлів історії.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator

from run_t112_10_historical_m1_to_m15_aggregation_integrity_check import (
    EXPECTED,
    FIRST_DATES,
    HEADER,
    HISTORY,
    LAST_DATES,
    SYMBOLS,
    Bar,
    IntegrityError,
    M15Counter,
)

M1_STEP = timedelta(minutes=1)
M15_STEP = timedelta(minutes=15)
EXPECTED_COMPLETE = {"EURUSD": 140731, "GBPUSD": 142429, "USDJPY": 142377}
EXPECTED_GAPS = {"EURUSD": 4167, "GBPUSD": 3065, "USDJPY": 3103}
EXPECTED_MAX_RUN = 95


@dataclass(slots=True)
class GapStudy:
    """Статистика розривів без перезапуску стану після пропуску."""

    last: datetime | None = None
    first: datetime | None = None
    bars: int = 0
    run_length: int = 0
    max_run: int = 0
    gaps: int = 0
    weekend_gaps: int = 0
    weekday_gaps: int = 0
    missing_slots: int = 0
    largest_weekday_gap: int = 0
    largest_weekday_start: datetime | None = None
    largest_weekday_end: datetime | None = None

    def add(self, timestamp: datetime) -> None:
        if self.last is not None:
            distance = timestamp - self.last
            if distance <= timedelta(0) or distance % M15_STEP:
                raise IntegrityError("Invalid completed-M15 chronology")
            if distance != M15_STEP:
                skipped = int(distance // M15_STEP) - 1
                self.gaps += 1
                self.missing_slots += skipped
                if _spans_weekend(self.last + M15_STEP, timestamp):
                    self.weekend_gaps += 1
                else:
                    self.weekday_gaps += 1
                    if skipped > self.largest_weekday_gap:
                        self.largest_weekday_gap = skipped
                        self.largest_weekday_start = self.last
                        self.largest_weekday_end = timestamp
                self.max_run = max(self.max_run, self.run_length)
                self.run_length = 0
        else:
            self.first = timestamp
        self.run_length += 1
        self.bars += 1
        self.last = timestamp

    def finish(self) -> None:
        self.max_run = max(self.max_run, self.run_length)


def _spans_weekend(start: datetime, end: datetime) -> bool:
    current = start.date()
    last = (end - M15_STEP).date()
    while current <= last:
        if current.weekday() >= 5:
            return True
        current += timedelta(days=1)
    return False


def _event(timestamp: datetime, *, timeframe: str, price: float = 1.10):
    """Побудувати справжню подію без імітації брокерської відповіді."""
    from core.workspace_market_event import WorkspaceMarketEvent

    spread = 0.00012
    return WorkspaceMarketEvent(
        timestamp=timestamp,
        broker="CTRADER",
        symbol="EURUSD",
        timeframe=timeframe,
        bid=price - spread / 2,
        ask=price + spread / 2,
        spread=spread,
        open=price,
        high=price + 0.0002,
        low=price - 0.0002,
        close=price,
        volume=1.0,
        source_mode="REPLAY",
    )


def _aggregation_contract() -> None:
    """Перевірити завершення, пропуск і невикористання майбутніх барів."""
    from core.workspace_replay import (
        REPLAY_STATE_COMPLETED,
        WorkspaceReplayService,
    )
    from core.workspace_timeframe_aggregation import WorkspaceTimeframeAggregator

    start = datetime(2026, 1, 6, 10, tzinfo=UTC)
    source = tuple(
        _event(start + M1_STEP * i, timeframe="M1", price=1.1 + i * 1e-6)
        for i in range(45)
        if i != 18
    )

    # Публічний Replay-шлях через тимчасовий CSV: історію не змінюємо.
    with TemporaryDirectory(prefix="t112_12_replay_") as temp_dir:
        path = Path(temp_dir) / "synthetic_m1.csv"
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(HEADER)
            for event in source:
                writer.writerow(
                    (
                        event.timestamp.isoformat(),
                        event.open,
                        event.high,
                        event.low,
                        event.close,
                        event.volume,
                    )
                )
        session = WorkspaceReplayService().create_historical_session(
            broker="CTRADER",
            symbol="EURUSD",
            timeframe="M15",
            replay_settings={
                "file_path": str(path),
                "source_timeframe": "M1",
                "source_timezone": "UTC",
                "spread": 0.00012,
            },
        )

    assert session.source_event_count == len(source)
    assert session.dropped_incomplete_strategy_buckets == 1
    assert session.multi_resolution
    completed = session.events
    assert len(completed) == 2
    assert completed[0].timestamp == start
    assert completed[1].timestamp == start + M15_STEP * 2
    assert completed[0].close == source[14].close

    # Завершені M15 не залежать від додавання майбутніх M1.
    for prefix_count in (15, 20, 29, 30):
        aggregator = WorkspaceTimeframeAggregator(
            source_timeframe="M1", target_timeframe="M15"
        )
        prefix_completed = []
        for event in source[:prefix_count]:
            observed = aggregator.on_market_event(event)
            if observed is not None:
                prefix_completed.append(observed)
        last_complete = aggregator.complete()
        if last_complete is not None:
            prefix_completed.append(last_complete)
        assert prefix_completed
        assert prefix_completed[0].event == completed[0]
        assert prefix_completed[0].completed_at == start + M15_STEP
        assert prefix_completed[0].source_bars == 15

    windows = session.execution_windows
    assert len(windows) == 2
    assert windows[0] and not windows[1]
    assert windows[0][0].timestamp >= start + M15_STEP
    assert windows[0][-1].timestamp < start + M15_STEP * 3
    session.start()
    assert session.step() == completed[0]
    assert session.step() == completed[1]
    assert session.state == REPLAY_STATE_COMPLETED
    assert session.current_event == completed[1]

    friday = datetime(2026, 1, 2, 20, 45, tzinfo=UTC)
    sunday = datetime(2026, 1, 4, 22, 0, tzinfo=UTC)
    weekend_source = tuple(
        _event(friday + M1_STEP * i, timeframe="M1") for i in range(15)
    ) + tuple(_event(sunday + M1_STEP * i, timeframe="M1") for i in range(15))
    agg = WorkspaceTimeframeAggregator(source_timeframe="M1", target_timeframe="M15")
    outputs = []
    for item in weekend_source:
        observed = agg.on_market_event(item)
        if observed is not None:
            outputs.append(observed)
    final = agg.complete()
    assert final is not None
    outputs.append(final)
    assert len(outputs) == 2
    assert outputs[0].completed_at == friday + M15_STEP
    assert outputs[1].completed_at == sunday + M15_STEP
    assert agg.dropped_incomplete_buckets > 0
    print("SYNTHETIC_COMPLETED_M15_GAP_CONTRACT=OK")


def _indicator_contract() -> None:
    """З'ясувати фактичну поведінку стану Alligator після M15 gap."""
    from core.workspace_alligator import (
        WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
        WorkspaceAlligatorFilter,
    )

    indicator = WorkspaceAlligatorFilter(
        enabled=True,
        confirmation_mode=WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
        timeframe="M15",
    )
    beginning = datetime(2026, 1, 5, 8, tzinfo=UTC)
    last_observation = None
    for index in range(72):
        timestamp = beginning + M15_STEP * index
        if index >= 60:
            timestamp += timedelta(days=3)
        last_observation = indicator.on_market_event(
            _event(timestamp, timeframe="M15", price=1.10 + index * 1e-5),
            available_at=timestamp + M15_STEP,
        )
        assert last_observation.available_at == timestamp + M15_STEP
        assert last_observation.bars_processed == index + 1
    assert last_observation is not None
    assert len(indicator.observations) == 72
    assert last_observation.warmed_up
    print("SYNTHETIC_ALLIGATOR_STATE_ACROSS_GAP=CONTINUED_NOT_RESET")


def _next_bar_contract() -> None:
    """Відхилити pending entry, коли запланований NEXT_BAR відсутній."""
    from core.workspace_replay_execution import (
        REPLAY_ORDER_STATUS_EXPIRED_NEXT_BAR_GAP,
        WorkspaceReplayExecutionEngine,
        WorkspaceReplayExecutionPolicy,
    )
    from core.workspace_signal import WorkspaceSignalRecord

    signal_time = datetime(2026, 1, 2, 20, 45, tzinfo=UTC)
    first_after_gap = datetime(2026, 1, 4, 22, tzinfo=UTC)
    engine = WorkspaceReplayExecutionEngine(
        workspace_uid="00000000-0000-4000-8000-000000000112",
        broker="CTRADER",
        account_id="DEMO",
        symbol="EURUSD",
        policy=WorkspaceReplayExecutionPolicy(
            fixed_volume=1000.0, maximum_open_positions=1
        ),
    )
    record = WorkspaceSignalRecord(
        timestamp=signal_time,
        signal_uid="t112-12-gap-signal",
        workspace_uid="00000000-0000-4000-8000-000000000112",
        broker="CTRADER",
        account_id="DEMO",
        symbol="EURUSD",
        timeframe="M15",
        source_mode="REPLAY",
        signal_type="MACD_CROSS",
        direction="BUY",
        strength=0.0002,
        macd_state="MACD_CROSS_UP",
        alligator_confirmation="DISABLED",
        spread_status="OK",
        accepted=True,
        reason="T112-12 TEST_ONLY",
    )
    created = engine.queue_signal(record, _event(signal_time, timeframe="M15"))
    assert len(created) == 1
    expired = engine.on_market_event(_event(first_after_gap, timeframe="M15"))
    assert len(expired) == 1
    assert expired[0].event == "VIRTUAL_ORDER_EXPIRED_NEXT_BAR_GAP"
    assert expired[0].details["broker_execution_attempted"] is False
    assert (
        engine.snapshot().orders[0].status == REPLAY_ORDER_STATUS_EXPIRED_NEXT_BAR_GAP
    )
    assert engine.pending_orders_count == 0
    assert engine.active_positions_count == 0
    print("SYNTHETIC_NEXT_BAR_GAP_EXPIRY=OK")


def _read_source(path: Path) -> Iterator[Bar]:
    """Читати 6-колонковий CSV без будь-яких модифікацій."""
    if not path.is_file():
        raise IntegrityError(f"Missing CSV: {path}")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        if tuple(next(reader, ())) != HEADER:
            raise IntegrityError(f"Unexpected CSV header: {path.name}")
        for line, row in enumerate(reader, 2):
            if len(row) != 6:
                raise IntegrityError(f"{path.name}:{line}: columns != 6")
            try:
                timestamp = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
                op, high, low, close, volume = map(float, row[1:])
            except ValueError as parsing_error:
                raise IntegrityError(
                    f"{path.name}:{line}: bad timestamp or OHLC"
                ) from parsing_error
            if timestamp.utcoffset() != timedelta(0):
                raise IntegrityError(f"{path.name}:{line}: timestamp not UTC")
            yield Bar(timestamp, op, high, low, close, volume)


def _audit_symbol(root: Path, symbol: str) -> None:
    """Порівняти gap semantics із зафіксованим T112-11, без нового Replay."""
    aggregator = M15Counter()
    study = GapStudy()
    for part, first in enumerate(FIRST_DATES):
        path = (
            root / symbol / "M1" / f"{first}_{LAST_DATES[part]}_CTRADER_{symbol}_M1.csv"
        )
        count = 0
        for bar in _read_source(path):
            complete = aggregator.add(bar)
            if complete is not None:
                if complete.available_at != complete.timestamp + M15_STEP:
                    raise IntegrityError("Completed M15 time availability mismatch")
                study.add(complete.timestamp)
            count += 1
        assert count == EXPECTED[symbol][part], (symbol, part, count)
    final = aggregator.finish()
    if final is not None:
        study.add(final.timestamp)
    study.finish()
    assert study.bars == EXPECTED_COMPLETE[symbol]
    assert study.gaps == EXPECTED_GAPS[symbol]
    assert study.max_run == EXPECTED_MAX_RUN
    assert study.gaps == study.weekend_gaps + study.weekday_gaps
    print(
        f"symbol={symbol}|complete_m15={study.bars}|m15_gaps={study.gaps}"
        f"|weekend_touching={study.weekend_gaps}"
        f"|non_weekend={study.weekday_gaps}|max_run={study.max_run}"
        f"|missing_m15_slots={study.missing_slots}"
    )
    print(
        f"symbol={symbol}|largest_non_weekend_gap="
        f"{study.largest_weekday_start}->{study.largest_weekday_end}"
        f"|missing_slots={study.largest_weekday_gap}"
    )


def _synthetic() -> None:
    gaps = GapStudy()
    base = datetime(2026, 1, 2, 20, 45, tzinfo=UTC)
    gaps.add(base)
    gaps.add(datetime(2026, 1, 4, 22, tzinfo=UTC))
    gaps.add(datetime(2026, 1, 5, 9, tzinfo=UTC))
    gaps.add(datetime(2026, 1, 5, 9, 15, tzinfo=UTC))
    gaps.add(datetime(2026, 1, 5, 10, tzinfo=UTC))
    gaps.finish()
    assert gaps.gaps == 3
    assert gaps.weekend_gaps == 2 and gaps.weekday_gaps == 1
    assert gaps.max_run == 2
    _aggregation_contract()
    _indicator_contract()
    _next_bar_contract()
    print("SYNTHETIC_REPLAY_GAP_SEMANTICS=OK")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-root", type=Path, default=HISTORY)
    parser.add_argument("--synthetic-only", action="store_true")
    args = parser.parse_args()
    print("T112_12_HISTORICAL_REPLAY_GAP_SEMANTICS")
    print("mode=RM112_T112_12_TEST_ONLY_DATA_ONLY")
    print("entry_exit_production_unchanged=True")
    _synthetic()
    if not args.synthetic_only:
        print(f"history_root={args.history_root}")
        for symbol in SYMBOLS:
            _audit_symbol(args.history_root, symbol)
    print("indicator_gap_state=CONTINUES_CURRENT_STATE_NO_AUTOMATIC_RESET")
    print("new_replay_run=False")
    print("baseline_2025_2026_replay=NOT_RERUN")
    print("market_calendar_completeness=NOT_ASSERTED")
    print("historical_files_modified=False")
    print("production_logic_changed=False")
    print("exit_logic_changed=False")
    print("md7_changed=False")
    print("broker_requests=0")
    print("T112_12_HISTORICAL_REPLAY_GAP_SEMANTICS=OK")


if __name__ == "__main__":
    try:
        main()
    except (IntegrityError, OSError, UnicodeError, csv.Error) as run_error:
        raise SystemExit(f"T112-12 FAILED: {run_error}") from run_error
