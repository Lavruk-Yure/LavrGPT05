# -*- coding: utf-8 -*-
"""RoadMap103 / 7C: домінування однієї M15-свічки перед SL Candidate F.

Diagnostic-only runner повторює production Candidate F Replay 2025 після 6K
negative-PD recovery та вимірює, яку частку 30-хвилинного спрямованого руху
створила остання завершена M15-свічка сигналу. Жоден signal gate, SL, TP,
entry, exit або production policy не змінюється. Майбутня ціна не
використовується як ознака або умова відбору.
"""

from __future__ import annotations

import math
import sys
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import TypedDict

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
EPSILON = 1e-12


class DiagnosticRow(TypedDict):
    """Каузальні ознаки та фактичний результат однієї Replay-угоди."""

    timestamp: datetime
    direction: str
    group: str
    profit: float
    current_m15_r: float
    previous_m15_r: float
    net_30m_r: float
    share_30: float
    abs_share_30: float
    previous_bar_opposed: bool
    close_location: float


class OneBarImpulseRuntime(WorkspaceRuntime):
    """Test-only runtime, що зберігає завершені strategy bars для 7C."""

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


def _directional_close_location(
    direction: str,
    event: WorkspaceMarketEvent,
) -> float:
    width = max(event.high - event.low, EPSILON)
    if direction == "BUY":
        return (event.close - event.low) / width
    return (event.high - event.close) / width


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


def _format_counts(counts: dict[str, int]) -> str:
    return (
        f"SL:{counts['STOP_LOSS']},"
        f"OTHER_LOSS:{counts['OTHER_LOSS']},"
        f"WIN:{counts['WIN']},"
        f"BREAK_EVEN:{counts['BREAK_EVEN']}"
    )


def main() -> None:
    """Повторити production 6K і виміряти one-bar impulse dominance."""
    assert_frozen_oos_snapshot()
    runtime = OneBarImpulseRuntime(
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

    rows: list[DiagnosticRow] = []
    group_values: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for trade in execution.trade_diagnostics():
        index = event_index.get(trade.signal_timestamp)
        assert index is not None, trade.signal_timestamp
        assert index >= 2, trade.signal_timestamp
        window = strategy_events[index - 2 : index + 1]  # noqa: E203
        previous_2 = window[0]
        previous_1 = window[1]
        signal_event = window[2]
        stop_distance = trade.stop_loss_distance
        assert stop_distance > 0.0

        current_m15_r = (
            _directional_delta(
                trade.direction,
                signal_event.close,
                previous_1.close,
            )
            / stop_distance
        )
        previous_m15_r = (
            _directional_delta(
                trade.direction,
                previous_1.close,
                previous_2.close,
            )
            / stop_distance
        )
        net_30m_r = current_m15_r + previous_m15_r
        if net_30m_r > EPSILON:
            share_30 = current_m15_r / net_30m_r
        else:
            share_30 = math.inf
        abs_share_30 = current_m15_r / max(
            abs(current_m15_r) + abs(previous_m15_r),
            EPSILON,
        )
        previous_bar_opposed = previous_m15_r <= 0.0
        close_location = _directional_close_location(
            trade.direction,
            signal_event,
        )
        group = _group_name(trade.final_profit, trade.close_reason)

        for name, value in (
            ("current_m15_r", current_m15_r),
            ("previous_m15_r", previous_m15_r),
            ("net_30m_r", net_30m_r),
            ("abs_share_30", abs_share_30),
            ("close_location", close_location),
        ):
            assert math.isfinite(value)
            group_values[group][name].append(value)
        if math.isfinite(share_30):
            group_values[group]["share_30"].append(share_30)

        rows.append(
            {
                "timestamp": trade.signal_timestamp,
                "direction": trade.direction,
                "group": group,
                "profit": float(trade.final_profit),
                "current_m15_r": current_m15_r,
                "previous_m15_r": previous_m15_r,
                "net_30m_r": net_30m_r,
                "share_30": share_30,
                "abs_share_30": abs_share_30,
                "previous_bar_opposed": previous_bar_opposed,
                "close_location": close_location,
            }
        )

    def evaluate_rule(
        rule_predicate: Callable[[DiagnosticRow], bool],
    ) -> tuple[dict[str, int], float]:
        rule_counts: dict[str, int] = defaultdict(int)
        rule_observed_pnl = 0.0
        for row in rows:
            if rule_predicate(row):
                rule_counts[row["group"]] += 1
                rule_observed_pnl += row["profit"]
        return rule_counts, rule_observed_pnl

    rules = (
        (
            "dominance_share30>=1.00",
            lambda row: float(row["share_30"]) >= 1.00,
            {"STOP_LOSS": 6, "OTHER_LOSS": 2, "WIN": 9, "BREAK_EVEN": 0},
            -10.24,
        ),
        (
            "dominance_share30>=1.10",
            lambda row: float(row["share_30"]) >= 1.10,
            {"STOP_LOSS": 6, "OTHER_LOSS": 2, "WIN": 8, "BREAK_EVEN": 0},
            -10.52,
        ),
        (
            "dominance_share30>=1.20",
            lambda row: float(row["share_30"]) >= 1.20,
            {"STOP_LOSS": 4, "OTHER_LOSS": 1, "WIN": 6, "BREAK_EVEN": 0},
            -5.01,
        ),
        (
            "dominance_share30>=1.30",
            lambda row: float(row["share_30"]) >= 1.30,
            {"STOP_LOSS": 3, "OTHER_LOSS": 1, "WIN": 5, "BREAK_EVEN": 0},
            -3.27,
        ),
        (
            "dominance>=1.00_and_close_location>=0.90",
            lambda row: (
                float(row["share_30"]) >= 1.00 and float(row["close_location"]) >= 0.90
            ),
            {"STOP_LOSS": 5, "OTHER_LOSS": 1, "WIN": 4, "BREAK_EVEN": 0},
            -8.63,
        ),
    )

    evaluated_rules: list[tuple[str, dict[str, int], float]] = []
    for name, predicate, expected_counts, expected_pnl in rules:
        counts, observed_pnl = evaluate_rule(predicate)
        for group, expected in expected_counts.items():
            assert counts[group] == expected, (name, group, counts[group], expected)
        assert _close_enough(observed_pnl, expected_pnl, 0.005), (
            name,
            observed_pnl,
            expected_pnl,
        )
        evaluated_rules.append((name, counts, observed_pnl))

    opposed_counts, opposed_pnl = evaluate_rule(
        lambda row: bool(row["previous_bar_opposed"])
    )
    assert opposed_counts["STOP_LOSS"] == 6
    assert opposed_counts["OTHER_LOSS"] == 2
    assert opposed_counts["WIN"] == 9
    assert opposed_counts["BREAK_EVEN"] == 0
    assert _close_enough(opposed_pnl, -10.24, 0.005)

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    print("Algorithm Workspace Candidate F SL One-Bar Impulse Dominance 2025 result")
    print("  mode=PRODUCTION_6K_CAUSAL_ONE_BAR_DOMINANCE_DIAGNOSTIC_ONLY")
    print("  production_logic_changed=False")
    print("  signal_filter_applied=False")
    print("  counterfactual_filter_applied=False")
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
        "  dominance_definition="
        "last_M15_directional_close_move/net_30m_directional_close_move"
    )
    print("  dominance_share30>=1.00_means=previous_M15_close_move_nonpositive")
    print("  group_medians:")
    for group in ("STOP_LOSS", "OTHER_LOSS", "WIN"):
        print(
            f"    {group}="
            f"current_M15:{_median(group_values[group]['current_m15_r']):+.3f}R,"
            f"previous_M15:{_median(group_values[group]['previous_m15_r']):+.3f}R,"
            f"net_30m:{_median(group_values[group]['net_30m_r']):+.3f}R,"
            f"share30:{_median(group_values[group]['share_30']):.3f},"
            f"abs_share30:{_median(group_values[group]['abs_share_30']):.3f},"
            f"close_location:{_median(group_values[group]['close_location']):.3f}"
        )
    print(
        "  previous_M15_nonpositive="
        f"{_format_counts(opposed_counts)},observed_flagged_pnl:{opposed_pnl:+.2f}"
    )
    print("  diagnostic_rule_matrix:")
    for name, counts, observed_pnl in evaluated_rules:
        print(
            f"    {name}: {_format_counts(counts)},"
            f"observed_flagged_pnl:{observed_pnl:+.2f}"
        )
    print("  observed_flagged_pnl_is_not_counterfactual=True")
    print("  completed_bars_only=True")
    print("  causal_signal_and_prior_bars_only=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_SL_ONE_BAR_IMPULSE_DOMINANCE_2025_CHECK=OK")


if __name__ == "__main__":
    main()
