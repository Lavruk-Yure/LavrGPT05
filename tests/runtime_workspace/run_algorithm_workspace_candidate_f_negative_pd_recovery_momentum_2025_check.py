# -*- coding: utf-8 -*-
"""RoadMap102 / 6H: causal M1 momentum anatomy negative-PD recovery OOS 2025.

Runner повторює frozen Candidate F Replay 2025, read-only відтворює paired
6F cases для 18 production negative PROFIT_DRAWDOWN exits і ділить їх після
першої завершеної M1 за causal ознакою: PnL покращився відносно production
PD trigger або ні. Окремо рахується paired diagnostic counterfactual: для
M1_STEP_NONPOSITIVE закрити на першій M1 замість очікування до M3, а для
M1_STEP_POSITIVE лишити fixed 6F lifecycle.

Це diagnostic-only аналіз. Production trades/exits не змінюються, нового
full Replay execution немає, future fate не використовується як gate, а PASS
не залежить від PnL/PF/DD.
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
from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    FrozenOosRuntime,
    assert_frozen_oos_snapshot,
    frozen_oos_workspace,
)
from run_algorithm_workspace_candidate_f_negative_pd_fate_2025_check import (
    FATE_GOOD,
    FATE_PREMATURE,
)  # noqa: E402
from run_algorithm_workspace_candidate_f_negative_pd_recovery_paired_2025_check import (
    BASELINE_NET,
    DELTA_IMPROVED,
    DELTA_NEAR_FLAT,
    DELTA_WORSENED,
    EXPECTED_6F_NET,
    OUTCOME_RECOVERY,
    OUTCOME_TIMEOUT,
    PairedRecoveryCase,
    build_paired_recovery_cases,
)  # noqa: E402

NUMERIC_EPSILON = 1e-9
COHORT_POSITIVE = "M1_STEP_POSITIVE"
COHORT_NONPOSITIVE = "M1_STEP_NONPOSITIVE"


@dataclass(frozen=True, slots=True)
class MomentumCase:
    """Paired 6G case плюс causal M1 momentum і M1 early-abort close."""

    pair: PairedRecoveryCase
    cohort: str
    m1_abort_r: float
    m1_abort_usd: float
    m1_abort_delta_vs_baseline_r: float
    m1_abort_delta_vs_baseline_usd: float
    m1_abort_delta_vs_6f_r: float
    m1_abort_delta_vs_6f_usd: float


def _risk_usd(case: PairedRecoveryCase) -> float:
    trade = case.fate.trade
    risk = trade.stop_loss_distance * trade.volume
    if risk <= 0.0:
        raise AssertionError("Initial risk must be positive")
    return risk


def _momentum_case(pair: PairedRecoveryCase) -> MomentumCase:
    cohort = COHORT_POSITIVE if pair.step_1_r > NUMERIC_EPSILON else COHORT_NONPOSITIVE
    risk_usd = _risk_usd(pair)
    m1_abort_r = pair.mark_1_r
    m1_abort_usd = m1_abort_r * risk_usd
    baseline_usd = pair.baseline_close_usd
    return MomentumCase(
        pair=pair,
        cohort=cohort,
        m1_abort_r=m1_abort_r,
        m1_abort_usd=m1_abort_usd,
        m1_abort_delta_vs_baseline_r=m1_abort_r - pair.baseline_close_r,
        m1_abort_delta_vs_baseline_usd=m1_abort_usd - baseline_usd,
        m1_abort_delta_vs_6f_r=m1_abort_r - pair.variant_close_r,
        m1_abort_delta_vs_6f_usd=m1_abort_usd - pair.variant_close_usd,
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


def _cohort_summary(name: str, cases: tuple[MomentumCase, ...]) -> None:
    pairs = tuple(case.pair for case in cases)
    recovery = tuple(pair for pair in pairs if pair.outcome == OUTCOME_RECOVERY)
    timeout = tuple(pair for pair in pairs if pair.outcome == OUTCOME_TIMEOUT)
    premature = sum(pair.fate.fate == FATE_PREMATURE for pair in pairs)
    good = sum(pair.fate.fate == FATE_GOOD for pair in pairs)
    baseline_sum = sum(pair.baseline_close_usd for pair in pairs)
    variant_sum = sum(pair.variant_close_usd for pair in pairs)
    delta_sum = sum(pair.delta_usd for pair in pairs)
    improved = sum(pair.delta_class == DELTA_IMPROVED for pair in pairs)
    worsened = sum(pair.delta_class == DELTA_WORSENED for pair in pairs)
    near_flat = sum(pair.delta_class == DELTA_NEAR_FLAT for pair in pairs)
    recovery_m1 = sum(
        pair.outcome == OUTCOME_RECOVERY and pair.close_event_index == 1
        for pair in pairs
    )
    recovery_m2 = sum(
        pair.outcome == OUTCOME_RECOVERY and pair.close_event_index == 2
        for pair in pairs
    )
    recovery_m3 = sum(
        pair.outcome == OUTCOME_RECOVERY and pair.close_event_index == 3
        for pair in pairs
    )

    print(f"  {name}:")
    print(
        f"    count={len(cases)},fate=premature:{premature},good:{good},"
        f"terminal=recovery:{len(recovery)},timeout:{len(timeout)}"
    )
    print(
        "    6f_delta_class="
        f"improved:{improved},worsened:{worsened},near_flat:{near_flat}"
    )
    print(
        "    6f_paired_pnl="
        f"baseline:{baseline_sum:+.2f},variant:{variant_sum:+.2f},"
        f"delta:{delta_sum:+.2f}"
    )
    print(
        "    recovery_timing="
        f"M1:{recovery_m1},M2:{recovery_m2},M3:{recovery_m3},"
        f"none_by_M3:{len(timeout)}"
    )
    print(
        "    causal_m1="
        f"step_mean:{_fmt(_mean(tuple(pair.step_1_r for pair in pairs)), signed=True)},"
        f"mark_mean:{_fmt(_mean(tuple(pair.mark_1_r for pair in pairs)), signed=True)}"
    )
    print(
        "    later_marks="
        f"M2_mean:{_fmt(_mean(tuple(pair.mark_2_r for pair in pairs)), signed=True)},"
        f"M3_mean:{_fmt(_mean(tuple(pair.mark_3_r for pair in pairs)), signed=True)}"
    )
    mfe_mean = _mean(tuple(pair.window_mfe_r for pair in pairs))
    mae_mean = _mean(tuple(pair.window_mae_r for pair in pairs))
    print(
        "    window_excursion="
        f"mfe_mean:{_fmt(mfe_mean, signed=True)},"
        f"mae_mean:{_fmt(mae_mean, signed=True)}"
    )


def _case_line(index: int, case: MomentumCase) -> str:
    pair = case.pair
    trade = pair.fate.trade
    return (
        f"    {index:02d}. {trade.close_timestamp.isoformat()} {trade.direction} "
        f"{case.cohort} fate:{pair.fate.fate} "
        f"6f:{pair.outcome}@M{pair.close_event_index} "
        f"trigger:{pair.baseline_close_r:+.3f}R "
        f"M1:{pair.mark_1_r:+.3f}R step:{pair.step_1_r:+.3f}R "
        f"M2:{pair.mark_2_r:+.3f}R M3:{pair.mark_3_r:+.3f}R "
        f"6f_close:{pair.variant_close_r:+.3f}R "
        f"6f_delta:{pair.delta_r:+.3f}R/{pair.delta_usd:+.2f}$ "
        f"abort_vs_base:{case.m1_abort_delta_vs_baseline_r:+.3f}R/"
        f"{case.m1_abort_delta_vs_baseline_usd:+.2f}$ "
        f"abort_vs_6f:{case.m1_abort_delta_vs_6f_r:+.3f}R/"
        f"{case.m1_abort_delta_vs_6f_usd:+.2f}$"
    )


def main() -> None:
    """Розкласти fixed 6F за causal momentum першої завершеної M1."""
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
    pairs = build_paired_recovery_cases(runtime)
    cases = tuple(_momentum_case(pair) for pair in pairs)
    positive = tuple(case for case in cases if case.cohort == COHORT_POSITIVE)
    nonpositive = tuple(case for case in cases if case.cohort == COHORT_NONPOSITIVE)

    nonpositive_later_recovery = tuple(
        case
        for case in nonpositive
        if case.pair.outcome == OUTCOME_RECOVERY and case.pair.close_event_index > 1
    )
    positive_timeout = tuple(
        case for case in positive if case.pair.outcome == OUTCOME_TIMEOUT
    )

    six_f_delta = sum(pair.delta_usd for pair in pairs)
    six_f_net = summary.net_profit + six_f_delta
    nonpositive_abort_delta_vs_6f = sum(
        case.m1_abort_delta_vs_6f_usd for case in nonpositive
    )
    hybrid_net = six_f_net + nonpositive_abort_delta_vs_6f
    hybrid_delta_vs_baseline = hybrid_net - summary.net_profit
    abort_nonpositive_baseline_sum = sum(
        case.pair.baseline_close_usd for case in nonpositive
    )
    abort_nonpositive_m1_sum = sum(case.m1_abort_usd for case in nonpositive)
    abort_nonpositive_6f_sum = sum(case.pair.variant_close_usd for case in nonpositive)

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )

    assert len(cases) == 18
    assert len(positive) == 8
    assert len(nonpositive) == 10
    assert sum(case.pair.outcome == OUTCOME_RECOVERY for case in positive) == 7
    assert sum(case.pair.outcome == OUTCOME_TIMEOUT for case in positive) == 1
    assert sum(case.pair.outcome == OUTCOME_RECOVERY for case in nonpositive) == 2
    assert sum(case.pair.outcome == OUTCOME_TIMEOUT for case in nonpositive) == 8
    assert len(nonpositive_later_recovery) == 2
    assert len(positive_timeout) == 1
    assert abs(summary.net_profit - BASELINE_NET) < 0.01
    assert abs(six_f_net - EXPECTED_6F_NET) < 0.01
    assert not broker_execution_attempted

    print("Algorithm Workspace Candidate F Negative PD Recovery Momentum 2025 result")
    print("  mode=M1_RECOVERY_MOMENTUM_DIAGNOSTIC_ONLY")
    print(
        "  baseline="
        f"trades:{summary.opened_trades},net:{summary.net_profit:+.2f},"
        f"pf:{summary.profit_factor:.4f},dd:{summary.maximum_drawdown:.2f}"
    )
    print("  source_negative_pd_pairs=18")
    print("  causal_partition=first_completed_M1_step_vs_negative_PD_trigger")
    print("  cohorts=M1_STEP_POSITIVE;M1_STEP_NONPOSITIVE")
    print("  fixed_6f_policy=recovery_to_0R_or_timeout_after_3_completed_M1")
    print(
        "  partition_counts=" f"positive:{len(positive)},nonpositive:{len(nonpositive)}"
    )
    _cohort_summary("m1_step_positive", positive)
    _cohort_summary("m1_step_nonpositive", nonpositive)

    print("  nonpositive_m1_early_abort_diagnostic:")
    print(
        "    paired_pnl="
        f"baseline:{abort_nonpositive_baseline_sum:+.2f},"
        f"m1_abort:{abort_nonpositive_m1_sum:+.2f},"
        f"fixed_6f:{abort_nonpositive_6f_sum:+.2f}"
    )
    abort_vs_baseline = abort_nonpositive_m1_sum - abort_nonpositive_baseline_sum
    print(
        "    aggregate="
        f"abort_vs_baseline:{abort_vs_baseline:+.2f},"
        f"abort_vs_6f:{nonpositive_abort_delta_vs_6f:+.2f}"
    )
    print(
        "    later_recovery_sacrificed_if_abort="
        f"{len(nonpositive_later_recovery)}/{len(nonpositive)}"
    )
    print(
        "    fixed_6f_positive_timeout_exception="
        f"{len(positive_timeout)}/{len(positive)}"
    )
    print("  hybrid_diagnostic=" "positive_step_keep_6f;nonpositive_step_abort_at_M1")
    print(
        "    reconstructed_net="
        f"{hybrid_net:+.2f},delta_vs_baseline:{hybrid_delta_vs_baseline:+.2f},"
        f"delta_vs_6f:{nonpositive_abort_delta_vs_6f:+.2f}"
    )

    print("  nonpositive_later_recovery_exceptions:")
    for index, case in enumerate(nonpositive_later_recovery, start=1):
        print(_case_line(index, case))
    print("  positive_timeout_exception:")
    for index, case in enumerate(positive_timeout, start=1):
        print(_case_line(index, case))

    print("  chronological_momentum_pairs:")
    for index, case in enumerate(cases, start=1):
        print(_case_line(index, case))

    print("  production_trades_modified=False")
    print("  production_exits_modified=False")
    print("  paired_6f_exits_reconstructed_read_only=True")
    print("  m1_early_abort_is_paired_diagnostic_only=True")
    print("  hybrid_full_replay_execution_created=False")
    print("  future_fate_used_only_as_diagnostic_label=True")
    print("  m1_partition_uses_only_first_completed_future_m1=True")
    print("  future_price_used_as_production_exit_gate=False")
    print("  exit_logic_changed=False")
    print("  entry_logic_changed=False")
    print("  macd_quality_thresholds_changed=False")
    print("  alligator_thresholds_changed=False")
    print("  candidate_f_thresholds_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_NEGATIVE_PD_RECOVERY_MOMENTUM_2025_CHECK=OK")


if __name__ == "__main__":
    main()
