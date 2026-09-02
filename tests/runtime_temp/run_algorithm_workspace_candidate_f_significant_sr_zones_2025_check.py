# -*- coding: utf-8 -*-
"""RoadMap103 / 7O: significant Support/Resistance zones diagnostic 2025.

Runner повторює production Candidate F після 6K без змін і для тих самих
59 baseline entries будує causal horizontal Support/Resistance zones тільки
з завершених M15 bars, доступних на signal timestamp.

На відміну від 7M/7N, рівень тут не є однією точною pivot-ціною. Підтверджені
2-left/2-right pivots кластеризуються в цінові зони шириною +/-1/2/3/5 pips.
Окремо перевіряються lookback 40/80/160 bars. Для кожної зони збираються
pivot count, bar touches, distinct touch clusters, reaction/rejection,
break/false-break, age/span та distance від entry. Execution, SL, TP та entry
gates не змінюються: це inventory/geometry diagnostic, не backtest.
"""

from __future__ import annotations

import csv
import importlib
import statistics
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    assert_frozen_oos_snapshot,
    frozen_oos_workspace,
)

_structural = importlib.import_module(
    "run_algorithm_workspace_candidate_f_structural_sl_tp_2025_check"
)
FOCUS_CASES = _structural.FOCUS_CASES
PIP = _structural.PIP
StructuralSlTpRuntime = _structural.StructuralSlTpRuntime
_assert_baseline = getattr(_structural, "_assert_baseline")
_summary_text = getattr(_structural, "_summary_text")
_lifecycle = importlib.import_module(
    "run_algorithm_workspace_candidate_f_" "trend_lifecycle_entry_quality_2025_check"
)
PIVOT_SIDE_BARS = _lifecycle.PIVOT_SIDE_BARS
_is_pivot_high = getattr(_lifecycle, "_is_pivot_high")
_is_pivot_low = getattr(_lifecycle, "_is_pivot_low")

from core.workspace_algorithm import create_registered_workspace_algorithm  # noqa: E402
from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_profit_guard import (  # noqa: E402
    WorkspaceCandidateFNegativePdRecoveryGuard,
)

ZONE_HALF_WIDTHS_PIPS = (1.0, 2.0, 3.0, 5.0)
LOOKBACK_VARIANTS_BARS = (40, 80, 160)
SIGNIFICANT_PIVOT_COUNTS = (1, 2, 3)
MIN_TP_DISTANCE_PIPS = 24.0
TOUCH_CLUSTER_GAP_BARS = 2
REACTION_LOOKAHEAD_BARS = 4
REJECTION_THRESHOLD_PIPS = 6.0

OUTPUT_DIR = (
    Path(tempfile.gettempdir()) / "LavrGPT05" / "RM103_7O_Significant_SR_Zones_2025"
)
OUTPUT_CSV = OUTPUT_DIR / "candidate_f_significant_sr_zones_2025.csv"


@dataclass(frozen=True, slots=True)
class PivotPoint:
    """Один causal підтверджений pivot у lookback."""

    kind: str
    index: int
    timestamp: datetime
    price: float


@dataclass(frozen=True, slots=True)
class SrZone:
    """Одна causal horizontal zone та її діагностичні ознаки."""

    kind: str
    center: float
    low: float
    high: float
    half_width_pips: float
    pivot_count: int
    pivot_indices: tuple[int, ...]
    touch_count: int
    distinct_touch_clusters: int
    first_touch_age_bars: int
    last_touch_age_bars: int
    rejection_count: int
    max_rejection_pips: float
    median_rejection_pips: float
    break_count: int
    false_break_count: int
    time_span_bars: int
    recentness: float


@dataclass(frozen=True, slots=True)
class EntryZoneSelection:
    """Найближчі stop-side/take-side zones для одного entry."""

    stop_zone: SrZone | None
    take_zone: SrZone | None
    stop_distance_pips: float | None
    take_distance_pips: float | None


def _pivot_points(
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
    *,
    kind: str,
    lookback_bars: int,
) -> tuple[PivotPoint, ...]:
    earliest = max(PIVOT_SIDE_BARS, signal_index - lookback_bars)
    latest = signal_index - PIVOT_SIDE_BARS
    if latest < earliest:
        return ()
    points: list[PivotPoint] = []
    for index in range(earliest, latest + 1):
        event = events[index]
        if kind == "SUPPORT":
            if not _is_pivot_low(events, index):
                continue
            price = event.low
        else:
            assert kind == "RESISTANCE"
            if not _is_pivot_high(events, index):
                continue
            price = event.high
        points.append(
            PivotPoint(
                kind=kind,
                index=index,
                timestamp=event.timestamp,
                price=price,
            )
        )
    return tuple(points)


def _cluster_pivots(
    pivots: tuple[PivotPoint, ...],
    *,
    half_width_pips: float,
) -> tuple[tuple[PivotPoint, ...], ...]:
    """Chronological deterministic clustering around a running median."""
    radius = half_width_pips * PIP
    clusters: list[list[PivotPoint]] = []
    centers: list[float] = []
    for pivot in pivots:
        candidates = [
            (abs(pivot.price - center), index)
            for index, center in enumerate(centers)
            if abs(pivot.price - center) <= radius
        ]
        if not candidates:
            clusters.append([pivot])
            centers.append(pivot.price)
            continue
        _, cluster_index = min(candidates)
        clusters[cluster_index].append(pivot)
        centers[cluster_index] = statistics.median(
            item.price for item in clusters[cluster_index]
        )
    return tuple(tuple(cluster) for cluster in clusters)


def _touch_indices(
    events: tuple[WorkspaceMarketEvent, ...],
    start_index: int,
    signal_index: int,
    *,
    zone_low: float,
    zone_high: float,
) -> tuple[int, ...]:
    return tuple(
        index
        for index in range(start_index, signal_index + 1)
        if events[index].low <= zone_high and events[index].high >= zone_low
    )


def _cluster_indices(indices: tuple[int, ...]) -> tuple[tuple[int, ...], ...]:
    if not indices:
        return ()
    clusters: list[list[int]] = [[indices[0]]]
    for index in indices[1:]:
        if index - clusters[-1][-1] <= TOUCH_CLUSTER_GAP_BARS:
            clusters[-1].append(index)
        else:
            clusters.append([index])
    return tuple(tuple(cluster) for cluster in clusters)


def _rejection_pips(
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
    *,
    kind: str,
    zone_low: float,
    zone_high: float,
    touch_clusters: tuple[tuple[int, ...], ...],
) -> tuple[float, ...]:
    values: list[float] = []
    for cluster in touch_clusters:
        start = cluster[-1] + 1
        stop = min(signal_index, cluster[-1] + REACTION_LOOKAHEAD_BARS)
        if start > stop:
            values.append(0.0)
            continue
        future = events[start : stop + 1]
        if kind == "SUPPORT":
            displacement = max(event.high - zone_high for event in future)
        else:
            displacement = max(zone_low - event.low for event in future)
        values.append(max(0.0, displacement / PIP))
    return tuple(values)


def _break_metrics(
    events: tuple[WorkspaceMarketEvent, ...],
    start_index: int,
    signal_index: int,
    *,
    kind: str,
    zone_low: float,
    zone_high: float,
) -> tuple[int, int]:
    break_indices: list[int] = []
    for index in range(start_index, signal_index + 1):
        close = events[index].close
        broken = close < zone_low if kind == "SUPPORT" else close > zone_high
        if broken:
            break_indices.append(index)
    break_clusters = _cluster_indices(tuple(break_indices))
    false_breaks = 0
    for cluster in break_clusters:
        start = cluster[-1] + 1
        stop = min(signal_index, cluster[-1] + REACTION_LOOKAHEAD_BARS)
        recovered = False
        for event in events[start : stop + 1]:
            if kind == "SUPPORT" and event.close >= zone_low:
                recovered = True
                break
            if kind == "RESISTANCE" and event.close <= zone_high:
                recovered = True
                break
        false_breaks += int(recovered)
    return len(break_clusters), false_breaks


def _build_zones(
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
    *,
    kind: str,
    lookback_bars: int,
    half_width_pips: float,
) -> tuple[SrZone, ...]:
    pivots = _pivot_points(
        events,
        signal_index,
        kind=kind,
        lookback_bars=lookback_bars,
    )
    clusters = _cluster_pivots(pivots, half_width_pips=half_width_pips)
    start_index = max(0, signal_index - lookback_bars)
    radius = half_width_pips * PIP
    zones: list[SrZone] = []
    for cluster in clusters:
        center = statistics.median(point.price for point in cluster)
        low = center - radius
        high = center + radius
        touch_indices = _touch_indices(
            events,
            start_index,
            signal_index,
            zone_low=low,
            zone_high=high,
        )
        touch_clusters = _cluster_indices(touch_indices)
        if touch_indices:
            first_age = signal_index - touch_indices[0]
            last_age = signal_index - touch_indices[-1]
        else:
            first_age = signal_index - min(point.index for point in cluster)
            last_age = signal_index - max(point.index for point in cluster)
        rejections = _rejection_pips(
            events,
            signal_index,
            kind=kind,
            zone_low=low,
            zone_high=high,
            touch_clusters=touch_clusters,
        )
        rejection_count = sum(value >= REJECTION_THRESHOLD_PIPS for value in rejections)
        break_count, false_break_count = _break_metrics(
            events,
            start_index,
            signal_index,
            kind=kind,
            zone_low=low,
            zone_high=high,
        )
        pivot_indices = tuple(point.index for point in cluster)
        zones.append(
            SrZone(
                kind=kind,
                center=center,
                low=low,
                high=high,
                half_width_pips=half_width_pips,
                pivot_count=len(cluster),
                pivot_indices=pivot_indices,
                touch_count=len(touch_indices),
                distinct_touch_clusters=len(touch_clusters),
                first_touch_age_bars=first_age,
                last_touch_age_bars=last_age,
                rejection_count=rejection_count,
                max_rejection_pips=max(rejections, default=0.0),
                median_rejection_pips=(
                    statistics.median(rejections) if rejections else 0.0
                ),
                break_count=break_count,
                false_break_count=false_break_count,
                time_span_bars=max(pivot_indices) - min(pivot_indices),
                recentness=1.0 / (1.0 + max(0, last_age)),
            )
        )
    return tuple(zones)


def _zone_distance_from_entry_pips(
    zone: SrZone,
    *,
    entry_price: float,
    side: str,
) -> float | None:
    """Distance to the nearest edge on the requested side of entry."""
    if side == "BELOW":
        if zone.high >= entry_price:
            return None
        return (entry_price - zone.high) / PIP
    assert side == "ABOVE"
    if zone.low <= entry_price:
        return None
    return (zone.low - entry_price) / PIP


def _nearest_zone(
    zones: tuple[SrZone, ...],
    *,
    entry_price: float,
    side: str,
    minimum_pivots: int,
    minimum_distance_pips: float = 0.0,
) -> tuple[SrZone | None, float | None]:
    candidates: list[tuple[float, SrZone]] = []
    for zone in zones:
        if zone.pivot_count < minimum_pivots:
            continue
        distance = _zone_distance_from_entry_pips(
            zone,
            entry_price=entry_price,
            side=side,
        )
        if distance is None or distance < minimum_distance_pips:
            continue
        candidates.append((distance, zone))
    if not candidates:
        return None, None
    distance, zone = min(
        candidates,
        key=lambda item: (
            item[0],
            -item[1].rejection_count,
            -item[1].distinct_touch_clusters,
            item[1].last_touch_age_bars,
        ),
    )
    return zone, distance


def _entry_selection(
    trade: WorkspaceHistoricalTradeDiagnostic,
    support_zones: tuple[SrZone, ...],
    resistance_zones: tuple[SrZone, ...],
    *,
    minimum_pivots: int,
) -> EntryZoneSelection:
    if trade.direction == "BUY":
        stop_side = "BELOW"
        take_side = "ABOVE"
        stop_zones = support_zones
        take_zones = resistance_zones
    else:
        stop_side = "ABOVE"
        take_side = "BELOW"
        stop_zones = resistance_zones
        take_zones = support_zones
    stop_zone, stop_distance = _nearest_zone(
        stop_zones,
        entry_price=trade.entry_price,
        side=stop_side,
        minimum_pivots=minimum_pivots,
    )
    take_zone, take_distance = _nearest_zone(
        take_zones,
        entry_price=trade.entry_price,
        side=take_side,
        minimum_pivots=minimum_pivots,
        minimum_distance_pips=MIN_TP_DISTANCE_PIPS,
    )
    return EntryZoneSelection(
        stop_zone=stop_zone,
        take_zone=take_zone,
        stop_distance_pips=stop_distance,
        take_distance_pips=take_distance,
    )


def _inventory_row(
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    events: tuple[WorkspaceMarketEvent, ...],
    event_index: dict[datetime, int],
    *,
    lookback_bars: int,
    half_width_pips: float,
    minimum_pivots: int,
) -> dict[str, int]:
    counts = {"stop": 0, "take_any": 0, "take_24plus": 0}
    for trade in trades:
        signal_index = event_index[trade.signal_timestamp]
        supports = _build_zones(
            events,
            signal_index,
            kind="SUPPORT",
            lookback_bars=lookback_bars,
            half_width_pips=half_width_pips,
        )
        resistances = _build_zones(
            events,
            signal_index,
            kind="RESISTANCE",
            lookback_bars=lookback_bars,
            half_width_pips=half_width_pips,
        )
        if trade.direction == "BUY":
            stop_zones = supports
            take_zones = resistances
            stop_side = "BELOW"
            take_side = "ABOVE"
        else:
            stop_zones = resistances
            take_zones = supports
            stop_side = "ABOVE"
            take_side = "BELOW"
        stop_zone, _ = _nearest_zone(
            stop_zones,
            entry_price=trade.entry_price,
            side=stop_side,
            minimum_pivots=minimum_pivots,
        )
        take_any, _ = _nearest_zone(
            take_zones,
            entry_price=trade.entry_price,
            side=take_side,
            minimum_pivots=minimum_pivots,
        )
        take_24, _ = _nearest_zone(
            take_zones,
            entry_price=trade.entry_price,
            side=take_side,
            minimum_pivots=minimum_pivots,
            minimum_distance_pips=MIN_TP_DISTANCE_PIPS,
        )
        counts["stop"] += int(stop_zone is not None)
        counts["take_any"] += int(take_any is not None)
        counts["take_24plus"] += int(take_24 is not None)
    return counts


def _zone_text(zone: SrZone | None, distance: float | None) -> str:
    if zone is None or distance is None:
        return "NONE"
    return (
        f"{zone.low:.5f}-{zone.high:.5f}/d:{distance:.1f}p/"
        f"piv:{zone.pivot_count}/touch:{zone.touch_count}/"
        f"clusters:{zone.distinct_touch_clusters}/rej:{zone.rejection_count}/"
        f"rejMed:{zone.median_rejection_pips:.1f}/"
        f"break:{zone.break_count}/false:{zone.false_break_count}/"
        f"age:{zone.last_touch_age_bars}"
    )


def _write_csv(
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    events: tuple[WorkspaceMarketEvent, ...],
    event_index: dict[datetime, int],
) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "signal_timestamp",
        "direction",
        "entry_price",
        "lookback_bars",
        "zone_half_width_pips",
        "minimum_pivots",
        "role",
        "zone_kind",
        "zone_center",
        "zone_low",
        "zone_high",
        "distance_from_entry_pips",
        "pivot_count",
        "touch_count",
        "distinct_touch_clusters",
        "first_touch_age_bars",
        "last_touch_age_bars",
        "rejection_count",
        "max_rejection_pips",
        "median_rejection_pips",
        "break_count",
        "false_break_count",
        "time_span_bars",
        "recentness",
    )
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for trade in trades:
            signal_index = event_index[trade.signal_timestamp]
            for lookback_bars in LOOKBACK_VARIANTS_BARS:
                for half_width_pips in ZONE_HALF_WIDTHS_PIPS:
                    supports = _build_zones(
                        events,
                        signal_index,
                        kind="SUPPORT",
                        lookback_bars=lookback_bars,
                        half_width_pips=half_width_pips,
                    )
                    resistances = _build_zones(
                        events,
                        signal_index,
                        kind="RESISTANCE",
                        lookback_bars=lookback_bars,
                        half_width_pips=half_width_pips,
                    )
                    for minimum_pivots in SIGNIFICANT_PIVOT_COUNTS:
                        selection = _entry_selection(
                            trade,
                            supports,
                            resistances,
                            minimum_pivots=minimum_pivots,
                        )
                        for role, zone, distance in (
                            (
                                "STOP",
                                selection.stop_zone,
                                selection.stop_distance_pips,
                            ),
                            (
                                "TAKE_24PLUS",
                                selection.take_zone,
                                selection.take_distance_pips,
                            ),
                        ):
                            if zone is None or distance is None:
                                continue
                            writer.writerow(
                                {
                                    "signal_timestamp": (
                                        trade.signal_timestamp.isoformat()
                                    ),
                                    "direction": trade.direction,
                                    "entry_price": f"{trade.entry_price:.5f}",
                                    "lookback_bars": lookback_bars,
                                    "zone_half_width_pips": (f"{half_width_pips:.1f}"),
                                    "minimum_pivots": minimum_pivots,
                                    "role": role,
                                    "zone_kind": zone.kind,
                                    "zone_center": f"{zone.center:.5f}",
                                    "zone_low": f"{zone.low:.5f}",
                                    "zone_high": f"{zone.high:.5f}",
                                    "distance_from_entry_pips": (f"{distance:.1f}"),
                                    "pivot_count": zone.pivot_count,
                                    "touch_count": zone.touch_count,
                                    "distinct_touch_clusters": (
                                        zone.distinct_touch_clusters
                                    ),
                                    "first_touch_age_bars": (zone.first_touch_age_bars),
                                    "last_touch_age_bars": (zone.last_touch_age_bars),
                                    "rejection_count": zone.rejection_count,
                                    "max_rejection_pips": (
                                        f"{zone.max_rejection_pips:.1f}"
                                    ),
                                    "median_rejection_pips": (
                                        f"{zone.median_rejection_pips:.1f}"
                                    ),
                                    "break_count": zone.break_count,
                                    "false_break_count": (zone.false_break_count),
                                    "time_span_bars": zone.time_span_bars,
                                    "recentness": f"{zone.recentness:.6f}",
                                }
                            )
    return OUTPUT_CSV


def main() -> None:
    """Run causal significant S/R zone geometry inventory."""
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
    baseline_trades = execution.trade_diagnostics()
    assert len(baseline_trades) == 59

    events = tuple(
        runtime.strategy_events[timestamp]
        for timestamp in sorted(runtime.strategy_events)
    )
    event_index = {event.timestamp: index for index, event in enumerate(events)}

    inventory: dict[tuple[int, float, int], dict[str, int]] = {}
    for lookback_bars in LOOKBACK_VARIANTS_BARS:
        for half_width_pips in ZONE_HALF_WIDTHS_PIPS:
            for minimum_pivots in SIGNIFICANT_PIVOT_COUNTS:
                inventory[(lookback_bars, half_width_pips, minimum_pivots)] = (
                    _inventory_row(
                        baseline_trades,
                        events,
                        event_index,
                        lookback_bars=lookback_bars,
                        half_width_pips=half_width_pips,
                        minimum_pivots=minimum_pivots,
                    )
                )

    focus_trades = tuple(
        trade for trade in baseline_trades if trade.signal_timestamp in FOCUS_CASES
    )
    assert len(focus_trades) == len(FOCUS_CASES)

    output_csv = _write_csv(baseline_trades, events, event_index)
    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    print("Algorithm Workspace Candidate F Significant S/R Zones 2025 result")
    print("  mode=PRODUCTION_6K_SIGNIFICANT_SR_ZONES_DIAGNOSTIC_ONLY")
    print("  production_logic_changed=False")
    print("  production_profile_changed=False")
    print("  entry_policy_changed=False")
    print("  production_sl_tp_changed=False")
    print("  production_exit_policy_changed=False")
    print("  execution_counterfactual_run=False")
    print("  future_price_used_to_define_zones=False")
    print("  pivot_confirmation=2_left_2_right_completed_M15_bars")
    print("  zone_model=CAUSAL_PIVOT_PRICE_CLUSTER_HORIZONTAL_BAND")
    print("  zone_half_widths_pips=1|2|3|5")
    print("  lookback_variants_bars=40|80|160")
    print("  significance_inventory_pivot_counts=1|2|3")
    print(f"  minimum_take_distance_pips={MIN_TP_DISTANCE_PIPS:.1f}")
    print(f"  rejection_threshold_pips={REJECTION_THRESHOLD_PIPS:.1f}")
    print(f"  reaction_lookahead_bars={REACTION_LOOKAHEAD_BARS}")
    print(f"  baseline={_summary_text(baseline_summary)}")
    print("  zone_inventory:")
    for lookback_bars in LOOKBACK_VARIANTS_BARS:
        print(f"    lookback={lookback_bars}:")
        for half_width_pips in ZONE_HALF_WIDTHS_PIPS:
            rows = []
            for minimum_pivots in SIGNIFICANT_PIVOT_COUNTS:
                counts = inventory[(lookback_bars, half_width_pips, minimum_pivots)]
                rows.append(
                    f"piv>={minimum_pivots}:stop:{counts['stop']}/59,"
                    f"take_any:{counts['take_any']}/59,"
                    f"take_24plus:{counts['take_24plus']}/59"
                )
            print(f"      width=+/-{half_width_pips:.0f}p " + " | ".join(rows))

    focus_lookback = 160
    focus_width = 3.0
    focus_minimum_pivots = 2
    print(
        "  focus_configuration="
        f"lookback:{focus_lookback},width:+/-{focus_width:.0f}p,"
        f"pivots>={focus_minimum_pivots}"
    )
    print("  chronological_focus_cases:")
    for index, trade in enumerate(focus_trades, start=1):
        signal_index = event_index[trade.signal_timestamp]
        supports = _build_zones(
            events,
            signal_index,
            kind="SUPPORT",
            lookback_bars=focus_lookback,
            half_width_pips=focus_width,
        )
        resistances = _build_zones(
            events,
            signal_index,
            kind="RESISTANCE",
            lookback_bars=focus_lookback,
            half_width_pips=focus_width,
        )
        selection = _entry_selection(
            trade,
            supports,
            resistances,
            minimum_pivots=focus_minimum_pivots,
        )
        print(
            f"    {index:02d}. {trade.signal_timestamp.isoformat()} "
            f"{trade.direction} entry:{trade.entry_price:.5f} "
            f"base:{trade.close_reason}/{trade.final_profit:+.2f}"
        )
        print(
            "        STOP="
            + _zone_text(
                selection.stop_zone,
                selection.stop_distance_pips,
            )
        )
        print(
            "        TAKE24="
            + _zone_text(
                selection.take_zone,
                selection.take_distance_pips,
            )
        )

    print(f"  output_csv={output_csv}")
    print("  completed_bars_only=True")
    print("  causal_signal_and_prior_completed_M15_only=True")
    print("  zones_are_bands_not_exact_prices=True")
    print("  sl_tp_execution_unchanged=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_SIGNIFICANT_SR_ZONES_2025_CHECK=OK")


if __name__ == "__main__":
    main()
