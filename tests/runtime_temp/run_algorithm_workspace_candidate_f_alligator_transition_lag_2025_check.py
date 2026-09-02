# -*- coding: utf-8 -*-
"""RoadMap102: full-OOS diagnostic lag переходу Alligator за 2025 рік.

Runner бере frozen Candidate F OOS 2025 без зміни production logic і знаходить
MACD Quality PASS у напрямку, протилежному ще ACTIVE старому Alligator trend.
Повторні сигнали всередині одного безперервного old-ACTIVE run об'єднуються
лише в межах одного 32-bar diagnostic horizon. Якщо horizon уже завершився або
перервався market gap, наступний quality signal починає новий episode.

Для кожного episode лише post-event diagnostic вимірює до 32 наступних
завершених M15 bars: вихід зі старого ACTIVE, появу нового directional state,
STARTING і ACTIVE нового trend, повторне повернення старого ACTIVE та
favorable/adverse price excursion у local-TR units. Horizon зупиняється на
першому market gap. Майбутні bars не є entry gate, counterfactual trades не
створюються, MACD/Alligator/Candidate F thresholds залишаються frozen.
"""

from __future__ import annotations

import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[2]
for path in (PROJECT_ROOT, TEST_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import run_algorithm_workspace_candidate_f_frozen_oos_2025_check as frozen  # noqa: E402
from run_algorithm_workspace_candidate_f_trend_coverage_2025_check import (  # noqa: E402,E501
    TrendWindow,
    price_only_trend_candidates,
    strongest_non_overlapping,
)

from core.workspace_algorithm import create_registered_workspace_algorithm  # noqa: E402
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_PHASE_STARTING,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    ALLIGATOR_STATE_BEARISH,
    ALLIGATOR_STATE_BULLISH,
    WorkspaceAlligatorObservation,
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402

TRANSITION_HORIZON_BARS = 32
VOLATILITY_REFERENCE_BARS = 64
EXPECTED_M15_DELTA = timedelta(minutes=15)

OUTCOME_GOOD_TRANSITION = "GOOD_TRANSITION"
OUTCOME_CONFIRMED_MIXED = "CONFIRMED_MIXED_OR_ADVERSE"
OUTCOME_UNCONFIRMED_FAVORABLE = "UNCONFIRMED_FAVORABLE"
OUTCOME_FALSE_OR_MIXED = "FALSE_OR_MIXED_REVERSAL"


@dataclass(frozen=True, slots=True)
class TransitionMilestone:
    """Одна causal milestone після першого opposite MACD Quality PASS."""

    timestamp: datetime
    bars_after_signal: int
    directional_move_tr: float


@dataclass(frozen=True, slots=True)
class TransitionEpisode:
    """Один old-ACTIVE run з одним або кількома opposite quality signals."""

    target_direction: str
    old_direction: str
    signal_timestamp: datetime
    signal_count: int
    signal_index: int
    old_active_slope: float | None
    old_active_opening: float | None
    strong_trend_aligned: bool
    horizon_bars: int
    horizon_stopped_by_gap: bool
    leave_old_active: TransitionMilestone | None
    target_state: TransitionMilestone | None
    target_starting: TransitionMilestone | None
    target_active: TransitionMilestone | None
    old_active_reasserted: TransitionMilestone | None
    endpoint_directional_tr: float
    mfe_tr: float
    mae_tr: float
    outcome: str


def _direction_sign(direction: str) -> float:
    if direction == "BUY":
        return 1.0
    if direction == "SELL":
        return -1.0
    raise AssertionError(direction)


def _old_active_key_for_target(direction: str) -> tuple[str, str]:
    if direction == "BUY":
        return ALLIGATOR_STATE_BEARISH, ALLIGATOR_REGIME_TREND_DOWN
    if direction == "SELL":
        return ALLIGATOR_STATE_BULLISH, ALLIGATOR_REGIME_TREND_UP
    raise AssertionError(direction)


def _target_key(direction: str) -> tuple[str, str]:
    if direction == "BUY":
        return ALLIGATOR_STATE_BULLISH, ALLIGATOR_REGIME_TREND_UP
    if direction == "SELL":
        return ALLIGATOR_STATE_BEARISH, ALLIGATOR_REGIME_TREND_DOWN
    raise AssertionError(direction)


def _is_active(
    observation: WorkspaceAlligatorObservation,
    state: str,
    regime: str,
) -> bool:
    return (
        observation.state == state
        and observation.regime == regime
        and observation.regime_phase == ALLIGATOR_REGIME_PHASE_ACTIVE
    )


def _reference_true_range(
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
) -> float:
    """Повернути median true range 64 завершених M15 bars до signal."""
    start = max(1, signal_index - VOLATILITY_REFERENCE_BARS)
    values: list[float] = []
    for index in range(start, signal_index):
        event = events[index]
        previous_close = events[index - 1].close
        values.append(
            max(
                event.high - event.low,
                abs(event.high - previous_close),
                abs(event.low - previous_close),
            )
        )
    assert values
    reference = float(statistics.median(values))
    assert reference > 0.0
    return reference


def _horizon_end_index(
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
) -> tuple[int, bool]:
    """Обмежити post-event horizon 32 bars і не перетинати market gap."""
    maximum = min(signal_index + TRANSITION_HORIZON_BARS, len(events) - 1)
    for index in range(signal_index + 1, maximum + 1):
        if events[index].timestamp - events[index - 1].timestamp != EXPECTED_M15_DELTA:
            return index - 1, True
    return maximum, False


def _strong_aligned(
    timestamp: datetime,
    direction: str,
    windows: tuple[TrendWindow, ...],
    events: tuple[WorkspaceMarketEvent, ...],
) -> bool:
    return any(
        window.direction == direction
        and events[window.start_index].timestamp
        <= timestamp
        <= events[window.end_index].timestamp
        for window in windows
    )


def _milestone(
    observation: WorkspaceAlligatorObservation,
    *,
    signal_index: int,
    event_index_by_timestamp: dict[datetime, int],
    events: tuple[WorkspaceMarketEvent, ...],
    sign: float,
    reference_tr: float,
) -> TransitionMilestone:
    event_index = event_index_by_timestamp[observation.timestamp]
    signal_close = events[signal_index].close
    move_tr = sign * (events[event_index].close - signal_close) / reference_tr
    return TransitionMilestone(
        timestamp=observation.timestamp,
        bars_after_signal=event_index - signal_index,
        directional_move_tr=move_tr,
    )


def _first_observation(
    observations: tuple[WorkspaceAlligatorObservation, ...],
    predicate,
) -> WorkspaceAlligatorObservation | None:
    for observation in observations:
        if predicate(observation):
            return observation
    return None


def _active_run_ids(
    observations: tuple[WorkspaceAlligatorObservation, ...],
) -> dict[datetime, int]:
    """Присвоїти id кожному безперервному directional ACTIVE run."""
    result: dict[datetime, int] = {}
    run_id = 0
    previous_key: tuple[str, str] | None = None
    for observation in observations:
        key: tuple[str, str] | None = None
        if observation.regime_phase == ALLIGATOR_REGIME_PHASE_ACTIVE:
            if (
                observation.state == ALLIGATOR_STATE_BULLISH
                and observation.regime == ALLIGATOR_REGIME_TREND_UP
            ):
                key = observation.state, observation.regime
            elif (
                observation.state == ALLIGATOR_STATE_BEARISH
                and observation.regime == ALLIGATOR_REGIME_TREND_DOWN
            ):
                key = observation.state, observation.regime
        if key is not None:
            if key != previous_key:
                run_id += 1
            result[observation.timestamp] = run_id
        previous_key = key
    return result


def _qualifying_opposite_records(
    records: tuple[WorkspaceSignalRecord, ...],
) -> tuple[WorkspaceSignalRecord, ...]:
    """Вибрати Quality PASS проти causal ACTIVE старого Alligator trend."""
    selected: list[WorkspaceSignalRecord] = []
    for record in records:
        if record.source_reason_code != "MACD_CROSS_ACCEPTED":
            continue
        context = record.filter_context
        if context is None:
            continue
        old_state, old_regime = _old_active_key_for_target(record.direction)
        if (
            context.regime == old_regime
            and context.regime_phase == ALLIGATOR_REGIME_PHASE_ACTIVE
            and (
                (
                    old_state == ALLIGATOR_STATE_BULLISH
                    and record.alligator_confirmation == "SAME_TIMEFRAME_BULLISH"
                )
                or (
                    old_state == ALLIGATOR_STATE_BEARISH
                    and record.alligator_confirmation == "SAME_TIMEFRAME_BEARISH"
                )
            )
        ):
            selected.append(record)
    return tuple(selected)


def _split_episode_records(
    records: list[WorkspaceSignalRecord],
    *,
    events: tuple[WorkspaceMarketEvent, ...],
    event_index_by_timestamp: dict[datetime, int],
) -> tuple[tuple[WorkspaceSignalRecord, ...], ...]:
    """Розділити один old-ACTIVE run на causal 32-bar signal episodes."""
    ordered = sorted(records, key=lambda item: item.timestamp)
    clusters: list[tuple[WorkspaceSignalRecord, ...]] = []
    current: list[WorkspaceSignalRecord] = []
    current_horizon_end = -1

    for record in ordered:
        signal_index = event_index_by_timestamp[record.timestamp]
        if not current or signal_index > current_horizon_end:
            if current:
                clusters.append(tuple(current))
            current = [record]
            current_horizon_end, _ = _horizon_end_index(events, signal_index)
        else:
            current.append(record)

    if current:
        clusters.append(tuple(current))
    return tuple(clusters)


def _episode_from_records(
    episode_records: tuple[WorkspaceSignalRecord, ...],
    *,
    observations_by_timestamp: dict[datetime, WorkspaceAlligatorObservation],
    observations: tuple[WorkspaceAlligatorObservation, ...],
    event_index_by_timestamp: dict[datetime, int],
    events: tuple[WorkspaceMarketEvent, ...],
    strong_windows: tuple[TrendWindow, ...],
) -> TransitionEpisode:
    first = min(episode_records, key=lambda item: item.timestamp)
    signal_index = event_index_by_timestamp[first.timestamp]
    horizon_end, stopped_by_gap = _horizon_end_index(events, signal_index)
    horizon_end_timestamp = events[horizon_end].timestamp
    post_observations = tuple(
        observation
        for observation in observations
        if first.timestamp <= observation.timestamp <= horizon_end_timestamp
    )
    assert post_observations

    old_state, old_regime = _old_active_key_for_target(first.direction)
    target_state, target_regime = _target_key(first.direction)
    first_observation = observations_by_timestamp[first.timestamp]
    assert _is_active(first_observation, old_state, old_regime)

    leave_old = _first_observation(
        post_observations[1:],
        lambda observation: not _is_active(observation, old_state, old_regime),
    )
    new_state = _first_observation(
        post_observations[1:],
        lambda observation: observation.state == target_state,
    )
    new_starting = _first_observation(
        post_observations[1:],
        lambda observation: (
            observation.state == target_state
            and observation.regime == target_regime
            and observation.regime_phase == ALLIGATOR_REGIME_PHASE_STARTING
        ),
    )
    new_active = _first_observation(
        post_observations[1:],
        lambda observation: _is_active(
            observation,
            target_state,
            target_regime,
        ),
    )

    reassert_search: tuple[WorkspaceAlligatorObservation, ...] = ()
    if leave_old is not None:
        reassert_search = tuple(
            observation
            for observation in post_observations
            if observation.timestamp > leave_old.timestamp
            and (new_active is None or observation.timestamp < new_active.timestamp)
        )
    old_reasserted = _first_observation(
        reassert_search,
        lambda observation: _is_active(observation, old_state, old_regime),
    )

    reference_tr = _reference_true_range(events, signal_index)
    sign = _direction_sign(first.direction)
    signal_close = events[signal_index].close
    future = events[signal_index : horizon_end + 1]  # noqa
    if first.direction == "BUY":
        favorable = max(event.high for event in future) - signal_close
        adverse = signal_close - min(event.low for event in future)
    else:
        favorable = signal_close - min(event.low for event in future)
        adverse = max(event.high for event in future) - signal_close
    endpoint_move = sign * (events[horizon_end].close - signal_close)
    endpoint_directional_tr = endpoint_move / reference_tr
    mfe_tr = favorable / reference_tr
    mae_tr = adverse / reference_tr
    price_favorable = endpoint_directional_tr > 0.0 and mfe_tr > mae_tr

    if new_active is not None and price_favorable:
        outcome = OUTCOME_GOOD_TRANSITION
    elif new_active is not None:
        outcome = OUTCOME_CONFIRMED_MIXED
    elif price_favorable:
        outcome = OUTCOME_UNCONFIRMED_FAVORABLE
    else:
        outcome = OUTCOME_FALSE_OR_MIXED

    context = first.filter_context
    assert context is not None

    def make_milestone(
        observation: WorkspaceAlligatorObservation | None,
    ) -> TransitionMilestone | None:
        if observation is None:
            return None
        return _milestone(
            observation,
            signal_index=signal_index,
            event_index_by_timestamp=event_index_by_timestamp,
            events=events,
            sign=sign,
            reference_tr=reference_tr,
        )

    return TransitionEpisode(
        target_direction=first.direction,
        old_direction="SELL" if first.direction == "BUY" else "BUY",
        signal_timestamp=first.timestamp,
        signal_count=len(episode_records),
        signal_index=signal_index,
        old_active_slope=context.normalized_slope,
        old_active_opening=context.normalized_opening,
        strong_trend_aligned=_strong_aligned(
            first.timestamp,
            first.direction,
            strong_windows,
            events,
        ),
        horizon_bars=horizon_end - signal_index,
        horizon_stopped_by_gap=stopped_by_gap,
        leave_old_active=make_milestone(leave_old),
        target_state=make_milestone(new_state),
        target_starting=make_milestone(new_starting),
        target_active=make_milestone(new_active),
        old_active_reasserted=make_milestone(old_reasserted),
        endpoint_directional_tr=endpoint_directional_tr,
        mfe_tr=mfe_tr,
        mae_tr=mae_tr,
        outcome=outcome,
    )


def _count(episodes: tuple[TransitionEpisode, ...], attribute: str) -> int:
    return sum(getattr(episode, attribute) is not None for episode in episodes)


def _average_delay(
    episodes: tuple[TransitionEpisode, ...],
    attribute: str,
) -> float | None:
    values = [
        milestone.bars_after_signal
        for episode in episodes
        if (milestone := getattr(episode, attribute)) is not None
    ]
    return statistics.mean(values) if values else None


def _fmt_optional(value: float | None, digits: int = 3) -> str:
    return "NONE" if value is None else f"{value:.{digits}f}"


def _episode_line(index: int, episode: TransitionEpisode) -> str:
    active = episode.target_active
    active_delay = "NONE" if active is None else str(active.bars_after_signal)
    active_move = "NONE" if active is None else f"{active.directional_move_tr:+.2f}TR"
    return (
        f"    {index:02d}. {episode.signal_timestamp.isoformat()} "
        f"{episode.target_direction} signals:{episode.signal_count} "
        f"strong:{episode.strong_trend_aligned} active_delay:{active_delay} "
        f"move_at_active:{active_move} "
        f"endpoint:{episode.endpoint_directional_tr:+.2f}TR "
        f"mfe:{episode.mfe_tr:.2f}TR mae:{episode.mae_tr:.2f}TR "
        f"reassert:{episode.old_active_reasserted is not None} "
        f"outcome:{episode.outcome}"
    )


@dataclass(frozen=True, slots=True)
class TransitionDiagnosticDataset:
    """Повний read-only набір causal transition diagnostic за frozen OOS 2025."""

    runtime: frozen.FrozenOosRuntime
    events: tuple[WorkspaceMarketEvent, ...]
    observations: tuple[WorkspaceAlligatorObservation, ...]
    episodes: tuple[TransitionEpisode, ...]
    opposite_records: tuple[WorkspaceSignalRecord, ...]


def build_transition_diagnostic_dataset() -> TransitionDiagnosticDataset:
    """Побудувати frozen 2025 transition episodes без counterfactual trading."""
    frozen.assert_frozen_oos_snapshot()

    runtime = frozen.FrozenOosRuntime(
        frozen.frozen_oos_workspace(),
        algorithm_factory=create_registered_workspace_algorithm,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    events = session.events
    assert events

    strong_windows = strongest_non_overlapping(price_only_trend_candidates(events))

    while not session.completed:
        runtime.advance_replay()

    algorithm = runtime.algorithm
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    signal_filter = algorithm.signal_filter
    assert signal_filter is not None
    observations = signal_filter.observations
    assert observations

    records = runtime.historical_signal_records_for_test()
    opposite_records = _qualifying_opposite_records(records)
    assert opposite_records

    observations_by_timestamp = {
        observation.timestamp: observation for observation in observations
    }
    event_index_by_timestamp = {
        event.timestamp: index for index, event in enumerate(events)
    }
    run_ids = _active_run_ids(observations)

    grouped: dict[tuple[int, str], list[WorkspaceSignalRecord]] = defaultdict(list)
    for record in opposite_records:
        assert record.timestamp in observations_by_timestamp
        run_id = run_ids.get(record.timestamp)
        assert run_id is not None
        grouped[(run_id, record.direction)].append(record)

    episode_record_groups = tuple(
        cluster
        for group_records in grouped.values()
        for cluster in _split_episode_records(
            group_records,
            events=events,
            event_index_by_timestamp=event_index_by_timestamp,
        )
    )
    episodes = tuple(
        sorted(
            (
                _episode_from_records(
                    episode_records,
                    observations_by_timestamp=observations_by_timestamp,
                    observations=observations,
                    event_index_by_timestamp=event_index_by_timestamp,
                    events=events,
                    strong_windows=strong_windows,
                )
                for episode_records in episode_record_groups
            ),
            key=lambda item: item.signal_timestamp,
        )
    )
    assert episodes

    return TransitionDiagnosticDataset(
        runtime=runtime,
        events=events,
        observations=observations,
        episodes=episodes,
        opposite_records=opposite_records,
    )


def main() -> None:
    dataset = build_transition_diagnostic_dataset()
    runtime = dataset.runtime
    episodes = dataset.episodes
    opposite_records = dataset.opposite_records

    outcome_counts = {
        outcome: sum(episode.outcome == outcome for episode in episodes)
        for outcome in (
            OUTCOME_GOOD_TRANSITION,
            OUTCOME_CONFIRMED_MIXED,
            OUTCOME_UNCONFIRMED_FAVORABLE,
            OUTCOME_FALSE_OR_MIXED,
        )
    }
    strong_episodes = tuple(
        episode for episode in episodes if episode.strong_trend_aligned
    )
    confirmed = tuple(
        episode for episode in episodes if episode.target_active is not None
    )
    unconfirmed = tuple(
        episode for episode in episodes if episode.target_active is None
    )
    reasserted = tuple(
        episode for episode in episodes if episode.old_active_reasserted is not None
    )

    priority_confirmed = tuple(
        sorted(
            confirmed,
            key=lambda item: (
                item.strong_trend_aligned,
                item.endpoint_directional_tr,
                item.mfe_tr - item.mae_tr,
            ),
            reverse=True,
        )[:10]
    )
    priority_false = tuple(
        sorted(
            unconfirmed,
            key=lambda item: (
                item.strong_trend_aligned,
                item.mae_tr - item.mfe_tr,
                -item.endpoint_directional_tr,
            ),
            reverse=True,
        )[:10]
    )

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    print("Algorithm Workspace Candidate F Alligator Transition Lag 2025 result")
    print("  mode=FULL_OOS_CAUSAL_TRANSITION_DIAGNOSTIC")
    print(f"  transition_horizon_bars={TRANSITION_HORIZON_BARS}")
    print(f"  volatility_reference_bars={VOLATILITY_REFERENCE_BARS}")
    print("  horizon_stops_at_market_gap=True")
    print(f"  opposite_quality_pass_signals={len(opposite_records)}")
    print(f"  unique_old_active_episodes={len(episodes)}")
    print(
        "  direction_counts="
        f"buy:{sum(item.target_direction == 'BUY' for item in episodes)},"
        f"sell:{sum(item.target_direction == 'SELL' for item in episodes)}"
    )
    print(
        "  milestone_reach="
        f"leave_old_active:{_count(episodes, 'leave_old_active')},"
        f"target_state:{_count(episodes, 'target_state')},"
        f"target_starting:{_count(episodes, 'target_starting')},"
        f"target_active:{_count(episodes, 'target_active')},"
        f"old_active_reasserted:{len(reasserted)}"
    )
    print(
        "  average_delay_bars="
        "leave_old_active:"
        f"{_fmt_optional(_average_delay(episodes, 'leave_old_active'))},"
        f"target_state:{_fmt_optional(_average_delay(episodes, 'target_state'))},"
        f"target_starting:{_fmt_optional(_average_delay(episodes, 'target_starting'))},"
        f"target_active:{_fmt_optional(_average_delay(episodes, 'target_active'))}"
    )
    print(
        "  outcome_counts="
        f"good_transition:{outcome_counts[OUTCOME_GOOD_TRANSITION]},"
        f"confirmed_mixed_or_adverse:{outcome_counts[OUTCOME_CONFIRMED_MIXED]},"
        f"unconfirmed_favorable:{outcome_counts[OUTCOME_UNCONFIRMED_FAVORABLE]},"
        f"false_or_mixed:{outcome_counts[OUTCOME_FALSE_OR_MIXED]}"
    )
    print(
        "  strong_trend_membership="
        f"aligned_episodes:{len(strong_episodes)},"
        f"outside:{len(episodes) - len(strong_episodes)}"
    )
    print(
        "  horizon_gap_truncation="
        f"{sum(item.horizon_stopped_by_gap for item in episodes)}"
    )
    if confirmed:
        confirmed_endpoint = statistics.mean(
            item.endpoint_directional_tr for item in confirmed
        )
        confirmed_mfe = statistics.mean(item.mfe_tr for item in confirmed)
        confirmed_mae = statistics.mean(item.mae_tr for item in confirmed)
        print(
            "  confirmed_price_average="
            f"endpoint:{confirmed_endpoint:+.3f}TR,"
            f"mfe:{confirmed_mfe:.3f}TR,"
            f"mae:{confirmed_mae:.3f}TR"
        )
    if unconfirmed:
        unconfirmed_endpoint = statistics.mean(
            item.endpoint_directional_tr for item in unconfirmed
        )
        unconfirmed_mfe = statistics.mean(item.mfe_tr for item in unconfirmed)
        unconfirmed_mae = statistics.mean(item.mae_tr for item in unconfirmed)
        print(
            "  unconfirmed_price_average="
            f"endpoint:{unconfirmed_endpoint:+.3f}TR,"
            f"mfe:{unconfirmed_mfe:.3f}TR,"
            f"mae:{unconfirmed_mae:.3f}TR"
        )

    print("  priority_confirmed_episodes:")
    for index, episode in enumerate(priority_confirmed, start=1):
        print(_episode_line(index, episode))
    print("  priority_unconfirmed_or_false_episodes:")
    for index, episode in enumerate(priority_false, start=1):
        print(_episode_line(index, episode))

    print("  counterfactual_trades_created=False")
    print("  future_price_used_as_entry_gate=False")
    print("  alligator_thresholds_changed=False")
    print("  macd_quality_thresholds_changed=False")
    print("  candidate_f_thresholds_changed=False")
    print("  research_diagnostic_only=True")
    print("  completed_bars_only=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_ALLIGATOR_TRANSITION_LAG_2025_CHECK=OK")


if __name__ == "__main__":
    main()
