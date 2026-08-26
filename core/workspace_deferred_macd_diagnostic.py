# -*- coding: utf-8 -*-
"""Діагностика відкладеного MACD-кандидата після блокування Alligator.

Модуль нічого не змінює у production trade gate. Він аналізує вже завершений
детермінований Replay і відповідає на питання: чи міг якісний MACD CROSS,
відхилений SAME_TIMEFRAME Alligator, стати допустимим через кілька завершених
барів без look-ahead і без нового MACD CROSS.

Консервативний ARMED-кандидат допускається лише коли Alligator перебуває у
STARTING того самого напрямку, що й MACD. ENDING, FLAT, протилежний напрямок і
інші відмови поки лише рахуються як blocked, але не озброюються.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from core.workspace_alligator import (
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_PHASE_STARTING,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    ALLIGATOR_STATE_BEARISH,
    ALLIGATOR_STATE_BULLISH,
    WorkspaceAlligatorObservation,
)
from core.workspace_macd import WorkspaceMacdObservation
from core.workspace_signal import (
    WORKSPACE_SIGNAL_FILTER_REJECT,
    WorkspaceSignalRecord,
)

DEFERRED_MACD_RELEASED = "RELEASED"
DEFERRED_MACD_OPPOSITE_CROSS = "OPPOSITE_MACD_CROSS"
DEFERRED_MACD_OPPOSITE_ALLIGATOR = "OPPOSITE_ALLIGATOR_ACTIVE"
DEFERRED_MACD_RELATION_INVALID = "MACD_RELATION_INVALID"
DEFERRED_MACD_EXPIRED = "EXPIRED"
DEFERRED_MACD_NOT_ARMED_PHASE = "NOT_ARMED_PHASE"
DEFERRED_MACD_NOT_ARMED_DIRECTION = "NOT_ARMED_DIRECTION"


@dataclass(frozen=True, slots=True)
class WorkspaceDeferredMacdCandidateOutcome:
    """Результат causal-аналізу одного blocked quality MACD CROSS."""

    signal_timestamp: datetime
    direction: str
    filter_reason_code: str
    regime: str | None
    regime_phase: str | None
    armed: bool
    terminal_reason: str
    release_after_bars: int | None = None
    release_timestamp: datetime | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceDeferredMacdDiagnosticSummary:
    """Агреговані лічильники ARMED diagnostic для одного Replay-вікна."""

    blocked_good_macd: int
    armed_candidates: int
    not_armed_phase: int
    not_armed_direction: int
    released_after_1: int
    released_after_2: int
    released_after_3: int
    released_after_4: int
    released_after_5: int
    released_after_5_plus: int
    opposite_cross_before_confirmation: int
    opposite_alligator_before_confirmation: int
    macd_relation_invalidated: int
    expired: int
    outcomes: tuple[WorkspaceDeferredMacdCandidateOutcome, ...]

    @property
    def potential_deferred_entries(self) -> int:
        """Кількість кандидатів, які causal досягли valid release."""
        return sum(
            1
            for outcome in self.outcomes
            if outcome.terminal_reason == DEFERRED_MACD_RELEASED
        )


def analyze_workspace_deferred_macd_candidates(
    signal_records: Iterable[WorkspaceSignalRecord],
    macd_observations: Iterable[WorkspaceMacdObservation],
    alligator_observations: Iterable[WorkspaceAlligatorObservation],
    *,
    expiry_bars: int = 5,
) -> WorkspaceDeferredMacdDiagnosticSummary:
    """Проаналізувати blocked quality MACD CROSS без зміни торгової логіки.

    ``expiry_bars`` задає майбутній практичний TTL для ``EXPIRED``. Для
    діагностики ``5+`` після цього TTL додатково перевіряється, чи існував би
    causal release до першого протилежного MACD CROSS. Такий release не є
    торговим рішенням і лише показує запізніле підтвердження Alligator.
    """
    if expiry_bars <= 0:
        raise ValueError("expiry_bars must be positive")

    records = tuple(signal_records)
    macd = tuple(macd_observations)
    alligator = tuple(alligator_observations)
    macd_index = {item.timestamp: index for index, item in enumerate(macd)}
    alligator_by_timestamp = {item.timestamp: item for item in alligator}
    crosses_by_timestamp = {
        record.timestamp: record
        for record in records
        if record.signal_type == "MACD_CROSS"
    }

    blocked = tuple(
        record
        for record in records
        if record.signal_type == "MACD_CROSS"
        and record.source_reason_code == "MACD_CROSS_ACCEPTED"
        and record.filter_decision == WORKSPACE_SIGNAL_FILTER_REJECT
        and str(record.filter_reason_code or "").startswith("ALLIGATOR_")
    )

    outcomes = tuple(
        _analyze_candidate(
            record,
            macd,
            macd_index,
            alligator_by_timestamp,
            crosses_by_timestamp,
            expiry_bars=expiry_bars,
        )
        for record in blocked
    )

    return WorkspaceDeferredMacdDiagnosticSummary(
        blocked_good_macd=len(blocked),
        armed_candidates=sum(outcome.armed for outcome in outcomes),
        not_armed_phase=_count_terminal(outcomes, DEFERRED_MACD_NOT_ARMED_PHASE),
        not_armed_direction=_count_terminal(
            outcomes,
            DEFERRED_MACD_NOT_ARMED_DIRECTION,
        ),
        released_after_1=_count_release_bar(outcomes, 1),
        released_after_2=_count_release_bar(outcomes, 2),
        released_after_3=_count_release_bar(outcomes, 3),
        released_after_4=_count_release_bar(outcomes, 4),
        released_after_5=_count_release_bar(outcomes, 5),
        released_after_5_plus=sum(
            outcome.terminal_reason == DEFERRED_MACD_RELEASED
            and outcome.release_after_bars is not None
            and outcome.release_after_bars > 5
            for outcome in outcomes
        ),
        opposite_cross_before_confirmation=_count_terminal(
            outcomes,
            DEFERRED_MACD_OPPOSITE_CROSS,
        ),
        opposite_alligator_before_confirmation=_count_terminal(
            outcomes,
            DEFERRED_MACD_OPPOSITE_ALLIGATOR,
        ),
        macd_relation_invalidated=_count_terminal(
            outcomes,
            DEFERRED_MACD_RELATION_INVALID,
        ),
        expired=_count_terminal(outcomes, DEFERRED_MACD_EXPIRED),
        outcomes=outcomes,
    )


def _analyze_candidate(
    record: WorkspaceSignalRecord,
    macd: tuple[WorkspaceMacdObservation, ...],
    macd_index: dict[datetime, int],
    alligator_by_timestamp: dict[datetime, WorkspaceAlligatorObservation],
    crosses_by_timestamp: dict[datetime, WorkspaceSignalRecord],
    *,
    expiry_bars: int,
) -> WorkspaceDeferredMacdCandidateOutcome:
    """Розібрати один blocked MACD CROSS тільки вперед у causal history."""
    direction = record.direction
    filter_context = record.filter_context
    regime = filter_context.regime if filter_context is not None else None
    phase = filter_context.regime_phase if filter_context is not None else None
    reason_code = str(record.filter_reason_code or "")

    if phase != ALLIGATOR_REGIME_PHASE_STARTING:
        return WorkspaceDeferredMacdCandidateOutcome(
            signal_timestamp=record.timestamp,
            direction=direction,
            filter_reason_code=reason_code,
            regime=regime,
            regime_phase=phase,
            armed=False,
            terminal_reason=DEFERRED_MACD_NOT_ARMED_PHASE,
        )
    if not _regime_matches_direction(regime, direction):
        return WorkspaceDeferredMacdCandidateOutcome(
            signal_timestamp=record.timestamp,
            direction=direction,
            filter_reason_code=reason_code,
            regime=regime,
            regime_phase=phase,
            armed=False,
            terminal_reason=DEFERRED_MACD_NOT_ARMED_DIRECTION,
        )

    start_index = macd_index.get(record.timestamp)
    if start_index is None:
        return WorkspaceDeferredMacdCandidateOutcome(
            signal_timestamp=record.timestamp,
            direction=direction,
            filter_reason_code=reason_code,
            regime=regime,
            regime_phase=phase,
            armed=True,
            terminal_reason=DEFERRED_MACD_EXPIRED,
        )

    late_release: tuple[int, datetime] | None = None
    for future_index in range(start_index + 1, len(macd)):
        bars_after = future_index - start_index
        macd_observation = macd[future_index]
        timestamp = macd_observation.timestamp

        cross = crosses_by_timestamp.get(timestamp)
        if cross is not None and cross.direction != direction:
            return WorkspaceDeferredMacdCandidateOutcome(
                signal_timestamp=record.timestamp,
                direction=direction,
                filter_reason_code=reason_code,
                regime=regime,
                regime_phase=phase,
                armed=True,
                terminal_reason=DEFERRED_MACD_OPPOSITE_CROSS,
            )

        if not _macd_relation_matches(macd_observation, direction):
            return WorkspaceDeferredMacdCandidateOutcome(
                signal_timestamp=record.timestamp,
                direction=direction,
                filter_reason_code=reason_code,
                regime=regime,
                regime_phase=phase,
                armed=True,
                terminal_reason=DEFERRED_MACD_RELATION_INVALID,
            )

        alligator_observation = alligator_by_timestamp.get(timestamp)
        if _alligator_active_opposite(alligator_observation, direction):
            return WorkspaceDeferredMacdCandidateOutcome(
                signal_timestamp=record.timestamp,
                direction=direction,
                filter_reason_code=reason_code,
                regime=regime,
                regime_phase=phase,
                armed=True,
                terminal_reason=DEFERRED_MACD_OPPOSITE_ALLIGATOR,
            )

        if _alligator_active_matches(alligator_observation, direction):
            if bars_after <= expiry_bars:
                return WorkspaceDeferredMacdCandidateOutcome(
                    signal_timestamp=record.timestamp,
                    direction=direction,
                    filter_reason_code=reason_code,
                    regime=regime,
                    regime_phase=phase,
                    armed=True,
                    terminal_reason=DEFERRED_MACD_RELEASED,
                    release_after_bars=bars_after,
                    release_timestamp=timestamp,
                )
            late_release = (bars_after, timestamp)
            break

        if bars_after >= expiry_bars:
            # Продовжуємо тільки діагностично до першого causal release/cancel,
            # щоб окремо побачити клас ``5+`` без зміни production TTL.
            continue

    if late_release is not None:
        return WorkspaceDeferredMacdCandidateOutcome(
            signal_timestamp=record.timestamp,
            direction=direction,
            filter_reason_code=reason_code,
            regime=regime,
            regime_phase=phase,
            armed=True,
            terminal_reason=DEFERRED_MACD_RELEASED,
            release_after_bars=late_release[0],
            release_timestamp=late_release[1],
        )

    return WorkspaceDeferredMacdCandidateOutcome(
        signal_timestamp=record.timestamp,
        direction=direction,
        filter_reason_code=reason_code,
        regime=regime,
        regime_phase=phase,
        armed=True,
        terminal_reason=DEFERRED_MACD_EXPIRED,
    )


def _regime_matches_direction(regime: str | None, direction: str) -> bool:
    if direction == "BUY":
        return regime == ALLIGATOR_REGIME_TREND_UP
    return regime == ALLIGATOR_REGIME_TREND_DOWN


def _macd_relation_matches(
    observation: WorkspaceMacdObservation,
    direction: str,
) -> bool:
    histogram = observation.histogram
    if histogram is None:
        return False
    if direction == "BUY":
        return histogram > 0.0
    return histogram < 0.0


def _alligator_active_matches(
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


def _alligator_active_opposite(
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


def _count_terminal(
    outcomes: tuple[WorkspaceDeferredMacdCandidateOutcome, ...],
    terminal_reason: str,
) -> int:
    return sum(outcome.terminal_reason == terminal_reason for outcome in outcomes)


def _count_release_bar(
    outcomes: tuple[WorkspaceDeferredMacdCandidateOutcome, ...],
    bars_after: int,
) -> int:
    return sum(
        outcome.terminal_reason == DEFERRED_MACD_RELEASED
        and outcome.release_after_bars == bars_after
        for outcome in outcomes
    )
