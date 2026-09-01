# run_algorithm_workspace_macd_quality_scale_normalization_check.py — RoadMap99_04I
# -*- coding: utf-8 -*-
"""Перевірка масштабування prominence/distance між MACD profiles у RoadMap99_04I.

Тест використовує один історичний EURUSD stream M1 -> completed M15 за
2026-01-02..2026-08-11 і змінює тільки periods MACD: 12/26/9, 8/17/5 та
6/13/4. Для всіх classic crossover обчислюються ті самі extremum diagnostics
3 -> 5 -> 7 без production thresholds, після чого порівнюються абсолютні
prominence/distance та одна проста кандидатна нормалізація через causal rolling
median ``abs(MACD-Signal)`` за 32/64/128 попередніх завершених M15 bars.

Мета — не примусово нормалізувати параметри, а перевірити, чи така операція
справді робить шкалу стабільнішою між різними швидкостями MACD. Окремо
вимірюється selectivity на reference-порогах 0.000005/0.000050, які тут є лише
контрольними точками EURUSD, а не універсальними market constants. Якщо
проста histogram-normalization погіршує cross-profile stability, тест повинен
це зафіксувати і залишити production незмінним.

RoadMap99_04I diagnostic-only: ABC angle, Alligator, risk, NEXT_BAR_OPEN,
production MACD Quality та broker execution не змінюються. Усі rolling scale
використовують тільки observations до поточного crossover, тому look-ahead
відсутній.
"""

from __future__ import annotations

import math
import statistics
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
REFERENCE_PROMINENCE = 0.000005
REFERENCE_DISTANCE = 0.000050
ROLLING_LOOKBACKS = (32, 64, 128)
PRIMARY_ROLLING_LOOKBACK = 64


@dataclass(frozen=True, slots=True)
class MacdQualityProfileVariant:
    """Один MACD profile з незмінними Close/EMA/EMA/shift=0."""

    code: str
    fast_period: int
    slow_period: int
    signal_period: int


@dataclass(frozen=True, slots=True)
class RollingScaleStatistics:
    """Медіани dimensionless prominence/distance для одного lookback."""

    lookback_bars: int
    prominence_median: float
    distance_median: float


@dataclass(frozen=True, slots=True)
class MacdQualityScaleStatistics:
    """Порівнювані raw та normalized quality metrics одного profile."""

    variant: MacdQualityProfileVariant
    crosses: int
    extremum_found: int
    extremum_not_found: int
    raw_prominence_median: float
    raw_distance_median: float
    prominence_reference_pass_rate: float
    distance_reference_pass_rate: float
    combined_reference_pass_rate: float
    rolling: tuple[RollingScaleStatistics, ...]


VARIANTS = (
    MacdQualityProfileVariant("BASELINE", 12, 26, 9),
    MacdQualityProfileVariant("FAST", 8, 17, 5),
    MacdQualityProfileVariant("VERY_FAST", 6, 13, 4),
)


def _load_m15_events():
    """Один раз завантажити M1 та сформувати спільний completed M15 stream."""
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
        source_name="IB_EURUSD_M1_RM99_QUALITY_SCALE_NORMALIZATION",
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


def _runtime_profile(
    variant: MacdQualityProfileVariant,
) -> WorkspaceMacdRuntimeProfile:
    """Побудувати isolated runtime profile без зміни profile catalog."""
    return WorkspaceMacdRuntimeProfile(
        profile_uid=(
            "RM99_QUALITY_SCALE_"
            f"{variant.fast_period}_{variant.slow_period}_{variant.signal_period}"
        ),
        profile_revision=1,
        profile_name=(
            "RM99 Quality Scale "
            f"{variant.fast_period}/{variant.slow_period}/{variant.signal_period}"
        ),
        source=WORKSPACE_INDICATOR_SOURCE_CLOSE,
        fast_period=variant.fast_period,
        slow_period=variant.slow_period,
        signal_period=variant.signal_period,
        oscillator_ma_type=WORKSPACE_INDICATOR_MA_EXPONENTIAL,
        signal_ma_type=WORKSPACE_INDICATOR_MA_EXPONENTIAL,
        shift=0,
    )


def _rolling_scale(
    observations,
    *,
    cross_index: int,
    lookback_bars: int,
) -> float:
    """Causal median abs(histogram) тільки до поточного crossover."""
    start = max(0, cross_index - lookback_bars)
    values = tuple(
        abs(observation.histogram)
        for observation in observations[start:cross_index]
        if observation.histogram is not None and abs(observation.histogram) > 0.0
    )
    if not values:
        raise AssertionError("rolling histogram scale is unavailable")
    scale = statistics.median(values)
    if not math.isfinite(scale) or scale <= 0.0:
        raise AssertionError("rolling histogram scale must be positive")
    return scale


def _run_variant(
    events,
    variant: MacdQualityProfileVariant,
) -> MacdQualityScaleStatistics:
    """Розрахувати raw та candidate-normalized metrics одного MACD profile."""
    source = WorkspaceMacdSignalSource(
        enabled=True,
        mode="LINEAR",
        runtime_profile=_runtime_profile(variant),
    )
    for event in events:
        source.on_market_event(event)

    quality_config = WorkspaceMacdCrossoverQualityConfig(
        angle_reference_y_per_minute=(
            calibrated_macd_cross_angle_reference_y_per_minute()
        ),
        extremum_min_prominence=0.0,
        extremum_to_cross_min_distance=0.0,
        cross_min_angle_degrees=0.0,
    )
    report = build_workspace_macd_crossover_quality_diagnostics(
        source.observations,
        config=quality_config,
    )
    repeated = build_workspace_macd_crossover_quality_diagnostics(
        source.observations,
        config=quality_config,
    )
    assert report == repeated

    timestamp_to_index = {
        observation.timestamp: index
        for index, observation in enumerate(source.observations)
    }
    found = tuple(
        diagnostic
        for diagnostic in report.signals
        if diagnostic.extremum_prominence is not None
        and diagnostic.extremum_to_cross_distance is not None
    )
    raw_prominence = tuple(
        diagnostic.extremum_prominence
        for diagnostic in found
        if diagnostic.extremum_prominence is not None
    )
    raw_distance = tuple(
        diagnostic.extremum_to_cross_distance
        for diagnostic in found
        if diagnostic.extremum_to_cross_distance is not None
    )
    assert len(raw_prominence) == len(found)
    assert len(raw_distance) == len(found)

    prominence_pass = sum(value >= REFERENCE_PROMINENCE for value in raw_prominence)
    distance_pass = sum(value >= REFERENCE_DISTANCE for value in raw_distance)
    combined_pass = sum(
        prominence >= REFERENCE_PROMINENCE and distance >= REFERENCE_DISTANCE
        for prominence, distance in zip(raw_prominence, raw_distance)
    )

    rolling_statistics = []
    for lookback_bars in ROLLING_LOOKBACKS:
        normalized_prominence = []
        normalized_distance = []
        for diagnostic in found:
            cross_index = timestamp_to_index[diagnostic.timestamp]
            scale = _rolling_scale(
                source.observations,
                cross_index=cross_index,
                lookback_bars=lookback_bars,
            )
            normalized_prominence.append(diagnostic.extremum_prominence / scale)
            normalized_distance.append(diagnostic.extremum_to_cross_distance / scale)
        rolling_statistics.append(
            RollingScaleStatistics(
                lookback_bars=lookback_bars,
                prominence_median=statistics.median(normalized_prominence),
                distance_median=statistics.median(normalized_distance),
            )
        )

    return MacdQualityScaleStatistics(
        variant=variant,
        crosses=report.total_crosses,
        extremum_found=len(found),
        extremum_not_found=report.extremum_not_found,
        raw_prominence_median=statistics.median(raw_prominence),
        raw_distance_median=statistics.median(raw_distance),
        prominence_reference_pass_rate=prominence_pass / len(found),
        distance_reference_pass_rate=distance_pass / len(found),
        combined_reference_pass_rate=combined_pass / len(found),
        rolling=tuple(rolling_statistics),
    )


def _ratio(values: tuple[float, ...]) -> float:
    """Повернути max/min ratio для додатних profile statistics."""
    if not values or min(values) <= 0.0:
        raise AssertionError("positive values are required for ratio")
    return max(values) / min(values)


def _primary_rolling(run: MacdQualityScaleStatistics) -> RollingScaleStatistics:
    """Знайти diagnostic для reference lookback=64 bars."""
    return next(
        item for item in run.rolling if item.lookback_bars == PRIMARY_ROLLING_LOOKBACK
    )


def _print_run(run: MacdQualityScaleStatistics) -> None:
    """Надрукувати profile metrics компактно й придатно для regression."""
    periods = (
        f"{run.variant.fast_period}/"
        f"{run.variant.slow_period}/"
        f"{run.variant.signal_period}"
    )
    print(
        f"  {run.variant.code} {periods}: crosses={run.crosses}, "
        f"extremum={run.extremum_found}/{run.extremum_not_found}, "
        f"raw_med prominence/distance="
        f"{run.raw_prominence_median:.8f}/"
        f"{run.raw_distance_median:.8f}, "
        f"reference_pass P/D/both="
        f"{run.prominence_reference_pass_rate:.2%}/"
        f"{run.distance_reference_pass_rate:.2%}/"
        f"{run.combined_reference_pass_rate:.2%}"
    )
    rolling_text = " ".join(
        (
            f"L{item.lookback_bars}:"
            f"{item.prominence_median:.4f}/"
            f"{item.distance_median:.4f}"
        )
        for item in run.rolling
    )
    print(f"    normalized_medians prominence/distance {rolling_text}")


def main() -> None:
    """Запустити RoadMap99_04I cross-profile scale diagnostic."""
    print(
        "Algorithm Workspace MACD Quality Scale Normalization Check — " "RoadMap99_04I"
    )
    print(
        "  Compare 12/26/9 -> 8/17/5 -> 6/13/4. Test raw "
        "prominence/distance and causal rolling histogram normalization; "
        "production remains unchanged."
    )
    print(
        "  Reference 0.000005/0.000050 is EURUSD diagnostic only, not a "
        "universal constant; rolling lookbacks 32/64/128 are sensitivity "
        "checks."
    )

    data_set, aggregator, events = _load_m15_events()
    completed = []
    for index, variant in enumerate(VARIANTS, start=1):
        periods = (
            f"{variant.fast_period}/"
            f"{variant.slow_period}/"
            f"{variant.signal_period}"
        )
        print(
            "MACD Quality Scale Normalization: running "
            f"{index}/{len(VARIANTS)} profile={periods} ..."
        )
        completed.append(_run_variant(events, variant))
    runs = tuple(completed)

    raw_prominence_ratio = _ratio(tuple(run.raw_prominence_median for run in runs))
    raw_distance_ratio = _ratio(tuple(run.raw_distance_median for run in runs))
    normalized_prominence_ratio = _ratio(
        tuple(_primary_rolling(run).prominence_median for run in runs)
    )
    normalized_distance_ratio = _ratio(
        tuple(_primary_rolling(run).distance_median for run in runs)
    )
    combined_rates = tuple(run.combined_reference_pass_rate for run in runs)
    combined_pass_spread_pp = (max(combined_rates) - min(combined_rates)) * 100.0

    normalization_improves_prominence = (
        normalized_prominence_ratio < raw_prominence_ratio
    )
    normalization_improves_distance = normalized_distance_ratio < raw_distance_ratio
    normalization_improves_both = (
        normalization_improves_prominence and normalization_improves_distance
    )
    raw_combined_selectivity_profile_stable = combined_pass_spread_pp < 2.0

    assert len(data_set.events) == 224125
    assert len(events) == 14941
    assert aggregator.dropped_incomplete_buckets >= 0
    assert tuple(run.crosses for run in runs) == (1154, 1864, 2443)
    assert tuple(run.extremum_found for run in runs) == (889, 1724, 2372)
    assert tuple(run.extremum_not_found for run in runs) == (265, 140, 71)
    assert raw_combined_selectivity_profile_stable
    assert not normalization_improves_both
    assert normalized_prominence_ratio > raw_prominence_ratio
    assert normalized_distance_ratio > raw_distance_ratio

    print("Algorithm Workspace MACD Quality Scale Normalization result")
    print(f"  source_rows={len(data_set.events)}")
    print(f"  completed_m15_bars={len(events)}")
    print("  source_timeframe=M1")
    print("  strategy_timeframe=M15")
    print("  controlled_parameter=MACD_PERIOD_PROFILE")
    print(f"  reference_prominence={REFERENCE_PROMINENCE:.6f}")
    print(f"  reference_distance={REFERENCE_DISTANCE:.6f}")
    print("  parameter_model=ADMISSIBLE_RANGE_NOT_UNIVERSAL_CONSTANT")
    print("  profile_variants:")
    for run in runs:
        _print_run(run)
    print(
        "  cross_profile_median_ratio raw_prominence/normalized64="
        f"{raw_prominence_ratio:.3f}/{normalized_prominence_ratio:.3f}"
    )
    print(
        "  cross_profile_median_ratio raw_distance/normalized64="
        f"{raw_distance_ratio:.3f}/{normalized_distance_ratio:.3f}"
    )
    print(
        "  combined_reference_pass_spread="
        f"{combined_pass_spread_pp:.2f} percentage_points"
    )
    print(
        "  raw_combined_selectivity_profile_stable="
        f"{raw_combined_selectivity_profile_stable}"
    )
    print(
        "  naive_histogram_normalization_improves_profile_stability="
        f"{normalization_improves_both}"
    )
    print("  production_normalization_applied=False")
    print("  production_quality_thresholds_changed=False")
    print("  abc_angle_changed=False")
    print("  alligator_changed=False")
    print("  future_observations_used=False")
    print("  deterministic=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_MACD_QUALITY_SCALE_NORMALIZATION_CHECK=OK")


if __name__ == "__main__":
    main()
