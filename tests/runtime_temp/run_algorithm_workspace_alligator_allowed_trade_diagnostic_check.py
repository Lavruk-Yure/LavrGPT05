# -*- coding: utf-8 -*-
"""Діагностика дозволених Alligator Replay-угод RoadMap101 №31.

Тест проганяє поточний production 3-bar SAME_TIMEFRAME gate. Параметри не
змінюються. Для кожної реально відкритої virtual position збирається causal
Alligator evidence на момент MACD signal: t-2/t-1/t, normalized
slope/opening, вік ACTIVE, безперервний aligned streak і вік regime. Після
закриття додаються MFE/MAE та PnL, щоб окремо порівняти winners і losers у
Development, Validation, Holdout та об'єднаному Validation+Holdout.

MFE/MAE є post-trade outcome diagnostics. Вони не трактуються як доступний
при вході trade-gate evidence. Production algorithm, trade gate, профілі та
broker execution тест не змінює.
"""

from __future__ import annotations

import math
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import core.workspace_alligator as workspace_alligator  # noqa: E402
from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    ALLIGATOR_STATE_BEARISH,
    ALLIGATOR_STATE_BULLISH,
    WorkspaceAlligatorObservation,
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_indicator_profile import (  # noqa: E402
    new_workspace_indicator_profile_bindings,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
    WORKSPACE_REPLAY_SOURCE_CSV,
)

HISTORY_FILE = (
    PROJECT_ROOT
    / "data"
    / "history"
    / "IB"
    / "EURUSD"
    / "M1"
    / "2026-01-02_2026-08-11_IB_EURUSD_M1.csv"
)

WINDOWS = (
    (
        "DEVELOPMENT",
        "2026-01-02T00:00:00+00:00",
        "2026-02-28T00:00:00+00:00",
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

CURRENT_CONFIRMATION_BARS = 3
WIN_LOSS_TOLERANCE = 1e-12


@dataclass(frozen=True, slots=True)
class LockedWindowBaseline:
    """Зафіксований production baseline перед diagnostic №31."""

    trades: int
    winners: int
    losers: int
    stop_loss_closes: int
    profit_drawdown_closes: int
    net_profit: float


BASELINES: dict[str, LockedWindowBaseline] = {
    "DEVELOPMENT": LockedWindowBaseline(
        trades=9,
        winners=6,
        losers=3,
        stop_loss_closes=1,
        profit_drawdown_closes=8,
        net_profit=-1.06,
    ),
    "VALIDATION": LockedWindowBaseline(
        trades=21,
        winners=10,
        losers=11,
        stop_loss_closes=4,
        profit_drawdown_closes=17,
        net_profit=-3.89,
    ),
    "HOLDOUT": LockedWindowBaseline(
        trades=10,
        winners=4,
        losers=6,
        stop_loss_closes=2,
        profit_drawdown_closes=8,
        net_profit=-4.01,
    ),
}


@dataclass(frozen=True, slots=True)
class ObservationPoint:
    """Компактний causal Alligator snapshot завершеного bar."""

    timestamp: datetime
    state: str
    regime: str
    phase: str
    normalized_slope: float
    normalized_opening: float


@dataclass(frozen=True, slots=True)
class AllowedTradeDiagnostic:
    """Entry-time Alligator evidence + post-trade outcome однієї угоди."""

    window: str
    signal_uid: str
    signal_timestamp: datetime
    entry_timestamp: datetime
    close_timestamp: datetime
    direction: str
    close_reason: str
    final_profit: float
    maximum_favorable_excursion: float
    maximum_adverse_excursion: float
    active_age_bars: int
    aligned_streak_bars: int
    regime_age_bars: int
    direction_stable_2: bool
    direction_stable_3: bool
    t_minus_2: ObservationPoint
    t_minus_1: ObservationPoint
    current: ObservationPoint

    @property
    def winner(self) -> bool:
        return self.final_profit > WIN_LOSS_TOLERANCE

    @property
    def loser(self) -> bool:
        return self.final_profit < -WIN_LOSS_TOLERANCE


@dataclass(frozen=True, slots=True)
class Aggregate:
    """Статистика entry evidence та outcome diagnostics."""

    count: int
    active_age_average: float
    active_age_median: float
    aligned_streak_average: float
    regime_age_average: float
    normalized_slope_average: float
    normalized_opening_average: float
    slope_change_t_minus_2_to_t_average: float
    opening_change_t_minus_2_to_t_average: float
    maximum_favorable_excursion_average: float
    maximum_adverse_excursion_average: float
    direction_stable_2_count: int
    direction_stable_3_count: int


@dataclass(frozen=True, slots=True)
class WindowResult:
    """Replay window з діагностикою дозволених угод."""

    window: str
    trades: tuple[AllowedTradeDiagnostic, ...]
    winners: int
    losers: int
    stop_loss_closes: int
    profit_drawdown_closes: int
    net_profit: float
    all_signal_records: int
    alligator_observations: int
    broker_execution_attempted: bool


def _workspace(start_utc: str, end_utc: str) -> AlgorithmWorkspace:
    """Побудувати незмінний RM96 EURUSD M15 Historical WSP."""
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id=None,
        account_mode=None,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        display_name="RM96 Alligator Allowed Trade Diagnostic",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        parameters={
            "macd_signal_enabled": True,
            "macd_signal_mode": "EXTENDED",
            "alligator_filter_enabled": True,
            "alligator_confirmation": WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
            "spread_limit": 0.00020,
            "warmup_bars": 3,
            "macd_extremum_min_prominence": 0.000015,
            "macd_extremum_to_cross_min_distance": 0.000050,
            "macd_cross_min_angle": 45.0,
            "macd_cross_angle_model": "ABC_REALTIME_SCALED",
            "macd_cross_min_abc_angle": 2.25,
        },
        risk_settings={
            "risk_percent": 0.5,
            "maximum_position_volume": 1000.0,
            "maximum_open_positions": 2,
            "max_daily_loss_percent": 2.0,
            "require_stop_loss": True,
        },
        profit_protection={
            "enabled": True,
            "activation_mode": "AFTER_SPREAD",
            "max_profit_drawdown_percent": 30.0,
            "minimum_profit": 0.0,
        },
        replay_settings={
            "source_type": WORKSPACE_REPLAY_SOURCE_CSV,
            "file_path": str(HISTORY_FILE),
            "start_utc": start_utc,
            "end_utc": end_utc,
            "source_timezone": "UTC",
            "delimiter": "AUTO",
            "decimal_separator": ".",
            "spread": 0.00012,
            "source": "2026-01-02_2026-08-11_IB_EURUSD_M1",
            "source_timeframe": "M1",
            "risk_equity": 1000.0,
            "speed": -1,
        },
        indicator_profile_bindings=new_workspace_indicator_profile_bindings(),
    )


def _direction_signature(direction: str) -> tuple[str, str]:
    """Повернути causal regime/state для BUY або SELL."""
    if direction == "BUY":
        return ALLIGATOR_REGIME_TREND_UP, ALLIGATOR_STATE_BULLISH
    if direction == "SELL":
        return ALLIGATOR_REGIME_TREND_DOWN, ALLIGATOR_STATE_BEARISH
    raise AssertionError(f"Unexpected direction: {direction}")


def _observation_point(observation: WorkspaceAlligatorObservation) -> ObservationPoint:
    """Нормалізувати observation для test output."""
    assert observation.normalized_slope is not None
    assert observation.normalized_opening is not None
    return ObservationPoint(
        timestamp=observation.timestamp,
        state=observation.state,
        regime=observation.regime,
        phase=observation.regime_phase,
        normalized_slope=observation.normalized_slope,
        normalized_opening=observation.normalized_opening,
    )


def _consecutive_count(
    observations: tuple[WorkspaceAlligatorObservation, ...],
    current_index: int,
    predicate,
) -> int:
    """Порахувати causal streak назад від observation."""
    count = 0
    for index in range(current_index, -1, -1):
        if not predicate(observations[index]):
            break
        count += 1
    return count


def _trade_diagnostic(
    *,
    window: str,
    trade,
    record: WorkspaceSignalRecord,
    observations: tuple[WorkspaceAlligatorObservation, ...],
    observation_index: int,
) -> AllowedTradeDiagnostic:
    """З'єднати immutable signal, Alligator history та closed trade."""
    context = record.filter_context
    assert context is not None
    current = observations[observation_index]
    regime, state = _direction_signature(trade.direction)

    assert record.accepted
    assert record.filter_decision == "ALLOW"
    assert context.regime == regime
    assert context.regime_phase == ALLIGATOR_REGIME_PHASE_ACTIVE
    assert current.regime == regime
    assert current.state == state
    assert current.regime_phase == ALLIGATOR_REGIME_PHASE_ACTIVE
    assert current.timestamp == context.observation_timestamp
    assert current.available_at <= record.timestamp
    assert current.timestamp <= record.timestamp
    assert observation_index >= 2

    active_age_bars = _consecutive_count(
        observations,
        observation_index,
        lambda item: bool(
            item.regime == regime
            and item.state == state
            and item.regime_phase == ALLIGATOR_REGIME_PHASE_ACTIVE
        ),
    )
    aligned_streak_bars = _consecutive_count(
        observations,
        observation_index,
        lambda item: bool(item.regime == regime and item.state == state),
    )
    regime_age_bars = _consecutive_count(
        observations,
        observation_index,
        lambda item: item.regime == regime,
    )

    history = observations[observation_index - 2 : observation_index + 1]  # noqa
    assert len(history) == 3
    assert history[0].timestamp < history[1].timestamp < history[2].timestamp
    direction_stable_2 = all(
        item.regime == regime and item.state == state for item in history[-2:]
    )
    direction_stable_3 = all(
        item.regime == regime and item.state == state for item in history
    )

    return AllowedTradeDiagnostic(
        window=window,
        signal_uid=trade.signal_uid,
        signal_timestamp=trade.signal_timestamp,
        entry_timestamp=trade.entry_timestamp,
        close_timestamp=trade.close_timestamp,
        direction=trade.direction,
        close_reason=trade.close_reason,
        final_profit=trade.final_profit,
        maximum_favorable_excursion=trade.maximum_favorable_excursion,
        maximum_adverse_excursion=trade.maximum_adverse_excursion,
        active_age_bars=active_age_bars,
        aligned_streak_bars=aligned_streak_bars,
        regime_age_bars=regime_age_bars,
        direction_stable_2=direction_stable_2,
        direction_stable_3=direction_stable_3,
        t_minus_2=_observation_point(history[0]),
        t_minus_1=_observation_point(history[1]),
        current=_observation_point(history[2]),
    )


def _run(window: str, start_utc: str, end_utc: str) -> WindowResult:
    """Виконати 3-bar Replay і зібрати diagnostic evidence."""
    runtime = WorkspaceRuntime(
        _workspace(start_utc, end_utc),
        algorithm_factory=create_registered_workspace_algorithm,
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
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    signal_filter = algorithm.signal_filter
    assert signal_filter is not None

    observations = signal_filter.observations
    observation_index_by_timestamp = {
        observation.timestamp: index for index, observation in enumerate(observations)
    }
    records = runtime.signal_records()
    record_by_uid = {record.signal_uid: record for record in records}
    diagnostics = execution.trade_diagnostics()

    trades: list[AllowedTradeDiagnostic] = []
    for trade in diagnostics:
        record = record_by_uid.get(trade.signal_uid)
        assert record is not None
        context = record.filter_context
        assert context is not None
        assert context.observation_timestamp is not None
        observation_index = observation_index_by_timestamp.get(
            context.observation_timestamp
        )
        assert observation_index is not None
        trades.append(
            _trade_diagnostic(
                window=window,
                trade=trade,
                record=record,
                observations=observations,
                observation_index=observation_index,
            )
        )

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )

    return WindowResult(
        window=window,
        trades=tuple(trades),
        winners=summary.winning_trades,
        losers=summary.losing_trades,
        stop_loss_closes=summary.close_reason_count("STOP_LOSS"),
        profit_drawdown_closes=summary.close_reason_count("PROFIT_DRAWDOWN"),
        net_profit=summary.net_profit,
        all_signal_records=len(records),
        alligator_observations=len(observations),
        broker_execution_attempted=broker_execution_attempted,
    )


def _aggregate(trades: tuple[AllowedTradeDiagnostic, ...]) -> Aggregate:
    """Побудувати entry/outcome агрегат для subset."""
    assert trades
    return Aggregate(
        count=len(trades),
        active_age_average=statistics.fmean(trade.active_age_bars for trade in trades),
        active_age_median=statistics.median(trade.active_age_bars for trade in trades),
        aligned_streak_average=statistics.fmean(
            trade.aligned_streak_bars for trade in trades
        ),
        regime_age_average=statistics.fmean(trade.regime_age_bars for trade in trades),
        normalized_slope_average=statistics.fmean(
            trade.current.normalized_slope for trade in trades
        ),
        normalized_opening_average=statistics.fmean(
            trade.current.normalized_opening for trade in trades
        ),
        slope_change_t_minus_2_to_t_average=statistics.fmean(
            trade.current.normalized_slope - trade.t_minus_2.normalized_slope
            for trade in trades
        ),
        opening_change_t_minus_2_to_t_average=statistics.fmean(
            trade.current.normalized_opening - trade.t_minus_2.normalized_opening
            for trade in trades
        ),
        maximum_favorable_excursion_average=statistics.fmean(
            trade.maximum_favorable_excursion for trade in trades
        ),
        maximum_adverse_excursion_average=statistics.fmean(
            trade.maximum_adverse_excursion for trade in trades
        ),
        direction_stable_2_count=sum(trade.direction_stable_2 for trade in trades),
        direction_stable_3_count=sum(trade.direction_stable_3 for trade in trades),
    )


def _outcome_subsets(
    trades: tuple[AllowedTradeDiagnostic, ...],
) -> tuple[tuple[AllowedTradeDiagnostic, ...], tuple[AllowedTradeDiagnostic, ...]]:
    """Розділити угоди на winners/losers за historical tolerance."""
    winners = tuple(trade for trade in trades if trade.winner)
    losers = tuple(trade for trade in trades if trade.loser)
    assert len(winners) + len(losers) == len(trades)
    return winners, losers


def _short_state(value: str) -> str:
    return value.removeprefix("ALLIGATOR_")


def _short_regime(value: str) -> str:
    return value.removeprefix("ALLIGATOR_REGIME_")


def _short_phase(value: str) -> str:
    return value.removeprefix("ALLIGATOR_REGIME_PHASE_")


def _format_point(point: ObservationPoint) -> str:
    """Компактно вивести один t-n snapshot."""
    return (
        f"{_short_regime(point.regime)}/{_short_phase(point.phase)}/"
        f"{_short_state(point.state)}:"
        f"s={point.normalized_slope:.6f},o={point.normalized_opening:.6f}"
    )


def _format_trade(index: int, trade: AllowedTradeDiagnostic) -> str:
    """One-line evidence однієї дозволеної угоди."""
    outcome = "WIN" if trade.winner else "LOSS"
    return (
        f"{trade.window.lower()}_trade_{index:02d}="
        f"{trade.signal_timestamp.isoformat()} {trade.direction} {outcome} "
        f"{trade.close_reason} pnl:{trade.final_profit:+.2f},"
        f"active_age:{trade.active_age_bars},"
        f"aligned:{trade.aligned_streak_bars},"
        f"regime_age:{trade.regime_age_bars},"
        f"stable2:{trade.direction_stable_2},"
        f"stable3:{trade.direction_stable_3},"
        f"mfe:{trade.maximum_favorable_excursion:+.2f},"
        f"mae:{trade.maximum_adverse_excursion:+.2f},"
        f"t-2[{_format_point(trade.t_minus_2)}],"
        f"t-1[{_format_point(trade.t_minus_1)}],"
        f"t[{_format_point(trade.current)}]"
    )


def _format_aggregate(aggregate: Aggregate) -> str:
    """Вивести aggregate без змішування entry й outcome."""
    return (
        f"count:{aggregate.count},"
        f"active_avg:{aggregate.active_age_average:.2f},"
        f"active_med:{aggregate.active_age_median:.2f},"
        f"aligned_avg:{aggregate.aligned_streak_average:.2f},"
        f"regime_age_avg:{aggregate.regime_age_average:.2f},"
        f"slope_avg:{aggregate.normalized_slope_average:.6f},"
        f"opening_avg:{aggregate.normalized_opening_average:.6f},"
        f"slope_t2_to_t:{aggregate.slope_change_t_minus_2_to_t_average:+.6f},"
        f"opening_t2_to_t:{aggregate.opening_change_t_minus_2_to_t_average:+.6f},"
        f"mfe_avg:{aggregate.maximum_favorable_excursion_average:+.3f},"
        f"mae_avg:{aggregate.maximum_adverse_excursion_average:+.3f},"
        f"stable2:{aggregate.direction_stable_2_count}/{aggregate.count},"
        f"stable3:{aggregate.direction_stable_3_count}/{aggregate.count}"
    )


def _assert_baseline(result: WindowResult) -> None:
    """Перевірити незмінність production Replay result."""
    expected = BASELINES[result.window]
    assert len(result.trades) == expected.trades
    assert result.winners == expected.winners
    assert result.losers == expected.losers
    assert result.stop_loss_closes == expected.stop_loss_closes
    assert result.profit_drawdown_closes == expected.profit_drawdown_closes
    assert math.isclose(
        result.net_profit,
        expected.net_profit,
        rel_tol=0.0,
        abs_tol=1e-9,
    )
    assert not result.broker_execution_attempted


def main() -> None:
    original_confirmation = (
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS
    )
    assert original_confirmation == CURRENT_CONFIRMATION_BARS

    results: dict[str, WindowResult] = {}
    for window, start_utc, end_utc in WINDOWS:
        result = _run(window, start_utc, end_utc)
        _assert_baseline(result)
        results[window] = result

    all_trades = tuple(
        trade
        for window, _start_utc, _end_utc in WINDOWS
        for trade in results[window].trades
    )
    validation_holdout = (
        *results["VALIDATION"].trades,
        *results["HOLDOUT"].trades,
    )
    vh_winners, vh_losers = _outcome_subsets(validation_holdout)
    vh_winner_aggregate = _aggregate(vh_winners)
    vh_loser_aggregate = _aggregate(vh_losers)

    assert len(all_trades) == 40
    assert len(validation_holdout) == 31
    assert len(vh_winners) == 14
    assert len(vh_losers) == 17
    assert all(trade.direction_stable_2 for trade in all_trades)
    assert all(trade.direction_stable_3 for trade in all_trades)
    assert all(trade.active_age_bars >= 1 for trade in all_trades)
    assert all(trade.aligned_streak_bars >= 3 for trade in all_trades)
    assert all(
        trade.t_minus_2.timestamp
        < trade.t_minus_1.timestamp
        < trade.current.timestamp
        <= trade.signal_timestamp
        for trade in all_trades
    )
    assert (
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS
        == original_confirmation
    )

    print("Algorithm Workspace Alligator allowed-trade diagnostic result")
    print("  mode=DIAGNOSTIC_ONLY_CURRENT_3BAR_PRODUCTION_GATE")
    print("  scope=EVERY_ACTUAL_REPLAY_TRADE_DEVELOPMENT_VALIDATION_HOLDOUT")
    print("  fixed_workspace=RM96 EURUSD M15 Historical")
    print(
        "  fixed_macd=8/17/5 EXTENDED prominence=0.000015 " "distance=0.000050 ABC=2.25"
    )
    print(
        "  fixed_alligator=13/8,8/5,5/3 SMOOTHED MEDIAN "
        "SAME_TIMEFRAME confirmation_bars=3"
    )
    print(
        "  entry_observables=active_age/aligned_streak/regime_age/"
        "normalized_slope/normalized_opening/t-2/t-1/t"
    )
    print("  post_trade_outcomes=PnL/MFE/MAE/close_reason")
    for window, _start_utc, _end_utc in WINDOWS:
        result = results[window]
        winners, losers = _outcome_subsets(result.trades)
        print(
            f"  {window.lower()}_baseline="
            f"trades:{len(result.trades)},wins:{result.winners},"
            f"losses:{result.losers},sl:{result.stop_loss_closes},"
            f"pd:{result.profit_drawdown_closes},pnl:{result.net_profit:.2f},"
            f"signals:{result.all_signal_records},"
            f"alligator_observations:{result.alligator_observations}"
        )
        print(f"  {window.lower()}_winners={_format_aggregate(_aggregate(winners))}")
        print(f"  {window.lower()}_losers={_format_aggregate(_aggregate(losers))}")
        for index, trade in enumerate(result.trades, start=1):
            print(f"  {_format_trade(index, trade)}")

    print("  validation_holdout_winners=" f"{_format_aggregate(vh_winner_aggregate)}")
    print("  validation_holdout_losers=" f"{_format_aggregate(vh_loser_aggregate)}")
    active_delta = (
        vh_loser_aggregate.active_age_average - vh_winner_aggregate.active_age_average
    )
    aligned_delta = (
        vh_loser_aggregate.aligned_streak_average
        - vh_winner_aggregate.aligned_streak_average
    )
    regime_age_delta = (
        vh_loser_aggregate.regime_age_average - vh_winner_aggregate.regime_age_average
    )
    slope_delta = (
        vh_loser_aggregate.normalized_slope_average
        - vh_winner_aggregate.normalized_slope_average
    )
    opening_delta = (
        vh_loser_aggregate.normalized_opening_average
        - vh_winner_aggregate.normalized_opening_average
    )
    print(
        "  validation_holdout_loser_minus_winner_entry_delta="
        f"active_avg:{active_delta:+.2f},"
        f"aligned_avg:{aligned_delta:+.2f},"
        f"regime_age_avg:{regime_age_delta:+.2f},"
        f"slope_avg:{slope_delta:+.6f},"
        f"opening_avg:{opening_delta:+.6f}"
    )
    print(
        "  validation_holdout_direction_stability="
        "stable2:31/31,stable3:31/31,"
        "not_discriminating_under_current_phase_gate=True"
    )
    print("  mfe_mae_are_post_trade_outcome_not_entry_gate_evidence=True")
    print("  completed_bars_only=True")
    print("  no_look_ahead=True")
    print("  production_trade_gate_changed=False")
    print("  production_algorithm_registration_changed=False")
    print("  production_confirmation_constant_unchanged=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_ALLIGATOR_ALLOWED_TRADE_DIAGNOSTIC_CHECK=OK")


if __name__ == "__main__":
    main()
