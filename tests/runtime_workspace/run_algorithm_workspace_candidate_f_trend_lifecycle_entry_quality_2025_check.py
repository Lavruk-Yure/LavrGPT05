# -*- coding: utf-8 -*-
"""RoadMap103 / 7L: Trend Lifecycle & Entry Quality diagnostic 2025.

Diagnostic-only runner повторює production Candidate F після 6K
і додає causal ознаки continuity, exhaustion, transition та market
structure для всіх 59 фактично відкритих угод 2025.
Production logic,
profile, entry, SL/TP та exit policy не змінюються.

Retrospective macro position із 7K використовується лише для
групування результатів після Replay. Усі нові 7L
features
обчислюються тільки з завершених M15 bars/indicator
observations,
доступних не пізніше signal bar. Structural support/resistance
шукаються як останні підтверджені pivot-рівні.
Pivot має по два
завершені bars зліва і справа, тому future bars після
signal
timestamp не використовуються.
"""

from __future__ import annotations

import csv
import math
import statistics
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, TEST_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from run_algorithm_workspace_candidate_f_entry_exit_context_2025_check import (  # noqa
    OUTCOME_BREAK_EVEN,
    OUTCOME_LOSS_PD,
    OUTCOME_STOP_LOSS,
    OUTCOME_TAKE_PROFIT,
    OUTCOME_WIN_PD,
    EntryExitContextRuntime,
    TradeContextEvidence,
    _assert_baseline,
    _build_evidence,
    _regime_direction,
    _split_active_runs,
    _split_macro_trends,
)
from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    assert_frozen_oos_snapshot,
    frozen_oos_workspace,
)

from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_alligator import (  # noqa: E402
    WorkspaceAlligatorObservation,
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_macd import WorkspaceMacdObservation  # noqa: E402
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_profit_guard import (  # noqa: E402
    WorkspaceCandidateFNegativePdRecoveryGuard,
)

PIP = 0.0001
EPSILON = 1e-12
PIVOT_SIDE_BARS = 2
PIVOT_LOOKBACK_BARS = 40
MACD_LOOKBACK_BARS = 20
TRANSITION_LOOKBACK_BARS = 40

OUTPUT_DIR = (
    Path(tempfile.gettempdir())
    / "LavrGPT05"
    / "RM103_7L_Trend_Lifecycle_Entry_Quality_2025"
)
OUTPUT_CSV = OUTPUT_DIR / "candidate_f_trend_lifecycle_entry_quality_2025.csv"

MANUAL_CASE_LABELS = {
    datetime.fromisoformat("2025-03-05T12:30:00+00:00"): "PULLBACK_TIMING",
    datetime.fromisoformat("2025-04-08T06:30:00+00:00"): "LOW_CONTINUITY",
    datetime.fromisoformat("2025-04-11T17:45:00+00:00"): "TRANSITION_FALSE_START",
    datetime.fromisoformat("2025-05-13T07:30:00+00:00"): "LATE_WEAK_TREND",
    datetime.fromisoformat("2025-05-29T12:15:00+00:00"): "EARLY_TP",
    datetime.fromisoformat("2025-05-30T08:45:00+00:00"): "LATE_ENTRY",
    datetime.fromisoformat("2025-07-29T00:45:00+00:00"): "POST_TREND_FLAT",
    datetime.fromisoformat("2025-08-05T11:30:00+00:00"): "END_WARNING",
    datetime.fromisoformat("2025-12-17T11:30:00+00:00"): "LATE_EXHAUSTION",
}


@dataclass(frozen=True, slots=True)
class PivotLevel:
    """Останній causal підтверджений локальний pivot."""

    timestamp: datetime
    price: float
    kind: str
    age_bars: int


@dataclass(frozen=True, slots=True)
class LifecycleEvidence:
    """7L causal lifecycle/structure features для однієї угоди."""

    base: TradeContextEvidence
    efficiency_3: float
    efficiency_5: float
    efficiency_8: float
    progress_30_r: float
    progress_60_r: float
    progress_120_r: float
    ordering_stability_3: float
    ordering_stability_5: float
    ordering_stability_8: float
    same_regime_age: int
    bars_since_flat_40: int
    bars_since_opposite_40: int
    regime_changes_8: int
    ordering_changes_8: int
    opening_delta_1: float
    opening_delta_2: float
    slope_delta_1: float
    slope_delta_2: float
    macd_directional_value: float
    macd_depth_percentile_20: float
    macd_recovery_from_extreme_20: float
    bars_since_macd_extreme_20: int
    macd_delta_1: float
    macd_delta_2: float
    directional_histogram: float
    directional_histogram_delta_1: float
    structural_sl: PivotLevel | None
    structural_tp: PivotLevel | None
    structural_sl_distance_r: float | None
    structural_tp_distance_r: float | None


def _directional_delta(direction: str, newer: float, older: float) -> float:
    if direction == "BUY":
        return newer - older
    return older - newer


def _directional_indicator(direction: str, value: float) -> float:
    if direction == "BUY":
        return value
    return -value


def _efficiency(
    direction: str,
    events: tuple[WorkspaceMarketEvent, ...],
    index: int,
    bars: int,
) -> float:
    assert index >= bars
    window = events[index - bars : index + 1]  # noqa: E203
    net = _directional_delta(direction, window[-1].close, window[0].close)
    travel_path = sum(
        abs(window[pos].close - window[pos - 1].close) for pos in range(1, len(window))
    )
    if travel_path <= EPSILON:
        return 0.0
    return net / travel_path


def _progress_r(
    direction: str,
    events: tuple[WorkspaceMarketEvent, ...],
    index: int,
    bars: int,
    stop_distance: float,
) -> float:
    assert index >= bars
    return (
        _directional_delta(
            direction,
            events[index].close,
            events[index - bars].close,
        )
        / stop_distance
    )


def _ordering(observation: WorkspaceAlligatorObservation) -> str:
    jaw = observation.jaw
    teeth = observation.teeth
    lips = observation.lips
    if jaw is None or teeth is None or lips is None:
        return "NONE"
    if lips > teeth > jaw:
        return "BUY"
    if lips < teeth < jaw:
        return "SELL"
    return "MIXED"


def _ordering_stability(
    direction: str,
    observations: tuple[WorkspaceAlligatorObservation, ...],
    index: int,
    bars: int,
) -> float:
    start = max(0, index - bars + 1)
    window = observations[start : index + 1]  # noqa

    assert window
    return sum(_ordering(item) == direction for item in window) / len(window)


def _consecutive_same_regime(
    direction: str,
    observations: tuple[WorkspaceAlligatorObservation, ...],
    index: int,
) -> int:
    count = 0
    for item in reversed(observations[: index + 1]):
        if _regime_direction(item) != direction:
            break
        count += 1
    return count


def _bars_since_condition_40(
    observations: tuple[WorkspaceAlligatorObservation, ...],
    index: int,
    predicate,
) -> int:
    start = max(0, index - TRANSITION_LOOKBACK_BARS)
    for age, item in enumerate(reversed(observations[start : index + 1])):  # noqa
        if predicate(item):
            return age
    return TRANSITION_LOOKBACK_BARS + 1


def _change_count(values: tuple[str, ...]) -> int:
    if len(values) < 2:
        return 0
    return sum(values[index] != values[index - 1] for index in range(1, len(values)))


def _recent_regime_changes(
    observations: tuple[WorkspaceAlligatorObservation, ...],
    index: int,
    bars: int,
) -> int:
    start = max(0, index - bars)
    values = tuple(
        _regime_direction(item) or "FLAT_OR_OTHER"
        for item in observations[start : index + 1]  # noqa
    )
    return _change_count(values)


def _recent_ordering_changes(
    observations: tuple[WorkspaceAlligatorObservation, ...],
    index: int,
    bars: int,
) -> int:
    start = max(0, index - bars)
    values = tuple(_ordering(item) for item in observations[start : index + 1])  # noqa
    return _change_count(values)


def _required_float(value: float | None, name: str) -> float:
    assert value is not None, name
    number = float(value)
    assert math.isfinite(number), name
    return number


def _macd_metrics(
    direction: str,
    observations: tuple[WorkspaceMacdObservation, ...],
    index: int,
) -> tuple[float, float, float, int, float, float, float, float]:
    current = observations[index]
    current_macd = _required_float(current.macd_value, "macd_value")
    current_histogram = _required_float(current.histogram, "histogram")
    directional_current = _directional_indicator(direction, current_macd)
    directional_histogram = _directional_indicator(direction, current_histogram)

    start = max(0, index - MACD_LOOKBACK_BARS + 1)
    window = tuple(
        item
        for item in observations[start : index + 1]  # noqa
        if item.macd_value is not None and math.isfinite(float(item.macd_value))
    )
    assert window
    directional_values = tuple(
        _directional_indicator(direction, float(item.macd_value)) for item in window
    )
    depth_percentile = sum(
        value <= directional_current for value in directional_values
    ) / len(directional_values)
    extreme = max(directional_values)
    low = min(directional_values)
    width = max(extreme - low, EPSILON)
    recovery = (extreme - directional_current) / width
    latest_extreme_index = max(
        pos
        for pos, value in enumerate(directional_values)
        if math.isclose(value, extreme, abs_tol=EPSILON)
    )
    bars_since_extreme = len(directional_values) - 1 - latest_extreme_index

    assert index >= 2
    previous_macd = _required_float(observations[index - 1].macd_value, "macd_prev")
    previous2_macd = _required_float(observations[index - 2].macd_value, "macd_prev2")
    macd_delta_1 = directional_current - _directional_indicator(
        direction, previous_macd
    )
    macd_delta_2 = directional_current - _directional_indicator(
        direction, previous2_macd
    )
    previous_histogram = _required_float(
        observations[index - 1].histogram,
        "histogram_prev",
    )
    histogram_delta_1 = directional_histogram - _directional_indicator(
        direction,
        previous_histogram,
    )
    return (
        directional_current,
        depth_percentile,
        recovery,
        bars_since_extreme,
        macd_delta_1,
        macd_delta_2,
        directional_histogram,
        histogram_delta_1,
    )


def _is_pivot_low(events: tuple[WorkspaceMarketEvent, ...], index: int) -> bool:
    value = events[index].low
    peers = (
        events[index - 2].low,
        events[index - 1].low,
        events[index + 1].low,
        events[index + 2].low,
    )
    return value < min(peers)


def _is_pivot_high(events: tuple[WorkspaceMarketEvent, ...], index: int) -> bool:
    value = events[index].high
    peers = (
        events[index - 2].high,
        events[index - 1].high,
        events[index + 1].high,
        events[index + 2].high,
    )
    return value > max(peers)


def _last_confirmed_pivot(
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
    *,
    kind: str,
    entry_price: float,
) -> PivotLevel | None:
    earliest = max(PIVOT_SIDE_BARS, signal_index - PIVOT_LOOKBACK_BARS)
    latest = signal_index - PIVOT_SIDE_BARS
    if latest < earliest:
        return None
    for pivot_index in range(latest, earliest - 1, -1):
        if kind == "SUPPORT":
            if not _is_pivot_low(events, pivot_index):
                continue
            price = events[pivot_index].low
            if price >= entry_price:
                continue
        else:
            assert kind == "RESISTANCE"
            if not _is_pivot_high(events, pivot_index):
                continue
            price = events[pivot_index].high
            if price <= entry_price:
                continue
        return PivotLevel(
            timestamp=events[pivot_index].timestamp,
            price=price,
            kind=kind,
            age_bars=signal_index - pivot_index,
        )
    return None


def _structure_for_trade(
    base: TradeContextEvidence,
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
) -> tuple[PivotLevel | None, PivotLevel | None, float | None, float | None]:
    trade = base.trade
    if trade.direction == "BUY":
        sl_pivot = _last_confirmed_pivot(
            events,
            signal_index,
            kind="SUPPORT",
            entry_price=trade.entry_price,
        )
        tp_pivot = _last_confirmed_pivot(
            events,
            signal_index,
            kind="RESISTANCE",
            entry_price=trade.entry_price,
        )
    else:
        sl_pivot = _last_confirmed_pivot(
            events,
            signal_index,
            kind="RESISTANCE",
            entry_price=trade.entry_price,
        )
        tp_pivot = _last_confirmed_pivot(
            events,
            signal_index,
            kind="SUPPORT",
            entry_price=trade.entry_price,
        )

    def distance_r(pivot: PivotLevel | None) -> float | None:
        if pivot is None:
            return None
        return abs(trade.entry_price - pivot.price) / trade.stop_loss_distance

    return sl_pivot, tp_pivot, distance_r(sl_pivot), distance_r(tp_pivot)


def _build_lifecycle_evidence(
    runtime: EntryExitContextRuntime,
    base_rows: tuple[TradeContextEvidence, ...],
) -> tuple[LifecycleEvidence, ...]:
    algorithm = runtime.algorithm
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    source = algorithm.source
    signal_filter = algorithm.signal_filter
    assert source is not None
    assert signal_filter is not None

    events = tuple(
        runtime.strategy_events[timestamp]
        for timestamp in sorted(runtime.strategy_events)
    )
    event_index = {event.timestamp: index for index, event in enumerate(events)}
    alligator_observations = tuple(signal_filter.observations)
    alligator_index = {
        item.timestamp: index for index, item in enumerate(alligator_observations)
    }
    macd_observations = tuple(source.observations)
    macd_index = {item.timestamp: index for index, item in enumerate(macd_observations)}

    rows: list[LifecycleEvidence] = []
    for base in base_rows:
        trade = base.trade
        timestamp = trade.signal_timestamp
        e_index = event_index.get(timestamp)
        a_index = alligator_index.get(timestamp)
        m_index = macd_index.get(timestamp)
        assert e_index is not None and e_index >= 8
        assert a_index is not None and a_index >= 8
        assert m_index is not None and m_index >= 2

        current_alligator = alligator_observations[a_index]
        previous_alligator = alligator_observations[a_index - 1]
        previous2_alligator = alligator_observations[a_index - 2]
        opening = _required_float(current_alligator.normalized_opening, "opening")
        opening_prev = _required_float(
            previous_alligator.normalized_opening,
            "opening_prev",
        )
        opening_prev2 = _required_float(
            previous2_alligator.normalized_opening,
            "opening_prev2",
        )
        slope = _required_float(current_alligator.normalized_slope, "slope")
        slope_prev = _required_float(previous_alligator.normalized_slope, "slope_prev")
        slope_prev2 = _required_float(
            previous2_alligator.normalized_slope,
            "slope_prev2",
        )

        macd_values = _macd_metrics(trade.direction, macd_observations, m_index)
        sl_pivot, tp_pivot, sl_distance_r, tp_distance_r = _structure_for_trade(
            base,
            events,
            e_index,
        )

        bars_since_flat = _bars_since_condition_40(
            alligator_observations,
            a_index,
            lambda item: _regime_direction(item) is None,
        )
        bars_since_opposite = _bars_since_condition_40(
            alligator_observations,
            a_index,
            lambda item: (
                _regime_direction(item) is not None
                and _regime_direction(item) != trade.direction
            ),
        )

        rows.append(
            LifecycleEvidence(
                base=base,
                efficiency_3=_efficiency(trade.direction, events, e_index, 3),
                efficiency_5=_efficiency(trade.direction, events, e_index, 5),
                efficiency_8=_efficiency(trade.direction, events, e_index, 8),
                progress_30_r=_progress_r(
                    trade.direction,
                    events,
                    e_index,
                    2,
                    trade.stop_loss_distance,
                ),
                progress_60_r=_progress_r(
                    trade.direction,
                    events,
                    e_index,
                    4,
                    trade.stop_loss_distance,
                ),
                progress_120_r=_progress_r(
                    trade.direction,
                    events,
                    e_index,
                    8,
                    trade.stop_loss_distance,
                ),
                ordering_stability_3=_ordering_stability(
                    trade.direction,
                    alligator_observations,
                    a_index,
                    3,
                ),
                ordering_stability_5=_ordering_stability(
                    trade.direction,
                    alligator_observations,
                    a_index,
                    5,
                ),
                ordering_stability_8=_ordering_stability(
                    trade.direction,
                    alligator_observations,
                    a_index,
                    8,
                ),
                same_regime_age=_consecutive_same_regime(
                    trade.direction,
                    alligator_observations,
                    a_index,
                ),
                bars_since_flat_40=bars_since_flat,
                bars_since_opposite_40=bars_since_opposite,
                regime_changes_8=_recent_regime_changes(
                    alligator_observations,
                    a_index,
                    8,
                ),
                ordering_changes_8=_recent_ordering_changes(
                    alligator_observations,
                    a_index,
                    8,
                ),
                opening_delta_1=opening - opening_prev,
                opening_delta_2=opening - opening_prev2,
                slope_delta_1=slope - slope_prev,
                slope_delta_2=slope - slope_prev2,
                macd_directional_value=macd_values[0],
                macd_depth_percentile_20=macd_values[1],
                macd_recovery_from_extreme_20=macd_values[2],
                bars_since_macd_extreme_20=macd_values[3],
                macd_delta_1=macd_values[4],
                macd_delta_2=macd_values[5],
                directional_histogram=macd_values[6],
                directional_histogram_delta_1=macd_values[7],
                structural_sl=sl_pivot,
                structural_tp=tp_pivot,
                structural_sl_distance_r=sl_distance_r,
                structural_tp_distance_r=tp_distance_r,
            )
        )
    return tuple(rows)


def _median(rows: tuple[LifecycleEvidence, ...], attr: str) -> float:
    assert rows
    return float(statistics.median(float(getattr(item, attr)) for item in rows))


def _optional_median(rows: tuple[LifecycleEvidence, ...], attr: str) -> float | None:
    values = tuple(
        float(value) for item in rows if (value := getattr(item, attr)) is not None
    )
    if not values:
        return None
    return float(statistics.median(values))


def _format_optional(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "NONE"
    return f"{value:.3f}{suffix}"


def _outcome_groups(
    rows: tuple[LifecycleEvidence, ...],
) -> dict[str, tuple[LifecycleEvidence, ...]]:
    outcomes = (
        OUTCOME_STOP_LOSS,
        OUTCOME_TAKE_PROFIT,
        OUTCOME_WIN_PD,
        OUTCOME_LOSS_PD,
        OUTCOME_BREAK_EVEN,
    )
    return {
        outcome: tuple(item for item in rows if item.base.outcome == outcome)
        for outcome in outcomes
    }


def _group_line(name: str, rows: tuple[LifecycleEvidence, ...]) -> str:
    sl_found = sum(item.structural_sl is not None for item in rows)
    tp_found = sum(item.structural_tp is not None for item in rows)
    sl_median = _optional_median(rows, "structural_sl_distance_r")
    tp_median = _optional_median(rows, "structural_tp_distance_r")
    return (
        f"    {name}=n:{len(rows)},"
        f"eff3:{_median(rows, 'efficiency_3'):+.3f},"
        f"eff5:{_median(rows, 'efficiency_5'):+.3f},"
        f"eff8:{_median(rows, 'efficiency_8'):+.3f},"
        f"progress30/60/120:"
        f"{_median(rows, 'progress_30_r'):+.2f}/"
        f"{_median(rows, 'progress_60_r'):+.2f}/"
        f"{_median(rows, 'progress_120_r'):+.2f}R,"
        f"order3/5/8:"
        f"{_median(rows, 'ordering_stability_3'):.2f}/"
        f"{_median(rows, 'ordering_stability_5'):.2f}/"
        f"{_median(rows, 'ordering_stability_8'):.2f},"
        f"regime_age:{_median(rows, 'same_regime_age'):.1f},"
        f"since_flat:{_median(rows, 'bars_since_flat_40'):.1f},"
        f"since_opp:{_median(rows, 'bars_since_opposite_40'):.1f},"
        f"regime_changes8:{_median(rows, 'regime_changes_8'):.1f},"
        f"macd_depth:{_median(rows, 'macd_depth_percentile_20'):.3f},"
        f"macd_recovery:{_median(rows, 'macd_recovery_from_extreme_20'):.3f},"
        f"macd_extreme_age:{_median(rows, 'bars_since_macd_extreme_20'):.1f},"
        f"structSL:{sl_found}/{len(rows)}@{_format_optional(sl_median, 'R')},"
        f"structTP:{tp_found}/{len(rows)}@{_format_optional(tp_median, 'R')}"
    )


def _structure_matrix(rows: tuple[LifecycleEvidence, ...]) -> tuple[str, ...]:
    lines: list[str] = []
    for threshold in (1.0, 1.5, 2.0, 3.0):
        matched = tuple(
            item
            for item in rows
            if item.structural_sl_distance_r is not None
            and item.structural_sl_distance_r > threshold
        )
        outcomes = Counter(item.base.outcome for item in matched)
        lines.append(
            "    "
            f"structural_sl>{threshold:.1f}R="
            f"n:{len(matched)},SL:{outcomes[OUTCOME_STOP_LOSS]},"
            f"TP:{outcomes[OUTCOME_TAKE_PROFIT]},"
            f"WIN_PD:{outcomes[OUTCOME_WIN_PD]},"
            f"LOSS_PD:{outcomes[OUTCOME_LOSS_PD]},"
            f"BE:{outcomes[OUTCOME_BREAK_EVEN]}"
        )
    return tuple(lines)


def _manual_line(item: LifecycleEvidence) -> str:
    base = item.base
    trade = base.trade
    label = MANUAL_CASE_LABELS[trade.signal_timestamp]
    return (
        "    "
        f"{trade.signal_timestamp.isoformat()} {trade.direction} {label} "
        f"{base.outcome} pnl:{trade.final_profit:+.2f} "
        f"macro_pos:{base.macro_position_ratio:.3f} "
        f"eff3/5/8:{item.efficiency_3:+.2f}/"
        f"{item.efficiency_5:+.2f}/{item.efficiency_8:+.2f} "
        f"order3/5/8:{item.ordering_stability_3:.2f}/"
        f"{item.ordering_stability_5:.2f}/{item.ordering_stability_8:.2f} "
        f"regime_age:{item.same_regime_age} "
        f"flat_age:{item.bars_since_flat_40} opp_age:{item.bars_since_opposite_40} "
        f"changes8:{item.regime_changes_8}/{item.ordering_changes_8} "
        f"open_d1/d2:{item.opening_delta_1:+.3f}/{item.opening_delta_2:+.3f} "
        f"macd_depth:{item.macd_depth_percentile_20:.2f} "
        f"macd_recovery:{item.macd_recovery_from_extreme_20:.2f} "
        f"macd_extreme_age:{item.bars_since_macd_extreme_20} "
        f"structSL:{_format_optional(item.structural_sl_distance_r, 'R')} "
        f"structTP:{_format_optional(item.structural_tp_distance_r, 'R')}"
    )


def _write_csv(rows: tuple[LifecycleEvidence, ...]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "signal_utc",
        "direction",
        "outcome",
        "final_profit",
        "macro_position_retrospective",
        "manual_label",
        "efficiency_3_causal",
        "efficiency_5_causal",
        "efficiency_8_causal",
        "progress_30_r_causal",
        "progress_60_r_causal",
        "progress_120_r_causal",
        "ordering_stability_3_causal",
        "ordering_stability_5_causal",
        "ordering_stability_8_causal",
        "same_regime_age_causal",
        "bars_since_flat_40_causal",
        "bars_since_opposite_40_causal",
        "regime_changes_8_causal",
        "ordering_changes_8_causal",
        "opening_delta_1_causal",
        "opening_delta_2_causal",
        "slope_delta_1_causal",
        "slope_delta_2_causal",
        "macd_directional_value_causal",
        "macd_depth_percentile_20_causal",
        "macd_recovery_from_extreme_20_causal",
        "bars_since_macd_extreme_20_causal",
        "macd_delta_1_causal",
        "macd_delta_2_causal",
        "directional_histogram_causal",
        "directional_histogram_delta_1_causal",
        "structural_sl_kind",
        "structural_sl_utc",
        "structural_sl_price",
        "structural_sl_age_bars",
        "structural_sl_distance_r",
        "structural_tp_kind",
        "structural_tp_utc",
        "structural_tp_price",
        "structural_tp_age_bars",
        "structural_tp_distance_r",
    )
    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for item in rows:
            base = item.base
            trade = base.trade
            sl = item.structural_sl
            tp = item.structural_tp
            writer.writerow(
                {
                    "signal_utc": trade.signal_timestamp.isoformat(),
                    "direction": trade.direction,
                    "outcome": base.outcome,
                    "final_profit": f"{trade.final_profit:.4f}",
                    "macro_position_retrospective": (
                        f"{base.macro_position_ratio:.6f}"
                    ),
                    "manual_label": MANUAL_CASE_LABELS.get(
                        trade.signal_timestamp,
                        "",
                    ),
                    "efficiency_3_causal": f"{item.efficiency_3:.6f}",
                    "efficiency_5_causal": f"{item.efficiency_5:.6f}",
                    "efficiency_8_causal": f"{item.efficiency_8:.6f}",
                    "progress_30_r_causal": f"{item.progress_30_r:.6f}",
                    "progress_60_r_causal": f"{item.progress_60_r:.6f}",
                    "progress_120_r_causal": f"{item.progress_120_r:.6f}",
                    "ordering_stability_3_causal": f"{item.ordering_stability_3:.6f}",
                    "ordering_stability_5_causal": f"{item.ordering_stability_5:.6f}",
                    "ordering_stability_8_causal": f"{item.ordering_stability_8:.6f}",
                    "same_regime_age_causal": item.same_regime_age,
                    "bars_since_flat_40_causal": item.bars_since_flat_40,
                    "bars_since_opposite_40_causal": item.bars_since_opposite_40,
                    "regime_changes_8_causal": item.regime_changes_8,
                    "ordering_changes_8_causal": item.ordering_changes_8,
                    "opening_delta_1_causal": f"{item.opening_delta_1:.6f}",
                    "opening_delta_2_causal": f"{item.opening_delta_2:.6f}",
                    "slope_delta_1_causal": f"{item.slope_delta_1:.6f}",
                    "slope_delta_2_causal": f"{item.slope_delta_2:.6f}",
                    "macd_directional_value_causal": (
                        f"{item.macd_directional_value:.8f}"
                    ),
                    "macd_depth_percentile_20_causal": (
                        f"{item.macd_depth_percentile_20:.6f}"
                    ),
                    "macd_recovery_from_extreme_20_causal": (
                        f"{item.macd_recovery_from_extreme_20:.6f}"
                    ),
                    "bars_since_macd_extreme_20_causal": (
                        item.bars_since_macd_extreme_20
                    ),
                    "macd_delta_1_causal": f"{item.macd_delta_1:.8f}",
                    "macd_delta_2_causal": f"{item.macd_delta_2:.8f}",
                    "directional_histogram_causal": (
                        f"{item.directional_histogram:.8f}"
                    ),
                    "directional_histogram_delta_1_causal": (
                        f"{item.directional_histogram_delta_1:.8f}"
                    ),
                    "structural_sl_kind": "" if sl is None else sl.kind,
                    "structural_sl_utc": (
                        "" if sl is None else sl.timestamp.isoformat()
                    ),
                    "structural_sl_price": "" if sl is None else f"{sl.price:.5f}",
                    "structural_sl_age_bars": "" if sl is None else sl.age_bars,
                    "structural_sl_distance_r": (
                        ""
                        if item.structural_sl_distance_r is None
                        else f"{item.structural_sl_distance_r:.6f}"
                    ),
                    "structural_tp_kind": "" if tp is None else tp.kind,
                    "structural_tp_utc": (
                        "" if tp is None else tp.timestamp.isoformat()
                    ),
                    "structural_tp_price": "" if tp is None else f"{tp.price:.5f}",
                    "structural_tp_age_bars": "" if tp is None else tp.age_bars,
                    "structural_tp_distance_r": (
                        ""
                        if item.structural_tp_distance_r is None
                        else f"{item.structural_tp_distance_r:.6f}"
                    ),
                }
            )
    return OUTPUT_CSV


def main() -> None:
    """Run production 6K Replay and print 7L lifecycle diagnostics."""
    assert_frozen_oos_snapshot()
    runtime = EntryExitContextRuntime(
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
    algorithm = runtime.algorithm
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    source = algorithm.source
    signal_filter = algorithm.signal_filter
    assert source is not None
    assert signal_filter is not None

    observations = tuple(signal_filter.observations)
    active_runs = _split_active_runs(observations)
    macros = _split_macro_trends(observations, active_runs)
    base_rows = _build_evidence(runtime, macros)
    rows = _build_lifecycle_evidence(runtime, base_rows)

    assert len(rows) == 59
    assert all(item.base.signal_record.accepted for item in rows)
    assert all(
        item.base.observation.available_at <= item.base.trade.signal_timestamp
        for item in rows
    )
    assert all(
        item.structural_sl is None
        or item.structural_sl.timestamp <= item.base.trade.signal_timestamp
        for item in rows
    )
    assert all(
        item.structural_tp is None
        or item.structural_tp.timestamp <= item.base.trade.signal_timestamp
        for item in rows
    )

    groups = _outcome_groups(rows)
    assert len(groups[OUTCOME_STOP_LOSS]) == 9
    assert len(groups[OUTCOME_TAKE_PROFIT]) == 2
    assert sum(len(items) for items in groups.values()) == 59

    manual_rows = tuple(
        item for item in rows if item.base.trade.signal_timestamp in MANUAL_CASE_LABELS
    )
    assert len(manual_rows) == len(MANUAL_CASE_LABELS)

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted
    output_csv = _write_csv(rows)

    summary = runtime.historical_summary
    assert summary is not None
    print("Algorithm Workspace Candidate F Trend Lifecycle Entry Quality 2025 result")
    print("  mode=PRODUCTION_6K_CAUSAL_TREND_LIFECYCLE_DIAGNOSTIC_ONLY")
    print("  production_logic_changed=False")
    print("  production_profile_changed=False")
    print("  entry_gate_applied=False")
    print("  sl_tp_changed=False")
    print("  exit_policy_changed=False")
    print("  future_price_used_as_feature=False")
    print("  retrospective_macro_position_used_as_gate=False")
    print("  pivot_confirmation=2_left_2_right_completed_M15_bars")
    print(f"  pivot_lookback_bars={PIVOT_LOOKBACK_BARS}")
    print(
        "  baseline="
        f"trades:{summary.opened_trades},wins:{summary.winning_trades},"
        f"losses:{summary.losing_trades},break_even:{summary.break_even_trades},"
        f"sl:{summary.close_reason_count('STOP_LOSS')},"
        f"tp:{summary.close_reason_count('TAKE_PROFIT')},"
        f"net:{summary.net_profit:+.2f},pf:{summary.profit_factor:.4f},"
        f"dd:{summary.maximum_drawdown:.2f}"
    )
    print("  outcome_group_medians:")
    for outcome, items in groups.items():
        if items:
            print(_group_line(outcome, items))
    print("  structural_sl_distance_diagnostic_matrix_not_a_gate:")
    for line in _structure_matrix(rows):
        print(line)
    print("  manually_reviewed_case_fingerprints:")
    for item in manual_rows:
        print(_manual_line(item))
    print(f"  output_csv={output_csv}")
    print("  completed_bars_only=True")
    print("  causal_signal_and_prior_completed_bars_only=True")
    print("  broker_requests=0")
    print(f"  broker_execution_attempted={broker_execution_attempted}")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_TREND_LIFECYCLE_ENTRY_QUALITY_2025_CHECK=OK")


if __name__ == "__main__":
    main()
