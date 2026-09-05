"""run_t108_08_macd_weak_reject_residual_segment_move_anatomy_check.py

T108-08 є TEST_ONLY anatomy фактичних ``MACD_EXTREMUM_TOO_WEAK`` reject
events усередині missed STRONG production Alligator segments. Canonical
Candidate F Replay ідентичний T105-18; T108-06 segment definition та factual
trade coverage не змінюються.

Для кожного causal reject на completed M15 bar runner бере close цього bar як
reference price, виключає вже завершений signal bar і вимірює maximum favorable
movement лише на наступних completed bars до кінця того самого ACTIVE segment.
Рух нормалізується canonical geometry ``R = max(signal_bar_range, spread*10)``.
Post-reject ``2R`` є тільки outcome label, а не альтернативним entry або
симуляцією trade: SL, fill, execution і exit path не моделюються.

Звіт показує timing reject-а, remaining bars/move та кількість segments із хоча
б одним factual residual-2R label. Threshold sweep, optimization, production
parameter changes, broker requests і look-ahead у classification відсутні.
"""

from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
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
    TrendSegment,
)
from run_t108_07_macd_weak_prominence_missed_strong_segments_anatomy_check import (  # noqa: E402, E501
    _diagnostics_in_segments,
    _missed_strong_segments,
)

from core.workspace_algorithm import create_registered_workspace_algorithm  # noqa: E402, E501
from core.workspace_alligator import (  # noqa: E402
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_macd_crossover_quality import (  # noqa: E402
    MACD_QUALITY_REASON_EXTREMUM_TOO_WEAK,
    WorkspaceMacdCrossoverQualityDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402

TEST_ID = "T108-08"
MODE = "RM108_T108_08_MACD_WEAK_REJECT_RESIDUAL_SEGMENT_MOVE_TEST_ONLY"
RESIDUAL_MOVE_LABEL_R = 2.0


@dataclass(frozen=True, slots=True)
class ResidualMoveRow:
    """Один causal weak reject та його окремий post-hoc residual label."""

    segment_start: datetime
    signal_timestamp: datetime
    direction: str
    segment_bar_number: int
    remaining_completed_bars: int
    prominence_ratio: float
    residual_move_r: float

    @property
    def reached_residual_label(self) -> bool:
        """Чи досяг factual future move незмінної позначки 2R."""

        return self.residual_move_r + 1e-12 >= RESIDUAL_MOVE_LABEL_R


@dataclass(frozen=True, slots=True)
class PeriodResult:
    """Baseline, segment population, residual rows і broker safety періоду."""

    baseline: str
    missed_strong_segments: tuple[TrendSegment, ...]
    rows: tuple[ResidualMoveRow, ...]
    broker_requests: int


def _residual_move_r(
    segment: TrendSegment,
    diagnostic: WorkspaceMacdCrossoverQualityDiagnostic,
    events: dict[datetime, WorkspaceMarketEvent],
) -> tuple[int, int, float]:
    """Виміряти future-only favorable move після completed rejected bar."""

    timestamps = tuple(item.timestamp for item in segment.observations)
    signal_index = timestamps.index(diagnostic.timestamp)
    signal_event = events[diagnostic.timestamp]
    stop_distance = max(
        signal_event.high - signal_event.low,
        signal_event.spread * 10.0,
    )
    assert stop_distance > 0.0

    future_timestamps = timestamps[signal_index + 1:]
    future_events = tuple(events[timestamp] for timestamp in future_timestamps)
    if not future_events:
        favorable = 0.0
    elif segment.side == "BUY":
        favorable = (
            max(item.high for item in future_events) - signal_event.close
        )
    else:
        favorable = (
            signal_event.close - min(item.low for item in future_events)
        )
    move_r = max(favorable, 0.0) / stop_distance
    return signal_index + 1, len(future_events), move_r


def _rows(
    segments: tuple[TrendSegment, ...],
    diagnostics: tuple[WorkspaceMacdCrossoverQualityDiagnostic, ...],
    events: dict[datetime, WorkspaceMarketEvent],
    minimum_prominence: float,
) -> tuple[ResidualMoveRow, ...]:
    """Побудувати factual rows без зміни або застосування нового guard."""

    result: list[ResidualMoveRow] = []
    for segment in segments:
        segment_diagnostics = _diagnostics_in_segments(
            diagnostics,
            (segment,),
        )
        for diagnostic in segment_diagnostics:
            prominence = diagnostic.extremum_prominence
            assert prominence is not None
            bar_number, remaining_bars, move_r = _residual_move_r(
                segment,
                diagnostic,
                events,
            )
            result.append(
                ResidualMoveRow(
                    segment_start=segment.start_timestamp,
                    signal_timestamp=diagnostic.timestamp,
                    direction=diagnostic.direction,
                    segment_bar_number=bar_number,
                    remaining_completed_bars=remaining_bars,
                    prominence_ratio=prominence / minimum_prominence,
                    residual_move_r=move_r,
                )
            )
    return tuple(result)


def _run_period(spec) -> PeriodResult:
    """Запустити canonical Replay і побудувати post-reject outcome labels."""

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
    assert session.completed
    assert broker_probe.requests == 0
    assert not _broker_execution_attempted(runtime)

    algorithm = runtime.algorithm
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    source = algorithm.source
    assert source is not None
    weak_diagnostics = tuple(
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
        (item.timestamp, item.direction) for item in weak_diagnostics
    )
    record_keys = Counter(
        (item.timestamp, item.direction) for item in rejected_records
    )
    assert diagnostic_keys == record_keys

    missed_segments = _missed_strong_segments(runtime, algorithm)
    segment_diagnostics = _diagnostics_in_segments(
        weak_diagnostics,
        missed_segments,
    )
    rows = _rows(
        missed_segments,
        segment_diagnostics,
        runtime.strategy_events,
        source.extremum_min_prominence,
    )
    assert rows
    assert len(rows) == len(segment_diagnostics)
    assert all(row.segment_bar_number >= 1 for row in rows)
    assert all(row.remaining_completed_bars >= 0 for row in rows)
    return PeriodResult(
        baseline=_summary_line(runtime),
        missed_strong_segments=missed_segments,
        rows=rows,
        broker_requests=broker_probe.requests,
    )


def _print_period(period: str, result: PeriodResult) -> None:
    """Надрукувати timing та residual-move anatomy одного періоду."""

    rows = result.rows
    reached = tuple(row for row in rows if row.reached_residual_label)
    reached_segments = {
        (row.segment_start, row.direction)
        for row in reached
    }
    segment_coverage = (
        100.0
        * len(reached_segments)
        / len(result.missed_strong_segments)
    )
    event_rate = 100.0 * len(reached) / len(rows)

    print(f"period={period}")
    print(f"  production_baseline={result.baseline}")
    print(f"  missed_strong_segments={len(result.missed_strong_segments)}")
    print(f"  weak_reject_events_in_missed_strong_segments={len(rows)}")
    bar_number_median = median(row.segment_bar_number for row in rows)
    remaining_bars_median = median(
        row.remaining_completed_bars for row in rows
    )
    residual_move_median = median(row.residual_move_r for row in rows)
    residual_move_max = max(row.residual_move_r for row in rows)
    print(f"  weak_reject_segment_bar_number_median={bar_number_median:.2f}")
    print(f"  remaining_completed_bars_median={remaining_bars_median:.2f}")
    print(f"  residual_move_r_median={residual_move_median:.4f}")
    print(f"  residual_move_r_max={residual_move_max:.4f}")
    print(f"  residual_2r_events={len(reached)}")
    print(f"  residual_2r_event_rate_percent={event_rate:.2f}")
    print(f"  missed_strong_segments_with_residual_2r={len(reached_segments)}")
    print(
        "  missed_strong_segment_residual_2r_coverage_percent="
        f"{segment_coverage:.2f}"
    )
    print("  RESIDUAL_2R_ROWS")
    for row in reached:
        print(
            f"    {row.segment_start.isoformat()}|"
            f"{row.signal_timestamp.isoformat()}|{row.direction}|"
            f"segment_bar={row.segment_bar_number}|"
            f"remaining_bars={row.remaining_completed_bars}|"
            f"prominence_ratio={row.prominence_ratio:.6f}|"
            f"residual_move_r={row.residual_move_r:.4f}"
        )


def main() -> None:
    """Виконати T108-08 та підтвердити незмінність production/safety."""

    production_before = _production_hashes()
    for spec in PERIODS:
        result = _run_period(spec)
        assert result.broker_requests == 0
        _print_period(spec.code, result)
    assert _production_hashes() == production_before

    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print("population=WEAK_REJECT_EVENTS_IN_MISSED_STRONG_SEGMENTS")
    print("signal_bar_in_future_window=False")
    print("residual_reference_price=REJECTED_COMPLETED_BAR_CLOSE")
    print("residual_horizon=NEXT_COMPLETED_BAR_TO_SAME_ACTIVE_SEGMENT_END")
    print("residual_r_geometry=max(rejected_bar_range,spread*10)")
    print(f"residual_label_threshold_r={RESIDUAL_MOVE_LABEL_R:.1f}")
    print("future_movement_role=OUTCOME_LABEL_ONLY")
    print("production_threshold_changed=False")
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
    print("T108_08_MACD_WEAK_REJECT_RESIDUAL_SEGMENT_MOVE_ANATOMY=OK")


if __name__ == "__main__":
    main()
