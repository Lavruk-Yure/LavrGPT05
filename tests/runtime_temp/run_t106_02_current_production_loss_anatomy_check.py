"""run_t106_02_current_production_loss_anatomy_check.py — T106-02.

TEST_ONLY runner виконує registered current-production Candidate F Replay для
2025 і 2026 та аналізує тільки factual відкриті угоди після production
Stochastic 14/1/3 CURRENT_BAR reject. Для кожної угоди causal entry snapshot
об'єднує готові completed-M15 MACD, Stochastic, Alligator context і signal-bar
geometry. Outcome, close reason та PnL додаються лише після Replay як labels.

Числові ознаки друкуються окремо для WIN, LOSS і BE як median, inclusive IQR,
minimum та maximum. Категоріальні ознаки показують W/L/BE і net для direction,
UTC hour/bin, Alligator regime/phase/line order та MACD/Stochastic cross
geometry. Cross-period блок порівнює лише напрямок WIN/LOSS медіан та IQR
overlap; він не створює threshold або filter.

Volatility proxy повторює чинний причинний контракт Candidate F: середній
range попередніх 20 completed M15 bars, без signal bar. Runner не досліджує
Donchian, не запускає ML або sweep, не змінює production entry, PD, SL/TP,
recovery чи exit wiring і гарантує broker_requests=0 та no look-ahead.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from dataclasses import dataclass

from run_algorithm_workspace_replay_virtual_execution_check import (
    BrokerRequestProbe,
)
from run_t105_10_pd_35_production_regression_check import (
    PeriodSpec,
    _workspace,
)
from run_t105_15_stochastic_entry_anatomy_check import (
    OUTCOME_BREAK_EVEN,
    OUTCOME_LOSS,
    OUTCOME_WIN,
    StochasticEntryRow,
)
from run_t105_15_stochastic_entry_anatomy_check import (
    _build_rows as _build_stochastic_rows,
)
from run_t105_18_stochastic_current_bar_production_regression_check import (
    PERIODS,
    _assert_geometry,
    _assert_metrics,
    _assert_policy,
    _assert_stochastic_path,
    _broker_execution_attempted,
)
from run_t105_21_donchian_rejected_anatomy_check import (
    RejectedSurvivorAnatomyRuntime,
    _alligator_anatomy,
    _production_hashes,
)

from core.workspace_algorithm import create_registered_workspace_algorithm
from core.workspace_alligator import WorkspaceMacdAlligatorReplayAlgorithm
from core.workspace_historical_trade_diagnostics import (
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_macd import WorkspaceMacdObservation
from core.workspace_market_event import WorkspaceMarketEvent

TEST_ID = "T106-02"
MODE = "RM106_T106_02_CURRENT_PRODUCTION_LOSS_ANATOMY_TEST_ONLY"
EPSILON = 1e-12
VOLATILITY_LOOKBACK = 20
OUTCOMES = (OUTCOME_WIN, OUTCOME_LOSS, OUTCOME_BREAK_EVEN)

NUMERIC_FEATURES = (
    "macd",
    "macd_signal",
    "macd_histogram",
    "directional_histogram",
    "macd_slope",
    "macd_signal_slope",
    "histogram_slope",
    "macd_bars_since_cross",
    "stochastic_k",
    "stochastic_d",
    "stochastic_signed_kd",
    "stochastic_abs_kd",
    "stochastic_k_slope",
    "stochastic_d_slope",
    "stochastic_bars_since_cross",
    "alligator_normalized_opening",
    "alligator_opening_delta",
    "alligator_center_slope",
    "signal_range",
    "body_ratio",
    "directional_body_ratio",
    "upper_wick_ratio",
    "lower_wick_ratio",
    "range_in_spreads",
    "body_in_spreads",
    "prior_range_20",
    "range_ratio_prior_20",
)

CATEGORICAL_FEATURES = (
    "direction",
    "utc_hour",
    "utc_session_bin",
    "alligator_regime",
    "alligator_phase",
    "alligator_line_order",
    "macd_last_cross",
    "macd_cross_alignment",
    "stochastic_last_cross",
    "stochastic_cross_alignment",
)


@dataclass(frozen=True, slots=True)
class LossAnatomyRow:
    """Causal entry features і factual outcome однієї production trade."""

    trade: WorkspaceHistoricalTradeDiagnostic
    outcome: str
    macd: float
    macd_signal: float
    macd_histogram: float
    directional_histogram: float
    macd_slope: float
    macd_signal_slope: float
    histogram_slope: float
    macd_bars_since_cross: int
    stochastic_k: float
    stochastic_d: float
    stochastic_signed_kd: float
    stochastic_abs_kd: float
    stochastic_k_slope: float
    stochastic_d_slope: float
    stochastic_bars_since_cross: int
    alligator_normalized_opening: float
    alligator_opening_delta: float
    alligator_center_slope: float
    signal_range: float
    body_ratio: float
    directional_body_ratio: float
    upper_wick_ratio: float
    lower_wick_ratio: float
    range_in_spreads: float
    body_in_spreads: float
    prior_range_20: float
    range_ratio_prior_20: float
    direction: str
    utc_hour: int
    utc_session_bin: str
    alligator_regime: str
    alligator_phase: str
    alligator_line_order: str
    macd_last_cross: str
    macd_cross_alignment: str
    stochastic_last_cross: str
    stochastic_cross_alignment: str


@dataclass(frozen=True, slots=True)
class FeatureStats:
    """Описова статистика числової causal feature для outcome group."""

    n: int
    median: float
    p25: float
    p75: float
    minimum: float
    maximum: float


def _required_float(value: float | None, name: str) -> float:
    """Повернути скінченне готове значення або зупинити diagnostic."""

    assert value is not None, name
    number = float(value)
    assert math.isfinite(number), name
    return number


def _macd_cross_direction(
    previous_histogram: float,
    current_histogram: float,
) -> str | None:
    """Визначити causal zero-line cross MACD histogram між двома bars."""

    if previous_histogram <= EPSILON < current_histogram:
        return "UP"
    if previous_histogram >= -EPSILON > current_histogram:
        return "DOWN"
    return None


def _last_macd_cross(
    observations: tuple[WorkspaceMacdObservation, ...],
    index: int,
) -> tuple[str, int]:
    """Знайти останній MACD histogram cross не пізніше signal bar."""

    for cross_index in range(index, 0, -1):
        current = observations[cross_index]
        previous = observations[cross_index - 1]
        if current.histogram is None or previous.histogram is None:
            continue
        direction = _macd_cross_direction(
            float(previous.histogram),
            float(current.histogram),
        )
        if direction is not None:
            return direction, index - cross_index
    raise AssertionError("MACD cross is unavailable for a factual trade")


def _cross_alignment(direction: str, cross: str) -> str:
    """Описати напрямну відповідність останнього cross стороні trade."""

    expected = "UP" if direction == "BUY" else "DOWN"
    return "ALIGNED" if cross == expected else "OPPOSED"


def _utc_session_bin(hour: int) -> str:
    """Згрупувати UTC hour у фіксовані 8-годинні anatomy bins."""

    if hour < 8:
        return "UTC_00_07"
    if hour < 16:
        return "UTC_08_15"
    return "UTC_16_23"


def _signal_geometry(
    event: WorkspaceMarketEvent,
    direction: str,
) -> tuple[float, float, float, float, float, float, float]:
    """Обчислити causal signal-bar та spread-normalized geometry."""

    signal_range = float(event.high - event.low)
    spread = float(event.spread)
    assert signal_range > 0.0 and spread > 0.0
    body = float(event.close - event.open)
    upper_wick = float(event.high - max(event.open, event.close))
    lower_wick = float(min(event.open, event.close) - event.low)
    sign = 1.0 if direction == "BUY" else -1.0
    return (
        signal_range,
        abs(body) / signal_range,
        sign * body / signal_range,
        upper_wick / signal_range,
        lower_wick / signal_range,
        signal_range / spread,
        abs(body) / spread,
    )


def _prior_range(
    events: tuple[WorkspaceMarketEvent, ...],
    index: int,
) -> float:
    """Повторити production 20-bar prior-range contract."""

    assert index >= VOLATILITY_LOOKBACK
    prior = events[index - VOLATILITY_LOOKBACK : index]  # noqa
    assert len(prior) == VOLATILITY_LOOKBACK
    assert all(event.timestamp < events[index].timestamp for event in prior)
    return statistics.fmean(float(event.high - event.low) for event in prior)


def _build_rows(
    runtime: RejectedSurvivorAnatomyRuntime,
) -> tuple[LossAnatomyRow, ...]:
    """Зіставити всі factual production trades з causal entry snapshots."""

    algorithm = runtime.algorithm
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    source = algorithm.source
    signal_filter = algorithm.signal_filter
    assert source is not None and signal_filter is not None
    assert signal_filter.runtime_profile.volatility_lookback_bars == 20

    stochastic_rows = {
        row.trade.signal_uid: row for row in _build_stochastic_rows(runtime)
    }
    records = {
        record.signal_uid: record
        for record in runtime.historical_signal_records
        if record.accepted
    }
    events = tuple(
        runtime.strategy_events[timestamp]
        for timestamp in sorted(runtime.strategy_events)
    )
    event_index = {event.timestamp: index for index, event in enumerate(events)}
    macd_observations = tuple(source.observations)
    macd_index = {
        observation.timestamp: index
        for index, observation in enumerate(macd_observations)
    }
    assert stochastic_rows.keys() == records.keys()

    rows: list[LossAnatomyRow] = []
    for signal_uid, stochastic in stochastic_rows.items():
        stochastic: StochasticEntryRow
        trade = stochastic.trade
        record = records[signal_uid]
        context = record.filter_context
        assert context is not None
        assert record.timestamp == trade.signal_timestamp
        event_position = event_index[trade.signal_timestamp]
        macd_position = macd_index[trade.signal_timestamp]
        assert macd_position >= 1
        current_macd = macd_observations[macd_position]
        previous_macd = macd_observations[macd_position - 1]
        assert current_macd.timestamp == trade.signal_timestamp

        macd = _required_float(current_macd.macd_value, "macd")
        macd_signal = _required_float(current_macd.signal_value, "signal")
        histogram = _required_float(current_macd.histogram, "histogram")
        previous_value = _required_float(previous_macd.macd_value, "macd_prev")
        previous_signal = _required_float(
            previous_macd.signal_value,
            "signal_prev",
        )
        previous_histogram = _required_float(
            previous_macd.histogram,
            "histogram_prev",
        )
        macd_cross, macd_cross_age = _last_macd_cross(
            macd_observations,
            macd_position,
        )
        assert stochastic.bars_since_cross is not None
        assert stochastic.bars_since_cross > 0

        regime, line_order, opening, opening_delta, center_slope = _alligator_anatomy(
            context, trade.signal_timestamp
        )
        event = events[event_position]
        geometry = _signal_geometry(event, trade.direction)
        prior_range = _prior_range(events, event_position)
        assert prior_range > 0.0
        directional_sign = 1.0 if trade.direction == "BUY" else -1.0
        rows.append(
            LossAnatomyRow(
                trade=trade,
                outcome=stochastic.outcome,
                macd=macd,
                macd_signal=macd_signal,
                macd_histogram=histogram,
                directional_histogram=directional_sign * histogram,
                macd_slope=macd - previous_value,
                macd_signal_slope=macd_signal - previous_signal,
                histogram_slope=histogram - previous_histogram,
                macd_bars_since_cross=macd_cross_age,
                stochastic_k=stochastic.percent_k,
                stochastic_d=stochastic.percent_d,
                stochastic_signed_kd=stochastic.k_minus_d,
                stochastic_abs_kd=abs(stochastic.k_minus_d),
                stochastic_k_slope=stochastic.slope_k,
                stochastic_d_slope=stochastic.slope_d,
                stochastic_bars_since_cross=stochastic.bars_since_cross,
                alligator_normalized_opening=opening,
                alligator_opening_delta=opening_delta,
                alligator_center_slope=center_slope,
                signal_range=geometry[0],
                body_ratio=geometry[1],
                directional_body_ratio=geometry[2],
                upper_wick_ratio=geometry[3],
                lower_wick_ratio=geometry[4],
                range_in_spreads=geometry[5],
                body_in_spreads=geometry[6],
                prior_range_20=prior_range,
                range_ratio_prior_20=geometry[0] / prior_range,
                direction=trade.direction,
                utc_hour=trade.signal_timestamp.hour,
                utc_session_bin=_utc_session_bin(trade.signal_timestamp.hour),
                alligator_regime=regime,
                alligator_phase=str(context.regime_phase or "NONE"),
                alligator_line_order=line_order,
                macd_last_cross=macd_cross,
                macd_cross_alignment=_cross_alignment(
                    trade.direction,
                    macd_cross,
                ),
                stochastic_last_cross=stochastic.last_cross_direction,
                stochastic_cross_alignment=stochastic.cross_alignment,
            )
        )

    execution = runtime.replay_execution
    assert execution is not None
    assert len(rows) == len(execution.trade_diagnostics())
    return tuple(rows)


def _feature_stats(
    rows: tuple[LossAnatomyRow, ...],
    feature: str,
) -> FeatureStats:
    """Обчислити inclusive quartiles навіть для малої outcome group."""

    values = sorted(float(getattr(row, feature)) for row in rows)
    assert values
    if len(values) == 1:
        p25 = p75 = values[0]
    else:
        quartiles = statistics.quantiles(values, n=4, method="inclusive")
        p25 = float(quartiles[0])
        p75 = float(quartiles[2])
    return FeatureStats(
        n=len(values),
        median=float(statistics.median(values)),
        p25=p25,
        p75=p75,
        minimum=values[0],
        maximum=values[-1],
    )


def _stats_line(outcome: str, item: FeatureStats) -> str:
    """Сформувати стабільний рядок numeric outcome statistics."""

    return (
        f"        {outcome}=n:{item.n},median:{item.median:+.6f},"
        f"p25:{item.p25:+.6f},p75:{item.p75:+.6f},"
        f"min:{item.minimum:+.6f},max:{item.maximum:+.6f}"
    )


def _numeric_stats(
    rows_by_period: dict[str, tuple[LossAnatomyRow, ...]],
) -> dict[str, dict[str, dict[str, FeatureStats]]]:
    """Надрукувати numeric WIN/LOSS/BE anatomy для кожного періоду."""

    result: dict[str, dict[str, dict[str, FeatureStats]]] = {}
    print("  NUMERIC_FEATURES")
    for period, rows in rows_by_period.items():
        result[period] = {}
        print(f"    period={period}")
        for feature in NUMERIC_FEATURES:
            result[period][feature] = {}
            print(f"      feature={feature}")
            for outcome in OUTCOMES:
                group = tuple(row for row in rows if row.outcome == outcome)
                item = _feature_stats(group, feature)
                result[period][feature][outcome] = item
                print(_stats_line(outcome, item))
    return result


def _categorical_value(row: LossAnatomyRow, feature: str) -> str:
    """Нормалізувати categorical feature до стабільного console label."""

    value = getattr(row, feature)
    if feature == "utc_hour":
        return f"UTC_{int(value):02d}"
    return str(value)


def _categorical_stats(
    rows_by_period: dict[str, tuple[LossAnatomyRow, ...]],
) -> None:
    """Надрукувати outcomes і PnL для кожної категоріальної ознаки."""

    print("  CATEGORICAL_FEATURES")
    for period, rows in rows_by_period.items():
        print(f"    period={period}")
        for feature in CATEGORICAL_FEATURES:
            print(f"      feature={feature}")
            values = sorted({_categorical_value(row, feature) for row in rows})
            for value in values:
                group = tuple(
                    row for row in rows if _categorical_value(row, feature) == value
                )
                counts = Counter(row.outcome for row in group)
                net = math.fsum(row.trade.final_profit for row in group)
                print(
                    f"        {value}=trades:{len(group)},"
                    f"W:{counts[OUTCOME_WIN]},L:{counts[OUTCOME_LOSS]},"
                    f"BE:{counts[OUTCOME_BREAK_EVEN]},net:{net:+.2f}"
                )


def _median_direction(win: FeatureStats, loss: FeatureStats) -> str:
    """Описати знак WIN/LOSS median difference без threshold."""

    if win.median > loss.median:
        return "WIN_GT_LOSS"
    if win.median < loss.median:
        return "WIN_LT_LOSS"
    return "EQUAL"


def _iqr_overlap(win: FeatureStats, loss: FeatureStats) -> bool:
    """Перевірити перетин inclusive WIN/LOSS IQR."""

    return max(win.p25, loss.p25) <= min(win.p75, loss.p75)


def _cross_period_separation(
    stats: dict[str, dict[str, dict[str, FeatureStats]]],
) -> None:
    """Показати consistency медіан та overlap без selection rule."""

    consistent_features: list[str] = []
    non_overlapping_features: list[str] = []
    print("  CROSS_PERIOD_WIN_LOSS_DESCRIPTION")
    for feature in NUMERIC_FEATURES:
        win_2025 = stats["2025"][feature][OUTCOME_WIN]
        loss_2025 = stats["2025"][feature][OUTCOME_LOSS]
        win_2026 = stats["2026"][feature][OUTCOME_WIN]
        loss_2026 = stats["2026"][feature][OUTCOME_LOSS]
        direction_2025 = _median_direction(win_2025, loss_2025)
        direction_2026 = _median_direction(win_2026, loss_2026)
        overlap_2025 = _iqr_overlap(win_2025, loss_2025)
        overlap_2026 = _iqr_overlap(win_2026, loss_2026)
        consistent = direction_2025 == direction_2026
        if consistent:
            consistent_features.append(feature)
        if consistent and not overlap_2025 and not overlap_2026:
            non_overlapping_features.append(feature)
        print(
            f"    {feature}=median_direction_2025:{direction_2025},"
            f"median_direction_2026:{direction_2026},"
            f"cross_period_direction_consistent:{consistent},"
            f"IQR_overlap_2025:{overlap_2025},"
            f"IQR_overlap_2026:{overlap_2026}"
        )
    print(
        "  DIRECTION_CONSISTENT_FEATURES=" + (",".join(consistent_features) or "NONE")
    )
    print(
        "  CONSISTENT_NON_OVERLAPPING_IQR_FEATURES="
        + (",".join(non_overlapping_features) or "NONE")
    )


def _row_line(row: LossAnatomyRow) -> str:
    """Сформувати causal evidence row для factual LOSS або BE."""

    return (
        f"      {row.trade.signal_timestamp.isoformat()}|{row.direction}|"
        f"{row.outcome}|{row.trade.final_profit:+.2f}|"
        f"{row.trade.close_reason}|{row.macd:+.8f}|"
        f"{row.macd_signal:+.8f}|{row.macd_histogram:+.8f}|"
        f"{row.macd_slope:+.8f}|{row.macd_bars_since_cross}|"
        f"{row.stochastic_k:.4f}|{row.stochastic_d:.4f}|"
        f"{row.stochastic_signed_kd:+.4f}|"
        f"{row.stochastic_bars_since_cross}|"
        f"{row.alligator_normalized_opening:.6f}|"
        f"{row.alligator_opening_delta:+.6f}|"
        f"{row.alligator_center_slope:+.6f}|"
        f"{row.signal_range:.6f}|{row.body_ratio:.4f}|"
        f"{row.upper_wick_ratio:.4f}|{row.lower_wick_ratio:.4f}|"
        f"{row.range_in_spreads:.4f}|{row.range_ratio_prior_20:.4f}|"
        f"{row.utc_hour:02d}|{row.utc_session_bin}|"
        f"{row.alligator_regime}|{row.alligator_phase}|"
        f"{row.alligator_line_order}"
    )


def _print_loss_be_rows(
    rows_by_period: dict[str, tuple[LossAnatomyRow, ...]],
) -> None:
    """Надрукувати всі remaining LOSS і BE для factual audit."""

    print("  FACTUAL_LOSS_AND_BE_ROWS")
    print(
        "      timestamp|side|outcome|pnl|close_reason|MACD|Signal|Histogram|"
        "MACD_slope|MACD_cross_age|K|D|signed_KD|stoch_cross_age|"
        "alligator_opening|opening_delta|center_slope|signal_range|"
        "body_ratio|upper_wick_ratio|lower_wick_ratio|range_spreads|"
        "range_ratio_prior20|utc_hour|utc_bin|regime|phase|line_order"
    )
    for period, rows in rows_by_period.items():
        print(f"    period={period}")
        selected = tuple(
            row for row in rows if row.outcome in {OUTCOME_LOSS, OUTCOME_BREAK_EVEN}
        )
        for row in selected:
            print(_row_line(row))


def _run_period(spec: PeriodSpec) -> tuple[LossAnatomyRow, ...]:
    """Виконати один current-production Replay без broker execution."""

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
    stochastic_rejects = _assert_stochastic_path(spec, runtime)
    _assert_geometry(runtime)
    rows = _build_rows(runtime)
    counts = Counter(row.outcome for row in rows)
    summary = runtime.historical_summary
    assert summary is not None
    assert len(rows) == summary.opened_trades
    assert counts[OUTCOME_WIN] == summary.winning_trades
    assert counts[OUTCOME_LOSS] == summary.losing_trades
    assert counts[OUTCOME_BREAK_EVEN] == summary.break_even_trades
    assert broker_probe.requests == 0
    assert not _broker_execution_attempted(runtime)
    assert session.completed
    assert all(event.timeframe == "M15" for event in session.events)
    print(
        f"  population_{spec.code}=trades:{summary.opened_trades},"
        f"W:{summary.winning_trades},L:{summary.losing_trades},"
        f"BE:{summary.break_even_trades},net:{summary.net_profit:+.2f},"
        f"pf:{summary.profit_factor:.4f},dd:{summary.maximum_drawdown:.2f},"
        f"stochastic_current_bar_rejects:{stochastic_rejects},"
        f"broker_requests:{broker_probe.requests}"
    )
    return rows


def main() -> None:
    """Запустити T106-02 як descriptive current-production anatomy."""

    production_before = _production_hashes()
    print("T106-02 Current Production Loss Anatomy")
    print(f"  test_id={TEST_ID}")
    print(f"  mode={MODE}")
    print("  population=FACTUAL_CURRENT_PRODUCTION_TRADES_ONLY")
    print("  outcome_groups=WIN,LOSS,BE")
    print("  signal_bar=CAUSAL_COMPLETED_M15")
    print("  volatility_proxy=MEAN_RANGE_PREVIOUS_20_M15")
    print("  volatility_reference_excludes_signal_bar=True")
    print("  utc_session_bins=UTC_00_07,UTC_08_15,UTC_16_23")
    rows_by_period = {spec.code: _run_period(spec) for spec in PERIODS}
    stats = _numeric_stats(rows_by_period)
    _categorical_stats(rows_by_period)
    _cross_period_separation(stats)
    _print_loss_be_rows(rows_by_period)

    assert _production_hashes() == production_before
    print("  outcome_used_as_label_only=True")
    print("  entry_features_future_bars_used=False")
    print("  completed_market_events_only=True")
    print("  no_look_ahead=True")
    print("  deterministic_replay=True")
    print("  production_stochastic_gate_active=True")
    print("  donchian_used=False")
    print("  production_logic_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  filter_rule_created=False")
    print("  threshold_optimization_performed=False")
    print("  machine_learning_used=False")
    print("T106_02_CURRENT_PRODUCTION_LOSS_ANATOMY=OK")


if __name__ == "__main__":
    main()
