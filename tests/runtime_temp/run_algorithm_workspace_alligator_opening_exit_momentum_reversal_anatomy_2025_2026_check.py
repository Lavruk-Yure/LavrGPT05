# -*- coding: utf-8 -*-
"""RoadMap104 / 8C.2: causal MACD momentum-reversal exit anatomy.

TEST_ONLY runner не змінює production Candidate F або GREEN 8C.1 entry.
Вхід повністю повторює 8C.1: Alligator opening expansion -> fresh
MACD 6/13/4 cross у 4-bar window -> next M15 open, SL/TP 12/24 pip.

Мета 8C.2 — не підібрати новий exit threshold, а перевірити causal
ознаки згасання MACD до повного opposite cross.
Діагностика порівнює три threshold-free event families: перше
стискання directional histogram, перший розворот directional MACD
slope та їх одночасне підтвердження. Event-и використовують
тільки поточний і попередні завершені M15 bars.
Performance diagnostic-only і не є PASS-критерієм.
"""

from __future__ import annotations

import importlib.util
import math
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BASE_SCRIPT_NAME = (
    "run_algorithm_workspace_alligator_opening_expansion_2025_2026_check.py"
)
EPSILON = 1e-12

EVENT_HISTOGRAM_CONTRACTION = "HISTOGRAM_CONTRACTION"
EVENT_MACD_SLOPE_REVERSAL = "MACD_SLOPE_REVERSAL"
EVENT_COMBINED_REVERSAL = "COMBINED_REVERSAL"
EVENTS = (
    EVENT_HISTOGRAM_CONTRACTION,
    EVENT_MACD_SLOPE_REVERSAL,
    EVENT_COMBINED_REVERSAL,
)


def _load_base_module() -> ModuleType:
    """Завантажити GREEN 8C.1 як read-only diagnostic dependency."""
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm104_8c2_alligator_opening_expansion_base"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()
CORE_BASE = getattr(BASE, "BASE")
WINDOWS = getattr(BASE, "WINDOWS")
PIP_SIZE = float(getattr(CORE_BASE, "PIP_SIZE"))
STOP_LOSS_PIPS = float(getattr(CORE_BASE, "STOP_LOSS_PIPS"))
TAKE_PROFIT_PIPS = float(getattr(CORE_BASE, "TAKE_PROFIT_PIPS"))
FIXED_VOLUME = float(getattr(CORE_BASE, "FIXED_VOLUME"))
EXPECTED_M15_DELTA = getattr(CORE_BASE, "EXPECTED_M15_DELTA")
_load_indicator_run: Callable[..., Any] = getattr(BASE, "_load_indicator_run")
_confirmed_expansion_candidates: Callable[..., Any] = getattr(
    BASE,
    "_confirmed_expansion_candidates",
)
_entry_price: Callable[..., float] = getattr(CORE_BASE, "_entry_price")
_close_at_market: Callable[..., float] = getattr(CORE_BASE, "_close_at_market")
_opposite_cross: Callable[..., bool] = getattr(CORE_BASE, "_opposite_cross")
_simulate_trade: Callable[..., Any] = getattr(BASE, "_simulate_trade")
_summary: Callable[..., Any] = getattr(BASE, "_summary")
_summary_text: Callable[..., str] = getattr(BASE, "_summary_text")
TradeResult = getattr(CORE_BASE, "TradeResult")
VariantSummary = getattr(BASE, "VariantSummary")


@dataclass(frozen=True, slots=True)
class ExitEvent:
    """Перший causal momentum-reversal event однієї позиції."""

    event_type: str
    index: int
    directional_histogram: float
    histogram_delta: float
    directional_macd_slope: float
    previous_directional_macd_slope: float


@dataclass(frozen=True, slots=True)
class VariantResult:
    """Counterfactual exit та paired relation до SL/TP baseline."""

    trade: Any
    event: ExitEvent | None
    opposite_cross_index: int | None


def _required_float(value: Any, name: str) -> float:
    assert value is not None, name
    number = float(value)
    assert math.isfinite(number), name
    return number


def _direction_sign(direction: str) -> float:
    assert direction in {"BUY", "SELL"}
    return 1.0 if direction == "BUY" else -1.0


def _directional_metrics(
    run: Any,
    direction: str,
    index: int,
) -> tuple[float, float, float, float]:
    """Повернути causal directional histogram та MACD slopes t/t-1."""
    assert index >= 2
    sign = _direction_sign(direction)
    current = run.macd[index]
    previous = run.macd[index - 1]
    older = run.macd[index - 2]
    histogram = sign * _required_float(current.histogram, "histogram")
    previous_histogram = sign * _required_float(
        previous.histogram,
        "previous_histogram",
    )
    current_macd = sign * _required_float(current.macd_value, "macd_value")
    previous_macd = sign * _required_float(previous.macd_value, "previous_macd")
    older_macd = sign * _required_float(older.macd_value, "older_macd")
    return (
        histogram,
        histogram - previous_histogram,
        current_macd - previous_macd,
        previous_macd - older_macd,
    )


def _event_matches(event_type: str, metrics: tuple[float, ...]) -> bool:
    """Threshold-free causal event predicates; 0 — лише знак, не tuning."""
    histogram, histogram_delta, macd_slope, previous_macd_slope = metrics
    still_aligned = histogram > EPSILON
    histogram_contracts = histogram_delta < -EPSILON
    macd_turned = macd_slope <= EPSILON < previous_macd_slope
    if event_type == EVENT_HISTOGRAM_CONTRACTION:
        return still_aligned and histogram_contracts
    if event_type == EVENT_MACD_SLOPE_REVERSAL:
        return still_aligned and macd_turned
    if event_type == EVENT_COMBINED_REVERSAL:
        return still_aligned and histogram_contracts and macd_turned
    raise AssertionError(event_type)


def _protection_prices(
    run: Any,
    candidate: Any,
) -> tuple[float, float, float]:
    entry_event = run.events[candidate.entry_index]
    entry_price = _entry_price(entry_event, candidate.direction)
    stop_distance = STOP_LOSS_PIPS * PIP_SIZE
    take_distance = TAKE_PROFIT_PIPS * PIP_SIZE
    if candidate.direction == "BUY":
        return entry_price, entry_price - stop_distance, entry_price + take_distance
    return entry_price, entry_price + stop_distance, entry_price - take_distance


def _protection_touched(
    event: Any,
    direction: str,
    stop_price: float,
    take_price: float,
) -> str | None:
    if direction == "BUY":
        stop_touched = event.low <= stop_price
        take_touched = event.high >= take_price
    else:
        stop_touched = event.high >= stop_price
        take_touched = event.low <= take_price
    if stop_touched:
        return "STOP_LOSS"
    if take_touched:
        return "TAKE_PROFIT"
    return None


def _first_opposite_cross_before_protection(
    run: Any,
    candidate: Any,
) -> int | None:
    _, stop_price, take_price = _protection_prices(run, candidate)
    for index in range(candidate.entry_index, len(run.events)):
        event = run.events[index]
        if (
            _protection_touched(
                event,
                candidate.direction,
                stop_price,
                take_price,
            )
            is not None
        ):
            return None
        if _opposite_cross(run.macd[index], candidate.direction):
            return index
    return None


def _simulate_event_exit(
    run: Any,
    candidate: Any,
    event_type: str,
) -> VariantResult:
    """Закрити на першому causal event після SL/TP check."""
    entry_price, stop_price, take_price = _protection_prices(run, candidate)
    close_index = len(run.events) - 1
    close_price = _close_at_market(run.events[close_index], candidate.direction)
    close_reason = "SESSION_END"
    matched_event: ExitEvent | None = None

    for index in range(candidate.entry_index, len(run.events)):
        event = run.events[index]
        protection = _protection_touched(
            event,
            candidate.direction,
            stop_price,
            take_price,
        )
        if protection is not None:
            close_index = index
            close_price = stop_price if protection == "STOP_LOSS" else take_price
            close_reason = protection
            break
        if index < 2:
            continue
        current = run.macd[index]
        if not current.warmed_up:
            continue
        metrics = _directional_metrics(run, candidate.direction, index)
        if not _event_matches(event_type, metrics):
            continue
        matched_event = ExitEvent(
            event_type=event_type,
            index=index,
            directional_histogram=metrics[0],
            histogram_delta=metrics[1],
            directional_macd_slope=metrics[2],
            previous_directional_macd_slope=metrics[3],
        )
        close_index = index
        close_price = _close_at_market(event, candidate.direction)
        close_reason = event_type
        break

    sign = _direction_sign(candidate.direction)
    pnl = (close_price - entry_price) * FIXED_VOLUME * sign
    trade = TradeResult(
        direction=candidate.direction,
        start_timestamp=candidate.start_timestamp,
        confirm_timestamp=candidate.confirm_timestamp,
        entry_timestamp=candidate.entry_timestamp,
        close_timestamp=run.events[close_index].timestamp + EXPECTED_M15_DELTA,
        entry_price=entry_price,
        close_price=close_price,
        close_reason=close_reason,
        pnl=pnl,
        holding_bars=close_index - candidate.entry_index + 1,
    )
    return VariantResult(
        trade=trade,
        event=matched_event,
        opposite_cross_index=_first_opposite_cross_before_protection(
            run,
            candidate,
        ),
    )


def _median_text(values: list[float], digits: int = 2) -> str:
    if not values:
        return "NONE"
    return f"{statistics.median(values):.{digits}f}"


def _event_diagnostics(
    baseline: tuple[Any, ...],
    variants: tuple[VariantResult, ...],
) -> dict[str, Any]:
    event_rows = [item for item in variants if item.event is not None]
    improved = 0
    worsened = 0
    unchanged = 0
    baseline_tp_with_event = 0
    baseline_sl_with_event = 0
    improved_from_sl = 0
    improved_from_tp = 0
    worsened_from_sl = 0
    worsened_from_tp = 0
    improved_delta = 0.0
    worsened_delta = 0.0
    before_opposite_cross = 0
    lead_bars: list[float] = []
    histogram_values: list[float] = []
    histogram_deltas: list[float] = []
    macd_slopes: list[float] = []

    for base_trade, variant in zip(baseline, variants):
        delta = variant.trade.pnl - base_trade.pnl
        if delta > EPSILON:
            improved += 1
            improved_delta += delta
            if base_trade.close_reason == "STOP_LOSS":
                improved_from_sl += 1
            elif base_trade.close_reason == "TAKE_PROFIT":
                improved_from_tp += 1
        elif delta < -EPSILON:
            worsened += 1
            worsened_delta += delta
            if base_trade.close_reason == "STOP_LOSS":
                worsened_from_sl += 1
            elif base_trade.close_reason == "TAKE_PROFIT":
                worsened_from_tp += 1
        else:
            unchanged += 1
        if variant.event is None:
            continue
        if base_trade.close_reason == "TAKE_PROFIT":
            baseline_tp_with_event += 1
        elif base_trade.close_reason == "STOP_LOSS":
            baseline_sl_with_event += 1
        histogram_values.append(variant.event.directional_histogram)
        histogram_deltas.append(variant.event.histogram_delta)
        macd_slopes.append(variant.event.directional_macd_slope)
        if (
            variant.opposite_cross_index is not None
            and variant.event.index < variant.opposite_cross_index
        ):
            before_opposite_cross += 1
            lead_bars.append(float(variant.opposite_cross_index - variant.event.index))

    return {
        "events": len(event_rows),
        "improved": improved,
        "worsened": worsened,
        "unchanged": unchanged,
        "baseline_tp_with_event": baseline_tp_with_event,
        "baseline_sl_with_event": baseline_sl_with_event,
        "improved_from_sl": improved_from_sl,
        "improved_from_tp": improved_from_tp,
        "worsened_from_sl": worsened_from_sl,
        "worsened_from_tp": worsened_from_tp,
        "improved_delta": improved_delta,
        "worsened_delta": worsened_delta,
        "before_opposite_cross": before_opposite_cross,
        "median_lead_bars": _median_text(lead_bars),
        "median_directional_histogram": _median_text(
            histogram_values,
            8,
        ),
        "median_histogram_delta": _median_text(histogram_deltas, 8),
        "median_directional_macd_slope": _median_text(macd_slopes, 8),
    }


def _run_window(window: Any) -> dict[str, Any]:
    print(f"  running_period={window.label}", flush=True)
    run = _load_indicator_run(window)
    candidates, openings, invalidated, timed_out, aligned_at_start = (
        _confirmed_expansion_candidates(run)
    )
    baseline = tuple(
        _simulate_trade(run, item, macd_exit_enabled=False) for item in candidates
    )
    results: dict[str, Any] = {
        "run": run,
        "candidates": candidates,
        "openings": openings,
        "invalidated": invalidated,
        "timed_out": timed_out,
        "aligned_at_start": aligned_at_start,
        "baseline": baseline,
        "baseline_summary": _summary(baseline),
    }
    for event_type in EVENTS:
        variants = tuple(
            _simulate_event_exit(run, item, event_type) for item in candidates
        )
        results[event_type] = variants
        results[f"{event_type}_summary"] = _summary(
            tuple(item.trade for item in variants)
        )
        results[f"{event_type}_diagnostics"] = _event_diagnostics(
            baseline,
            variants,
        )
    return results


def _diagnostic_text(data: dict[str, Any]) -> str:
    return (
        f"events:{data['events']},"
        f"improved:{data['improved']},worsened:{data['worsened']},"
        f"unchanged:{data['unchanged']},"
        f"baseline_tp_with_event:{data['baseline_tp_with_event']},"
        f"baseline_sl_with_event:{data['baseline_sl_with_event']},"
        f"improved_from_sl:{data['improved_from_sl']},"
        f"improved_from_tp:{data['improved_from_tp']},"
        f"worsened_from_sl:{data['worsened_from_sl']},"
        f"worsened_from_tp:{data['worsened_from_tp']},"
        f"improved_delta:{data['improved_delta']:+.2f},"
        f"worsened_delta:{data['worsened_delta']:+.2f},"
        f"before_opposite_cross:{data['before_opposite_cross']},"
        f"median_lead_bars:{data['median_lead_bars']},"
        f"median_hist:{data['median_directional_histogram']},"
        f"median_hist_delta:{data['median_histogram_delta']},"
        f"median_macd_slope:{data['median_directional_macd_slope']}"
    )


def main() -> None:
    results = [(window, _run_window(window)) for window in WINDOWS]

    print("Algorithm Workspace Alligator Opening Exit Momentum Reversal Anatomy result")
    print("  mode=RM104_8C2_EXIT_MOMENTUM_REVERSAL_ANATOMY_TEST_ONLY")
    print("  production_candidate_f_logic_changed=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  entry_pipeline_reused_from_green_8c1=True")
    print("  opening_event=FIRST_EXPANSION_FROM_CANONICAL_COMPRESSED_MOUTH")
    print("  macd_profile=6/13/4_EMA_EMA_CLOSE")
    print("  entry_policy=NEXT_M15_OPEN_AFTER_CONFIRM")
    print("  stop_loss_pips=12.0")
    print("  take_profit_pips=24.0")
    print("  exit_research_scope=MACD_EARLY_MOMENTUM_REVERSAL_ONLY")
    print("  new_numeric_tuning=False")
    print("  event_histogram_contraction=ALIGNED_HISTOGRAM_DELTA_LT_0")
    print("  event_macd_slope_reversal=PREVIOUS_SLOPE_GT_0_AND_CURRENT_SLOPE_LE_0")
    print("  event_combined=BOTH_EVENTS_ON_SAME_COMPLETED_M15_BAR")
    print("  protection_checked_before_diagnostic_exit_on_same_bar=True")
    print("  future_price_used_for_exit_event=False")

    for window, result in results:
        baseline_summary = result["baseline_summary"]
        assert isinstance(baseline_summary, VariantSummary)
        candidates = result["candidates"]
        assert len(candidates) == baseline_summary.trades
        print(
            f"  {window.label}/ENTRY="
            f"openings:{result['openings']},confirmed:{len(candidates)},"
            f"invalidated:{result['invalidated']},timeout:{result['timed_out']},"
            f"aligned_at_start_not_used:{result['aligned_at_start']}"
        )
        print(f"  {window.label}/SLTP_BASELINE=" f"{_summary_text(baseline_summary)}")
        for event_type in EVENTS:
            summary = result[f"{event_type}_summary"]
            diagnostics = result[f"{event_type}_diagnostics"]
            assert isinstance(summary, VariantSummary)
            assert isinstance(diagnostics, dict)
            print(f"  {window.label}/{event_type}=" f"{_summary_text(summary)}")
            print(
                f"  {window.label}/{event_type}_PAIRED="
                f"{_diagnostic_text(diagnostics)}"
            )

    print("  performance_is_diagnostic_not_pass_criterion=True")
    print("  causal_completed_m15_only=True")
    print("  green_8c1_entry_frozen=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print(
        "ALGORITHM_WORKSPACE_ALLIGATOR_OPENING_EXIT_MOMENTUM_REVERSAL_"
        "ANATOMY_CHECK=OK"
    )


if __name__ == "__main__":
    main()
