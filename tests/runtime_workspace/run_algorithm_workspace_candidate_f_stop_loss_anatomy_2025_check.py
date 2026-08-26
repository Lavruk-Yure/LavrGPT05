# -*- coding: utf-8 -*-
"""RoadMap103 / 7A: анатомія Stop Loss production Candidate F OOS 2025.

Diagnostic-only runner повторює production Candidate F Replay 2025 після 6K
negative-PD recovery та аналізує лише фактичні STOP_LOSS угоди. Production
entry/exit policy не змінюється, альтернативний SL не застосовується, broker
execution не виконується. Мета — зафіксувати, з чого формується initial 1R,
як NEXT_BAR_OPEN змінює entry відносно signal close, коли спрацьовує SL і яку
MFE позиція встигла отримати до закриття.
"""

from __future__ import annotations

import math
import sys
from collections import Counter
from pathlib import Path
from statistics import median

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, TEST_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_profit_guard import (  # noqa: E402
    WorkspaceCandidateFNegativePdRecoveryGuard,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import (  # noqa: E402
    WorkspaceSignalProposal,
    WorkspaceSignalRecord,
)
from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    assert_frozen_oos_snapshot,
    frozen_oos_workspace,
)

EXPECTED_TRADES = 59
EXPECTED_STOP_LOSSES = 9
EXPECTED_NET = -4.05
EXPECTED_PROFIT_FACTOR = 0.7808
EXPECTED_DRAWDOWN = 5.80
PIP = 0.0001
EPSILON = 1e-12


class StopLossAnatomyRuntime(WorkspaceRuntime):
    """Test-only runtime, що зберігає signal і protective close events."""

    def __init__(self, *args, **kwargs) -> None:
        self.signal_events: dict[str, WorkspaceMarketEvent] = {}
        self.close_execution_events: dict[str, WorkspaceMarketEvent] = {}
        super().__init__(*args, **kwargs)

    def _record_signal(
        self,
        event: WorkspaceMarketEvent,
        proposal: WorkspaceSignalProposal,
    ) -> WorkspaceSignalRecord:
        record = super()._record_signal(event, proposal)
        self.signal_events[record.signal_uid] = event
        return record

    def _advance_replay_execution(self, event: WorkspaceMarketEvent) -> None:
        journal_offset = len(self.journal)
        super()._advance_replay_execution(event)
        for entry in self.journal[journal_offset:]:
            if entry.event != "VIRTUAL_POSITION_CLOSED":
                continue
            position_id = str(entry.details.get("position_id") or "").strip()
            if position_id:
                self.close_execution_events[position_id] = event


def _close_enough(actual: float, expected: float, tolerance: float = 0.005) -> bool:
    return abs(float(actual) - float(expected)) <= tolerance


def _risk_usd(stop_distance: float, volume: float) -> float:
    return stop_distance * volume


def _signed_r(value_usd: float, risk_usd: float) -> float:
    if risk_usd <= 0.0:
        raise AssertionError("Initial risk must be positive")
    return value_usd / risk_usd


def _adverse_entry_gap(
    direction: str,
    signal_close: float,
    entry_price: float,
) -> float:
    if direction == "BUY":
        return entry_price - signal_close
    return signal_close - entry_price


def _stop_price(direction: str, entry_price: float, distance: float) -> float:
    if direction == "BUY":
        return entry_price - distance
    return entry_price + distance


def _take_price(direction: str, entry_price: float, distance: float) -> float:
    if direction == "BUY":
        return entry_price + distance * 2.0
    return entry_price - distance * 2.0


def _stop_and_take_touched(
    direction: str,
    event: WorkspaceMarketEvent,
    stop_price: float,
    take_price: float,
) -> tuple[bool, bool]:
    if direction == "BUY":
        return event.low <= stop_price, event.high >= take_price
    return event.high >= stop_price, event.low <= take_price


def _gap_through_stop(
    direction: str,
    event: WorkspaceMarketEvent,
    stop_price: float,
) -> bool:
    if direction == "BUY":
        return event.open <= stop_price
    return event.open >= stop_price


def main() -> None:
    """Запустити production 6K baseline і надрукувати SL anatomy."""
    assert_frozen_oos_snapshot()
    runtime = StopLossAnatomyRuntime(
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

    trades = execution.trade_diagnostics()
    sl_trades = tuple(trade for trade in trades if trade.close_reason == "STOP_LOSS")
    assert len(sl_trades) == EXPECTED_STOP_LOSSES

    basis_counts: Counter[str] = Counter()
    immediate_counts: Counter[str] = Counter()
    stop_gap_through = 0
    ambiguous_stop_first = 0
    favorable_025r = 0
    favorable_050r = 0
    favorable_100r = 0
    risks_usd: list[float] = []
    stop_distances: list[float] = []
    entry_gaps_r: list[float] = []
    mfe_values_r: list[float] = []
    holding_minutes: list[float] = []

    rows: list[str] = []
    for index, trade in enumerate(sl_trades, start=1):
        signal_event = runtime.signal_events.get(trade.signal_uid)
        close_event = runtime.close_execution_events.get(trade.position_id)
        assert signal_event is not None, trade.signal_uid
        assert close_event is not None, trade.position_id

        signal_range = max(signal_event.high - signal_event.low, 0.0)
        spread_floor = signal_event.spread * execution.policy.minimum_spread_multiples
        expected_distance = max(signal_range, spread_floor)
        expected_distance *= execution.policy.stop_range_multiplier
        assert math.isclose(
            trade.stop_loss_distance,
            expected_distance,
            rel_tol=0.0,
            abs_tol=1e-12,
        )

        basis = (
            "SIGNAL_RANGE"
            if signal_range + EPSILON >= spread_floor
            else "SPREAD_FLOOR"
        )
        basis_counts[basis] += 1
        risk_usd = _risk_usd(trade.stop_loss_distance, trade.volume)
        risks_usd.append(risk_usd)
        stop_distances.append(trade.stop_loss_distance)

        adverse_gap = _adverse_entry_gap(
            trade.direction,
            signal_event.close,
            trade.entry_price,
        )
        adverse_gap_r = adverse_gap / trade.stop_loss_distance
        entry_gaps_r.append(adverse_gap_r)

        mfe_r = _signed_r(trade.maximum_favorable_excursion, risk_usd)
        mfe_values_r.append(mfe_r)
        if mfe_r >= 0.25:
            favorable_025r += 1
        if mfe_r >= 0.50:
            favorable_050r += 1
        if mfe_r >= 1.00:
            favorable_100r += 1

        holding_min = trade.holding_seconds / 60.0
        holding_minutes.append(holding_min)
        if holding_min <= 1.0 + EPSILON:
            immediate_counts["<=1M"] += 1
        elif holding_min <= 5.0 + EPSILON:
            immediate_counts["2-5M"] += 1
        elif holding_min <= 15.0 + EPSILON:
            immediate_counts["6-15M"] += 1
        else:
            immediate_counts[">15M"] += 1

        stop_price = _stop_price(
            trade.direction,
            trade.entry_price,
            trade.stop_loss_distance,
        )
        take_price = _take_price(
            trade.direction,
            trade.entry_price,
            trade.stop_loss_distance,
        )
        stop_touched, take_touched = _stop_and_take_touched(
            trade.direction,
            close_event,
            stop_price,
            take_price,
        )
        assert stop_touched
        if take_touched:
            ambiguous_stop_first += 1
        if _gap_through_stop(trade.direction, close_event, stop_price):
            stop_gap_through += 1

        rows.append(
            "    "
            f"{index:02d}. signal:{trade.signal_timestamp.isoformat()} "
            f"{trade.direction} entry:{trade.entry_timestamp.isoformat()} "
            f"close:{trade.close_timestamp.isoformat()} "
            f"basis:{basis} "
            f"range:{signal_range / PIP:.1f}pip "
            f"floor:{spread_floor / PIP:.1f}pip "
            f"SL:{trade.stop_loss_distance / PIP:.1f}pip "
            f"risk:${risk_usd:.2f} "
            f"entry_gap:{adverse_gap / PIP:+.1f}pip/{adverse_gap_r:+.3f}R "
            f"mfe:{mfe_r:.3f}R "
            f"hold:{holding_min:.0f}m "
            f"close_bar:{close_event.open:.5f}/{close_event.high:.5f}/"
            f"{close_event.low:.5f}/{close_event.close:.5f} "
            "gap_through:"
            f"{_gap_through_stop(trade.direction, close_event, stop_price)} "
            f"ambiguous:{take_touched}"
        )

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    print("Algorithm Workspace Candidate F Stop Loss Anatomy 2025 result")
    print("  mode=PRODUCTION_6K_STOP_LOSS_DIAGNOSTIC_ONLY")
    print("  production_logic_changed=False")
    print("  alternative_stop_applied=False")
    print(
        "  baseline="
        f"trades:{summary.opened_trades},wins:{summary.winning_trades},"
        f"losses:{summary.losing_trades},break_even:{summary.break_even_trades},"
        f"net:{summary.net_profit:+.2f},pf:{summary.profit_factor:.4f},"
        f"dd:{summary.maximum_drawdown:.2f}"
    )
    print(f"  stop_loss_trades={len(sl_trades)}")
    print(
        "  stop_distance_formula="
        "max(SIGNAL_M15_HIGH_LOW,SPREAD_X10)*1.0"
    )
    print(
        "  stop_basis="
        f"signal_range:{basis_counts['SIGNAL_RANGE']},"
        f"spread_floor:{basis_counts['SPREAD_FLOOR']}"
    )
    print(
        "  stop_distance_pips="
        f"min:{min(stop_distances) / PIP:.1f},"
        f"median:{median(stop_distances) / PIP:.1f},"
        f"max:{max(stop_distances) / PIP:.1f}"
    )
    print(
        "  initial_risk_usd="
        f"min:{min(risks_usd):.2f},median:{median(risks_usd):.2f},"
        f"max:{max(risks_usd):.2f}"
    )
    print(
        "  next_bar_entry_adverse_gap_r="
        f"min:{min(entry_gaps_r):+.3f},median:{median(entry_gaps_r):+.3f},"
        f"max:{max(entry_gaps_r):+.3f}"
    )
    print(
        "  stopped_after_favorable_excursion="
        f">=0.25R:{favorable_025r},>=0.50R:{favorable_050r},"
        f">=1.00R:{favorable_100r}"
    )
    print(
        "  stop_trade_mfe_r="
        f"min:{min(mfe_values_r):.3f},median:{median(mfe_values_r):.3f},"
        f"max:{max(mfe_values_r):.3f}"
    )
    print(
        "  holding="
        f"<=1m:{immediate_counts['<=1M']},"
        f"2-5m:{immediate_counts['2-5M']},"
        f"6-15m:{immediate_counts['6-15M']},"
        f">15m:{immediate_counts['>15M']},"
        f"median:{median(holding_minutes):.0f}m,"
        f"max:{max(holding_minutes):.0f}m"
    )
    print(f"  close_bar_gap_through_stop={stop_gap_through}")
    print(f"  ambiguous_stop_and_tp_same_m1={ambiguous_stop_first}")
    print("  stop_loss_first_policy_preserved=True")
    print("  chronological_stop_loss_anatomy:")
    for row in rows:
        print(row)
    print("  completed_bars_only=True")
    print("  future_price_used_as_gate=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_STOP_LOSS_ANATOMY_2025_CHECK=OK")


if __name__ == "__main__":
    main()
