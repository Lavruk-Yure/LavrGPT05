# run_algorithm_workspace_macd_abc_angle_profile_comparison_check.py — RoadMap99_04H
# -*- coding: utf-8 -*-
"""Порівняння ABC-кутів crossover для трьох швидкостей MACD у RoadMap99_04H.

Тест використовує один і той самий історичний EURUSD stream M1 -> completed
M15 за 2026-01-02..2026-08-11 і змінює тільки periods MACD: класичний
12/26/9, FAST 8/17/5 та VERY_FAST 6/13/4. Джерело Close, EMA для oscillator
і Signal, shift=0, часовий масштаб і вертикальний scale ABC-геометрії
залишаються незмінними.

Для кожного profile будуються всі classic crossover та їхній кут ``∠ACB``:
X — реальний UTC elapsed time у хвилинах, Y — indicator value * 10000 для
EURUSD, C — інтерпольована точка перетину MACD/Signal. Друкуються середнє,
медіана, P25/P50/P75/P90, фіксовані angle bins та окремі BUY/SELL середні й
медіани. Це дозволяє перевірити, наскільки ABC-angle переноситься між різними
MACD periods краще за абсолютні prominence/distance.

RoadMap99_04H залишається diagnostic-only: production angle, MACD Quality,
Alligator, NEXT_BAR_OPEN, risk і broker execution не змінюються. Отримані
градуси не оголошуються універсальним threshold; задача тесту — визначити
робочі діапазони та стабільність геометричної шкали між профілями без
look-ahead і без підгонки PnL.
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
from core.workspace_macd_cross_angle_abc import (  # noqa: E402
    WorkspaceMacdCrossAngleAbcConfig,
    build_workspace_macd_cross_angle_abc_report,
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


@dataclass(frozen=True, slots=True)
class MacdAbcProfileVariant:
    """Один MACD profile із незмінними Close/EMA/EMA/shift=0."""

    code: str
    fast_period: int
    slow_period: int
    signal_period: int


@dataclass(frozen=True, slots=True)
class MacdAbcProfileStatistics:
    """Порівнювані ABC-метрики одного profile на спільних M15 bars."""

    variant: MacdAbcProfileVariant
    crosses: int
    buy_crosses: int
    sell_crosses: int
    degenerate_crosses: int
    angle_average: float
    angle_median: float
    p25: float
    p50: float
    p75: float
    p90: float
    buy_average: float
    buy_median: float
    sell_average: float
    sell_median: float
    distribution: tuple[int, int, int, int, int, int, int, int]


VARIANTS = (
    MacdAbcProfileVariant("BASELINE", 12, 26, 9),
    MacdAbcProfileVariant("FAST", 8, 17, 5),
    MacdAbcProfileVariant("VERY_FAST", 6, 13, 4),
)


def load_m15_events():
    """Один раз завантажити M1 та створити спільний completed M15 stream."""
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
        source_name="IB_EURUSD_M1_RM99_ABC_PROFILE_COMPARISON",
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


def runtime_profile(
    variant: MacdAbcProfileVariant,
) -> WorkspaceMacdRuntimeProfile:
    """Побудувати isolated runtime profile без зміни profile catalog."""
    return WorkspaceMacdRuntimeProfile(
        profile_uid=(
            "RM99_ABC_PROFILE_"
            f"{variant.fast_period}_{variant.slow_period}_{variant.signal_period}"
        ),
        profile_revision=1,
        profile_name=(
            "RM99 ABC Profile "
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


def percentile(values: tuple[float, ...], percent: float) -> float:
    """Лінійно інтерполювати percentile на відсортованому finite наборі."""
    if not values:
        raise ValueError("percentile requires at least one value")
    if percent < 0.0 or percent > 100.0:
        raise ValueError("percent must be within 0..100")
    ordered = tuple(sorted(values))
    if len(ordered) == 1:
        return ordered[0]
    position = percent / 100.0 * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def angle_distribution(
    angles: tuple[float, ...],
) -> tuple[int, int, int, int, int, int, int, int]:
    """Порахувати однакові bins, використані в RoadMap99_04G regression."""
    return (
        sum(angle < 0.5 for angle in angles),
        sum(0.5 <= angle < 1.0 for angle in angles),
        sum(1.0 <= angle < 1.5 for angle in angles),
        sum(1.5 <= angle < 2.0 for angle in angles),
        sum(2.0 <= angle < 2.5 for angle in angles),
        sum(2.5 <= angle < 3.0 for angle in angles),
        sum(3.0 <= angle < 5.0 for angle in angles),
        sum(angle >= 5.0 for angle in angles),
    )


def run_variant(
    events,
    variant: MacdAbcProfileVariant,
    *,
    config: WorkspaceMacdCrossAngleAbcConfig,
) -> MacdAbcProfileStatistics:
    """Розрахувати всі classic crossover і ABC-статистику одного profile."""
    source = WorkspaceMacdSignalSource(
        enabled=True,
        mode="LINEAR",
        runtime_profile=runtime_profile(variant),
    )
    for event in events:
        source.on_market_event(event)
    report = build_workspace_macd_cross_angle_abc_report(
        source.observations,
        config=config,
    )
    repeated = build_workspace_macd_cross_angle_abc_report(
        source.observations,
        config=config,
    )
    assert report == repeated

    angles = tuple(
        item.angle_degrees
        for item in report.diagnostics
        if item.angle_degrees is not None
    )
    buy_angles = tuple(
        item.angle_degrees
        for item in report.diagnostics
        if item.direction == "BUY" and item.angle_degrees is not None
    )
    sell_angles = tuple(
        item.angle_degrees
        for item in report.diagnostics
        if item.direction == "SELL" and item.angle_degrees is not None
    )
    assert len(angles) == report.total_crosses
    assert len(buy_angles) == report.buy_crosses
    assert len(sell_angles) == report.sell_crosses

    return MacdAbcProfileStatistics(
        variant=variant,
        crosses=report.total_crosses,
        buy_crosses=report.buy_crosses,
        sell_crosses=report.sell_crosses,
        degenerate_crosses=report.degenerate_crosses,
        angle_average=statistics.mean(angles),
        angle_median=statistics.median(angles),
        p25=percentile(angles, 25.0),
        p50=percentile(angles, 50.0),
        p75=percentile(angles, 75.0),
        p90=percentile(angles, 90.0),
        buy_average=statistics.mean(buy_angles),
        buy_median=statistics.median(buy_angles),
        sell_average=statistics.mean(sell_angles),
        sell_median=statistics.median(sell_angles),
        distribution=angle_distribution(angles),
    )


def print_run(run: MacdAbcProfileStatistics) -> None:
    """Надрукувати повний профіль ABC-angle у компактному форматі."""
    distribution = run.distribution
    print(
        "  "
        f"{run.variant.code} "
        f"{run.variant.fast_period}/{run.variant.slow_period}/"
        f"{run.variant.signal_period}: crosses={run.crosses}, "
        f"BUY/SELL={run.buy_crosses}/{run.sell_crosses}, "
        f"avg/median={run.angle_average:.4f}/{run.angle_median:.4f}deg, "
        f"P25/P50/P75/P90={run.p25:.4f}/{run.p50:.4f}/"
        f"{run.p75:.4f}/{run.p90:.4f}deg, "
        f"BUY avg/med={run.buy_average:.4f}/{run.buy_median:.4f}, "
        f"SELL avg/med={run.sell_average:.4f}/{run.sell_median:.4f}",
        flush=True,
    )
    print(
        "    distribution="
        f"<0.5:{distribution[0]} 0.5-1:{distribution[1]} "
        f"1-1.5:{distribution[2]} 1.5-2:{distribution[3]} "
        f"2-2.5:{distribution[4]} 2.5-3:{distribution[5]} "
        f"3-5:{distribution[6]} >=5:{distribution[7]}",
        flush=True,
    )


def main() -> None:
    print(
        "Algorithm Workspace MACD ABC Angle Profile Comparison Check — "
        "RoadMap99_04H",
        flush=True,
    )
    print(
        "  Controlled variable: MACD EMA periods only. ABC geometry remains "
        "X=real UTC minutes, Y=indicator*10000 for EURUSD; production angle "
        "and trading logic stay unchanged.",
        flush=True,
    )
    print(
        "  Compare 12/26/9 -> 8/17/5 -> 6/13/4 as admissible ranges, not "
        "universal constants or PnL optimization.",
        flush=True,
    )
    if not M1_FILE.is_file():
        raise FileNotFoundError("Real EURUSD M1 history is required: " + str(M1_FILE))

    data_set, aggregator, events = load_m15_events()
    config = WorkspaceMacdCrossAngleAbcConfig(
        indicator_value_scale=EURUSD_VALUE_SCALE,
        time_unit_seconds=TIME_UNIT_SECONDS,
    )
    runs = []
    for index, variant in enumerate(VARIANTS, start=1):
        print(
            "MACD ABC Angle Profile Comparison: running "
            f"{index}/{len(VARIANTS)} profile="
            f"{variant.fast_period}/{variant.slow_period}/"
            f"{variant.signal_period} ...",
            flush=True,
        )
        runs.append(run_variant(events, variant, config=config))
    completed = tuple(runs)

    assert data_set.report.accepted_rows == 224125
    assert aggregator.completed_bars == 14941
    assert len(events) == 14941
    assert tuple(run.crosses for run in completed) == (1154, 1864, 2443)
    assert tuple(run.buy_crosses for run in completed) == (577, 932, 1221)
    assert tuple(run.sell_crosses for run in completed) == (577, 932, 1222)
    assert all(run.degenerate_crosses == 0 for run in completed)
    assert all(sum(run.distribution) == run.crosses for run in completed)

    repeated_fast = run_variant(events, VARIANTS[-1], config=config)
    assert repeated_fast == completed[-1]

    print("Algorithm Workspace MACD ABC Angle Profile Comparison result")
    print(f"  source_rows={data_set.report.accepted_rows}")
    print(f"  completed_m15_bars={aggregator.completed_bars}")
    print("  source_timeframe=M1")
    print("  strategy_timeframe=M15")
    print("  controlled_parameter=MACD_PERIOD_PROFILE")
    print("  abc_x_unit=REAL_UTC_MINUTE")
    print(f"  abc_y_scale_eurusd={EURUSD_VALUE_SCALE:.0f}")
    print("  abc_cross_point=LINEAR_INTERPOLATION")
    print("  parameter_model=ADMISSIBLE_RANGE_NOT_UNIVERSAL_CONSTANT")
    print("  profile_variants:")
    for run in completed:
        print_run(run)
    print("  same_m1_dataset=True")
    print("  same_m15_events=True")
    print("  source_close=True")
    print("  oscillator_ma_ema=True")
    print("  signal_ma_ema=True")
    print("  shift_zero=True")
    print("  abc_profile_threshold_selection_deferred=True")
    print("  prominence_distance_normalization_not_applied=True")
    print("  production_angle_logic_changed=False")
    print("  production_signal_logic_changed=False")
    print("  alligator_changed=False")
    print("  future_observations_used=False")
    print("  deterministic=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_MACD_ABC_ANGLE_PROFILE_COMPARISON_CHECK=OK")


if __name__ == "__main__":
    main()
