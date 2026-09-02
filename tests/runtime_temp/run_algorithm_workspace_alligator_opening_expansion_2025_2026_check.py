# -*- coding: utf-8 -*-
"""RoadMap103 / 8C.1: causal Alligator opening-expansion diagnostic.

TEST_ONLY runner не змінює production Candidate F. Він порівнює попередній
8C event ``FIRST_DIRECTIONAL_STARTING_BAR`` з раннішим causal event: перше
розширення пащі Alligator із канонічної стиснутої області. Стиснення бере
вже наявний поріг ``ALLIGATOR_REGIME_FLAT_MAX_NORMALIZED_OPENING``; нового
числового tuning немає. Напрямок раннього event задають Lips проти Jaw та
знак causal center slope. MACD 6/13/4 лишається тільки fresh-cross confirm
у 4-bar window. Entry — next M15 open, SL/TP — 12/24 pip.

Окремо повторюється paired opposite-MACD-cross exit, щоб перевірити його
cross-period robustness. Future bars не використовуються для opening або
confirmation; broker I/O та production logic не змінюються.
"""

from __future__ import annotations

import importlib.util
import statistics
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_FLAT_MAX_NORMALIZED_OPENING,
)

BASE_SCRIPT_NAME = (
    "run_algorithm_workspace_alligator_primary_macd_confirm_2025_2026_check.py"
)
MATCH_STARTING_MAX_LEAD_BARS = 8
EPSILON = 1e-12


def _load_base_module() -> ModuleType:
    """Завантажити GREEN 8C runner як read-only diagnostic dependency."""
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm103_8c_alligator_primary_macd_confirm_base"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()
WINDOWS = getattr(BASE, "WINDOWS")
CONFIRMATION_WINDOW_BARS = int(getattr(BASE, "CONFIRMATION_WINDOW_BARS"))
EXPECTED_M15_DELTA = getattr(BASE, "EXPECTED_M15_DELTA")
ConfirmedCandidate = getattr(BASE, "ConfirmedCandidate")
VariantSummary = getattr(BASE, "VariantSummary")
_load_indicator_run: Callable[..., Any] = getattr(BASE, "_load_indicator_run")
_is_starting_opening: Callable[..., bool] = getattr(BASE, "_is_opening")
_alligator_direction: Callable[..., str | None] = getattr(
    BASE,
    "_alligator_direction",
)
_fresh_cross: Callable[..., bool] = getattr(BASE, "_fresh_cross")
_macd_aligned: Callable[..., bool] = getattr(BASE, "_macd_aligned")
_confirmed_starting_candidates: Callable[..., Any] = getattr(
    BASE,
    "_confirmed_candidates",
)
_simulate_trade: Callable[..., Any] = getattr(BASE, "_simulate_trade")
_summary: Callable[..., Any] = getattr(BASE, "_summary")
_summary_text: Callable[..., str] = getattr(BASE, "_summary_text")


def _incipient_opening_direction(observation: Any) -> str | None:
    """Повернути ранній напрямок пащі без вимоги повного line ordering."""
    if not bool(observation.warmed_up):
        return None
    if (
        observation.lips is None
        or observation.jaw is None
        or observation.center_slope_per_bar is None
    ):
        return None
    if observation.lips > observation.jaw and observation.center_slope_per_bar > 0:
        return "BUY"
    if observation.lips < observation.jaw and observation.center_slope_per_bar < 0:
        return "SELL"
    return None


def _is_expansion_from_compressed(observations: tuple[Any, ...], index: int) -> bool:
    """Виявити перший causal expansion bar усередині/з compressed mouth."""
    if index < 1:
        return False
    current = observations[index]
    previous = observations[index - 1]
    if _incipient_opening_direction(current) is None:
        return False
    if current.normalized_opening is None or previous.normalized_opening is None:
        return False
    if previous.normalized_opening > ALLIGATOR_REGIME_FLAT_MAX_NORMALIZED_OPENING:
        return False
    if current.normalized_opening <= previous.normalized_opening + EPSILON:
        return False

    if index < 2:
        return True
    older = observations[index - 2]
    if older.normalized_opening is None:
        return True
    previous_was_expanding_while_compressed = bool(
        older.normalized_opening <= ALLIGATOR_REGIME_FLAT_MAX_NORMALIZED_OPENING
        and previous.normalized_opening > older.normalized_opening + EPSILON
    )
    return not previous_was_expanding_while_compressed


def _expansion_candidate_still_valid(observation: Any, direction: str) -> bool:
    """Валідність раннього candidate: lips/jaw та center slope не змінили знак."""
    return _incipient_opening_direction(observation) == direction


def _confirmed_expansion_candidates(
    run: Any,
) -> tuple[tuple[Any, ...], int, int, int, int]:
    """Підтвердити opening-expansion тільки fresh MACD cross після event."""
    confirmed: list[Any] = []
    opening_count = 0
    invalidated = 0
    timed_out = 0
    aligned_at_start = 0

    for start_index in range(len(run.events)):
        if not _is_expansion_from_compressed(run.alligator, start_index):
            continue
        opening_count += 1
        direction = _incipient_opening_direction(run.alligator[start_index])
        assert direction is not None
        if _macd_aligned(run.macd[start_index], direction):
            aligned_at_start += 1

        found_index: int | None = None
        candidate_invalidated = False
        maximum_index = min(
            start_index + CONFIRMATION_WINDOW_BARS - 1,
            len(run.events) - 2,
        )
        for index in range(start_index, maximum_index + 1):
            if not _expansion_candidate_still_valid(run.alligator[index], direction):
                candidate_invalidated = True
                break
            if _fresh_cross(run.macd[index], direction):
                found_index = index
                break

        if found_index is None:
            if candidate_invalidated:
                invalidated += 1
            else:
                timed_out += 1
            continue

        entry_index = found_index + 1
        if entry_index >= len(run.events):
            timed_out += 1
            continue
        if run.events[entry_index].timestamp - run.events[found_index].timestamp != (
            EXPECTED_M15_DELTA
        ):
            timed_out += 1
            continue

        confirmed.append(
            ConfirmedCandidate(
                direction=direction,
                start_index=start_index,
                confirm_index=found_index,
                entry_index=entry_index,
                start_timestamp=run.completed_at[start_index],
                confirm_timestamp=run.completed_at[found_index],
                entry_timestamp=run.events[entry_index].timestamp,
                delay_bars=found_index - start_index,
                confirmation_is_fresh_cross=True,
                macd_was_aligned_before_start=bool(
                    start_index > 0
                    and _macd_aligned(run.macd[start_index - 1], direction)
                ),
            )
        )

    return (
        tuple(confirmed),
        opening_count,
        invalidated,
        timed_out,
        aligned_at_start,
    )


def _opening_events(
    run: Any,
    predicate: Callable[[tuple[Any, ...], int], bool],
    direction_resolver: Callable[[Any], str | None],
) -> tuple[tuple[int, str], ...]:
    rows: list[tuple[int, str]] = []
    for index in range(len(run.events)):
        if not predicate(run.alligator, index):
            continue
        direction = direction_resolver(run.alligator[index])
        if direction is not None:
            rows.append((index, direction))
    return tuple(rows)


def _lead_to_next_starting(run: Any) -> tuple[int, float | None, Counter[int]]:
    """Виміряти, на скільки bars ранній expansion випереджає STARTING."""
    expansion = _opening_events(
        run,
        _is_expansion_from_compressed,
        _incipient_opening_direction,
    )
    starting = _opening_events(
        run,
        _is_starting_opening,
        _alligator_direction,
    )
    leads: list[int] = []
    for expansion_index, direction in expansion:
        for starting_index, starting_direction in starting:
            if starting_index < expansion_index:
                continue
            lead = starting_index - expansion_index
            if lead > MATCH_STARTING_MAX_LEAD_BARS:
                break
            if starting_direction == direction:
                leads.append(lead)
                break
    median_lead = statistics.median(leads) if leads else None
    return len(leads), median_lead, Counter(leads)


def _variant_pair(run: Any, candidates: tuple[Any, ...]) -> dict[str, Any]:
    sltp = tuple(
        _simulate_trade(run, item, macd_exit_enabled=False) for item in candidates
    )
    macd_exit = tuple(
        _simulate_trade(run, item, macd_exit_enabled=True) for item in candidates
    )
    improved = sum(
        right.pnl > left.pnl + EPSILON for left, right in zip(sltp, macd_exit)
    )
    worsened = sum(
        right.pnl < left.pnl - EPSILON for left, right in zip(sltp, macd_exit)
    )
    return {
        "sltp": _summary(sltp),
        "macd_exit": _summary(macd_exit),
        "improved": improved,
        "worsened": worsened,
        "unchanged": len(candidates) - improved - worsened,
    }


def _run_window(window: Any) -> dict[str, Any]:
    print(f"  running_period={window.label}", flush=True)
    run = _load_indicator_run(window)

    (
        starting_candidates,
        starting_openings,
        starting_invalidated,
        starting_timed_out,
    ) = _confirmed_starting_candidates(run)
    (
        expansion_candidates,
        expansion_openings,
        expansion_invalidated,
        expansion_timed_out,
        expansion_aligned_at_start,
    ) = _confirmed_expansion_candidates(run)

    assert starting_openings > 0
    assert expansion_openings > 0
    assert starting_candidates
    assert expansion_candidates
    assert all(
        0 <= item.delay_bars < CONFIRMATION_WINDOW_BARS for item in expansion_candidates
    )
    assert all(
        item.start_timestamp <= item.confirm_timestamp == item.entry_timestamp
        for item in expansion_candidates
    )
    assert all(item.confirmation_is_fresh_cross for item in expansion_candidates)

    matched, median_lead, lead_counts = _lead_to_next_starting(run)
    return {
        "run": run,
        "starting_candidates": starting_candidates,
        "starting_openings": starting_openings,
        "starting_invalidated": starting_invalidated,
        "starting_timed_out": starting_timed_out,
        "starting_pair": _variant_pair(run, starting_candidates),
        "expansion_candidates": expansion_candidates,
        "expansion_openings": expansion_openings,
        "expansion_invalidated": expansion_invalidated,
        "expansion_timed_out": expansion_timed_out,
        "expansion_aligned_at_start": expansion_aligned_at_start,
        "expansion_pair": _variant_pair(run, expansion_candidates),
        "matched_starting": matched,
        "median_lead": median_lead,
        "lead_counts": lead_counts,
    }


def _net(summary: Any) -> float:
    return float(summary.net)


def _format_median(value: float | None) -> str:
    if value is None:
        return "NONE"
    return f"{value:.1f}"


def main() -> None:
    results = [(window, _run_window(window)) for window in WINDOWS]

    print("Algorithm Workspace Alligator Opening Expansion result")
    print("  mode=RM103_8C1_ALLIGATOR_OPENING_EXPANSION_TEST_ONLY")
    print("  production_candidate_f_logic_changed=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  repeated_8c_indicator_pipeline=True")
    print("  alligator_profile=VIEW_ZALLIGATOR_21_13_8_TEST_ONLY")
    print("  alligator_view_parameters=8/3_13/5_21/8_hl2")
    print("  opening_event=FIRST_EXPANSION_FROM_CANONICAL_COMPRESSED_MOUTH")
    print(
        "  compressed_opening_threshold="
        f"{ALLIGATOR_REGIME_FLAT_MAX_NORMALIZED_OPENING:.3f}"
    )
    print("  threshold_source=EXISTING_ALLIGATOR_FLAT_OPENING_THRESHOLD")
    print("  new_numeric_tuning=False")
    print("  early_direction=LIPS_VS_JAW_AND_CENTER_SLOPE_SIGN")
    print("  full_line_order_required_at_opening=False")
    print("  macd_profile=6/13/4_EMA_EMA_CLOSE")
    print("  macd_confirm=FRESH_SAME_DIRECTION_CROSS_WITHIN_4_BARS")
    print("  prealigned_macd_is_confirmation=False")
    print("  entry_policy=NEXT_M15_OPEN_AFTER_CONFIRM")
    print("  stop_loss_pips=12.0")
    print("  take_profit_pips=24.0")
    print("  future_price_used_for_opening_or_confirmation=False")

    expansion_positive = []
    macd_exit_not_worse = []
    for window, result in results:
        run = result["run"]
        starting_candidates = result["starting_candidates"]
        expansion_candidates = result["expansion_candidates"]
        starting_pair = result["starting_pair"]
        expansion_pair = result["expansion_pair"]
        starting_sltp = starting_pair["sltp"]
        expansion_sltp = expansion_pair["sltp"]
        expansion_macd_exit = expansion_pair["macd_exit"]
        assert isinstance(starting_sltp, VariantSummary)
        assert isinstance(expansion_sltp, VariantSummary)
        assert isinstance(expansion_macd_exit, VariantSummary)

        expansion_positive.append(_net(expansion_sltp) > 0.0)
        macd_exit_not_worse.append(_net(expansion_macd_exit) >= _net(expansion_sltp))
        lead_counts = result["lead_counts"]
        assert isinstance(lead_counts, Counter)
        print(
            f"  {window.label}/DATA="
            f"m1:{run.accepted_m1_rows},m15:{run.completed_m15_bars},"
            f"dropped_incomplete:{run.dropped_incomplete_buckets}"
        )
        print(
            f"  {window.label}/STARTING_REFERENCE="
            f"openings:{result['starting_openings']},"
            f"confirmed:{len(starting_candidates)},"
            f"invalidated:{result['starting_invalidated']},"
            f"timeout:{result['starting_timed_out']};"
            f"sltp:{_summary_text(starting_sltp)}"
        )
        print(
            f"  {window.label}/EXPANSION="
            f"openings:{result['expansion_openings']},"
            f"confirmed:{len(expansion_candidates)},"
            f"invalidated:{result['expansion_invalidated']},"
            f"timeout:{result['expansion_timed_out']},"
            f"aligned_at_start_not_used:{result['expansion_aligned_at_start']}"
        )
        print(
            f"  {window.label}/EXPANSION_LEAD_TO_STARTING="
            f"matched_within_{MATCH_STARTING_MAX_LEAD_BARS}bars:"
            f"{result['matched_starting']},"
            f"median_lead_bars:{_format_median(result['median_lead'])},"
            f"b0:{lead_counts[0]},b1:{lead_counts[1]},b2:{lead_counts[2]},"
            f"b3:{lead_counts[3]},b4:{lead_counts[4]}"
        )
        print(
            f"  {window.label}/EXPANSION_SLTP_ONLY=" f"{_summary_text(expansion_sltp)}"
        )
        print(
            f"  {window.label}/EXPANSION_MACD_EXIT="
            f"{_summary_text(expansion_macd_exit)}"
        )
        print(
            f"  {window.label}/EXPANSION_MACD_EXIT_PAIRED="
            f"improved:{expansion_pair['improved']},"
            f"worsened:{expansion_pair['worsened']},"
            f"unchanged:{expansion_pair['unchanged']}"
        )

    print("  expansion_sltp_net_positive_both_periods=" f"{all(expansion_positive)}")
    print(
        "  opposite_macd_cross_exit_not_worse_both_periods="
        f"{all(macd_exit_not_worse)}"
    )
    print("  performance_is_diagnostic_not_pass_criterion=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_ALLIGATOR_OPENING_EXPANSION_CHECK=OK")


if __name__ == "__main__":
    main()
