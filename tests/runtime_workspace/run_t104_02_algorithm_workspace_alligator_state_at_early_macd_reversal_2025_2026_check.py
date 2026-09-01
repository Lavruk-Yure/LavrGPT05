# -*- coding: utf-8 -*-
"""RoadMap104 / T104-02 / 8C.3: Alligator state at early MACD reversal.

TEST_ONLY runner не змінює production Candidate F, GREEN 8C.1 entry або exit.
Він повторно використовує T104-01 і дивиться стан Alligator саме на першому
causal early-MACD-reversal event, який виник до SL/TP.

Мета — відрізнити звичайний pullback усередині живого тренду від структурного
завершення руху. Нових числових thresholds немає: порівнюються безпосередні
causal величини Alligator, їх знак/дельта, порядок Lips/Teeth/Jaw та вже
наявні regime/phase diagnostics. Окремо групуються baseline STOP_LOSS і
TAKE_PROFIT, щоб не підбирати exit за aggregate PnL.
"""

from __future__ import annotations

import importlib.util
import math
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
    "run_algorithm_workspace_alligator_opening_exit_momentum_reversal_"
    "anatomy_2025_2026_check.py"
)
EPSILON = 1e-12


def _load_base_module() -> ModuleType:
    """Завантажити T104-01 як read-only diagnostic dependency."""
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm104_t104_02_momentum_reversal_base"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()
WINDOWS = getattr(BASE, "WINDOWS")
EVENT_HISTOGRAM_CONTRACTION = getattr(BASE, "EVENT_HISTOGRAM_CONTRACTION")
EVENT_MACD_SLOPE_REVERSAL = getattr(BASE, "EVENT_MACD_SLOPE_REVERSAL")
EVENT_COMBINED_REVERSAL = getattr(BASE, "EVENT_COMBINED_REVERSAL")
EVENTS = getattr(BASE, "EVENTS")
_load_indicator_run: Callable[..., Any] = getattr(BASE, "_load_indicator_run")
_confirmed_expansion_candidates: Callable[..., Any] = getattr(
    BASE,
    "_confirmed_expansion_candidates",
)
_simulate_trade: Callable[..., Any] = getattr(BASE, "_simulate_trade")
_simulate_event_exit: Callable[..., Any] = getattr(BASE, "_simulate_event_exit")


@dataclass(frozen=True, slots=True)
class AlligatorEventSnapshot:
    """Causal Alligator snapshot у момент early MACD reversal."""

    normalized_opening: float
    normalized_opening_delta: float
    directional_normalized_center_slope: float
    directional_normalized_center_slope_delta: float
    directional_lips_jaw_gap: float
    directional_lips_teeth_gap: float
    directional_teeth_jaw_gap: float
    mouth_contracting: bool
    center_direction_broken: bool
    lips_jaw_broken: bool
    full_order_holds: bool
    regime_aligned: bool
    regime: str
    phase: str


def _required_float(value: Any, name: str) -> float:
    assert value is not None, name
    number = float(value)
    assert math.isfinite(number), name
    return number


def _direction_sign(direction: str) -> float:
    assert direction in {"BUY", "SELL"}
    return 1.0 if direction == "BUY" else -1.0


def _regime_aligned(regime: str, direction: str) -> bool:
    if direction == "BUY":
        return regime == "ALLIGATOR_REGIME_TREND_UP"
    assert direction == "SELL"
    return regime == "ALLIGATOR_REGIME_TREND_DOWN"


def _snapshot(run: Any, direction: str, index: int) -> AlligatorEventSnapshot:
    """Побудувати threshold-free Alligator snapshot на completed M15 bar."""
    assert index >= 1
    current = run.alligator[index]
    previous = run.alligator[index - 1]
    assert bool(current.warmed_up)

    range_reference = _required_float(current.range_reference, "range_reference")
    assert range_reference > 0.0
    previous_range_reference = _required_float(
        previous.range_reference,
        "previous_range_reference",
    )
    assert previous_range_reference > 0.0

    normalized_opening = _required_float(
        current.normalized_opening,
        "normalized_opening",
    )
    previous_normalized_opening = _required_float(
        previous.normalized_opening,
        "previous_normalized_opening",
    )
    sign = _direction_sign(direction)

    center_slope = _required_float(
        current.center_slope_per_bar,
        "center_slope_per_bar",
    )
    previous_center_slope = _required_float(
        previous.center_slope_per_bar,
        "previous_center_slope_per_bar",
    )
    directional_center_slope = sign * center_slope / range_reference
    previous_directional_center_slope = (
        sign * previous_center_slope / previous_range_reference
    )

    lips = _required_float(current.lips, "lips")
    teeth = _required_float(current.teeth, "teeth")
    jaw = _required_float(current.jaw, "jaw")
    lips_jaw = sign * (lips - jaw) / range_reference
    lips_teeth = sign * (lips - teeth) / range_reference
    teeth_jaw = sign * (teeth - jaw) / range_reference
    full_order_holds = lips_teeth > EPSILON and teeth_jaw > EPSILON

    return AlligatorEventSnapshot(
        normalized_opening=normalized_opening,
        normalized_opening_delta=(normalized_opening - previous_normalized_opening),
        directional_normalized_center_slope=directional_center_slope,
        directional_normalized_center_slope_delta=(
            directional_center_slope - previous_directional_center_slope
        ),
        directional_lips_jaw_gap=lips_jaw,
        directional_lips_teeth_gap=lips_teeth,
        directional_teeth_jaw_gap=teeth_jaw,
        mouth_contracting=(normalized_opening < previous_normalized_opening - EPSILON),
        center_direction_broken=directional_center_slope <= EPSILON,
        lips_jaw_broken=lips_jaw <= EPSILON,
        full_order_holds=full_order_holds,
        regime_aligned=_regime_aligned(str(current.regime), direction),
        regime=str(current.regime),
        phase=str(current.regime_phase),
    )


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def _median_text(value: float | None, digits: int = 4) -> str:
    if value is None:
        return "NONE"
    return f"{value:+.{digits}f}"


def _counts_text(counter: Counter[str]) -> str:
    if not counter:
        return "NONE"
    return "|".join(f"{key}:{counter[key]}" for key in sorted(counter))


def _group_summary(rows: list[AlligatorEventSnapshot]) -> dict[str, Any]:
    return {
        "events": len(rows),
        "median_opening": _median([row.normalized_opening for row in rows]),
        "median_opening_delta": _median([row.normalized_opening_delta for row in rows]),
        "median_directional_slope": _median(
            [row.directional_normalized_center_slope for row in rows]
        ),
        "median_directional_slope_delta": _median(
            [row.directional_normalized_center_slope_delta for row in rows]
        ),
        "median_lips_jaw": _median([row.directional_lips_jaw_gap for row in rows]),
        "mouth_contracting": sum(row.mouth_contracting for row in rows),
        "center_direction_broken": sum(row.center_direction_broken for row in rows),
        "lips_jaw_broken": sum(row.lips_jaw_broken for row in rows),
        "full_order_holds": sum(row.full_order_holds for row in rows),
        "regime_aligned": sum(row.regime_aligned for row in rows),
        "regimes": Counter(row.regime for row in rows),
        "phases": Counter(row.phase for row in rows),
    }


def _group_text(data: dict[str, Any]) -> str:
    return (
        f"events:{data['events']},"
        f"median_opening:{_median_text(data['median_opening'])},"
        f"median_opening_delta:{_median_text(data['median_opening_delta'])},"
        f"median_dir_slope:{_median_text(data['median_directional_slope'], 6)},"
        f"median_dir_slope_delta:"
        f"{_median_text(data['median_directional_slope_delta'], 6)},"
        f"median_lips_jaw:{_median_text(data['median_lips_jaw'], 4)},"
        f"mouth_contracting:{data['mouth_contracting']},"
        f"center_direction_broken:{data['center_direction_broken']},"
        f"lips_jaw_broken:{data['lips_jaw_broken']},"
        f"full_order_holds:{data['full_order_holds']},"
        f"regime_aligned:{data['regime_aligned']},"
        f"regimes:{_counts_text(data['regimes'])},"
        f"phases:{_counts_text(data['phases'])}"
    )


def _event_outcome_groups(
    run: Any,
    candidates: tuple[Any, ...],
    baseline: tuple[Any, ...],
    event_type: str,
) -> dict[str, Any]:
    groups: dict[str, list[AlligatorEventSnapshot]] = {
        "STOP_LOSS": [],
        "TAKE_PROFIT": [],
        "OTHER": [],
    }
    event_count = 0
    for candidate, baseline_trade in zip(candidates, baseline):
        variant = _simulate_event_exit(run, candidate, event_type)
        if variant.event is None:
            continue
        event_count += 1
        outcome = str(baseline_trade.close_reason)
        group_key = outcome if outcome in {"STOP_LOSS", "TAKE_PROFIT"} else "OTHER"
        groups[group_key].append(
            _snapshot(run, candidate.direction, variant.event.index)
        )

    return {
        "event_count": event_count,
        "STOP_LOSS": _group_summary(groups["STOP_LOSS"]),
        "TAKE_PROFIT": _group_summary(groups["TAKE_PROFIT"]),
        "OTHER": _group_summary(groups["OTHER"]),
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
        event_type: _event_outcome_groups(
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


def main() -> None:
    results = [(window, _run_window(window)) for window in WINDOWS]

    print("T104-02 Alligator State at Early MACD Reversal result")
    print("  test_id=T104-02")
    print("  roadmap_block=8C.3")
    print("  mode=RM104_T104_02_8C3_ALLIGATOR_STATE_AT_EARLY_MACD_REVERSAL_TEST_ONLY")
    print("  base_test_id=T104-01")
    print("  production_candidate_f_logic_changed=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  green_8c1_entry_frozen=True")
    print("  event_source=FIRST_CAUSAL_EARLY_MACD_REVERSAL_BEFORE_SLTP")
    print("  outcome_groups=BASELINE_STOP_LOSS_VS_TAKE_PROFIT")
    print("  alligator_metrics=OPENING_DELTA_CENTER_SLOPE_LINE_ORDER_REGIME_PHASE")
    print("  normalized_line_gaps_use_current_causal_range_reference=True")
    print("  new_numeric_tuning=False")
    print("  zero_sign_tests_are_structural_not_tuned_thresholds=True")
    print("  future_price_used_for_alligator_snapshot=False")

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
            sl = grouped["STOP_LOSS"]
            tp = grouped["TAKE_PROFIT"]
            other = grouped["OTHER"]
            assert grouped["event_count"] == (
                sl["events"] + tp["events"] + other["events"]
            )
            print(f"  {window.label}/{event_type}/BASELINE_SL=" f"{_group_text(sl)}")
            print(f"  {window.label}/{event_type}/BASELINE_TP=" f"{_group_text(tp)}")
            if other["events"]:
                print(
                    f"  {window.label}/{event_type}/BASELINE_OTHER="
                    f"{_group_text(other)}"
                )

    print("  performance_is_diagnostic_not_pass_criterion=True")
    print("  causal_completed_m15_only=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T104_02_ALGORITHM_WORKSPACE_ALLIGATOR_STATE_AT_EARLY_MACD_REVERSAL_CHECK=OK")


if __name__ == "__main__":
    main()
