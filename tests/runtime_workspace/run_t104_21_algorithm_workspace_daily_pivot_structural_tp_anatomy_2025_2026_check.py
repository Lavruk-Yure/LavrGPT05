# -*- coding: utf-8 -*-
"""RoadMap104 / T104-21: causal Traditional Daily Pivot TP anatomy.

TEST_ONLY anatomy over the T104-15 identity-normalized GREEN 8C.1 first-leg
inventory. Daily levels for an M15 entry are calculated only from the fully
completed preceding observed trading day. They are therefore fixed and known
before the entry day starts. No pivot outcome participates in trade selection.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BASE_SCRIPT_NAME = (
    "run_t104_15_algorithm_workspace_causal_execution_identity_normalization_"
    "2025_2026_check.py"
)
TEST_ID = "T104-21"
STOP_LOSS_PIPS = 12.0
TAKE_PROFIT_PIPS = 24.0
EPSILON = 1e-12


def _load_base_module() -> ModuleType:
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm104_t104_21_normalized_green_8c1_base"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()
WINDOWS = getattr(BASE, "WINDOWS")
_run_normalized: Callable[..., Any] = getattr(BASE, "_run_normalized")
_first_leg_survivor_indices: Callable[..., Any] = getattr(
    BASE, "_first_leg_survivor_indices"
)


def _load_opening_module() -> ModuleType:
    file_path = Path(__file__).with_name(
        "run_algorithm_workspace_alligator_opening_expansion_2025_2026_check.py"
    )
    spec = importlib.util.spec_from_file_location(
        "rm104_t104_21_green_8c1_opening_base", file_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


OPENING_BASE = _load_opening_module()
CORE_BASE = getattr(OPENING_BASE, "BASE")
PIP_SIZE = float(getattr(CORE_BASE, "PIP_SIZE"))
_entry_price: Callable[..., float] = getattr(CORE_BASE, "_entry_price")
_load_indicator_run: Callable[..., Any] = getattr(OPENING_BASE, "_load_indicator_run")


@dataclass(frozen=True, slots=True)
class DailyLevels:
    source_day: date
    p: float
    r1: float
    r2: float
    r3: float
    s1: float
    s2: float
    s3: float


@dataclass(frozen=True, slots=True)
class PivotAnatomy:
    direction: str
    outcome: str
    level: str | None
    distance_pips: float | None
    distance_bucket: str
    hit: bool
    breakout: bool
    next_level: str | None
    next_reached: bool
    reversal_to_sl: bool
    relation_to_2r: str


def _daily_levels(events: tuple[Any, ...]) -> dict[date, DailyLevels]:
    """Map each day to levels derived from the preceding completed day."""
    daily: dict[date, list[float]] = {}
    for event in events:
        day = event.timestamp.date()
        values = daily.get(day)
        if values is None:
            daily[day] = [float(event.high), float(event.low), float(event.close)]
        else:
            values[0] = max(values[0], float(event.high))
            values[1] = min(values[1], float(event.low))
            values[2] = float(event.close)

    result: dict[date, DailyLevels] = {}
    days = sorted(daily)
    for current_day, previous_day in zip(days[1:], days):
        high, low, close = daily[previous_day]
        p = (high + low + close) / 3.0
        result[current_day] = DailyLevels(
            source_day=previous_day,
            p=p,
            r1=2.0 * p - low,
            r2=p + high - low,
            r3=high + 2.0 * (p - low),
            s1=2.0 * p - high,
            s2=p - high + low,
            s3=low - 2.0 * (high - p),
        )
    return result


def _favorable_levels(
    levels: DailyLevels, direction: str
) -> tuple[tuple[str, float], ...]:
    if direction == "BUY":
        return ("R1", levels.r1), ("R2", levels.r2), ("R3", levels.r3)
    assert direction == "SELL"
    return ("S1", levels.s1), ("S2", levels.s2), ("S3", levels.s3)


def _distance_bucket(distance: float | None) -> str:
    if distance is None:
        return "NO_FAVORABLE_PIVOT"
    if distance < STOP_LOSS_PIPS - EPSILON:
        return "CLOSER_THAN_1R"
    if distance <= TAKE_PROFIT_PIPS + EPSILON:
        return "BETWEEN_1R_AND_2R"
    return "BEYOND_2R"


def _first_touch_indices(
    events: tuple[Any, ...], candidate: Any, pivot: float, stop: float, take: float
) -> tuple[int | None, int | None, int | None, int | None]:
    hit_index = breakout_index = stop_index = take_index = None
    for index in range(int(candidate.entry_index), len(events)):
        event = events[index]
        if candidate.direction == "BUY":
            stop_touched = float(event.low) <= stop
            take_touched = float(event.high) >= take
            hit_touched = float(event.high) >= pivot
            broken = float(event.high) > pivot + EPSILON
        else:
            stop_touched = float(event.high) >= stop
            take_touched = float(event.low) <= take
            hit_touched = float(event.low) <= pivot
            broken = float(event.low) < pivot - EPSILON

        # Match the established conservative SL-first same-M15-bar convention.
        if stop_touched:
            stop_index = index
            break
        if take_touched and take_index is None:
            take_index = index
        if hit_touched and hit_index is None:
            hit_index = index
        if broken and breakout_index is None:
            breakout_index = index
    return hit_index, breakout_index, stop_index, take_index


def _anatomy(
    events: tuple[Any, ...], candidate: Any, outcome: str, levels: DailyLevels
) -> PivotAnatomy:
    entry = _entry_price(events[int(candidate.entry_index)], candidate.direction)
    sign = 1.0 if candidate.direction == "BUY" else -1.0
    stop = entry - sign * STOP_LOSS_PIPS * PIP_SIZE
    take = entry + sign * TAKE_PROFIT_PIPS * PIP_SIZE
    favorable = _favorable_levels(levels, candidate.direction)
    available = [
        (name, price) for name, price in favorable if sign * (price - entry) > EPSILON
    ]
    if not available:
        return PivotAnatomy(
            candidate.direction,
            outcome,
            None,
            None,
            _distance_bucket(None),
            False,
            False,
            None,
            False,
            False,
            "NO_FAVORABLE_PIVOT",
        )

    name, price = min(available, key=lambda item: sign * (item[1] - entry))
    distance = sign * (price - entry) / PIP_SIZE
    hit_index, breakout_index, stop_index, take_index = _first_touch_indices(
        events, candidate, price, stop, take
    )
    next_name = next_price = None
    original_index = next(i for i, item in enumerate(favorable) if item[0] == name)
    if original_index + 1 < len(favorable):
        next_name, next_price = favorable[original_index + 1]
    next_reached = False
    if breakout_index is not None and next_price is not None:
        continuation_end = stop_index or len(events)
        for event in events[breakout_index:continuation_end]:
            if candidate.direction == "BUY" and float(event.high) >= next_price:
                next_reached = True
                break
            if candidate.direction == "SELL" and float(event.low) <= next_price:
                next_reached = True
                break
    reversal_to_sl = (
        breakout_index is not None and stop_index is not None and not next_reached
    )
    if hit_index is not None and (take_index is None or hit_index < take_index):
        relation = "PIVOT_REACHED_BEFORE_BASELINE_TP"
    elif take_index is not None and (hit_index is None or take_index < hit_index):
        relation = "BASELINE_TP_REACHED_BEFORE_PIVOT"
    elif hit_index is not None and take_index == hit_index:
        relation = "PIVOT_AND_BASELINE_TP_SAME_BAR"
    else:
        relation = "NEITHER_REACHED_BEFORE_SL_OR_END"
    return PivotAnatomy(
        candidate.direction,
        outcome,
        name,
        distance,
        _distance_bucket(distance),
        hit_index is not None,
        breakout_index is not None,
        next_name,
        next_reached,
        reversal_to_sl,
        relation,
    )


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _fmt(value: float | None) -> str:
    return "NONE" if value is None else f"{value:.3f}"


def _counts(rows: tuple[PivotAnatomy, ...], attribute: str) -> str:
    counts = Counter(str(getattr(row, attribute)) for row in rows)
    return "|".join(f"{key}:{counts[key]}" for key in sorted(counts)) or "NONE"


def _summary_text(rows: tuple[PivotAnatomy, ...]) -> str:
    distances = [row.distance_pips for row in rows if row.distance_pips is not None]
    hits = sum(row.hit for row in rows)
    breakouts = sum(row.breakout for row in rows)
    continuation_base = sum(row.breakout and row.next_level is not None for row in rows)
    continuations = sum(row.next_reached for row in rows)
    denominator = len(rows)

    def ratio(count: int, base: int = denominator) -> float:
        return count / base if base else 0.0

    return (
        f"trades:{denominator},distance_median:{_fmt(_percentile(distances, 0.50))},"
        f"distance_p25:{_fmt(_percentile(distances, 0.25))},"
        f"distance_p75:{_fmt(_percentile(distances, 0.75))},"
        f"levels:{_counts(rows, 'level')},"
        f"distance_vs_2r:{_counts(rows, 'distance_bucket')},hit:{hits},"
        f"hit_rate:{ratio(hits):.6f},breakout:{breakouts},"
        f"breakout_rate:{ratio(breakouts):.6f},next_level_continuation:{continuations},"
        f"next_level_continuation_rate:{ratio(continuations, continuation_base):.6f},"
        f"breakout_reversal_sl:{sum(row.reversal_to_sl for row in rows)},"
        f"relation_to_2r:{_counts(rows, 'relation_to_2r')}"
    )


def main() -> int:
    results: dict[str, tuple[PivotAnatomy, ...]] = {}
    for window in WINDOWS:
        print(f"  running_period={window.label}", flush=True)
        normalized = _run_normalized(window)
        base = normalized["data"]["base"]
        run = _load_indicator_run(window)
        events = tuple(run.events)
        candidates = tuple(base["candidates"])
        survivor_indices = tuple(_first_leg_survivor_indices(candidates))
        selected = tuple(candidates[index] for index in survivor_indices)
        trades = tuple(normalized["normalized_baseline"])
        daily = _daily_levels(events)
        assert len(selected) == len(trades)
        rows = tuple(
            _anatomy(
                events,
                candidate,
                str(trade.close_reason),
                daily[events[int(candidate.entry_index)].timestamp.date()],
            )
            for candidate, trade in zip(selected, trades, strict=True)
        )
        assert all(
            row.outcome in {"TAKE_PROFIT", "STOP_LOSS", "SESSION_END"} for row in rows
        )
        results[window.label] = rows

    print("T104-21 Daily Pivot Structural TP Anatomy result")
    print(f"  test_id={TEST_ID}")
    print("  mode=TEST_ONLY")
    print("  inventory=T104_15_IDENTITY_NORMALIZED_GREEN_8C1_FIRST_LEG")
    print("  pivot_type=TRADITIONAL")
    print("  pivot_timeframe=1D_FOR_M15_BASELINE")
    print("  pivot_source=PREVIOUS_COMPLETED_OBSERVED_TRADING_DAY")
    print("  levels=P_R1_R2_R3_S1_S2_S3_CANONICAL_ONLY")
    print("  favorable_levels=BUY_R1_R2_R3_ABOVE_ENTRY_SELL_S1_S2_S3_BELOW_ENTRY")
    print("  hit_definition=LEVEL_TOUCHED_BEFORE_SL")
    print("  breakout_definition=STRICTLY_THROUGH_LEVEL_BEFORE_SL")
    print("  same_bar_policy=SL_FIRST_CONSERVATIVE")
    print("  relation_target=EXISTING_FIXED_12P_SL_24P_2R_TP")
    for window in WINDOWS:
        rows = results[window.label]
        print(f"  {window.label}/ALL={_summary_text(rows)}")
        for direction in ("BUY", "SELL"):
            subset = tuple(row for row in rows if row.direction == direction)
            print(f"  {window.label}/{direction}={_summary_text(subset)}")
            for outcome in ("TAKE_PROFIT", "STOP_LOSS", "SESSION_END"):
                outcome_rows = tuple(row for row in subset if row.outcome == outcome)
                print(
                    f"  {window.label}/{direction}/{outcome}="
                    f"{_summary_text(outcome_rows)}"
                )

    print("  outcome_used_for_selection=False")
    print("  tuned_thresholds_added=False")
    print("  production_tp_policy_changed=False")
    print("  production_logic_changed=False")
    print("  candidate_f_changed=False")
    print("  entry_logic_changed=False")
    print("  exit_logic_changed=False")
    print("  sl_logic_changed=False")
    print("  bbw_changed=False")
    print("  ac_changed=False")
    print("  stochastic_changed=False")
    print("  dmi_adx_changed=False")
    print("  fractal_logic_changed=False")
    print("  completed_bars_only=True")
    print("  future_price_used=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T104_21_DAILY_PIVOT_STRUCTURAL_TP_ANATOMY_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
