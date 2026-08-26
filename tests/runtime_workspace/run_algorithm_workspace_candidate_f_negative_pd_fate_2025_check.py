# -*- coding: utf-8 -*-
"""RoadMap102 / 6D: fate diagnostic для negative Profit Drawdown OOS 2025.

Runner повторює frozen Candidate F Replay 2025 і бере тільки 18 production
позицій, які були закриті через PROFIT_DRAWDOWN з від'ємним realized PnL.
Після фактичного production close він read-only продовжує ціновий шлях кожної
такої позиції до першого початкового SL/TP або до кінця OOS, не створюючи
counterfactual trades/exits у Runtime.

Окремо фіксується causal стан, доступний саме на production PD close: остання
завершена Alligator observation, slope/opening та їх зміни, а також cumulative
price move останніх 1/2/3 завершених M15 bars у напрямку позиції. Post-close
future використовується тільки як diagnostic label/fate, ніколи як exit gate.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean, median

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, TEST_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    FrozenOosRuntime,
    assert_frozen_oos_snapshot,
    frozen_oos_workspace,
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
from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402

M15_SECONDS = 15 * 60
NUMERIC_EPSILON = 1e-9
RECOVERY_LEVELS_R = (0.0, 0.10, 0.20, 0.30)
FATE_PREMATURE = "EARLY_EXIT_WAS_PREMATURE"
FATE_GOOD = "EARLY_EXIT_WAS_GOOD"
FATE_UNRESOLVED = "UNRESOLVED_BY_OOS_END"


@dataclass(frozen=True, slots=True)
class CausalExitState:
    """Causal features available no later than the production PD close."""

    observation_timestamp: datetime
    observation_available_at: datetime
    state: str
    regime: str
    phase: str
    aligned_active: bool
    opposite_active: bool
    normalized_slope: float | None
    normalized_opening: float | None
    slope_delta_1: float | None
    opening_delta_1: float | None
    move_1_r: float | None
    move_2_r: float | None
    move_3_r: float | None


@dataclass(frozen=True, slots=True)
class NegativePdFate:
    """Post-close diagnostic fate одного production negative-PD trade."""

    trade: WorkspaceHistoricalTradeDiagnostic
    risk_usd: float
    close_r: float
    production_peak_r: float
    causal_state: CausalExitState
    fate: str
    terminal_reason: str
    terminal_timestamp: datetime | None
    terminal_delay_m15: float | None
    recovered_0r: bool
    recovery_0r_timestamp: datetime | None
    recovery_0r_delay_m15: float | None
    reached_010r: bool
    reached_020r: bool
    reached_030r: bool
    recovered_production_peak: bool
    take_profit_reached: bool
    stop_loss_reached: bool
    post_close_mark_mfe_r: float
    post_close_mark_mae_r: float


def _risk_usd(trade: WorkspaceHistoricalTradeDiagnostic) -> float:
    risk = trade.stop_loss_distance * trade.volume
    if risk <= 0.0:
        raise AssertionError("Initial risk must be positive")
    return risk


def _mark_profit(
    trade: WorkspaceHistoricalTradeDiagnostic,
    event: WorkspaceMarketEvent,
) -> float:
    close_price = event.bid if trade.direction == "BUY" else event.ask
    sign = 1.0 if trade.direction == "BUY" else -1.0
    return (close_price - trade.entry_price) * trade.volume * sign


def _protection_reason(
    trade: WorkspaceHistoricalTradeDiagnostic,
    event: WorkspaceMarketEvent,
) -> str | None:
    """Повторити STOP_LOSS_FIRST protective-bar semantics production Replay."""
    if trade.direction == "BUY":
        stop_price = trade.entry_price - trade.stop_loss_distance
        take_price = trade.entry_price + trade.take_profit_distance
        stop_touched = event.low <= stop_price
        take_touched = event.high >= take_price
    else:
        stop_price = trade.entry_price + trade.stop_loss_distance
        take_price = trade.entry_price - trade.take_profit_distance
        stop_touched = event.high >= stop_price
        take_touched = event.low <= take_price
    if stop_touched:
        return "STOP_LOSS"
    if take_touched:
        return "TAKE_PROFIT"
    return None


def _latest_causal_observation_index(
    observations: tuple[WorkspaceAlligatorObservation, ...],
    close_timestamp: datetime,
) -> int:
    candidates = tuple(
        index
        for index, observation in enumerate(observations)
        if observation.available_at <= close_timestamp
    )
    if not candidates:
        raise AssertionError("No causal Alligator observation at PD close")
    return candidates[-1]


def _optional_delta(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return current - previous


def _directional_move_r(
    trade: WorkspaceHistoricalTradeDiagnostic,
    events: tuple[WorkspaceMarketEvent, ...],
    current_index: int,
    bars: int,
) -> float | None:
    if current_index - bars < 0:
        return None
    current = events[current_index].close
    previous = events[current_index - bars].close
    sign = 1.0 if trade.direction == "BUY" else -1.0
    return sign * (current - previous) / trade.stop_loss_distance


def _is_aligned_active(
    trade: WorkspaceHistoricalTradeDiagnostic,
    observation: WorkspaceAlligatorObservation,
) -> bool:
    if observation.regime_phase != ALLIGATOR_REGIME_PHASE_ACTIVE:
        return False
    if trade.direction == "BUY":
        return (
            observation.state == ALLIGATOR_STATE_BULLISH
            and observation.regime == ALLIGATOR_REGIME_TREND_UP
        )
    return (
        observation.state == ALLIGATOR_STATE_BEARISH
        and observation.regime == ALLIGATOR_REGIME_TREND_DOWN
    )


def _is_opposite_active(
    trade: WorkspaceHistoricalTradeDiagnostic,
    observation: WorkspaceAlligatorObservation,
) -> bool:
    if observation.regime_phase != ALLIGATOR_REGIME_PHASE_ACTIVE:
        return False
    if trade.direction == "BUY":
        return (
            observation.state == ALLIGATOR_STATE_BEARISH
            and observation.regime == ALLIGATOR_REGIME_TREND_DOWN
        )
    return (
        observation.state == ALLIGATOR_STATE_BULLISH
        and observation.regime == ALLIGATOR_REGIME_TREND_UP
    )


def _causal_exit_state(
    trade: WorkspaceHistoricalTradeDiagnostic,
    observations: tuple[WorkspaceAlligatorObservation, ...],
    strategy_events: tuple[WorkspaceMarketEvent, ...],
    strategy_index_by_timestamp: dict[datetime, int],
) -> CausalExitState:
    index = _latest_causal_observation_index(observations, trade.close_timestamp)
    observation = observations[index]
    previous = observations[index - 1] if index > 0 else None
    event_index = strategy_index_by_timestamp.get(observation.timestamp)
    if event_index is None:
        raise AssertionError("Alligator observation has no matching M15 event")

    return CausalExitState(
        observation_timestamp=observation.timestamp,
        observation_available_at=observation.available_at,
        state=observation.state,
        regime=observation.regime,
        phase=observation.regime_phase,
        aligned_active=_is_aligned_active(trade, observation),
        opposite_active=_is_opposite_active(trade, observation),
        normalized_slope=observation.normalized_slope,
        normalized_opening=observation.normalized_opening,
        slope_delta_1=(
            None
            if previous is None
            else _optional_delta(
                observation.normalized_slope,
                previous.normalized_slope,
            )
        ),
        opening_delta_1=(
            None
            if previous is None
            else _optional_delta(
                observation.normalized_opening,
                previous.normalized_opening,
            )
        ),
        move_1_r=_directional_move_r(trade, strategy_events, event_index, 1),
        move_2_r=_directional_move_r(trade, strategy_events, event_index, 2),
        move_3_r=_directional_move_r(trade, strategy_events, event_index, 3),
    )


def _future_execution_events(
    trade: WorkspaceHistoricalTradeDiagnostic,
    source_events: tuple[WorkspaceMarketEvent, ...],
) -> tuple[WorkspaceMarketEvent, ...]:
    selected = tuple(
        event for event in source_events if event.timestamp > trade.close_timestamp
    )
    if not selected:
        raise AssertionError("No post-close OOS execution events")
    return selected


def _fate_for_trade(
    trade: WorkspaceHistoricalTradeDiagnostic,
    source_events: tuple[WorkspaceMarketEvent, ...],
    causal_state: CausalExitState,
) -> NegativePdFate:
    risk_usd = _risk_usd(trade)
    close_r = trade.final_profit / risk_usd
    peak_r = trade.peak_profit / risk_usd
    assert close_r < 0.0
    assert peak_r > 0.0

    future = _future_execution_events(trade, source_events)
    milestone_timestamps: dict[float, datetime] = {}
    recovered_peak_timestamp: datetime | None = None
    terminal_reason = "OOS_END"
    terminal_timestamp: datetime | None = None
    mark_mfe_r = close_r
    mark_mae_r = close_r

    for event in future:
        protection = _protection_reason(trade, event)
        if protection is not None:
            terminal_reason = protection
            terminal_timestamp = event.timestamp
            if protection == "STOP_LOSS":
                mark_mae_r = min(mark_mae_r, -1.0)
            else:
                mark_mfe_r = max(mark_mfe_r, 2.0)
                # TP necessarily crossed every lower recovery target intrabar.
                for level_r in RECOVERY_LEVELS_R:
                    milestone_timestamps.setdefault(level_r, event.timestamp)
                if recovered_peak_timestamp is None:
                    recovered_peak_timestamp = event.timestamp
            break

        mark_r = _mark_profit(trade, event) / risk_usd
        mark_mfe_r = max(mark_mfe_r, mark_r)
        mark_mae_r = min(mark_mae_r, mark_r)
        for level_r in RECOVERY_LEVELS_R:
            if mark_r + NUMERIC_EPSILON >= level_r:
                milestone_timestamps.setdefault(level_r, event.timestamp)
        if mark_r + NUMERIC_EPSILON >= peak_r and recovered_peak_timestamp is None:
            recovered_peak_timestamp = event.timestamp

    recovery_timestamp = milestone_timestamps.get(0.0)
    recovered = recovery_timestamp is not None
    stop_reached = terminal_reason == "STOP_LOSS"
    take_reached = terminal_reason == "TAKE_PROFIT"

    if recovered:
        fate = FATE_PREMATURE
    elif stop_reached:
        fate = FATE_GOOD
    else:
        fate = FATE_UNRESOLVED

    def delay_m15(timestamp: datetime | None) -> float | None:
        if timestamp is None:
            return None
        return (timestamp - trade.close_timestamp).total_seconds() / M15_SECONDS

    return NegativePdFate(
        trade=trade,
        risk_usd=risk_usd,
        close_r=close_r,
        production_peak_r=peak_r,
        causal_state=causal_state,
        fate=fate,
        terminal_reason=terminal_reason,
        terminal_timestamp=terminal_timestamp,
        terminal_delay_m15=delay_m15(terminal_timestamp),
        recovered_0r=recovered,
        recovery_0r_timestamp=recovery_timestamp,
        recovery_0r_delay_m15=delay_m15(recovery_timestamp),
        reached_010r=0.10 in milestone_timestamps,
        reached_020r=0.20 in milestone_timestamps,
        reached_030r=0.30 in milestone_timestamps,
        recovered_production_peak=recovered_peak_timestamp is not None,
        take_profit_reached=take_reached,
        stop_loss_reached=stop_reached,
        post_close_mark_mfe_r=mark_mfe_r,
        post_close_mark_mae_r=mark_mae_r,
    )


def _mean_optional(values: tuple[float | None, ...]) -> float | None:
    available = tuple(value for value in values if value is not None)
    return mean(available) if available else None


def _median_optional(values: tuple[float | None, ...]) -> float | None:
    available = tuple(value for value in values if value is not None)
    return median(available) if available else None


def _fmt(value: float | None, digits: int = 3, signed: bool = False) -> str:
    if value is None:
        return "NONE"
    if signed:
        return f"{value:+.{digits}f}"
    return f"{value:.{digits}f}"


def _group_metrics(label: str, cases: tuple[NegativePdFate, ...]) -> None:
    print(f"  {label}:")
    print(f"    count={len(cases)}")
    if not cases:
        return

    states = tuple(case.causal_state for case in cases)
    other_count = sum(
        not state.aligned_active and not state.opposite_active for state in states
    )
    slope_mean = _mean_optional(tuple(state.normalized_slope for state in states))
    opening_mean = _mean_optional(tuple(state.normalized_opening for state in states))
    slope_delta_mean = _mean_optional(tuple(state.slope_delta_1 for state in states))
    opening_delta_mean = _mean_optional(
        tuple(state.opening_delta_1 for state in states)
    )
    move_1_mean = _mean_optional(tuple(state.move_1_r for state in states))
    move_2_mean = _mean_optional(tuple(state.move_2_r for state in states))
    move_3_mean = _mean_optional(tuple(state.move_3_r for state in states))
    recovery_delay_median = _median_optional(
        tuple(case.recovery_0r_delay_m15 for case in cases)
    )
    terminal_delay_median = _median_optional(
        tuple(case.terminal_delay_m15 for case in cases)
    )

    print(
        "    causal_alligator="
        f"aligned_active:{sum(state.aligned_active for state in states)},"
        f"opposite_active:{sum(state.opposite_active for state in states)},"
        f"other:{other_count}"
    )
    print(
        "    causal_metrics_mean="
        f"slope:{_fmt(slope_mean, signed=True)},"
        f"opening:{_fmt(opening_mean, signed=True)},"
        f"slope_d1:{_fmt(slope_delta_mean, signed=True)},"
        f"opening_d1:{_fmt(opening_delta_mean, signed=True)},"
        f"move1:{_fmt(move_1_mean, signed=True)}R,"
        f"move2:{_fmt(move_2_mean, signed=True)}R,"
        f"move3:{_fmt(move_3_mean, signed=True)}R"
    )
    print(
        "    production_exit="
        f"close_r_mean:{mean(case.close_r for case in cases):+.3f},"
        f"peak_r_mean:{mean(case.production_peak_r for case in cases):.3f}"
    )
    print(
        "    post_close="
        f"mfe_r_mean:{mean(case.post_close_mark_mfe_r for case in cases):+.3f},"
        f"mae_r_mean:{mean(case.post_close_mark_mae_r for case in cases):+.3f},"
        f"recovery_delay_median:{_fmt(recovery_delay_median, 2)}M15eq,"
        f"terminal_delay_median:{_fmt(terminal_delay_median, 2)}M15eq"
    )


def _case_line(index: int, case: NegativePdFate) -> str:
    state = case.causal_state
    return (
        f"    {index:02d}. {case.trade.close_timestamp.isoformat()} "
        f"{case.trade.direction} close:{case.close_r:+.3f}R "
        f"peak:{case.production_peak_r:.3f}R "
        f"fate:{case.fate} terminal:{case.terminal_reason} "
        f"recover0:{case.recovered_0r} +0.1:{case.reached_010r} "
        f"+0.2:{case.reached_020r} +0.3:{case.reached_030r} "
        f"peak_recovered:{case.recovered_production_peak} "
        f"tp:{case.take_profit_reached} "
        f"mfe_after:{case.post_close_mark_mfe_r:+.3f}R "
        f"mae_after:{case.post_close_mark_mae_r:+.3f}R "
        f"allig:{state.state}/{state.regime}/{state.phase} "
        f"aligned_active:{state.aligned_active} "
        f"opposite_active:{state.opposite_active} "
        f"slope:{_fmt(state.normalized_slope, signed=True)} "
        f"open:{_fmt(state.normalized_opening, signed=True)} "
        f"sd1:{_fmt(state.slope_delta_1, signed=True)} "
        f"od1:{_fmt(state.opening_delta_1, signed=True)} "
        f"m1:{_fmt(state.move_1_r, signed=True)}R "
        f"m2:{_fmt(state.move_2_r, signed=True)}R "
        f"m3:{_fmt(state.move_3_r, signed=True)}R"
    )


def build_negative_pd_fates(
    runtime: FrozenOosRuntime,
) -> tuple[
    tuple[NegativePdFate, ...],
    tuple[WorkspaceMarketEvent, ...],
]:
    """Повернути 18 negative-PD fate records і causal M1 source events."""
    session = runtime.replay_session
    execution = runtime.replay_execution
    algorithm = runtime.algorithm
    assert session is not None
    assert execution is not None
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    signal_filter = algorithm.signal_filter
    assert signal_filter is not None

    trades = execution.trade_diagnostics()
    negative_pd = tuple(
        trade
        for trade in trades
        if trade.close_reason == "PROFIT_DRAWDOWN" and trade.final_profit < 0.0
    )
    assert len(trades) == 59
    assert len(negative_pd) == 18

    source_events = tuple(
        event for window in session.execution_windows for event in window
    )
    strategy_events = session.events
    observations = signal_filter.observations
    assert source_events
    assert strategy_events
    assert observations
    strategy_index_by_timestamp = {
        event.timestamp: index for index, event in enumerate(strategy_events)
    }

    cases = tuple(
        _fate_for_trade(
            trade,
            source_events,
            _causal_exit_state(
                trade,
                observations,
                strategy_events,
                strategy_index_by_timestamp,
            ),
        )
        for trade in negative_pd
    )
    return cases, source_events


def main() -> None:
    """Побудувати negative-PD fate labels та causal exit-state contrast."""
    assert_frozen_oos_snapshot()

    runtime = FrozenOosRuntime(
        frozen_oos_workspace(),
        algorithm_factory=create_registered_workspace_algorithm,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()

    summary = runtime.historical_summary
    assert summary is not None
    cases, _source_events = build_negative_pd_fates(runtime)

    premature = tuple(case for case in cases if case.fate == FATE_PREMATURE)
    good = tuple(case for case in cases if case.fate == FATE_GOOD)
    unresolved = tuple(case for case in cases if case.fate == FATE_UNRESOLVED)

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted
    assert all(
        case.causal_state.observation_available_at <= case.trade.close_timestamp
        for case in cases
    )

    print("Algorithm Workspace Candidate F Negative PD Fate 2025 result")
    print("  mode=NEGATIVE_PROFIT_DRAWDOWN_FATE_DIAGNOSTIC_ONLY")
    print(
        "  baseline="
        f"trades:{summary.opened_trades},net:{summary.net_profit:+.2f},"
        f"pf:{summary.profit_factor:.4f},dd:{summary.maximum_drawdown:.2f}"
    )
    print("  production_negative_pd_trades=18")
    print("  post_close_path=read_only_until_original_SL_or_TP_or_OOS_end")
    print("  protective_ambiguity_policy=STOP_LOSS_FIRST")
    print("  premature_definition=recovered_to_nonnegative_mark_before_original_SL")
    print("  good_definition=original_SL_before_nonnegative_mark_recovery")
    print(
        "  fate_counts="
        f"premature:{len(premature)},good:{len(good)},unresolved:{len(unresolved)}"
    )
    print(
        "  recovery_milestones="
        f"0R:{sum(case.recovered_0r for case in cases)},"
        f"0.10R:{sum(case.reached_010r for case in cases)},"
        f"0.20R:{sum(case.reached_020r for case in cases)},"
        f"0.30R:{sum(case.reached_030r for case in cases)},"
        f"production_peak:{sum(case.recovered_production_peak for case in cases)}"
    )
    print(
        "  eventual_original_protection="
        f"sl:{sum(case.stop_loss_reached for case in cases)},"
        f"tp:{sum(case.take_profit_reached for case in cases)},"
        f"oos_end:{sum(case.terminal_reason == 'OOS_END' for case in cases)}"
    )
    _group_metrics("early_exit_was_premature", premature)
    _group_metrics("early_exit_was_good", good)
    _group_metrics("unresolved", unresolved)

    print("  chronological_negative_pd_fates:")
    for index, case in enumerate(cases, start=1):
        print(_case_line(index, case))

    print("  production_trades_modified=False")
    print("  counterfactual_trades_created=False")
    print("  counterfactual_exits_created=False")
    print("  future_after_pd_close_used_only_for_diagnostic_label=True")
    print("  future_price_used_as_exit_gate=False")
    print("  exit_logic_changed=False")
    print("  entry_logic_changed=False")
    print("  macd_quality_thresholds_changed=False")
    print("  alligator_thresholds_changed=False")
    print("  candidate_f_thresholds_changed=False")
    print("  completed_alligator_observations_only=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_NEGATIVE_PD_FATE_2025_CHECK=OK")


if __name__ == "__main__":
    main()
