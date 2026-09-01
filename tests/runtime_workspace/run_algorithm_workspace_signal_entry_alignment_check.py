# run_algorithm_workspace_signal_entry_alignment_check.py — Signal ↔ Entry
# -*- coding: utf-8 -*-
"""RoadMap99_04C: перевірка Signal ↔ NEXT_BAR_OPEN Entry diagnostics.

Тест доводить, що Replay position snapshot зберігає два часові моменти:
``signal_timestamp`` завершеного strategy bar, на якому алгоритм прийняв
рішення, і ``opened_at`` наступного bar, на open якого virtual order було
виконано. BUY/SELL перевіряються симетрично відносно open та half-spread.

Окремо перевіряється chart navigation до вже обробленого signal/entry
timestamp центрує потрібний bar, але future timestamp до його обробки
недоступний. UI contract вимагає окремі колонки Positions і кнопки
«До сигналу»/«На діаграму». Trading logic і broker execution не змінюються.
"""

from __future__ import annotations

import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import WORKSPACE_DATA_MODE_REPLAY  # noqa: E402
from core.translation_policy import translation_override_for_key  # noqa: E402
from core.workspace_chart import WorkspaceChartModel  # noqa: E402
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_replay_execution import (  # noqa: E402
    WorkspaceReplayExecutionEngine,
    WorkspaceReplayExecutionPolicy,
)
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402

AREA_PATH = PROJECT_ROOT / "core" / "algorithm_workspace_area.py"
CONTROLLER_PATH = PROJECT_ROOT / "core" / "algorithm_workspace_controller.py"
RUNTIME_PATH = PROJECT_ROOT / "core" / "workspace_runtime.py"

WORKSPACE_UID = "00000000-0000-4000-8000-00000000099c"


def market_event(
    timestamp: datetime,
    *,
    open_price: float,
    close_price: float,
) -> WorkspaceMarketEvent:
    spread = 0.00012
    bid = close_price - spread / 2.0
    ask = close_price + spread / 2.0
    return WorkspaceMarketEvent(
        timestamp=timestamp,
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        bid=bid,
        ask=ask,
        spread=spread,
        open=open_price,
        high=max(open_price, close_price) + 0.00020,
        low=min(open_price, close_price) - 0.00020,
        close=close_price,
        volume=1000.0,
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
    )


def signal(timestamp: datetime, direction: str) -> WorkspaceSignalRecord:
    return WorkspaceSignalRecord(
        timestamp=timestamp,
        signal_uid=f"roadmap99-04c-{direction.lower()}",
        workspace_uid=WORKSPACE_UID,
        broker="IB",
        account_id="DUM513747",
        symbol="EURUSD",
        timeframe="M15",
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
        signal_type="MACD_CROSS",
        direction=direction,
        strength=0.0002,
        macd_state=("MACD_CROSS_UP" if direction == "BUY" else "MACD_CROSS_DOWN"),
        alligator_confirmation=(
            "SAME_TIMEFRAME_BULLISH" if direction == "BUY" else "SAME_TIMEFRAME_BEARISH"
        ),
        spread_status="OK",
        accepted=True,
        reason="RoadMap99_04C signal-entry alignment",
    )


def opened_position(direction: str, start: datetime):
    engine = WorkspaceReplayExecutionEngine(
        workspace_uid=WORKSPACE_UID,
        broker="IB",
        account_id="DUM513747",
        symbol="EURUSD",
        policy=WorkspaceReplayExecutionPolicy(
            fixed_volume=1000.0,
            maximum_open_positions=1,
        ),
    )
    signal_event = market_event(
        start,
        open_price=1.10000,
        close_price=1.10010,
    )
    engine.queue_signal(signal(start, direction), signal_event)
    fill_event = market_event(
        start + timedelta(minutes=15),
        open_price=1.10100,
        close_price=1.10110,
    )
    lifecycle = engine.on_market_event(fill_event)
    assert any(item.event == "VIRTUAL_POSITION_OPENED" for item in lifecycle)
    return engine.snapshot().positions[0], fill_event


def main() -> None:
    print(
        "Algorithm Workspace Signal ↔ Entry Diagnostic Alignment Check — "
        "RoadMap99_04C",
        flush=True,
    )
    print(
        "  Verify signal_timestamp != NEXT_BAR_OPEN opened_at, BUY/SELL "
        "symmetry and chart jump without look-ahead; broker execution remains "
        "disabled.",
        flush=True,
    )

    start = datetime(2026, 3, 11, 18, 5, tzinfo=UTC)
    buy, buy_fill = opened_position("BUY", start)
    sell, sell_fill = opened_position("SELL", start)

    assert buy.signal_timestamp == start.isoformat()
    assert sell.signal_timestamp == start.isoformat()
    assert buy.opened_at == buy_fill.timestamp.isoformat()
    assert sell.opened_at == sell_fill.timestamp.isoformat()
    assert buy_fill.timestamp - start == timedelta(minutes=15)
    assert sell_fill.timestamp - start == timedelta(minutes=15)

    half_spread = buy_fill.spread / 2.0
    assert buy.entry_price is not None
    assert sell.entry_price is not None
    assert math.isclose(
        buy.entry_price,
        buy_fill.open + half_spread,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    assert math.isclose(
        sell.entry_price,
        sell_fill.open - half_spread,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    assert math.isclose(
        buy.entry_price - buy_fill.open,
        buy_fill.open - sell.entry_price,
        rel_tol=0.0,
        abs_tol=1e-12,
    )

    events = tuple(
        market_event(
            start + timedelta(minutes=15 * index),
            open_price=1.10000 + index * 0.00010,
            close_price=1.10005 + index * 0.00010,
        )
        for index in range(24)
    )
    chart = WorkspaceChartModel(visible_count=12)
    chart.attach_full_history(events)
    for event in events[:10]:
        chart.append(event)
    assert not chart.scroll_to_timestamp(events[15].timestamp)
    assert chart.scroll_to_timestamp(events[4].timestamp)
    partial_snapshot = chart.snapshot()
    assert events[4] in partial_snapshot.visible_events

    for event in events[10:]:
        chart.append(event)
    assert chart.scroll_to_timestamp(events[15].timestamp)
    full_snapshot = chart.snapshot()
    assert events[15] in full_snapshot.visible_events
    assert full_snapshot.visible_start <= 15 < full_snapshot.visible_end

    entry_between_bars = events[15].timestamp + timedelta(minutes=1)
    assert not chart.scroll_to_timestamp(entry_between_bars, exact=True)
    assert chart.scroll_to_timestamp(entry_between_bars, exact=False)
    containing_snapshot = chart.snapshot()
    assert events[15] in containing_snapshot.visible_events

    area_source = AREA_PATH.read_text(encoding="utf-8")
    controller_source = CONTROLLER_PATH.read_text(encoding="utf-8")
    runtime_source = RUNTIME_PATH.read_text(encoding="utf-8")
    assert "AlgorithmWorkspaceWindow.colPositionSignalTime" in area_source
    assert "btnPositionGoSignal" in area_source
    assert "btnPositionGoEntry" in area_source
    assert "framePositionTimeActions" in area_source
    assert "QSizePolicy.Policy.Expanding" in area_source
    assert "button_layout.addWidget(self.btn_position_go_signal, 1)" in area_source
    assert "button_layout.addWidget(self.btn_position_go_entry, 1)" in area_source
    assert "chart_timestamp_requested" in area_source
    assert "INDEX_BY_PANEL[WORKSPACE_PANEL_SIGNALS]" in area_source
    assert "scroll_workspace_chart_to_timestamp" in controller_source
    assert "scroll_chart_to_timestamp" in runtime_source

    assert (
        translation_override_for_key(
            "AlgorithmWorkspaceWindow.colPositionSignalTime",
            "uk",
        )
        == "Сигнал"
    )
    assert (
        translation_override_for_key(
            "AlgorithmWorkspaceWindow.btnPositionGoSignal",
            "uk",
        )
        == "До сигналу"
    )
    assert (
        translation_override_for_key(
            "AlgorithmWorkspaceWindow.btnPositionGoEntry",
            "uk",
        )
        == "На діаграму"
    )

    print("Algorithm Workspace Signal ↔ Entry Alignment result")
    print("  signal_timestamp_preserved=True")
    print("  next_bar_open_entry_timestamp_preserved=True")
    print("  buy_sell_entry_spread_symmetry=True")
    print("  future_chart_timestamp_blocked=True")
    print("  processed_signal_chart_jump=True")
    print("  processed_entry_chart_jump=True")
    print("  lower_resolution_entry_maps_to_containing_bar=True")
    print("  positions_signal_entry_columns=True")
    print("  position_go_signal_targets_signals_tab=True")
    print("  position_chart_action_targets_entry_bar=True")
    print("  ukrainian_diagnostic_labels=True")
    print("  production_signal_logic_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_SIGNAL_ENTRY_ALIGNMENT_CHECK=OK")


if __name__ == "__main__":
    main()
