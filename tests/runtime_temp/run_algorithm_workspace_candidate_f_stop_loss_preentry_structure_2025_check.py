# -*- coding: utf-8 -*-
"""RoadMap103 / 7B: causal pre-entry structure of Candidate F SL trades.

Diagnostic-only runner repeats the production Candidate F Replay 2025 after 6K
negative-PD recovery and compares only information available by the signal/entry
moment. No signal gate, SL, TP, entry, exit or production policy is changed.
The goal is to see whether the 9 STOP_LOSS trades already differ structurally
from winning and other losing trades before any future price is known.
"""

from __future__ import annotations

import math
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, TEST_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    assert_frozen_oos_snapshot,
    frozen_oos_workspace,
)

from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_profit_guard import (  # noqa: E402
    WorkspaceCandidateFNegativePdRecoveryGuard,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402

EXPECTED_TRADES = 59
EXPECTED_STOP_LOSSES = 9
EXPECTED_NET = -4.05
EXPECTED_PROFIT_FACTOR = 0.7808
EXPECTED_DRAWDOWN = 5.80
PIP = 0.0001
EPSILON = 1e-12


class StopLossPreEntryRuntime(WorkspaceRuntime):
    """Test-only runtime that retains strategy bars for causal diagnostics."""

    def __init__(self, *args, **kwargs) -> None:
        self.strategy_events: dict[datetime, WorkspaceMarketEvent] = {}
        super().__init__(*args, **kwargs)

    def _accept_market_event(
        self,
        event: WorkspaceMarketEvent,
        *,
        origin: str,
        warmup_only: bool = False,
        advance_replay_execution: bool = True,
    ) -> None:
        if event.timeframe == self.context.timeframe:
            self.strategy_events[event.timestamp] = event
        super()._accept_market_event(
            event,
            origin=origin,
            warmup_only=warmup_only,
            advance_replay_execution=advance_replay_execution,
        )


def _close_enough(actual: float, expected: float, tolerance: float = 0.005) -> bool:
    return abs(float(actual) - float(expected)) <= tolerance


def _directional_delta(direction: str, newer: float, older: float) -> float:
    if direction == "BUY":
        return newer - older
    return older - newer


def _directional_body(direction: str, event: WorkspaceMarketEvent) -> float:
    return _directional_delta(direction, event.close, event.open)


def _directional_close_location(
    direction: str,
    event: WorkspaceMarketEvent,
) -> float:
    width = max(event.high - event.low, EPSILON)
    if direction == "BUY":
        return (event.close - event.low) / width
    return (event.high - event.close) / width


def _adverse_wick(direction: str, event: WorkspaceMarketEvent) -> float:
    if direction == "BUY":
        return max(min(event.open, event.close) - event.low, 0.0)
    return max(event.high - max(event.open, event.close), 0.0)


def _directional_range_location(
    direction: str,
    close: float,
    events: tuple[WorkspaceMarketEvent, ...],
) -> float:
    high = max(event.high for event in events)
    low = min(event.low for event in events)
    width = max(high - low, EPSILON)
    if direction == "BUY":
        return (close - low) / width
    return (high - close) / width


def _trend_consistency(
    direction: str,
    events: tuple[WorkspaceMarketEvent, ...],
) -> float:
    if len(events) < 2:
        return 0.0
    moves = 0
    total = 0
    for older, newer in zip(events, events[1:]):
        total += 1
        if _directional_delta(direction, newer.close, older.close) > 0.0:
            moves += 1
    return moves / total


def _group_name(final_profit: float, close_reason: str) -> str:
    if close_reason == "STOP_LOSS":
        return "STOP_LOSS"
    if final_profit > EPSILON:
        return "WIN"
    if final_profit < -EPSILON:
        return "OTHER_LOSS"
    return "BREAK_EVEN"


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(median(values))


def main() -> None:
    """Repeat production 6K and compare causal pre-entry structures."""
    assert_frozen_oos_snapshot()
    runtime = StopLossPreEntryRuntime(
        frozen_oos_workspace(),
        algorithm_factory=create_registered_workspace_algorithm,
    )
    assert isinstance(
        runtime.profit_drawdown_guard,
        WorkspaceCandidateFNegativePdRecoveryGuard,
    )

    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()

    summary = runtime.historical_summary
    execution = runtime.replay_execution
    assert summary is not None
    assert execution is not None
    assert summary.opened_trades == EXPECTED_TRADES
    assert summary.close_reason_count("STOP_LOSS") == EXPECTED_STOP_LOSSES
    assert _close_enough(summary.net_profit, EXPECTED_NET)
    assert summary.profit_factor is not None
    assert _close_enough(summary.profit_factor, EXPECTED_PROFIT_FACTOR, 0.00005)
    assert _close_enough(summary.maximum_drawdown, EXPECTED_DRAWDOWN)

    strategy_events = tuple(
        runtime.strategy_events[timestamp]
        for timestamp in sorted(runtime.strategy_events)
    )
    event_index = {
        event.timestamp: index for index, event in enumerate(strategy_events)
    }

    metrics: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    sl_rows: list[str] = []
    group_counts: dict[str, int] = defaultdict(int)

    for trade in execution.trade_diagnostics():
        index = event_index.get(trade.signal_timestamp)
        assert index is not None, trade.signal_timestamp
        assert index >= 4, trade.signal_timestamp
        window = strategy_events[index - 4 : index + 1]  # noqa: E203
        signal_event = window[-1]
        stop_distance = trade.stop_loss_distance
        assert stop_distance > 0.0

        pre15_r = (
            _directional_delta(
                trade.direction,
                signal_event.close,
                window[-2].close,
            )
            / stop_distance
        )
        pre30_r = (
            _directional_delta(
                trade.direction,
                signal_event.close,
                window[-3].close,
            )
            / stop_distance
        )
        pre60_r = (
            _directional_delta(
                trade.direction,
                signal_event.close,
                window[-5].close,
            )
            / stop_distance
        )
        body_r = _directional_body(trade.direction, signal_event) / stop_distance
        close_loc = _directional_close_location(trade.direction, signal_event)
        adverse_wick_r = _adverse_wick(trade.direction, signal_event) / stop_distance
        recent_range_r = (
            max(event.high for event in window) - min(event.low for event in window)
        ) / stop_distance
        range_loc = _directional_range_location(
            trade.direction,
            signal_event.close,
            window,
        )
        consistency = _trend_consistency(trade.direction, window)
        previous_range = max(window[-2].high - window[-2].low, EPSILON)
        signal_range = signal_event.high - signal_event.low
        range_expansion = signal_range / previous_range
        previous_gap_minutes = (
            signal_event.timestamp - window[-2].timestamp
        ).total_seconds() / 60.0

        group = _group_name(trade.final_profit, trade.close_reason)
        group_counts[group] += 1
        values = {
            "pre15_r": pre15_r,
            "pre30_r": pre30_r,
            "pre60_r": pre60_r,
            "body_r": body_r,
            "close_loc": close_loc,
            "adverse_wick_r": adverse_wick_r,
            "recent_range_r": recent_range_r,
            "range_loc": range_loc,
            "consistency": consistency,
            "range_expansion": range_expansion,
            "prev_gap_min": previous_gap_minutes,
        }
        for name, value in values.items():
            assert math.isfinite(value)
            metrics[group][name].append(value)

        if trade.close_reason == "STOP_LOSS":
            sl_rows.append(
                "    "
                f"{len(sl_rows) + 1:02d}. {trade.signal_timestamp.isoformat()} "
                f"{trade.direction} "
                f"SL:{stop_distance / PIP:.1f}pip "
                f"pre15:{pre15_r:+.3f}R pre30:{pre30_r:+.3f}R "
                f"pre60:{pre60_r:+.3f}R body:{body_r:+.3f}R "
                f"close_loc:{close_loc:.3f} wick:{adverse_wick_r:.3f}R "
                f"range5:{recent_range_r:.3f}R "
                f"range_loc:{range_loc:.3f} "
                f"consistency:{consistency:.2f} "
                f"range_expand:{range_expansion:.2f}"
            )

    assert group_counts["STOP_LOSS"] == EXPECTED_STOP_LOSSES
    assert group_counts["WIN"] == summary.winning_trades
    assert group_counts["OTHER_LOSS"] + group_counts["STOP_LOSS"] == (
        summary.losing_trades
    )
    assert group_counts["BREAK_EVEN"] == summary.break_even_trades

    metric_order = (
        ("pre15_r", "pre15_R", "+.3f"),
        ("pre30_r", "pre30_R", "+.3f"),
        ("pre60_r", "pre60_R", "+.3f"),
        ("body_r", "signal_body_R", "+.3f"),
        ("close_loc", "signal_close_location", ".3f"),
        ("adverse_wick_r", "adverse_wick_R", ".3f"),
        ("recent_range_r", "recent_5bar_range_R", ".3f"),
        ("range_loc", "close_location_in_5bar_range", ".3f"),
        ("consistency", "directional_consistency_4", ".3f"),
        ("range_expansion", "signal_vs_previous_range", ".3f"),
    )

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    print("Algorithm Workspace Candidate F SL Pre-Entry Structure 2025 result")
    print("  mode=PRODUCTION_6K_CAUSAL_PREENTRY_DIAGNOSTIC_ONLY")
    print("  production_logic_changed=False")
    print("  signal_filter_applied=False")
    print("  alternative_stop_applied=False")
    print("  future_price_used_as_feature=False")
    print(
        "  baseline="
        f"trades:{summary.opened_trades},wins:{summary.winning_trades},"
        f"losses:{summary.losing_trades},break_even:{summary.break_even_trades},"
        f"net:{summary.net_profit:+.2f},pf:{summary.profit_factor:.4f},"
        f"dd:{summary.maximum_drawdown:.2f}"
    )
    print(
        "  groups="
        f"stop_loss:{group_counts['STOP_LOSS']},"
        f"other_loss:{group_counts['OTHER_LOSS']},"
        f"win:{group_counts['WIN']},"
        f"break_even:{group_counts['BREAK_EVEN']}"
    )
    print("  group_medians:")
    for key, label, fmt in metric_order:
        stop_value = _median(metrics["STOP_LOSS"][key])
        other_loss_value = _median(metrics["OTHER_LOSS"][key])
        win_value = _median(metrics["WIN"][key])
        print(
            f"    {label}="
            f"SL:{format(stop_value, fmt)},"
            f"OTHER_LOSS:{format(other_loss_value, fmt)},"
            f"WIN:{format(win_value, fmt)}"
        )
    print("  chronological_stop_loss_preentry_structure:")
    for row in sl_rows:
        print(row)
    print("  completed_bars_only=True")
    print("  causal_signal_and_prior_bars_only=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_SL_PREENTRY_STRUCTURE_2025_CHECK=OK")


if __name__ == "__main__":
    main()
