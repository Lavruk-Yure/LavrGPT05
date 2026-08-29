# -*- coding: utf-8 -*-
"""RoadMap104 / T104-20: causal Williams Fractal structural-SL anatomy.

TEST_ONLY paired replay over the T104-15 identity-normalized GREEN 8C.1
first-leg entries. A canonical Williams fractal has two bars on each side;
therefore, at a NEXT_M15_OPEN entry, its centre must be at most entry_index-3.
Only completed M15 bars are inspected and no outcome selects a fractal.

Missing or non-protective fractals use the fixed 12-pip fallback so every
variant retains the identical entry inventory. The bounded baseline uses a
buffered fractal only when its distance is within 12..24 pips, matching the
existing bounded structural-SL convention; otherwise it also uses 12 pips.
Every variant keeps the existing 2R TP relative to its actual SL distance.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from dataclasses import dataclass
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
TEST_ID = "T104-20"
FRACTAL_PERIODS = 2
BUFFER_PIPS = 1.0
MINIMUM_SL_PIPS = 12.0
MAXIMUM_SL_PIPS = 24.0
TAKE_PROFIT_R = 2.0
EPSILON = 1e-9

FIXED = "FIXED_12_2R"
BOUNDED = "BOUNDED_12_24_STRUCTURAL_2R"
FRACTAL = "FRACTAL_2R"
FRACTAL_BUFFER = "FRACTAL_PLUS_1P_2R"
VARIANTS = (FIXED, BOUNDED, FRACTAL, FRACTAL_BUFFER)


def _load_base_module() -> ModuleType:
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm104_t104_20_normalized_green_8c1_base"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()
WINDOWS = getattr(BASE, "WINDOWS")
_run_normalized: Callable[..., Any] = getattr(BASE, "_run_normalized")


def _load_opening_module() -> ModuleType:
    file_path = Path(__file__).with_name(
        "run_algorithm_workspace_alligator_opening_expansion_2025_2026_check.py"
    )
    spec = importlib.util.spec_from_file_location(
        "rm104_t104_20_green_8c1_opening_base", file_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


OPENING_BASE = _load_opening_module()
CORE_BASE = getattr(OPENING_BASE, "BASE")
PIP_SIZE = float(getattr(CORE_BASE, "PIP_SIZE"))
FIXED_VOLUME = float(getattr(CORE_BASE, "FIXED_VOLUME"))
EXPECTED_M15_DELTA = getattr(CORE_BASE, "EXPECTED_M15_DELTA")
TradeResult = getattr(CORE_BASE, "TradeResult")
_entry_price: Callable[..., float] = getattr(CORE_BASE, "_entry_price")
_close_at_market: Callable[..., float] = getattr(CORE_BASE, "_close_at_market")
_summary: Callable[..., Any] = getattr(OPENING_BASE, "_summary")
_summary_text: Callable[..., str] = getattr(OPENING_BASE, "_summary_text")
_load_indicator_run: Callable[..., Any] = getattr(OPENING_BASE, "_load_indicator_run")


@dataclass(frozen=True, slots=True)
class FractalReference:
    """Last direction-appropriate causal confirmed Williams fractal."""

    center_index: int
    confirmed_index: int
    price: float
    distance_pips: float


def _is_fractal(events: tuple[Any, ...], center: int, direction: str) -> bool:
    left = events[center - FRACTAL_PERIODS : center]  # noqa: E203
    right = events[center + 1 : center + FRACTAL_PERIODS + 1]  # noqa: E203
    if direction == "BUY":
        price = float(events[center].low)
        return all(price < float(event.low) for event in (*left, *right))
    assert direction == "SELL"
    price = float(events[center].high)
    return all(price > float(event.high) for event in (*left, *right))


def _last_confirmed_fractal(
    events: tuple[Any, ...], candidate: Any
) -> FractalReference | None:
    """Find the last fractal whose second right bar closed before entry."""
    entry_index = int(candidate.entry_index)
    entry_price = _entry_price(events[entry_index], str(candidate.direction))
    latest_center = entry_index - FRACTAL_PERIODS - 1
    for center in range(latest_center, FRACTAL_PERIODS - 1, -1):
        if not _is_fractal(events, center, str(candidate.direction)):
            continue
        price = float(
            events[center].low if candidate.direction == "BUY" else events[center].high
        )
        distance = (
            entry_price - price if candidate.direction == "BUY" else price - entry_price
        ) / PIP_SIZE
        return FractalReference(
            center_index=center,
            confirmed_index=center + FRACTAL_PERIODS,
            price=price,
            distance_pips=distance,
        )
    return None


def _variant_distance(name: str, reference: FractalReference | None) -> float:
    if name == FIXED or reference is None or reference.distance_pips <= EPSILON:
        return MINIMUM_SL_PIPS
    raw = reference.distance_pips
    if name == FRACTAL:
        return raw
    buffered = raw + BUFFER_PIPS
    if name == FRACTAL_BUFFER:
        return buffered
    assert name == BOUNDED
    if MINIMUM_SL_PIPS <= buffered <= MAXIMUM_SL_PIPS:
        return buffered
    return MINIMUM_SL_PIPS


def _simulate(run: Any, candidate: Any, stop_pips: float) -> Any:
    assert stop_pips > 0.0 and math.isfinite(stop_pips)
    entry_index = int(candidate.entry_index)
    entry_price = _entry_price(run.events[entry_index], candidate.direction)
    stop_distance = stop_pips * PIP_SIZE
    take_distance = stop_distance * TAKE_PROFIT_R
    sign = 1.0 if candidate.direction == "BUY" else -1.0
    stop_price = entry_price - sign * stop_distance
    take_price = entry_price + sign * take_distance
    close_index = len(run.events) - 1
    close_price = _close_at_market(run.events[close_index], candidate.direction)
    close_reason = "SESSION_END"
    for index in range(entry_index, len(run.events)):
        event = run.events[index]
        if candidate.direction == "BUY":
            stop_touched = event.low <= stop_price
            take_touched = event.high >= take_price
        else:
            stop_touched = event.high >= stop_price
            take_touched = event.low <= take_price
        # Preserve the baseline's conservative SL-first same-bar convention.
        if stop_touched:
            close_index, close_price, close_reason = index, stop_price, "STOP_LOSS"
            break
        if take_touched:
            close_index, close_price, close_reason = index, take_price, "TAKE_PROFIT"
            break
    pnl = (close_price - entry_price) * FIXED_VOLUME * sign
    return TradeResult(
        direction=candidate.direction,
        start_timestamp=candidate.start_timestamp,
        confirm_timestamp=candidate.confirm_timestamp,
        entry_timestamp=candidate.entry_timestamp,
        close_timestamp=run.events[close_index].timestamp + EXPECTED_M15_DELTA,
        entry_price=entry_price,
        close_price=close_price,
        close_reason=close_reason,
        pnl=pnl,
        holding_bars=close_index - entry_index + 1,
    )


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _fmt(value: float | None) -> str:
    return "NONE" if value is None else f"{value:.3f}"


def _distance_text(references: tuple[FractalReference | None, ...]) -> str:
    values = [item.distance_pips for item in references if item is not None]
    below = sum(value < MINIMUM_SL_PIPS for value in values)
    inside = sum(MINIMUM_SL_PIPS <= value <= MAXIMUM_SL_PIPS for value in values)
    above = sum(value > MAXIMUM_SL_PIPS for value in values)
    denominator = len(values)

    def ratio(count: int) -> float:
        return count / denominator if denominator else 0.0

    return (
        f"median:{_fmt(_percentile(values, 0.50))},"
        f"p25:{_fmt(_percentile(values, 0.25))},"
        f"p75:{_fmt(_percentile(values, 0.75))},"
        f"below_12:{below},below_12_fraction:{ratio(below):.6f},"
        f"inside_12_24:{inside},inside_12_24_fraction:{ratio(inside):.6f},"
        f"above_24:{above},above_24_fraction:{ratio(above):.6f},"
        f"missing:{sum(item is None for item in references)}"
    )


def main() -> int:
    results: dict[str, Any] = {}
    for window in WINDOWS:
        print(f"  running_period={window.label}", flush=True)
        normalized = _run_normalized(window)
        base = normalized["data"]["base"]
        run = _load_indicator_run(window)
        candidates = tuple(base["candidates"])
        survivor_indices = tuple(
            getattr(BASE, "_first_leg_survivor_indices")(candidates)
        )
        selected = tuple(candidates[index] for index in survivor_indices)
        references = tuple(
            _last_confirmed_fractal(tuple(run.events), candidate)
            for candidate in selected
        )
        assert len(selected) == len(normalized["normalized_baseline"])
        assert all(
            item is None or item.confirmed_index < int(candidate.entry_index)
            for candidate, item in zip(selected, references, strict=True)
        )
        variants = {
            name: tuple(
                _simulate(run, candidate, _variant_distance(name, reference))
                for candidate, reference in zip(selected, references, strict=True)
            )
            for name in VARIANTS
        }
        results[window.label] = (references, variants)

    print("T104-20 Fractal Structural SL Anatomy result")
    print(f"  test_id={TEST_ID}")
    print("  mode=TEST_ONLY")
    print("  inventory=T104_15_IDENTITY_NORMALIZED_GREEN_8C1_FIRST_LEG")
    print("  williams_fractal_periods=2")
    print("  confirmation=AFTER_TWO_RIGHT_M15_BARS_COMPLETED")
    print("  bounded_baseline=BUFFERED_FRACTAL_IF_INSIDE_12_24_ELSE_FIXED_12")
    print("  missing_or_non_protective_fractal_policy=FIXED_12_FALLBACK")
    print("  take_profit_policy=EXISTING_2R_FROM_ACTUAL_SL_DISTANCE")
    for window in WINDOWS:
        references, variants = results[window.label]
        print(f"  {window.label}/FRACTAL_DISTANCE={_distance_text(references)}")
        non_protective = sum(
            item is not None and item.distance_pips <= EPSILON for item in references
        )
        print(f"  {window.label}/NON_PROTECTIVE={non_protective}")
        for name in VARIANTS:
            summary = _summary(variants[name])
            print(f"  {window.label}/{name}={_summary_text(summary)}")
            assert summary.trades == len(references)

    print("  production_logic_changed=False")
    print("  candidate_f_changed=False")
    print("  entry_logic_changed=False")
    print("  exit_logic_changed=False")
    print("  tp_logic_changed=False")
    print("  bbw_changed=False")
    print("  ac_changed=False")
    print("  stochastic_changed=False")
    print("  dmi_adx_changed=False")
    print("  completed_bars_only=True")
    print("  future_price_used=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T104_20_FRACTAL_STRUCTURAL_SL_ANATOMY_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
