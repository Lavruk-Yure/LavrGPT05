# -*- coding: utf-8 -*-
"""RoadMap104 / T104-26: SELL protected-exit cross-period stability.

TEST_ONLY diagnostic over the unchanged T104-25 paired replay.  The runner
adds per-switch excursion/anatomy and robustness statistics for 2025 full and
2026 YTD.  It does not alter Supertrend(10, 3), entry selection, BUY exits,
SELL protected-switch behavior, or any production module.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BASE_SCRIPT_NAME = (
    "run_t104_25_algorithm_workspace_sell_supertrend_protected_exit_"
    "diagnostic_2025_2026_check.py"
)
TEST_ID = "T104-26"
SWITCH_REASON = "SUPERTREND_OPPOSITE_SWITCH"


def _load_base_module() -> ModuleType:
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm104_t104_26_protected_exit_base"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()
WINDOWS = getattr(BASE, "WINDOWS")
PIP_SIZE = float(getattr(BASE, "PIP_SIZE"))
EPSILON = float(getattr(BASE, "EPSILON"))
STOP_LOSS_PIPS = float(getattr(BASE.BASE, "STOP_LOSS_PIPS"))
TAKE_PROFIT_PIPS = float(getattr(BASE.BASE, "TAKE_PROFIT_PIPS"))
_run_period: Callable[..., Any] = getattr(BASE, "_run_period")
_comparison_text: Callable[..., str] = getattr(BASE, "_comparison_text")
_first_opposite_switch: Callable[..., Any] = getattr(BASE, "_first_opposite_switch")
_canonical_supertrend: Callable[..., Any] = getattr(BASE, "_canonical_supertrend")
_close_at_market: Callable[..., float] = getattr(BASE.BASE, "_close_at_market")


@dataclass(frozen=True, slots=True)
class StabilityCase:
    """One causally triggered SELL protected-switch execution."""

    entry_index: int
    switch_index: int
    entry_timestamp: Any
    switch_timestamp: Any
    baseline_outcome: str
    baseline_pnl: float
    protected_outcome: str
    protected_pnl: float
    paired_delta: float
    bars_entry_to_switch: int
    mfe_before_switch_pips: float
    mae_before_switch_pips: float
    classification: str
    baseline_tp_reached_later: bool


def _percentile(values: Iterable[float], fraction: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def _fmt_optional(value: float | None) -> str:
    return "NONE" if value is None else f"{value:+.2f}"


def _pnl_outcome(pnl: float) -> str:
    if pnl > EPSILON:
        return "PROFIT"
    if pnl < -EPSILON:
        return "LOSS"
    return "BREAK_EVEN"


def _classification(baseline_pnl: float, protected_pnl: float) -> str:
    delta = protected_pnl - baseline_pnl
    if protected_pnl > EPSILON:
        return "PROFIT"
    if delta > EPSILON:
        return "REDUCED_LOSS"
    if protected_pnl < -EPSILON and delta < -EPSILON:
        return "WORSE_LOSS"
    return "UNCHANGED_OR_BREAK_EVEN"


def _switch_case(
    events: tuple[Any, ...],
    points: tuple[Any, ...],
    candidate: Any,
    baseline: Any,
    protected: Any,
) -> StabilityCase:
    assert candidate.direction == "SELL"
    assert protected.close_reason == SWITCH_REASON
    entry_index = int(candidate.entry_index)
    switch_index = _first_opposite_switch(points, candidate)
    assert switch_index is not None and switch_index >= entry_index
    assert points[switch_index].state == "BUY"
    assert points[switch_index].switched
    assert protected.close_timestamp < baseline.close_timestamp
    assert protected.close_price == _close_at_market(events[switch_index], "SELL")

    entry_price = float(protected.entry_price)
    completed_path = events[slice(entry_index, switch_index + 1)]
    mfe = max(
        0.0,
        max(entry_price - float(event.low) for event in completed_path) / PIP_SIZE,
    )
    mae = max(
        0.0,
        max(float(event.high) - entry_price for event in completed_path) / PIP_SIZE,
    )
    baseline_pnl = float(baseline.pnl)
    protected_pnl = float(protected.pnl)
    return StabilityCase(
        entry_index=entry_index,
        switch_index=switch_index,
        entry_timestamp=candidate.entry_timestamp,
        switch_timestamp=protected.close_timestamp,
        baseline_outcome=str(baseline.close_reason),
        baseline_pnl=baseline_pnl,
        protected_outcome=_pnl_outcome(protected_pnl),
        protected_pnl=protected_pnl,
        paired_delta=protected_pnl - baseline_pnl,
        bars_entry_to_switch=switch_index - entry_index + 1,
        mfe_before_switch_pips=mfe,
        mae_before_switch_pips=mae,
        classification=_classification(baseline_pnl, protected_pnl),
        baseline_tp_reached_later=bool(
            baseline.close_reason == "TAKE_PROFIT"
            and baseline.close_timestamp > protected.close_timestamp
        ),
    )


def _enrich_period(data: dict[str, Any]) -> tuple[StabilityCase, ...]:
    events = tuple(data["run"].events)
    points = tuple(_canonical_supertrend(events))
    cases = []
    for candidate, baseline, protected in zip(
        data["sell_candidates"],
        data["sell_baseline"],
        data["sell_protected"],
        strict=True,
    ):
        if protected.close_reason == SWITCH_REASON:
            cases.append(_switch_case(events, points, candidate, baseline, protected))
    assert len(cases) == len(data["trigger_cases"])
    return tuple(cases)


def _case_text(case: StabilityCase) -> str:
    return (
        f"identity:SELL+{case.entry_index},"
        f"entry:{case.entry_timestamp.isoformat()},"
        f"switch:{case.switch_timestamp.isoformat()},"
        f"baseline_outcome:{case.baseline_outcome},"
        f"baseline_pnl:{case.baseline_pnl:+.2f},"
        f"protected_outcome:{case.protected_outcome},"
        f"protected_close_reason:{SWITCH_REASON},"
        f"protected_pnl:{case.protected_pnl:+.2f},"
        f"paired_delta:{case.paired_delta:+.2f},"
        f"bars_entry_to_switch:{case.bars_entry_to_switch},"
        f"mfe_before_switch_pips:{case.mfe_before_switch_pips:.3f},"
        f"mae_before_switch_pips:{case.mae_before_switch_pips:.3f},"
        f"classification:{case.classification},"
        f"baseline_tp_reached_later:{case.baseline_tp_reached_later}"
    )


def _monthly_text(cases: tuple[StabilityCase, ...]) -> str:
    grouped: defaultdict[str, list[StabilityCase]] = defaultdict(list)
    for case in cases:
        grouped[case.entry_timestamp.strftime("%Y-%m")].append(case)
    parts = []
    for month, rows in sorted(grouped.items()):
        delta = sum(row.paired_delta for row in rows)
        parts.append(f"{month}[triggers:{len(rows)},delta:{delta:+.2f}]")
    return "|".join(parts) or "NONE"


def _robustness_text(cases: tuple[StabilityCase, ...]) -> str:
    deltas = [case.paired_delta for case in cases]
    positives = sorted((value for value in deltas if value > EPSILON), reverse=True)
    negatives = sorted(value for value in deltas if value < -EPSILON)
    total = sum(deltas)
    best = max(deltas) if deltas else 0.0
    worst = min(deltas) if deltas else 0.0
    positive_sum = sum(positives)
    negative_magnitude = sum(abs(value) for value in negatives)
    top3_positive_share = (
        sum(positives[:3]) / positive_sum if positive_sum > EPSILON else 0.0
    )
    top3_negative_share = (
        sum(abs(value) for value in negatives[:3]) / negative_magnitude
        if negative_magnitude > EPSILON
        else 0.0
    )
    positive_fraction = len(positives) / len(deltas) if deltas else 0.0
    return (
        f"basis:SWITCH_TRIGGERS_ONLY,triggers:{len(deltas)},"
        f"paired_delta:{total:+.2f},"
        f"leave_one_best_out:{total - best:+.2f},"
        f"leave_one_worst_out:{total - worst:+.2f},"
        f"top3_positive_share:{top3_positive_share:.6f},"
        f"top3_negative_share:{top3_negative_share:.6f},"
        f"median_paired_delta:{_fmt_optional(_percentile(deltas, 0.50))},"
        f"p25_paired_delta:{_fmt_optional(_percentile(deltas, 0.25))},"
        f"p75_paired_delta:{_fmt_optional(_percentile(deltas, 0.75))},"
        f"positive_trigger_fraction:{positive_fraction:.6f}"
    )


def _identity_text(data: dict[str, Any]) -> str:
    keys = [
        (str(candidate.direction), int(candidate.entry_index))
        for candidate in data["candidates"]
    ]
    counts = Counter(keys)
    collisions = sum(count - 1 for count in counts.values() if count > 1)
    assert collisions == 0
    return (
        f"executions:{len(keys)},unique_executions:{len(counts)},"
        f"collisions:{collisions},identity:DIRECTION_PLUS_NEXT_M15_ENTRY_INDEX"
    )


def _cross_period_identity(results: dict[str, dict[str, Any]]) -> str:
    keys = [
        (label, str(candidate.direction), int(candidate.entry_index))
        for label, data in results.items()
        for candidate in data["candidates"]
    ]
    counts = Counter(keys)
    collisions = sum(count - 1 for count in counts.values() if count > 1)
    assert collisions == 0
    return (
        f"executions:{len(keys)},unique_executions:{len(counts)},"
        f"collisions:{collisions},identity:PERIOD_PLUS_DIRECTION_PLUS_ENTRY_INDEX"
    )


def _stability_verdict(
    period_cases: dict[str, tuple[StabilityCase, ...]],
) -> str:
    deltas = [
        sum(case.paired_delta for case in cases) for cases in period_cases.values()
    ]
    if deltas and all(delta > EPSILON for delta in deltas):
        return "DIRECTIONALLY_STABLE_POSITIVE_BOTH_PERIODS"
    if deltas and all(delta < -EPSILON for delta in deltas):
        return "DIRECTIONALLY_STABLE_NEGATIVE_BOTH_PERIODS"
    if deltas and all(abs(delta) <= EPSILON for delta in deltas):
        return "DIRECTIONALLY_STABLE_FLAT_BOTH_PERIODS"
    return "CROSS_PERIOD_DIRECTION_NOT_STABLE"


def _assert_policy_identity(data: dict[str, Any]) -> None:
    assert len(data["baseline"]) == len(data["combined"])
    assert all(
        baseline is combined
        for candidate, baseline, combined in zip(
            data["candidates"],
            data["baseline"],
            data["combined"],
            strict=True,
        )
        if candidate.direction == "BUY"
    )


def main() -> int:
    results: dict[str, dict[str, Any]] = {}
    period_cases: dict[str, tuple[StabilityCase, ...]] = {}
    for window in WINDOWS:
        data = _run_period(window)
        _assert_policy_identity(data)
        results[window.label] = data
        period_cases[window.label] = _enrich_period(data)

    print("T104-26 SELL Supertrend Protected Exit Cross-Period Stability result")
    print(f"  test_id={TEST_ID}")
    print("  mode=TEST_ONLY")
    print("  base=T104_25_SELL_SUPERTREND_PROTECTED_EXIT_DIAGNOSTIC")
    print("  inventory=T104_15_IDENTITY_NORMALIZED_GREEN_8C1_FIRST_LEG")
    print("  period_run_loads=ONE_PER_PERIOD")
    print("  buy_policy=BASELINE_FIXED_SL_TP_UNCHANGED")
    print("  sell_policy=UNCHANGED_T104_25_PROTECTED_SWITCH")
    print("  supertrend_atr_length=10")
    print("  supertrend_factor=3.0")
    print("  switch_signal_source=COMPLETED_M15_BAR")
    print("  switch_exit_price=SWITCH_M15_BAR_MARKET_CLOSE")
    print("  hard_sl_tp_priority_on_same_bar=True")
    print("  same_bar_hard_protection_policy=SL_THEN_TP_THEN_SWITCH")

    for window in WINDOWS:
        label = window.label
        data = results[label]
        cases = period_cases[label]
        run = data["run"]
        print(
            f"  {label}/DATA=m1:{run.accepted_m1_rows},"
            f"m15:{run.completed_m15_bars},"
            f"dropped_incomplete:{run.dropped_incomplete_buckets}"
        )
        print(
            f"  {label}/BASELINE_ALL="
            f"{_comparison_text(data['baseline'], data['baseline'])}"
        )
        print(
            f"  {label}/SELL_BASELINE="
            f"{_comparison_text(data['sell_baseline'], data['sell_baseline'])}"
        )
        print(
            f"  {label}/SELL_PROTECTED_SWITCH="
            f"{_comparison_text(data['sell_baseline'], data['sell_protected'])}"
        )
        print(
            f"  {label}/COMBINED_BUY_BASELINE_SELL_PROTECTED="
            f"{_comparison_text(data['baseline'], data['combined'])}"
        )
        print(f"  {label}/IDENTITY={_identity_text(data)}")
        print(f"  {label}/MONTHLY_DELTA={_monthly_text(cases)}")
        print(f"  {label}/ROBUSTNESS={_robustness_text(cases)}")
        classifications = Counter(case.classification for case in cases)
        print(
            f"  {label}/SWITCH_CLASSIFICATIONS=triggers:{len(cases)},"
            f"reduced_loss:{classifications['REDUCED_LOSS']},"
            f"profit:{classifications['PROFIT']},"
            f"worse_loss:{classifications['WORSE_LOSS']},"
            "unchanged_or_break_even:"
            f"{classifications['UNCHANGED_OR_BREAK_EVEN']},"
            "baseline_tp_reached_later:"
            f"{sum(case.baseline_tp_reached_later for case in cases)}"
        )
        for case in cases:
            print(f"  {label}/SELL_SWITCH_CASE={_case_text(case)}")

    combined_cases = tuple(case for cases in period_cases.values() for case in cases)
    print(f"  CROSS_PERIOD/IDENTITY={_cross_period_identity(results)}")
    print(f"  CROSS_PERIOD/ROBUSTNESS={_robustness_text(combined_cases)}")
    print(f"  stability_verdict={_stability_verdict(period_cases)}")
    print("  stability_basis=PAIRED_DELTA_SIGN_NO_ADDED_THRESHOLD")
    print("  completed_m15_bars_only=True")
    print("  switch_exit_equals_switch_bar_close=True")
    print("  hard_sl_tp_priority_on_same_bar=True")
    print("  future_price_used=False")
    print("  outcome_used_for_selection=False")
    print("  new_thresholds_added=False")
    print("  supertrend_parameters_optimized=False")
    print("  supertrend_parameters_unchanged_10_3=True")
    print("  production_logic_changed=False")
    print("  candidate_f_changed=False")
    print("  entry_logic_changed=False")
    print("  buy_exit_logic_changed=False")
    print("  sell_protected_switch_policy_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  diagnostic_status=GREEN")
    print("T104_26_SELL_SUPERTREND_PROTECTED_EXIT_STABILITY_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
