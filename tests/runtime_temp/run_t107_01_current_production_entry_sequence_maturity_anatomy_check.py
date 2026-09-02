"""T107-01: factual anatomy production entry sequence та signal maturity.

TEST_ONLY runner повторює registered current-production Candidate F Replay 2025
і 2026. Для кожної factual trade він використовує лише causal
completed-M15
стани, доступні на signal bar: production Alligator observations/context,
production MACD observations і canonical production Stochastic 14/1/3 history.
Outcome додається після Replay лише як label.

Production не має окремого canonical Alligator "opening event" timestamp.
Тому runner не вигадує його: sequence використовує factual початок
поточного production-relevant ACTIVE Alligator state, відновлений з
production observation
history і context.active_age. Поле opening event друкується NOT_DEFINED.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime

from run_algorithm_workspace_replay_virtual_execution_check import BrokerRequestProbe
from run_t105_10_pd_35_production_regression_check import PeriodSpec, _workspace
from run_t105_15_stochastic_entry_anatomy_check import (
    OUTCOME_BREAK_EVEN,
    OUTCOME_LOSS,
    OUTCOME_WIN,
    StochasticEntryRow,
)
from run_t105_15_stochastic_entry_anatomy_check import (
    _build_rows as _build_stochastic_rows,
)
from run_t105_15_stochastic_entry_anatomy_check import (
    _production_hashes,
)
from run_t105_18_stochastic_current_bar_production_regression_check import (
    PERIODS,
    _assert_geometry,
    _assert_metrics,
    _assert_policy,
    _assert_stochastic_path,
    _broker_execution_attempted,
)
from run_t105_21_donchian_rejected_anatomy_check import RejectedSurvivorAnatomyRuntime
from run_t106_02_current_production_loss_anatomy_check import (
    _cross_alignment,
    _last_macd_cross,
)

from core.workspace_algorithm import create_registered_workspace_algorithm
from core.workspace_alligator import (
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    ALLIGATOR_STATE_BEARISH,
    ALLIGATOR_STATE_BULLISH,
    WorkspaceAlligatorObservation,
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_historical_trade_diagnostics import (
    WorkspaceHistoricalTradeDiagnostic,
)

TEST_ID = "T107-01"
MODE = "RM107_T107_01_CURRENT_PRODUCTION_ENTRY_SEQUENCE_MATURITY_ANATOMY_TEST_ONLY"
EPSILON = 1e-12
OUTCOMES = (OUTCOME_WIN, OUTCOME_LOSS, OUTCOME_BREAK_EVEN)
NUMERIC_FEATURES = (
    "bars_since_alligator_state_start",
    "bars_since_macd_cross",
    "bars_since_stochastic_cross",
    "max_component_age_bars",
    "min_component_age_bars",
    "age_spread_bars",
    "number_of_components_on_signal_bar",
)


@dataclass(frozen=True, slots=True)
class SequenceRow:
    """Causal chronology однієї factual current-production trade."""

    period: str
    trade: WorkspaceHistoricalTradeDiagnostic
    outcome: str
    alligator_state_start_timestamp: datetime
    bars_since_alligator_state_start: int
    alligator_state_changed_on_signal_bar: bool
    alligator_phase: str
    alligator_state: str
    alligator_direction_aligned: bool
    macd_cross_timestamp: datetime
    bars_since_macd_cross: int
    macd_cross_direction: str
    macd_aligned: bool
    macd_cross_on_signal_bar: bool
    stochastic_cross_timestamp: datetime
    bars_since_stochastic_cross: int
    stochastic_cross_direction: str
    stochastic_aligned: bool
    stochastic_cross_on_signal_bar: bool
    sequence_label: str
    oldest_component: str
    newest_component: str
    max_component_age_bars: int
    min_component_age_bars: int
    age_spread_bars: int
    number_of_components_on_signal_bar: int
    all_components_aligned_at_entry: bool


@dataclass(frozen=True, slots=True)
class FeatureStats:
    """Descriptive statistics одного maturity feature."""

    count: int
    mean: float
    median: float
    q1: float
    q3: float
    minimum: float
    maximum: float


def _outcome(trade: WorkspaceHistoricalTradeDiagnostic) -> str:
    if trade.final_profit > EPSILON:
        return OUTCOME_WIN
    if trade.final_profit < -EPSILON:
        return OUTCOME_LOSS
    return OUTCOME_BREAK_EVEN


def _alligator_matches_side(
    observation: WorkspaceAlligatorObservation,
    side: str,
) -> bool:
    if observation.regime_phase != ALLIGATOR_REGIME_PHASE_ACTIVE:
        return False
    if side == "BUY":
        return (
            observation.regime == ALLIGATOR_REGIME_TREND_UP
            and observation.state == ALLIGATOR_STATE_BULLISH
        )
    return (
        observation.regime == ALLIGATOR_REGIME_TREND_DOWN
        and observation.state == ALLIGATOR_STATE_BEARISH
    )


def _alligator_state_start(
    observations: tuple[WorkspaceAlligatorObservation, ...],
    signal_timestamp: datetime,
    side: str,
    active_age: int,
) -> tuple[datetime, int, bool, WorkspaceAlligatorObservation]:
    """Відновити початок current production-relevant ACTIVE state."""

    by_timestamp = {item.timestamp: index for index, item in enumerate(observations)}
    index = by_timestamp[signal_timestamp]
    current = observations[index]
    assert _alligator_matches_side(current, side)
    assert active_age >= 1
    start_index = index - active_age + 1
    assert start_index >= 0
    start = observations[start_index]
    assert _alligator_matches_side(start, side)
    assert all(
        _alligator_matches_side(item, side)
        for item in observations[start_index : index + 1]  # noqa
    )
    if start_index > 0:
        assert not _alligator_matches_side(observations[start_index - 1], side)
    return start.timestamp, index - start_index, start_index == index, current


def _sequence_label(events: dict[str, datetime]) -> str:
    """Побудувати canonical timestamp order без intrabar ordering."""

    grouped: dict[datetime, list[str]] = defaultdict(list)
    for name, timestamp in events.items():
        grouped[timestamp].append(name)
    parts: list[str] = []
    for timestamp in sorted(grouped):
        names = sorted(grouped[timestamp])
        if len(names) == 1:
            parts.append(names[0])
        else:
            parts.append(f"SAME_BAR({','.join(names)})")
    parts.append("ENTRY")
    return ">".join(parts)


def _component_extreme(ages: dict[str, int], *, oldest: bool) -> str:
    target = max(ages.values()) if oldest else min(ages.values())
    names = sorted(name for name, age in ages.items() if age == target)
    if len(names) == 1:
        return names[0]
    return f"SAME_BAR({','.join(names)})"


def _build_rows(
    runtime: RejectedSurvivorAnatomyRuntime,
    period: str,
) -> tuple[SequenceRow, ...]:
    """Зіставити factual trades з causal chronology production components."""

    algorithm = runtime.algorithm
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    source = algorithm.source
    signal_filter = algorithm.signal_filter
    assert source is not None and signal_filter is not None

    stochastic_rows = {
        row.trade.signal_uid: row for row in _build_stochastic_rows(runtime)
    }
    records = {
        record.signal_uid: record
        for record in runtime.historical_signal_records
        if record.accepted
    }
    assert stochastic_rows.keys() == records.keys()

    events = tuple(
        runtime.strategy_events[timestamp]
        for timestamp in sorted(runtime.strategy_events)
    )
    event_index = {event.timestamp: index for index, event in enumerate(events)}
    macd_observations = tuple(source.observations)
    macd_index = {item.timestamp: index for index, item in enumerate(macd_observations)}
    alligator_observations = tuple(signal_filter.observations)

    rows: list[SequenceRow] = []
    for signal_uid, stochastic in stochastic_rows.items():
        stochastic: StochasticEntryRow
        trade = stochastic.trade
        record = records[signal_uid]
        context = record.filter_context
        assert context is not None
        assert context.active_age is not None
        assert record.timestamp == trade.signal_timestamp

        (
            alligator_start,
            alligator_age,
            alligator_changed,
            alligator_current,
        ) = _alligator_state_start(
            alligator_observations,
            trade.signal_timestamp,
            trade.direction,
            context.active_age,
        )
        assert alligator_age == context.active_age - 1

        macd_position = macd_index[trade.signal_timestamp]
        macd_direction, macd_age = _last_macd_cross(macd_observations, macd_position)
        macd_cross_position = macd_position - macd_age
        macd_cross_timestamp = macd_observations[macd_cross_position].timestamp
        assert macd_cross_timestamp <= trade.signal_timestamp

        assert stochastic.bars_since_cross is not None
        stoch_age = stochastic.bars_since_cross
        assert stoch_age > 0
        signal_event_position = event_index[trade.signal_timestamp]
        stoch_cross_position = signal_event_position - stoch_age
        assert stoch_cross_position >= 0
        stoch_cross_timestamp = events[stoch_cross_position].timestamp
        assert stoch_cross_timestamp <= trade.signal_timestamp

        macd_aligned = _cross_alignment(trade.direction, macd_direction) == "ALIGNED"
        stoch_aligned = stochastic.cross_alignment == "ALIGNED"
        alligator_aligned = _alligator_matches_side(alligator_current, trade.direction)
        component_events = {
            "ALLIGATOR_STATE_START": alligator_start,
            "MACD": macd_cross_timestamp,
            "STOCH": stoch_cross_timestamp,
        }
        ages = {
            "ALLIGATOR_STATE_START": alligator_age,
            "MACD": macd_age,
            "STOCH": stoch_age,
        }
        max_age = max(ages.values())
        min_age = min(ages.values())
        rows.append(
            SequenceRow(
                period=period,
                trade=trade,
                outcome=_outcome(trade),
                alligator_state_start_timestamp=alligator_start,
                bars_since_alligator_state_start=alligator_age,
                alligator_state_changed_on_signal_bar=alligator_changed,
                alligator_phase=alligator_current.regime_phase,
                alligator_state=alligator_current.state,
                alligator_direction_aligned=alligator_aligned,
                macd_cross_timestamp=macd_cross_timestamp,
                bars_since_macd_cross=macd_age,
                macd_cross_direction=macd_direction,
                macd_aligned=macd_aligned,
                macd_cross_on_signal_bar=macd_age == 0,
                stochastic_cross_timestamp=stoch_cross_timestamp,
                bars_since_stochastic_cross=stoch_age,
                stochastic_cross_direction=stochastic.last_cross_direction,
                stochastic_aligned=stoch_aligned,
                stochastic_cross_on_signal_bar=stoch_age == 0,
                sequence_label=_sequence_label(component_events),
                oldest_component=_component_extreme(ages, oldest=True),
                newest_component=_component_extreme(ages, oldest=False),
                max_component_age_bars=max_age,
                min_component_age_bars=min_age,
                age_spread_bars=max_age - min_age,
                number_of_components_on_signal_bar=sum(
                    age == 0 for age in ages.values()
                ),
                all_components_aligned_at_entry=(
                    alligator_aligned and macd_aligned and stoch_aligned
                ),
            )
        )
    execution = runtime.replay_execution
    assert execution is not None
    assert len(rows) == len(execution.trade_diagnostics())
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                row.trade.signal_timestamp,
                row.trade.position_id,
            ),
        )
    )


def _feature_stats(rows: tuple[SequenceRow, ...], feature: str) -> FeatureStats | None:
    values = [float(getattr(row, feature)) for row in rows]
    if not values:
        return None
    if len(values) == 1:
        q1 = q3 = values[0]
    else:
        q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return FeatureStats(
        count=len(values),
        mean=statistics.fmean(values),
        median=statistics.median(values),
        q1=q1,
        q3=q3,
        minimum=min(values),
        maximum=max(values),
    )


def _stats_text(item: FeatureStats | None) -> str:
    if item is None:
        return "count:0"
    return (
        f"count:{item.count},mean:{item.mean:.4f},median:{item.median:.4f},"
        f"Q1:{item.q1:.4f},Q3:{item.q3:.4f},"
        f"min:{item.minimum:.4f},max:{item.maximum:.4f}"
    )


def _row_line(index: int, row: SequenceRow) -> str:
    trade = row.trade
    return (
        f"    {index:02d}|period:{row.period}|"
        f"signal:{trade.signal_timestamp.isoformat()}|"
        f"entry:{trade.entry_timestamp.isoformat()}|side:{trade.direction}|"
        f"outcome:{row.outcome}|"
        f"pnl:{trade.final_profit:+.2f}|close_reason:{trade.close_reason}|"
        f"alligator_state_start:{row.alligator_state_start_timestamp.isoformat()}|"
        f"bars_since_alligator_state_start:{row.bars_since_alligator_state_start}|"
        "alligator_opening_event:NOT_DEFINED|"
        f"alligator_state_changed_on_signal_bar:"
        f"{row.alligator_state_changed_on_signal_bar}|"
        f"alligator_phase:{row.alligator_phase}|alligator_state:{row.alligator_state}|"
        f"alligator_aligned:{row.alligator_direction_aligned}|"
        f"macd_cross:{row.macd_cross_timestamp.isoformat()}|"
        f"bars_since_macd_cross:{row.bars_since_macd_cross}|"
        f"macd_direction:{row.macd_cross_direction}|macd_aligned:{row.macd_aligned}|"
        f"macd_cross_on_signal_bar:{row.macd_cross_on_signal_bar}|"
        f"stoch_cross:{row.stochastic_cross_timestamp.isoformat()}|"
        f"bars_since_stoch_cross:{row.bars_since_stochastic_cross}|"
        f"stoch_direction:{row.stochastic_cross_direction}|"
        f"stoch_aligned:{row.stochastic_aligned}|"
        f"stoch_cross_on_signal_bar:{row.stochastic_cross_on_signal_bar}|"
        f"sequence:{row.sequence_label}|oldest:{row.oldest_component}|"
        f"newest:{row.newest_component}|"
        f"max_age:{row.max_component_age_bars}|min_age:{row.min_component_age_bars}|"
        f"age_spread:{row.age_spread_bars}|"
        f"components_on_signal_bar:{row.number_of_components_on_signal_bar}|"
        f"all_components_aligned:{row.all_components_aligned_at_entry}"
    )


def _run_period(spec: PeriodSpec) -> tuple[SequenceRow, ...]:
    """Виконати один deterministic current-production Replay."""

    broker_probe = BrokerRequestProbe()
    runtime = RejectedSurvivorAnatomyRuntime(
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
    rejects = _assert_stochastic_path(spec, runtime)
    _assert_geometry(runtime)
    rows = _build_rows(runtime, spec.code)
    counts = Counter(row.outcome for row in rows)
    summary = runtime.historical_summary
    assert summary is not None
    assert len(rows) == summary.opened_trades
    assert counts[OUTCOME_WIN] == summary.winning_trades
    assert counts[OUTCOME_LOSS] == summary.losing_trades
    assert counts[OUTCOME_BREAK_EVEN] == summary.break_even_trades
    assert broker_probe.requests == 0
    assert not _broker_execution_attempted(runtime)
    assert all(event.timeframe == "M15" for event in session.events)
    print(
        f"  population_{spec.code}=trades:{summary.opened_trades},"
        f"wins:{summary.winning_trades},"
        f"losses:{summary.losing_trades},"
        f"break_even:{summary.break_even_trades},"
        f"net:{summary.net_profit:+.2f},"
        f"pf:{summary.profit_factor:.4f},dd:{summary.maximum_drawdown:.2f},"
        f"stochastic_current_bar_rejects:{rejects},"
        f"broker_requests:{broker_probe.requests}"
    )
    print(f"  factual_trade_rows_{spec.code}")
    for index, row in enumerate(rows, start=1):
        print(_row_line(index, row))
    return rows


def _numeric_analysis(
    rows_by_period: dict[str, tuple[SequenceRow, ...]],
) -> dict[tuple[str, str, str], FeatureStats | None]:
    stats: dict[tuple[str, str, str], FeatureStats | None] = {}
    print("  maturity_numeric_stats")
    for period, rows in rows_by_period.items():
        print(f"    period={period}")
        for feature in NUMERIC_FEATURES:
            for outcome in OUTCOMES:
                group = tuple(row for row in rows if row.outcome == outcome)
                item = _feature_stats(group, feature)
                stats[(period, feature, outcome)] = item
                print(f"      {feature}|{outcome}|{_stats_text(item)}")
    return stats


def _sequence_analysis(rows_by_period: dict[str, tuple[SequenceRow, ...]]) -> set[str]:
    print("  sequence_categorical_stats")
    loss_sequences: dict[str, set[str]] = {}
    for period, rows in rows_by_period.items():
        print(f"    period={period}")
        loss_sequences[period] = set()
        for outcome in (OUTCOME_WIN, OUTCOME_LOSS):
            group = tuple(row for row in rows if row.outcome == outcome)
            counts = Counter(row.sequence_label for row in group)
            total = len(group)
            for label in sorted(counts):
                count = counts[label]
                percent = 100.0 * count / total if total else 0.0
                print(f"      {outcome}|{label}|count:{count},pct:{percent:.2f}")
                if outcome == OUTCOME_LOSS:
                    loss_sequences[period].add(label)
    repeated = set.intersection(*loss_sequences.values()) if loss_sequences else set()
    return repeated


def _direction(win: FeatureStats | None, loss: FeatureStats | None) -> str:
    if win is None or loss is None:
        return "NONE"
    if loss.median > win.median:
        return "LOSS_HIGHER"
    if loss.median < win.median:
        return "LOSS_LOWER"
    return "EQUAL"


def _non_overlapping_iqr(win: FeatureStats | None, loss: FeatureStats | None) -> bool:
    if win is None or loss is None:
        return False
    return loss.q1 > win.q3 or win.q1 > loss.q3


def _cross_period_summary(
    rows_by_period: dict[str, tuple[SequenceRow, ...]],
    stats: dict[tuple[str, str, str], FeatureStats | None],
    repeated_loss_sequences: set[str],
) -> tuple[list[str], list[str], list[str], bool]:
    periods = tuple(rows_by_period)
    consistent_direction: list[str] = []
    consistent_non_overlap: list[str] = []
    for feature in NUMERIC_FEATURES:
        directions = [
            _direction(
                stats[(period, feature, OUTCOME_WIN)],
                stats[(period, feature, OUTCOME_LOSS)],
            )
            for period in periods
        ]
        if (
            directions
            and directions[0] != "NONE"
            and all(item == directions[0] for item in directions)
        ):
            consistent_direction.append(f"{feature}:{directions[0]}")
            if all(
                _non_overlapping_iqr(
                    stats[(period, feature, OUTCOME_WIN)],
                    stats[(period, feature, OUTCOME_LOSS)],
                )
                for period in periods
            ):
                consistent_non_overlap.append(f"{feature}:{directions[0]}")

    exclusive_loss_sequences: list[str] = []
    for label in sorted(repeated_loss_sequences):
        if all(
            any(
                row.outcome == OUTCOME_LOSS and row.sequence_label == label
                for row in rows_by_period[period]
            )
            and not any(
                row.outcome == OUTCOME_WIN and row.sequence_label == label
                for row in rows_by_period[period]
            )
            for period in periods
        ):
            exclusive_loss_sequences.append(label)

    stable = bool(consistent_non_overlap or exclusive_loss_sequences)
    return (
        consistent_direction,
        consistent_non_overlap,
        exclusive_loss_sequences,
        stable,
    )


def _joined(values: list[str] | set[str]) -> str:
    return "NONE" if not values else ";".join(sorted(values))


def main() -> None:
    """Запустити factual T107-01 без rule або threshold."""

    production_before = _production_hashes()
    print("T107-01 Current Production Entry Sequence / Signal Maturity Anatomy")
    print(f"  test_id={TEST_ID}")
    print(f"  mode={MODE}")
    print("  population=FACTUAL_CURRENT_PRODUCTION_TRADES_ONLY")
    print("  outcome_role=LABEL_ONLY")
    print("  alligator_state_start=PRODUCTION_ACTIVE_STATE_CONTIGUOUS_START")
    print("  alligator_active_age_semantics=context.active_age_includes_signal_bar")
    print("  alligator_opening_event=NOT_DEFINED")
    print("  feature_not_defined_by_current_production=True")
    print(
        "  feature_not_defined_reason="
        "no_separate_canonical_alligator_opening_event_timestamp"
    )
    print("  macd_event=PRODUCTION_MACD_HISTOGRAM_ZERO_CROSS")
    print("  stochastic_event=CANONICAL_PRODUCTION_KD_CROSS_14_1_3")
    print("  same_completed_bar_order=SAME_BAR")
    print(
        "  stable_pattern_criterion="
        "NON_OVERLAPPING_WIN_LOSS_IQR_BOTH_PERIODS_OR_"
        "LOSS_ONLY_SEQUENCE_BOTH_PERIODS"
    )

    rows_by_period = {spec.code: _run_period(spec) for spec in PERIODS}
    stats = _numeric_analysis(rows_by_period)
    repeated = _sequence_analysis(rows_by_period)
    (
        consistent_direction,
        consistent_non_overlap,
        exclusive_loss_sequences,
        stable,
    ) = _cross_period_summary(
        rows_by_period,
        stats,
        repeated,
    )

    assert _production_hashes() == production_before
    print(f"  sequence_labels_cross_period_loss_repeat={_joined(repeated)}")
    print(f"  consistent_direction_maturity_features={_joined(consistent_direction)}")
    print(
        "  consistent_non_overlapping_iqr_maturity_features="
        f"{_joined(consistent_non_overlap)}"
    )
    print(
        "  cross_period_loss_only_sequence_labels="
        f"{_joined(exclusive_loss_sequences)}"
    )
    print(f"  stable_cross_period_sequence_or_maturity_pattern_found={stable}")
    if stable:
        if consistent_non_overlap:
            print(f"  strongest_factual_hypothesis={consistent_non_overlap[0]}")
        else:
            print(
                "  strongest_factual_hypothesis=LOSS_ONLY_SEQUENCE:"
                f"{exclusive_loss_sequences[0]}"
            )
    else:
        print("  strongest_factual_hypothesis=NONE")
    print("  candidate_rule_created=False")
    print("  threshold_optimization_performed=False")
    print("  future_bars_used_for_entry_features=False")
    print("  completed_market_events_only=True")
    print("  no_look_ahead=True")
    print("  deterministic_replay=True")
    print("  production_logic_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T107_01_CURRENT_PRODUCTION_ENTRY_SEQUENCE_MATURITY_ANATOMY=OK")


if __name__ == "__main__":
    main()
