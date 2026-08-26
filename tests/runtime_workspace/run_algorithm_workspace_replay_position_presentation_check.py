# run_algorithm_workspace_replay_position_presentation_check.py — Positions UI
# -*- coding: utf-8 -*-
"""Перевірка представлення Replay positions у WSP після RoadMap99_04C.

Тест зберігає RoadMap97 contract для status/close reason і додатково
перевіряє, що position snapshot не плутає час алгоритмічного сигналу з
NEXT_BAR_OPEN entry timestamp. Positions table має окремі колонки Signal та
Opened, а технічний reconciliation status лишається доступним у tooltip.
Broker execution не використовується.
"""

from __future__ import annotations

import ast
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import WORKSPACE_DATA_MODE_REPLAY  # noqa: E402
from core.translation_policy import translation_override_for_key  # noqa: E402
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_replay_execution import (  # noqa: E402
    REPLAY_CLOSE_STOP_LOSS,
    WorkspaceReplayExecutionEngine,
    WorkspaceReplayExecutionPolicy,
)
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402

AREA_PATH = PROJECT_ROOT / "core" / "algorithm_workspace_area.py"


def _market_event(
    timestamp: datetime,
    *,
    open_price: float,
    high: float,
    low: float,
    close: float,
) -> WorkspaceMarketEvent:
    bid = close - 0.0001
    ask = close + 0.0001
    return WorkspaceMarketEvent(
        timestamp=timestamp,
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        bid=bid,
        ask=ask,
        spread=ask - bid,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=1000.0,
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
    )


def _signal(timestamp: datetime) -> WorkspaceSignalRecord:
    return WorkspaceSignalRecord(
        timestamp=timestamp,
        signal_uid="signal-position-presentation-1",
        workspace_uid="00000000-0000-4000-8000-000000000097",
        broker="IB",
        account_id="DUM513747",
        symbol="EURUSD",
        timeframe="M15",
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
        signal_type="MACD_CROSS",
        direction="BUY",
        strength=0.0002,
        macd_state="MACD_CROSS_UP",
        alligator_confirmation="SAME_TIMEFRAME_BULLISH",
        spread_status="OK",
        accepted=True,
        reason="accepted for signal display only",
    )


def _literal_value(node: ast.expr) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Tuple):
        return tuple(_literal_value(item) for item in node.elts)
    raise ValueError(f"Unsupported literal node: {type(node).__name__}")


def _position_columns() -> tuple[tuple[str, str], ...]:
    source = AREA_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id != "POSITION_TABLE_COLUMNS":
            continue
        value = _literal_value(node.value)
        assert isinstance(value, tuple)
        columns: list[tuple[str, str]] = []
        for item in value:
            assert isinstance(item, tuple) and len(item) == 2
            key, label = item
            assert isinstance(key, str) and isinstance(label, str)
            columns.append((key, label))
        return tuple(columns)
    raise AssertionError("POSITION_TABLE_COLUMNS not found")


def main() -> None:
    start = datetime(2026, 8, 7, 8, 0, tzinfo=UTC)
    engine = WorkspaceReplayExecutionEngine(
        workspace_uid="00000000-0000-4000-8000-000000000097",
        broker="IB",
        account_id="DUM513747",
        symbol="EURUSD",
        policy=WorkspaceReplayExecutionPolicy(
            fixed_volume=1000.0,
            maximum_open_positions=1,
        ),
    )

    signal_event = _market_event(
        start,
        open_price=1.1000,
        high=1.1010,
        low=1.0990,
        close=1.1000,
    )
    engine.queue_signal(_signal(start), signal_event)

    fill_event = _market_event(
        start + timedelta(minutes=15),
        open_price=1.1005,
        high=1.1010,
        low=1.1000,
        close=1.1006,
    )
    engine.on_market_event(fill_event)
    active_position = engine.snapshot().positions[0]
    assert active_position.active
    assert active_position.close_reason is None
    assert active_position.signal_timestamp == start.isoformat()
    assert active_position.signal_uid == "signal-position-presentation-1"
    assert active_position.opened_at == fill_event.timestamp.isoformat()
    assert active_position.closed_at is None
    assert active_position.reconciliation_status == "REPLAY_VIRTUAL_ACTIVE"

    close_event = _market_event(
        start + timedelta(minutes=30),
        open_price=1.1000,
        high=1.1005,
        low=1.0980,
        close=1.0985,
    )
    engine.on_market_event(close_event)
    closed_position = engine.snapshot().positions[0]
    assert not closed_position.active
    assert closed_position.close_reason == REPLAY_CLOSE_STOP_LOSS
    assert closed_position.closed_at == close_event.timestamp.isoformat()
    assert closed_position.reconciliation_status == "REPLAY_VIRTUAL_CLOSED_STOP_LOSS"

    columns = _position_columns()
    assert len(columns) == 14
    assert columns[9][0] == "AlgorithmWorkspaceWindow.colPositionSignalTime"
    assert columns[10][0] == "AlgorithmWorkspaceWindow.colOpenedAt"
    assert columns[11][0] == "AlgorithmWorkspaceWindow.colClosedAt"
    assert columns[12][0] == "AlgorithmWorkspaceWindow.colStatus"
    assert columns[13][0] == "AlgorithmWorkspaceWindow.colCloseReason"

    assert (
        translation_override_for_key(
            "AlgorithmWorkspaceWindow.colClosedAt",
            "uk",
        )
        == "Закрито"
    )

    assert (
        translation_override_for_key(
            "AlgorithmWorkspacePositionStatus.open",
            "uk",
        )
        == "Відкрита"
    )
    assert (
        translation_override_for_key(
            "AlgorithmWorkspacePositionStatus.closed",
            "uk",
        )
        == "Закрита"
    )
    assert (
        translation_override_for_key(
            "AlgorithmWorkspacePositionCloseReason.stopLoss",
            "uk",
        )
        == "Stop Loss"
    )
    assert (
        translation_override_for_key(
            "AlgorithmWorkspacePositionCloseReason.profitDrawdown",
            "uk",
        )
        == "Відкат прибутку"
    )

    area_source = AREA_PATH.read_text(encoding="utf-8")
    assert 'state_code = "OPEN" if position.active else "CLOSED"' in area_source
    assert "_position_close_reason_code(position)" in area_source
    assert "position.reconciliation_status" in area_source
    assert "Technical status" in area_source
    assert "AlgorithmWorkspacePositionTooltip.technicalReason" in area_source
    assert 'f"{position.reconciliation_status} • {runtime_status}"' not in area_source

    print("Algorithm Workspace Replay position presentation result")
    print("  active_closed_state_separated=True")
    print("  close_reason_structured=True")
    print("  signal_entry_timestamps_separated=True")
    print("  close_timestamp_preserved=True")
    print("  closed_at_column_visible=True")
    print("  signal_uid_propagated_to_position=True")
    print("  status_column_visible=True")
    print("  close_reason_column_visible=True")
    print("  ukrainian_position_state_localized=True")
    print("  ukrainian_close_reason_localized=True")
    print("  technical_status_preserved_in_tooltip=True")
    print("  technical_reason_preserved_in_tooltip=True")
    print("ALGORITHM_WORKSPACE_REPLAY_POSITION_PRESENTATION_CHECK=OK")


if __name__ == "__main__":
    main()
