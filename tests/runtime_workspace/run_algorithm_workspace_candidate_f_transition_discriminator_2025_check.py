# -*- coding: utf-8 -*-
"""RoadMap102: diagnostic discriminator справжнього Alligator transition 2025.

Runner використовує frozen full-OOS transition episodes із 05H і порівнює
GOOD_TRANSITION проти FALSE_OR_MIXED_REVERSAL. На signal bar він вимірює лише
causal ознаки: deterioration normalized opening/slope старого ACTIVE trend,
локальний 8-bar price breakout і структуру signal bar. Окремо, лише як
post-event diagnostic, додає follow-through та зміну Alligator на +1/+2/+3
completed M15 bars.

Майбутні bars не є entry gate, counterfactual trades не створюються, жоден
MACD/Alligator/Candidate F threshold не змінюється. Фіксовані cohort-ознаки
служать лише для порівняння класів і не є production trading rules.
"""

from __future__ import annotations

import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[2]
for path in (PROJECT_ROOT, TEST_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    ALLIGATOR_STATE_BEARISH,
    ALLIGATOR_STATE_BULLISH,
    WorkspaceAlligatorObservation,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from run_algorithm_workspace_candidate_f_alligator_transition_lag_2025_check import (  # noqa: E402,E501
    OUTCOME_FALSE_OR_MIXED,
    OUTCOME_GOOD_TRANSITION,
    TransitionDiagnosticDataset,
    TransitionEpisode,
    build_transition_diagnostic_dataset,
)

EXPECTED_M15_DELTA = timedelta(minutes=15)
REFERENCE_TR_BARS = 64
LOCAL_EXTREMUM_BARS = 8
SIGNAL_RANGE_REFERENCE_BARS = 20


@dataclass(frozen=True, slots=True)
class TransitionFeatures:
    """Read-only signal-time і +1/+2/+3 diagnostic features одного episode."""

    timestamp: datetime
    direction: str
    outcome: str
    old_slope: float
    old_opening: float
    slope_delta_1: float | None
    opening_delta_1: float | None
    slope_delta_2: float | None
    opening_delta_2: float | None
    range_ratio: float
    body_fraction: float
    target_close_location: float
    aligned_body: bool
    wick_break_8: bool
    close_break_8: bool
    breakout_close_tr: float
    follow_1_tr: float | None
    follow_2_tr: float | None
    follow_3_tr: float | None
    slope_change_1: float | None
    slope_change_2: float | None
    slope_change_3: float | None
    opening_change_1: float | None
    opening_change_2: float | None
    opening_change_3: float | None
    leave_old_active_by_3: bool
    target_state_by_3: bool
    target_active_by_3: bool
    old_active_reasserted_by_3: bool


@dataclass(frozen=True, slots=True)
class CohortResult:
    """Одна фіксована diagnostic cohort для GOOD/FALSE contrast."""

    name: str
    matched_good: int
    matched_false: int
    available_good: int
    available_false: int

    @property
    def matched_total(self) -> int:
        return self.matched_good + self.matched_false

    @property
    def good_rate(self) -> float | None:
        if self.matched_total <= 0:
            return None
        return self.matched_good / self.matched_total

    @property
    def good_coverage(self) -> float:
        if self.available_good <= 0:
            return 0.0
        return self.matched_good / self.available_good


FeaturePredicate = Callable[[TransitionFeatures], bool | None]


def _direction_sign(direction: str) -> float:
    if direction == "BUY":
        return 1.0
    if direction == "SELL":
        return -1.0
    raise AssertionError(direction)


def _reference_true_range(
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
) -> float:
    start = max(1, signal_index - REFERENCE_TR_BARS)
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
    result = float(statistics.median(values))
    assert result > 0.0
    return result


def _prior_mean_range(
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
) -> float:
    start = max(0, signal_index - SIGNAL_RANGE_REFERENCE_BARS)
    values = [
        events[index].high - events[index].low
        for index in range(start, signal_index)
    ]
    assert values
    result = statistics.mean(values)
    assert result > 0.0
    return result


def _observation_at_offset(
    episode: TransitionEpisode,
    offset: int,
    *,
    events: tuple[WorkspaceMarketEvent, ...],
    observations_by_timestamp: dict[datetime, WorkspaceAlligatorObservation],
) -> WorkspaceAlligatorObservation | None:
    index = episode.signal_index + offset
    if index < 0 or index >= len(events):
        return None
    low = min(episode.signal_index, index)
    high = max(episode.signal_index, index)
    for current in range(low + 1, high + 1):
        delta = events[current].timestamp - events[current - 1].timestamp
        if delta != EXPECTED_M15_DELTA:
            return None
    return observations_by_timestamp.get(events[index].timestamp)


def _event_at_future_offset(
    episode: TransitionEpisode,
    offset: int,
    *,
    events: tuple[WorkspaceMarketEvent, ...],
) -> WorkspaceMarketEvent | None:
    index = episode.signal_index + offset
    if index < 0 or index >= len(events):
        return None
    for current in range(episode.signal_index + 1, index + 1):
        delta = events[current].timestamp - events[current - 1].timestamp
        if delta != EXPECTED_M15_DELTA:
            return None
    return events[index]


def _old_active_key(direction: str) -> tuple[str, str]:
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


def _is_old_active(
    observation: WorkspaceAlligatorObservation | None,
    direction: str,
) -> bool:
    if observation is None:
        return False
    state, regime = _old_active_key(direction)
    return (
        observation.state == state
        and observation.regime == regime
        and observation.regime_phase == ALLIGATOR_REGIME_PHASE_ACTIVE
    )


def _features_for_episode(
    episode: TransitionEpisode,
    *,
    events: tuple[WorkspaceMarketEvent, ...],
    observations_by_timestamp: dict[datetime, WorkspaceAlligatorObservation],
) -> TransitionFeatures:
    signal_index = episode.signal_index
    signal_event = events[signal_index]
    signal_observation = observations_by_timestamp[episode.signal_timestamp]
    assert signal_observation.normalized_slope is not None
    assert signal_observation.normalized_opening is not None
    reference_tr = _reference_true_range(events, signal_index)
    sign = _direction_sign(episode.target_direction)

    previous_1 = _observation_at_offset(
        episode,
        -1,
        events=events,
        observations_by_timestamp=observations_by_timestamp,
    )
    previous_2 = _observation_at_offset(
        episode,
        -2,
        events=events,
        observations_by_timestamp=observations_by_timestamp,
    )

    def previous_delta(
        observation: WorkspaceAlligatorObservation | None,
        attribute: str,
    ) -> float | None:
        if observation is None:
            return None
        previous_value = getattr(observation, attribute)
        current_value = getattr(signal_observation, attribute)
        if previous_value is None or current_value is None:
            return None
        return float(current_value) - float(previous_value)

    bar_range = signal_event.high - signal_event.low
    assert bar_range > 0.0
    body = signal_event.close - signal_event.open
    body_fraction = abs(body) / bar_range
    aligned_body = sign * body > 0.0
    if episode.target_direction == "BUY":
        target_close_location = (signal_event.close - signal_event.low) / bar_range
    else:
        target_close_location = (signal_event.high - signal_event.close) / bar_range

    prior_start = max(0, signal_index - LOCAL_EXTREMUM_BARS)
    prior_events = events[prior_start:signal_index]
    assert prior_events
    if episode.target_direction == "BUY":
        prior_extreme = max(event.high for event in prior_events)
        wick_break_8 = signal_event.high > prior_extreme
        close_break_8 = signal_event.close > prior_extreme
        breakout_close = signal_event.close - prior_extreme
    else:
        prior_extreme = min(event.low for event in prior_events)
        wick_break_8 = signal_event.low < prior_extreme
        close_break_8 = signal_event.close < prior_extreme
        breakout_close = prior_extreme - signal_event.close

    def follow(offset: int) -> float | None:
        event = _event_at_future_offset(episode, offset, events=events)
        if event is None:
            return None
        return sign * (event.close - signal_event.close) / reference_tr

    def alligator_change(offset: int, attribute: str) -> float | None:
        observation = _observation_at_offset(
            episode,
            offset,
            events=events,
            observations_by_timestamp=observations_by_timestamp,
        )
        if observation is None:
            return None
        value = getattr(observation, attribute)
        signal_value = getattr(signal_observation, attribute)
        if value is None or signal_value is None:
            return None
        return float(value) - float(signal_value)

    observations_1_to_3 = tuple(
        _observation_at_offset(
            episode,
            offset,
            events=events,
            observations_by_timestamp=observations_by_timestamp,
        )
        for offset in (1, 2, 3)
    )
    observation_3 = observations_1_to_3[-1]
    target_state, target_regime = _target_key(episode.target_direction)

    return TransitionFeatures(
        timestamp=episode.signal_timestamp,
        direction=episode.target_direction,
        outcome=episode.outcome,
        old_slope=signal_observation.normalized_slope,
        old_opening=signal_observation.normalized_opening,
        slope_delta_1=previous_delta(previous_1, "normalized_slope"),
        opening_delta_1=previous_delta(previous_1, "normalized_opening"),
        slope_delta_2=previous_delta(previous_2, "normalized_slope"),
        opening_delta_2=previous_delta(previous_2, "normalized_opening"),
        range_ratio=bar_range / _prior_mean_range(events, signal_index),
        body_fraction=body_fraction,
        target_close_location=target_close_location,
        aligned_body=aligned_body,
        wick_break_8=wick_break_8,
        close_break_8=close_break_8,
        breakout_close_tr=breakout_close / reference_tr,
        follow_1_tr=follow(1),
        follow_2_tr=follow(2),
        follow_3_tr=follow(3),
        slope_change_1=alligator_change(1, "normalized_slope"),
        slope_change_2=alligator_change(2, "normalized_slope"),
        slope_change_3=alligator_change(3, "normalized_slope"),
        opening_change_1=alligator_change(1, "normalized_opening"),
        opening_change_2=alligator_change(2, "normalized_opening"),
        opening_change_3=alligator_change(3, "normalized_opening"),
        leave_old_active_by_3=any(
            observation is not None
            and not _is_old_active(observation, episode.target_direction)
            for observation in observations_1_to_3
        ),
        target_state_by_3=any(
            observation is not None and observation.state == target_state
            for observation in observations_1_to_3
        ),
        target_active_by_3=any(
            observation is not None
            and observation.state == target_state
            and observation.regime == target_regime
            and observation.regime_phase == ALLIGATOR_REGIME_PHASE_ACTIVE
            for observation in observations_1_to_3
        ),
        old_active_reasserted_by_3=_is_old_active(
            observation_3,
            episode.target_direction,
        ),
    )


def _numeric_summary(
    items: tuple[TransitionFeatures, ...],
    attribute: str,
) -> tuple[int, float | None, float | None]:
    values = [
        float(value)
        for item in items
        if (value := getattr(item, attribute)) is not None
    ]
    if not values:
        return 0, None, None
    return len(values), statistics.mean(values), statistics.median(values)


def _fmt_number(value: float | None, digits: int = 3) -> str:
    return "NONE" if value is None else f"{value:+.{digits}f}"


def _cohort(
    name: str,
    good: tuple[TransitionFeatures, ...],
    false: tuple[TransitionFeatures, ...],
    predicate: FeaturePredicate,
) -> CohortResult:
    def evaluate(
        items: tuple[TransitionFeatures, ...],
    ) -> tuple[int, int]:
        matched = 0
        available = 0
        for item in items:
            result = predicate(item)
            if result is None:
                continue
            available += 1
            if result:
                matched += 1
        return matched, available

    matched_good, available_good = evaluate(good)
    matched_false, available_false = evaluate(false)
    return CohortResult(
        name=name,
        matched_good=matched_good,
        matched_false=matched_false,
        available_good=available_good,
        available_false=available_false,
    )


def _cohort_line(result: CohortResult) -> str:
    rate = "NONE" if result.good_rate is None else f"{result.good_rate:.3f}"
    return (
        f"    {result.name}: matched={result.matched_total} "
        f"good={result.matched_good} false={result.matched_false} "
        f"good_rate={rate} good_coverage={result.good_coverage:.3f} "
        f"available={result.available_good + result.available_false}"
    )


def _feature_line(item: TransitionFeatures) -> str:
    return (
        f"    {item.timestamp.isoformat()} {item.direction} "
        f"open_d1:{_fmt_number(item.opening_delta_1)} "
        f"slope_d1:{_fmt_number(item.slope_delta_1)} "
        f"range:{item.range_ratio:.2f} body:{item.body_fraction:.2f} "
        f"close_loc:{item.target_close_location:.2f} "
        f"break8:{item.close_break_8} breakout:{item.breakout_close_tr:+.2f}TR "
        f"f1:{_fmt_number(item.follow_1_tr)} "
        f"f2:{_fmt_number(item.follow_2_tr)} "
        f"f3:{_fmt_number(item.follow_3_tr)} "
        f"leave3:{item.leave_old_active_by_3} target3:{item.target_state_by_3}"
    )


def _build_features(
    dataset: TransitionDiagnosticDataset,
) -> tuple[TransitionFeatures, ...]:
    observations_by_timestamp = {
        observation.timestamp: observation for observation in dataset.observations
    }
    return tuple(
        _features_for_episode(
            episode,
            events=dataset.events,
            observations_by_timestamp=observations_by_timestamp,
        )
        for episode in dataset.episodes
    )


def main() -> None:
    dataset = build_transition_diagnostic_dataset()
    features = _build_features(dataset)
    assert len(features) == len(dataset.episodes)

    good = tuple(
        item for item in features if item.outcome == OUTCOME_GOOD_TRANSITION
    )
    false = tuple(
        item for item in features if item.outcome == OUTCOME_FALSE_OR_MIXED
    )
    assert good
    assert false

    baseline_good_rate = len(good) / (len(good) + len(false))

    metrics = (
        "old_slope",
        "old_opening",
        "slope_delta_1",
        "opening_delta_1",
        "slope_delta_2",
        "opening_delta_2",
        "range_ratio",
        "body_fraction",
        "target_close_location",
        "breakout_close_tr",
        "follow_1_tr",
        "follow_2_tr",
        "follow_3_tr",
        "slope_change_1",
        "slope_change_2",
        "slope_change_3",
        "opening_change_1",
        "opening_change_2",
        "opening_change_3",
    )

    cohorts = (
        _cohort(
            "signal_opening_deteriorating",
            good,
            false,
            lambda item: None
            if item.opening_delta_1 is None
            else item.opening_delta_1 < 0.0,
        ),
        _cohort(
            "signal_slope_deteriorating",
            good,
            false,
            lambda item: None
            if item.slope_delta_1 is None
            else item.slope_delta_1 < 0.0,
        ),
        _cohort(
            "signal_both_deteriorating",
            good,
            false,
            lambda item: None
            if item.opening_delta_1 is None or item.slope_delta_1 is None
            else item.opening_delta_1 < 0.0 and item.slope_delta_1 < 0.0,
        ),
        _cohort(
            "signal_wick_break_8",
            good,
            false,
            lambda item: item.wick_break_8,
        ),
        _cohort(
            "signal_close_break_8",
            good,
            false,
            lambda item: item.close_break_8,
        ),
        _cohort(
            "signal_aligned_impulse",
            good,
            false,
            lambda item: (
                item.aligned_body
                and item.body_fraction >= 0.60
                and item.target_close_location >= 0.75
            ),
        ),
        _cohort(
            "follow_1_positive",
            good,
            false,
            lambda item: None if item.follow_1_tr is None else item.follow_1_tr > 0.0,
        ),
        _cohort(
            "follow_2_positive",
            good,
            false,
            lambda item: None if item.follow_2_tr is None else item.follow_2_tr > 0.0,
        ),
        _cohort(
            "follow_3_positive",
            good,
            false,
            lambda item: None if item.follow_3_tr is None else item.follow_3_tr > 0.0,
        ),
        _cohort(
            "follow_1_2_3_all_positive",
            good,
            false,
            lambda item: None
            if (
                item.follow_1_tr is None
                or item.follow_2_tr is None
                or item.follow_3_tr is None
            )
            else (
                item.follow_1_tr > 0.0
                and item.follow_2_tr > 0.0
                and item.follow_3_tr > 0.0
            ),
        ),
        _cohort(
            "leave_old_active_by_3",
            good,
            false,
            lambda item: item.leave_old_active_by_3,
        ),
        _cohort(
            "target_state_by_3",
            good,
            false,
            lambda item: item.target_state_by_3,
        ),
        _cohort(
            "signal_both_deteriorating_and_follow_3_positive",
            good,
            false,
            lambda item: None
            if (
                item.opening_delta_1 is None
                or item.slope_delta_1 is None
                or item.follow_3_tr is None
            )
            else (
                item.opening_delta_1 < 0.0
                and item.slope_delta_1 < 0.0 < item.follow_3_tr
            ),
        ),
        _cohort(
            "signal_close_break_8_and_follow_3_positive",
            good,
            false,
            lambda item: None
            if item.follow_3_tr is None
            else item.close_break_8 and item.follow_3_tr > 0.0,
        ),
    )

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in dataset.runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    print("Algorithm Workspace Candidate F Transition Discriminator 2025 result")
    print("  mode=GOOD_VS_FALSE_CAUSAL_FEATURE_DIAGNOSTIC")
    print(f"  source_transition_episodes={len(features)}")
    print(
        "  contrast="
        f"good:{len(good)},false_or_mixed:{len(false)},"
        f"baseline_good_rate:{baseline_good_rate:.3f}"
    )
    print("  signal_time_metrics:")
    for attribute in metrics[:10]:
        good_n, good_mean, good_median = _numeric_summary(good, attribute)
        false_n, false_mean, false_median = _numeric_summary(false, attribute)
        print(
            f"    {attribute}: "
            f"good=n{good_n}/mean:{_fmt_number(good_mean)}/"
            f"median:{_fmt_number(good_median)} "
            f"false=n{false_n}/mean:{_fmt_number(false_mean)}/"
            f"median:{_fmt_number(false_median)}"
        )
    print("  post_1_3_bar_metrics_diagnostic_only:")
    for attribute in metrics[10:]:
        good_n, good_mean, good_median = _numeric_summary(good, attribute)
        false_n, false_mean, false_median = _numeric_summary(false, attribute)
        print(
            f"    {attribute}: "
            f"good=n{good_n}/mean:{_fmt_number(good_mean)}/"
            f"median:{_fmt_number(good_median)} "
            f"false=n{false_n}/mean:{_fmt_number(false_mean)}/"
            f"median:{_fmt_number(false_median)}"
        )
    print("  fixed_diagnostic_cohorts:")
    for cohort in cohorts:
        print(_cohort_line(cohort))

    best_cohorts = tuple(
        sorted(
            (
                cohort
                for cohort in cohorts
                if cohort.good_rate is not None and cohort.matched_total >= 5
            ),
            key=lambda item: (
                item.good_rate if item.good_rate is not None else -1.0,
                item.matched_good,
            ),
            reverse=True,
        )[:5]
    )
    print("  highest_good_rate_cohorts_min5:")
    for cohort in best_cohorts:
        print(_cohort_line(cohort))

    priority_good = tuple(
        sorted(
            good,
            key=lambda item: (
                item.follow_3_tr if item.follow_3_tr is not None else -999.0,
                item.close_break_8,
            ),
            reverse=True,
        )[:8]
    )
    priority_false = tuple(
        sorted(
            false,
            key=lambda item: (
                item.follow_3_tr if item.follow_3_tr is not None else 999.0,
                item.close_break_8,
            )
        )[:8]
    )
    print("  priority_good_examples:")
    for item in priority_good:
        print(_feature_line(item))
    print("  priority_false_examples:")
    for item in priority_false:
        print(_feature_line(item))

    print("  signal_time_features_use_future=False")
    print("  plus_1_2_3_features_are_post_event_diagnostic=True")
    print("  counterfactual_trades_created=False")
    print("  future_price_used_as_signal_time_gate=False")
    print("  alligator_thresholds_changed=False")
    print("  macd_quality_thresholds_changed=False")
    print("  candidate_f_thresholds_changed=False")
    print("  research_diagnostic_only=True")
    print("  completed_bars_only=True")
    print("  broker_requests=0")
    print(f"  broker_execution_attempted={broker_execution_attempted}")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_TRANSITION_DISCRIMINATOR_2025_CHECK=OK")


if __name__ == "__main__":
    main()
