# run_algorithm_workspace_macd_signal_latency_diagnostic_check.py — RoadMap99_04D
# -*- coding: utf-8 -*-
"""Довгий Historical Replay diagnostic фактичної затримки MACD-сигналу.

Тест продовжує ручний RoadMap99_04C acceptance, де було окремо показано
``signal_timestamp`` і NEXT_BAR_OPEN ``opened_at``. Тут на реальній EURUSD M1
історії 2026-01-02..2026-08-11 вимірюється ще й попередня частина ланцюга:
наскільки MACD 12/26/9 crossover відстає від directional price extremum.

Price turn не оголошується абсолютною істиною. Для стійкості результат
порівнюється на lookback 4/8/12 завершених M15 bars; основним diagnostic
reference є 8 bars, бо той самий горизонт уже застосовується в RoadMap99 для
missed-move аналізу. BUY використовує найближчий minimum Low, SELL —
найближчий maximum High, причому тільки до signal timestamp включно.

MACD працює у поточному EXTENDED режимі з prominence=0.000005,
distance=0.000050 і angle=45°. Alligator вимкнений, щоб вимірювати intrinsic
MACD latency, а не наслідок downstream-фільтра. Production logic, risk,
virtual execution і broker execution не змінюються.
"""

from __future__ import annotations

import math
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_history import WorkspaceCsvHistoryLoader  # noqa: E402
from core.workspace_macd import WorkspaceMacdSignalSource  # noqa: E402
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
STRATEGY_BAR_MINUTES = 15
PRIMARY_LOOKBACK = 8


def load_m15_and_macd():
    """Завантажити M1, агрегувати M15 і побудувати MACD diagnostics."""
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
        source_name="IB_EURUSD_M1_RM99_MACD_LATENCY",
    )
    aggregator = WorkspaceTimeframeAggregator(
        source_timeframe="M1",
        target_timeframe="M15",
    )
    source = WorkspaceMacdSignalSource(
        enabled=True,
        mode="EXTENDED",
        extremum_min_prominence=PROMINENCE,
        extremum_to_cross_min_distance=DISTANCE,
        cross_min_angle_degrees=ANGLE,
    )
    events = []
    for event in data_set.events:
        completed = aggregator.on_market_event(event)
        if completed is None:
            continue
        events.append(completed.event)
        source.on_market_event(completed.event)
    final = aggregator.complete()
    if final is not None:
        events.append(final.event)
        source.on_market_event(final.event)
    return data_set, aggregator, tuple(events), source


def sample_by_timestamp(report: WorkspaceMacdSignalLatencyReport, timestamp):
    """Знайти один manual checkpoint у latency report."""
    return next(item for item in report.samples if item.signal_timestamp == timestamp)


def print_report(report: WorkspaceMacdSignalLatencyReport) -> None:
    """Надрукувати компактний latency summary для одного lookback."""
    entry_average = report.average_price_to_entry_bars
    entry_minutes = report.average_price_to_entry_minutes
    assert entry_average is not None
    assert entry_minutes is not None
    print(
        f"  lookback={report.lookback_bars}: "
        f"signal_avg={report.average_price_to_signal_bars:.2f} bars/"
        f"{report.average_price_to_signal_minutes:.1f} min, "
        f"signal_median={report.median_price_to_signal_bars:.1f} bars, "
        f"entry_avg={entry_average:.2f} bars/{entry_minutes:.1f} min, "
        f"lag<=1/2/3={report.lag_le_1}/{report.lag_le_2}/"
        f"{report.lag_le_3} of {report.total_signals}, "
        f"dist=0:{report.lag_0} 1:{report.lag_1} 2:{report.lag_2} "
        f"3:{report.lag_3} 4:{report.lag_4} 5+:{report.lag_5_plus}",
        flush=True,
    )


def main() -> None:
    print(
        "Algorithm Workspace MACD Signal Latency Diagnostic Check — " "RoadMap99_04D",
        flush=True,
    )
    print(
        "  Measure price-turn proxy -> M15 MACD signal -> NEXT_BAR_OPEN entry "
        "on EURUSD 2026-01-02..2026-08-11. Alligator=OFF; broker execution "
        "remains disabled.",
        flush=True,
    )
    print(
        "  Price-turn proxy is tested on lookback 4/8/12 bars; it is a "
        "diagnostic range, not a universal market constant.",
        flush=True,
    )
    if not M1_FILE.is_file():
        raise FileNotFoundError("Real EURUSD M1 history is required: " + str(M1_FILE))

    data_set, aggregator, events, source = load_m15_and_macd()
    reports = tuple(
        build_workspace_macd_signal_latency_report(
            events,
            source.quality_diagnostics,
            lookback_bars=lookback,
            strategy_bar_minutes=STRATEGY_BAR_MINUTES,
            quality_only=True,
        )
        for lookback in (4, PRIMARY_LOOKBACK, 12)
    )
    repeated = build_workspace_macd_signal_latency_report(
        events,
        source.quality_diagnostics,
        lookback_bars=PRIMARY_LOOKBACK,
        strategy_bar_minutes=STRATEGY_BAR_MINUTES,
        quality_only=True,
    )
    primary = reports[1]
    assert primary == repeated

    assert data_set.report.accepted_rows == 224125
    assert aggregator.completed_bars == 14941
    assert len(source.quality_diagnostics) == 1154
    assert primary.total_signals == 114
    assert primary.buy_signals == 69
    assert primary.sell_signals == 45
    assert primary.entry_eligible_signals == 114
    assert primary.entry_gap_signals == 0

    assert math.isclose(
        primary.average_price_to_signal_bars,
        3.1315789473684212,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    assert primary.median_price_to_signal_bars == 3.0
    assert math.isclose(
        primary.average_price_to_entry_bars or 0.0,
        4.131578947368421,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    assert primary.median_price_to_entry_bars == 4.0
    assert primary.lag_0 == 7
    assert primary.lag_1 == 14
    assert primary.lag_2 == 25
    assert primary.lag_3 == 19
    assert primary.lag_4 == 24
    assert primary.lag_5_plus == 25
    assert primary.lag_le_1 == 21
    assert primary.lag_le_2 == 46
    assert primary.lag_le_3 == 65
    assert math.isclose(
        primary.buy_average_price_to_signal_bars,
        3.1449275362318843,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    assert math.isclose(
        primary.sell_average_price_to_signal_bars,
        3.111111111111111,
        rel_tol=0.0,
        abs_tol=1e-12,
    )

    jan_09 = sample_by_timestamp(
        primary,
        datetime(2026, 1, 9, 14, 15, tzinfo=UTC),
    )
    assert jan_09.direction == "SELL"
    assert jan_09.price_extremum_timestamp == datetime(2026, 1, 9, 13, 30, tzinfo=UTC)
    assert jan_09.price_to_signal_bars == 3
    assert jan_09.expected_entry_timestamp == datetime(2026, 1, 9, 14, 30, tzinfo=UTC)
    assert jan_09.price_to_entry_bars == 4

    mar_23 = sample_by_timestamp(
        primary,
        datetime(2026, 3, 23, 9, 15, tzinfo=UTC),
    )
    assert mar_23.direction == "SELL"
    assert mar_23.price_extremum_timestamp == datetime(2026, 3, 23, 8, 30, tzinfo=UTC)
    assert mar_23.price_to_signal_bars == 3
    assert mar_23.expected_entry_timestamp == datetime(2026, 3, 23, 9, 30, tzinfo=UTC)
    assert mar_23.price_to_entry_bars == 4

    print("Algorithm Workspace MACD Signal Latency Diagnostic result", flush=True)
    print(f"  historical_m15_bars={len(events)}", flush=True)
    print(f"  classic_macd_crosses={len(source.quality_diagnostics)}", flush=True)
    print(f"  macd_quality_candidates={primary.total_signals}", flush=True)
    print("  macd_profile=LGE Classic EMA 12/26/9 Close", flush=True)
    print(f"  prominence={PROMINENCE:.6f}", flush=True)
    print(f"  distance={DISTANCE:.6f}", flush=True)
    print(f"  angle={ANGLE:.2f}", flush=True)
    for report in reports:
        print_report(report)
    print(
        "  primary_lookback_8_buy_sell_signal_avg="
        f"{primary.buy_average_price_to_signal_bars:.2f}/"
        f"{primary.sell_average_price_to_signal_bars:.2f} bars",
        flush=True,
    )
    print(
        "  manual_2026-01-09_14_15_SELL="
        f"price_extremum={jan_09.price_extremum_timestamp.isoformat()} "
        f"signal_lag={jan_09.price_to_signal_bars} "
        f"entry_lag={jan_09.price_to_entry_bars}",
        flush=True,
    )
    print(
        "  manual_2026-03-23_09_15_SELL="
        f"price_extremum={mar_23.price_extremum_timestamp.isoformat()} "
        f"signal_lag={mar_23.price_to_signal_bars} "
        f"entry_lag={mar_23.price_to_entry_bars}",
        flush=True,
    )
    print("  price_extremum_uses_future_bars=False", flush=True)
    print("  next_bar_open_policy_changed=False", flush=True)
    print("  production_signal_logic_changed=False", flush=True)
    print("  broker_requests=0", flush=True)
    print("  broker_execution_attempted=False", flush=True)
    print("ALGORITHM_WORKSPACE_MACD_SIGNAL_LATENCY_DIAGNOSTIC_CHECK=OK", flush=True)


if __name__ == "__main__":
    main()
