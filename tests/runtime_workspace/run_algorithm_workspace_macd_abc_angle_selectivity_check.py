# run_algorithm_workspace_macd_abc_angle_selectivity_check.py — RoadMap99_04J
# -*- coding: utf-8 -*-
"""Порівняння селективності legacy та ABC-кута після prominence/distance.

RoadMap99_04J продовжує 04H/04I на одному EURUSD M1 -> completed M15 stream
2026-01-02..2026-08-11. Змінюються тільки periods MACD: 12/26/9, 8/17/5
та 6/13/4. Для кожного classic crossover спочатку застосовуються однакові
EURUSD diagnostic thresholds prominence=0.000005 і distance=0.000050, а вже
після цього окремо порівнюється селективність старого calibrated angle 45°
та нового ABC-angle в діапазоні 1.50..2.50°.

Мета тесту — не знайти одну універсальну константу, а перевірити, чи ABC-кут
дає стабільніший відсоток відсікання між різними швидкостями MACD. Окремо
2.06° використовується лише як regression anchor для шести ручних кейсів:
це приблизний ABC-відповідник старої візуальної reference-точки 45°, а не
production recommendation.

Production MACD Quality, UI, Alligator, NEXT_BAR_OPEN і broker execution не
змінюються. Усі обчислення використовують тільки завершені observations;
ABC C отримується лінійною інтерполяцією між попереднім і поточним MACD bar,
тому майбутні дані не використовуються.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_history import WorkspaceCsvHistoryLoader  # noqa: E402
from core.workspace_indicator_profile import (  # noqa: E402
    WORKSPACE_INDICATOR_MA_EXPONENTIAL,
    WORKSPACE_INDICATOR_SOURCE_CLOSE,
)
from core.workspace_macd import (  # noqa: E402
    WorkspaceMacdRuntimeProfile,
    WorkspaceMacdSignalSource,
)
from core.workspace_macd_cross_angle_abc import (  # noqa: E402
    WorkspaceMacdCrossAngleAbcConfig,
    build_workspace_macd_cross_angle_abc_report,
)
from core.workspace_macd_crossover_quality import (  # noqa: E402
    WorkspaceMacdCrossoverQualityConfig,
    build_workspace_macd_crossover_quality_diagnostics,
    calibrated_macd_cross_angle_reference_y_per_minute,
)
from core.workspace_timeframe_aggregation import (  # noqa: E402
    WorkspaceTimeframeAggregator,
)

M1_FILE = (
    PROJECT_ROOT
    / "data"
    / "history"
    / "IB"
    / "EURUSD"
    / "M1"
    / "2026-01-02_2026-08-11_IB_EURUSD_M1.csv"
)
START_UTC = datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
END_UTC = datetime(2026, 8, 11, 8, 24, tzinfo=UTC)
EURUSD_VALUE_SCALE = 10000.0
TIME_UNIT_SECONDS = 60.0
PROMINENCE = 0.000005
DISTANCE = 0.000050
LEGACY_ANGLE = 45.0
ABC_THRESHOLDS = (1.50, 1.75, 2.00, 2.25, 2.50)
MANUAL_REFERENCE_ABC = 2.06

MANUAL_CASES = (
    ("A_NEAR_41", datetime(2026, 1, 5, 9, 30, tzinfo=UTC), False),
    ("B_NEAR_42", datetime(2026, 1, 5, 14, 15, tzinfo=UTC), False),
    (
        "C_VISUAL_45_REFERENCE",
        datetime(2026, 1, 9, 14, 15, tzinfo=UTC),
        True,
    ),
    ("D_KNOWN_WEAK", datetime(2026, 1, 7, 17, 30, tzinfo=UTC), False),
    (
        "E_ANGLE_PASS_WEAK_EXTREMUM",
        datetime(2026, 1, 4, 22, 45, tzinfo=UTC),
        True,
    ),
    (
        "F_NO_EXTREMUM_LOW_ANGLE",
        datetime(2026, 1, 2, 21, 45, tzinfo=UTC),
        False,
    ),
)


@dataclass(frozen=True, slots=True)
class MacdVariant:
    """Один isolated MACD profile для контрольованого порівняння."""

    code: str
    fast_period: int
    slow_period: int
    signal_period: int


@dataclass(frozen=True, slots=True)
class AbcThresholdResult:
    """Кількість і частка P+D candidates, що пройшли один ABC threshold."""

    threshold: float
    accepted: int
    pass_rate: float


@dataclass(frozen=True, slots=True)
class MacdSelectivityResult:
    """Селективність legacy та ABC angle для одного MACD profile."""

    variant: MacdVariant
    crosses: int
    prominence_distance_candidates: int
    legacy_accepted: int
    legacy_pass_rate: float
    abc_results: tuple[AbcThresholdResult, ...]
    manual_reference_accepted: int
    manual_reference_pass_rate: float


VARIANTS = (
    MacdVariant("BASELINE", 12, 26, 9),
    MacdVariant("FAST", 8, 17, 5),
    MacdVariant("VERY_FAST", 6, 13, 4),
)


def _load_m15_events():
    """Один раз завантажити M1 та сформувати спільні completed M15 bars."""
    data_set = WorkspaceCsvHistoryLoader().load(
        file_path=M1_FILE,
        broker="IB",
        symbol="EURUSD",
        timeframe="M1",
        start_utc=START_UTC,
        end_utc=END_UTC,
        source_timezone="UTC",
        delimiter="AUTO",
        decimal_separator=".",
        default_spread=0.00012,
        source_name="IB_EURUSD_M1_RM99_ABC_ANGLE_SELECTIVITY",
    )
    aggregator = WorkspaceTimeframeAggregator(
        source_timeframe="M1",
        target_timeframe="M15",
    )
    events = []
    for event in data_set.events:
        completed = aggregator.on_market_event(event)
        if completed is not None:
            events.append(completed.event)
    final = aggregator.complete()
    if final is not None:
        events.append(final.event)
    return data_set, aggregator, tuple(events)


def _runtime_profile(variant: MacdVariant) -> WorkspaceMacdRuntimeProfile:
    """Побудувати isolated Close/EMA/EMA/shift=0 runtime profile."""
    periods = (
        f"{variant.fast_period}_{variant.slow_period}_{variant.signal_period}"
    )
    return WorkspaceMacdRuntimeProfile(
        profile_uid=f"RM99_ABC_SELECTIVITY_{periods}",
        profile_revision=1,
        profile_name=f"RM99 ABC Selectivity {periods}",
        source=WORKSPACE_INDICATOR_SOURCE_CLOSE,
        fast_period=variant.fast_period,
        slow_period=variant.slow_period,
        signal_period=variant.signal_period,
        oscillator_ma_type=WORKSPACE_INDICATOR_MA_EXPONENTIAL,
        signal_ma_type=WORKSPACE_INDICATOR_MA_EXPONENTIAL,
        shift=0,
    )


def _run_variant(events, variant: MacdVariant) -> MacdSelectivityResult:
    """Порахувати P+D pool і angle selectivity без зміни production."""
    source = WorkspaceMacdSignalSource(
        enabled=True,
        mode="LINEAR",
        runtime_profile=_runtime_profile(variant),
    )
    for event in events:
        source.on_market_event(event)

    quality = build_workspace_macd_crossover_quality_diagnostics(
        source.observations,
        config=WorkspaceMacdCrossoverQualityConfig(
            angle_reference_y_per_minute=(
                calibrated_macd_cross_angle_reference_y_per_minute()
            ),
            extremum_min_prominence=PROMINENCE,
            extremum_to_cross_min_distance=DISTANCE,
            cross_min_angle_degrees=LEGACY_ANGLE,
        ),
    )
    abc = build_workspace_macd_cross_angle_abc_report(
        source.observations,
        config=WorkspaceMacdCrossAngleAbcConfig(
            indicator_value_scale=EURUSD_VALUE_SCALE,
            time_unit_seconds=TIME_UNIT_SECONDS,
        ),
    )
    abc_by_timestamp = {
        diagnostic.timestamp: diagnostic for diagnostic in abc.diagnostics
    }
    candidates = tuple(
        diagnostic
        for diagnostic in quality.signals
        if diagnostic.extremum_found
        and diagnostic.criterion_prominence_pass
        and diagnostic.criterion_distance_pass
    )
    if not candidates:
        raise AssertionError("prominence/distance candidate pool is empty")

    abc_results = []
    for threshold in ABC_THRESHOLDS:
        accepted = sum(
            abc_by_timestamp[item.timestamp].angle_degrees is not None
            and abc_by_timestamp[item.timestamp].angle_degrees >= threshold
            for item in candidates
        )
        abc_results.append(
            AbcThresholdResult(
                threshold=threshold,
                accepted=accepted,
                pass_rate=accepted / len(candidates),
            )
        )

    reference_accepted = sum(
        abc_by_timestamp[item.timestamp].angle_degrees is not None
        and abc_by_timestamp[item.timestamp].angle_degrees
        >= MANUAL_REFERENCE_ABC
        for item in candidates
    )
    return MacdSelectivityResult(
        variant=variant,
        crosses=quality.total_crosses,
        prominence_distance_candidates=len(candidates),
        legacy_accepted=quality.final_quality_pass,
        legacy_pass_rate=quality.final_quality_pass / len(candidates),
        abc_results=tuple(abc_results),
        manual_reference_accepted=reference_accepted,
        manual_reference_pass_rate=reference_accepted / len(candidates),
    )


def _spread(values: tuple[float, ...]) -> float:
    """Розкид pass-rate між профілями у percentage points."""
    return (max(values) - min(values)) * 100.0


def _print_result(result: MacdSelectivityResult) -> None:
    """Надрукувати angle selectivity одного MACD profile."""
    periods = (
        f"{result.variant.fast_period}/"
        f"{result.variant.slow_period}/"
        f"{result.variant.signal_period}"
    )
    print(
        f"  {result.variant.code} {periods}: crosses={result.crosses}, "
        f"P+D={result.prominence_distance_candidates}, "
        f"legacy45={result.legacy_accepted}/"
        f"{result.legacy_pass_rate:.2%}, "
        f"ABC2.06={result.manual_reference_accepted}/"
        f"{result.manual_reference_pass_rate:.2%}"
    )
    sweep = " ".join(
        f"{item.threshold:.2f}:{item.accepted}/{item.pass_rate:.2%}"
        for item in result.abc_results
    )
    print(f"    ABC sweep {sweep}")


def main() -> None:
    """Запустити RoadMap99_04J conditional angle selectivity regression."""
    print(
        "Algorithm Workspace MACD ABC Angle Selectivity Check — RoadMap99_04J"
    )
    print(
        "  After the same EURUSD prominence=0.000005 and "
        "distance=0.000050 pool, compare legacy45 with ABC 1.50..2.50deg."
    )
    print(
        "  ABC 2.06deg is manual-reference regression only, not a universal "
        "production threshold; production remains unchanged."
    )
    if not M1_FILE.is_file():
        raise FileNotFoundError("Real EURUSD M1 history is required: " + str(M1_FILE))

    data_set, aggregator, events = _load_m15_events()
    results = tuple(_run_variant(events, variant) for variant in VARIANTS)
    repeated = tuple(_run_variant(events, variant) for variant in VARIANTS)
    assert results == repeated

    assert data_set.report.accepted_rows == 224125
    assert aggregator.completed_bars == 14941
    assert tuple(result.crosses for result in results) == (1154, 1864, 2443)
    assert tuple(
        result.prominence_distance_candidates for result in results
    ) == (337, 631, 897)
    assert tuple(result.legacy_accepted for result in results) == (114, 122, 142)

    legacy_spread = _spread(tuple(result.legacy_pass_rate for result in results))
    abc_spreads = {
        threshold: _spread(
            tuple(
                next(
                    item.pass_rate
                    for item in result.abc_results
                    if item.threshold == threshold
                )
                for result in results
            )
        )
        for threshold in ABC_THRESHOLDS
    }
    reference_spread = _spread(
        tuple(result.manual_reference_pass_rate for result in results)
    )

    baseline_source = WorkspaceMacdSignalSource(
        enabled=True,
        mode="LINEAR",
        runtime_profile=_runtime_profile(VARIANTS[0]),
    )
    for event in events:
        baseline_source.on_market_event(event)
    baseline_abc = build_workspace_macd_cross_angle_abc_report(
        baseline_source.observations,
        config=WorkspaceMacdCrossAngleAbcConfig(
            indicator_value_scale=EURUSD_VALUE_SCALE,
            time_unit_seconds=TIME_UNIT_SECONDS,
        ),
    )
    manual_by_timestamp = {
        item.timestamp: item for item in baseline_abc.diagnostics
    }
    manual_match = True
    for code, timestamp, expected_pass in MANUAL_CASES:
        angle = manual_by_timestamp[timestamp].angle_degrees
        if angle is None:
            raise AssertionError(f"ABC angle is missing for {code}")
        actual_pass = angle >= MANUAL_REFERENCE_ABC
        manual_match = manual_match and actual_pass == expected_pass

    print("Algorithm Workspace MACD ABC Angle Selectivity result")
    print(f"  source_rows={data_set.report.accepted_rows}")
    print(f"  completed_m15_bars={aggregator.completed_bars}")
    print("  parameter_model=ADMISSIBLE_RANGE_NOT_UNIVERSAL_CONSTANT")
    print("  angle_candidate_pool=EXTREMUM_AND_PROMINENCE_AND_DISTANCE")
    for result in results:
        _print_result(result)
    print(f"  legacy45_cross_profile_pass_spread={legacy_spread:.2f}pp")
    print(
        "  abc_cross_profile_pass_spread="
        + " ".join(
            f"{threshold:.2f}:{abc_spreads[threshold]:.2f}pp"
            for threshold in ABC_THRESHOLDS
        )
    )
    print(
        f"  abc_manual_reference_2_06_spread={reference_spread:.2f}pp"
    )
    print(f"  abc_2_06_manual_anchor_match={manual_match}")
    print(
        "  abc_conditional_selectivity_more_profile_stable_than_legacy="
        f"{reference_spread < legacy_spread}"
    )
    print("  production_angle_logic_changed=False")
    print("  production_quality_thresholds_changed=False")
    print("  future_observations_used=False")
    print("  deterministic=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")

    assert manual_match
    assert reference_spread < legacy_spread
    assert abc_spreads[2.00] < legacy_spread
    assert abc_spreads[2.25] < legacy_spread
    print("ALGORITHM_WORKSPACE_MACD_ABC_ANGLE_SELECTIVITY_CHECK=OK")


if __name__ == "__main__":
    main()
