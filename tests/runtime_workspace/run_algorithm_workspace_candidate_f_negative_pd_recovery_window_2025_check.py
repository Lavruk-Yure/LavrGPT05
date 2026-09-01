# -*- coding: utf-8 -*-
"""RoadMap102 / 6E: negative-PD recovery-window diagnostic OOS 2025.

Runner повторює frozen Candidate F Replay 2025 і бере 18 production-позицій,
закритих PROFIT_DRAWDOWN з від'ємним realized PnL. Для кожної позиції після
production close read-only перевіряються рівно три наперед зафіксовані grace
windows: 1, 3 і 5 наступних M1 execution events.

У межах кожного window фіксується recovery до 0R/+0.10R, mark PnL наприкінці
window, adverse excursion та початковий SL/TP. Protective ambiguity лишається
STOP_LOSS_FIRST. Future після production close використовується тільки для
діагностики; production trades/exits не змінюються і counterfactual execution
не створюється.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, TEST_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    FrozenOosRuntime,
    assert_frozen_oos_snapshot,
    frozen_oos_workspace,
)
from run_algorithm_workspace_candidate_f_negative_pd_fate_2025_check import (
    FATE_GOOD,
    FATE_PREMATURE,
    NegativePdFate,
    build_negative_pd_fates,
)  # noqa: E402

GRACE_WINDOWS_M1 = (1, 3, 5)
NUMERIC_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class RecoveryWindowCase:
    """Один read-only grace-window результат для negative-PD trade."""

    fate: NegativePdFate
    window_m1: int
    available_events: int
    recovered_0r: bool
    recovered_0r_event: int | None
    reached_010r: bool
    reached_010r_event: int | None
    stop_loss_in_window: bool
    take_profit_in_window: bool
    terminal_event: int | None
    end_mark_r: float | None
    mark_mfe_r: float
    mark_mae_r: float


@dataclass(frozen=True, slots=True)
class WindowSummary:
    """Aggregate одного фіксованого M1 grace window."""

    window_m1: int
    cases: tuple[RecoveryWindowCase, ...]

    @property
    def premature(self) -> tuple[RecoveryWindowCase, ...]:
        return tuple(case for case in self.cases if case.fate.fate == FATE_PREMATURE)

    @property
    def good(self) -> tuple[RecoveryWindowCase, ...]:
        return tuple(case for case in self.cases if case.fate.fate == FATE_GOOD)


def _risk_usd(trade: WorkspaceHistoricalTradeDiagnostic) -> float:
    risk = trade.stop_loss_distance * trade.volume
    if risk <= 0.0:
        raise AssertionError("Initial risk must be positive")
    return risk


def _mark_profit(
    trade: WorkspaceHistoricalTradeDiagnostic,
    event: WorkspaceMarketEvent,
) -> float:
    close_price = event.bid if trade.direction == "BUY" else event.ask
    sign = 1.0 if trade.direction == "BUY" else -1.0
    return (close_price - trade.entry_price) * trade.volume * sign


def _protection_reason(
    trade: WorkspaceHistoricalTradeDiagnostic,
    event: WorkspaceMarketEvent,
) -> str | None:
    """Повторити STOP_LOSS_FIRST protective-bar semantics production Replay."""
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


def _future_events_after_close(
    trade: WorkspaceHistoricalTradeDiagnostic,
    source_events: tuple[WorkspaceMarketEvent, ...],
) -> tuple[WorkspaceMarketEvent, ...]:
    return tuple(
        event for event in source_events if event.timestamp > trade.close_timestamp
    )


def _window_case(
    fate: NegativePdFate,
    source_events: tuple[WorkspaceMarketEvent, ...],
    window_m1: int,
) -> RecoveryWindowCase:
    trade = fate.trade
    risk_usd = _risk_usd(trade)
    future = _future_events_after_close(trade, source_events)
    selected = future[:window_m1]
    if len(selected) != window_m1:
        raise AssertionError("Insufficient M1 events inside fixed grace window")

    recovered_event: int | None = None
    reached_010_event: int | None = None
    stop_loss_in_window = False
    take_profit_in_window = False
    terminal_event: int | None = None
    end_mark_r: float | None = None
    mark_mfe_r = fate.close_r
    mark_mae_r = fate.close_r

    for event_index, event in enumerate(selected, start=1):
        protection = _protection_reason(trade, event)
        if protection == "STOP_LOSS":
            stop_loss_in_window = True
            terminal_event = event_index
            mark_mae_r = min(mark_mae_r, -1.0)
            end_mark_r = -1.0
            break
        if protection == "TAKE_PROFIT":
            take_profit_in_window = True
            terminal_event = event_index
            mark_mfe_r = max(mark_mfe_r, 2.0)
            if recovered_event is None:
                recovered_event = event_index
            if reached_010_event is None:
                reached_010_event = event_index
            end_mark_r = 2.0
            break

        mark_r = _mark_profit(trade, event) / risk_usd
        mark_mfe_r = max(mark_mfe_r, mark_r)
        mark_mae_r = min(mark_mae_r, mark_r)
        end_mark_r = mark_r
        if mark_r + NUMERIC_EPSILON >= 0.0 and recovered_event is None:
            recovered_event = event_index
        if mark_r + NUMERIC_EPSILON >= 0.10 and reached_010_event is None:
            reached_010_event = event_index

    return RecoveryWindowCase(
        fate=fate,
        window_m1=window_m1,
        available_events=len(selected),
        recovered_0r=recovered_event is not None,
        recovered_0r_event=recovered_event,
        reached_010r=reached_010_event is not None,
        reached_010r_event=reached_010_event,
        stop_loss_in_window=stop_loss_in_window,
        take_profit_in_window=take_profit_in_window,
        terminal_event=terminal_event,
        end_mark_r=end_mark_r,
        mark_mfe_r=mark_mfe_r,
        mark_mae_r=mark_mae_r,
    )


def _mean(values: tuple[float, ...]) -> float | None:
    return mean(values) if values else None


def _median(values: tuple[float, ...]) -> float | None:
    return median(values) if values else None


def _fmt(value: float | None, digits: int = 3, signed: bool = False) -> str:
    if value is None:
        return "NONE"
    if signed:
        return f"{value:+.{digits}f}"
    return f"{value:.{digits}f}"


def _event_delay_minutes(event_index: int | None) -> int | None:
    return event_index


def _group_line(
    label: str,
    cases: tuple[RecoveryWindowCase, ...],
) -> None:
    not_recovered = tuple(case for case in cases if not case.recovered_0r)
    end_marks = tuple(
        case.end_mark_r for case in not_recovered if case.end_mark_r is not None
    )
    recovery_delays = tuple(
        float(delay)
        for case in cases
        if (delay := _event_delay_minutes(case.recovered_0r_event)) is not None
    )
    print(
        f"    {label}=count:{len(cases)},"
        f"recover0:{sum(case.recovered_0r for case in cases)},"
        f"reach_0.10R:{sum(case.reached_010r for case in cases)},"
        f"no_recovery:{len(not_recovered)},"
        f"sl_in_window:{sum(case.stop_loss_in_window for case in cases)},"
        f"tp_in_window:{sum(case.take_profit_in_window for case in cases)}"
    )
    print(
        f"      recovery_delay_min=mean:{_fmt(_mean(recovery_delays), 2)},"
        f"median:{_fmt(_median(recovery_delays), 2)}"
    )
    print(
        f"      unrecovered_end_mark_r=mean:{_fmt(_mean(end_marks), signed=True)},"
        f"median:{_fmt(_median(end_marks), signed=True)}"
    )
    mfe_mean = _mean(tuple(case.mark_mfe_r for case in cases))
    mae_mean = _mean(tuple(case.mark_mae_r for case in cases))
    print(
        "      window_excursion_r="
        f"mfe_mean:{_fmt(mfe_mean, signed=True)},"
        f"mae_mean:{_fmt(mae_mean, signed=True)}"
    )


def _case_line(case_index: int, windows: tuple[RecoveryWindowCase, ...]) -> str:
    first = windows[0]
    trade = first.fate.trade
    window_text = " ".join(
        (
            f"W{case.window_m1}:r0={case.recovered_0r},"
            f"r01={case.reached_010r},sl={case.stop_loss_in_window},"
            f"end={_fmt(case.end_mark_r, signed=True)}R,"
            f"mae={case.mark_mae_r:+.3f}R"
        )
        for case in windows
    )
    return (
        f"    {case_index:02d}. {trade.close_timestamp.isoformat()} "
        f"{trade.direction} fate:{first.fate.fate} "
        f"close:{first.fate.close_r:+.3f}R {window_text}"
    )


def main() -> None:
    """Виміряти recovery latency у фіксованих 1/3/5 M1 grace windows."""
    assert_frozen_oos_snapshot()

    runtime = FrozenOosRuntime(
        frozen_oos_workspace(),
        algorithm_factory=create_registered_workspace_algorithm,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()

    summary = runtime.historical_summary
    assert summary is not None
    fates, source_events = build_negative_pd_fates(runtime)

    summaries = tuple(
        WindowSummary(
            window_m1=window_m1,
            cases=tuple(_window_case(fate, source_events, window_m1) for fate in fates),
        )
        for window_m1 in GRACE_WINDOWS_M1
    )

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted
    assert all(len(item.cases) == 18 for item in summaries)
    assert all(
        case.available_events == case.window_m1
        for item in summaries
        for case in item.cases
    )

    print("Algorithm Workspace Candidate F Negative PD Recovery Window 2025 result")
    print("  mode=FIXED_1_3_5_M1_RECOVERY_WINDOW_DIAGNOSTIC_ONLY")
    print(
        "  baseline="
        f"trades:{summary.opened_trades},net:{summary.net_profit:+.2f},"
        f"pf:{summary.profit_factor:.4f},dd:{summary.maximum_drawdown:.2f}"
    )
    print("  production_negative_pd_trades=18")
    print("  fate_reference=premature:15,good:3")
    print("  grace_windows_m1=1,3,5")
    print("  recovery_target=mark_PnL_at_or_above_0R")
    print("  secondary_target=mark_PnL_at_or_above_0.10R")
    print("  protective_ambiguity_policy=STOP_LOSS_FIRST")
    print("  m1_window_uses_completed_execution_events_only=True")

    for item in summaries:
        print(f"  window_{item.window_m1}m:")
        _group_line("all", item.cases)
        _group_line("premature", item.premature)
        _group_line("good", item.good)

    print("  chronological_window_outcomes:")
    by_trade = tuple(
        tuple(item.cases[index] for item in summaries) for index in range(len(fates))
    )
    for index, windows in enumerate(by_trade, start=1):
        print(_case_line(index, windows))

    print("  production_trades_modified=False")
    print("  counterfactual_trades_created=False")
    print("  counterfactual_exits_created=False")
    print("  future_after_pd_close_used_only_for_diagnostic=True")
    print("  future_price_used_as_exit_gate=False")
    print("  exit_logic_changed=False")
    print("  entry_logic_changed=False")
    print("  macd_quality_thresholds_changed=False")
    print("  alligator_thresholds_changed=False")
    print("  candidate_f_thresholds_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_NEGATIVE_PD_RECOVERY_WINDOW_2025_CHECK=OK")


if __name__ == "__main__":
    main()
