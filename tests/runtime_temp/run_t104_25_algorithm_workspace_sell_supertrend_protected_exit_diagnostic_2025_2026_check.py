# -*- coding: utf-8 -*-
"""RoadMap104 / T104-25: SELL Supertrend protected-exit diagnostic.

TEST_ONLY paired replay over the T104-15 identity-normalized GREEN 8C.1
first-leg inventory. BUY trades remain the fixed 12-pip SL / 24-pip TP
baseline. SELL trades preserve those hard levels but may exit at the close of
the first completed M15 bar that causally switches canonical Supertrend(10, 3)
from SELL to BUY. Hard SL/TP are evaluated before the switch on the same bar.

The canonical implementation is reused from T104-24. No outcome selects an
execution, no threshold is added, and no production behavior is changed.
"""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BASE_SCRIPT_NAME = (
    "run_t104_24_algorithm_workspace_supertrend_dynamic_sl_exit_anatomy_"
    "2025_2026_check.py"
)
TEST_ID = "T104-25"
SWITCH_REASON = "SUPERTREND_OPPOSITE_SWITCH"


def _load_base_module() -> ModuleType:
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm104_t104_25_supertrend_anatomy_base"
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
_load_indicator_run: Callable[..., Any] = getattr(BASE, "_load_indicator_run")
_confirmed_candidates: Callable[..., Any] = getattr(BASE, "_confirmed_candidates")
_first_leg_survivor_indices: Callable[..., Any] = getattr(
    BASE, "_first_leg_survivor_indices"
)
_simulate_baseline: Callable[..., Any] = getattr(BASE, "_simulate_baseline")
_canonical_supertrend: Callable[..., Any] = getattr(BASE, "_canonical_supertrend")
_first_opposite_switch: Callable[..., Any] = getattr(BASE, "_first_opposite_switch")
_protected_switch_trade: Callable[..., Any] = getattr(BASE, "_protected_switch_trade")
_summary: Callable[..., Any] = getattr(BASE, "_summary")


@dataclass(frozen=True, slots=True)
class TriggerCase:
    """One SELL whose causal switch exit precedes its baseline exit."""

    entry_index: int
    entry_timestamp: Any
    baseline_outcome: str
    baseline_pnl: float
    protected_pnl: float
    delta: float
    bars_to_switch: int
    previous_bar_distance_pips: float
    saved_baseline_sl: bool
    cut_baseline_tp_early: bool


def _fmt_pf(value: float | None) -> str:
    return "NONE" if value is None else f"{value:.4f}"


def _summary_text(trades: tuple[Any, ...]) -> str:
    summary = _summary(trades)
    reasons = summary.close_reasons
    return (
        f"trades:{summary.trades},wins:{summary.wins},losses:{summary.losses},"
        f"break_even:{summary.break_even},net:{summary.net:+.2f},"
        f"pf:{_fmt_pf(summary.profit_factor)},dd:{summary.maximum_drawdown:.2f},"
        f"hold:{summary.average_holding_bars:.2f},"
        f"sl:{reasons['STOP_LOSS']},tp:{reasons['TAKE_PROFIT']},"
        f"switch:{reasons[SWITCH_REASON]},session_end:{reasons['SESSION_END']}"
    )


def _paired_counts(baseline: tuple[Any, ...], variant: tuple[Any, ...]) -> str:
    assert len(baseline) == len(variant)
    deltas = [
        float(right.pnl) - float(left.pnl)
        for left, right in zip(baseline, variant, strict=True)
    ]
    improved = sum(delta > EPSILON for delta in deltas)
    worsened = sum(delta < -EPSILON for delta in deltas)
    return (
        f"paired_pnl_delta:{sum(deltas):+.2f},improved:{improved},"
        f"worsened:{worsened},unchanged:{len(deltas) - improved - worsened}"
    )


def _comparison_text(baseline: tuple[Any, ...], variant: tuple[Any, ...]) -> str:
    return f"{_summary_text(variant)},{_paired_counts(baseline, variant)}"


def _trigger_case(
    events: tuple[Any, ...],
    points: tuple[Any, ...],
    candidate: Any,
    baseline: Any,
    protected: Any,
) -> TriggerCase:
    assert candidate.direction == "SELL"
    assert protected.close_reason == SWITCH_REASON
    switch_index = _first_opposite_switch(points, candidate)
    assert switch_index is not None and switch_index > 0
    assert points[switch_index - 1].state == "SELL"
    assert points[switch_index].state == "BUY"
    assert points[switch_index].switched
    assert protected.close_timestamp < baseline.close_timestamp
    previous_line = points[switch_index - 1].line
    assert previous_line is not None
    previous_close = float(events[switch_index - 1].close)
    previous_distance = abs(float(previous_line) - previous_close) / PIP_SIZE
    delta = float(protected.pnl) - float(baseline.pnl)
    return TriggerCase(
        entry_index=int(candidate.entry_index),
        entry_timestamp=candidate.entry_timestamp,
        baseline_outcome=str(baseline.close_reason),
        baseline_pnl=float(baseline.pnl),
        protected_pnl=float(protected.pnl),
        delta=delta,
        bars_to_switch=switch_index - int(candidate.entry_index) + 1,
        previous_bar_distance_pips=previous_distance,
        saved_baseline_sl=(baseline.close_reason == "STOP_LOSS" and delta > EPSILON),
        cut_baseline_tp_early=(
            baseline.close_reason == "TAKE_PROFIT" and delta < -EPSILON
        ),
    )


def _case_text(case: TriggerCase) -> str:
    return (
        f"identity:SELL+{case.entry_index},"
        f"entry:{case.entry_timestamp.isoformat()},"
        f"baseline_outcome:{case.baseline_outcome},"
        f"baseline_pnl:{case.baseline_pnl:+.2f},"
        f"protected_pnl:{case.protected_pnl:+.2f},delta:{case.delta:+.2f},"
        f"bars_entry_to_switch:{case.bars_to_switch},"
        f"previous_completed_bar_st_distance_pips:"
        f"{case.previous_bar_distance_pips:.3f},"
        f"saved_baseline_sl:{case.saved_baseline_sl},"
        f"cut_baseline_tp_early:{case.cut_baseline_tp_early}"
    )


def _monthly_text(
    candidates: tuple[Any, ...],
    baseline: tuple[Any, ...],
    protected: tuple[Any, ...],
) -> str:
    grouped: defaultdict[str, list[tuple[Any, Any]]] = defaultdict(list)
    for candidate, left, right in zip(candidates, baseline, protected, strict=True):
        month = candidate.entry_timestamp.strftime("%Y-%m")
        grouped[month].append((left, right))

    parts: list[str] = []
    for month in sorted(grouped):
        pairs = grouped[month]
        baseline_net = sum(float(left.pnl) for left, _ in pairs)
        protected_net = sum(float(right.pnl) for _, right in pairs)
        switches = sum(right.close_reason == SWITCH_REASON for _, right in pairs)
        improved = sum(
            float(right.pnl) > float(left.pnl) + EPSILON for left, right in pairs
        )
        worsened = sum(
            float(right.pnl) < float(left.pnl) - EPSILON for left, right in pairs
        )
        parts.append(
            f"{month}[trades:{len(pairs)},baseline_net:{baseline_net:+.2f},"
            f"protected_net:{protected_net:+.2f},"
            f"delta:{protected_net - baseline_net:+.2f},switch:{switches},"
            f"improved:{improved},worsened:{worsened},"
            f"unchanged:{len(pairs) - improved - worsened}]"
        )
    return "|".join(parts) or "NONE"


def _outlier_text(baseline: tuple[Any, ...], protected: tuple[Any, ...]) -> str:
    deltas = sorted(
        (
            float(right.pnl) - float(left.pnl)
            for left, right in zip(baseline, protected, strict=True)
        ),
        reverse=True,
    )
    positive = [delta for delta in deltas if delta > EPSILON]
    total_delta = sum(deltas)
    positive_sum = sum(positive)
    best = positive[0] if positive else 0.0
    top_three = sum(positive[:3])
    best_share = best / positive_sum if positive_sum > EPSILON else 0.0
    top_three_share = top_three / positive_sum if positive_sum > EPSILON else 0.0
    leave_one_best_out = total_delta - best
    return (
        f"combined_delta:{total_delta:+.2f},positive_contributors:{len(positive)},"
        f"positive_contribution_sum:{positive_sum:+.2f},"
        f"best_improvement:{best:+.2f},best_share_of_positive:{best_share:.6f},"
        f"top3_share_of_positive:{top_three_share:.6f},"
        f"leave_one_best_improvement_out_combined_delta:{leave_one_best_out:+.2f},"
        f"positive_after_leave_one_best_out:{leave_one_best_out > EPSILON},"
        "assessment=DESCRIPTIVE_NO_OUTLIER_THRESHOLD"
    )


def _identity_text(candidates: tuple[Any, ...]) -> str:
    keys = [(str(row.direction), int(row.entry_index)) for row in candidates]
    counts = Counter(keys)
    collisions = sum(value - 1 for value in counts.values() if value > 1)
    return (
        f"executions:{len(keys)},unique:{len(counts)},"
        f"collision_instances:{collisions},"
        "identity=DIRECTION_PLUS_NEXT_M15_ENTRY_INDEX"
    )


def _run_period(window: Any) -> dict[str, Any]:
    print(f"  running_period={window.label}", flush=True)
    run = _load_indicator_run(window)
    events = tuple(run.events)
    candidates = tuple(_confirmed_candidates(run)[0])
    survivor_indices = tuple(_first_leg_survivor_indices(candidates))
    selected = tuple(candidates[index] for index in survivor_indices)
    raw_baseline = tuple(
        _simulate_baseline(run, candidate, macd_exit_enabled=False)
        for candidate in candidates
    )
    baseline = tuple(raw_baseline[index] for index in survivor_indices)
    points = tuple(_canonical_supertrend(events))

    protected: list[Any] = []
    sell_candidates: list[Any] = []
    sell_baseline: list[Any] = []
    sell_protected: list[Any] = []
    trigger_cases: list[TriggerCase] = []
    for candidate, baseline_trade in zip(selected, baseline, strict=True):
        if candidate.direction == "BUY":
            policy_trade = baseline_trade
        else:
            switch_index = _first_opposite_switch(points, candidate)
            policy_trade = _protected_switch_trade(events, candidate, switch_index)
            sell_candidates.append(candidate)
            sell_baseline.append(baseline_trade)
            sell_protected.append(policy_trade)
            if policy_trade.close_reason == SWITCH_REASON:
                trigger_cases.append(
                    _trigger_case(
                        events,
                        points,
                        candidate,
                        baseline_trade,
                        policy_trade,
                    )
                )
        protected.append(policy_trade)

    combined = tuple(protected)
    sell_candidates_tuple = tuple(sell_candidates)
    sell_baseline_tuple = tuple(sell_baseline)
    sell_protected_tuple = tuple(sell_protected)
    assert len(selected) == len(baseline) == len(combined)
    assert all(
        left is right
        for candidate, left, right in zip(selected, baseline, combined, strict=True)
        if candidate.direction == "BUY"
    )
    assert len(selected) == len(
        {(row.direction, int(row.entry_index)) for row in selected}
    )
    assert len(sell_candidates_tuple) == len(
        {(row.direction, int(row.entry_index)) for row in sell_candidates_tuple}
    )
    assert sum(
        trade.close_reason == SWITCH_REASON for trade in sell_protected_tuple
    ) == len(trigger_cases)
    return {
        "run": run,
        "candidates": selected,
        "baseline": baseline,
        "combined": combined,
        "sell_candidates": sell_candidates_tuple,
        "sell_baseline": sell_baseline_tuple,
        "sell_protected": sell_protected_tuple,
        "trigger_cases": tuple(trigger_cases),
    }


def main() -> int:
    results = {window.label: _run_period(window) for window in WINDOWS}

    print("T104-25 SELL Supertrend Protected Exit Diagnostic result")
    print(f"  test_id={TEST_ID}")
    print("  mode=TEST_ONLY")
    print("  base=T104_24_CANONICAL_SUPERTREND_ANATOMY")
    print("  inventory=T104_15_IDENTITY_NORMALIZED_GREEN_8C1_FIRST_LEG")
    print("  period_run_loads=ONE_PER_PERIOD")
    print("  buy_policy=BASELINE_FIXED_SL_TP_UNCHANGED")
    print("  sell_policy=HARD_SL_TP_OR_FIRST_CAUSAL_SELL_TO_BUY_SWITCH")
    print("  supertrend_atr_length=10")
    print("  supertrend_factor=3.0")
    print("  supertrend_source=HL2")
    print("  supertrend_atr_smoothing=WILDER_RMA")
    print("  switch_exit_price=SWITCH_M15_BAR_MARKET_CLOSE")
    print("  hard_protection_checked_before_switch_on_same_bar=True")
    print("  same_bar_policy=SL_FIRST_CONSERVATIVE")
    print("  fixed_sl_pips=12.0")
    print("  fixed_tp_pips=24.0")

    for window in WINDOWS:
        data = results[window.label]
        run = data["run"]
        baseline = data["baseline"]
        sell_baseline = data["sell_baseline"]
        sell_protected = data["sell_protected"]
        combined = data["combined"]
        print(
            f"  {window.label}/DATA=m1:{run.accepted_m1_rows},"
            f"m15:{run.completed_m15_bars},"
            f"dropped_incomplete:{run.dropped_incomplete_buckets}"
        )
        print(
            f"  {window.label}/BASELINE_ALL=" f"{_comparison_text(baseline, baseline)}"
        )
        print(
            f"  {window.label}/SELL_BASELINE="
            f"{_comparison_text(sell_baseline, sell_baseline)}"
        )
        print(
            f"  {window.label}/SELL_PROTECTED_SWITCH="
            f"{_comparison_text(sell_baseline, sell_protected)}"
        )
        print(
            f"  {window.label}/COMBINED_BUY_BASELINE_SELL_PROTECTED="
            f"{_comparison_text(baseline, combined)}"
        )
        print(f"  {window.label}/ALL_IDENTITY=" f"{_identity_text(data['candidates'])}")
        print(
            f"  {window.label}/SELL_IDENTITY="
            f"{_identity_text(data['sell_candidates'])}"
        )
        print(
            f"  {window.label}/SELL_MONTHLY="
            f"{_monthly_text(data['sell_candidates'], sell_baseline, sell_protected)}"
        )
        print(
            f"  {window.label}/OUTLIER_DIAGNOSTIC="
            f"{_outlier_text(sell_baseline, sell_protected)}"
        )
        outcomes = Counter(case.baseline_outcome for case in data["trigger_cases"])
        print(
            f"  {window.label}/TRIGGER_CASES="
            f"trades:{len(data['trigger_cases'])},"
            f"baseline_tp:{outcomes['TAKE_PROFIT']},"
            f"baseline_sl:{outcomes['STOP_LOSS']},"
            f"baseline_session_end:{outcomes['SESSION_END']},"
            "saved_baseline_sl:"
            f"{sum(case.saved_baseline_sl for case in data['trigger_cases'])},"
            "cut_baseline_tp_early:"
            f"{sum(case.cut_baseline_tp_early for case in data['trigger_cases'])}"
        )
        for case in data["trigger_cases"]:
            print(f"  {window.label}/SELL_SWITCH_CASE={_case_text(case)}")

    print("  outcome_used_for_selection=False")
    print("  new_thresholds_added=False")
    print("  supertrend_parameters_optimized=False")
    print("  performance_is_diagnostic_not_pass_criterion=True")
    print("  production_logic_changed=False")
    print("  candidate_f_changed=False")
    print("  entry_logic_changed=False")
    print("  buy_exit_logic_changed=False")
    print("  production_sell_exit_logic_changed=False")
    print("  completed_bars_only=True")
    print("  future_price_used=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  diagnostic_status=GREEN")
    print("T104_25_SELL_SUPERTREND_PROTECTED_EXIT_DIAGNOSTIC_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
