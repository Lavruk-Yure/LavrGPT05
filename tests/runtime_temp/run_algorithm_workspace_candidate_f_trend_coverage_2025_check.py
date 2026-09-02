# -*- coding: utf-8 -*-
"""RoadMap102: price-only Trend Coverage Diagnostic Candidate F за OOS 2025.

Діагностика не шукає збиткові угоди і не використовує PnL для визначення
тренду. Спочатку лише за завершеними M15 OHLC виділяються сильні 8-годинні
directional windows. Потім на frozen price-only список накладаються MACD,
MACD Quality, Alligator, Candidate F і Replay trades.

Baseline detector v1 фіксується до аналізу торгового результату:
- 32 завершені M15 bars на trend window;
- scan step 4 bars;
- volatility reference 64 попередні M15 bars;
- net move >= 8 median true ranges reference-вікна;
- path efficiency >= 0.55;
- window із gap усередині не вважається безперервним трендом;
- серед overlapping candidates лишається strongest non-overlapping window.

Це post-event research diagnostic, не entry gate. Він може дивитися на весь
trend window після факту, але його metrics не потрапляють у production trade
logic. Candidate F thresholds, risk, execution і broker path не змінюються.
Performance assertions типу PnL > 0 відсутні.
"""

from __future__ import annotations

import importlib.util
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REASON_OPENING_COLLAPSE,
    ALLIGATOR_REASON_OVEREXTENDED,
    ALLIGATOR_REASON_VOLATILITY_SPIKE,
    ALLIGATOR_REASON_WEAK_OPENING,
    CANDIDATE_F_LIFECYCLE_CANCEL,
    CANDIDATE_F_LIFECYCLE_EXPIRE,
)
from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402

FROZEN_OOS_RUNNER = Path(__file__).with_name(
    "run_algorithm_workspace_candidate_f_frozen_oos_2025_check.py"
)

TREND_WINDOW_BARS = 32
TREND_SCAN_STEP_BARS = 4
TREND_VOLATILITY_REFERENCE_BARS = 64
TREND_MIN_NORMALIZED_MOVE = 8.0
TREND_MIN_PATH_EFFICIENCY = 0.55
EXPECTED_M15_DELTA = timedelta(minutes=15)

COVERAGE_TRADE_POSITIVE = "TRADE_POSITIVE"
COVERAGE_TRADE_NEGATIVE = "TRADE_NEGATIVE"
COVERAGE_TRADE_FLAT = "TRADE_FLAT"
COVERAGE_NO_MACD = "NO_MACD"
COVERAGE_MACD_QUALITY_REJECT = "MACD_QUALITY_REJECT"
COVERAGE_ALLIGATOR_REJECT = "ALLIGATOR_REJECT"
COVERAGE_ARMED_CANCEL_EXPIRE = "ARMED_CANCEL_EXPIRE"
COVERAGE_STRUCTURAL_REJECT = "STRUCTURAL_REJECT"

STRUCTURAL_REJECT_CODES = {
    ALLIGATOR_REASON_OPENING_COLLAPSE,
    ALLIGATOR_REASON_WEAK_OPENING,
    ALLIGATOR_REASON_VOLATILITY_SPIKE,
    ALLIGATOR_REASON_OVEREXTENDED,
}


@dataclass(frozen=True, slots=True)
class TrendWindow:
    """Один price-only strong directional M15 window."""

    start_index: int
    end_index: int
    direction: str
    normalized_move: float
    path_efficiency: float
    score: float
    net_move: float


@dataclass(frozen=True, slots=True)
class TrendCoverage:
    """Накладення Candidate F evidence на один price-only trend window."""

    window: TrendWindow
    coverage: str
    macd_signals: int
    macd_quality_pass: int
    aligned_trades: int
    aligned_net_profit: float
    opposite_trades: int
    opposite_net_profit: float
    primary_reason_codes: tuple[str, ...]


def load_frozen_oos_runner() -> ModuleType:
    """Завантажити frozen OOS runner як canonical workspace source."""
    assert FROZEN_OOS_RUNNER.is_file(), FROZEN_OOS_RUNNER
    spec = importlib.util.spec_from_file_location(
        "rm102_candidate_f_frozen_oos_2025",
        FROZEN_OOS_RUNNER,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _true_range_reference(events: tuple[WorkspaceMarketEvent, ...]) -> float:
    """Повернути median true range попереднього reference-вікна."""
    assert events
    previous_close = events[0].close
    true_ranges: list[float] = []
    for event in events:
        true_ranges.append(
            max(
                event.high - event.low,
                abs(event.high - previous_close),
                abs(event.low - previous_close),
            )
        )
        previous_close = event.close
    reference = statistics.median(true_ranges)
    assert reference > 0.0
    return float(reference)


def _window_is_contiguous(
    events: tuple[WorkspaceMarketEvent, ...],
    start_index: int,
    end_index: int,
) -> bool:
    """Не трактувати market gap як частину безперервного тренду."""
    return all(
        events[index].timestamp - events[index - 1].timestamp == EXPECTED_M15_DELTA
        for index in range(start_index + 1, end_index + 1)
    )


def price_only_trend_candidates(
    events: tuple[WorkspaceMarketEvent, ...],
) -> tuple[TrendWindow, ...]:
    """Знайти strong 8h windows лише з M15 OHLC без trade evidence."""
    first_end = TREND_VOLATILITY_REFERENCE_BARS + TREND_WINDOW_BARS - 1
    candidates: list[TrendWindow] = []

    for end_index in range(
        first_end,
        len(events),
        TREND_SCAN_STEP_BARS,
    ):
        start_index = end_index - TREND_WINDOW_BARS + 1
        if not _window_is_contiguous(events, start_index, end_index):
            continue

        reference_start = start_index - TREND_VOLATILITY_REFERENCE_BARS
        reference = _true_range_reference(events[reference_start:start_index])
        net_move = events[end_index].close - events[start_index].close
        absolute_move = abs(net_move)
        path = sum(
            abs(events[index].close - events[index - 1].close)
            for index in range(start_index + 1, end_index + 1)
        )
        if path <= 0.0:
            continue

        normalized_move = absolute_move / reference
        path_efficiency = absolute_move / path
        if normalized_move < TREND_MIN_NORMALIZED_MOVE:
            continue
        if path_efficiency < TREND_MIN_PATH_EFFICIENCY:
            continue

        candidates.append(
            TrendWindow(
                start_index=start_index,
                end_index=end_index,
                direction="BUY" if net_move > 0.0 else "SELL",
                normalized_move=normalized_move,
                path_efficiency=path_efficiency,
                score=normalized_move * path_efficiency,
                net_move=net_move,
            )
        )

    return tuple(candidates)


def strongest_non_overlapping(
    candidates: tuple[TrendWindow, ...],
) -> tuple[TrendWindow, ...]:
    """Прибрати overlap, залишивши strongest price-only window."""
    selected: list[TrendWindow] = []
    ranked = sorted(
        candidates,
        key=lambda item: (
            item.score,
            item.normalized_move,
            item.path_efficiency,
        ),
        reverse=True,
    )
    for candidate in ranked:
        overlaps = any(
            not (
                candidate.end_index < existing.start_index
                or candidate.start_index > existing.end_index
            )
            for existing in selected
        )
        if not overlaps:
            selected.append(candidate)

    return tuple(sorted(selected, key=lambda item: item.start_index))


def _aligned_records(
    records: tuple[WorkspaceSignalRecord, ...],
    start: datetime,
    end: datetime,
    direction: str,
) -> tuple[WorkspaceSignalRecord, ...]:
    return tuple(
        record
        for record in records
        if start <= record.timestamp <= end and record.direction == direction
    )


def _aligned_trades(
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    start: datetime,
    end: datetime,
    direction: str,
) -> tuple[WorkspaceHistoricalTradeDiagnostic, ...]:
    return tuple(
        trade
        for trade in trades
        if start <= trade.signal_timestamp <= end and trade.direction == direction
    )


def _opposite_trades(
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    start: datetime,
    end: datetime,
    direction: str,
) -> tuple[WorkspaceHistoricalTradeDiagnostic, ...]:
    return tuple(
        trade
        for trade in trades
        if start <= trade.signal_timestamp <= end and trade.direction != direction
    )


def coverage_for_window(
    window: TrendWindow,
    events: tuple[WorkspaceMarketEvent, ...],
    records: tuple[WorkspaceSignalRecord, ...],
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
) -> TrendCoverage:
    """Класифікувати coverage після price-only trend detection."""
    start = events[window.start_index].timestamp
    end = events[window.end_index].timestamp
    same_direction_records = _aligned_records(
        records,
        start,
        end,
        window.direction,
    )
    quality_pass = tuple(
        record
        for record in same_direction_records
        if record.source_reason_code == "MACD_CROSS_ACCEPTED"
    )
    aligned_trades = _aligned_trades(
        trades,
        start,
        end,
        window.direction,
    )
    opposite_trades = _opposite_trades(
        trades,
        start,
        end,
        window.direction,
    )
    aligned_net_profit = sum(trade.final_profit for trade in aligned_trades)
    opposite_net_profit = sum(trade.final_profit for trade in opposite_trades)

    if aligned_trades:
        if aligned_net_profit > 1e-12:
            coverage = COVERAGE_TRADE_POSITIVE
        elif aligned_net_profit < -1e-12:
            coverage = COVERAGE_TRADE_NEGATIVE
        else:
            coverage = COVERAGE_TRADE_FLAT
    elif not same_direction_records:
        coverage = COVERAGE_NO_MACD
    elif not quality_pass:
        coverage = COVERAGE_MACD_QUALITY_REJECT
    elif any(
        record.filter_reason_code in STRUCTURAL_REJECT_CODES for record in quality_pass
    ):
        coverage = COVERAGE_STRUCTURAL_REJECT
    elif any(
        record.candidate_f_lifecycle_action
        in {CANDIDATE_F_LIFECYCLE_CANCEL, CANDIDATE_F_LIFECYCLE_EXPIRE}
        for record in quality_pass
    ):
        coverage = COVERAGE_ARMED_CANCEL_EXPIRE
    else:
        coverage = COVERAGE_ALLIGATOR_REJECT

    reason_codes = tuple(
        sorted(
            {
                str(record.filter_reason_code or "").strip().upper()
                for record in quality_pass
                if str(record.filter_reason_code or "").strip()
            }
        )
    )
    return TrendCoverage(
        window=window,
        coverage=coverage,
        macd_signals=len(same_direction_records),
        macd_quality_pass=len(quality_pass),
        aligned_trades=len(aligned_trades),
        aligned_net_profit=aligned_net_profit,
        opposite_trades=len(opposite_trades),
        opposite_net_profit=opposite_net_profit,
        primary_reason_codes=reason_codes,
    )


def _coverage_count(
    items: tuple[TrendCoverage, ...],
    coverage_code: str,
) -> int:
    """Порахувати trend windows одного coverage-класу без generic Counter."""
    return sum(item.coverage == coverage_code for item in items)


def _format_window(
    item: TrendCoverage,
    events: tuple[WorkspaceMarketEvent, ...],
) -> str:
    window = item.window
    start = events[window.start_index].timestamp
    end = events[window.end_index].timestamp
    reasons = ",".join(item.primary_reason_codes) or "-"
    return (
        f"{start.isoformat()} -> {end.isoformat()} {window.direction} "
        f"move:{window.normalized_move:.2f}TR "
        f"eff:{window.path_efficiency:.3f} "
        f"coverage:{item.coverage} "
        f"macd:{item.macd_signals} quality:{item.macd_quality_pass} "
        f"trades:{item.aligned_trades} pnl:{item.aligned_net_profit:+.2f} "
        f"opposite:{item.opposite_trades}/{item.opposite_net_profit:+.2f} "
        f"reasons:{reasons}"
    )


def main() -> None:
    source = load_frozen_oos_runner()
    source.assert_frozen_oos_snapshot()

    runtime = source.FrozenOosRuntime(
        source.frozen_oos_workspace(),
        algorithm_factory=create_registered_workspace_algorithm,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    events = session.events
    assert events
    assert all(event.timeframe == "M15" for event in events)

    candidates = price_only_trend_candidates(events)
    strong_windows = strongest_non_overlapping(candidates)
    assert candidates
    assert strong_windows
    assert all(
        left.end_index < right.start_index
        for left, right in zip(strong_windows, strong_windows[1:])
    )

    while not session.completed:
        runtime.advance_replay()

    summary = runtime.historical_summary
    execution = runtime.replay_execution
    assert summary is not None
    assert execution is not None
    assert summary.period_start.year == 2025
    assert summary.period_end.year == 2025
    records = runtime.historical_signal_records_for_test()
    trades = execution.trade_diagnostics()

    coverage = tuple(
        coverage_for_window(window, events, records, trades)
        for window in strong_windows
    )
    positive_segments = _coverage_count(coverage, COVERAGE_TRADE_POSITIVE)
    negative_segments = _coverage_count(coverage, COVERAGE_TRADE_NEGATIVE)
    flat_segments = _coverage_count(coverage, COVERAGE_TRADE_FLAT)
    no_trade_segments = len(coverage) - (
        positive_segments + negative_segments + flat_segments
    )
    aligned_trade_count = sum(item.aligned_trades for item in coverage)
    aligned_net_profit = sum(item.aligned_net_profit for item in coverage)
    opposite_trade_count = sum(item.opposite_trades for item in coverage)
    opposite_net_profit = sum(item.opposite_net_profit for item in coverage)
    missed = tuple(
        sorted(
            (item for item in coverage if item.coverage != COVERAGE_TRADE_POSITIVE),
            key=lambda item: item.window.score,
            reverse=True,
        )
    )

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    print("Algorithm Workspace Candidate F Trend Coverage 2025 result")
    print("  detector=PRICE_ONLY_M15_STRONG_WINDOW_V1")
    print(f"  trend_window_bars={TREND_WINDOW_BARS}")
    print(f"  scan_step_bars={TREND_SCAN_STEP_BARS}")
    print("  volatility_reference_bars=" f"{TREND_VOLATILITY_REFERENCE_BARS}")
    print(
        "  minimum_trend="
        f"move:{TREND_MIN_NORMALIZED_MOVE:.1f}TR,"
        f"path_efficiency:{TREND_MIN_PATH_EFFICIENCY:.2f}"
    )
    print("  internal_gap_windows_rejected=True")
    print("  trend_detection_uses_signal_or_pnl=False")
    print(f"  price_only_candidates={len(candidates)}")
    print(f"  strong_non_overlapping_segments={len(strong_windows)}")
    print(
        "  segment_coverage="
        f"positive:{positive_segments},negative:{negative_segments},"
        f"flat:{flat_segments},no_trade:{no_trade_segments}"
    )
    print(
        "  no_trade_primary_blocker="
        f"no_macd:{_coverage_count(coverage, COVERAGE_NO_MACD)},"
        f"macd_quality:{_coverage_count(coverage, COVERAGE_MACD_QUALITY_REJECT)},"
        f"alligator:{_coverage_count(coverage, COVERAGE_ALLIGATOR_REJECT)},"
        "armed_cancel_expire:"
        f"{_coverage_count(coverage, COVERAGE_ARMED_CANCEL_EXPIRE)},"
        f"structural:{_coverage_count(coverage, COVERAGE_STRUCTURAL_REJECT)}"
    )
    print(
        "  aligned_trades="
        f"{aligned_trade_count},net_profit:{aligned_net_profit:+.2f}"
    )
    print(
        "  opposite_trades_inside_segments="
        f"{opposite_trade_count},net_profit:{opposite_net_profit:+.2f}"
    )
    print("  chronological_segments:")
    for index, item in enumerate(coverage, start=1):
        print(f"    {index:02d}. {_format_window(item, events)}")
    print("  priority_no_positive_segments:")
    for index, item in enumerate(missed[:10], start=1):
        print(f"    {index:02d}. {_format_window(item, events)}")
    print("  candidate_f_thresholds_changed=False")
    print("  research_diagnostic_only=True")
    print("  completed_bars_only=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_TREND_COVERAGE_2025_CHECK=OK")


if __name__ == "__main__":
    main()
