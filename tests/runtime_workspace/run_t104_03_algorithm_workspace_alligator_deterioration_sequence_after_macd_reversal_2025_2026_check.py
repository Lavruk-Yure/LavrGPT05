# -*- coding: utf-8 -*-
"""RoadMap104 / T104-03 / 8C.4: Alligator deterioration sequence.

TEST_ONLY runner не змінює production Candidate F, GREEN 8C.1 entry або exit.
Він продовжує T104-02: після першого causal early-MACD-reversal event
спостерігає наступні 2 та 3 завершені M15 bars і порівнює, як змінюється
структура Alligator у baseline STOP_LOSS та TAKE_PROFIT групах.

Нових числових thresholds немає. Horizon 2/3 bars використовується паралельно
як diagnostic window, а не як підібраний параметр. Порівнюються тільки знаки
зміни opening, directional center slope, Lips/Jaw gap та structural breaks.
"""

from __future__ import annotations

import importlib.util
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BASE_SCRIPT_NAME = (
    "run_t104_02_algorithm_workspace_alligator_state_at_early_macd_"
    "reversal_2025_2026_check.py"
)
EPSILON = 1e-12
HORIZONS = (2, 3)


def _load_base_module() -> ModuleType:
    """Завантажити T104-02 як read-only diagnostic dependency."""
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm104_t104_03_alligator_state_base"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()
MOMENTUM_BASE = getattr(BASE, "BASE")
WINDOWS = getattr(BASE, "WINDOWS")
EVENT_HISTOGRAM_CONTRACTION = getattr(BASE, "EVENT_HISTOGRAM_CONTRACTION")
EVENT_MACD_SLOPE_REVERSAL = getattr(BASE, "EVENT_MACD_SLOPE_REVERSAL")
EVENTS = (
    EVENT_HISTOGRAM_CONTRACTION,
    EVENT_MACD_SLOPE_REVERSAL,
)
_load_indicator_run: Callable[..., Any] = getattr(BASE, "_load_indicator_run")
_confirmed_expansion_candidates: Callable[..., Any] = getattr(
    BASE,
    "_confirmed_expansion_candidates",
)
_simulate_trade: Callable[..., Any] = getattr(BASE, "_simulate_trade")
_simulate_event_exit: Callable[..., Any] = getattr(BASE, "_simulate_event_exit")
_snapshot: Callable[..., Any] = getattr(BASE, "_snapshot")
_protection_prices: Callable[..., Any] = getattr(MOMENTUM_BASE, "_protection_prices")
_protection_touched: Callable[..., Any] = getattr(
    MOMENTUM_BASE,
    "_protection_touched",
)


@dataclass(frozen=True, slots=True)
class SequenceObservation:
    """Causal зміна Alligator від MACD event до diagnostic horizon."""

    horizon: int
    opening_change: float
    directional_slope_change: float
    lips_jaw_change: float
    opening_lower: bool
    directional_slope_lower: bool
    lips_jaw_lower: bool
    all_three_lower: bool
    opening_down_streak: bool
    directional_slope_down_streak: bool
    lips_jaw_down_streak: bool
    all_three_down_streak: bool
    center_break_within: bool
    lips_jaw_break_within: bool
    full_order_break_within: bool
    regime_misaligned_within: bool


def _baseline_close_index(run: Any, candidate: Any) -> int:
    """Знайти causal baseline SL/TP close index без diagnostic exit."""
    _, stop_price, take_price = _protection_prices(run, candidate)
    for index in range(candidate.entry_index, len(run.events)):
        reason = _protection_touched(
            run.events[index],
            candidate.direction,
            stop_price,
            take_price,
        )
        if reason is not None:
            return index
    return len(run.events) - 1


def _strictly_lower(values: list[float]) -> bool:
    """True, якщо кожний наступний causal value нижчий за попередній."""
    return all(
        current < previous - EPSILON for previous, current in zip(values, values[1:])
    )


def _sequence_observation(
    run: Any,
    direction: str,
    event_index: int,
    horizon: int,
) -> SequenceObservation:
    assert horizon in HORIZONS
    snapshots = [
        _snapshot(run, direction, index)
        for index in range(event_index, event_index + horizon + 1)
    ]
    first = snapshots[0]
    last = snapshots[-1]

    openings = [row.normalized_opening for row in snapshots]
    slopes = [row.directional_normalized_center_slope for row in snapshots]
    lips_jaw = [row.directional_lips_jaw_gap for row in snapshots]

    opening_lower = last.normalized_opening < first.normalized_opening - EPSILON
    slope_lower = (
        last.directional_normalized_center_slope
        < first.directional_normalized_center_slope - EPSILON
    )
    lips_jaw_lower = (
        last.directional_lips_jaw_gap < first.directional_lips_jaw_gap - EPSILON
    )

    return SequenceObservation(
        horizon=horizon,
        opening_change=last.normalized_opening - first.normalized_opening,
        directional_slope_change=(
            last.directional_normalized_center_slope
            - first.directional_normalized_center_slope
        ),
        lips_jaw_change=(
            last.directional_lips_jaw_gap - first.directional_lips_jaw_gap
        ),
        opening_lower=opening_lower,
        directional_slope_lower=slope_lower,
        lips_jaw_lower=lips_jaw_lower,
        all_three_lower=opening_lower and slope_lower and lips_jaw_lower,
        opening_down_streak=_strictly_lower(openings),
        directional_slope_down_streak=_strictly_lower(slopes),
        lips_jaw_down_streak=_strictly_lower(lips_jaw),
        all_three_down_streak=(
            _strictly_lower(openings)
            and _strictly_lower(slopes)
            and _strictly_lower(lips_jaw)
        ),
        center_break_within=any(row.center_direction_broken for row in snapshots[1:]),
        lips_jaw_break_within=any(row.lips_jaw_broken for row in snapshots[1:]),
        full_order_break_within=any(not row.full_order_holds for row in snapshots[1:]),
        regime_misaligned_within=any(not row.regime_aligned for row in snapshots[1:]),
    )


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def _median_text(value: float | None, digits: int = 4) -> str:
    if value is None:
        return "NONE"
    return f"{value:+.{digits}f}"


def _summary(rows: list[SequenceObservation]) -> dict[str, Any]:
    return {
        "eligible": len(rows),
        "median_opening_change": _median([row.opening_change for row in rows]),
        "median_slope_change": _median([row.directional_slope_change for row in rows]),
        "median_lips_jaw_change": _median([row.lips_jaw_change for row in rows]),
        "opening_lower": sum(row.opening_lower for row in rows),
        "slope_lower": sum(row.directional_slope_lower for row in rows),
        "lips_jaw_lower": sum(row.lips_jaw_lower for row in rows),
        "all_three_lower": sum(row.all_three_lower for row in rows),
        "opening_down_streak": sum(row.opening_down_streak for row in rows),
        "slope_down_streak": sum(row.directional_slope_down_streak for row in rows),
        "lips_jaw_down_streak": sum(row.lips_jaw_down_streak for row in rows),
        "all_three_down_streak": sum(row.all_three_down_streak for row in rows),
        "center_break_within": sum(row.center_break_within for row in rows),
        "lips_jaw_break_within": sum(row.lips_jaw_break_within for row in rows),
        "full_order_break_within": sum(row.full_order_break_within for row in rows),
        "regime_misaligned_within": sum(row.regime_misaligned_within for row in rows),
    }


def _summary_text(data: dict[str, Any]) -> str:
    return (
        f"eligible:{data['eligible']},"
        f"median_opening_change:"
        f"{_median_text(data['median_opening_change'])},"
        f"median_dir_slope_change:"
        f"{_median_text(data['median_slope_change'], 6)},"
        f"median_lips_jaw_change:"
        f"{_median_text(data['median_lips_jaw_change'])},"
        f"opening_lower:{data['opening_lower']},"
        f"slope_lower:{data['slope_lower']},"
        f"lips_jaw_lower:{data['lips_jaw_lower']},"
        f"all_three_lower:{data['all_three_lower']},"
        f"opening_down_streak:{data['opening_down_streak']},"
        f"slope_down_streak:{data['slope_down_streak']},"
        f"lips_jaw_down_streak:{data['lips_jaw_down_streak']},"
        f"all_three_down_streak:{data['all_three_down_streak']},"
        f"center_break_within:{data['center_break_within']},"
        f"lips_jaw_break_within:{data['lips_jaw_break_within']},"
        f"full_order_break_within:{data['full_order_break_within']},"
        f"regime_misaligned_within:{data['regime_misaligned_within']}"
    )


def _event_sequence_groups(
    run: Any,
    candidates: tuple[Any, ...],
    baseline: tuple[Any, ...],
    event_type: str,
) -> dict[str, Any]:
    rows: dict[int, dict[str, list[SequenceObservation]]] = {
        horizon: {
            "STOP_LOSS": [],
            "TAKE_PROFIT": [],
            "OTHER": [],
        }
        for horizon in HORIZONS
    }
    events_by_outcome: Counter[str] = Counter()
    closed_before_horizon: dict[int, Counter[str]] = {
        horizon: Counter() for horizon in HORIZONS
    }

    for candidate, baseline_trade in zip(candidates, baseline):
        variant = _simulate_event_exit(run, candidate, event_type)
        if variant.event is None:
            continue
        outcome = str(baseline_trade.close_reason)
        group = outcome if outcome in {"STOP_LOSS", "TAKE_PROFIT"} else "OTHER"
        events_by_outcome[group] += 1
        event_index = variant.event.index
        close_index = _baseline_close_index(run, candidate)

        for horizon in HORIZONS:
            target_index = event_index + horizon
            if target_index >= close_index or target_index >= len(run.events):
                closed_before_horizon[horizon][group] += 1
                continue
            rows[horizon][group].append(
                _sequence_observation(
                    run,
                    candidate.direction,
                    event_index,
                    horizon,
                )
            )

    summaries = {
        horizon: {
            group: _summary(group_rows) for group, group_rows in horizon_rows.items()
        }
        for horizon, horizon_rows in rows.items()
    }
    return {
        "events_by_outcome": events_by_outcome,
        "closed_before_horizon": closed_before_horizon,
        "summaries": summaries,
    }


def _run_window(window: Any) -> dict[str, Any]:
    print(f"  running_period={window.label}", flush=True)
    run = _load_indicator_run(window)
    candidates, openings, invalidated, timed_out, aligned_at_start = (
        _confirmed_expansion_candidates(run)
    )
    baseline = tuple(
        _simulate_trade(run, candidate, macd_exit_enabled=False)
        for candidate in candidates
    )
    event_groups = {
        event_type: _event_sequence_groups(
            run,
            candidates,
            baseline,
            event_type,
        )
        for event_type in EVENTS
    }
    return {
        "candidates": candidates,
        "openings": openings,
        "invalidated": invalidated,
        "timed_out": timed_out,
        "aligned_at_start": aligned_at_start,
        "baseline": baseline,
        "event_groups": event_groups,
    }


def _counter_text(counter: Counter[str]) -> str:
    return (
        "|".join(
            f"{key}:{counter[key]}"
            for key in ("STOP_LOSS", "TAKE_PROFIT", "OTHER")
            if counter[key]
        )
        or "NONE"
    )


def main() -> None:
    results = [(window, _run_window(window)) for window in WINDOWS]

    print("T104-03 Alligator Deterioration Sequence after MACD Reversal result")
    print("  test_id=T104-03")
    print("  roadmap_block=8C.4")
    print(
        "  mode=RM104_T104_03_8C4_ALLIGATOR_DETERIORATION_SEQUENCE_"
        "AFTER_MACD_REVERSAL_TEST_ONLY"
    )
    print("  base_test_id=T104-02")
    print("  production_candidate_f_logic_changed=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  green_8c1_entry_frozen=True")
    print("  event_sources=HISTOGRAM_CONTRACTION|MACD_SLOPE_REVERSAL")
    print("  combined_reversal_omitted_as_current_duplicate_of_slope_reversal=True")
    print("  diagnostic_horizons_completed_m15_bars=2|3")
    print("  horizons_are_parallel_diagnostics_not_tuned_parameters=True")
    print("  new_numeric_tuning=False")
    print("  structural_comparisons_use_sign_only=True")
    print("  future_price_used_for_sequence_event=False")

    for window, result in results:
        candidates = result["candidates"]
        baseline = result["baseline"]
        assert len(candidates) == len(baseline)
        print(
            f"  {window.label}/ENTRY="
            f"openings:{result['openings']},confirmed:{len(candidates)},"
            f"invalidated:{result['invalidated']},timeout:{result['timed_out']},"
            f"aligned_at_start_not_used:{result['aligned_at_start']}"
        )
        for event_type in EVENTS:
            grouped = result["event_groups"][event_type]
            print(
                f"  {window.label}/{event_type}/EVENTS="
                f"{_counter_text(grouped['events_by_outcome'])}"
            )
            for horizon in HORIZONS:
                closed = grouped["closed_before_horizon"][horizon]
                print(
                    f"  {window.label}/{event_type}/H{horizon}/"
                    f"CLOSED_BEFORE_HORIZON={_counter_text(closed)}"
                )
                for group in ("STOP_LOSS", "TAKE_PROFIT", "OTHER"):
                    summary = grouped["summaries"][horizon][group]
                    if not summary["eligible"] and group == "OTHER":
                        continue
                    group_label = {
                        "STOP_LOSS": "SL",
                        "TAKE_PROFIT": "TP",
                        "OTHER": "OTHER",
                    }[group]
                    print(
                        f"  {window.label}/{event_type}/H{horizon}/"
                        f"BASELINE_{group_label}={_summary_text(summary)}"
                    )

    print("  performance_is_diagnostic_not_pass_criterion=True")
    print("  causal_completed_m15_only=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print(
        "T104_03_ALGORITHM_WORKSPACE_ALLIGATOR_DETERIORATION_SEQUENCE_"
        "AFTER_MACD_REVERSAL_CHECK=OK"
    )


if __name__ == "__main__":
    main()
