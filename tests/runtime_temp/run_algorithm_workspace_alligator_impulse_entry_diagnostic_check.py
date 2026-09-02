# -*- coding: utf-8 -*-
"""Impulse/exhaustion entry diagnostic після GREEN RoadMap101 №35.

Тест виконує рівно один combined Replay для Development, Validation і Holdout:
4-bar Alligator + opening-collapse -0.700 + три structural guards із №35.
Для кожної фактично surviving угоди збирає тільки causal entry-time evidence.

Додатково до Alligator/MACD/range evidence №34 обчислюються форма signal bar,
положення close всередині bar, directional body, directional move від
попереднього close та за три bars, а також range×MACD angle і
range×MACD steepness. Усі reference bars завершені до signal timestamp.

Мета — перевірити, чи великий SL 2026-04-21 19:30 SELL належить до окремого
класу "entry after impulse", чи подібні entry-time ознаки мають і winners.
Другий remaining SL 2026-03-06 21:00 BUY використовується як контрольний.
Жоден metric не перетворюється на trade gate; MFE/MAE — лише outcome.
Production trade gate, registration, профілі та broker execution не змінює.
"""

from __future__ import annotations

import importlib.util
import math
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import core.workspace_alligator as workspace_alligator  # noqa: E402
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402

SOURCE_30 = Path(__file__).with_name(
    "run_algorithm_workspace_macd_deferred_alligator_entry_comparison_check.py"
)
SOURCE_33 = Path(__file__).with_name(
    "run_algorithm_workspace_alligator_opening_collapse_counterfactual_check.py"
)
SOURCE_34 = Path(__file__).with_name(
    "run_algorithm_workspace_alligator_remaining_sl_diagnostic_check.py"
)
SOURCE_35 = Path(__file__).with_name(
    "run_algorithm_workspace_alligator_structural_guard_counterfactual_check.py"
)

WINDOWS = (
    (
        "DEVELOPMENT",
        "2026-01-02T00:00:00+00:00",
        "2026-02-28T23:59:00+00:00",
    ),
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
WIN_LOSS_TOLERANCE = 1e-12
TARGET_IMPULSE_TIMESTAMP = "2026-04-21T19:30:00+00:00"
TARGET_CONTROL_TIMESTAMP = "2026-03-06T21:00:00+00:00"

LOCKED_COMBINED_RESULTS = {
    "DEVELOPMENT": (6, 5, 1, 0, 6, 1.03),
    "VALIDATION": (16, 10, 6, 2, 14, -1.03),
    "HOLDOUT": (7, 4, 3, 0, 7, 0.11),
}


@dataclass(frozen=True, slots=True)
class ImpulseEvidence:
    """Causal impulse evidence однієї surviving combined угоди."""

    base: Any
    signal_open: float
    signal_high: float
    signal_low: float
    signal_close: float
    body_ratio: float
    directional_body_ratio: float
    directional_close_location: float
    one_bar_directional_move_ratio: float
    three_bar_directional_move_ratio: float
    three_bar_path_efficiency: float
    range_angle_product: float
    range_steepness_product: float

    @property
    def winner(self) -> bool:
        return self.base.final_profit > WIN_LOSS_TOLERANCE

    @property
    def loser(self) -> bool:
        return self.base.final_profit < -WIN_LOSS_TOLERANCE

    @property
    def stop_loss(self) -> bool:
        return self.base.close_reason == "STOP_LOSS"


@dataclass(frozen=True, slots=True)
class WindowResult:
    """Combined Replay metrics + surviving impulse evidence."""

    window: str
    trades: tuple[ImpulseEvidence, ...]
    winners: int
    losers: int
    stop_loss_closes: int
    profit_drawdown_closes: int
    net_profit: float
    broker_execution_attempted: bool


@dataclass(frozen=True, slots=True)
class MetricSummary:
    """Mean/median/min/max одного diagnostic metric."""

    mean: float
    median: float
    minimum: float
    maximum: float


def _load_module(path: Path, module_name: str):
    """Завантажити sibling GREEN test без tests package dependency."""
    assert path.is_file(), path
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _direction_sign(direction: str) -> float:
    if direction == "BUY":
        return 1.0
    if direction == "SELL":
        return -1.0
    raise AssertionError(direction)


def _build_impulse_evidence(
    base,
    session,
) -> ImpulseEvidence:
    """Додати causal signal-bar/impulse features до evidence №34."""
    index_by_timestamp = {
        event.timestamp: index for index, event in enumerate(session.events)
    }
    index = index_by_timestamp.get(base.signal_timestamp)
    assert index is not None
    assert index >= 3

    event = session.events[index]
    previous = session.events[index - 1]
    three_back = session.events[index - 3]
    recent = session.events[index - 2 : index + 1]  # noqa
    assert len(recent) == 3
    assert three_back.timestamp < previous.timestamp < event.timestamp
    assert all(item.timestamp <= event.timestamp for item in recent)

    signal_range = float(event.high - event.low)
    assert signal_range > 0.0
    assert math.isclose(
        signal_range,
        base.signal_bar_range,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    prior_average = float(base.prior_range_average)
    assert prior_average > 0.0

    body = float(event.close - event.open)
    body_ratio = abs(body) / signal_range
    sign = _direction_sign(base.direction)
    directional_body_ratio = sign * body / signal_range
    close_location = float(event.close - event.low) / signal_range
    directional_close_location = close_location if sign > 0.0 else 1.0 - close_location

    one_bar_move = sign * float(event.close - previous.close)
    three_bar_move = sign * float(event.close - three_back.close)
    one_bar_ratio = one_bar_move / prior_average
    three_bar_ratio = three_bar_move / prior_average
    path = sum(abs(float(item.close - item.open)) for item in recent)
    if path <= 1e-15:
        path_efficiency = 0.0
    else:
        path_efficiency = max(-1.0, min(1.0, three_bar_move / path))

    return ImpulseEvidence(
        base=base,
        signal_open=float(event.open),
        signal_high=float(event.high),
        signal_low=float(event.low),
        signal_close=float(event.close),
        body_ratio=body_ratio,
        directional_body_ratio=directional_body_ratio,
        directional_close_location=directional_close_location,
        one_bar_directional_move_ratio=one_bar_ratio,
        three_bar_directional_move_ratio=three_bar_ratio,
        three_bar_path_efficiency=path_efficiency,
        range_angle_product=(base.signal_range_ratio * base.macd_effective_angle),
        range_steepness_product=(
            base.signal_range_ratio * base.macd_crossover_steepness
        ),
    )


def _run_window(
    source_30,
    source_33,
    source_34,
    source_35,
    window: str,
    start: str,
    end: str,
) -> WindowResult:
    """Виконати один GREEN №35 combined Replay з extra evidence."""
    original = workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS
    workspace_factory = getattr(source_30, "_workspace")
    quality_map = getattr(source_34, "_quality_map")
    build_base_evidence = getattr(source_34, "_build_evidence")
    guarded_factory = getattr(source_35, "_guarded_class")
    guarded_class = guarded_factory(source_33)

    def algorithm_factory(algorithm_id: str):
        return guarded_class(algorithm_id)

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
        assert algorithm is not None
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
        diagnostics = quality_map(macd_source)

        trades: list[ImpulseEvidence] = []
        for trade in execution.trade_diagnostics():
            record = record_by_uid.get(trade.signal_uid)
            assert record is not None
            context = record.filter_context
            assert context is not None
            assert context.observation_timestamp is not None
            obs_index = observation_index.get(context.observation_timestamp)
            assert obs_index is not None
            quality = diagnostics.get((record.timestamp, record.direction))
            assert quality is not None
            base = build_base_evidence(
                window=window,
                trade=trade,
                record=record,
                observations=observations,
                observation_index=obs_index,
                quality_diagnostic=quality,
                session=session,
            )
            trades.append(_build_impulse_evidence(base, session))

        broker_execution_attempted = any(
            bool(entry.details.get("broker_execution_attempted"))
            for entry in runtime.journal
            if isinstance(entry.details, dict)
        )
        assert not broker_execution_attempted
        return WindowResult(
            window=window,
            trades=tuple(trades),
            winners=summary.winning_trades,
            losers=summary.losing_trades,
            stop_loss_closes=summary.close_reason_count("STOP_LOSS"),
            profit_drawdown_closes=summary.close_reason_count("PROFIT_DRAWDOWN"),
            net_profit=summary.net_profit,
            broker_execution_attempted=broker_execution_attempted,
        )
    finally:
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS = original


def _summary(
    trades: tuple[ImpulseEvidence, ...],
    getter: Callable[[ImpulseEvidence], float],
) -> MetricSummary:
    values = tuple(float(getter(trade)) for trade in trades)
    assert values
    return MetricSummary(
        mean=statistics.fmean(values),
        median=statistics.median(values),
        minimum=min(values),
        maximum=max(values),
    )


def _format_metric(summary: MetricSummary, digits: int) -> str:
    return (
        f"avg:{summary.mean:.{digits}f},med:{summary.median:.{digits}f},"
        f"range:{summary.minimum:.{digits}f}..{summary.maximum:.{digits}f}"
    )


def _format_group(name: str, trades: tuple[ImpulseEvidence, ...]) -> str:
    """Агрегувати impulse metrics для winners/losers/SL."""
    range_ratio = _summary(trades, lambda item: item.base.signal_range_ratio)
    angle = _summary(trades, lambda item: item.base.macd_effective_angle)
    range_angle = _summary(trades, lambda item: item.range_angle_product)
    body = _summary(trades, lambda item: item.body_ratio)
    dir_body = _summary(trades, lambda item: item.directional_body_ratio)
    close_loc = _summary(
        trades,
        lambda item: item.directional_close_location,
    )
    move1 = _summary(
        trades,
        lambda item: item.one_bar_directional_move_ratio,
    )
    move3 = _summary(
        trades,
        lambda item: item.three_bar_directional_move_ratio,
    )
    path = _summary(trades, lambda item: item.three_bar_path_efficiency)
    return (
        f"{name}=range_ratio[{_format_metric(range_ratio, 3)}];"
        f"angle[{_format_metric(angle, 2)}];"
        f"range_x_angle[{_format_metric(range_angle, 3)}];"
        f"body_ratio[{_format_metric(body, 3)}];"
        f"dir_body[{_format_metric(dir_body, 3)}];"
        f"dir_close[{_format_metric(close_loc, 3)}];"
        f"move1[{_format_metric(move1, 3)}];"
        f"move3[{_format_metric(move3, 3)}];"
        f"path_eff[{_format_metric(path, 3)}]"
    )


def _format_trade(trade: ImpulseEvidence) -> str:
    base = trade.base
    return (
        f"{base.signal_timestamp.isoformat()} {base.direction} "
        f"{base.close_reason} pnl:{base.final_profit:+.2f},"
        f"range_ratio:{base.signal_range_ratio:.3f},"
        f"angle:{base.macd_effective_angle:.2f},"
        f"range_x_angle:{trade.range_angle_product:.3f},"
        f"range_x_steep:{trade.range_steepness_product:.8f},"
        f"body:{trade.body_ratio:.3f},"
        f"dir_body:{trade.directional_body_ratio:+.3f},"
        f"dir_close:{trade.directional_close_location:.3f},"
        f"move1:{trade.one_bar_directional_move_ratio:+.3f},"
        f"move3:{trade.three_bar_directional_move_ratio:+.3f},"
        f"path_eff:{trade.three_bar_path_efficiency:+.3f},"
        f"active:{base.active_age_bars},"
        f"opening:{base.normalized_opening:.6f},"
        f"opening_d:{base.opening_delta_t2_t:+.6f},"
        f"slope:{base.normalized_slope:.6f},"
        f"slope_d:{base.slope_delta_t2_t:+.6f}"
    )


def _top_trades(
    trades: tuple[ImpulseEvidence, ...],
    getter: Callable[[ImpulseEvidence], float],
    limit: int = 5,
) -> tuple[ImpulseEvidence, ...]:
    return tuple(sorted(trades, key=getter, reverse=True)[:limit])


def _format_ranked(trades: tuple[ImpulseEvidence, ...]) -> str:
    return "; ".join(
        f"{trade.base.signal_timestamp.isoformat()} {trade.base.direction} "
        f"{trade.base.close_reason} pnl:{trade.base.final_profit:+.2f}"
        for trade in trades
    )


def _winner_percentile(
    value: float,
    winners: tuple[ImpulseEvidence, ...],
    getter: Callable[[ImpulseEvidence], float],
) -> float:
    values = sorted(float(getter(item)) for item in winners)
    assert values
    less_or_equal = sum(1 for item in values if item <= value)
    return 100.0 * less_or_equal / len(values)


def _format_target_percentiles(
    name: str,
    trade: ImpulseEvidence,
    winners: tuple[ImpulseEvidence, ...],
) -> str:
    metrics = (
        (
            "range_ratio",
            trade.base.signal_range_ratio,
            lambda item: item.base.signal_range_ratio,
        ),
        (
            "angle",
            trade.base.macd_effective_angle,
            lambda item: item.base.macd_effective_angle,
        ),
        (
            "range_x_angle",
            trade.range_angle_product,
            lambda item: item.range_angle_product,
        ),
        ("body", trade.body_ratio, lambda item: item.body_ratio),
        (
            "dir_close",
            trade.directional_close_location,
            lambda item: item.directional_close_location,
        ),
        (
            "move1",
            trade.one_bar_directional_move_ratio,
            lambda item: item.one_bar_directional_move_ratio,
        ),
        (
            "move3",
            trade.three_bar_directional_move_ratio,
            lambda item: item.three_bar_directional_move_ratio,
        ),
    )
    parts = []
    for metric_name, value, getter in metrics:
        percentile = _winner_percentile(value, winners, getter)
        parts.append(f"{metric_name}:{percentile:.1f}pct")
    return f"{name}_vs_winner_percentiles=" + ",".join(parts)


def _assert_locked(result: WindowResult) -> None:
    expected = LOCKED_COMBINED_RESULTS[result.window]
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
        "roadmap101_deferred_entry_comparison_30_for_36",
    )
    source_33 = _load_module(
        SOURCE_33,
        "roadmap101_opening_collapse_33_for_36",
    )
    source_34 = _load_module(
        SOURCE_34,
        "roadmap101_remaining_sl_34_for_36",
    )
    source_35 = _load_module(
        SOURCE_35,
        "roadmap101_structural_guard_35_for_36",
    )
    original_confirmation = (
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS
    )
    assert original_confirmation == 3

    results = []
    for window, start, end in WINDOWS:
        result = _run_window(
            source_30,
            source_33,
            source_34,
            source_35,
            window,
            start,
            end,
        )
        _assert_locked(result)
        results.append(result)

    assert (
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS
        == original_confirmation
    )

    all_trades = tuple(trade for result in results for trade in result.trades)
    winners = tuple(trade for trade in all_trades if trade.winner)
    stop_losses = tuple(trade for trade in all_trades if trade.stop_loss)
    non_sl_losers = tuple(
        trade for trade in all_trades if trade.loser and not trade.stop_loss
    )
    assert len(all_trades) == 29
    assert len(winners) == 19
    assert len(stop_losses) == 2
    assert len(non_sl_losers) == 8

    targets = {trade.base.signal_timestamp.isoformat(): trade for trade in stop_losses}
    impulse_target = targets.get(TARGET_IMPULSE_TIMESTAMP)
    control_target = targets.get(TARGET_CONTROL_TIMESTAMP)
    assert impulse_target is not None
    assert control_target is not None

    print("Algorithm Workspace Alligator impulse-entry diagnostic result")
    print("  mode=DIAGNOSTIC_ONLY_GREEN_35_COMBINED_SURVIVING_TRADES")
    print("  baseline=4BAR+COLLAPSE_-0.700+STRUCTURAL_GUARDS")
    print("  scope=DEVELOPMENT_VALIDATION_HOLDOUT_SURVIVING_TRADES")
    print(
        "  features=SIGNAL_BAR_SHAPE/CLOSE_LOCATION/1BAR_3BAR_MOVE/"
        "RANGE_X_MACD_ANGLE/RANGE_X_STEEPNESS"
    )
    print("  price_normalization=MEAN_20_PREVIOUS_COMPLETED_M15_RANGES")
    print("  diagnostic_only_no_new_thresholds=True")
    for result in results:
        print(
            f"  {result.window.lower()}_combined="
            f"trades:{len(result.trades)},wins:{result.winners},"
            f"losses:{result.losers},sl:{result.stop_loss_closes},"
            f"pd:{result.profit_drawdown_closes},"
            f"pnl:{result.net_profit:+.2f}"
        )

    print(f"  surviving_total={len(all_trades)}")
    print(f"  surviving_winners={len(winners)}")
    print(f"  surviving_stop_losses={len(stop_losses)}")
    print(f"  surviving_non_sl_losers={len(non_sl_losers)}")
    print("  " + _format_group("winners", winners))
    print("  " + _format_group("stop_losses", stop_losses))
    print("  " + _format_group("non_sl_losers", non_sl_losers))

    print("  target_impulse=" + _format_trade(impulse_target))
    print("  target_control=" + _format_trade(control_target))
    print(
        "  "
        + _format_target_percentiles(
            "target_impulse",
            impulse_target,
            winners,
        )
    )
    print(
        "  "
        + _format_target_percentiles(
            "target_control",
            control_target,
            winners,
        )
    )

    ranked_metrics = (
        (
            "top_range_ratio",
            lambda item: item.base.signal_range_ratio,
        ),
        ("top_range_x_angle", lambda item: item.range_angle_product),
        (
            "top_range_x_steepness",
            lambda item: item.range_steepness_product,
        ),
        (
            "top_directional_move1",
            lambda item: item.one_bar_directional_move_ratio,
        ),
        (
            "top_directional_move3",
            lambda item: item.three_bar_directional_move_ratio,
        ),
        (
            "top_directional_close_location",
            lambda item: item.directional_close_location,
        ),
    )
    for name, getter in ranked_metrics:
        print(f"  {name}=" f"{_format_ranked(_top_trades(all_trades, getter))}")

    print("  mfe_mae_not_used_as_entry_features=True")
    print("  signal_bar_and_history_completed_only=True")
    print("  volatility_reference_excludes_signal_bar=True")
    print("  no_look_ahead=True")
    print("  production_trade_gate_changed=False")
    print("  production_algorithm_registration_changed=False")
    print("  production_confirmation_constant_restored=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_ALLIGATOR_IMPULSE_ENTRY_DIAGNOSTIC_CHECK=OK")


if __name__ == "__main__":
    main()
