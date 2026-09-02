# -*- coding: utf-8 -*-
"""RoadMap102 / 6I: two-step M1 deterioration anatomy OOS 2025.

Runner повторює frozen Candidate F Replay 2025. Read-only відтворює
paired 6F cases для 18 production negative PROFIT_DRAWDOWN exits.
Для cases із непозитивною першою M1 перевіряється одна causal ознака:
M1 step <= 0 і M2 step <= 0. Для неї порівнюються production PD close,
early-abort на M2 і fixed 6F close.

Це diagnostic-only аналіз. Production exits не змінюються. Нового
full Replay counterfactual execution немає. Future fate використовується
лише як label, а PASS не залежить від PnL/PF/DD.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

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
from run_algorithm_workspace_candidate_f_negative_pd_fate_2025_check import (  # noqa: E402,E501
    FATE_GOOD,
    FATE_PREMATURE,
)  # noqa: E402
from run_algorithm_workspace_candidate_f_negative_pd_recovery_paired_2025_check import (  # noqa: E402,E501
    BASELINE_NET,
    EXPECTED_6F_NET,
    OUTCOME_RECOVERY,
    OUTCOME_TIMEOUT,
    PairedRecoveryCase,
    build_paired_recovery_cases,
)  # noqa: E402

NUMERIC_EPSILON = 1e-9
COHORT_TWO_STEP = "M1_NONPOSITIVE_M2_NONPOSITIVE"
COHORT_M2_REBOUND = "M1_NONPOSITIVE_M2_POSITIVE"


@dataclass(frozen=True, slots=True)
class TwoStepCase:
    """Paired case плюс M2 early-abort counterfactual."""

    pair: PairedRecoveryCase
    cohort: str
    m2_abort_r: float
    m2_abort_usd: float
    abort_delta_vs_baseline_r: float
    abort_delta_vs_baseline_usd: float
    abort_delta_vs_6f_r: float
    abort_delta_vs_6f_usd: float


def _risk_usd(pair: PairedRecoveryCase) -> float:
    trade = pair.fate.trade
    risk = trade.stop_loss_distance * trade.volume
    if risk <= 0.0:
        raise AssertionError("Initial risk must be positive")
    return risk


def _two_step_case(pair: PairedRecoveryCase) -> TwoStepCase | None:
    if pair.step_1_r > NUMERIC_EPSILON:
        return None
    cohort = COHORT_M2_REBOUND if pair.step_2_r > NUMERIC_EPSILON else COHORT_TWO_STEP
    risk_usd = _risk_usd(pair)
    m2_abort_r = pair.mark_2_r
    m2_abort_usd = m2_abort_r * risk_usd
    return TwoStepCase(
        pair=pair,
        cohort=cohort,
        m2_abort_r=m2_abort_r,
        m2_abort_usd=m2_abort_usd,
        abort_delta_vs_baseline_r=m2_abort_r - pair.baseline_close_r,
        abort_delta_vs_baseline_usd=m2_abort_usd - pair.baseline_close_usd,
        abort_delta_vs_6f_r=m2_abort_r - pair.variant_close_r,
        abort_delta_vs_6f_usd=m2_abort_usd - pair.variant_close_usd,
    )


def _fmt(value: float | None, digits: int = 3, signed: bool = False) -> str:
    if value is None:
        return "NONE"
    if signed:
        return f"{value:+.{digits}f}"
    return f"{value:.{digits}f}"


def _mean(values: tuple[float, ...]) -> float | None:
    return mean(values) if values else None


def _cohort_summary(name: str, cases: tuple[TwoStepCase, ...]) -> None:
    pairs = tuple(case.pair for case in cases)
    recovery = sum(pair.outcome == OUTCOME_RECOVERY for pair in pairs)
    timeout = sum(pair.outcome == OUTCOME_TIMEOUT for pair in pairs)
    premature = sum(pair.fate.fate == FATE_PREMATURE for pair in pairs)
    good = sum(pair.fate.fate == FATE_GOOD for pair in pairs)
    baseline_sum = sum(pair.baseline_close_usd for pair in pairs)
    abort_sum = sum(case.m2_abort_usd for case in cases)
    six_f_sum = sum(pair.variant_close_usd for pair in pairs)
    abort_vs_baseline = abort_sum - baseline_sum
    abort_vs_6f = abort_sum - six_f_sum

    print(f"  {name}:")
    print(
        f"    count={len(cases)},fate=premature:{premature},good:{good},"
        f"6f_terminal=recovery:{recovery},timeout:{timeout}"
    )
    print(
        "    paired_pnl="
        f"baseline:{baseline_sum:+.2f},m2_abort:{abort_sum:+.2f},"
        f"fixed_6f:{six_f_sum:+.2f}"
    )
    print(
        "    aggregate_delta="
        f"abort_vs_baseline:{abort_vs_baseline:+.2f},"
        f"abort_vs_6f:{abort_vs_6f:+.2f}"
    )
    s1_mean = _mean(tuple(pair.step_1_r for pair in pairs))
    s2_mean = _mean(tuple(pair.step_2_r for pair in pairs))
    s3_mean = _mean(tuple(pair.step_3_r for pair in pairs))
    print(
        "    causal_steps="
        f"s1_mean:{_fmt(s1_mean, signed=True)},"
        f"s2_mean:{_fmt(s2_mean, signed=True)},"
        f"s3_mean:{_fmt(s3_mean, signed=True)}"
    )
    m1_mean = _mean(tuple(pair.mark_1_r for pair in pairs))
    m2_mean = _mean(tuple(pair.mark_2_r for pair in pairs))
    m3_mean = _mean(tuple(pair.mark_3_r for pair in pairs))
    print(
        "    marks="
        f"m1_mean:{_fmt(m1_mean, signed=True)},"
        f"m2_mean:{_fmt(m2_mean, signed=True)},"
        f"m3_mean:{_fmt(m3_mean, signed=True)}"
    )


def _case_line(index: int, case: TwoStepCase) -> str:
    pair = case.pair
    trade = pair.fate.trade
    m2_to_m3 = pair.mark_3_r - pair.mark_2_r
    return (
        f"    {index:02d}. {trade.close_timestamp.isoformat()} {trade.direction} "
        f"{case.cohort} fate:{pair.fate.fate} "
        f"6f:{pair.outcome}@M{pair.close_event_index} "
        f"base:{pair.baseline_close_r:+.3f}R "
        f"M1:{pair.mark_1_r:+.3f}R s1:{pair.step_1_r:+.3f}R "
        f"M2:{pair.mark_2_r:+.3f}R s2:{pair.step_2_r:+.3f}R "
        f"M3:{pair.mark_3_r:+.3f}R s3:{pair.step_3_r:+.3f}R "
        f"M2toM3:{m2_to_m3:+.3f}R "
        f"abortM2:{case.m2_abort_r:+.3f}R "
        f"6f_close:{pair.variant_close_r:+.3f}R "
        f"abort_vs_base:{case.abort_delta_vs_baseline_r:+.3f}R/"
        f"{case.abort_delta_vs_baseline_usd:+.2f}$ "
        f"abort_vs_6f:{case.abort_delta_vs_6f_r:+.3f}R/"
        f"{case.abort_delta_vs_6f_usd:+.2f}$"
    )


def main() -> None:
    """Перевірити fixed two-step M1 deterioration як paired diagnostic."""
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
    cases = tuple(case for pair in pairs if (case := _two_step_case(pair)) is not None)
    two_step = tuple(case for case in cases if case.cohort == COHORT_TWO_STEP)
    rebound = tuple(case for case in cases if case.cohort == COHORT_M2_REBOUND)

    six_f_delta = sum(pair.delta_usd for pair in pairs)
    six_f_net = summary.net_profit + six_f_delta
    two_step_abort_delta_vs_6f = sum(case.abort_delta_vs_6f_usd for case in two_step)
    hybrid_net = six_f_net + two_step_abort_delta_vs_6f
    hybrid_delta_vs_baseline = hybrid_net - summary.net_profit

    sacrificed_recovery = sum(
        case.pair.outcome == OUTCOME_RECOVERY for case in two_step
    )
    shortened_timeout = sum(case.pair.outcome == OUTCOME_TIMEOUT for case in two_step)
    rebound_recovery = sum(case.pair.outcome == OUTCOME_RECOVERY for case in rebound)
    rebound_timeout = sum(case.pair.outcome == OUTCOME_TIMEOUT for case in rebound)
    m2_to_m3_improved = sum(
        case.pair.mark_3_r > case.pair.mark_2_r + NUMERIC_EPSILON for case in two_step
    )
    m2_to_m3_worsened = sum(
        case.pair.mark_3_r < case.pair.mark_2_r - NUMERIC_EPSILON for case in two_step
    )
    m2_to_m3_flat = len(two_step) - m2_to_m3_improved - m2_to_m3_worsened

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )

    assert len(pairs) == 18
    assert len(cases) == 10
    assert len(two_step) == 5
    assert len(rebound) == 5
    assert sacrificed_recovery == 0
    assert shortened_timeout == 5
    assert rebound_recovery == 2
    assert rebound_timeout == 3
    assert abs(summary.net_profit - BASELINE_NET) < 0.01
    assert abs(six_f_net - EXPECTED_6F_NET) < 0.01
    assert not broker_execution_attempted

    print(
        "Algorithm Workspace Candidate F Negative PD Two-Step "
        "Deterioration 2025 result"
    )
    print("  mode=TWO_STEP_M1_DETERIORATION_DIAGNOSTIC_ONLY")
    print(
        "  baseline="
        f"trades:{summary.opened_trades},net:{summary.net_profit:+.2f},"
        f"pf:{summary.profit_factor:.4f},dd:{summary.maximum_drawdown:.2f}"
    )
    print("  source_negative_pd_pairs=18")
    print("  source_m1_nonpositive_pairs=10")
    print("  fixed_candidate=" "M1_STEP_NONPOSITIVE_AND_M2_STEP_NONPOSITIVE")
    print("  candidate_action=paired_M2_early_abort_diagnostic_only")
    print("  control=M1_STEP_NONPOSITIVE_AND_M2_STEP_POSITIVE")
    _cohort_summary("two_step_deterioration", two_step)
    _cohort_summary("m2_rebound_control", rebound)

    print("  two_step_candidate_effect:")
    print(
        f"    recovery_sacrificed={sacrificed_recovery}/{len(two_step)},"
        f"timeouts_shortened={shortened_timeout}/{len(two_step)}"
    )
    print(
        "    M2_to_M3="
        f"improved:{m2_to_m3_improved},worsened:{m2_to_m3_worsened},"
        f"flat:{m2_to_m3_flat}"
    )
    print(
        "    hybrid_reconstructed_net="
        f"{hybrid_net:+.2f},delta_vs_baseline:{hybrid_delta_vs_baseline:+.2f},"
        f"delta_vs_6f:{two_step_abort_delta_vs_6f:+.2f}"
    )

    print("  two_step_candidate_cases:")
    for index, case in enumerate(two_step, start=1):
        print(_case_line(index, case))
    print("  m2_rebound_control_cases:")
    for index, case in enumerate(rebound, start=1):
        print(_case_line(index, case))

    print("  production_trades_modified=False")
    print("  production_exits_modified=False")
    print("  paired_6f_exits_reconstructed_read_only=True")
    print("  m2_early_abort_is_paired_diagnostic_only=True")
    print("  hybrid_full_replay_execution_created=False")
    print("  future_fate_used_only_as_diagnostic_label=True")
    print("  candidate_uses_only_first_two_completed_future_m1=True")
    print("  future_price_used_as_production_exit_gate=False")
    print("  exit_logic_changed=False")
    print("  entry_logic_changed=False")
    print("  macd_quality_thresholds_changed=False")
    print("  alligator_thresholds_changed=False")
    print("  candidate_f_thresholds_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print(
        "ALGORITHM_WORKSPACE_CANDIDATE_F_NEGATIVE_PD_"
        "TWO_STEP_DETERIORATION_2025_CHECK=OK"
    )


if __name__ == "__main__":
    main()
