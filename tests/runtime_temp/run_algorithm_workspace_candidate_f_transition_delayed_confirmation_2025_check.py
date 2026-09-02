# -*- coding: utf-8 -*-
"""RoadMap102: causal delayed transition confirmation diagnostic за 2025 рік.

Runner бере frozen transition episodes із 05H і порівнює лише чисті класи
GOOD_TRANSITION та FALSE_OR_MIXED_REVERSAL. Після первинного opposite MACD
Quality PASS перевіряються чотири наперед зафіксовані causal variants:
D1/D2/D3 — directional close follow-through через 1/2/3 завершені M15 bars,
D3+S — D3 разом із deterioration slope старого Alligator вже на signal bar.

Для кожного variant вимірюється precision/coverage, скільки directional move
уже пройдено до confirmation, скільки endpoint/MFE потенціалу лишається після
confirmation, post-confirmation MAE та повторне відновлення старого ACTIVE.
Future outcome не є entry gate, counterfactual trades не створюються, жоден
MACD/Alligator/Candidate F threshold не змінюється.
"""

from __future__ import annotations

import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[2]
for path in (PROJECT_ROOT, TEST_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from run_algorithm_workspace_candidate_f_alligator_transition_lag_2025_check import (  # noqa: E402,E501
    OUTCOME_FALSE_OR_MIXED,
    OUTCOME_GOOD_TRANSITION,
    TransitionDiagnosticDataset,
    TransitionEpisode,
    build_transition_diagnostic_dataset,
)

from core.workspace_alligator import WorkspaceAlligatorObservation  # noqa: E402
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402

EXPECTED_M15_DELTA = timedelta(minutes=15)
REFERENCE_TR_BARS = 64


@dataclass(frozen=True, slots=True)
class DelayedConfirmationCase:
    """Один causal confirmation одного transition episode."""

    variant: str
    timestamp: datetime
    direction: str
    outcome: str
    delay_bars: int
    confirmation_move_tr: float
    endpoint_remaining_tr: float
    post_confirmation_mfe_tr: float
    post_confirmation_mae_tr: float
    old_active_reasserted_after_confirmation: bool
    horizon_stopped_by_gap: bool


@dataclass(frozen=True, slots=True)
class VariantSummary:
    """Підсумок одного fixed delayed-confirmation variant."""

    name: str
    delay_bars: int
    available_good: int
    available_false: int
    matched_good: int
    matched_false: int
    buy_good: int
    buy_false: int
    sell_good: int
    sell_false: int
    gap_truncated_available: int
    gap_truncated_matched: int
    good_confirmation_move_mean: float | None
    false_confirmation_move_mean: float | None
    good_endpoint_remaining_mean: float | None
    false_endpoint_remaining_mean: float | None
    good_mfe_remaining_mean: float | None
    false_mfe_remaining_mean: float | None
    good_mae_after_mean: float | None
    false_mae_after_mean: float | None
    good_reassert_after: int
    false_reassert_after: int

    @property
    def matched_total(self) -> int:
        return self.matched_good + self.matched_false

    @property
    def available_total(self) -> int:
        return self.available_good + self.available_false

    @property
    def good_rate(self) -> float | None:
        if self.matched_total == 0:
            return None
        return self.matched_good / self.matched_total

    @property
    def good_coverage(self) -> float:
        if self.available_good == 0:
            return 0.0
        return self.matched_good / self.available_good


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


def _continuous_to_delay(
    episode: TransitionEpisode,
    delay_bars: int,
    events: tuple[WorkspaceMarketEvent, ...],
) -> bool:
    if episode.horizon_bars < delay_bars:
        return False
    end_index = episode.signal_index + delay_bars
    for index in range(episode.signal_index + 1, end_index + 1):
        if events[index].timestamp - events[index - 1].timestamp != EXPECTED_M15_DELTA:
            return False
    return True


def _signal_slope_deteriorating(
    episode: TransitionEpisode,
    *,
    events: tuple[WorkspaceMarketEvent, ...],
    observations_by_timestamp: dict[datetime, WorkspaceAlligatorObservation],
) -> bool | None:
    if episode.signal_index <= 0:
        return None
    signal_event = events[episode.signal_index]
    previous_event = events[episode.signal_index - 1]
    if signal_event.timestamp - previous_event.timestamp != EXPECTED_M15_DELTA:
        return None
    current = observations_by_timestamp.get(signal_event.timestamp)
    previous = observations_by_timestamp.get(previous_event.timestamp)
    if current is None or previous is None:
        return None
    if current.normalized_slope is None or previous.normalized_slope is None:
        return None
    return current.normalized_slope - previous.normalized_slope < 0.0


def _variant_matches(
    variant: str,
    episode: TransitionEpisode,
    *,
    delay_bars: int,
    events: tuple[WorkspaceMarketEvent, ...],
    observations_by_timestamp: dict[datetime, WorkspaceAlligatorObservation],
) -> bool | None:
    if not _continuous_to_delay(episode, delay_bars, events):
        return None
    sign = _direction_sign(episode.target_direction)
    signal_close = events[episode.signal_index].close
    confirmation_close = events[episode.signal_index + delay_bars].close
    follow_through = sign * (confirmation_close - signal_close) > 0.0
    if variant != "D3+S":
        return follow_through
    slope_deteriorating = _signal_slope_deteriorating(
        episode,
        events=events,
        observations_by_timestamp=observations_by_timestamp,
    )
    if slope_deteriorating is None:
        return None
    return follow_through and slope_deteriorating


def _confirmation_case(
    variant: str,
    episode: TransitionEpisode,
    *,
    delay_bars: int,
    events: tuple[WorkspaceMarketEvent, ...],
) -> DelayedConfirmationCase:
    reference_tr = _reference_true_range(events, episode.signal_index)
    sign = _direction_sign(episode.target_direction)
    signal_close = events[episode.signal_index].close
    confirmation_index = episode.signal_index + delay_bars
    confirmation_close = events[confirmation_index].close
    horizon_end_index = episode.signal_index + episode.horizon_bars
    assert confirmation_index <= horizon_end_index

    future = events[confirmation_index : horizon_end_index + 1]  # noqa
    if episode.target_direction == "BUY":
        favorable = max(event.high for event in future) - confirmation_close
        adverse = confirmation_close - min(event.low for event in future)
    else:
        favorable = confirmation_close - min(event.low for event in future)
        adverse = max(event.high for event in future) - confirmation_close

    endpoint_remaining = (
        sign * (events[horizon_end_index].close - confirmation_close) / reference_tr
    )
    confirmation_move = sign * (confirmation_close - signal_close) / reference_tr
    reasserted = episode.old_active_reasserted
    reasserted_after = (
        reasserted is not None and reasserted.bars_after_signal > delay_bars
    )

    return DelayedConfirmationCase(
        variant=variant,
        timestamp=episode.signal_timestamp,
        direction=episode.target_direction,
        outcome=episode.outcome,
        delay_bars=delay_bars,
        confirmation_move_tr=confirmation_move,
        endpoint_remaining_tr=endpoint_remaining,
        post_confirmation_mfe_tr=favorable / reference_tr,
        post_confirmation_mae_tr=adverse / reference_tr,
        old_active_reasserted_after_confirmation=reasserted_after,
        horizon_stopped_by_gap=episode.horizon_stopped_by_gap,
    )


def _mean_or_none(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def _summary_for_variant(
    name: str,
    delay_bars: int,
    *,
    episodes: tuple[TransitionEpisode, ...],
    events: tuple[WorkspaceMarketEvent, ...],
    observations_by_timestamp: dict[datetime, WorkspaceAlligatorObservation],
) -> tuple[VariantSummary, tuple[DelayedConfirmationCase, ...]]:
    available_good = 0
    available_false = 0
    gap_truncated_available = 0
    cases: list[DelayedConfirmationCase] = []

    for episode in episodes:
        if episode.outcome not in (OUTCOME_GOOD_TRANSITION, OUTCOME_FALSE_OR_MIXED):
            continue
        matched = _variant_matches(
            name,
            episode,
            delay_bars=delay_bars,
            events=events,
            observations_by_timestamp=observations_by_timestamp,
        )
        if matched is None:
            continue
        if episode.outcome == OUTCOME_GOOD_TRANSITION:
            available_good += 1
        else:
            available_false += 1
        if episode.horizon_stopped_by_gap:
            gap_truncated_available += 1
        if not matched:
            continue
        cases.append(
            _confirmation_case(
                name,
                episode,
                delay_bars=delay_bars,
                events=events,
            )
        )

    good = [item for item in cases if item.outcome == OUTCOME_GOOD_TRANSITION]
    false = [item for item in cases if item.outcome == OUTCOME_FALSE_OR_MIXED]

    summary = VariantSummary(
        name=name,
        delay_bars=delay_bars,
        available_good=available_good,
        available_false=available_false,
        matched_good=len(good),
        matched_false=len(false),
        buy_good=sum(item.direction == "BUY" for item in good),
        buy_false=sum(item.direction == "BUY" for item in false),
        sell_good=sum(item.direction == "SELL" for item in good),
        sell_false=sum(item.direction == "SELL" for item in false),
        gap_truncated_available=gap_truncated_available,
        gap_truncated_matched=sum(item.horizon_stopped_by_gap for item in cases),
        good_confirmation_move_mean=_mean_or_none(
            [item.confirmation_move_tr for item in good]
        ),
        false_confirmation_move_mean=_mean_or_none(
            [item.confirmation_move_tr for item in false]
        ),
        good_endpoint_remaining_mean=_mean_or_none(
            [item.endpoint_remaining_tr for item in good]
        ),
        false_endpoint_remaining_mean=_mean_or_none(
            [item.endpoint_remaining_tr for item in false]
        ),
        good_mfe_remaining_mean=_mean_or_none(
            [item.post_confirmation_mfe_tr for item in good]
        ),
        false_mfe_remaining_mean=_mean_or_none(
            [item.post_confirmation_mfe_tr for item in false]
        ),
        good_mae_after_mean=_mean_or_none(
            [item.post_confirmation_mae_tr for item in good]
        ),
        false_mae_after_mean=_mean_or_none(
            [item.post_confirmation_mae_tr for item in false]
        ),
        good_reassert_after=sum(
            item.old_active_reasserted_after_confirmation for item in good
        ),
        false_reassert_after=sum(
            item.old_active_reasserted_after_confirmation for item in false
        ),
    )
    return summary, tuple(cases)


def _fmt(value: float | None) -> str:
    return "NONE" if value is None else f"{value:+.3f}"


def _summary_lines(summary: VariantSummary) -> tuple[str, ...]:
    rate = "NONE" if summary.good_rate is None else f"{summary.good_rate:.3f}"
    return (
        f"  {summary.name}: delay_bars={summary.delay_bars} "
        f"available={summary.available_total} matched={summary.matched_total} "
        f"good={summary.matched_good} false={summary.matched_false} "
        f"good_rate={rate} good_coverage={summary.good_coverage:.3f}",
        "    direction="
        f"BUY good/false:{summary.buy_good}/{summary.buy_false},"
        f"SELL good/false:{summary.sell_good}/{summary.sell_false}",
        "    confirmation_move_mean="
        f"good:{_fmt(summary.good_confirmation_move_mean)}TR,"
        f"false:{_fmt(summary.false_confirmation_move_mean)}TR",
        "    endpoint_remaining_mean="
        f"good:{_fmt(summary.good_endpoint_remaining_mean)}TR,"
        f"false:{_fmt(summary.false_endpoint_remaining_mean)}TR",
        "    post_confirmation_mfe_mean="
        f"good:{_fmt(summary.good_mfe_remaining_mean)}TR,"
        f"false:{_fmt(summary.false_mfe_remaining_mean)}TR",
        "    post_confirmation_mae_mean="
        f"good:{_fmt(summary.good_mae_after_mean)}TR,"
        f"false:{_fmt(summary.false_mae_after_mean)}TR",
        "    old_active_reasserted_after_confirmation="
        f"good:{summary.good_reassert_after},false:{summary.false_reassert_after}",
        "    gap_truncated="
        f"available:{summary.gap_truncated_available},"
        f"matched:{summary.gap_truncated_matched}",
    )


def _priority_line(item: DelayedConfirmationCase) -> str:
    return (
        f"    {item.timestamp.isoformat()} {item.direction} {item.variant} "
        f"confirm:{item.confirmation_move_tr:+.2f}TR "
        f"endpoint_left:{item.endpoint_remaining_tr:+.2f}TR "
        f"mfe_left:{item.post_confirmation_mfe_tr:.2f}TR "
        f"mae_after:{item.post_confirmation_mae_tr:.2f}TR "
        f"reassert:{item.old_active_reasserted_after_confirmation} "
        f"gap:{item.horizon_stopped_by_gap} outcome:{item.outcome}"
    )


def main() -> None:
    dataset: TransitionDiagnosticDataset = build_transition_diagnostic_dataset()
    observations_by_timestamp = {
        observation.timestamp: observation for observation in dataset.observations
    }
    contrast_episodes = tuple(
        episode
        for episode in dataset.episodes
        if episode.outcome in (OUTCOME_GOOD_TRANSITION, OUTCOME_FALSE_OR_MIXED)
    )
    assert contrast_episodes
    good_total = sum(
        episode.outcome == OUTCOME_GOOD_TRANSITION for episode in contrast_episodes
    )
    false_total = sum(
        episode.outcome == OUTCOME_FALSE_OR_MIXED for episode in contrast_episodes
    )
    assert good_total == 34
    assert false_total == 75

    variants = (
        ("D1", 1),
        ("D2", 2),
        ("D3", 3),
        ("D3+S", 3),
    )
    results = tuple(
        _summary_for_variant(
            name,
            delay_bars,
            episodes=contrast_episodes,
            events=dataset.events,
            observations_by_timestamp=observations_by_timestamp,
        )
        for name, delay_bars in variants
    )

    summaries = tuple(item[0] for item in results)
    cases_by_variant = {summary.name: cases for summary, cases in results}

    assert summaries[0].matched_good == 23
    assert summaries[0].matched_false == 31
    assert summaries[1].matched_good == 23
    assert summaries[1].matched_false == 27
    assert summaries[2].matched_good == 25
    assert summaries[2].matched_false == 21
    assert summaries[3].matched_total <= summaries[2].matched_total

    d3_good = tuple(
        item
        for item in cases_by_variant["D3"]
        if item.outcome == OUTCOME_GOOD_TRANSITION
    )
    d3_false = tuple(
        item
        for item in cases_by_variant["D3"]
        if item.outcome == OUTCOME_FALSE_OR_MIXED
    )
    priority_good = tuple(
        sorted(
            d3_good,
            key=lambda item: (
                item.post_confirmation_mfe_tr - item.post_confirmation_mae_tr,
                item.endpoint_remaining_tr,
            ),
            reverse=True,
        )[:8]
    )
    priority_false = tuple(
        sorted(
            d3_false,
            key=lambda item: (
                item.post_confirmation_mae_tr - item.post_confirmation_mfe_tr,
                -item.endpoint_remaining_tr,
            ),
            reverse=True,
        )[:8]
    )

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in dataset.runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    print("Algorithm Workspace Candidate F Transition Delayed Confirmation 2025 result")
    print("  mode=FIXED_CAUSAL_D1_D2_D3_DIAGNOSTIC_ONLY")
    print(
        "  contrast="
        f"good:{good_total},false_or_mixed:{false_total},"
        f"baseline_good_rate:{good_total / (good_total + false_total):.3f}"
    )
    print(
        "  variants="
        "D1:+1 close directional;D2:+2 close directional;"
        "D3:+3 close directional;D3+S:D3 + signal slope deterioration"
    )
    print("  confirmation_uses_completed_m15_bars_only=True")
    for summary in summaries:
        for line in _summary_lines(summary):
            print(line)

    print("  priority_d3_good_examples:")
    for item in priority_good:
        print(_priority_line(item))
    print("  priority_d3_false_examples:")
    for item in priority_false:
        print(_priority_line(item))

    print("  counterfactual_trades_created=False")
    print("  future_outcome_used_as_confirmation_gate=False")
    print("  alligator_thresholds_changed=False")
    print("  macd_quality_thresholds_changed=False")
    print("  candidate_f_thresholds_changed=False")
    print("  research_diagnostic_only=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print(
        "ALGORITHM_WORKSPACE_CANDIDATE_F_TRANSITION_DELAYED_CONFIRMATION_2025_CHECK=OK"
    )


if __name__ == "__main__":
    main()
