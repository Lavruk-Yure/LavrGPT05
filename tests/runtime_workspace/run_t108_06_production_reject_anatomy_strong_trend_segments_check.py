"""run_t108_06_production_reject_anatomy_strong_trend_segments_check.py — T108-06.

TEST_ONLY factual anatomy вимірює coverage чинного production entry на
production-defined ACTIVE Alligator trend segments. Segment формується лише з
послідовних completed M15 observations одного directional ACTIVE state.

Strong label НЕ є новим entry rule: після завершення Replay segment позначається
STRONG, якщо його maximum favorable excursion від close першого ACTIVE bar
досягає canonical production TP distance 2R, де R = max(signal-bar range,
spread * 10). Майбутні bars використовуються тільки для outcome label і ніколи
не впливають на production Replay або стан умов на досліджуваному bar.

Для STRONG segment runner окремо рахує factual production trades і missed
segments. Для кожного completed bar missed segment фіксується фактичний
production signal/reject state: відсутність production MACD proposal,
конкретний filter_reason_code rejected proposal або accepted signal без factual
trade. Threshold sweep, optimization, alternative entry/exit і production
зміни відсутні.
"""

from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
TEMP_ROOT = PROJECT_ROOT / "tests" / "runtime_temp"
for import_path in (PROJECT_ROOT, TEST_ROOT, TEMP_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from run_algorithm_workspace_replay_virtual_execution_check import (  # noqa: E402
    BrokerRequestProbe,
)
from run_t105_10_pd_35_production_regression_check import _workspace  # noqa: E402
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

from core.workspace_algorithm import create_registered_workspace_algorithm  # noqa: E402
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    ALLIGATOR_STATE_BEARISH,
    ALLIGATOR_STATE_BULLISH,
    WorkspaceAlligatorObservation,
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402

TEST_ID = "T108-06"
MODE = "RM108_T108_06_PRODUCTION_REJECT_ANATOMY_STRONG_TREND_SEGMENTS_TEST_ONLY"
STRONG_MOVE_R = 2.0
NO_PRODUCTION_MACD_PROPOSAL = "NO_PRODUCTION_MACD_PROPOSAL"
ACCEPTED_SIGNAL_NO_FACTUAL_TRADE = "ACCEPTED_SIGNAL_NO_FACTUAL_TRADE"


@dataclass(frozen=True, slots=True)
class TrendSegment:
    """Один contiguous production ACTIVE directional Alligator segment."""

    side: str
    observations: tuple[WorkspaceAlligatorObservation, ...]

    @property
    def start_timestamp(self) -> datetime:
        return self.observations[0].timestamp

    @property
    def end_timestamp(self) -> datetime:
        return self.observations[-1].timestamp


@dataclass(frozen=True, slots=True)
class StrongSegmentRow:
    """Factual coverage/reject anatomy одного STRONG trend segment."""

    period: str
    segment: TrendSegment
    move_r: float
    production_trade_count: int
    accepted_signal_count: int
    reject_counts: tuple[tuple[str, int], ...]

    @property
    def missed(self) -> bool:
        return self.production_trade_count == 0


def _observation_side(observation: WorkspaceAlligatorObservation) -> str | None:
    """Повернути production directional side лише для ACTIVE aligned state."""

    if observation.regime_phase != ALLIGATOR_REGIME_PHASE_ACTIVE:
        return None
    if (
        observation.regime == ALLIGATOR_REGIME_TREND_UP
        and observation.state == ALLIGATOR_STATE_BULLISH
    ):
        return "BUY"
    if (
        observation.regime == ALLIGATOR_REGIME_TREND_DOWN
        and observation.state == ALLIGATOR_STATE_BEARISH
    ):
        return "SELL"
    return None


def _segments(
    observations: tuple[WorkspaceAlligatorObservation, ...],
) -> tuple[TrendSegment, ...]:
    """Зібрати contiguous ACTIVE segments без future-dependent selection."""

    result: list[TrendSegment] = []
    current_side: str | None = None
    current: list[WorkspaceAlligatorObservation] = []
    for observation in observations:
        side = _observation_side(observation)
        if side is not None and side == current_side:
            current.append(observation)
            continue
        if current_side is not None and current:
            result.append(TrendSegment(current_side, tuple(current)))
        current_side = side
        current = [observation] if side is not None else []
    if current_side is not None and current:
        result.append(TrendSegment(current_side, tuple(current)))
    return tuple(result)


def _strong_move_r(
    segment: TrendSegment,
    events: dict[datetime, WorkspaceMarketEvent],
) -> float:
    """Порахувати post-hoc MFE label segment у canonical production R geometry."""

    first = events[segment.start_timestamp]
    stop_distance = max(first.high - first.low, first.spread * 10.0)
    assert stop_distance > 0.0
    segment_events = tuple(events[item.timestamp] for item in segment.observations)
    if segment.side == "BUY":
        favorable = max(item.high for item in segment_events) - first.close
    else:
        favorable = first.close - min(item.low for item in segment_events)
    return max(favorable, 0.0) / stop_distance


def _records_by_bar(
    records: tuple[WorkspaceSignalRecord, ...],
) -> dict[tuple[datetime, str], tuple[WorkspaceSignalRecord, ...]]:
    grouped: dict[tuple[datetime, str], list[WorkspaceSignalRecord]] = {}
    for record in records:
        key = (record.timestamp, record.direction)
        grouped.setdefault(key, []).append(record)
    return {key: tuple(value) for key, value in grouped.items()}


def _segment_reject_counts(
    segment: TrendSegment,
    records: dict[tuple[datetime, str], tuple[WorkspaceSignalRecord, ...]],
    trade_signal_uids: set[str],
) -> tuple[int, Counter[str]]:
    """Зафіксувати actual production signal/reject state кожного segment bar."""

    accepted_count = 0
    proposal_count = 0
    reasons: Counter[str] = Counter()
    for observation in segment.observations:
        bar_records = records.get((observation.timestamp, segment.side), ())
        proposal_count += len(bar_records)
        accepted = tuple(record for record in bar_records if record.accepted)
        rejected = tuple(record for record in bar_records if not record.accepted)
        accepted_count += len(accepted)
        for record in rejected:
            assert record.filter_reason_code is not None
            reasons[record.filter_reason_code] += 1
        for record in accepted:
            if record.signal_uid not in trade_signal_uids:
                reasons[ACCEPTED_SIGNAL_NO_FACTUAL_TRADE] += 1
    if proposal_count == 0:
        reasons[NO_PRODUCTION_MACD_PROPOSAL] += 1
    return accepted_count, reasons


def _run_period(spec) -> tuple[tuple[StrongSegmentRow, ...], str, int]:
    """Запустити незмінений production Replay і побудувати post-hoc anatomy."""

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
    signal_filter = algorithm.signal_filter
    assert signal_filter is not None
    observations = tuple(signal_filter.observations)
    events = runtime.strategy_events
    records = _records_by_bar(runtime.historical_signal_records)
    execution = runtime.replay_execution
    assert execution is not None
    trades = execution.trade_diagnostics()
    trade_signal_uids = {trade.signal_uid for trade in trades}
    trades_by_segment_key = Counter(
        (trade.signal_timestamp, trade.direction) for trade in trades
    )

    rows: list[StrongSegmentRow] = []
    for segment in _segments(observations):
        assert all(item.timestamp in events for item in segment.observations)
        move_r = _strong_move_r(segment, events)
        if move_r + 1e-12 < STRONG_MOVE_R:
            continue
        timestamps = {item.timestamp for item in segment.observations}
        production_trade_count = sum(
            count
            for (timestamp, side), count in trades_by_segment_key.items()
            if side == segment.side and timestamp in timestamps
        )
        accepted_count, reject_counts = _segment_reject_counts(
            segment,
            records,
            trade_signal_uids,
        )
        rows.append(
            StrongSegmentRow(
                period=spec.code,
                segment=segment,
                move_r=move_r,
                production_trade_count=production_trade_count,
                accepted_signal_count=accepted_count,
                reject_counts=tuple(sorted(reject_counts.items())),
            )
        )
    return tuple(rows), _summary_line(runtime), broker_probe.requests


def _print_period(
    period: str, rows: tuple[StrongSegmentRow, ...], baseline: str
) -> None:
    """Надрукувати compact factual coverage і bottleneck counts одного періоду."""

    captured = tuple(row for row in rows if not row.missed)
    missed = tuple(row for row in rows if row.missed)
    missed_reasons: Counter[str] = Counter()
    for row in missed:
        missed_reasons.update(dict(row.reject_counts))

    print(f"period={period}")
    print(f"  production_baseline={baseline}")
    print(f"  strong_trend_segments={len(rows)}")
    print(f"  segments_with_production_trade={len(captured)}")
    print(f"  missed_strong_trend_segments={len(missed)}")
    coverage = 0.0 if not rows else 100.0 * len(captured) / len(rows)
    print(f"  strong_segment_trade_coverage_percent={coverage:.2f}")
    print(f"  missed_segment_reject_events={sum(missed_reasons.values())}")
    for reason, count in missed_reasons.most_common():
        print(f"  missed_reject_reason|{reason}|count={count}")
    print("  MISSED_STRONG_SEGMENT_ROWS")
    for row in missed:
        reasons = ",".join(f"{reason}:{count}" for reason, count in row.reject_counts)
        print(
            f"    {row.segment.start_timestamp.isoformat()}|"
            f"{row.segment.end_timestamp.isoformat()}|{row.segment.side}|"
            f"bars={len(row.segment.observations)}|move_r={row.move_r:.4f}|"
            f"accepted_signals={row.accepted_signal_count}|rejects={reasons}"
        )


def main() -> None:
    """Запустити T108-06 без створення alternative entry architecture."""

    production_before = _production_hashes()
    results = {}
    for spec in PERIODS:
        rows, baseline, broker_requests = _run_period(spec)
        assert broker_requests == 0
        results[spec.code] = rows
        _print_period(spec.code, rows, baseline)
    assert _production_hashes() == production_before

    combined_missed_reasons: Counter[str] = Counter()
    for rows in results.values():
        for row in rows:
            if row.missed:
                combined_missed_reasons.update(dict(row.reject_counts))
    dominant = (
        combined_missed_reasons.most_common(1)[0][0]
        if combined_missed_reasons
        else "NONE"
    )

    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print(f"strong_label_threshold_r={STRONG_MOVE_R:.1f}")
    print("strong_label_reference=PRODUCTION_TP_DISTANCE_2R")
    print("strong_label_horizon=REMAINDER_OF_SAME_PRODUCTION_ACTIVE_SEGMENT")
    print("segment_definition=CONTIGUOUS_PRODUCTION_ACTIVE_ALLIGATOR_DIRECTION")
    print("segment_start_reference_price=FIRST_ACTIVE_BAR_CLOSE")
    print("r_geometry=max(first_active_bar_range,spread*10)")
    print(f"dominant_missed_reject_reason={dominant}")
    print("future_movement_role=OUTCOME_LABEL_ONLY")
    print("completed_bars_only=True")
    print("lookahead_used=False")
    print("threshold_sweep_performed=False")
    print("optimization_performed=False")
    print("new_entry_rule_created=False")
    print("multi_path_entry_created=False")
    print("alternative_exit_simulated=False")
    print("broker_requests=0")
    print("broker_execution_attempted=False")
    print("production_logic_changed=False")
    print("T108_06_PRODUCTION_REJECT_ANATOMY_STRONG_TREND_SEGMENTS=OK")


if __name__ == "__main__":
    main()
