# -*- coding: utf-8 -*-
"""RoadMap104 / T104-23: ATR structural-SL distance anatomy.

TEST_ONLY descriptive analysis over the T104-15 identity-normalized GREEN 8C.1
first-leg inventory. ATR is canonical True Range with Wilder RMA smoothing over
14 M15 bars. The value attached to an entry is from entry_index - 1, so only
bars completed before the NEXT_M15_OPEN execution are used.

The fixed 12-pip SL and fixed 24-pip TP remain unchanged. ATR ratios describe
the frozen baseline and do not select trades or define a policy.
"""

from __future__ import annotations

import importlib.util
import math
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
    "run_t104_15_algorithm_workspace_causal_execution_identity_normalization_"
    "2025_2026_check.py"
)
TEST_ID = "T104-23"
ATR_LENGTH = 14
STOP_LOSS_PIPS = 12.0
TAKE_PROFIT_PIPS = 24.0


def _load_base_module() -> ModuleType:
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm104_t104_23_normalized_green_8c1_base"
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
        "rm104_t104_23_green_8c1_opening_base", file_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


OPENING_BASE = _load_opening_module()
CORE_BASE = getattr(OPENING_BASE, "BASE")
PIP_SIZE = float(getattr(CORE_BASE, "PIP_SIZE"))
_load_indicator_run: Callable[..., Any] = getattr(OPENING_BASE, "_load_indicator_run")


@dataclass(frozen=True, slots=True)
class AtrAnatomy:
    """Canonical completed-bar ATR measurements for one frozen trade."""

    direction: str
    outcome: str
    entry_index: int
    atr_source_index: int
    atr_price: float
    atr_pips: float
    sl_atr_ratio: float
    tp_atr_ratio: float


def _canonical_atr(events: tuple[Any, ...]) -> tuple[float | None, ...]:
    """Return canonical TR(1) -> Wilder RMA(14), aligned to M15 bars."""
    true_ranges: list[float] = []
    result: list[float | None] = []
    previous_close: float | None = None
    rma: float | None = None
    for index, event in enumerate(events):
        high = float(event.high)
        low = float(event.low)
        if previous_close is None:
            true_range = high - low
        else:
            true_range = max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )
        assert true_range >= 0.0 and math.isfinite(true_range)
        true_ranges.append(true_range)
        if index == ATR_LENGTH - 1:
            rma = sum(true_ranges) / ATR_LENGTH
        elif index >= ATR_LENGTH:
            assert rma is not None
            rma = ((ATR_LENGTH - 1) * rma + true_range) / ATR_LENGTH
        result.append(rma)
        previous_close = float(event.close)
    return tuple(result)


def _entry_rows(
    events: tuple[Any, ...], candidates: tuple[Any, ...], trades: tuple[Any, ...]
) -> tuple[AtrAnatomy, ...]:
    atr = _canonical_atr(events)
    assert len(candidates) == len(trades)
    rows: list[AtrAnatomy] = []
    for candidate, trade in zip(candidates, trades, strict=True):
        entry_index = int(candidate.entry_index)
        source_index = entry_index - 1
        assert source_index >= ATR_LENGTH - 1
        atr_price = atr[source_index]
        assert atr_price is not None and atr_price > 0.0
        atr_pips = atr_price / PIP_SIZE
        rows.append(
            AtrAnatomy(
                direction=str(candidate.direction),
                outcome=str(trade.close_reason),
                entry_index=entry_index,
                atr_source_index=source_index,
                atr_price=atr_price,
                atr_pips=atr_pips,
                sl_atr_ratio=STOP_LOSS_PIPS / atr_pips,
                tp_atr_ratio=TAKE_PROFIT_PIPS / atr_pips,
            )
        )
    return tuple(rows)


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _fmt(value: float | None, decimals: int = 3) -> str:
    return "NONE" if value is None else f"{value:.{decimals}f}"


def _distribution(rows: tuple[AtrAnatomy, ...]) -> str:
    counts = Counter(row.outcome for row in rows)
    return "|".join(f"{key}:{counts[key]}" for key in sorted(counts)) or "NONE"


def _summary_text(rows: tuple[AtrAnatomy, ...]) -> str:
    atr_price = [row.atr_price for row in rows]
    atr_pips = [row.atr_pips for row in rows]
    sl_ratio = [row.sl_atr_ratio for row in rows]
    tp_ratio = [row.tp_atr_ratio for row in rows]
    return (
        f"trades:{len(rows)},outcomes:{_distribution(rows)},"
        f"atr_price_median:{_fmt(_percentile(atr_price, 0.50), 6)},"
        f"atr_pips_median:{_fmt(_percentile(atr_pips, 0.50))},"
        f"atr_pips_p25:{_fmt(_percentile(atr_pips, 0.25))},"
        f"atr_pips_p75:{_fmt(_percentile(atr_pips, 0.75))},"
        f"sl_atr_median:{_fmt(_percentile(sl_ratio, 0.50))},"
        f"sl_atr_p25:{_fmt(_percentile(sl_ratio, 0.25))},"
        f"sl_atr_p75:{_fmt(_percentile(sl_ratio, 0.75))},"
        f"tp_atr_median:{_fmt(_percentile(tp_ratio, 0.50))},"
        f"tp_atr_p25:{_fmt(_percentile(tp_ratio, 0.25))},"
        f"tp_atr_p75:{_fmt(_percentile(tp_ratio, 0.75))}"
    )


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    covariance = sum(
        (x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True)
    )
    left_ss = sum((value - left_mean) ** 2 for value in left)
    right_ss = sum((value - right_mean) ** 2 for value in right)
    denominator = math.sqrt(left_ss * right_ss)
    return covariance / denominator if denominator else None


def _midranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][1] == ordered[start][1]:
            end += 1
        rank = (start + 1 + end) / 2.0
        for position in range(start, end):
            ranks[ordered[position][0]] = rank
        start = end
    return ranks


def _auc(positive: list[float], negative: list[float]) -> float | None:
    if not positive or not negative:
        return None
    favorable = 0.0
    for positive_value in positive:
        for negative_value in negative:
            if positive_value > negative_value:
                favorable += 1.0
            elif positive_value == negative_value:
                favorable += 0.5
    return favorable / (len(positive) * len(negative))


def _relation_text(rows: tuple[AtrAnatomy, ...]) -> str:
    decisive = tuple(row for row in rows if row.outcome in {"TAKE_PROFIT", "STOP_LOSS"})
    ratios = [row.sl_atr_ratio for row in decisive]
    outcome = [1.0 if row.outcome == "TAKE_PROFIT" else 0.0 for row in decisive]
    tp_ratio = [row.sl_atr_ratio for row in decisive if row.outcome == "TAKE_PROFIT"]
    sl_ratio = [row.sl_atr_ratio for row in decisive if row.outcome == "STOP_LOSS"]
    point_biserial = _pearson(ratios, outcome)
    spearman = _pearson(_midranks(ratios), _midranks(outcome))
    auc = _auc(tp_ratio, sl_ratio)
    return (
        f"decisive_trades:{len(decisive)},tp:{len(tp_ratio)},sl:{len(sl_ratio)},"
        f"point_biserial_ratio_vs_tp:{_fmt(point_biserial, 6)},"
        f"spearman_ratio_vs_tp:{_fmt(spearman, 6)},"
        f"auc_probability_tp_ratio_gt_sl_ratio:{_fmt(auc, 6)},"
        "outcome_encoding:TAKE_PROFIT_1_STOP_LOSS_0"
    )


def _outcome_atr_comparison_text(rows: tuple[AtrAnatomy, ...]) -> str:
    tp = [row.atr_pips for row in rows if row.outcome == "TAKE_PROFIT"]
    sl = [row.atr_pips for row in rows if row.outcome == "STOP_LOSS"]
    tp_median = _percentile(tp, 0.50)
    sl_median = _percentile(sl, 0.50)
    difference = None
    if tp_median is not None and sl_median is not None:
        difference = sl_median - tp_median
    return (
        f"tp_atr_pips_median:{_fmt(tp_median)},"
        f"sl_atr_pips_median:{_fmt(sl_median)},"
        f"sl_minus_tp_median_pips:{_fmt(difference)},"
        f"auc_probability_sl_atr_gt_tp_atr:{_fmt(_auc(sl, tp), 6)}"
    )


def _report_slices(label: str, rows: tuple[AtrAnatomy, ...]) -> None:
    print(f"  {label}/ALL={_summary_text(rows)}")
    for direction in ("BUY", "SELL"):
        direction_rows = tuple(row for row in rows if row.direction == direction)
        print(f"  {label}/{direction}={_summary_text(direction_rows)}")
    for outcome in ("TAKE_PROFIT", "STOP_LOSS", "SESSION_END"):
        outcome_rows = tuple(row for row in rows if row.outcome == outcome)
        if outcome_rows:
            print(f"  {label}/{outcome}={_summary_text(outcome_rows)}")
            for direction in ("BUY", "SELL"):
                subset = tuple(
                    row for row in outcome_rows if row.direction == direction
                )
                print(f"  {label}/{direction}/{outcome}={_summary_text(subset)}")
    print(f"  {label}/TP_VS_SL_ATR={_outcome_atr_comparison_text(rows)}")
    print(f"  {label}/ATR_RATIO_OUTCOME_RELATION={_relation_text(rows)}")


def _cross_period_text(
    left_label: str,
    left: tuple[AtrAnatomy, ...],
    right_label: str,
    right: tuple[AtrAnatomy, ...],
) -> str:
    left_atr = [row.atr_pips for row in left]
    right_atr = [row.atr_pips for row in right]
    left_ratio = [row.sl_atr_ratio for row in left]
    right_ratio = [row.sl_atr_ratio for row in right]
    left_atr_median = _percentile(left_atr, 0.50)
    right_atr_median = _percentile(right_atr, 0.50)
    left_ratio_median = _percentile(left_ratio, 0.50)
    right_ratio_median = _percentile(right_ratio, 0.50)
    assert left_atr_median is not None and right_atr_median is not None
    assert left_ratio_median is not None and right_ratio_median is not None
    overlap_low = max(
        _percentile(left_ratio, 0.25) or 0.0,
        _percentile(right_ratio, 0.25) or 0.0,
    )
    overlap_high = min(
        _percentile(left_ratio, 0.75) or 0.0,
        _percentile(right_ratio, 0.75) or 0.0,
    )
    return (
        f"left:{left_label},right:{right_label},"
        f"atr_median_change_pct:"
        f"{100.0 * (right_atr_median / left_atr_median - 1.0):+.3f},"
        f"sl_atr_median_change_pct:"
        f"{100.0 * (right_ratio_median / left_ratio_median - 1.0):+.3f},"
        f"sl_atr_iqr_overlap:{overlap_low <= overlap_high},"
        f"sl_atr_iqr_overlap_low:{_fmt(overlap_low)},"
        f"sl_atr_iqr_overlap_high:{_fmt(overlap_high)},"
        "assessment=DESCRIPTIVE_NO_STABILITY_THRESHOLD"
    )


def main() -> int:
    results: dict[str, tuple[AtrAnatomy, ...]] = {}
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
        rows = _entry_rows(events, selected, trades)
        assert len(rows) == len(trades)
        assert all(row.atr_source_index == row.entry_index - 1 for row in rows)
        assert all(
            math.isclose(row.tp_atr_ratio, 2.0 * row.sl_atr_ratio, rel_tol=1e-12)
            for row in rows
        )
        results[window.label] = rows

    print("T104-23 ATR Structural SL Distance Anatomy result")
    print(f"  test_id={TEST_ID}")
    print("  mode=TEST_ONLY")
    print("  inventory=T104_15_IDENTITY_NORMALIZED_GREEN_8C1_FIRST_LEG")
    print("  timeframe=M15")
    print(f"  atr_length={ATR_LENGTH}")
    print("  true_range=MAX_HIGH_LOW_HIGH_PREV_CLOSE_LOW_PREV_CLOSE")
    print("  smoothing=WILDER_RMA")
    print("  rma_seed=SMA_OF_FIRST_14_TRUE_RANGES")
    print("  entry_atr_source=ENTRY_INDEX_MINUS_1_COMPLETED_M15_BAR")
    print(f"  pip_size={PIP_SIZE:.6f}")
    print(f"  fixed_sl_pips={STOP_LOSS_PIPS:.1f}")
    print(f"  baseline_tp_pips={TAKE_PROFIT_PIPS:.1f}")
    for window in WINDOWS:
        _report_slices(window.label, results[window.label])
    if len(WINDOWS) == 2:
        left_window, right_window = WINDOWS
        print(
            "  CROSS_PERIOD_STABILITY="
            + _cross_period_text(
                left_window.label,
                results[left_window.label],
                right_window.label,
                results[right_window.label],
            )
        )

    print("  correlation_scope=DESCRIPTIVE_DECISIVE_TP_VS_SL_ONLY")
    print("  outcome_used_for_selection=False")
    print("  atr_based_sl_policy_created=False")
    print("  atr_multiplier_created=False")
    print("  new_numeric_thresholds=False")
    print("  production_logic_changed=False")
    print("  candidate_f_changed=False")
    print("  entry_logic_changed=False")
    print("  exit_logic_changed=False")
    print("  sl_logic_changed=False")
    print("  tp_logic_changed=False")
    print("  completed_bars_only=True")
    print("  future_price_used=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  diagnostic_status=GREEN")
    print("T104_23_ATR_STRUCTURAL_SL_DISTANCE_ANATOMY_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
