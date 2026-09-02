# -*- coding: utf-8 -*-
"""T105-05: actual Candidate F production Profit Drawdown anatomy, cTrader 2025.

TEST_ONLY diagnostic. Production WorkspaceRuntime and Candidate F entry/exit logic
are not modified. The runner records causal PD threshold breaches and actual PD
closes, then performs a post-close read-only SL/TP fate diagnostic. Future data
is used only after the production close as a label, never as an exit gate.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean, median

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, TEST_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    assert_frozen_oos_snapshot,
    frozen_oos_workspace,
)

from core.workspace_algorithm import create_registered_workspace_algorithm  # noqa: E402
from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_profit_guard import (  # noqa: E402
    WorkspaceCandidateFNegativePdRecoveryGuard,
    WorkspaceProfitProtectionDecision,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402

TEST_ID = "T105-05"
EPSILON = 1e-9
EXPECTED_TRADES = 59
EXPECTED_WINS = 40
EXPECTED_LOSSES = 18
EXPECTED_BREAK_EVEN = 1
EXPECTED_PD = 48
EXPECTED_SL = 9
EXPECTED_TP = 2


@dataclass(frozen=True, slots=True)
class PdTrigger:
    position_id: str
    timestamp: datetime
    current_profit: float
    peak_profit: float
    drawdown_percent: float
    negative: bool


@dataclass(frozen=True, slots=True)
class PdExitState:
    position_id: str
    timestamp: datetime
    current_profit: float
    peak_profit: float
    drawdown_percent: float
    reason: str


@dataclass(frozen=True, slots=True)
class PdAnatomy:
    trade: WorkspaceHistoricalTradeDiagnostic
    trigger: PdTrigger
    exit_state: PdExitState
    risk_usd: float
    trigger_peak_r: float
    trigger_current_r: float
    exit_peak_r: float
    exit_current_r: float
    mfe_r: float
    mae_r: float
    retracement_at_trigger_r: float
    retracement_at_exit_r: float
    fate: str
    fate_timestamp: datetime | None


class AnatomyRuntime(WorkspaceRuntime):
    """TEST_ONLY observer around the unmodified production PD guard."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.pd_triggers: dict[str, PdTrigger] = {}
        self.pd_exit_states: dict[str, PdExitState] = {}
        self._seen_eval_keys: set[tuple[str, datetime]] = set()
        super().__init__(*args, **kwargs)

    def _evaluate_profit_protection_at(
        self,
        timestamp: datetime,
    ) -> tuple[WorkspaceProfitProtectionDecision, ...]:
        active_before = {
            position.position_id: position
            for position in self.owned_snapshot.active_positions
        }
        decisions = super()._evaluate_profit_protection_at(timestamp)
        for decision in decisions:
            position = active_before.get(decision.position_id)
            if position is None:
                continue
            key = (position.position_id, timestamp)
            if key in self._seen_eval_keys:
                continue
            self._seen_eval_keys.add(key)
            threshold_breached = bool(
                position.peak_profit > 0.0
                and position.profit_drawdown
                > self.profit_protection_policy.max_drawdown_percent
            )
            if threshold_breached and position.position_id not in self.pd_triggers:
                self.pd_triggers[position.position_id] = PdTrigger(
                    position_id=position.position_id,
                    timestamp=timestamp,
                    current_profit=position.current_profit,
                    peak_profit=position.peak_profit,
                    drawdown_percent=position.profit_drawdown,
                    negative=position.current_profit < 0.0,
                )
            if decision.close_requested:
                self.pd_exit_states[position.position_id] = PdExitState(
                    position_id=position.position_id,
                    timestamp=timestamp,
                    current_profit=position.current_profit,
                    peak_profit=position.peak_profit,
                    drawdown_percent=position.profit_drawdown,
                    reason=decision.reason,
                )
        return decisions


def _risk_usd(trade: WorkspaceHistoricalTradeDiagnostic) -> float:
    risk = trade.stop_loss_distance * trade.volume
    assert risk > 0.0
    return risk


def _protection_reason(
    trade: WorkspaceHistoricalTradeDiagnostic,
    event: WorkspaceMarketEvent,
) -> str | None:
    """Repeat production STOP_LOSS_FIRST protective-bar semantics."""
    if trade.direction == "BUY":
        stop_price = trade.entry_price - trade.stop_loss_distance
        take_price = trade.entry_price + trade.take_profit_distance
        stop_touched = event.low <= stop_price
        take_touched = event.high >= take_price
    else:
        stop_price = trade.entry_price + trade.stop_loss_distance
        take_price = trade.entry_price - trade.take_profit_distance
        stop_touched = event.high >= stop_price
        take_touched = event.low <= take_price
    if stop_touched:
        return "STOP_LOSS"
    if take_touched:
        return "TAKE_PROFIT"
    return None


def _post_close_fate(
    trade: WorkspaceHistoricalTradeDiagnostic,
    execution_events: tuple[WorkspaceMarketEvent, ...],
) -> tuple[str, datetime | None]:
    for event in execution_events:
        if event.timestamp <= trade.close_timestamp:
            continue
        reason = _protection_reason(trade, event)
        if reason == "STOP_LOSS":
            return "PD_SAVED_FUTURE_SL", event.timestamp
        if reason == "TAKE_PROFIT":
            return "PD_CUT_FUTURE_TP", event.timestamp
    return "UNRESOLVED_BY_2025_END", None


def _flatten_execution_events(
    runtime: AnatomyRuntime,
) -> tuple[WorkspaceMarketEvent, ...]:
    session = runtime.replay_session
    assert session is not None
    events = tuple(event for window in session.execution_windows for event in window)
    assert events
    return events


def _anatomy_rows(runtime: AnatomyRuntime) -> tuple[PdAnatomy, ...]:
    execution = runtime.replay_execution
    assert execution is not None
    trades = execution.trade_diagnostics()
    pd_trades = tuple(
        trade for trade in trades if trade.close_reason == "PROFIT_DRAWDOWN"
    )
    execution_events = _flatten_execution_events(runtime)
    rows: list[PdAnatomy] = []
    for trade in pd_trades:
        trigger = runtime.pd_triggers.get(trade.position_id)
        exit_state = runtime.pd_exit_states.get(trade.position_id)
        assert trigger is not None, trade.position_id
        assert exit_state is not None, trade.position_id
        risk = _risk_usd(trade)
        fate, fate_timestamp = _post_close_fate(trade, execution_events)
        rows.append(
            PdAnatomy(
                trade=trade,
                trigger=trigger,
                exit_state=exit_state,
                risk_usd=risk,
                trigger_peak_r=trigger.peak_profit / risk,
                trigger_current_r=trigger.current_profit / risk,
                exit_peak_r=exit_state.peak_profit / risk,
                exit_current_r=exit_state.current_profit / risk,
                mfe_r=trade.maximum_favorable_excursion / risk,
                mae_r=trade.maximum_adverse_excursion / risk,
                retracement_at_trigger_r=(trigger.peak_profit - trigger.current_profit)
                / risk,
                retracement_at_exit_r=(
                    exit_state.peak_profit - exit_state.current_profit
                )
                / risk,
                fate=fate,
                fate_timestamp=fate_timestamp,
            )
        )
    return tuple(rows)


def _fmt(value: float) -> str:
    return f"{value:.4f}"


def main() -> None:
    assert_frozen_oos_snapshot()
    workspace = frozen_oos_workspace()
    workspace.broker = "CTRADER"
    replay_settings = dict(workspace.replay_settings)
    replay_settings.update(
        {
            "file_path": str(
                PROJECT_ROOT
                / "data"
                / "history"
                / "CTRADER"
                / "EURUSD"
                / "M1"
                / "2025-01-01_2025-12-31_CTRADER_EURUSD_M1.csv"
            ),
            "start_utc": "2025-01-01T22:01:00+00:00",
            "end_utc": "2025-12-31T21:58:00+00:00",
            "source": "2025-01-01_2025-12-31_CTRADER_EURUSD_M1",
            "source_timeframe": "M1",
        }
    )
    workspace.set_replay_settings(replay_settings)

    runtime = AnatomyRuntime(
        workspace,
        algorithm_factory=create_registered_workspace_algorithm,
    )
    guard = runtime.profit_drawdown_guard
    assert isinstance(guard, WorkspaceCandidateFNegativePdRecoveryGuard)

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
    assert summary.winning_trades == EXPECTED_WINS
    assert summary.losing_trades == EXPECTED_LOSSES
    assert summary.break_even_trades == EXPECTED_BREAK_EVEN
    assert summary.close_reason_count("PROFIT_DRAWDOWN") == EXPECTED_PD
    assert summary.close_reason_count("STOP_LOSS") == EXPECTED_SL
    assert summary.close_reason_count("TAKE_PROFIT") == EXPECTED_TP

    rows = _anatomy_rows(runtime)
    assert len(rows) == EXPECTED_PD
    assert len(runtime.pd_triggers) == EXPECTED_PD
    assert len(runtime.pd_exit_states) == EXPECTED_PD

    immediate_positive = tuple(row for row in rows if not row.trigger.negative)
    negative_triggered = tuple(row for row in rows if row.trigger.negative)
    assert len(negative_triggered) == len(guard.started_position_ids) == 18

    saved_sl = tuple(row for row in rows if row.fate == "PD_SAVED_FUTURE_SL")
    cut_tp = tuple(row for row in rows if row.fate == "PD_CUT_FUTURE_TP")
    unresolved = tuple(row for row in rows if row.fate == "UNRESOLVED_BY_2025_END")

    positive_pd_exits = sum(row.trade.final_profit > EPSILON for row in rows)
    negative_pd_exits = sum(row.trade.final_profit < -EPSILON for row in rows)
    zero_pd_exits = len(rows) - positive_pd_exits - negative_pd_exits

    trigger_peaks = tuple(row.trigger_peak_r for row in rows)
    trigger_retracements = tuple(row.retracement_at_trigger_r for row in rows)
    exit_retracements = tuple(row.retracement_at_exit_r for row in rows)
    mfes = tuple(row.mfe_r for row in rows)
    maes = tuple(row.mae_r for row in rows)

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted
    assert all(row.trigger.timestamp <= row.exit_state.timestamp for row in rows)
    assert all(row.trade.close_timestamp >= row.exit_state.timestamp for row in rows)
    assert all(math.isfinite(value) for value in (*trigger_peaks, *mfes, *maes))

    print("T105-05 Candidate F Production Profit Drawdown Anatomy 2025 result")
    print("  mode=TEST_ONLY_ACTUAL_WORKSPACE_RUNTIME_PD_ANATOMY")
    print("  source=CTRADER_EURUSD_M1_2025")
    print("  profile=LGE_CANDIDATE_F_SMOOTHED_R1")
    print("  production_profit_drawdown_percent=30.0")
    print("  production_negative_pd_recovery=3_M1_WITH_M2_EARLY_ABORT")
    print(
        "  baseline="
        f"trades:{summary.opened_trades},wins:{summary.winning_trades},"
        f"losses:{summary.losing_trades},break_even:{summary.break_even_trades},"
        f"net:{summary.net_profit:+.2f},pf:{summary.profit_factor:.4f},"
        f"dd:{summary.maximum_drawdown:.2f}"
    )
    print(
        "  closes="
        f"profit_drawdown:{EXPECTED_PD},stop_loss:{EXPECTED_SL},"
        f"take_profit:{EXPECTED_TP}"
    )
    print(
        "  pd_threshold_breaches="
        f"total:{len(rows)},positive_or_zero_current:{len(immediate_positive)},"
        f"negative:{len(negative_triggered)}"
    )
    print(
        "  negative_pd_recovery="
        f"started:{len(guard.started_position_ids)},"
        f"recovered_to_nonnegative:{len(guard.recovery_close_ids)},"
        f"m2_early_abort:{len(guard.early_abort_close_ids)},"
        f"m3_timeout:{len(guard.timeout_close_ids)}"
    )
    print(
        "  pd_exit_pnl="
        f"positive:{positive_pd_exits},negative:{negative_pd_exits},"
        f"zero:{zero_pd_exits}"
    )
    print(
        "  trigger_peak_R="
        f"mean:{_fmt(mean(trigger_peaks))},median:{_fmt(median(trigger_peaks))},"
        f"min:{_fmt(min(trigger_peaks))},max:{_fmt(max(trigger_peaks))}"
    )
    print(
        "  trigger_retracement_R="
        f"mean:{_fmt(mean(trigger_retracements))},"
        f"median:{_fmt(median(trigger_retracements))}"
    )
    print(
        "  actual_exit_retracement_R="
        f"mean:{_fmt(mean(exit_retracements))},median:{_fmt(median(exit_retracements))}"
    )
    print(
        "  pd_trade_MFE_R="
        f"mean:{_fmt(mean(mfes))},median:{_fmt(median(mfes))},max:{_fmt(max(mfes))}"
    )
    print(
        "  pd_trade_MAE_R="
        f"mean:{_fmt(mean(maes))},median:{_fmt(median(maes))},min:{_fmt(min(maes))}"
    )
    print(
        "  post_close_initial_SLTP_fate="
        f"saved_future_sl:{len(saved_sl)},cut_future_tp:{len(cut_tp)},"
        f"unresolved:{len(unresolved)}"
    )
    print("  post_close_future_used_for_diagnostic_label_only=True")
    print("  future_price_used_as_production_exit_gate=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T105_05_CANDIDATE_F_PRODUCTION_PROFIT_DRAWDOWN_ANATOMY_2025=OK")


if __name__ == "__main__":
    main()
