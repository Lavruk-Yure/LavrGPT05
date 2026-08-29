# -*- coding: utf-8 -*-
"""RoadMap104 / T104-22: causal Traditional Daily Pivot TP policy diagnostic.

TEST_ONLY paired replay over the T104-15 identity-normalized GREEN 8C.1
first-leg inventory. Each period's indicator run is loaded exactly once.
Nearest favorable pivots use T104-21 canonical previous-completed-day
semantics and are fixed at entry. Policy selection never uses an outcome.
"""

from __future__ import annotations

import importlib.util
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
    "run_t104_21_algorithm_workspace_daily_pivot_structural_tp_anatomy_"
    "2025_2026_check.py"
)
TEST_ID = "T104-22"
STOP_LOSS_PIPS = 12.0
TAKE_PROFIT_PIPS = 24.0
EPSILON = 1e-12
BASELINE = "BASELINE_FIXED_2R"
PIVOT_CAP = "PIVOT_CAP_1R_TO_2R"


def _load_base_module() -> ModuleType:
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm104_t104_22_daily_pivot_anatomy_base"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()
WINDOWS = getattr(BASE, "WINDOWS")
OPENING_BASE = getattr(BASE, "OPENING_BASE")
CORE_BASE = getattr(BASE, "CORE_BASE")
PIP_SIZE = float(getattr(BASE, "PIP_SIZE"))
FIXED_VOLUME = float(getattr(CORE_BASE, "FIXED_VOLUME"))
EXPECTED_M15_DELTA = getattr(CORE_BASE, "EXPECTED_M15_DELTA")
TradeResult = getattr(CORE_BASE, "TradeResult")
_load_indicator_run: Callable[..., Any] = getattr(BASE, "_load_indicator_run")
_entry_price: Callable[..., float] = getattr(BASE, "_entry_price")
_close_at_market: Callable[..., float] = getattr(CORE_BASE, "_close_at_market")
_confirmed_candidates: Callable[..., Any] = getattr(
    OPENING_BASE, "_confirmed_expansion_candidates"
)
_first_leg_survivor_indices: Callable[..., Any] = getattr(
    BASE, "_first_leg_survivor_indices"
)
_daily_levels: Callable[..., Any] = getattr(BASE, "_daily_levels")
_favorable_levels: Callable[..., Any] = getattr(BASE, "_favorable_levels")
_summary: Callable[..., Any] = getattr(OPENING_BASE, "_summary")
_summary_text: Callable[..., str] = getattr(OPENING_BASE, "_summary_text")


@dataclass(frozen=True, slots=True)
class EntryPivot:
    level: str | None
    price: float | None
    distance_pips: float | None
    category: str


@dataclass(frozen=True, slots=True)
class PolicyResult:
    trade: Any
    target_pips: float
    target_was_capped: bool
    pivot_broken_before_exit: bool
    breakout_then_2r: bool
    breakout_then_sl: bool


def _entry_pivot(
    events: tuple[Any, ...], candidate: Any, daily: dict[Any, Any]
) -> EntryPivot:
    entry = _entry_price(events[int(candidate.entry_index)], candidate.direction)
    sign = 1.0 if candidate.direction == "BUY" else -1.0
    day = events[int(candidate.entry_index)].timestamp.date()
    available = [
        (name, price)
        for name, price in _favorable_levels(daily[day], candidate.direction)
        if sign * (price - entry) > EPSILON
    ]
    if not available:
        return EntryPivot(None, None, None, "NO_FAVORABLE_PIVOT")
    name, price = min(available, key=lambda item: sign * (item[1] - entry))
    distance = sign * (price - entry) / PIP_SIZE
    if distance < STOP_LOSS_PIPS - EPSILON:
        category = "PIVOT_TOO_CLOSE_IGNORE"
    elif distance < TAKE_PROFIT_PIPS - EPSILON:
        category = "PIVOT_CAP_1R_TO_2R"
    elif distance <= TAKE_PROFIT_PIPS + EPSILON:
        category = "PIVOT_AT_2R_BASELINE_EQUIVALENT"
    else:
        category = "PIVOT_BEYOND_2R_CONTEXT_ONLY"
    return EntryPivot(name, price, distance, category)


def _target_pips(pivot: EntryPivot, policy: str) -> float:
    if policy == PIVOT_CAP and pivot.category == "PIVOT_CAP_1R_TO_2R":
        assert pivot.distance_pips is not None
        return pivot.distance_pips
    assert policy in {BASELINE, PIVOT_CAP}
    return TAKE_PROFIT_PIPS


def _simulate(
    events: tuple[Any, ...], candidate: Any, pivot: EntryPivot, policy: str
) -> PolicyResult:
    entry_index = int(candidate.entry_index)
    entry = _entry_price(events[entry_index], candidate.direction)
    sign = 1.0 if candidate.direction == "BUY" else -1.0
    target_pips = _target_pips(pivot, policy)
    stop = entry - sign * STOP_LOSS_PIPS * PIP_SIZE
    take = entry + sign * target_pips * PIP_SIZE
    close_index = len(events) - 1
    close_price = _close_at_market(events[close_index], candidate.direction)
    close_reason = "SESSION_END"
    pivot_broken = False

    for index in range(entry_index, len(events)):
        event = events[index]
        if candidate.direction == "BUY":
            stop_touched = float(event.low) <= stop
            take_touched = float(event.high) >= take
            strictly_broken = bool(
                pivot.price is not None and float(event.high) > pivot.price + EPSILON
            )
        else:
            stop_touched = float(event.high) >= stop
            take_touched = float(event.low) <= take
            strictly_broken = bool(
                pivot.price is not None and float(event.low) < pivot.price - EPSILON
            )

        # Existing conservative convention: an ambiguous same bar is an SL.
        if stop_touched:
            close_index, close_price, close_reason = index, stop, "STOP_LOSS"
            break
        if take_touched:
            # A lower pivot is necessarily crossed before a 2R price target.
            if target_pips == TAKE_PROFIT_PIPS and strictly_broken:
                pivot_broken = True
            close_index, close_price, close_reason = index, take, "TAKE_PROFIT"
            break
        if strictly_broken:
            pivot_broken = True

    trade = TradeResult(
        direction=candidate.direction,
        start_timestamp=candidate.start_timestamp,
        confirm_timestamp=candidate.confirm_timestamp,
        entry_timestamp=candidate.entry_timestamp,
        close_timestamp=events[close_index].timestamp + EXPECTED_M15_DELTA,
        entry_price=entry,
        close_price=close_price,
        close_reason=close_reason,
        pnl=(close_price - entry) * FIXED_VOLUME * sign,
        holding_bars=close_index - entry_index + 1,
    )
    eligible_breakout = bool(
        pivot.distance_pips is not None
        and pivot.distance_pips < TAKE_PROFIT_PIPS - EPSILON
        and pivot_broken
    )
    return PolicyResult(
        trade=trade,
        target_pips=target_pips,
        target_was_capped=target_pips < TAKE_PROFIT_PIPS - EPSILON,
        pivot_broken_before_exit=eligible_breakout,
        breakout_then_2r=eligible_breakout and close_reason == "TAKE_PROFIT",
        breakout_then_sl=eligible_breakout and close_reason == "STOP_LOSS",
    )


def _paired_counts(
    baseline: tuple[PolicyResult, ...], capped: tuple[PolicyResult, ...]
) -> str:
    shortened = sum(row.target_was_capped for row in capped)
    sl_to_win = sum(
        left.trade.close_reason == "STOP_LOSS"
        and right.trade.close_reason == "TAKE_PROFIT"
        for left, right in zip(baseline, capped, strict=True)
    )
    tp_lost_profit = sum(
        left.trade.close_reason == "TAKE_PROFIT"
        and right.target_was_capped
        and right.trade.pnl < left.trade.pnl - EPSILON
        for left, right in zip(baseline, capped, strict=True)
    )
    delta = sum(
        right.trade.pnl - left.trade.pnl
        for left, right in zip(baseline, capped, strict=True)
    )
    return (
        f"tp_shortened:{shortened},baseline_sl_to_pivot_tp_win:{sl_to_win},"
        f"baseline_tp_lost_profit:{tp_lost_profit},paired_pnl_delta:{delta:+.2f}"
    )


def _breakout_text(rows: tuple[PolicyResult, ...]) -> str:
    broken = sum(row.pivot_broken_before_exit for row in rows)
    return (
        f"strict_break_before_actual_exit:{broken},"
        f"then_baseline_2r:{sum(row.breakout_then_2r for row in rows)},"
        f"then_sl:{sum(row.breakout_then_sl for row in rows)}"
    )


def _category_text(pivots: tuple[EntryPivot, ...]) -> str:
    counts = Counter(pivot.category for pivot in pivots)
    return "|".join(f"{key}:{counts[key]}" for key in sorted(counts))


def _beyond_2r_context_text(
    pivots: tuple[EntryPivot, ...], baseline: tuple[PolicyResult, ...]
) -> str:
    paired = tuple(
        row
        for pivot, row in zip(pivots, baseline, strict=True)
        if pivot.category == "PIVOT_BEYOND_2R_CONTEXT_ONLY"
    )
    baseline_tp = sum(row.trade.close_reason == "TAKE_PROFIT" for row in paired)
    return (
        f"trades:{len(paired)},baseline_tp_before_pivot:{baseline_tp},"
        f"baseline_exit_without_tp:{len(paired) - baseline_tp}"
    )


def _subset(
    rows: tuple[PolicyResult, ...], indices: tuple[int, ...]
) -> tuple[PolicyResult, ...]:
    return tuple(rows[index] for index in indices)


def _report_slice(
    label: str,
    indices: tuple[int, ...],
    pivots: tuple[EntryPivot, ...],
    baseline: tuple[PolicyResult, ...],
    capped: tuple[PolicyResult, ...],
) -> None:
    slice_pivots = tuple(pivots[index] for index in indices)
    slice_baseline = _subset(baseline, indices)
    slice_capped = _subset(capped, indices)
    print(
        f"  {label}/{BASELINE}="
        f"{_summary_text(_summary(tuple(row.trade for row in slice_baseline)))}"
    )
    print(
        f"  {label}/{PIVOT_CAP}="
        f"{_summary_text(_summary(tuple(row.trade for row in slice_capped)))},"
        f"{_paired_counts(slice_baseline, slice_capped)}"
    )
    print(f"  {label}/ENTRY_CATEGORIES={_category_text(slice_pivots)}")
    print(
        f"  {label}/PIVOT_BEYOND_2R_CONTEXT_ONLY="
        f"{_beyond_2r_context_text(slice_pivots, slice_baseline)}"
    )
    print(f"  {label}/BASELINE_BREAKOUT={_breakout_text(slice_baseline)}")
    print(f"  {label}/PIVOT_CAP_BREAKOUT={_breakout_text(slice_capped)}")


def main() -> int:
    results: dict[str, dict[str, Any]] = {}
    for window in WINDOWS:
        print(f"  running_period={window.label}", flush=True)
        run = _load_indicator_run(window)
        events = tuple(run.events)
        candidates = tuple(_confirmed_candidates(run)[0])
        survivor_indices = tuple(_first_leg_survivor_indices(candidates))
        selected = tuple(candidates[index] for index in survivor_indices)
        assert len(selected) == len(
            {(row.direction, row.entry_index) for row in selected}
        )
        daily = _daily_levels(events)
        pivots = tuple(_entry_pivot(events, candidate, daily) for candidate in selected)
        baseline = tuple(
            _simulate(events, candidate, pivot, BASELINE)
            for candidate, pivot in zip(selected, pivots, strict=True)
        )
        capped = tuple(
            _simulate(events, candidate, pivot, PIVOT_CAP)
            for candidate, pivot in zip(selected, pivots, strict=True)
        )
        assert all(not row.target_was_capped for row in baseline)
        assert all(
            row.target_was_capped == (pivot.category == "PIVOT_CAP_1R_TO_2R")
            for row, pivot in zip(capped, pivots, strict=True)
        )
        results[window.label] = {
            "candidates": selected,
            "pivots": pivots,
            "baseline": baseline,
            "capped": capped,
        }

    print("T104-22 Causal Pivot TP Policy Diagnostic result")
    print(f"  test_id={TEST_ID}")
    print("  mode=TEST_ONLY")
    print("  inventory=T104_15_IDENTITY_NORMALIZED_GREEN_8C1_FIRST_LEG")
    print("  period_run_loads=ONE_PER_PERIOD")
    print("  stop_loss_pips=12.0")
    print("  baseline_take_profit_pips=24.0")
    print("  policy_a=PIVOT_CAP_IF_DISTANCE_GTE_1R_AND_LT_2R")
    print("  policy_b=PIVOT_LT_1R_IGNORED_DIAGNOSTIC_CATEGORY")
    print("  policy_c=PIVOT_GT_2R_CONTEXT_ONLY_BASELINE_TP_UNCHANGED")
    print("  pivot_exactly_2r=BASELINE_EQUIVALENT_SEPARATE_CATEGORY")
    print("  same_bar_policy=SL_FIRST_CONSERVATIVE")
    print("  post_actual_policy_exit_events_used=False")
    for window in WINDOWS:
        data = results[window.label]
        candidates = data["candidates"]
        all_indices = tuple(range(len(candidates)))
        _report_slice(
            f"{window.label}/ALL",
            all_indices,
            data["pivots"],
            data["baseline"],
            data["capped"],
        )
        for direction in ("BUY", "SELL"):
            indices = tuple(
                index
                for index, candidate in enumerate(candidates)
                if candidate.direction == direction
            )
            _report_slice(
                f"{window.label}/{direction}",
                indices,
                data["pivots"],
                data["baseline"],
                data["capped"],
            )

    print("  performance_is_diagnostic_not_pass_criterion=True")
    print("  production_logic_changed=False")
    print("  candidate_f_changed=False")
    print("  entry_logic_changed=False")
    print("  sl_logic_changed=False")
    print("  bbw_changed=False")
    print("  ac_changed=False")
    print("  stochastic_changed=False")
    print("  dmi_adx_changed=False")
    print("  fractal_logic_changed=False")
    print("  new_numeric_thresholds=False")
    print("  completed_bars_only=True")
    print("  future_price_used=False")
    print("  outcome_used_for_selection=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  diagnostic_status=GREEN")
    print("T104_22_CAUSAL_PIVOT_TP_POLICY_DIAGNOSTIC_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
