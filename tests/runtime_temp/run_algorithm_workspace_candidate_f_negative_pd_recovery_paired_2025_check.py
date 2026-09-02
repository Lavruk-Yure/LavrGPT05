# -*- coding: utf-8 -*-
"""RoadMap102 / 6G: paired anatomy negative-PD recovery OOS 2025.

Runner повторює frozen Candidate F Replay 2025 і для тих самих 18 production
позицій з negative PROFIT_DRAWDOWN read-only відтворює вже перевірену в 6F
fixed політику: максимум 3 наступні завершені M1 execution events, recovery
close при першому current PnL >= 0R, інакше timeout на третьому M1. Початкові
SL/TP мають пріоритет.

Для кожної позиції production close порівнюється з 6F close: delta R/USD,
RECOVERY/TIMEOUT, delay, M1 mark path та causal Alligator state у момент
production PD trigger. Post-event fate з 6D використовується тільки як
діагностична мітка. Production trades/exits не змінюються, нового trading
counterfactual execution тут немає, PASS не залежить від PnL/PF/DD.
"""

from __future__ import annotations

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
    FrozenOosRuntime,
    assert_frozen_oos_snapshot,
    frozen_oos_workspace,
)
from run_algorithm_workspace_candidate_f_negative_pd_fate_2025_check import (  # noqa
    FATE_GOOD,
    FATE_PREMATURE,
    NegativePdFate,
    build_negative_pd_fates,
)

from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402

RECOVERY_WINDOW_M1 = 3
NUMERIC_EPSILON = 1e-9
NEAR_FLAT_DELTA_R = 0.01
BASELINE_NET = -5.90
EXPECTED_6F_NET = -4.34
EXPECTED_6F_DELTA = 1.56

OUTCOME_RECOVERY = "RECOVERY"
OUTCOME_TIMEOUT = "TIMEOUT"
OUTCOME_STOP_LOSS = "STOP_LOSS"
OUTCOME_TAKE_PROFIT = "TAKE_PROFIT"

DELTA_IMPROVED = "IMPROVED"
DELTA_WORSENED = "WORSENED"
DELTA_NEAR_FLAT = "NEAR_FLAT"


@dataclass(frozen=True, slots=True)
class PairedRecoveryCase:
    """Production negative-PD close проти fixed 3-M1 6F close."""

    fate: NegativePdFate
    outcome: str
    close_event_index: int
    baseline_close_r: float
    variant_close_r: float
    delta_r: float
    baseline_close_usd: float
    variant_close_usd: float
    delta_usd: float
    mark_1_r: float
    mark_2_r: float
    mark_3_r: float
    step_1_r: float
    step_2_r: float
    step_3_r: float
    window_mfe_r: float
    window_mae_r: float
    delta_class: str


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
    """Повторити STOP_LOSS_FIRST semantics production Replay."""
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
        return OUTCOME_STOP_LOSS
    if take_touched:
        return OUTCOME_TAKE_PROFIT
    return None


def _future_events_after_close(
    trade: WorkspaceHistoricalTradeDiagnostic,
    source_events: tuple[WorkspaceMarketEvent, ...],
) -> tuple[WorkspaceMarketEvent, ...]:
    return tuple(
        event for event in source_events if event.timestamp > trade.close_timestamp
    )


def _delta_class(delta_r: float) -> str:
    if delta_r > NEAR_FLAT_DELTA_R:
        return DELTA_IMPROVED
    if delta_r < -NEAR_FLAT_DELTA_R:
        return DELTA_WORSENED
    return DELTA_NEAR_FLAT


def _paired_case(
    fate: NegativePdFate,
    source_events: tuple[WorkspaceMarketEvent, ...],
) -> PairedRecoveryCase:
    trade = fate.trade
    risk_usd = _risk_usd(trade)
    selected = _future_events_after_close(trade, source_events)[:RECOVERY_WINDOW_M1]
    if len(selected) != RECOVERY_WINDOW_M1:
        raise AssertionError("Insufficient M1 events for fixed recovery window")

    marks = tuple(_mark_profit(trade, event) / risk_usd for event in selected)
    window_mfe_r = max((fate.close_r, *marks))
    window_mae_r = min((fate.close_r, *marks))
    outcome: str | None = None
    close_event_index: int | None = None
    close_timestamp: datetime | None = None
    variant_close_r: float | None = None

    for event_index, event in enumerate(selected, start=1):
        protection = _protection_reason(trade, event)
        if protection == OUTCOME_STOP_LOSS:
            outcome = OUTCOME_STOP_LOSS
            close_event_index = event_index
            close_timestamp = event.timestamp
            variant_close_r = -1.0
            break
        if protection == OUTCOME_TAKE_PROFIT:
            outcome = OUTCOME_TAKE_PROFIT
            close_event_index = event_index
            close_timestamp = event.timestamp
            variant_close_r = 2.0
            break

        mark_r = marks[event_index - 1]
        if mark_r + NUMERIC_EPSILON >= 0.0:
            outcome = OUTCOME_RECOVERY
            close_event_index = event_index
            close_timestamp = event.timestamp
            variant_close_r = mark_r
            break

        if event_index == RECOVERY_WINDOW_M1:
            outcome = OUTCOME_TIMEOUT
            close_event_index = event_index
            close_timestamp = event.timestamp
            variant_close_r = mark_r
            break

    if outcome is None or close_event_index is None:
        raise AssertionError("Fixed recovery case has no terminal outcome")
    if close_timestamp is None or variant_close_r is None:
        raise AssertionError("Fixed recovery close data is incomplete")

    baseline_usd = trade.final_profit
    variant_usd = variant_close_r * risk_usd
    delta_r = variant_close_r - fate.close_r

    return PairedRecoveryCase(
        fate=fate,
        outcome=outcome,
        close_event_index=close_event_index,
        baseline_close_r=fate.close_r,
        variant_close_r=variant_close_r,
        delta_r=delta_r,
        baseline_close_usd=baseline_usd,
        variant_close_usd=variant_usd,
        delta_usd=variant_usd - baseline_usd,
        mark_1_r=marks[0],
        mark_2_r=marks[1],
        mark_3_r=marks[2],
        step_1_r=marks[0] - fate.close_r,
        step_2_r=marks[1] - marks[0],
        step_3_r=marks[2] - marks[1],
        window_mfe_r=window_mfe_r,
        window_mae_r=window_mae_r,
        delta_class=_delta_class(delta_r),
    )


def build_paired_recovery_cases(
    runtime: FrozenOosRuntime,
) -> tuple[PairedRecoveryCase, ...]:
    """Побудувати paired 6F cases без зміни production exits."""
    fates, source_events = build_negative_pd_fates(runtime)
    return tuple(_paired_case(fate, source_events) for fate in fates)


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


def _group_summary(name: str, cases: tuple[PairedRecoveryCase, ...]) -> None:
    baseline_sum = sum(case.baseline_close_usd for case in cases)
    variant_sum = sum(case.variant_close_usd for case in cases)
    delta_sum = sum(case.delta_usd for case in cases)
    causal = tuple(case.fate.causal_state for case in cases)
    aligned_active = sum(state.aligned_active for state in causal)
    opposite_active = sum(state.opposite_active for state in causal)
    premature = sum(case.fate.fate == FATE_PREMATURE for case in cases)
    good = sum(case.fate.fate == FATE_GOOD for case in cases)

    print(f"  {name}:")
    print(
        f"    count={len(cases)},fate=premature:{premature},good:{good},"
        f"aligned_active:{aligned_active},opposite_active:{opposite_active}"
    )
    print(
        "    paired_pnl="
        f"baseline:{baseline_sum:+.2f},variant:{variant_sum:+.2f},"
        f"delta:{delta_sum:+.2f}"
    )
    print(
        "    delta_class="
        f"improved:{sum(case.delta_class == DELTA_IMPROVED for case in cases)},"
        f"worsened:{sum(case.delta_class == DELTA_WORSENED for case in cases)},"
        f"near_flat:{sum(case.delta_class == DELTA_NEAR_FLAT for case in cases)}"
    )
    close_delays = tuple(float(case.close_event_index) for case in cases)
    baseline_close_r = tuple(case.baseline_close_r for case in cases)
    variant_close_r = tuple(case.variant_close_r for case in cases)
    delta_r = tuple(case.delta_r for case in cases)
    print(
        "    close_delay_m1="
        f"mean:{_fmt(_mean(close_delays), 2)},"
        f"median:{_fmt(_median(close_delays), 2)}"
    )
    print(
        "    trigger_r="
        f"baseline_close_mean:{_fmt(_mean(baseline_close_r), signed=True)},"
        f"variant_close_mean:{_fmt(_mean(variant_close_r), signed=True)},"
        f"delta_mean:{_fmt(_mean(delta_r), signed=True)}"
    )
    print(
        "    m1_mark_mean="
        f"m1:{_fmt(_mean(tuple(case.mark_1_r for case in cases)), signed=True)},"
        f"m2:{_fmt(_mean(tuple(case.mark_2_r for case in cases)), signed=True)},"
        f"m3:{_fmt(_mean(tuple(case.mark_3_r for case in cases)), signed=True)}"
    )
    print(
        "    m1_step_mean="
        f"s1:{_fmt(_mean(tuple(case.step_1_r for case in cases)), signed=True)},"
        f"s2:{_fmt(_mean(tuple(case.step_2_r for case in cases)), signed=True)},"
        f"s3:{_fmt(_mean(tuple(case.step_3_r for case in cases)), signed=True)}"
    )
    print(
        "    window_excursion_mean="
        f"mfe:{_fmt(_mean(tuple(case.window_mfe_r for case in cases)), signed=True)},"
        f"mae:{_fmt(_mean(tuple(case.window_mae_r for case in cases)), signed=True)}"
    )
    print(
        "    causal_alligator_mean="
        f"slope:{_fmt(_mean(tuple(
            state.normalized_slope
            for state in causal
            if state.normalized_slope is not None
        )), signed=True)},"
        f"opening:{_fmt(_mean(tuple(
            state.normalized_opening
            for state in causal
            if state.normalized_opening is not None
        )), signed=True)},"
        f"slope_d1:{_fmt(_mean(tuple(
            state.slope_delta_1
            for state in causal
            if state.slope_delta_1 is not None
        )), signed=True)},"
        f"opening_d1:{_fmt(_mean(tuple(
            state.opening_delta_1
            for state in causal
            if state.opening_delta_1 is not None
        )), signed=True)}"
    )


def _case_line(index: int, case: PairedRecoveryCase) -> str:
    trade = case.fate.trade
    state = case.fate.causal_state
    return (
        f"    {index:02d}. {trade.close_timestamp.isoformat()} {trade.direction} "
        f"fate:{case.fate.fate} outcome:{case.outcome}@M{case.close_event_index} "
        f"base:{case.baseline_close_r:+.3f}R "
        f"new:{case.variant_close_r:+.3f}R delta:{case.delta_r:+.3f}R/"
        f"{case.delta_usd:+.2f}$ class:{case.delta_class} "
        f"marks:{case.mark_1_r:+.3f}/{case.mark_2_r:+.3f}/"
        f"{case.mark_3_r:+.3f}R steps:{case.step_1_r:+.3f}/"
        f"{case.step_2_r:+.3f}/{case.step_3_r:+.3f}R "
        f"mfe:{case.window_mfe_r:+.3f}R mae:{case.window_mae_r:+.3f}R "
        f"allig:{state.state}/{state.regime}/{state.phase} "
        f"aligned:{state.aligned_active} "
        f"slope:{_fmt(state.normalized_slope, signed=True)} "
        f"open:{_fmt(state.normalized_opening, signed=True)} "
        f"sd1:{_fmt(state.slope_delta_1, signed=True)} "
        f"od1:{_fmt(state.opening_delta_1, signed=True)}"
    )


def main() -> None:
    """Порівняти paired production PD close і fixed 3-M1 6F close."""
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
    cases = build_paired_recovery_cases(runtime)

    recovery = tuple(case for case in cases if case.outcome == OUTCOME_RECOVERY)
    timeout = tuple(case for case in cases if case.outcome == OUTCOME_TIMEOUT)
    protective = tuple(
        case
        for case in cases
        if case.outcome in {OUTCOME_STOP_LOSS, OUTCOME_TAKE_PROFIT}
    )
    improved = tuple(case for case in cases if case.delta_class == DELTA_IMPROVED)
    worsened = tuple(case for case in cases if case.delta_class == DELTA_WORSENED)
    near_flat = tuple(case for case in cases if case.delta_class == DELTA_NEAR_FLAT)

    paired_delta_usd = sum(case.delta_usd for case in cases)
    reconstructed_net = summary.net_profit + paired_delta_usd
    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )

    assert len(cases) == 18
    assert len(recovery) == 9
    assert len(timeout) == 9
    assert not protective
    assert all(case.fate.fate == FATE_PREMATURE for case in recovery)
    assert sum(case.fate.fate == FATE_GOOD for case in timeout) == 3
    assert abs(paired_delta_usd - EXPECTED_6F_DELTA) < 0.01
    assert abs(reconstructed_net - EXPECTED_6F_NET) < 0.01
    assert abs(summary.net_profit - BASELINE_NET) < 0.01
    assert not broker_execution_attempted

    print("Algorithm Workspace Candidate F Negative PD Recovery Paired 2025 result")
    print("  mode=PAIRED_BASELINE_VS_FIXED_3_M1_RECOVERY_DIAGNOSTIC_ONLY")
    print(
        "  baseline="
        f"trades:{summary.opened_trades},net:{summary.net_profit:+.2f},"
        f"pf:{summary.profit_factor:.4f},dd:{summary.maximum_drawdown:.2f}"
    )
    print("  production_negative_pd_trades=18")
    print("  fixed_6f_policy=recovery_to_0R_or_timeout_after_3_completed_M1")
    print("  protective_priority=original_SL_TP_before_recovery_guard")
    print("  paired_close_reconstruction=18/18")
    print(
        "  aggregate_reconstruction="
        f"paired_delta:{paired_delta_usd:+.2f},"
        f"baseline_net:{summary.net_profit:+.2f},"
        f"reconstructed_6f_net:{reconstructed_net:+.2f}"
    )
    print(
        "  terminal_outcomes="
        f"recovery:{len(recovery)},timeout:{len(timeout)},"
        f"protective:{len(protective)}"
    )
    print(
        "  delta_classes_abs_0.01R="
        f"improved:{len(improved)},worsened:{len(worsened)},"
        f"near_flat:{len(near_flat)}"
    )

    _group_summary("recovery_group", recovery)
    _group_summary("timeout_group", timeout)

    print("  improved_cases:")
    for index, case in enumerate(improved, start=1):
        print(_case_line(index, case))
    print("  worsened_cases:")
    for index, case in enumerate(worsened, start=1):
        print(_case_line(index, case))
    print("  near_flat_cases:")
    for index, case in enumerate(near_flat, start=1):
        print(_case_line(index, case))

    print("  chronological_pairs:")
    for index, case in enumerate(cases, start=1):
        print(_case_line(index, case))

    print("  production_trades_modified=False")
    print("  production_exits_modified=False")
    print("  paired_6f_exits_reconstructed_read_only=True")
    print("  new_counterfactual_trades_created=False")
    print("  future_fate_used_only_as_diagnostic_label=True")
    print("  fixed_6f_decision_uses_only_next_completed_m1_events=True")
    print("  exit_logic_changed=False")
    print("  entry_logic_changed=False")
    print("  macd_quality_thresholds_changed=False")
    print("  alligator_thresholds_changed=False")
    print("  candidate_f_thresholds_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_NEGATIVE_PD_RECOVERY_PAIRED_2025_CHECK=OK")


if __name__ == "__main__":
    main()
