# -*- coding: utf-8 -*-
"""RoadMap102 / 6J: full Replay two-step negative-PD recovery OOS 2025.

Runner не змінює production-код. Frozen Candidate F Replay 2025
повторюється з fixed test-only exit lifecycle з RoadMap102/6F і однією
структурною causal поправкою з 6I.

Після negative PROFIT_DRAWDOWN позиція переходить у RECOVERY_PENDING.
Recovery до current PnL >= 0R закриває позицію негайно. Після другої
завершеної майбутньої M1 позиція закривається early-abort, якщо і перший,
і другий M1 step були непозитивними. Інакше recovery window триває до
третьої M1, де за відсутності recovery виконується timeout close.
Початкові SL/TP мають пріоритет. Positive-PD production close лишається
негайним. PASS не залежить від PnL/PF/DD.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, TEST_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_ownership import WorkspacePositionSnapshot  # noqa: E402
from core.workspace_profit_guard import (  # noqa: E402
    WORKSPACE_PROFIT_ACTION_CLOSE,
    WORKSPACE_PROFIT_ACTION_HOLD,
    WorkspaceProfitDrawdownGuard,
    WorkspaceProfitProtectionDecision,
    WorkspaceProfitProtectionPolicy,
)
from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    FrozenOosRuntime,
    assert_frozen_oos_snapshot,
    frozen_oos_workspace,
)

RECOVERY_WINDOW_M1 = 3
EARLY_ABORT_EVENT_INDEX = 2
BASELINE_TRADES = 59
BASELINE_WINS = 31
BASELINE_LOSSES = 27
BASELINE_BREAK_EVEN = 1
BASELINE_NET = -5.90
BASELINE_PROFIT_FACTOR = 0.6895
BASELINE_DRAWDOWN = 6.90
FIXED_6F_NET = -4.34
FIXED_6F_PROFIT_FACTOR = 0.7688
FIXED_6F_DRAWDOWN = 5.78
BASELINE_MACD_QUALITY_PASS = 414
BASELINE_MACD_QUALITY_REJECT = 2626
BASELINE_ALLIGATOR_ALLOW = 59
BASELINE_ALLIGATOR_REJECT = 357
NUMERIC_EPSILON = 1e-9


@dataclass(slots=True)
class PendingRecovery:
    """Mutable state одного test-only negative-PD recovery window."""

    position_id: str
    trigger_timestamp: datetime
    last_timestamp: datetime
    trigger_profit: float
    previous_profit: float
    completed_future_events: int = 0
    first_step_nonpositive: bool | None = None


class WorkspaceNegativePdTwoStepRecoveryGuard:
    """Production PD guard плюс recovery і M2 two-step early-abort."""

    def __init__(
        self,
        policy: WorkspaceProfitProtectionPolicy,
        recovery_window_m1: int,
    ) -> None:
        if recovery_window_m1 <= EARLY_ABORT_EVENT_INDEX:
            raise ValueError("recovery_window_m1 must exceed early-abort index")
        self.policy = policy
        self.recovery_window_m1 = int(recovery_window_m1)
        self.production_guard = WorkspaceProfitDrawdownGuard(policy)
        self.pending: dict[str, PendingRecovery] = {}
        self.started_position_ids: set[str] = set()
        self.recovery_close_ids: set[str] = set()
        self.early_abort_close_ids: set[str] = set()
        self.timeout_close_ids: set[str] = set()

    @staticmethod
    def _hold(
        decision: WorkspaceProfitProtectionDecision,
        reason: str,
    ) -> WorkspaceProfitProtectionDecision:
        return replace(
            decision,
            action=WORKSPACE_PROFIT_ACTION_HOLD,
            reason=reason,
        )

    @staticmethod
    def _close(
        decision: WorkspaceProfitProtectionDecision,
        reason: str,
    ) -> WorkspaceProfitProtectionDecision:
        return replace(
            decision,
            action=WORKSPACE_PROFIT_ACTION_CLOSE,
            reason=reason,
        )

    def evaluate(
        self,
        position: WorkspacePositionSnapshot,
        *,
        timestamp: datetime,
        runtime_ready: bool,
        spread_guard_passed: bool,
    ) -> WorkspaceProfitProtectionDecision:
        """Evaluate one position using only information available now."""
        decision = self.production_guard.evaluate(
            position,
            timestamp=timestamp,
            runtime_ready=runtime_ready,
            spread_guard_passed=spread_guard_passed,
        )
        pending = self.pending.get(position.position_id)

        if pending is None:
            if not decision.close_requested:
                return decision
            if position.current_profit + NUMERIC_EPSILON >= 0.0:
                return decision
            pending = PendingRecovery(
                position_id=position.position_id,
                trigger_timestamp=decision.timestamp,
                last_timestamp=decision.timestamp,
                trigger_profit=position.current_profit,
                previous_profit=position.current_profit,
            )
            self.pending[position.position_id] = pending
            self.started_position_ids.add(position.position_id)
            return self._hold(
                decision,
                "negative profit drawdown entered 3-M1 recovery pending",
            )

        if decision.timestamp <= pending.last_timestamp:
            return self._hold(
                decision,
                "negative profit drawdown remains inside recovery pending",
            )

        pending.completed_future_events += 1
        pending.last_timestamp = decision.timestamp
        step = position.current_profit - pending.previous_profit
        pending.previous_profit = position.current_profit

        if position.current_profit + NUMERIC_EPSILON >= 0.0:
            self.recovery_close_ids.add(position.position_id)
            self.pending.pop(position.position_id, None)
            return self._close(
                decision,
                "negative profit drawdown recovered to non-negative PnL",
            )

        if pending.completed_future_events == 1:
            pending.first_step_nonpositive = step <= NUMERIC_EPSILON

        if pending.completed_future_events == EARLY_ABORT_EVENT_INDEX:
            first_nonpositive = bool(pending.first_step_nonpositive)
            second_nonpositive = step <= NUMERIC_EPSILON
            if first_nonpositive and second_nonpositive:
                self.early_abort_close_ids.add(position.position_id)
                self.pending.pop(position.position_id, None)
                return self._close(
                    decision,
                    "negative profit drawdown two-step M1 deterioration abort",
                )

        if pending.completed_future_events >= self.recovery_window_m1:
            self.timeout_close_ids.add(position.position_id)
            self.pending.pop(position.position_id, None)
            return self._close(
                decision,
                "negative profit drawdown recovery window expired after 3 M1",
            )

        return self._hold(
            decision,
            "negative profit drawdown remains inside 3-M1 recovery pending",
        )


@dataclass(frozen=True, slots=True)
class TwoStepRecoveryResult:
    """Підсумок full frozen Replay для fixed 6J exit lifecycle."""

    trades: int
    wins: int
    losses: int
    break_even: int
    net_profit: float
    profit_factor: float | None
    maximum_drawdown: float
    maximum_drawdown_percent: float
    average_trade: float
    final_balance: float
    stop_loss_closes: int
    take_profit_closes: int
    profit_drawdown_closes: int
    session_end_closes: int
    pd_positive: int
    pd_negative: int
    pd_zero: int
    pending_started: int
    recovery_closes: int
    early_abort_closes: int
    timeout_closes: int
    pending_sl_closes: int
    pending_tp_closes: int
    pending_other_closes: int
    macd_quality_pass: int
    macd_quality_reject: int
    alligator_allow: int
    alligator_reject: int
    broker_execution_attempted: bool


def _run_variant() -> TwoStepRecoveryResult:
    workspace = frozen_oos_workspace()
    assert workspace.profit_protection["max_profit_drawdown_percent"] == 30.0
    assert workspace.profit_protection["minimum_profit"] == 0.0

    runtime = FrozenOosRuntime(
        workspace,
        algorithm_factory=create_registered_workspace_algorithm,
    )
    guard = WorkspaceNegativePdTwoStepRecoveryGuard(
        runtime.profit_protection_policy,
        RECOVERY_WINDOW_M1,
    )
    runtime.profit_drawdown_guard = guard

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
    trades = execution.trade_diagnostics()
    assert len(trades) == summary.opened_trades

    trade_by_position = {trade.position_id: trade for trade in trades}
    pending_terminal_trades = tuple(
        trade_by_position[position_id]
        for position_id in guard.started_position_ids
        if position_id in trade_by_position
    )
    pending_sl = sum(
        trade.close_reason == "STOP_LOSS" for trade in pending_terminal_trades
    )
    pending_tp = sum(
        trade.close_reason == "TAKE_PROFIT" for trade in pending_terminal_trades
    )
    known_decision_ids = (
        guard.recovery_close_ids
        | guard.early_abort_close_ids
        | guard.timeout_close_ids
    )
    pending_other = sum(
        trade.position_id not in known_decision_ids
        and trade.close_reason not in {"STOP_LOSS", "TAKE_PROFIT"}
        for trade in pending_terminal_trades
    )

    pd_trades = tuple(
        trade for trade in trades if trade.close_reason == "PROFIT_DRAWDOWN"
    )
    signals = summary.signals
    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )

    terminal_ids = (
        guard.recovery_close_ids
        | guard.early_abort_close_ids
        | guard.timeout_close_ids
    )
    assert signals.macd_quality_accept == BASELINE_MACD_QUALITY_PASS
    assert signals.macd_quality_reject == BASELINE_MACD_QUALITY_REJECT
    assert signals.alligator_allow == BASELINE_ALLIGATOR_ALLOW
    assert signals.alligator_reject == BASELINE_ALLIGATOR_REJECT
    assert len(guard.started_position_ids) == 18
    assert terminal_ids.issubset(guard.started_position_ids)
    assert guard.recovery_close_ids.isdisjoint(guard.early_abort_close_ids)
    assert guard.recovery_close_ids.isdisjoint(guard.timeout_close_ids)
    assert guard.early_abort_close_ids.isdisjoint(guard.timeout_close_ids)
    assert not broker_execution_attempted

    return TwoStepRecoveryResult(
        trades=summary.opened_trades,
        wins=summary.winning_trades,
        losses=summary.losing_trades,
        break_even=summary.break_even_trades,
        net_profit=summary.net_profit,
        profit_factor=summary.profit_factor,
        maximum_drawdown=summary.maximum_drawdown,
        maximum_drawdown_percent=summary.maximum_drawdown_percent,
        average_trade=summary.average_trade,
        final_balance=summary.final_balance,
        stop_loss_closes=summary.close_reason_count("STOP_LOSS"),
        take_profit_closes=summary.close_reason_count("TAKE_PROFIT"),
        profit_drawdown_closes=summary.close_reason_count("PROFIT_DRAWDOWN"),
        session_end_closes=summary.close_reason_count("SESSION_END"),
        pd_positive=sum(trade.final_profit > 0.0 for trade in pd_trades),
        pd_negative=sum(trade.final_profit < 0.0 for trade in pd_trades),
        pd_zero=sum(trade.final_profit == 0.0 for trade in pd_trades),
        pending_started=len(guard.started_position_ids),
        recovery_closes=len(guard.recovery_close_ids),
        early_abort_closes=len(guard.early_abort_close_ids),
        timeout_closes=len(guard.timeout_close_ids),
        pending_sl_closes=pending_sl,
        pending_tp_closes=pending_tp,
        pending_other_closes=pending_other,
        macd_quality_pass=signals.macd_quality_accept,
        macd_quality_reject=signals.macd_quality_reject,
        alligator_allow=signals.alligator_allow,
        alligator_reject=signals.alligator_reject,
        broker_execution_attempted=broker_execution_attempted,
    )


def _fmt_pf(value: float | None) -> str:
    return "NONE" if value is None else f"{value:.4f}"


def main() -> None:
    """Run full Replay for fixed 6F plus two-step M2 early-abort."""
    assert_frozen_oos_snapshot()
    result = _run_variant()

    print(
        "Algorithm Workspace Candidate F Negative PD Two-Step "
        "Recovery Pending 2025 result"
    )
    print("  mode=TEST_ONLY_FIXED_3_M1_WITH_M2_TWO_STEP_EARLY_ABORT")
    print(
        "  baseline="
        f"trades:{BASELINE_TRADES},wins:{BASELINE_WINS},"
        f"losses:{BASELINE_LOSSES},break_even:{BASELINE_BREAK_EVEN},"
        f"net:{BASELINE_NET:+.2f},pf:{BASELINE_PROFIT_FACTOR:.4f},"
        f"dd:{BASELINE_DRAWDOWN:.2f}"
    )
    print(
        "  fixed_6f_reference="
        f"net:{FIXED_6F_NET:+.2f},pf:{FIXED_6F_PROFIT_FACTOR:.4f},"
        f"dd:{FIXED_6F_DRAWDOWN:.2f}"
    )
    print("  recovery_window_m1=3")
    print("  recovery_target=current_profit_at_or_above_0R")
    print("  early_abort_event=M2")
    print("  early_abort_rule=M1_STEP_NONPOSITIVE_AND_M2_STEP_NONPOSITIVE")
    print("  timeout_exit=third_completed_future_M1_event")
    print("  protective_priority=original_SL_TP_before_recovery_guard")
    print("  positive_profit_drawdown_behavior=production_immediate_close")
    print("  entry_policy=NEXT_BAR_OPEN")
    print("  execution_chronology=M1")
    print(
        "  trades="
        f"{result.trades},wins:{result.wins},losses:{result.losses},"
        f"break_even:{result.break_even}"
    )
    print(
        "  performance="
        f"net:{result.net_profit:+.2f},pf:{_fmt_pf(result.profit_factor)},"
        f"dd:{result.maximum_drawdown:.2f}/"
        f"{result.maximum_drawdown_percent:.2f}%,"
        f"avg_trade:{result.average_trade:+.4f},"
        f"final_balance:{result.final_balance:.2f}"
    )
    print(
        "  delta_vs_baseline="
        f"net:{result.net_profit - BASELINE_NET:+.2f},"
        f"dd:{result.maximum_drawdown - BASELINE_DRAWDOWN:+.2f},"
        f"trades:{result.trades - BASELINE_TRADES:+d}"
    )
    print(
        "  delta_vs_fixed_6f="
        f"net:{result.net_profit - FIXED_6F_NET:+.2f},"
        f"dd:{result.maximum_drawdown - FIXED_6F_DRAWDOWN:+.2f}"
    )
    print(
        "  closes="
        f"sl:{result.stop_loss_closes},tp:{result.take_profit_closes},"
        f"profit_drawdown:{result.profit_drawdown_closes},"
        f"session_end:{result.session_end_closes}"
    )
    print(
        "  profit_drawdown_outcomes="
        f"positive:{result.pd_positive},negative:{result.pd_negative},"
        f"zero:{result.pd_zero}"
    )
    print(
        "  recovery_pending="
        f"started:{result.pending_started},"
        f"recovery_close:{result.recovery_closes},"
        f"early_abort_close:{result.early_abort_closes},"
        f"timeout_close:{result.timeout_closes},"
        f"protective_sl:{result.pending_sl_closes},"
        f"protective_tp:{result.pending_tp_closes},"
        f"other:{result.pending_other_closes}"
    )
    print(
        "  signal_pipeline="
        f"macd_quality_pass:{result.macd_quality_pass},"
        f"macd_quality_reject:{result.macd_quality_reject},"
        f"alligator_allow:{result.alligator_allow},"
        f"alligator_reject:{result.alligator_reject}"
    )
    print("  production_candidate_f_signals_preserved=True")
    print("  entry_logic_changed=False")
    print("  stop_loss_policy_changed=False")
    print("  take_profit_policy_changed=False")
    print("  profit_drawdown_percent_changed=False")
    print("  fixed_6f_recovery_window_preserved=True")
    print("  only_m2_two_step_early_abort_added_test_only=True")
    print("  recovery_uses_completed_m1_execution_events_only=True")
    print("  future_price_used_as_exit_gate=False")
    print("  macd_quality_thresholds_changed=False")
    print("  alligator_thresholds_changed=False")
    print("  candidate_f_thresholds_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print(
        "ALGORITHM_WORKSPACE_CANDIDATE_F_NEGATIVE_PD_TWO_STEP_"
        "RECOVERY_PENDING_2025_CHECK=OK"
    )


if __name__ == "__main__":
    main()
