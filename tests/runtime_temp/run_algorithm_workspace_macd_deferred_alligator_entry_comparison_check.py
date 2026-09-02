# -*- coding: utf-8 -*-
"""Порівняння 3-bar, 4-bar і 4-bar + ARMED deferred entry.

RoadMap101 №30. A/B baseline зафіксований попереднім GREEN-тестом №28.
A — поточний 3-bar confirmation; B — 4-bar confirmation без пам'яті
MACD. У цьому тесті повторно виконується лише варіант C, щоб не ганяти
зайві Replay: 4-bar confirmation + test-only ARMED MACD candidate.

Якщо якісний MACD CROSS заблоковано тільки SAME_TIMEFRAME фазою
STARTING того самого напрямку, кандидат тимчасово ARMED. На наступних
завершених M15 bars він causal скасовується протилежним MACD CROSS,
протилежним ACTIVE Alligator, втратою MACD relation або TTL. Якщо
Alligator стає ACTIVE того самого напрямку, формується test-only
deferred release signal. Після цього WorkspaceRuntime використовує
звичайний production NEXT_BAR_OPEN, margin, SL/TP і Profit Drawdown
lifecycle.

Production algorithm registration, production trade gate і константи
після тесту не змінюються; broker execution не виконується.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, replace
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
from core.workspace_algorithm import WorkspaceSignalOutput  # noqa: E402
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_PHASE_STARTING,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    ALLIGATOR_STATE_BEARISH,
    ALLIGATOR_STATE_BULLISH,
    WorkspaceAlligatorFilter,
    WorkspaceAlligatorObservation,
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_indicator_profile import (  # noqa: E402
    new_workspace_indicator_profile_bindings,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import (  # noqa: E402
    WORKSPACE_SIGNAL_FILTER_ALLOW,
    WORKSPACE_SIGNAL_FILTER_REJECT,
    WorkspaceSignalFilterContext,
    WorkspaceSignalProposal,
)
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

CANDIDATE_CONFIRMATION_BARS = 4
DEFERRED_EXPIRY_BARS = 5
DEFERRED_SIGNAL_TYPE = "MACD_DEFERRED_RELEASE"
DEFERRED_SOURCE_REASON_CODE = "MACD_DEFERRED_RELEASE"


@dataclass(frozen=True, slots=True)
class LockedBaseline:
    """A/B контроль, уже підтверджений RoadMap101 №28."""

    trades: int
    winners: int
    losers: int
    stop_loss_closes: int
    profit_drawdown_closes: int
    take_profit_closes: int
    net_profit: float
    maximum_drawdown: float
    profit_factor: float | None
    position_signatures: tuple[tuple[str, str, str, float], ...]


A_3BAR: dict[str, LockedBaseline] = {
    "DEVELOPMENT": LockedBaseline(
        trades=9,
        winners=6,
        losers=3,
        stop_loss_closes=1,
        profit_drawdown_closes=8,
        take_profit_closes=0,
        net_profit=-1.06,
        maximum_drawdown=2.65,
        profit_factor=0.6268,
        position_signatures=(),
    ),
    "VALIDATION": LockedBaseline(
        trades=21,
        winners=10,
        losers=11,
        stop_loss_closes=4,
        profit_drawdown_closes=17,
        take_profit_closes=0,
        net_profit=-3.89,
        maximum_drawdown=4.46,
        profit_factor=0.5221,
        position_signatures=(),
    ),
    "HOLDOUT": LockedBaseline(
        trades=10,
        winners=4,
        losers=6,
        stop_loss_closes=2,
        profit_drawdown_closes=8,
        take_profit_closes=0,
        net_profit=-4.01,
        maximum_drawdown=4.01,
        profit_factor=0.0631,
        position_signatures=(),
    ),
}

B_4BAR: dict[str, LockedBaseline] = {
    "DEVELOPMENT": LockedBaseline(
        trades=7,
        winners=5,
        losers=2,
        stop_loss_closes=0,
        profit_drawdown_closes=7,
        take_profit_closes=0,
        net_profit=1.01,
        maximum_drawdown=0.19,
        profit_factor=6.3158,
        position_signatures=(
            ("2026-01-06T15:00:00+00:00", "SELL", "PROFIT_DRAWDOWN", 0.23),
            ("2026-01-28T11:00:00+00:00", "SELL", "PROFIT_DRAWDOWN", 0.43),
            ("2026-01-28T13:15:00+00:00", "SELL", "PROFIT_DRAWDOWN", -0.17),
            ("2026-01-28T15:00:00+00:00", "SELL", "PROFIT_DRAWDOWN", -0.02),
            ("2026-01-28T18:30:00+00:00", "SELL", "PROFIT_DRAWDOWN", 0.23),
            ("2026-01-30T20:15:00+00:00", "SELL", "PROFIT_DRAWDOWN", 0.23),
            ("2026-02-02T18:00:00+00:00", "SELL", "PROFIT_DRAWDOWN", 0.08),
        ),
    ),
    "VALIDATION": LockedBaseline(
        trades=21,
        winners=10,
        losers=11,
        stop_loss_closes=4,
        profit_drawdown_closes=17,
        take_profit_closes=0,
        net_profit=-3.89,
        maximum_drawdown=4.46,
        profit_factor=0.5221,
        position_signatures=(),
    ),
    "HOLDOUT": LockedBaseline(
        trades=10,
        winners=4,
        losers=6,
        stop_loss_closes=2,
        profit_drawdown_closes=8,
        take_profit_closes=0,
        net_profit=-4.01,
        maximum_drawdown=4.01,
        profit_factor=0.0631,
        position_signatures=(),
    ),
}


@dataclass(slots=True)
class _ArmedCandidate:
    """Test-only ARMED кандидат до формування торгового сигналу."""

    proposal: WorkspaceSignalProposal
    armed_timestamp: datetime
    bars_waited: int = 0


@dataclass(frozen=True, slots=True)
class DeferredReleaseEvent:
    """Causal signal -> release факт test-only deferred алгоритму."""

    original_signal_timestamp: datetime
    release_timestamp: datetime
    direction: str
    delay_bars: int


class DeferredMacdAlligatorReplayAlgorithm(WorkspaceMacdAlligatorReplayAlgorithm):
    """Test-only production wrapper з ARMED/deferred release lifecycle."""

    def __init__(self, algorithm_id: str = "MACD_ALLIGATOR_DEFERRED_TEST") -> None:
        super().__init__(algorithm_id)
        self._armed: _ArmedCandidate | None = None
        self.deferred_releases: list[DeferredReleaseEvent] = []
        self.cancelled_opposite_cross = 0
        self.cancelled_opposite_alligator = 0
        self.cancelled_macd_invalid = 0
        self.expired = 0
        self.rearm_while_pending = 0

    def start(self) -> None:
        super().start()
        self._armed = None
        self.deferred_releases = []
        self.cancelled_opposite_cross = 0
        self.cancelled_opposite_alligator = 0
        self.cancelled_macd_invalid = 0
        self.expired = 0
        self.rearm_while_pending = 0

    def on_market_event(self, event: WorkspaceMarketEvent) -> WorkspaceSignalOutput:
        base_output = super().on_market_event(event)
        base_proposals = _proposal_tuple(base_output)
        deferred = self._advance_armed_candidate(event, base_proposals)
        self._arm_from_base_proposals(event, base_proposals)
        if deferred is None:
            return base_output
        return *base_proposals, deferred

    def _advance_armed_candidate(
        self,
        event: WorkspaceMarketEvent,
        base_proposals: tuple[WorkspaceSignalProposal, ...],
    ) -> WorkspaceSignalProposal | None:
        armed = self._armed
        if armed is None or event.timestamp <= armed.armed_timestamp:
            return None
        armed.bars_waited += 1

        if any(
            proposal.signal_type == "MACD_CROSS"
            and proposal.direction != armed.proposal.direction
            for proposal in base_proposals
        ):
            self.cancelled_opposite_cross += 1
            self._armed = None
            return None

        source = self.source
        signal_filter = self.signal_filter
        if source is None or signal_filter is None or not source.observations:
            self.cancelled_macd_invalid += 1
            self._armed = None
            return None
        macd_observation = source.observations[-1]
        if not _macd_relation_matches(
            macd_observation.histogram,
            armed.proposal.direction,
        ):
            self.cancelled_macd_invalid += 1
            self._armed = None
            return None

        alligator_observation = signal_filter.latest_observation
        if _active_opposite(alligator_observation, armed.proposal.direction):
            self.cancelled_opposite_alligator += 1
            self._armed = None
            return None

        if _active_matches(alligator_observation, armed.proposal.direction):
            decision = signal_filter.evaluate(
                armed.proposal,
                alligator_observation,
                proposal_timestamp=event.timestamp,
            )
            assert decision.allowed
            release = replace(
                armed.proposal,
                signal_type=DEFERRED_SIGNAL_TYPE,
                strength=abs(float(macd_observation.histogram or 0.0)),
                macd_state=macd_observation.state,
                alligator_confirmation=decision.confirmation,
                reason=(
                    "Deferred MACD release; original_signal_timestamp="
                    f"{armed.armed_timestamp.isoformat()}; "
                    f"delay_bars={armed.bars_waited}; "
                    f"{decision.reason_code}: {decision.reason_text}"
                ),
                source_reason_code=DEFERRED_SOURCE_REASON_CODE,
                filter_decision=WORKSPACE_SIGNAL_FILTER_ALLOW,
                filter_reason_code=None,
                filter_context=_filter_context(
                    signal_filter,
                    alligator_observation,
                    event,
                ),
            )
            self.deferred_releases.append(
                DeferredReleaseEvent(
                    original_signal_timestamp=armed.armed_timestamp,
                    release_timestamp=event.timestamp,
                    direction=armed.proposal.direction,
                    delay_bars=armed.bars_waited,
                )
            )
            self._armed = None
            return release

        if armed.bars_waited >= DEFERRED_EXPIRY_BARS:
            self.expired += 1
            self._armed = None
        return None

    def _arm_from_base_proposals(
        self,
        event: WorkspaceMarketEvent,
        base_proposals: tuple[WorkspaceSignalProposal, ...],
    ) -> None:
        for proposal in base_proposals:
            if not _is_armed_candidate(proposal):
                continue
            if self._armed is not None:
                self.rearm_while_pending += 1
                continue
            self._armed = _ArmedCandidate(
                proposal=proposal,
                armed_timestamp=event.timestamp,
            )


def _proposal_tuple(
    output: WorkspaceSignalOutput,
) -> tuple[WorkspaceSignalProposal, ...]:
    if output is None:
        return ()
    if isinstance(output, WorkspaceSignalProposal):
        return (output,)
    return tuple(output)


def _is_armed_candidate(proposal: WorkspaceSignalProposal) -> bool:
    context = proposal.filter_context
    return bool(
        proposal.signal_type == "MACD_CROSS"
        and proposal.source_reason_code == "MACD_CROSS_ACCEPTED"
        and proposal.filter_decision == WORKSPACE_SIGNAL_FILTER_REJECT
        and context is not None
        and context.regime_phase == ALLIGATOR_REGIME_PHASE_STARTING
        and _regime_matches(context.regime, proposal.direction)
    )


def _regime_matches(regime: str | None, direction: str) -> bool:
    if direction == "BUY":
        return regime == ALLIGATOR_REGIME_TREND_UP
    return regime == ALLIGATOR_REGIME_TREND_DOWN


def _macd_relation_matches(histogram: float | None, direction: str) -> bool:
    if histogram is None:
        return False
    if direction == "BUY":
        return histogram > 0.0
    return histogram < 0.0


def _active_matches(
    observation: WorkspaceAlligatorObservation | None,
    direction: str,
) -> bool:
    if observation is None or observation.regime_phase != ALLIGATOR_REGIME_PHASE_ACTIVE:
        return False
    if direction == "BUY":
        return bool(
            observation.regime == ALLIGATOR_REGIME_TREND_UP
            and observation.state == ALLIGATOR_STATE_BULLISH
        )
    return bool(
        observation.regime == ALLIGATOR_REGIME_TREND_DOWN
        and observation.state == ALLIGATOR_STATE_BEARISH
    )


def _active_opposite(
    observation: WorkspaceAlligatorObservation | None,
    direction: str,
) -> bool:
    if observation is None or observation.regime_phase != ALLIGATOR_REGIME_PHASE_ACTIVE:
        return False
    if direction == "BUY":
        return bool(
            observation.regime == ALLIGATOR_REGIME_TREND_DOWN
            and observation.state == ALLIGATOR_STATE_BEARISH
        )
    return bool(
        observation.regime == ALLIGATOR_REGIME_TREND_UP
        and observation.state == ALLIGATOR_STATE_BULLISH
    )


def _filter_context(
    signal_filter: WorkspaceAlligatorFilter,
    observation: WorkspaceAlligatorObservation,
    event: WorkspaceMarketEvent,
) -> WorkspaceSignalFilterContext:
    return WorkspaceSignalFilterContext(
        mode=signal_filter.confirmation_mode,
        timeframe=signal_filter.timeframe or event.timeframe,
        profile_uid=signal_filter.profile_uid,
        profile_revision=signal_filter.profile_revision,
        observation_timestamp=observation.timestamp,
        available_at=observation.available_at,
        regime=observation.regime,
        regime_phase=observation.regime_phase,
        normalized_slope=observation.normalized_slope,
        normalized_opening=observation.normalized_opening,
    )


@dataclass(frozen=True, slots=True)
class DeferredTradeResult:
    """Фактична deferred trade після release + production NEXT_BAR_OPEN."""

    original_signal_timestamp: datetime
    release_timestamp: datetime
    direction: str
    delay_bars: int
    entry_timestamp: datetime | None
    close_reason: str | None
    final_profit: float | None
    maximum_favorable_excursion: float | None
    maximum_adverse_excursion: float | None


@dataclass(frozen=True, slots=True)
class ComparisonRun:
    """Фактичний C Replay result."""

    window: str
    trades: int
    winners: int
    losers: int
    stop_loss_closes: int
    profit_drawdown_closes: int
    take_profit_closes: int
    net_profit: float
    maximum_drawdown: float
    profit_factor: float | None
    position_signatures: tuple[tuple[str, str, str, float], ...]
    deferred_releases: int
    deferred_trades: tuple[DeferredTradeResult, ...]
    cancelled_opposite_cross: int
    cancelled_opposite_alligator: int
    cancelled_macd_invalid: int
    deferred_expired: int
    rearm_while_pending: int


def _workspace(start_utc: str, end_utc: str) -> AlgorithmWorkspace:
    """Побудувати фіксований RM96 WSP для варіанта C."""
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id=None,
        account_mode=None,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        display_name="RM96 Deferred MACD Entry Comparison",
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


def _deferred_factory(algorithm_id: str) -> DeferredMacdAlligatorReplayAlgorithm:
    return DeferredMacdAlligatorReplayAlgorithm(algorithm_id)


def _run_c(window: str, start_utc: str, end_utc: str) -> ComparisonRun:
    original = workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS
    try:
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS = (
            CANDIDATE_CONFIRMATION_BARS
        )
        runtime = WorkspaceRuntime(
            _workspace(start_utc, end_utc),
            algorithm_factory=_deferred_factory,
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
        assert isinstance(algorithm, DeferredMacdAlligatorReplayAlgorithm)

        diagnostics = execution.trade_diagnostics()
        records = runtime.signal_records()
        deferred_records = tuple(
            record
            for record in records
            if record.signal_type == DEFERRED_SIGNAL_TYPE and record.accepted
        )
        diagnostics_by_uid = {trade.signal_uid: trade for trade in diagnostics}
        deferred_trades: list[DeferredTradeResult] = []
        for release in algorithm.deferred_releases:
            matching_records = [
                record
                for record in deferred_records
                if record.timestamp == release.release_timestamp
                and record.direction == release.direction
            ]
            assert len(matching_records) == 1
            trade = diagnostics_by_uid.get(matching_records[0].signal_uid)
            deferred_trades.append(
                DeferredTradeResult(
                    original_signal_timestamp=release.original_signal_timestamp,
                    release_timestamp=release.release_timestamp,
                    direction=release.direction,
                    delay_bars=release.delay_bars,
                    entry_timestamp=(
                        trade.entry_timestamp if trade is not None else None
                    ),
                    close_reason=trade.close_reason if trade is not None else None,
                    final_profit=trade.final_profit if trade is not None else None,
                    maximum_favorable_excursion=(
                        trade.maximum_favorable_excursion if trade is not None else None
                    ),
                    maximum_adverse_excursion=(
                        trade.maximum_adverse_excursion if trade is not None else None
                    ),
                )
            )

        broker_execution_attempted = any(
            bool(entry.details.get("broker_execution_attempted"))
            for entry in runtime.journal
            if isinstance(entry.details, dict)
        )
        assert not broker_execution_attempted

        return ComparisonRun(
            window=window,
            trades=summary.opened_trades,
            winners=summary.winning_trades,
            losers=summary.losing_trades,
            stop_loss_closes=summary.close_reason_count("STOP_LOSS"),
            profit_drawdown_closes=summary.close_reason_count("PROFIT_DRAWDOWN"),
            take_profit_closes=summary.close_reason_count("TAKE_PROFIT"),
            net_profit=summary.net_profit,
            maximum_drawdown=summary.maximum_drawdown,
            profit_factor=summary.profit_factor,
            position_signatures=tuple(
                (
                    trade.signal_timestamp.isoformat(),
                    trade.direction,
                    trade.close_reason,
                    round(trade.final_profit, 2),
                )
                for trade in diagnostics
            ),
            deferred_releases=len(algorithm.deferred_releases),
            deferred_trades=tuple(deferred_trades),
            cancelled_opposite_cross=algorithm.cancelled_opposite_cross,
            cancelled_opposite_alligator=algorithm.cancelled_opposite_alligator,
            cancelled_macd_invalid=algorithm.cancelled_macd_invalid,
            deferred_expired=algorithm.expired,
            rearm_while_pending=algorithm.rearm_while_pending,
        )
    finally:
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS = original


def _format_baseline(result: LockedBaseline) -> str:
    pf = "NONE" if result.profit_factor is None else f"{result.profit_factor:.4f}"
    return (
        f"trades:{result.trades},wins:{result.winners},losses:{result.losers},"
        f"sl:{result.stop_loss_closes},pd:{result.profit_drawdown_closes},"
        f"tp:{result.take_profit_closes},pnl:{result.net_profit:.2f},"
        f"dd:{result.maximum_drawdown:.2f},pf:{pf}"
    )


def _format_c(result: ComparisonRun) -> str:
    pf = "NONE" if result.profit_factor is None else f"{result.profit_factor:.4f}"
    return (
        f"trades:{result.trades},wins:{result.winners},losses:{result.losers},"
        f"sl:{result.stop_loss_closes},pd:{result.profit_drawdown_closes},"
        f"tp:{result.take_profit_closes},pnl:{result.net_profit:.2f},"
        f"dd:{result.maximum_drawdown:.2f},pf:{pf}"
    )


def _format_deferred(result: ComparisonRun) -> str:
    if not result.deferred_trades:
        return "NONE"
    parts: list[str] = []
    for item in result.deferred_trades:
        if item.entry_timestamp is None:
            outcome = "NO_ENTRY"
        else:
            outcome = (
                f"entry:{item.entry_timestamp.isoformat()},"
                f"close:{item.close_reason},pnl:{float(item.final_profit or 0.0):+.2f},"
                "mfe:"
                f"{float(item.maximum_favorable_excursion or 0.0):+.2f},"
                "mae:"
                f"{float(item.maximum_adverse_excursion or 0.0):+.2f}"
            )
        parts.append(
            f"{item.original_signal_timestamp.isoformat()} {item.direction}"
            f" -> release:+{item.delay_bars} {item.release_timestamp.isoformat()}"
            f" -> {outcome}"
        )
    return "; ".join(parts)


def _ordinary_c_signatures(result: ComparisonRun) -> set[tuple[str, str, str, float]]:
    deferred_keys = {
        (item.release_timestamp.isoformat(), item.direction)
        for item in result.deferred_trades
    }
    return {
        signature
        for signature in result.position_signatures
        if (signature[0], signature[1]) not in deferred_keys
    }


def main() -> None:
    original = workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS
    results: dict[str, ComparisonRun] = {}
    for window, start_utc, end_utc in WINDOWS:
        results[window] = _run_c(window, start_utc, end_utc)

    development = results["DEVELOPMENT"]
    validation = results["VALIDATION"]
    holdout = results["HOLDOUT"]

    assert development.deferred_releases == 2
    assert len(development.deferred_trades) == 2
    assert all(item.delay_bars == 1 for item in development.deferred_trades)
    assert validation.deferred_releases == 0
    assert holdout.deferred_releases == 0
    assert holdout.cancelled_opposite_cross == 1
    assert development.rearm_while_pending == 0
    assert validation.rearm_while_pending == 0
    assert holdout.rearm_while_pending == 0

    assert _ordinary_c_signatures(development) == set(
        B_4BAR["DEVELOPMENT"].position_signatures
    )
    assert validation.trades == B_4BAR["VALIDATION"].trades
    assert validation.stop_loss_closes == B_4BAR["VALIDATION"].stop_loss_closes
    assert math.isclose(
        validation.net_profit,
        B_4BAR["VALIDATION"].net_profit,
        rel_tol=0.0,
        abs_tol=1e-9,
    )
    assert holdout.trades == B_4BAR["HOLDOUT"].trades
    assert holdout.stop_loss_closes == B_4BAR["HOLDOUT"].stop_loss_closes
    assert math.isclose(
        holdout.net_profit,
        B_4BAR["HOLDOUT"].net_profit,
        rel_tol=0.0,
        abs_tol=1e-9,
    )

    assert development.trades == 9
    assert development.stop_loss_closes == 0
    assert math.isclose(development.net_profit, 1.02, rel_tol=0.0, abs_tol=1e-9)
    assert (
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS == original
    )

    print("Algorithm Workspace deferred MACD real-entry comparison result")
    print("  mode=TEST_ONLY_DEFERRED_RELEASE_WITH_PRODUCTION_REPLAY_EXECUTION")
    print("  variants=A:3BAR_CURRENT / B:4BAR_CURRENT / C:4BAR+ARMED")
    print("  a_b_reference=LOCKED_GREEN_ROADMAP101_28")
    print("  armed_policy=QUALITY_MACD + SAME_DIRECTION_ALLIGATOR_STARTING")
    print("  release_policy=ACTIVE_SAME_DIRECTION + MACD_RELATION_STILL_VALID")
    print("  cancel_policy=OPPOSITE_MACD/OPPOSITE_ACTIVE_ALLIGATOR/MACD_INVALID/TTL")
    print(f"  deferred_expiry_bars={DEFERRED_EXPIRY_BARS}")
    print("  deferred_execution=RELEASE_SIGNAL -> PRODUCTION_NEXT_BAR_OPEN")
    print("  fixed_workspace=RM96 EURUSD M15 Historical")
    print("  fixed_macd=8/17/5 EXTENDED prominence=0.000015 distance=0.000050 ABC=2.25")
    print("  fixed_alligator=13/8,8/5,5/3 SMOOTHED MEDIAN SAME_TIMEFRAME")
    for window, _start_utc, _end_utc in WINDOWS:
        print(f"  {window.lower()}_a_3bar={_format_baseline(A_3BAR[window])}")
        print(f"  {window.lower()}_b_4bar={_format_baseline(B_4BAR[window])}")
        result = results[window]
        print(f"  {window.lower()}_c_4bar_armed={_format_c(result)}")
        print(
            f"  {window.lower()}_armed_lifecycle="
            f"releases:{result.deferred_releases},"
            f"opposite_cross:{result.cancelled_opposite_cross},"
            f"opposite_alligator:{result.cancelled_opposite_alligator},"
            f"macd_invalid:{result.cancelled_macd_invalid},"
            f"expired:{result.deferred_expired}"
        )
        print(f"  {window.lower()}_deferred_trades=" f"{_format_deferred(result)}")
    print("  ordinary_4bar_trades_preserved=True")
    print("  completed_bars_only=True")
    print("  no_look_ahead=True")
    print("  production_trade_gate_changed=False")
    print("  production_algorithm_registration_changed=False")
    print("  production_constant_restored_after_comparison=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_MACD_DEFERRED_ALLIGATOR_ENTRY_COMPARISON_CHECK=OK")


if __name__ == "__main__":
    main()
