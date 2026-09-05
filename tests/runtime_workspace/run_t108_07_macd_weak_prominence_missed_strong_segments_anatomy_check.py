"""run_t108_07_macd_weak_prominence_missed_strong_segments_anatomy_check.py

TEST_ONLY anatomy продовжує factual висновок T108-06 про домінантний
production reject ``MACD_EXTREMUM_TOO_WEAK`` у пропущених STRONG Alligator
segments. Runner виконує незмінений canonical Candidate F Replay для двох
періодів, звіряє production baseline і зіставляє causal MACD quality
diagnostics із post-hoc segment labels.

Для всієї production rejected-популяції та окремо для reject events усередині
missed STRONG segments звіт показує фактичний ``extremum_prominence``, його
відношення до незмінного production minimum і shortfall. STRONG/missed є лише
future outcome labels: вони не беруть участі в MACD evaluation. Threshold
sweep, alternative entry/exit, counterfactual trades та production wiring
навмисно відсутні; Replay використовує completed bars і не звертається до
broker.
"""

from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import median

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_TEST_ROOT = PROJECT_ROOT / "tests" / "runtime_workspace"
TEMP_TEST_ROOT = PROJECT_ROOT / "tests" / "runtime_temp"
for import_path in (PROJECT_ROOT, WORKSPACE_TEST_ROOT, TEMP_TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from run_algorithm_workspace_replay_virtual_execution_check import (  # noqa: E402, E501
    BrokerRequestProbe,
)
from run_t105_10_pd_35_production_regression_check import _workspace  # noqa: E402, E501
from run_t105_15_stochastic_entry_anatomy_check import (  # noqa: E402
    StochasticAnatomyRuntime,
    _production_hashes,
)
from run_t105_18_stochastic_current_bar_production_regression_check import (  # noqa: E402, E501
    PERIODS,
    _assert_geometry,
    _assert_metrics,
    _assert_policy,
    _assert_stochastic_path,
    _broker_execution_attempted,
    _summary_line,
)
from run_t108_06_production_reject_anatomy_strong_trend_segments_check import (  # noqa: E402, E501
    STRONG_MOVE_R,
    TrendSegment,
    _segments,
    _strong_move_r,
)

from core.workspace_algorithm import create_registered_workspace_algorithm  # noqa: E402, E501
from core.workspace_alligator import (  # noqa: E402
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_macd_crossover_quality import (  # noqa: E402
    MACD_QUALITY_REASON_EXTREMUM_TOO_WEAK,
    WorkspaceMacdCrossoverQualityDiagnostic,
)

TEST_ID = "T108-07"
MODE = "RM108_T108_07_MACD_WEAK_PROMINENCE_MISSED_STRONG_SEGMENTS_TEST_ONLY"


@dataclass(frozen=True, slots=True)
class PeriodAnatomy:
    """Незмінні factual вибірки prominence і safety output одного періоду."""

    baseline: str
    minimum_prominence: float
    all_weak: tuple[WorkspaceMacdCrossoverQualityDiagnostic, ...]
    missed_strong_weak: tuple[WorkspaceMacdCrossoverQualityDiagnostic, ...]
    missed_strong_segments: tuple[TrendSegment, ...]
    broker_requests: int


def _missed_strong_segments(
    runtime: StochasticAnatomyRuntime,
    algorithm: WorkspaceMacdAlligatorReplayAlgorithm,
) -> tuple[TrendSegment, ...]:
    """Виділити post-hoc STRONG segments без factual production trade."""

    signal_filter = algorithm.signal_filter
    assert signal_filter is not None
    execution = runtime.replay_execution
    assert execution is not None
    trade_keys = {
        (trade.signal_timestamp, trade.direction)
        for trade in execution.trade_diagnostics()
    }

    missed: list[TrendSegment] = []
    for segment in _segments(tuple(signal_filter.observations)):
        assert all(
            item.timestamp in runtime.strategy_events
            for item in segment.observations
        )
        if _strong_move_r(segment, runtime.strategy_events) < STRONG_MOVE_R:
            continue
        if any(
            (item.timestamp, segment.side) in trade_keys
            for item in segment.observations
        ):
            continue
        missed.append(segment)
    return tuple(missed)


def _diagnostics_in_segments(
    diagnostics: tuple[WorkspaceMacdCrossoverQualityDiagnostic, ...],
    segments: tuple[TrendSegment, ...],
) -> tuple[WorkspaceMacdCrossoverQualityDiagnostic, ...]:
    """Зіставити causal diagnostics з outcome-labeled segment membership."""

    segment_keys = {
        (item.timestamp, segment.side)
        for segment in segments
        for item in segment.observations
    }
    return tuple(
        item
        for item in diagnostics
        if (item.timestamp, item.direction) in segment_keys
    )


def _run_period(spec) -> PeriodAnatomy:
    """Запустити canonical Replay і зібрати лише factual MACD anatomy."""

    broker_probe = BrokerRequestProbe()
    runtime = StochasticAnatomyRuntime(
        _workspace(spec),
        algorithm_factory=create_registered_workspace_algorithm,
        broker_market_provider=broker_probe,
    )
    _assert_policy(runtime)
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()

    _assert_metrics(spec, runtime)
    _assert_stochastic_path(spec, runtime)
    _assert_geometry(runtime)
    assert broker_probe.requests == 0
    assert not _broker_execution_attempted(runtime)
    assert session.completed

    algorithm = runtime.algorithm
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    source = algorithm.source
    assert source is not None
    all_weak = tuple(
        item
        for item in source.quality_diagnostics
        if item.reason_code == MACD_QUALITY_REASON_EXTREMUM_TOO_WEAK
    )
    rejected_records = tuple(
        record
        for record in runtime.historical_signal_records
        if record.filter_reason_code == MACD_QUALITY_REASON_EXTREMUM_TOO_WEAK
    )
    diagnostic_keys = Counter(
        (item.timestamp, item.direction) for item in all_weak
    )
    record_keys = Counter(
        (item.timestamp, item.direction) for item in rejected_records
    )
    assert diagnostic_keys == record_keys
    assert all(item.extremum_prominence is not None for item in all_weak)
    assert all(not item.criterion_prominence_pass for item in all_weak)

    missed_segments = _missed_strong_segments(runtime, algorithm)
    missed_weak = _diagnostics_in_segments(all_weak, missed_segments)
    assert all_weak
    assert missed_segments
    assert missed_weak
    return PeriodAnatomy(
        baseline=_summary_line(runtime),
        minimum_prominence=source.extremum_min_prominence,
        all_weak=all_weak,
        missed_strong_weak=missed_weak,
        missed_strong_segments=missed_segments,
        broker_requests=broker_probe.requests,
    )


def _values(
    diagnostics: tuple[WorkspaceMacdCrossoverQualityDiagnostic, ...],
) -> tuple[float, ...]:
    """Повернути перевірені числові prominence values."""

    values = tuple(item.extremum_prominence for item in diagnostics)
    assert all(item is not None for item in values)
    return tuple(float(item) for item in values)


def _print_population(
    label: str,
    diagnostics: tuple[WorkspaceMacdCrossoverQualityDiagnostic, ...],
    minimum: float,
) -> None:
    """Надрукувати compact distribution без підбору нового threshold."""

    values = _values(diagnostics)
    ratios = tuple(value / minimum for value in values)
    shortfalls = tuple(minimum - value for value in values)
    print(f"  {label}_events={len(values)}")
    print(f"  {label}_prominence_min={min(values):.10f}")
    print(f"  {label}_prominence_median={median(values):.10f}")
    print(f"  {label}_prominence_max={max(values):.10f}")
    print(f"  {label}_ratio_to_production_min_median={median(ratios):.6f}")
    print(f"  {label}_ratio_to_production_min_max={max(ratios):.6f}")
    print(f"  {label}_shortfall_median={median(shortfalls):.10f}")


def _print_period(period: str, anatomy: PeriodAnatomy) -> None:
    """Надрукувати baseline і порівняльну anatomy одного періоду."""

    segments_with_weak = {
        (segment.start_timestamp, segment.side)
        for segment in anatomy.missed_strong_segments
        if _diagnostics_in_segments(anatomy.missed_strong_weak, (segment,))
    }
    print(f"period={period}")
    print(f"  production_baseline={anatomy.baseline}")
    print(
        "  production_extremum_min_prominence="
        f"{anatomy.minimum_prominence:.10f}"
    )
    print(f"  missed_strong_segments={len(anatomy.missed_strong_segments)}")
    print(
        "  missed_strong_segments_with_weak_reject="
        f"{len(segments_with_weak)}"
    )
    _print_population(
        "all_production_weak_reject",
        anatomy.all_weak,
        anatomy.minimum_prominence,
    )
    _print_population(
        "missed_strong_weak_reject",
        anatomy.missed_strong_weak,
        anatomy.minimum_prominence,
    )


def main() -> None:
    """Виконати T108-07 і підтвердити TEST_ONLY safety contracts."""

    production_before = _production_hashes()
    results = {}
    for spec in PERIODS:
        anatomy = _run_period(spec)
        assert anatomy.broker_requests == 0
        results[spec.code] = anatomy
        _print_period(spec.code, anatomy)
    assert _production_hashes() == production_before

    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print("population=PRODUCTION_MACD_EXTREMUM_TOO_WEAK_REJECT_EVENTS")
    print("comparison=ALL_WEAK_REJECTS_VS_MISSED_STRONG_SEGMENT_WEAK_REJECTS")
    print("production_threshold_changed=False")
    print("future_movement_role=OUTCOME_LABEL_ONLY")
    print("completed_bars_only=True")
    print("lookahead_used=False")
    print("threshold_sweep_performed=False")
    print("optimization_performed=False")
    print("counterfactual_trades_simulated=False")
    print("new_entry_rule_created=False")
    print("alternative_exit_simulated=False")
    print("broker_requests=0")
    print("broker_execution_attempted=False")
    print("production_logic_changed=False")
    print("T108_07_MACD_WEAK_PROMINENCE_MISSED_STRONG_SEGMENTS_ANATOMY=OK")


if __name__ == "__main__":
    main()
