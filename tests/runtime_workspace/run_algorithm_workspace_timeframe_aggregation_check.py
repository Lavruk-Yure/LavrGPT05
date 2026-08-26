# -*- coding: utf-8 -*-
"""Перевірка aggregation завершених старших Replay bars."""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import WORKSPACE_DATA_MODE_REPLAY  # noqa: E402
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_timeframe_aggregation import (  # noqa: E402
    WorkspaceTimeframeAggregationError,
    WorkspaceTimeframeAggregator,
)


def _event(index: int, close: float | None = None) -> WorkspaceMarketEvent:
    value = close if close is not None else 1.1000 + index * 0.0001
    spread = 0.00012
    return WorkspaceMarketEvent(
        timestamp=datetime(2026, 8, 2, 8, 0, tzinfo=UTC)
        + timedelta(minutes=15 * index),
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        bid=value - spread / 2.0,
        ask=value + spread / 2.0,
        spread=spread,
        open=value - 0.00005,
        high=value + 0.00020,
        low=value - 0.00020,
        close=value,
        volume=100.0 + index,
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
    )


def main() -> None:
    aggregator = WorkspaceTimeframeAggregator(
        source_timeframe="M15",
        target_timeframe="H1",
    )
    outputs = []
    for index in range(9):
        completed = aggregator.on_market_event(_event(index))
        if completed is not None:
            outputs.append(completed)

    assert len(outputs) == 2
    first = outputs[0]
    assert first.event.timestamp == datetime(2026, 8, 2, 8, 0, tzinfo=UTC)
    assert first.completed_at == datetime(2026, 8, 2, 9, 0, tzinfo=UTC)
    assert first.source_bars == 4
    assert first.event.open == _event(0).open
    assert first.event.close == _event(3).close
    assert first.event.high == max(_event(index).high for index in range(4))
    assert first.event.low == min(_event(index).low for index in range(4))
    assert first.event.volume == sum(_event(index).volume for index in range(4))
    assert aggregator.active_source_bars == 1

    changed_future = WorkspaceTimeframeAggregator(
        source_timeframe="M15",
        target_timeframe="H1",
    )
    changed_outputs = []
    for index in range(9):
        event = _event(index)
        if index >= 5:
            changed_close = event.close + 0.5000
            event = replace(
                event,
                open=changed_close,
                high=changed_close + 0.00020,
                low=changed_close - 0.00020,
                close=changed_close,
                bid=changed_close - 0.00006,
                ask=changed_close + 0.00006,
            )
        completed = changed_future.on_market_event(event)
        if completed is not None:
            changed_outputs.append(completed)
    assert changed_outputs[0] == first

    duplicate_blocked = False
    duplicate = WorkspaceTimeframeAggregator(
        source_timeframe="M15",
        target_timeframe="H1",
    )
    duplicate.on_market_event(_event(0))
    try:
        duplicate.on_market_event(_event(0))
    except WorkspaceTimeframeAggregationError:
        duplicate_blocked = True
    assert duplicate_blocked

    misaligned_blocked = False
    try:
        duplicate = WorkspaceTimeframeAggregator(
            source_timeframe="M15",
            target_timeframe="H1",
        )
        duplicate.on_market_event(
            replace(_event(0), timestamp=_event(0).timestamp + timedelta(minutes=1))
        )
    except WorkspaceTimeframeAggregationError:
        misaligned_blocked = True
    assert misaligned_blocked

    missing = WorkspaceTimeframeAggregator(
        source_timeframe="M15",
        target_timeframe="H1",
    )
    assert missing.on_market_event(_event(0)) is None
    assert missing.on_market_event(_event(1)) is None
    assert missing.on_market_event(_event(3)) is None
    assert missing.on_market_event(_event(4)) is None
    assert missing.last_boundary_crossed
    assert missing.last_boundary_was_incomplete
    assert missing.completed_bars == 0
    assert missing.dropped_incomplete_buckets == 1

    skipped = WorkspaceTimeframeAggregator(
        source_timeframe="M15",
        target_timeframe="H1",
    )
    for index in range(4):
        assert skipped.on_market_event(_event(index)) is None
    skipped_output = skipped.on_market_event(_event(12))
    assert skipped_output is not None
    assert skipped.last_boundary_crossed
    assert skipped.last_boundary_was_incomplete
    assert skipped.completed_bars == 1
    assert skipped.dropped_incomplete_buckets == 2

    print("Algorithm Workspace Timeframe Aggregation result")
    print("  source_timeframe=M15")
    print("  target_timeframe=H1")
    print("  completed_bars=2")
    print("  only_closed_higher_bars=True")
    print("  incomplete_bucket_not_emitted=True")
    print("  skipped_higher_buckets_detected=True")
    print("  duplicate_blocked=True")
    print("  misaligned_timestamp_blocked=True")
    print("  future_change_does_not_change_past=True")
    print("  deterministic=True")
    print("ALGORITHM_WORKSPACE_TIMEFRAME_AGGREGATION_CHECK=OK")


if __name__ == "__main__":
    main()
