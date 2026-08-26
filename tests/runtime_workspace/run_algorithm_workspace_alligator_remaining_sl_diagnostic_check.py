# -*- coding: utf-8 -*-
"""Діагностика п'яти SL після 4-bar + collapse -0.700, RoadMap101 №34.

Тест виконує test-only counterfactual D із GREEN №33 лише для Validation та
Holdout: Alligator confirmation=4 і causal opening-collapse guard -0.700.
Для кожної фактично відкритої угоди збирає тільки entry-time evidence,
відомий на завершеному M15 bar сигналу: Alligator active/regime age,
normalized slope/opening та їх t-2 -> t delta; MACD prominence, distance,
ABC angle і crossover steepness; range signal-bar та його відношення до
середнього range 20 попередніх завершених strategy bars.

Головне порівняння: п'ять STOP_LOSS, що залишилися після guard, проти всіх
surviving winners Validation+Holdout. MFE/MAE та PnL друкуються лише як
post-trade outcome і не використовуються як entry gate. Production algorithm,
trade gate, registration, профілі та broker execution тест не змінює.
"""

from __future__ import annotations

import importlib.util
import math
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import core.workspace_alligator as workspace_alligator  # noqa: E402
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    ALLIGATOR_STATE_BEARISH,
    ALLIGATOR_STATE_BULLISH,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402

SOURCE_30 = Path(__file__).with_name(
    "run_algorithm_workspace_macd_deferred_alligator_entry_comparison_check.py"
)
SOURCE_33 = Path(__file__).with_name(
    "run_algorithm_workspace_alligator_opening_collapse_counterfactual_check.py"
)

WINDOWS = (
    (
        "VALIDATION",
        "2026-03-01T00:00:00+00:00",
        "2026-05-31T23:59:00+00:00",
    ),
    (
        "HOLDOUT",
        "2026-06-01T00:00:00+00:00",
        "2026-08-11T08:24:00+00:00",
    ),
)

CONFIRMATION_BARS = 4
COLLAPSE_THRESHOLD = -0.700
VOLATILITY_LOOKBACK_BARS = 20
WIN_LOSS_TOLERANCE = 1e-12

LOCKED_D_RESULTS = {
    "VALIDATION": (17, 10, 7, 3, 14, -2.23),
    "HOLDOUT": (9, 4, 5, 2, 7, -3.84),
}

EXPECTED_REMAINING_SL = (
    ("2026-03-06T21:00:00+00:00", "BUY", -1.25),
    ("2026-04-02T06:00:00+00:00", "SELL", -1.20),
    ("2026-04-21T19:30:00+00:00", "SELL", -3.10),
    ("2026-06-18T06:15:00+00:00", "BUY", -1.20),
    ("2026-06-26T12:45:00+00:00", "BUY", -2.75),
)


@dataclass(frozen=True, slots=True)
class EntryEvidence:
    """Causal entry evidence + post-trade outcome однієї фактичної угоди."""

    window: str
    signal_timestamp: datetime
    direction: str
    close_reason: str
    final_profit: float
    maximum_favorable_excursion: float
    maximum_adverse_excursion: float
    active_age_bars: int
    regime_age_bars: int
    normalized_slope: float
    normalized_opening: float
    slope_delta_t2_t: float
    opening_delta_t2_t: float
    macd_strength: float
    macd_extremum_prominence: float
    macd_extremum_distance: float
    macd_effective_angle: float
    macd_crossover_steepness: float
    macd_search_window: int
    signal_bar_range: float
    prior_range_average: float
    signal_range_ratio: float

    @property
    def winner(self) -> bool:
        return self.final_profit > WIN_LOSS_TOLERANCE

    @property
    def loser(self) -> bool:
        return self.final_profit < -WIN_LOSS_TOLERANCE


@dataclass(frozen=True, slots=True)
class WindowResult:
    """Один фактичний D Replay із causal evidence усіх відкритих угод."""

    window: str
    trades: tuple[EntryEvidence, ...]
    winners: int
    losers: int
    stop_loss_closes: int
    profit_drawdown_closes: int
    net_profit: float
    guard_rejections: int
    broker_execution_attempted: bool


@dataclass(frozen=True, slots=True)
class MetricSummary:
    """Mean/median/range одного entry-time metric."""

    mean: float
    median: float
    minimum: float
    maximum: float


def _load_module(path: Path, module_name: str):
    """Завантажити sibling GREEN test без залежності від tests package."""
    assert path.is_file(), path
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _direction_signature(direction: str) -> tuple[str, str]:
    """Повернути очікуваний causal Alligator regime/state для direction."""
    if direction == "BUY":
        return ALLIGATOR_REGIME_TREND_UP, ALLIGATOR_STATE_BULLISH
    if direction == "SELL":
        return ALLIGATOR_REGIME_TREND_DOWN, ALLIGATOR_STATE_BEARISH
    raise AssertionError(direction)


def _consecutive_count(
    observations: tuple[Any, ...],
    current_index: int,
    predicate: Callable[[Any], bool],
) -> int:
    """Порахувати causal streak назад від поточного observation."""
    count = 0
    for index in range(current_index, -1, -1):
        if not predicate(observations[index]):
            break
        count += 1
    return count


def _quality_map(source) -> dict[tuple[datetime, str], Any]:
    """Індексувати MACD quality diagnostics за signal timestamp/direction."""
    result: dict[tuple[datetime, str], Any] = {}
    for diagnostic in source.quality_diagnostics:
        key = (diagnostic.timestamp, diagnostic.direction)
        assert key not in result
        result[key] = diagnostic
    return result


def _event_range_evidence(session, signal_timestamp: datetime) -> tuple[float, ...]:
    """Повернути range signal bar, prior-20 average та causal ratio."""
    event_index = {
        event.timestamp: index for index, event in enumerate(session.events)
    }.get(signal_timestamp)
    assert event_index is not None
    assert event_index >= VOLATILITY_LOOKBACK_BARS
    event = session.events[event_index]
    prior = session.events[event_index - VOLATILITY_LOOKBACK_BARS : event_index]  # noqa
    assert len(prior) == VOLATILITY_LOOKBACK_BARS
    assert all(item.timestamp < signal_timestamp for item in prior)

    signal_range = float(event.high - event.low)
    prior_average = statistics.fmean(float(item.high - item.low) for item in prior)
    assert signal_range > 0.0
    assert prior_average > 0.0
    return signal_range, prior_average, signal_range / prior_average


def _build_evidence(
    *,
    window: str,
    trade,
    record,
    observations: tuple[Any, ...],
    observation_index: int,
    quality_diagnostic,
    session,
) -> EntryEvidence:
    """Зібрати causal entry snapshot для однієї фактичної D-угоди."""
    context = record.filter_context
    assert context is not None
    current = observations[observation_index]
    regime, state = _direction_signature(trade.direction)

    assert record.accepted
    assert record.filter_decision == "ALLOW"
    assert current.regime == regime
    assert current.state == state
    assert current.regime_phase == ALLIGATOR_REGIME_PHASE_ACTIVE
    assert current.timestamp == context.observation_timestamp
    assert current.timestamp <= record.timestamp
    assert current.available_at <= record.timestamp
    assert observation_index >= 2

    history = observations[observation_index - 2 : observation_index + 1]  # noqa
    assert len(history) == 3
    oldest = history[0]
    assert oldest.timestamp < history[1].timestamp < current.timestamp
    assert oldest.normalized_slope is not None
    assert oldest.normalized_opening is not None
    assert current.normalized_slope is not None
    assert current.normalized_opening is not None

    active_age = _consecutive_count(
        observations,
        observation_index,
        lambda item: bool(
            item.regime == regime
            and item.state == state
            and item.regime_phase == ALLIGATOR_REGIME_PHASE_ACTIVE
        ),
    )
    regime_age = _consecutive_count(
        observations,
        observation_index,
        lambda item: item.regime == regime,
    )

    assert quality_diagnostic.timestamp == record.timestamp
    assert quality_diagnostic.direction == trade.direction
    assert quality_diagnostic.final_quality_pass
    assert quality_diagnostic.extremum_prominence is not None
    assert quality_diagnostic.extremum_to_cross_distance is not None
    assert quality_diagnostic.search_window is not None

    signal_range, prior_range, range_ratio = _event_range_evidence(
        session,
        record.timestamp,
    )
    return EntryEvidence(
        window=window,
        signal_timestamp=trade.signal_timestamp,
        direction=trade.direction,
        close_reason=trade.close_reason,
        final_profit=trade.final_profit,
        maximum_favorable_excursion=trade.maximum_favorable_excursion,
        maximum_adverse_excursion=trade.maximum_adverse_excursion,
        active_age_bars=active_age,
        regime_age_bars=regime_age,
        normalized_slope=float(current.normalized_slope),
        normalized_opening=float(current.normalized_opening),
        slope_delta_t2_t=float(current.normalized_slope - oldest.normalized_slope),
        opening_delta_t2_t=float(
            current.normalized_opening - oldest.normalized_opening
        ),
        macd_strength=float(record.strength),
        macd_extremum_prominence=float(quality_diagnostic.extremum_prominence),
        macd_extremum_distance=float(quality_diagnostic.extremum_to_cross_distance),
        macd_effective_angle=float(quality_diagnostic.effective_angle_degrees),
        macd_crossover_steepness=float(quality_diagnostic.crossover_steepness),
        macd_search_window=int(quality_diagnostic.search_window),
        signal_bar_range=signal_range,
        prior_range_average=prior_range,
        signal_range_ratio=range_ratio,
    )


def _run_window(
    source_30,
    source_33,
    window: str,
    start: str,
    end: str,
) -> WindowResult:
    """Виконати фактичний D=4-bar+collapse -0.700 Replay для одного window."""
    original = workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS
    workspace_factory = getattr(source_30, "_workspace")
    guard_class = source_33.OpeningCollapseGuardAlgorithm

    def algorithm_factory(algorithm_id: str):
        return guard_class(algorithm_id, COLLAPSE_THRESHOLD)

    try:
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS = (
            CONFIRMATION_BARS
        )
        runtime = WorkspaceRuntime(
            workspace_factory(start, end),
            algorithm_factory=algorithm_factory,
        )
        runtime.begin_start()
        runtime.complete_start()
        session = runtime.replay_session
        assert session is not None
        while not session.completed:
            runtime.advance_replay()

        summary = runtime.historical_summary
        execution = runtime.replay_execution
        algorithm = runtime.algorithm
        assert summary is not None
        assert execution is not None
        signal_filter = getattr(algorithm, "signal_filter")
        macd_source = getattr(algorithm, "source")
        assert signal_filter is not None
        assert macd_source is not None

        observations = tuple(signal_filter.observations)
        observation_index = {
            item.timestamp: index for index, item in enumerate(observations)
        }
        records = runtime.signal_records()
        record_by_uid = {record.signal_uid: record for record in records}
        diagnostics = _quality_map(macd_source)

        trades: list[EntryEvidence] = []
        for trade in execution.trade_diagnostics():
            record = record_by_uid.get(trade.signal_uid)
            assert record is not None
            context = record.filter_context
            assert context is not None
            assert context.observation_timestamp is not None
            index = observation_index.get(context.observation_timestamp)
            assert index is not None
            quality = diagnostics.get((record.timestamp, record.direction))
            assert quality is not None
            trades.append(
                _build_evidence(
                    window=window,
                    trade=trade,
                    record=record,
                    observations=observations,
                    observation_index=index,
                    quality_diagnostic=quality,
                    session=session,
                )
            )

        broker_execution_attempted = any(
            bool(entry.details.get("broker_execution_attempted"))
            for entry in runtime.journal
            if isinstance(entry.details, dict)
        )
        guard_rejections = len(getattr(algorithm, "guard_rejections", ()))
        return WindowResult(
            window=window,
            trades=tuple(trades),
            winners=summary.winning_trades,
            losers=summary.losing_trades,
            stop_loss_closes=summary.close_reason_count("STOP_LOSS"),
            profit_drawdown_closes=summary.close_reason_count("PROFIT_DRAWDOWN"),
            net_profit=summary.net_profit,
            guard_rejections=guard_rejections,
            broker_execution_attempted=broker_execution_attempted,
        )
    finally:
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS = original


def _summary(values) -> MetricSummary:
    """Побудувати mean/median/min/max для непорожнього numeric sequence."""
    values = tuple(float(value) for value in values)
    assert values
    return MetricSummary(
        mean=statistics.fmean(values),
        median=statistics.median(values),
        minimum=min(values),
        maximum=max(values),
    )


def _format_metric(summary: MetricSummary, digits: int) -> str:
    """Компактно показати mean/median/range."""
    return (
        f"avg:{summary.mean:.{digits}f},med:{summary.median:.{digits}f},"
        f"range:{summary.minimum:.{digits}f}..{summary.maximum:.{digits}f}"
    )


def _format_alligator_group(name: str, trades: tuple[EntryEvidence, ...]) -> str:
    """Агрегувати Alligator entry evidence групи."""
    active = _summary(trade.active_age_bars for trade in trades)
    regime = _summary(trade.regime_age_bars for trade in trades)
    slope = _summary(trade.normalized_slope for trade in trades)
    slope_delta = _summary(trade.slope_delta_t2_t for trade in trades)
    opening = _summary(trade.normalized_opening for trade in trades)
    opening_delta = _summary(trade.opening_delta_t2_t for trade in trades)
    return (
        f"{name}_alligator="
        f"active[{_format_metric(active, 2)}];"
        f"regime[{_format_metric(regime, 2)}];"
        f"slope[{_format_metric(slope, 6)}];"
        f"slope_delta[{_format_metric(slope_delta, 6)}];"
        f"opening[{_format_metric(opening, 6)}];"
        f"opening_delta[{_format_metric(opening_delta, 6)}]"
    )


def _format_macd_group(name: str, trades: tuple[EntryEvidence, ...]) -> str:
    """Агрегувати MACD geometry групи."""
    prominence = _summary(trade.macd_extremum_prominence for trade in trades)
    distance = _summary(trade.macd_extremum_distance for trade in trades)
    angle = _summary(trade.macd_effective_angle for trade in trades)
    steepness = _summary(trade.macd_crossover_steepness for trade in trades)
    strength = _summary(trade.macd_strength for trade in trades)
    return (
        f"{name}_macd="
        f"prominence[{_format_metric(prominence, 8)}];"
        f"distance[{_format_metric(distance, 8)}];"
        f"angle[{_format_metric(angle, 2)}];"
        f"steepness[{_format_metric(steepness, 8)}];"
        f"strength[{_format_metric(strength, 8)}]"
    )


def _format_range_group(name: str, trades: tuple[EntryEvidence, ...]) -> str:
    """Агрегувати causal signal-bar range/volatility evidence групи."""
    signal_range = _summary(trade.signal_bar_range for trade in trades)
    prior_range = _summary(trade.prior_range_average for trade in trades)
    ratio = _summary(trade.signal_range_ratio for trade in trades)
    return (
        f"{name}_range="
        f"signal[{_format_metric(signal_range, 6)}];"
        f"prior20[{_format_metric(prior_range, 6)}];"
        f"ratio[{_format_metric(ratio, 3)}]"
    )


def _format_trade(index: int, trade: EntryEvidence) -> str:
    """Вивести всі causal entry features однієї remaining SL."""
    return (
        f"remaining_sl_{index:02d}={trade.signal_timestamp.isoformat()} "
        f"{trade.direction} pnl:{trade.final_profit:+.2f},"
        f"active:{trade.active_age_bars},regime:{trade.regime_age_bars},"
        f"slope:{trade.normalized_slope:.6f},"
        f"slope_d:{trade.slope_delta_t2_t:+.6f},"
        f"opening:{trade.normalized_opening:.6f},"
        f"opening_d:{trade.opening_delta_t2_t:+.6f},"
        f"prom:{trade.macd_extremum_prominence:.8f},"
        f"dist:{trade.macd_extremum_distance:.8f},"
        f"angle:{trade.macd_effective_angle:.2f},"
        f"steep:{trade.macd_crossover_steepness:.8f},"
        f"search:{trade.macd_search_window},"
        f"bar_range:{trade.signal_bar_range:.6f},"
        f"range20:{trade.prior_range_average:.6f},"
        f"range_ratio:{trade.signal_range_ratio:.3f},"
        f"mfe:{trade.maximum_favorable_excursion:+.2f},"
        f"mae:{trade.maximum_adverse_excursion:+.2f}"
    )


def _assert_locked(result: WindowResult) -> None:
    """Перевірити фактичний D result проти GREEN №33."""
    expected = LOCKED_D_RESULTS[result.window]
    actual = (
        len(result.trades),
        result.winners,
        result.losers,
        result.stop_loss_closes,
        result.profit_drawdown_closes,
        result.net_profit,
    )
    assert actual[:5] == expected[:5]
    assert math.isclose(actual[5], expected[5], rel_tol=0.0, abs_tol=1e-9)
    assert not result.broker_execution_attempted


def main() -> None:
    source_30 = _load_module(
        SOURCE_30,
        "roadmap101_deferred_entry_comparison_30_for_34",
    )
    source_33 = _load_module(
        SOURCE_33,
        "roadmap101_opening_collapse_33_for_34",
    )
    original_confirmation = (
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS
    )
    assert original_confirmation == 3

    results: dict[str, WindowResult] = {}
    for window, start, end in WINDOWS:
        result = _run_window(source_30, source_33, window, start, end)
        _assert_locked(result)
        results[window] = result

    all_trades = tuple(
        trade for window, _start, _end in WINDOWS for trade in results[window].trades
    )
    winners = tuple(trade for trade in all_trades if trade.winner)
    losers = tuple(trade for trade in all_trades if trade.loser)
    remaining_sl = tuple(
        trade for trade in all_trades if trade.close_reason == "STOP_LOSS"
    )
    non_sl_losers = tuple(
        trade for trade in losers if trade.close_reason != "STOP_LOSS"
    )

    assert len(all_trades) == 26
    assert len(winners) == 14
    assert len(losers) == 12
    assert len(remaining_sl) == 5
    assert len(non_sl_losers) == 7
    actual_sl = tuple(
        (
            trade.signal_timestamp.isoformat(),
            trade.direction,
            round(trade.final_profit, 2),
        )
        for trade in remaining_sl
    )
    assert actual_sl == EXPECTED_REMAINING_SL
    assert all(trade.opening_delta_t2_t >= COLLAPSE_THRESHOLD for trade in all_trades)
    assert all(trade.active_age_bars >= 1 for trade in all_trades)
    assert all(trade.regime_age_bars >= trade.active_age_bars for trade in all_trades)
    assert all(trade.macd_search_window in {3, 5, 7} for trade in all_trades)
    assert all(trade.signal_range_ratio > 0.0 for trade in all_trades)
    assert (
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS
        == original_confirmation
    )

    print("Algorithm Workspace Alligator remaining-SL diagnostic result")
    print("  mode=DIAGNOSTIC_ONLY_D_4BAR_COLLAPSE_MINUS_0_700")
    print("  source=GREEN_ROADMAP101_33_COUNTERFACTUAL_D")
    print("  scope=VALIDATION_HOLDOUT_ACTUAL_SURVIVING_TRADES")
    print("  comparison=REMAINING_5_STOP_LOSS_vs_14_SURVIVING_WINNERS")
    print("  secondary_comparison=7_SURVIVING_NON_SL_LOSERS")
    print("  confirmation_bars=4")
    print("  opening_collapse_threshold=-0.700")
    print(
        "  entry_features=ALLIGATOR_AGE/SLOPE/OPENING_DELTAS + "
        "MACD_GEOMETRY + SIGNAL_BAR_RANGE"
    )
    print("  range_reference=MEAN_20_PREVIOUS_COMPLETED_M15_BARS")
    for window, _start, _end in WINDOWS:
        result = results[window]
        print(
            f"  {window.lower()}_d="
            f"trades:{len(result.trades)},wins:{result.winners},"
            f"losses:{result.losers},sl:{result.stop_loss_closes},"
            f"pd:{result.profit_drawdown_closes},"
            f"pnl:{result.net_profit:+.2f},"
            f"guard_rejects:{result.guard_rejections}"
        )

    print(f"  {_format_alligator_group('vh_winners', winners)}")
    print(f"  {_format_alligator_group('vh_remaining_sl', remaining_sl)}")
    print(f"  {_format_alligator_group('vh_non_sl_losers', non_sl_losers)}")
    print(f"  {_format_macd_group('vh_winners', winners)}")
    print(f"  {_format_macd_group('vh_remaining_sl', remaining_sl)}")
    print(f"  {_format_macd_group('vh_non_sl_losers', non_sl_losers)}")
    print(f"  {_format_range_group('vh_winners', winners)}")
    print(f"  {_format_range_group('vh_remaining_sl', remaining_sl)}")
    print(f"  {_format_range_group('vh_non_sl_losers', non_sl_losers)}")
    for index, trade in enumerate(remaining_sl, start=1):
        print(f"  {_format_trade(index, trade)}")

    print("  remaining_sl_count=5")
    print("  remaining_sl_total_pnl=-9.50")
    print("  mfe_mae_are_post_trade_outcome_only=True")
    print("  completed_bars_only=True")
    print("  volatility_reference_uses_prior_bars_only=True")
    print("  no_look_ahead=True")
    print("  production_trade_gate_changed=False")
    print("  production_algorithm_registration_changed=False")
    print("  production_confirmation_constant_restored=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_ALLIGATOR_REMAINING_SL_DIAGNOSTIC_CHECK=OK")


if __name__ == "__main__":
    main()
