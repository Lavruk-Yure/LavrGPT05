# -*- coding: utf-8 -*-
"""RoadMap104 / T104-14 / 8C.15: Alligator forward displacement audit.

TEST_ONLY runner перевіряє, чи forward-tail Bill Williams Alligator справді
можна відтворити causal у LGE. Для профілю Zalligator 21/8, 13/5, 8/3
найменший shift дорівнює 3, тому після завершення поточного M15 bar уже
відомі графічні H0..H3 значення всіх трьох ліній.

Projection не є прогнозом ціни та не створює future timestamp. Вона лише
зменшує залишковий display shift для вже обчислених raw SMMA values. Аудит
послідовно будує projection до надходження майбутніх bars, а потім лише для
валідації порівнює її з тим, що фактично буде намальовано на H1..H3.

Додатково diagnostic-only вимірюється, скільки GREEN 8C.1 opening-expansion
подій можна побачити на один bar раніше через H1. Це не permission rule і не
performance PASS criterion.
"""

from __future__ import annotations

import importlib.util
import statistics
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_FLAT_MAX_NORMALIZED_OPENING,
    WorkspaceAlligatorCausalProjection,
    WorkspaceAlligatorFilter,
)
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
)

BASE_SCRIPT_NAME = (
    "run_algorithm_workspace_alligator_opening_expansion_2025_2026_check.py"
)
TEST_ID = "T104-14"
ROADMAP_BLOCK = "8C.15"
EPSILON = 1e-12


def _load_base_module() -> ModuleType:
    """Завантажити GREEN 8C.1 як read-only diagnostic dependency."""
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm104_t104_14_projection_base"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()
PRIMARY = getattr(BASE, "BASE")
WINDOWS = getattr(BASE, "WINDOWS")
_load_indicator_run: Callable[..., Any] = getattr(BASE, "_load_indicator_run")
_is_expansion_from_compressed: Callable[..., bool] = getattr(
    BASE,
    "_is_expansion_from_compressed",
)
_incipient_opening_direction: Callable[..., str | None] = getattr(
    BASE,
    "_incipient_opening_direction",
)
_alligator_runtime_profile: Callable[..., Any] = getattr(
    PRIMARY,
    "_alligator_runtime_profile",
)


def _projection_direction(
    projection: WorkspaceAlligatorCausalProjection,
) -> str | None:
    slope = projection.center_slope_per_bar
    if slope is None:
        return None
    if projection.lips > projection.jaw and slope > 0.0:
        return "BUY"
    if projection.lips < projection.jaw and slope < 0.0:
        return "SELL"
    return None


def _projected_h1_opening(
    projections: tuple[WorkspaceAlligatorCausalProjection, ...],
    previous_observation: Any,
) -> str | None:
    """Diagnostic first-expansion predicate на один graphical bar вперед."""
    if len(projections) < 2:
        return None
    current = projections[0]
    forward = projections[1]
    if (
        current.normalized_opening is None
        or forward.normalized_opening is None
        or current.range_reference is None
        or current.range_reference <= 0.0
        or previous_observation.opening is None
    ):
        return None
    if current.normalized_opening > ALLIGATOR_REGIME_FLAT_MAX_NORMALIZED_OPENING:
        return None
    if forward.normalized_opening <= current.normalized_opening + EPSILON:
        return None

    previous_normalized = float(previous_observation.opening) / current.range_reference
    current_was_already_expanding = bool(
        previous_normalized <= ALLIGATOR_REGIME_FLAT_MAX_NORMALIZED_OPENING
        and current.normalized_opening > previous_normalized + EPSILON
    )
    if current_was_already_expanding:
        return None
    return _projection_direction(forward)


def _run_window(window: Any) -> dict[str, Any]:
    print(f"  running_period={window.label}", flush=True)
    run = _load_indicator_run(window)
    signal_filter = WorkspaceAlligatorFilter(
        enabled=True,
        confirmation_mode=WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
        runtime_profile=_alligator_runtime_profile(),
        timeframe="M15",
    )

    projection_history: list[tuple[WorkspaceAlligatorCausalProjection, ...]] = []
    maximum_horizon = 0
    h0_exact = True
    causal_available_now = True

    for event, available_at, reference_observation in zip(
        run.events,
        run.completed_at,
        run.alligator,
    ):
        observation = signal_filter.on_market_event(
            event,
            available_at=available_at,
        )
        assert observation == reference_observation
        projections = signal_filter.causal_forward_projections()
        projection_history.append(projections)
        maximum_horizon = max(
            maximum_horizon,
            signal_filter.maximum_causal_projection_bars,
        )
        if not projections:
            continue
        h0 = projections[0]
        normalized_opening_equal = bool(
            h0.normalized_opening is None and observation.normalized_opening is None
        ) or bool(
            h0.normalized_opening is not None
            and observation.normalized_opening is not None
            and abs(h0.normalized_opening - observation.normalized_opening) <= EPSILON
        )
        h0_exact = h0_exact and bool(
            abs(h0.jaw - float(observation.jaw)) <= EPSILON
            and abs(h0.teeth - float(observation.teeth)) <= EPSILON
            and abs(h0.lips - float(observation.lips)) <= EPSILON
            and abs(h0.center - float(observation.center)) <= EPSILON
            and abs(h0.opening - float(observation.opening)) <= EPSILON
            and normalized_opening_equal
        )
        causal_available_now = causal_available_now and all(
            item.source_timestamp == observation.timestamp
            and item.available_at == observation.available_at
            and 0 <= item.horizon_bars <= maximum_horizon
            for item in projections
        )

    compared_triplets = 0
    maximum_line_difference = 0.0
    forward_exact = True
    for index, projections in enumerate(projection_history):
        for projection in projections:
            horizon = projection.horizon_bars
            if horizon == 0 or index + horizon >= len(run.alligator):
                continue
            future = run.alligator[index + horizon]
            if future.jaw is None or future.teeth is None or future.lips is None:
                continue
            differences = (
                abs(projection.jaw - future.jaw),
                abs(projection.teeth - future.teeth),
                abs(projection.lips - future.lips),
            )
            maximum_line_difference = max(maximum_line_difference, *differences)
            forward_exact = forward_exact and all(
                value <= EPSILON for value in differences
            )
            compared_triplets += 1

    actual_openings = {
        (index, _incipient_opening_direction(run.alligator[index]))
        for index in range(len(run.alligator))
        if _is_expansion_from_compressed(run.alligator, index)
    }
    projected_candidates: list[tuple[int, str]] = []
    for index in range(1, len(projection_history) - 1):
        direction = _projected_h1_opening(
            projection_history[index],
            run.alligator[index - 1],
        )
        if direction is not None:
            projected_candidates.append((index, direction))

    matched = sum(
        (index + 1, direction) in actual_openings
        for index, direction in projected_candidates
    )
    matched_actual = sum(
        (index - 1, direction) in set(projected_candidates)
        for index, direction in actual_openings
        if direction is not None and index > 0
    )
    precision = matched / len(projected_candidates) if projected_candidates else 0.0
    coverage = matched_actual / len(actual_openings) if actual_openings else 0.0
    lead_bars = [1 for _ in range(matched)]

    return {
        "run": run,
        "maximum_horizon": maximum_horizon,
        "h0_exact": h0_exact,
        "causal_available_now": causal_available_now,
        "compared_triplets": compared_triplets,
        "maximum_line_difference": maximum_line_difference,
        "forward_exact": forward_exact,
        "actual_openings": len(actual_openings),
        "projected_candidates": len(projected_candidates),
        "matched": matched,
        "precision": precision,
        "coverage": coverage,
        "median_lead": statistics.median(lead_bars) if lead_bars else None,
    }


def main() -> None:
    results = [(window, _run_window(window)) for window in WINDOWS]

    print("T104-14 Alligator Forward Displacement Projection Audit result")
    print(f"  test_id={TEST_ID}")
    print(f"  roadmap_block={ROADMAP_BLOCK}")
    print(
        "  mode=RM104_T104_14_8C15_ALLIGATOR_FORWARD_DISPLACEMENT_"
        "PROJECTION_AUDIT_TEST_ONLY"
    )
    print("  production_candidate_f_logic_changed=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  green_8c1_entry_logic_changed=False")
    print("  lge_runtime_projection_api_added=True")
    print("  projection_semantics=KNOWN_DISPLAY_SHIFT_GEOMETRY_NOT_PRICE_FORECAST")
    print("  profile=VIEW_ZALLIGATOR_21_13_8_TEST_ONLY")
    print("  shifts=JAW_8|TEETH_5|LIPS_3")
    print("  expected_maximum_causal_projection_bars=3")
    print("  projected_timestamp_invented=False")
    print("  future_market_data_used_for_projection=False")
    print("  new_numeric_tuning=False")

    all_exact = True
    all_causal = True
    maximum_is_three = True
    any_early_match = False
    for window, result in results:
        all_exact = all_exact and result["h0_exact"] and result["forward_exact"]
        all_causal = all_causal and result["causal_available_now"]
        maximum_is_three = maximum_is_three and result["maximum_horizon"] == 3
        any_early_match = any_early_match or result["matched"] > 0
        median_text = (
            "NONE" if result["median_lead"] is None else f"{result['median_lead']:.1f}"
        )
        print(
            f"  {window.label}/PROJECTION="
            f"max_horizon:{result['maximum_horizon']},"
            f"h0_exact:{result['h0_exact']},"
            f"future_triplets_compared:{result['compared_triplets']},"
            f"max_line_difference:{result['maximum_line_difference']:.12f},"
            f"forward_exact:{result['forward_exact']},"
            f"causal_available_now:{result['causal_available_now']}"
        )
        print(
            f"  {window.label}/H1_OPENING_DIAGNOSTIC="
            f"actual_8c1_openings:{result['actual_openings']},"
            f"projected_candidates:{result['projected_candidates']},"
            f"matched_next_bar:{result['matched']},"
            f"precision:{result['precision']:.4f},"
            f"actual_coverage:{result['coverage']:.4f},"
            f"median_lead_bars:{median_text}"
        )

    assert maximum_is_three
    assert all_exact
    assert all_causal
    assert any_early_match

    print(f"  maximum_causal_projection_is_three_bars={maximum_is_three}")
    print(f"  projected_lines_equal_later_display_values={all_exact}")
    print(f"  projection_is_available_without_future_market_data={all_causal}")
    print(f"  projected_h1_can_precede_green_8c1_opening={any_early_match}")
    print("  projected_h1_is_diagnostic_not_entry_permission=True")
    print("  performance_is_diagnostic_not_pass_criterion=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T104_14_ALGORITHM_WORKSPACE_ALLIGATOR_FORWARD_PROJECTION_AUDIT_CHECK=OK")


if __name__ == "__main__":
    main()
