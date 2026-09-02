# -*- coding: utf-8 -*-
"""RoadMap103 / 7P: S/R zone quality matrix diagnostic 2025.

Runner повторює production Candidate F після 6K без змін і для тих
самих 59 baseline entries аналізує causal Support/Resistance zones з 7O.

Мета 7P — не ставити SL/TP і не створювати один довільний quality score.
Знайдені horizontal price bands розкладаються за незалежними ознаками:
distance, pivot count, touch clusters, rejection history, break history,
recent touch age та zone span. Окремо формується описовий zone character
REJECTION / TRAFFIC / MIXED. Усі ознаки використовують лише завершені
M15, доступні на signal timestamp. Execution та production gates не
змінюються.
"""

from __future__ import annotations

import csv
import importlib
import sys
import tempfile
from collections import Counter, defaultdict
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
MIN_TP_DISTANCE_PIPS = _sr_zones.MIN_TP_DISTANCE_PIPS
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

OUTPUT_DIR = (
    Path(tempfile.gettempdir()) / "LavrGPT05" / "RM103_7P_SR_Zone_Quality_Matrix_2025"
)
OUTPUT_CSV = OUTPUT_DIR / "candidate_f_sr_zone_quality_matrix_2025.csv"


class SrZoneLike(Protocol):
    """Мінімальний typed contract зони, який потрібен 7P."""

    kind: str
    low: float
    high: float
    center: float
    pivot_count: int
    touch_count: int
    distinct_touch_clusters: int
    rejection_count: int
    max_rejection_pips: float
    median_rejection_pips: float
    break_count: int
    false_break_count: int
    first_touch_age_bars: int
    last_touch_age_bars: int
    time_span_bars: int
    recentness: float


@dataclass(frozen=True, slots=True)
class ZoneObservation:
    """Одна zone відносно конкретного production entry."""

    signal_timestamp: datetime
    direction: str
    entry_price: float
    role: str
    distance_pips: float
    distance_bin: str
    age_bin: str
    pivot_bin: str
    cluster_bin: str
    rejection_bin: str
    raw_break_ratio_bin: str
    durable_break_ratio_bin: str
    false_break_ratio_bin: str
    zone_character: str
    rejection_ratio: float
    raw_break_ratio: float
    durable_break_ratio: float
    false_break_ratio: float
    durable_break_count: int
    zone: SrZoneLike


def _distance_bin(role: str, distance_pips: float) -> str:
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


def _age_bin(last_touch_age_bars: int) -> str:
    if last_touch_age_bars <= 4:
        return "0-4"
    if last_touch_age_bars <= 12:
        return "5-12"
    if last_touch_age_bars <= 24:
        return "13-24"
    if last_touch_age_bars <= 48:
        return "25-48"
    if last_touch_age_bars <= 96:
        return "49-96"
    return ">96"


def _count_bin(value: int) -> str:
    if value <= 1:
        return str(value)
    if value == 2:
        return "2"
    if value == 3:
        return "3"
    return "4+"


def _rejection_bin(value: int) -> str:
    if value == 0:
        return "0"
    if value == 1:
        return "1"
    if value == 2:
        return "2"
    return "3+"


def _ratio_bin(value: float) -> str:
    if value == 0.0:
        return "0"
    if value <= 0.25:
        return "0-0.25"
    if value < 0.50:
        return "0.25-0.50"
    return ">=0.50"


def _zone_character(
    zone: SrZoneLike,
) -> tuple[str, float, float, float, float, int]:
    clusters = max(1, zone.distinct_touch_clusters)
    rejection_ratio = zone.rejection_count / clusters
    raw_break_ratio = zone.break_count / clusters
    durable_break_count = max(0, zone.break_count - zone.false_break_count)
    durable_break_ratio = durable_break_count / clusters
    false_break_ratio = zone.false_break_count / clusters
    if raw_break_ratio < 0.50 <= rejection_ratio:
        character = "REJECTION"
    elif rejection_ratio < 0.50 <= raw_break_ratio:
        character = "TRAFFIC"
    else:
        character = "MIXED"
    return (
        character,
        rejection_ratio,
        raw_break_ratio,
        durable_break_ratio,
        false_break_ratio,
        durable_break_count,
    )


def _candidate_zones(
    trade: WorkspaceHistoricalTradeDiagnostic,
    supports: tuple[SrZoneLike, ...],
    resistances: tuple[SrZoneLike, ...],
) -> tuple[tuple[str, SrZoneLike, float], ...]:
    if trade.direction == "BUY":
        stop_zones = supports
        stop_side = "BELOW"
        take_zones = resistances
        take_side = "ABOVE"
    else:
        stop_zones = resistances
        stop_side = "ABOVE"
        take_zones = supports
        take_side = "BELOW"

    candidates: list[tuple[str, SrZoneLike, float]] = []
    for role, zones, side in (
        ("STOP", stop_zones, stop_side),
        ("TAKE", take_zones, take_side),
    ):
        for zone in zones:
            if zone.pivot_count < MINIMUM_PIVOTS:
                continue
            distance = _zone_distance_from_entry_pips(
                zone,
                entry_price=trade.entry_price,
                side=side,
            )
            if distance is None:
                continue
            candidates.append((role, zone, distance))
    return tuple(candidates)


def _observation(
    trade: WorkspaceHistoricalTradeDiagnostic,
    role: str,
    zone: SrZoneLike,
    distance_pips: float,
) -> ZoneObservation:
    (
        character,
        rejection_ratio,
        raw_break_ratio,
        durable_break_ratio,
        false_break_ratio,
        durable_break_count,
    ) = _zone_character(zone)
    return ZoneObservation(
        signal_timestamp=trade.signal_timestamp,
        direction=trade.direction,
        entry_price=trade.entry_price,
        role=role,
        distance_pips=distance_pips,
        distance_bin=_distance_bin(role, distance_pips),
        age_bin=_age_bin(zone.last_touch_age_bars),
        pivot_bin=_count_bin(zone.pivot_count),
        cluster_bin=_count_bin(zone.distinct_touch_clusters),
        rejection_bin=_rejection_bin(zone.rejection_count),
        raw_break_ratio_bin=_ratio_bin(raw_break_ratio),
        durable_break_ratio_bin=_ratio_bin(durable_break_ratio),
        false_break_ratio_bin=_ratio_bin(false_break_ratio),
        zone_character=character,
        rejection_ratio=rejection_ratio,
        raw_break_ratio=raw_break_ratio,
        durable_break_ratio=durable_break_ratio,
        false_break_ratio=false_break_ratio,
        durable_break_count=durable_break_count,
        zone=zone,
    )


def _all_observations(
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    events: tuple[WorkspaceMarketEvent, ...],
    event_index: dict[datetime, int],
) -> tuple[ZoneObservation, ...]:
    observations: list[ZoneObservation] = []
    for trade in trades:
        signal_index = event_index[trade.signal_timestamp]
        supports = _build_zones(
            events,
            signal_index,
            kind="SUPPORT",
            lookback_bars=FOCUS_LOOKBACK_BARS,
            half_width_pips=FOCUS_ZONE_HALF_WIDTH_PIPS,
        )
        resistances = _build_zones(
            events,
            signal_index,
            kind="RESISTANCE",
            lookback_bars=FOCUS_LOOKBACK_BARS,
            half_width_pips=FOCUS_ZONE_HALF_WIDTH_PIPS,
        )
        for role, zone, distance in _candidate_zones(
            trade,
            supports,
            resistances,
        ):
            observations.append(_observation(trade, role, zone, distance))
    return tuple(observations)


def _nearest(
    observations: tuple[ZoneObservation, ...],
    *,
    timestamp: datetime,
    role: str,
    minimum_distance_pips: float = 0.0,
) -> ZoneObservation | None:
    candidates = [
        item
        for item in observations
        if item.signal_timestamp == timestamp
        and item.role == role
        and item.distance_pips >= minimum_distance_pips
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: (
            item.distance_pips,
            -item.zone.rejection_count,
            -item.zone.distinct_touch_clusters,
            item.zone.last_touch_age_bars,
        ),
    )


def _matrix_text(
    observations: tuple[ZoneObservation, ...],
    *,
    role: str,
    distance_order: tuple[str, ...],
) -> tuple[str, ...]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for item in observations:
        if item.role != role:
            continue
        counts[item.distance_bin][item.zone_character] += 1
    rows: list[str] = []
    for distance_bin in distance_order:
        row = counts[distance_bin]
        rows.append(
            f"{distance_bin}:R:{row['REJECTION']},"
            f"T:{row['TRAFFIC']},M:{row['MIXED']}"
        )
    return tuple(rows)


def _counter_text(counter: Counter[str], order: tuple[str, ...]) -> str:
    return ",".join(f"{key}:{counter[key]}" for key in order)


def _zone_text(item: ZoneObservation | None) -> str:
    if item is None:
        return "NONE"
    zone = item.zone
    return (
        f"{zone.low:.5f}-{zone.high:.5f}/d:{item.distance_pips:.1f}p/"
        f"char:{item.zone_character}/piv:{zone.pivot_count}/"
        f"clusters:{zone.distinct_touch_clusters}/rej:{zone.rejection_count}/"
        f"rejRatio:{item.rejection_ratio:.2f}/break:{zone.break_count}/"
        f"false:{zone.false_break_count}/rawBR:{item.raw_break_ratio:.2f}/"
        f"durBR:{item.durable_break_ratio:.2f}/"
        f"age:{zone.last_touch_age_bars}/span:{zone.time_span_bars}"
    )


def _write_csv(observations: tuple[ZoneObservation, ...]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "signal_timestamp",
        "direction",
        "entry_price",
        "role",
        "distance_pips",
        "distance_bin",
        "zone_character",
        "zone_kind",
        "zone_center",
        "zone_low",
        "zone_high",
        "pivot_count",
        "pivot_bin",
        "touch_count",
        "distinct_touch_clusters",
        "cluster_bin",
        "first_touch_age_bars",
        "last_touch_age_bars",
        "age_bin",
        "rejection_count",
        "rejection_bin",
        "max_rejection_pips",
        "median_rejection_pips",
        "rejection_ratio",
        "break_count",
        "false_break_count",
        "durable_break_count",
        "raw_break_ratio",
        "raw_break_ratio_bin",
        "durable_break_ratio",
        "durable_break_ratio_bin",
        "false_break_ratio",
        "false_break_ratio_bin",
        "time_span_bars",
        "recentness",
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
                    "role": item.role,
                    "distance_pips": f"{item.distance_pips:.1f}",
                    "distance_bin": item.distance_bin,
                    "zone_character": item.zone_character,
                    "zone_kind": zone.kind,
                    "zone_center": f"{zone.center:.5f}",
                    "zone_low": f"{zone.low:.5f}",
                    "zone_high": f"{zone.high:.5f}",
                    "pivot_count": zone.pivot_count,
                    "pivot_bin": item.pivot_bin,
                    "touch_count": zone.touch_count,
                    "distinct_touch_clusters": zone.distinct_touch_clusters,
                    "cluster_bin": item.cluster_bin,
                    "first_touch_age_bars": zone.first_touch_age_bars,
                    "last_touch_age_bars": zone.last_touch_age_bars,
                    "age_bin": item.age_bin,
                    "rejection_count": zone.rejection_count,
                    "rejection_bin": item.rejection_bin,
                    "max_rejection_pips": f"{zone.max_rejection_pips:.1f}",
                    "median_rejection_pips": f"{zone.median_rejection_pips:.1f}",
                    "rejection_ratio": f"{item.rejection_ratio:.6f}",
                    "break_count": zone.break_count,
                    "false_break_count": zone.false_break_count,
                    "durable_break_count": item.durable_break_count,
                    "raw_break_ratio": f"{item.raw_break_ratio:.6f}",
                    "raw_break_ratio_bin": item.raw_break_ratio_bin,
                    "durable_break_ratio": f"{item.durable_break_ratio:.6f}",
                    "durable_break_ratio_bin": item.durable_break_ratio_bin,
                    "false_break_ratio": f"{item.false_break_ratio:.6f}",
                    "false_break_ratio_bin": item.false_break_ratio_bin,
                    "time_span_bars": zone.time_span_bars,
                    "recentness": f"{zone.recentness:.6f}",
                }
            )
    return OUTPUT_CSV


def main() -> None:
    """Run causal S/R zone quality matrix without execution changes."""
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

    role_counts = Counter(item.role for item in observations)
    character_counts = Counter(item.zone_character for item in observations)
    age_counts = Counter(item.age_bin for item in observations)
    cluster_counts = Counter(item.cluster_bin for item in observations)
    raw_break_ratio_counts = Counter(item.raw_break_ratio_bin for item in observations)
    durable_break_ratio_counts = Counter(
        item.durable_break_ratio_bin for item in observations
    )
    false_break_ratio_counts = Counter(
        item.false_break_ratio_bin for item in observations
    )

    entries_with_stop = {
        item.signal_timestamp for item in observations if item.role == "STOP"
    }
    entries_with_take = {
        item.signal_timestamp for item in observations if item.role == "TAKE"
    }
    entries_with_take24 = {
        item.signal_timestamp
        for item in observations
        if item.role == "TAKE" and item.distance_pips >= MIN_TP_DISTANCE_PIPS
    }

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

    print("Algorithm Workspace Candidate F S/R Zone Quality Matrix 2025 result")
    print("  mode=PRODUCTION_6K_SR_ZONE_QUALITY_MATRIX_DIAGNOSTIC_ONLY")
    print("  production_logic_changed=False")
    print("  production_profile_changed=False")
    print("  entry_policy_changed=False")
    print("  production_sl_tp_changed=False")
    print("  production_exit_policy_changed=False")
    print("  execution_counterfactual_run=False")
    print("  future_price_used_to_define_zones=False")
    print("  single_quality_score_used=False")
    print("  zone_model=CAUSAL_HORIZONTAL_PRICE_BAND")
    print(f"  focus_lookback_bars={FOCUS_LOOKBACK_BARS}")
    print("  focus_zone_half_width_pips=" f"{FOCUS_ZONE_HALF_WIDTH_PIPS:.1f}")
    print(f"  minimum_pivots={MINIMUM_PIVOTS}")
    print(f"  minimum_take_distance_pips={MIN_TP_DISTANCE_PIPS:.1f}")
    print(
        "  zone_character_rule="
        "REJECTION_if_rejRatio>=0.50_and_rawBreakRatio<0.50;"
        "TRAFFIC_if_rawBreakRatio>=0.50_and_rejRatio<0.50;"
        "else_MIXED"
    )
    print(f"  baseline={_summary_text(baseline_summary)}")
    print(
        "  candidate_inventory="
        f"STOP:{role_counts['STOP']},TAKE:{role_counts['TAKE']},"
        f"entries_stop:{len(entries_with_stop)}/59,"
        f"entries_take:{len(entries_with_take)}/59,"
        f"entries_take24:{len(entries_with_take24)}/59"
    )
    print(
        "  zone_character_inventory="
        f"REJECTION:{character_counts['REJECTION']},"
        f"TRAFFIC:{character_counts['TRAFFIC']},"
        f"MIXED:{character_counts['MIXED']}"
    )
    print("  stop_distance_character_matrix:")
    for row in _matrix_text(
        observations,
        role="STOP",
        distance_order=("<12", "12-18", "18-24", "24-36", "36-48", ">48"),
    ):
        print(f"    {row}")
    print("  take_distance_character_matrix:")
    for row in _matrix_text(
        observations,
        role="TAKE",
        distance_order=("<24", "24-36", "36-48", "48-72", ">72"),
    ):
        print(f"    {row}")
    print(
        "  recent_touch_age_inventory="
        + _counter_text(
            age_counts,
            ("0-4", "5-12", "13-24", "25-48", "49-96", ">96"),
        )
    )
    print(
        "  touch_cluster_inventory="
        + _counter_text(cluster_counts, ("1", "2", "3", "4+"))
    )
    ratio_order = ("0", "0-0.25", "0.25-0.50", ">=0.50")
    print(
        "  raw_break_ratio_inventory="
        + _counter_text(raw_break_ratio_counts, ratio_order)
    )
    print(
        "  durable_break_ratio_inventory="
        + _counter_text(durable_break_ratio_counts, ratio_order)
    )
    print(
        "  false_break_ratio_inventory="
        + _counter_text(false_break_ratio_counts, ratio_order)
    )
    print("  chronological_focus_cases:")
    for index, trade in enumerate(focus_trades, start=1):
        stop = _nearest(
            observations,
            timestamp=trade.signal_timestamp,
            role="STOP",
        )
        take24 = _nearest(
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
        print("        STOP=" + _zone_text(stop))
        print("        TAKE24=" + _zone_text(take24))

    print(f"  output_csv={output_csv}")
    print("  completed_bars_only=True")
    print("  causal_signal_and_prior_completed_M15_only=True")
    print("  zones_are_bands_not_exact_prices=True")
    print("  distance_and_quality_features_decoupled=True")
    print("  sl_tp_execution_unchanged=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_SR_ZONE_QUALITY_MATRIX_2025_CHECK=OK")


if __name__ == "__main__":
    main()
