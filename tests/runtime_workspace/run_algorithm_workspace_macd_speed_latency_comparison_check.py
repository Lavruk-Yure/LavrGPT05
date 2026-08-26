# run_algorithm_workspace_macd_speed_latency_comparison_check.py — RoadMap99_04E
# -*- coding: utf-8 -*-
"""Порівняння latency кількох швидших EMA-профілів MACD на одному Replay.

RoadMap99_04D підтвердив, що базовий MACD 12/26/9 у середньому відстає від
price-turn proxy приблизно на три M15 bars, а NEXT_BAR_OPEN додає ще один bar
до фактичного входу. Цей тест змінює тільки periods MACD і перевіряє, чи можна
отримати раніший первинний crossover без зміни dataset, timeframe, source,
типів MA або execution policy.

Порівнюються 12/26/9, 10/22/7, 8/17/5 і 6/13/4. Це не кандидати на
універсальні «правильні» константи, а діагностичний діапазон швидкості для
EURUSD M15 на історії 2026-01-02..2026-08-11. Основною метрикою є latency усіх
classic crossovers на однаковому price-turn proxy lookback=8. Кількість
сигналів, BUY/SELL symmetry і розподіл lag також фіксуються.

Поточні MACD Quality thresholds 0.000005/0.000050/45° застосовуються лише як
другорядна довідкова метрика. Їх не можна напряму використовувати для вибору
MACD profile, бо зміна periods змінює числовий масштаб MACD/histogram і надалі
потребуватиме окремого калібрування допустимих діапазонів фільтрів.
Alligator вимкнений. Production signal logic, risk, NEXT_BAR_OPEN і broker
execution не змінюються.
"""

from __future__ import annotations

import math
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
from core.workspace_macd_signal_latency import (  # noqa: E402
    WorkspaceMacdSignalLatencyReport,
    build_workspace_macd_signal_latency_report,
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
PROMINENCE = 0.000005
DISTANCE = 0.000050
ANGLE = 45.0
LOOKBACK_BARS = 8
STRATEGY_BAR_MINUTES = 15


@dataclass(frozen=True, slots=True)
class MacdPeriodVariant:
    """Один діагностичний набір periods із незмінними EMA/Close/shift=0."""

    name: str
    fast_period: int
    slow_period: int
    signal_period: int


@dataclass(frozen=True, slots=True)
class MacdPeriodRun:
    """Повний результат одного profile на однакових M15 events."""

    variant: MacdPeriodVariant
    raw_report: WorkspaceMacdSignalLatencyReport
    quality_report: WorkspaceMacdSignalLatencyReport | None
    classic_crosses: int
    quality_pass: int
    quality_reject: int


VARIANTS = (
    MacdPeriodVariant("BASELINE", 12, 26, 9),
    MacdPeriodVariant("MODERATE", 10, 22, 7),
    MacdPeriodVariant("FAST", 8, 17, 5),
    MacdPeriodVariant("VERY_FAST", 6, 13, 4),
)


def load_m15_events():
    """Один раз завантажити M1 та агрегувати спільний набір M15 bars."""
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
        source_name="IB_EURUSD_M1_RM99_MACD_SPEED_LATENCY",
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


def runtime_profile(variant: MacdPeriodVariant) -> WorkspaceMacdRuntimeProfile:
    """Побудувати isolated runtime profile без запису в profile catalog."""
    return WorkspaceMacdRuntimeProfile(
        profile_uid=(
            "RM99_MACD_SPEED_"
            f"{variant.fast_period}_{variant.slow_period}_{variant.signal_period}"
        ),
        profile_revision=1,
        profile_name=(
            "RM99 MACD Speed "
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


def run_variant(events, variant: MacdPeriodVariant) -> MacdPeriodRun:
    """Обчислити classic latency та інформаційний Quality результат."""
    source = WorkspaceMacdSignalSource(
        enabled=True,
        mode="EXTENDED",
        runtime_profile=runtime_profile(variant),
        extremum_min_prominence=PROMINENCE,
        extremum_to_cross_min_distance=DISTANCE,
        cross_min_angle_degrees=ANGLE,
    )
    for event in events:
        source.on_market_event(event)

    diagnostics = source.quality_diagnostics
    raw_report = build_workspace_macd_signal_latency_report(
        events,
        diagnostics,
        lookback_bars=LOOKBACK_BARS,
        strategy_bar_minutes=STRATEGY_BAR_MINUTES,
        quality_only=False,
    )
    quality_pass = sum(item.final_quality_pass for item in diagnostics)
    quality_report = None
    if quality_pass:
        quality_report = build_workspace_macd_signal_latency_report(
            events,
            diagnostics,
            lookback_bars=LOOKBACK_BARS,
            strategy_bar_minutes=STRATEGY_BAR_MINUTES,
            quality_only=True,
        )
    return MacdPeriodRun(
        variant=variant,
        raw_report=raw_report,
        quality_report=quality_report,
        classic_crosses=len(diagnostics),
        quality_pass=quality_pass,
        quality_reject=len(diagnostics) - quality_pass,
    )


def print_run(run: MacdPeriodRun) -> None:
    """Надрукувати порівнювані метрики одного MACD profile."""
    report = run.raw_report
    quality_latency = (
        f"{run.quality_report.average_price_to_signal_bars:.2f}"
        if run.quality_report is not None
        else "N/A"
    )
    print(
        "  "
        f"{run.variant.name} "
        f"{run.variant.fast_period}/{run.variant.slow_period}/"
        f"{run.variant.signal_period}: "
        f"crosses={run.classic_crosses}, BUY/SELL="
        f"{report.buy_signals}/{report.sell_signals}, "
        f"raw_signal_avg={report.average_price_to_signal_bars:.2f}, "
        f"median={report.median_price_to_signal_bars:.1f}, "
        f"raw_entry_avg={report.average_price_to_entry_bars:.2f}, "
        f"entry_gaps={report.entry_gap_signals}, "
        f"lag<=1/2/3={report.lag_le_1}/{report.lag_le_2}/"
        f"{report.lag_le_3}, quality={run.quality_pass}/{run.quality_reject}, "
        f"quality_signal_avg={quality_latency}",
        flush=True,
    )


def main() -> None:
    print(
        "Algorithm Workspace MACD Speed/Latency Comparison Check — "
        "RoadMap99_04E",
        flush=True,
    )
    print(
        "  Controlled variable: MACD EMA periods only. Compare classic "
        "crossover latency for 12/26/9 -> 10/22/7 -> 8/17/5 -> 6/13/4; "
        "Alligator=OFF and broker execution remains disabled.",
        flush=True,
    )
    print(
        "  Quality counts are informational only because existing absolute "
        "thresholds are not normalized across different MACD periods.",
        flush=True,
    )
    if not M1_FILE.is_file():
        raise FileNotFoundError("Real EURUSD M1 history is required: " + str(M1_FILE))

    data_set, aggregator, events = load_m15_events()
    runs = []
    for index, variant in enumerate(VARIANTS, start=1):
        print(
            "MACD Speed/Latency: running "
            f"{index}/{len(VARIANTS)} profile="
            f"{variant.fast_period}/{variant.slow_period}/"
            f"{variant.signal_period} ...",
            flush=True,
        )
        runs.append(run_variant(events, variant))
    completed = tuple(runs)

    baseline = completed[0]
    assert data_set.report.accepted_rows == 224125
    assert aggregator.completed_bars == 14941
    assert baseline.classic_crosses == 1154
    assert baseline.quality_pass == 114
    assert baseline.quality_reject == 1040
    assert math.isclose(
        baseline.raw_report.average_price_to_signal_bars,
        3.8570190641247835,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    assert baseline.quality_report is not None
    assert math.isclose(
        baseline.quality_report.average_price_to_signal_bars,
        3.1315789473684212,
        rel_tol=0.0,
        abs_tol=1e-12,
    )

    assert all(run.raw_report.total_signals == run.classic_crosses for run in completed)
    assert all(
        run.raw_report.entry_eligible_signals + run.raw_report.entry_gap_signals
        == run.raw_report.total_signals
        for run in completed
    )
    assert all(run.raw_report.buy_signals > 0 for run in completed)
    assert all(run.raw_report.sell_signals > 0 for run in completed)

    raw_latencies = tuple(
        run.raw_report.average_price_to_signal_bars for run in completed
    )
    raw_crosses = tuple(run.classic_crosses for run in completed)
    assert all(
        left > right
        for left, right in zip(raw_latencies, raw_latencies[1:])
    )
    assert all(
        left < right for left, right in zip(raw_crosses, raw_crosses[1:])
    )

    repeated_fast = run_variant(events, VARIANTS[-1])
    assert repeated_fast == completed[-1]

    print("Algorithm Workspace MACD Speed/Latency Comparison result", flush=True)
    print(f"  historical_m15_bars={len(events)}", flush=True)
    print("  source_timeframe=M1", flush=True)
    print("  strategy_timeframe=M15", flush=True)
    print("  controlled_parameter=MACD_PERIOD_PROFILE", flush=True)
    print("  source=Close", flush=True)
    print("  oscillator_ma=EMA", flush=True)
    print("  signal_ma=EMA", flush=True)
    print("  shift=0", flush=True)
    print(f"  latency_lookback={LOOKBACK_BARS}", flush=True)
    print("  parameter_model=ADMISSIBLE_RANGE_NOT_UNIVERSAL_CONSTANT", flush=True)
    print("  profile_variants:", flush=True)
    for run in completed:
        print_run(run)
    print("  same_m1_dataset=True", flush=True)
    print("  same_m15_events=True", flush=True)
    print("  quality_thresholds_recalibration_required=True", flush=True)
    print("  alligator_changed=False", flush=True)
    print("  next_bar_open_policy_changed=False", flush=True)
    print("  production_signal_logic_changed=False", flush=True)
    print("  deterministic=True", flush=True)
    print("  broker_requests=0", flush=True)
    print("  broker_execution_attempted=False", flush=True)
    print("ALGORITHM_WORKSPACE_MACD_SPEED_LATENCY_COMPARISON_CHECK=OK", flush=True)


if __name__ == "__main__":
    main()
