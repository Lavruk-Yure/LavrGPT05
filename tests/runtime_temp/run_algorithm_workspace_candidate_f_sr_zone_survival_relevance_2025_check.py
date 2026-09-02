# -*- coding: utf-8 -*-
"""RoadMap103 / 7Q: S/R zone survival and relevance diagnostic 2025.

Runner повторює production Candidate F після 6K без змін і для тих самих
59 baseline entries аналізує causal horizontal Support/Resistance zones з 7O.

Мета 7Q — відрізнити живу зону від пробитої/перевернутої та окремо оцінити
її практичну відстань до entry. Для кожної зони рахуються wick/close breaks,
1-bar/2-bar hold beyond, reclaim after break, effective role на signal bar,
last interaction/rejection/break age та distance bins. SL/TP, entry gates і
execution не змінюються; counterfactual PnL тут не запускається.
"""

from __future__ import annotations

import csv
import importlib
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    assert_frozen_oos_snapshot,
    frozen_oos_workspace,
)

_sr_zones = importlib.import_module(
    "run_algorithm_workspace_candidate_f_significant_sr_zones_2025_check"
)
PIP = _sr_zones.PIP
MIN_TP_DISTANCE_PIPS = _sr_zones.MIN_TP_DISTANCE_PIPS
PIVOT_SIDE_BARS = _sr_zones.PIVOT_SIDE_BARS
REJECTION_THRESHOLD_PIPS = _sr_zones.REJECTION_THRESHOLD_PIPS
REACTION_LOOKAHEAD_BARS = _sr_zones.REACTION_LOOKAHEAD_BARS
_build_zones = getattr(_sr_zones, "_build_zones")
_zone_distance_from_entry_pips = getattr(_sr_zones, "_zone_distance_from_entry_pips")

_structural = importlib.import_module(
    "run_algorithm_workspace_candidate_f_structural_sl_tp_2025_check"
)
FOCUS_CASES = _structural.FOCUS_CASES
StructuralSlTpRuntime = _structural.StructuralSlTpRuntime
_assert_baseline = getattr(_structural, "_assert_baseline")
_summary_text = getattr(_structural, "_summary_text")

from core.workspace_algorithm import create_registered_workspace_algorithm  # noqa: E402
from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_profit_guard import (  # noqa: E402
    WorkspaceCandidateFNegativePdRecoveryGuard,
)

FOCUS_LOOKBACK_BARS = 160
FOCUS_ZONE_HALF_WIDTH_PIPS = 3.0
MINIMUM_PIVOTS = 2
RECLAIM_LOOKAHEAD_BARS = 4

OUTPUT_DIR = (
    Path(tempfile.gettempdir())
    / "LavrGPT05"
    / "RM103_7Q_SR_Zone_Survival_Relevance_2025"
)
OUTPUT_CSV = OUTPUT_DIR / "candidate_f_sr_zone_survival_relevance_2025.csv"


class SrZoneLike(Protocol):
    """Мінімальний typed contract causal S/R zone з 7O."""

    kind: str
    center: float
    low: float
    high: float
    pivot_count: int
    pivot_indices: tuple[int, ...]
    touch_count: int
    distinct_touch_clusters: int
    rejection_count: int
    last_touch_age_bars: int
    time_span_bars: int


@dataclass(frozen=True, slots=True)
class BreakEpisode:
    """Один послідовний episode закриттів за дальньою межею зони."""

    start_index: int
    end_index: int
    bar_count: int
    one_bar_hold_beyond: bool
    two_bar_hold_beyond: bool
    reclaimed_within_window: bool


@dataclass(frozen=True, slots=True)
class ZoneSurvival:
    """Causal survival/relevance ознаки однієї зони на signal timestamp."""

    signal_timestamp: datetime
    direction: str
    entry_price: float
    original_kind: str
    effective_role: str
    survival_state: str
    current_side: str
    distance_role: str
    distance_pips: float | None
    distance_bin: str
    wick_break_episodes: int
    close_break_episodes: int
    one_bar_hold_count: int
    two_bar_hold_count: int
    reclaim_count: int
    last_interaction_age_bars: int | None
    last_rejection_age_bars: int | None
    last_break_age_bars: int | None
    latest_durable_break_age_bars: int | None
    post_durable_touch: bool
    zone: SrZoneLike


def _consecutive_episodes(indices: tuple[int, ...]) -> tuple[tuple[int, ...], ...]:
    if not indices:
        return ()
    episodes: list[list[int]] = [[indices[0]]]
    for index in indices[1:]:
        if index == episodes[-1][-1] + 1:
            episodes[-1].append(index)
        else:
            episodes.append([index])
    return tuple(tuple(episode) for episode in episodes)


def _formation_index(zone: SrZoneLike, signal_index: int) -> int:
    pivots = sorted(zone.pivot_indices)
    if not pivots:
        return signal_index
    minimum_pivots = min(MINIMUM_PIVOTS, len(pivots))
    pivot_index = pivots[minimum_pivots - 1]
    return min(signal_index, pivot_index + PIVOT_SIDE_BARS)


def _is_broken_close(event: WorkspaceMarketEvent, zone: SrZoneLike) -> bool:
    if zone.kind == "SUPPORT":
        return event.close < zone.low
    assert zone.kind == "RESISTANCE"
    return event.close > zone.high


def _is_wick_beyond(event: WorkspaceMarketEvent, zone: SrZoneLike) -> bool:
    if zone.kind == "SUPPORT":
        return event.low < zone.low
    assert zone.kind == "RESISTANCE"
    return event.high > zone.high


def _is_reclaimed_close(event: WorkspaceMarketEvent, zone: SrZoneLike) -> bool:
    if zone.kind == "SUPPORT":
        return event.close >= zone.low
    assert zone.kind == "RESISTANCE"
    return event.close <= zone.high


def _break_episodes(
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
    zone: SrZoneLike,
) -> tuple[BreakEpisode, ...]:
    start_index = _formation_index(zone, signal_index)
    broken_indices = tuple(
        index
        for index in range(start_index, signal_index + 1)
        if _is_broken_close(events[index], zone)
    )
    episodes: list[BreakEpisode] = []
    for indices in _consecutive_episodes(broken_indices):
        start = indices[0]
        end = indices[-1]
        reclaim_stop = min(signal_index, start + RECLAIM_LOOKAHEAD_BARS)
        reclaimed = any(
            _is_reclaimed_close(events[index], zone)
            for index in range(start + 1, reclaim_stop + 1)
        )
        episodes.append(
            BreakEpisode(
                start_index=start,
                end_index=end,
                bar_count=len(indices),
                one_bar_hold_beyond=len(indices) >= 2,
                two_bar_hold_beyond=len(indices) >= 3,
                reclaimed_within_window=reclaimed,
            )
        )
    return tuple(episodes)


def _wick_break_episode_count(
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
    zone: SrZoneLike,
) -> int:
    start_index = _formation_index(zone, signal_index)
    indices = tuple(
        index
        for index in range(start_index, signal_index + 1)
        if _is_wick_beyond(events[index], zone)
    )
    return len(_consecutive_episodes(indices))


def _touch_indices(
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
    zone: SrZoneLike,
) -> tuple[int, ...]:
    start_index = _formation_index(zone, signal_index)
    return tuple(
        index
        for index in range(start_index, signal_index + 1)
        if events[index].low <= zone.high and events[index].high >= zone.low
    )


def _touch_clusters(indices: tuple[int, ...]) -> tuple[tuple[int, ...], ...]:
    if not indices:
        return ()
    clusters: list[list[int]] = [[indices[0]]]
    for index in indices[1:]:
        if index - clusters[-1][-1] <= 2:
            clusters[-1].append(index)
        else:
            clusters.append([index])
    return tuple(tuple(cluster) for cluster in clusters)


def _cluster_rejection_pips(
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
    zone: SrZoneLike,
    cluster: tuple[int, ...],
) -> float:
    start = cluster[-1] + 1
    stop = min(signal_index, cluster[-1] + REACTION_LOOKAHEAD_BARS)
    if start > stop:
        return 0.0
    future = events[start : stop + 1]  # noqa
    if zone.kind == "SUPPORT":
        displacement = max(event.high - zone.high for event in future)
    else:
        displacement = max(zone.low - event.low for event in future)
    return max(0.0, displacement / PIP)


def _interaction_ages(
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
    zone: SrZoneLike,
    episodes: tuple[BreakEpisode, ...],
) -> tuple[int | None, int | None, int | None, int | None]:
    touches = _touch_indices(events, signal_index, zone)
    clusters = _touch_clusters(touches)
    last_interaction_age = signal_index - touches[-1] if touches else None

    rejection_indices = tuple(
        cluster[-1]
        for cluster in clusters
        if _cluster_rejection_pips(
            events,
            signal_index,
            zone,
            cluster,
        )
        >= REJECTION_THRESHOLD_PIPS
    )
    last_rejection_age = (
        signal_index - rejection_indices[-1] if rejection_indices else None
    )
    last_break_age = signal_index - episodes[-1].end_index if episodes else None
    durable = tuple(episode for episode in episodes if episode.two_bar_hold_beyond)
    latest_durable_age = signal_index - durable[-1].end_index if durable else None
    return (
        last_interaction_age,
        last_rejection_age,
        last_break_age,
        latest_durable_age,
    )


def _current_side(close: float, zone: SrZoneLike) -> str:
    if close < zone.low:
        return "BELOW"
    if close > zone.high:
        return "ABOVE"
    return "INSIDE"


def _role_and_survival(
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
    zone: SrZoneLike,
    episodes: tuple[BreakEpisode, ...],
) -> tuple[str, str, str, bool]:
    side = _current_side(events[signal_index].close, zone)
    durable = tuple(episode for episode in episodes if episode.two_bar_hold_beyond)
    if zone.kind == "SUPPORT":
        original_valid = side in {"ABOVE", "INSIDE"}
        flipped_role = "FLIPPED_RESISTANCE"
    else:
        original_valid = side in {"BELOW", "INSIDE"}
        flipped_role = "FLIPPED_SUPPORT"

    if not episodes:
        return zone.kind, "INTACT", side, False

    if not durable:
        if original_valid:
            return zone.kind, "RECLAIMED", side, False
        return "INVALIDATED", "BREAK_PENDING", side, False

    latest_durable = durable[-1]
    touches = _touch_indices(events, signal_index, zone)
    post_durable_touch = any(index > latest_durable.end_index for index in touches)
    if original_valid:
        return zone.kind, "RECLAIMED_AFTER_DURABLE_BREAK", side, False
    if post_durable_touch:
        return flipped_role, "FLIPPED", side, True
    return "INVALIDATED", "DURABLY_BROKEN", side, False


def _role_for_trade(
    trade: WorkspaceHistoricalTradeDiagnostic,
    effective_role: str,
) -> tuple[str, str] | None:
    is_support = effective_role in {"SUPPORT", "FLIPPED_SUPPORT"}
    is_resistance = effective_role in {
        "RESISTANCE",
        "FLIPPED_RESISTANCE",
    }
    if trade.direction == "BUY":
        if is_support:
            return "STOP", "BELOW"
        if is_resistance:
            return "TAKE", "ABOVE"
    else:
        if is_resistance:
            return "STOP", "ABOVE"
        if is_support:
            return "TAKE", "BELOW"
    return None


def _distance_bin(role: str, distance_pips: float | None) -> str:
    if distance_pips is None:
        return "NONE"
    if role == "STOP":
        if distance_pips < 12.0:
            return "<12"
        if distance_pips < 18.0:
            return "12-18"
        if distance_pips < 24.0:
            return "18-24"
        if distance_pips < 36.0:
            return "24-36"
        if distance_pips < 48.0:
            return "36-48"
        return ">48"
    assert role == "TAKE"
    if distance_pips < 24.0:
        return "<24"
    if distance_pips < 36.0:
        return "24-36"
    if distance_pips < 48.0:
        return "36-48"
    if distance_pips < 72.0:
        return "48-72"
    return ">72"


def _survival_observation(
    trade: WorkspaceHistoricalTradeDiagnostic,
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
    zone: SrZoneLike,
) -> ZoneSurvival:
    episodes = _break_episodes(events, signal_index, zone)
    effective_role, state, side, post_durable_touch = _role_and_survival(
        events,
        signal_index,
        zone,
        episodes,
    )
    trade_role = _role_for_trade(trade, effective_role)
    if trade_role is None:
        distance_role = "NONE"
        distance = None
    else:
        distance_role, side_for_distance = trade_role
        distance = _zone_distance_from_entry_pips(
            zone,
            entry_price=trade.entry_price,
            side=side_for_distance,
        )
    (
        last_interaction_age,
        last_rejection_age,
        last_break_age,
        latest_durable_age,
    ) = _interaction_ages(events, signal_index, zone, episodes)
    return ZoneSurvival(
        signal_timestamp=trade.signal_timestamp,
        direction=trade.direction,
        entry_price=trade.entry_price,
        original_kind=zone.kind,
        effective_role=effective_role,
        survival_state=state,
        current_side=side,
        distance_role=distance_role,
        distance_pips=distance,
        distance_bin=_distance_bin(distance_role, distance),
        wick_break_episodes=_wick_break_episode_count(
            events,
            signal_index,
            zone,
        ),
        close_break_episodes=len(episodes),
        one_bar_hold_count=sum(episode.one_bar_hold_beyond for episode in episodes),
        two_bar_hold_count=sum(episode.two_bar_hold_beyond for episode in episodes),
        reclaim_count=sum(episode.reclaimed_within_window for episode in episodes),
        last_interaction_age_bars=last_interaction_age,
        last_rejection_age_bars=last_rejection_age,
        last_break_age_bars=last_break_age,
        latest_durable_break_age_bars=latest_durable_age,
        post_durable_touch=post_durable_touch,
        zone=zone,
    )


def _all_observations(
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    events: tuple[WorkspaceMarketEvent, ...],
    event_index: dict[datetime, int],
) -> tuple[ZoneSurvival, ...]:
    observations: list[ZoneSurvival] = []
    for trade in trades:
        signal_index = event_index[trade.signal_timestamp]
        for kind in ("SUPPORT", "RESISTANCE"):
            zones = _build_zones(
                events,
                signal_index,
                kind=kind,
                lookback_bars=FOCUS_LOOKBACK_BARS,
                half_width_pips=FOCUS_ZONE_HALF_WIDTH_PIPS,
            )
            for zone in zones:
                if zone.pivot_count < MINIMUM_PIVOTS:
                    continue
                observations.append(
                    _survival_observation(
                        trade,
                        events,
                        signal_index,
                        zone,
                    )
                )
    return tuple(observations)


def _nearest(
    observations: tuple[ZoneSurvival, ...],
    *,
    timestamp: datetime,
    role: str,
    minimum_distance_pips: float = 0.0,
) -> ZoneSurvival | None:
    candidates = [
        item
        for item in observations
        if item.signal_timestamp == timestamp
        and item.distance_role == role
        and item.distance_pips is not None
        and item.distance_pips >= minimum_distance_pips
        and item.effective_role != "INVALIDATED"
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: (
            item.distance_pips if item.distance_pips is not None else 1e9,
            (
                item.last_interaction_age_bars
                if item.last_interaction_age_bars is not None
                else 1_000_000
            ),
            -item.zone.pivot_count,
        ),
    )


def _age_bin(value: int | None) -> str:
    if value is None:
        return "NONE"
    if value <= 4:
        return "0-4"
    if value <= 12:
        return "5-12"
    if value <= 24:
        return "13-24"
    if value <= 48:
        return "25-48"
    if value <= 96:
        return "49-96"
    return ">96"


def _counter_text(counter: Counter[str], order: tuple[str, ...]) -> str:
    return ",".join(f"{key}:{counter[key]}" for key in order)


def _zone_text(item: ZoneSurvival | None) -> str:
    if item is None:
        return "NONE"
    zone = item.zone
    distance = (
        f"{item.distance_pips:.1f}p" if item.distance_pips is not None else "NONE"
    )
    return (
        f"{zone.low:.5f}-{zone.high:.5f}/d:{distance}/"
        f"role:{item.effective_role}/state:{item.survival_state}/"
        f"wick:{item.wick_break_episodes}/close:{item.close_break_episodes}/"
        f"hold1:{item.one_bar_hold_count}/hold2:{item.two_bar_hold_count}/"
        f"reclaim:{item.reclaim_count}/"
        f"intAge:{item.last_interaction_age_bars}/"
        f"rejAge:{item.last_rejection_age_bars}/"
        f"breakAge:{item.last_break_age_bars}/piv:{zone.pivot_count}"
    )


def _write_csv(observations: tuple[ZoneSurvival, ...]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "signal_timestamp",
        "direction",
        "entry_price",
        "original_kind",
        "effective_role",
        "survival_state",
        "current_side",
        "distance_role",
        "distance_pips",
        "distance_bin",
        "zone_center",
        "zone_low",
        "zone_high",
        "pivot_count",
        "touch_count",
        "distinct_touch_clusters",
        "wick_break_episodes",
        "close_break_episodes",
        "one_bar_hold_count",
        "two_bar_hold_count",
        "reclaim_count",
        "last_interaction_age_bars",
        "last_rejection_age_bars",
        "last_break_age_bars",
        "latest_durable_break_age_bars",
        "post_durable_touch",
        "time_span_bars",
    )
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for item in observations:
            zone = item.zone
            writer.writerow(
                {
                    "signal_timestamp": item.signal_timestamp.isoformat(),
                    "direction": item.direction,
                    "entry_price": f"{item.entry_price:.5f}",
                    "original_kind": item.original_kind,
                    "effective_role": item.effective_role,
                    "survival_state": item.survival_state,
                    "current_side": item.current_side,
                    "distance_role": item.distance_role,
                    "distance_pips": (
                        ""
                        if item.distance_pips is None
                        else f"{item.distance_pips:.1f}"
                    ),
                    "distance_bin": item.distance_bin,
                    "zone_center": f"{zone.center:.5f}",
                    "zone_low": f"{zone.low:.5f}",
                    "zone_high": f"{zone.high:.5f}",
                    "pivot_count": zone.pivot_count,
                    "touch_count": zone.touch_count,
                    "distinct_touch_clusters": zone.distinct_touch_clusters,
                    "wick_break_episodes": item.wick_break_episodes,
                    "close_break_episodes": item.close_break_episodes,
                    "one_bar_hold_count": item.one_bar_hold_count,
                    "two_bar_hold_count": item.two_bar_hold_count,
                    "reclaim_count": item.reclaim_count,
                    "last_interaction_age_bars": item.last_interaction_age_bars,
                    "last_rejection_age_bars": item.last_rejection_age_bars,
                    "last_break_age_bars": item.last_break_age_bars,
                    "latest_durable_break_age_bars": (
                        item.latest_durable_break_age_bars
                    ),
                    "post_durable_touch": item.post_durable_touch,
                    "time_span_bars": zone.time_span_bars,
                }
            )
    return OUTPUT_CSV


def main() -> None:
    """Run causal S/R zone survival/relevance inventory only."""
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

    baseline_summary = runtime.historical_summary
    execution = runtime.replay_execution
    assert baseline_summary is not None
    assert execution is not None
    trades = execution.trade_diagnostics()
    assert len(trades) == 59

    events = tuple(
        runtime.strategy_events[timestamp]
        for timestamp in sorted(runtime.strategy_events)
    )
    event_index = {event.timestamp: index for index, event in enumerate(events)}
    observations = _all_observations(trades, events, event_index)
    assert observations

    state_counts = Counter(item.survival_state for item in observations)
    role_counts = Counter(item.effective_role for item in observations)
    wick_breaks = sum(item.wick_break_episodes for item in observations)
    close_breaks = sum(item.close_break_episodes for item in observations)
    hold1 = sum(item.one_bar_hold_count for item in observations)
    hold2 = sum(item.two_bar_hold_count for item in observations)
    reclaims = sum(item.reclaim_count for item in observations)

    valid_stop = {
        item.signal_timestamp
        for item in observations
        if item.distance_role == "STOP" and item.distance_pips is not None
    }
    valid_take = {
        item.signal_timestamp
        for item in observations
        if item.distance_role == "TAKE" and item.distance_pips is not None
    }
    valid_take24 = {
        item.signal_timestamp
        for item in observations
        if item.distance_role == "TAKE"
        and item.distance_pips is not None
        and item.distance_pips >= MIN_TP_DISTANCE_PIPS
    }

    nearest_stops = tuple(
        item
        for trade in trades
        if (
            item := _nearest(
                observations,
                timestamp=trade.signal_timestamp,
                role="STOP",
            )
        )
        is not None
    )
    nearest_takes24 = tuple(
        item
        for trade in trades
        if (
            item := _nearest(
                observations,
                timestamp=trade.signal_timestamp,
                role="TAKE",
                minimum_distance_pips=MIN_TP_DISTANCE_PIPS,
            )
        )
        is not None
    )
    stop_distance_counts = Counter(item.distance_bin for item in nearest_stops)
    take_distance_counts = Counter(item.distance_bin for item in nearest_takes24)
    interaction_age_counts = Counter(
        _age_bin(item.last_interaction_age_bars) for item in observations
    )
    rejection_age_counts = Counter(
        _age_bin(item.last_rejection_age_bars) for item in observations
    )
    break_age_counts = Counter(
        _age_bin(item.last_break_age_bars) for item in observations
    )

    focus_trades = tuple(
        trade for trade in trades if trade.signal_timestamp in FOCUS_CASES
    )
    assert len(focus_trades) == len(FOCUS_CASES)

    output_csv = _write_csv(observations)
    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    print(
        "Algorithm Workspace Candidate F S/R Zone Survival & Relevance " "2025 result"
    )
    print("  mode=PRODUCTION_6K_SR_ZONE_SURVIVAL_RELEVANCE_DIAGNOSTIC_ONLY")
    print("  production_logic_changed=False")
    print("  production_profile_changed=False")
    print("  entry_policy_changed=False")
    print("  production_sl_tp_changed=False")
    print("  production_exit_policy_changed=False")
    print("  execution_counterfactual_run=False")
    print("  future_price_used_to_define_or_score_zones=False")
    print("  zone_model=CAUSAL_HORIZONTAL_PRICE_BAND")
    print(f"  focus_lookback_bars={FOCUS_LOOKBACK_BARS}")
    print(f"  focus_zone_half_width_pips={FOCUS_ZONE_HALF_WIDTH_PIPS:.1f}")
    print(f"  minimum_pivots={MINIMUM_PIVOTS}")
    print(f"  minimum_take_distance_pips={MIN_TP_DISTANCE_PIPS:.1f}")
    print("  close_break_definition=close_beyond_far_zone_edge")
    print("  one_bar_hold_definition=break_close_plus_1_more_beyond_close")
    print("  two_bar_hold_definition=break_close_plus_2_more_beyond_closes")
    print(f"  reclaim_lookahead_bars={RECLAIM_LOOKAHEAD_BARS}")
    print("  flipped_role_requires=durable_break_plus_post_break_zone_touch")
    print(f"  baseline={_summary_text(baseline_summary)}")
    print(f"  candidate_zones={len(observations)}")
    print(
        "  break_episode_inventory="
        f"wick:{wick_breaks},close:{close_breaks},"
        f"hold1:{hold1},hold2:{hold2},reclaim:{reclaims}"
    )
    print(
        "  survival_state_inventory="
        + _counter_text(
            state_counts,
            (
                "INTACT",
                "RECLAIMED",
                "BREAK_PENDING",
                "RECLAIMED_AFTER_DURABLE_BREAK",
                "FLIPPED",
                "DURABLY_BROKEN",
            ),
        )
    )
    print(
        "  effective_role_inventory="
        + _counter_text(
            role_counts,
            (
                "SUPPORT",
                "RESISTANCE",
                "FLIPPED_SUPPORT",
                "FLIPPED_RESISTANCE",
                "INVALIDATED",
            ),
        )
    )
    print(
        "  entry_zone_inventory="
        f"stop:{len(valid_stop)}/59,take_any:{len(valid_take)}/59,"
        f"take_24plus:{len(valid_take24)}/59"
    )
    print(
        "  nearest_valid_stop_distance_bins="
        + _counter_text(
            stop_distance_counts,
            ("<12", "12-18", "18-24", "24-36", "36-48", ">48"),
        )
    )
    print(
        "  nearest_valid_take24_distance_bins="
        + _counter_text(
            take_distance_counts,
            ("24-36", "36-48", "48-72", ">72"),
        )
    )
    age_order = ("0-4", "5-12", "13-24", "25-48", "49-96", ">96", "NONE")
    print(
        "  last_interaction_age_inventory="
        + _counter_text(interaction_age_counts, age_order)
    )
    print(
        "  last_rejection_age_inventory="
        + _counter_text(rejection_age_counts, age_order)
    )
    print("  last_break_age_inventory=" + _counter_text(break_age_counts, age_order))
    print("  chronological_focus_cases:")
    for index, trade in enumerate(focus_trades, start=1):
        stop = _nearest(
            observations,
            timestamp=trade.signal_timestamp,
            role="STOP",
        )
        take = _nearest(
            observations,
            timestamp=trade.signal_timestamp,
            role="TAKE",
            minimum_distance_pips=MIN_TP_DISTANCE_PIPS,
        )
        print(
            f"    {index:02d}. {trade.signal_timestamp.isoformat()} "
            f"{trade.direction} entry:{trade.entry_price:.5f} "
            f"base:{trade.close_reason}/{trade.final_profit:+.2f}"
        )
        print(f"        STOP={_zone_text(stop)}")
        print(f"        TAKE24={_zone_text(take)}")

    print(f"  output_csv={output_csv}")
    print("  completed_bars_only=True")
    print("  causal_signal_and_prior_completed_M15_only=True")
    print("  zones_are_bands_not_exact_prices=True")
    print("  survival_and_distance_features_decoupled=True")
    print("  sl_tp_execution_unchanged=True")
    print("  broker_requests=0")
    print(f"  broker_execution_attempted={broker_execution_attempted}")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_SR_ZONE_SURVIVAL_RELEVANCE_2025_CHECK=OK")


if __name__ == "__main__":
    main()
