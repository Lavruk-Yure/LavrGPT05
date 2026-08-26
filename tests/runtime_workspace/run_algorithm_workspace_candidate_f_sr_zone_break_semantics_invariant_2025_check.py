# -*- coding: utf-8 -*-
"""RoadMap103 / 7Q.1: S/R break semantics invariant check 2025.

Runner не змінює Candidate F або S/R execution. Він повторно будує causal
zones з 7Q і перевіряє семантику break-метрик перед 7R counterfactual:
close break на конкретному M15 bar завжди має wick beyond на тому самому bar;
hold1/hold2 є властивостями close-break episode; FLIPPED вимагає durable break
і post-break touch. Окремо фіксується, що episode counters — це кількість
послідовних серій, а не кількість bars, тому close episode count може бути
більшим за wick episode count без порушення bar-level implication.
"""

from __future__ import annotations

import importlib
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

_q = importlib.import_module(
    "run_algorithm_workspace_candidate_f_sr_zone_survival_relevance_2025_check"
)

StructuralSlTpRuntime = getattr(_q, "StructuralSlTpRuntime")
create_registered_workspace_algorithm = getattr(
    _q,
    "create_registered_workspace_algorithm",
)
WorkspaceCandidateFNegativePdRecoveryGuard = getattr(
    _q,
    "WorkspaceCandidateFNegativePdRecoveryGuard",
)
assert_frozen_oos_snapshot = getattr(_q, "assert_frozen_oos_snapshot")
frozen_oos_workspace = getattr(_q, "frozen_oos_workspace")
_assert_baseline = getattr(_q, "_assert_baseline")
_all_observations = getattr(_q, "_all_observations")
_break_episodes = getattr(_q, "_break_episodes")
_consecutive_episodes = getattr(_q, "_consecutive_episodes")
_formation_index = getattr(_q, "_formation_index")
_is_broken_close = getattr(_q, "_is_broken_close")
_is_wick_beyond = getattr(_q, "_is_wick_beyond")
_touch_indices = getattr(_q, "_touch_indices")


def _wick_episode_indices(
    events: tuple[Any, ...],
    signal_index: int,
    zone: Any,
) -> tuple[tuple[int, ...], ...]:
    """Return wick-beyond episode indices using the exact 7Q formation scope."""
    start_index = _formation_index(zone, signal_index)
    wick_indices = tuple(
        index
        for index in range(start_index, signal_index + 1)
        if _is_wick_beyond(events[index], zone)
    )
    return _consecutive_episodes(wick_indices)


def main() -> None:
    """Run 7Q break semantics invariants without execution changes."""
    assert_frozen_oos_snapshot()
    runtime = StructuralSlTpRuntime(
        frozen_oos_workspace(),
        algorithm_factory=create_registered_workspace_algorithm,
    )
    assert isinstance(
        runtime.profit_drawdown_guard,
        WorkspaceCandidateFNegativePdRecoveryGuard,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()
    _assert_baseline(runtime)

    execution = runtime.replay_execution
    assert execution is not None
    trades = execution.trade_diagnostics()
    assert len(trades) == 59

    events = tuple(
        runtime.strategy_events[timestamp]
        for timestamp in sorted(runtime.strategy_events)
    )
    event_index = {
        event.timestamp: index for index, event in enumerate(events)
    }
    observations = _all_observations(trades, events, event_index)
    assert observations

    wick_bar_count = 0
    close_bar_count = 0
    wick_episode_count = 0
    close_episode_count = 0
    hold1_episode_count = 0
    hold2_episode_count = 0
    close_episode_gt_wick_observations = 0
    wick_episode_splitting_close_runs = 0
    flipped_count = 0
    invalidated_count = 0
    state_counts: Counter[str] = Counter()

    close_break_implies_wick_break = True
    hold1_implies_close_break = True
    hold2_implies_hold1 = True
    flipped_requires_durable_break = True
    flipped_requires_post_break_touch = True
    invalidated_has_no_effective_sr_role = True
    scans_end_at_or_before_signal = True

    for observation in observations:
        signal_index = event_index[observation.signal_timestamp]
        zone = observation.zone
        start_index = _formation_index(zone, signal_index)
        scans_end_at_or_before_signal = (
            scans_end_at_or_before_signal
            and 0 <= start_index <= signal_index < len(events)
        )

        wick_indices = tuple(
            index
            for index in range(start_index, signal_index + 1)
            if _is_wick_beyond(events[index], zone)
        )
        close_indices = tuple(
            index
            for index in range(start_index, signal_index + 1)
            if _is_broken_close(events[index], zone)
        )
        wick_bar_count += len(wick_indices)
        close_bar_count += len(close_indices)
        if not set(close_indices).issubset(wick_indices):
            close_break_implies_wick_break = False

        wick_episodes = _wick_episode_indices(events, signal_index, zone)
        close_episodes = _break_episodes(events, signal_index, zone)
        wick_episode_count += len(wick_episodes)
        close_episode_count += len(close_episodes)
        if len(close_episodes) > len(wick_episodes):
            close_episode_gt_wick_observations += 1

        for wick_episode in wick_episodes:
            start = wick_episode[0]
            end = wick_episode[-1]
            close_runs_inside = sum(
                start <= episode.start_index <= end
                for episode in close_episodes
            )
            if close_runs_inside > 1:
                wick_episode_splitting_close_runs += 1

        for episode in close_episodes:
            if episode.one_bar_hold_beyond:
                hold1_episode_count += 1
                if episode.bar_count < 2:
                    hold1_implies_close_break = False
            if episode.two_bar_hold_beyond:
                hold2_episode_count += 1
                if not episode.one_bar_hold_beyond or episode.bar_count < 3:
                    hold2_implies_hold1 = False

        state_counts[observation.survival_state] += 1
        if observation.survival_state == "FLIPPED":
            flipped_count += 1
            durable = tuple(
                episode
                for episode in close_episodes
                if episode.two_bar_hold_beyond
            )
            if not durable:
                flipped_requires_durable_break = False
            if not observation.post_durable_touch:
                flipped_requires_post_break_touch = False
            if durable:
                touches = _touch_indices(events, signal_index, zone)
                if not any(
                    index > durable[-1].end_index for index in touches
                ):
                    flipped_requires_post_break_touch = False

        if observation.effective_role == "INVALIDATED":
            invalidated_count += 1
            if observation.distance_role != "NONE":
                invalidated_has_no_effective_sr_role = False

    break_event_units_consistent = (
        close_break_implies_wick_break
        and close_bar_count <= wick_bar_count
        and close_episode_gt_wick_observations > 0
        and wick_episode_splitting_close_runs > 0
    )

    assert close_break_implies_wick_break
    assert close_bar_count <= wick_bar_count
    assert hold1_implies_close_break
    assert hold2_implies_hold1
    assert flipped_count > 0
    assert flipped_requires_durable_break
    assert flipped_requires_post_break_touch
    assert invalidated_count > 0
    assert invalidated_has_no_effective_sr_role
    assert scans_end_at_or_before_signal
    assert break_event_units_consistent

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    print(
        "Algorithm Workspace Candidate F S/R Zone Break Semantics "
        "Invariant 2025 result"
    )
    print("  mode=PRODUCTION_6K_SR_ZONE_BREAK_SEMANTICS_INVARIANT_ONLY")
    print("  production_logic_changed=False")
    print("  production_profile_changed=False")
    print("  entry_policy_changed=False")
    print("  production_sl_tp_changed=False")
    print("  production_exit_policy_changed=False")
    print("  execution_counterfactual_run=False")
    print("  future_price_used=False")
    print("  break_counter_unit=CONSECUTIVE_BAR_EPISODES")
    print(
        "  bar_inventory="
        f"wick_beyond:{wick_bar_count},close_beyond:{close_bar_count}"
    )
    print(
        "  episode_inventory="
        f"wick:{wick_episode_count},close:{close_episode_count},"
        f"hold1:{hold1_episode_count},hold2:{hold2_episode_count}"
    )
    print(
        "  close_episode_gt_wick_episode_observations="
        f"{close_episode_gt_wick_observations}"
    )
    print(
        "  wick_episodes_containing_multiple_close_runs="
        f"{wick_episode_splitting_close_runs}"
    )
    print(f"  flipped_zones={flipped_count}")
    print(f"  invalidated_zones={invalidated_count}")
    print(
        "  survival_states="
        + ",".join(
            f"{key}:{state_counts[key]}"
            for key in (
                "INTACT",
                "RECLAIMED",
                "BREAK_PENDING",
                "RECLAIMED_AFTER_DURABLE_BREAK",
                "FLIPPED",
                "DURABLY_BROKEN",
            )
        )
    )
    print(
        "  close_break_bar_implies_wick_break_bar="
        f"{close_break_implies_wick_break}"
    )
    print(f"  hold1_implies_close_break={hold1_implies_close_break}")
    print(f"  hold2_implies_hold1={hold2_implies_hold1}")
    print(
        "  flipped_requires_durable_break="
        f"{flipped_requires_durable_break}"
    )
    print(
        "  flipped_requires_post_break_touch="
        f"{flipped_requires_post_break_touch}"
    )
    print(
        "  invalidated_has_no_effective_support_resistance_role="
        f"{invalidated_has_no_effective_sr_role}"
    )
    print(f"  break_event_units_consistent={break_event_units_consistent}")
    print("  completed_bars_only=True")
    print("  causal_signal_and_prior_completed_M15_only=True")
    print("  sl_tp_execution_unchanged=True")
    print("  broker_requests=0")
    print(f"  broker_execution_attempted={broker_execution_attempted}")
    print("  performance_threshold_assertions=False")
    print(
        "ALGORITHM_WORKSPACE_CANDIDATE_F_SR_ZONE_BREAK_SEMANTICS_"
        "INVARIANT_2025_CHECK=OK"
    )


if __name__ == "__main__":
    main()
