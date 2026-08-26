# -*- coding: utf-8 -*-
"""RoadMap104 / T104-04 / 8C.5: Donchian structure exit diagnostic.

TEST_ONLY runner не змінює production Candidate F, GREEN 8C.1 entry або exit.
Після T104-01..03 він додає цінову структуру:
canonical Donchian Channel Period=20, Shift=0. Для causal bar t
межі рахуються ТІЛЬКИ з попередніх 20 завершених M15
bars [t-20, t), тому current/future OHLC не потрапляє у channel reference.

Мета — перевірити, чи Donchian відділяє звичайний
MACD pullback від справжнього зламу структури.
Діагностика:
1) snapshot Donchian у момент early MACD reversal для baseline SL/TP;
2) paired exit variants без numeric tuning:
   - adverse Donchian midline break;
   - early histogram contraction + adverse midline break на тому самому bar;
   - early MACD slope reversal + adverse midline break на тому самому bar;
   - adverse opposite-channel boundary break.

Period=20 — поточний canonical/visual reference,
а не універсальна константа.
Performance diagnostic-only і не є PASS-критерієм.
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
    "run_algorithm_workspace_alligator_opening_exit_momentum_reversal_"
    "anatomy_2025_2026_check.py"
)
TEST_ID = "T104-04"
ROADMAP_BLOCK = "8C.5"
DONCHIAN_PERIOD = 20
EPSILON = 1e-12

VARIANT_MIDLINE = "DONCHIAN_MIDLINE_BREAK"
VARIANT_HISTOGRAM_MIDLINE = "HISTOGRAM_CONTRACTION_AND_DONCHIAN_MIDLINE"
VARIANT_SLOPE_MIDLINE = "MACD_SLOPE_REVERSAL_AND_DONCHIAN_MIDLINE"
VARIANT_OPPOSITE_BOUNDARY = "DONCHIAN_OPPOSITE_BOUNDARY_BREAK"
VARIANTS = (
    VARIANT_MIDLINE,
    VARIANT_HISTOGRAM_MIDLINE,
    VARIANT_SLOPE_MIDLINE,
    VARIANT_OPPOSITE_BOUNDARY,
)


def _load_base_module() -> ModuleType:
    """Завантажити T104-01/8C.2 як read-only diagnostic dependency."""
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm104_t104_04_momentum_base"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()
ENTRY_BASE = getattr(BASE, "BASE")
WINDOWS = getattr(BASE, "WINDOWS")
EVENT_HISTOGRAM_CONTRACTION = getattr(BASE, "EVENT_HISTOGRAM_CONTRACTION")
EVENT_MACD_SLOPE_REVERSAL = getattr(BASE, "EVENT_MACD_SLOPE_REVERSAL")
EXPECTED_M15_DELTA = getattr(BASE, "EXPECTED_M15_DELTA")
FIXED_VOLUME = float(getattr(BASE, "FIXED_VOLUME"))
TradeResult = getattr(BASE, "TradeResult")
_load_indicator_run: Callable[..., Any] = getattr(BASE, "_load_indicator_run")
_confirmed_expansion_candidates: Callable[..., Any] = getattr(
    BASE,
    "_confirmed_expansion_candidates",
)
_simulate_trade: Callable[..., Any] = getattr(BASE, "_simulate_trade")
_summary: Callable[..., Any] = getattr(BASE, "_summary")
_summary_text: Callable[..., str] = getattr(BASE, "_summary_text")
_direction_sign: Callable[..., float] = getattr(BASE, "_direction_sign")
_directional_metrics: Callable[..., Any] = getattr(BASE, "_directional_metrics")
_event_matches: Callable[..., bool] = getattr(BASE, "_event_matches")
_protection_prices: Callable[..., Any] = getattr(BASE, "_protection_prices")
_protection_touched: Callable[..., Any] = getattr(BASE, "_protection_touched")
_close_at_market: Callable[..., float] = getattr(BASE, "_close_at_market")


@dataclass(frozen=True, slots=True)
class DonchianSnapshot:
    """Canonical causal Donchian state for one completed M15 bar."""

    upper: float
    lower: float
    middle: float
    width: float
    directional_channel_position: float
    directional_midline_distance: float
    favorable_breakout: bool
    adverse_midline_break: bool
    adverse_boundary_break: bool


@dataclass(frozen=True, slots=True)
class ExitVariant:
    """Paired Donchian exit result."""

    trade: Any
    event_index: int | None


def _donchian_snapshot(run: Any, direction: str, index: int) -> DonchianSnapshot | None:
    """Розрахувати Period=20 з попередніх completed bars.

    Поточний bar у channel reference не входить.
    """
    if index < DONCHIAN_PERIOD:
        return None
    reference = run.events[index - DONCHIAN_PERIOD:index]
    assert len(reference) == DONCHIAN_PERIOD
    upper = max(float(item.high) for item in reference)
    lower = min(float(item.low) for item in reference)
    width = upper - lower
    if width <= EPSILON:
        return None
    middle = (upper + lower) / 2.0
    close = float(run.events[index].close)
    if direction == "BUY":
        channel_position = (close - lower) / width
        directional_midline_distance = (close - middle) / width
        favorable_breakout = close > upper + EPSILON
        adverse_midline_break = close < middle - EPSILON
        adverse_boundary_break = close < lower - EPSILON
    else:
        channel_position = (upper - close) / width
        directional_midline_distance = (middle - close) / width
        favorable_breakout = close < lower - EPSILON
        adverse_midline_break = close > middle + EPSILON
        adverse_boundary_break = close > upper + EPSILON
    return DonchianSnapshot(
        upper=upper,
        lower=lower,
        middle=middle,
        width=width,
        directional_channel_position=channel_position,
        directional_midline_distance=directional_midline_distance,
        favorable_breakout=favorable_breakout,
        adverse_midline_break=adverse_midline_break,
        adverse_boundary_break=adverse_boundary_break,
    )


def _early_event_matches(run: Any, direction: str, index: int, event_type: str) -> bool:
    if index < 2 or not run.macd[index].warmed_up:
        return False
    metrics = _directional_metrics(run, direction, index)
    return bool(_event_matches(event_type, metrics))


def _variant_matches(run: Any, direction: str, index: int, variant: str) -> bool:
    snapshot = _donchian_snapshot(run, direction, index)
    if snapshot is None:
        return False
    if variant == VARIANT_MIDLINE:
        return snapshot.adverse_midline_break
    if variant == VARIANT_HISTOGRAM_MIDLINE:
        return bool(
            snapshot.adverse_midline_break
            and _early_event_matches(
                run,
                direction,
                index,
                EVENT_HISTOGRAM_CONTRACTION,
            )
        )
    if variant == VARIANT_SLOPE_MIDLINE:
        return bool(
            snapshot.adverse_midline_break
            and _early_event_matches(
                run,
                direction,
                index,
                EVENT_MACD_SLOPE_REVERSAL,
            )
        )
    if variant == VARIANT_OPPOSITE_BOUNDARY:
        return snapshot.adverse_boundary_break
    raise AssertionError(variant)


def _simulate_variant(run: Any, candidate: Any, variant: str) -> ExitVariant:
    """Paired exit: hard SL/TP мають пріоритет на current bar."""
    entry_price, stop_price, take_price = _protection_prices(run, candidate)
    close_index = len(run.events) - 1
    close_price = _close_at_market(run.events[close_index], candidate.direction)
    close_reason = "SESSION_END"
    matched_index: int | None = None

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
        if not _variant_matches(run, candidate.direction, index, variant):
            continue
        close_index = index
        close_price = _close_at_market(event, candidate.direction)
        close_reason = variant
        matched_index = index
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
    return ExitVariant(trade=trade, event_index=matched_index)


def _first_early_event_index(
    run: Any,
    candidate: Any,
    event_type: str,
) -> int | None:
    """Перший early MACD event до baseline hard protection."""
    _, stop_price, take_price = _protection_prices(run, candidate)
    for index in range(candidate.entry_index, len(run.events)):
        event = run.events[index]
        if _protection_touched(
            event,
            candidate.direction,
            stop_price,
            take_price,
        ) is not None:
            return None
        if _early_event_matches(run, candidate.direction, index, event_type):
            return index
    return None


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def _number(value: float | None, digits: int = 4) -> str:
    if value is None:
        return "NONE"
    return f"{value:+.{digits}f}"


def _snapshot_groups(
    run: Any,
    candidates: tuple[Any, ...],
    baseline: tuple[Any, ...],
    event_type: str,
) -> dict[str, dict[str, Any]]:
    rows: dict[str, list[DonchianSnapshot]] = {
        "STOP_LOSS": [],
        "TAKE_PROFIT": [],
        "OTHER": [],
    }
    for candidate, baseline_trade in zip(candidates, baseline):
        event_index = _first_early_event_index(run, candidate, event_type)
        if event_index is None:
            continue
        snapshot = _donchian_snapshot(run, candidate.direction, event_index)
        if snapshot is None:
            continue
        reason = str(baseline_trade.close_reason)
        group = reason if reason in {"STOP_LOSS", "TAKE_PROFIT"} else "OTHER"
        rows[group].append(snapshot)

    result: dict[str, dict[str, Any]] = {}
    for group, group_rows in rows.items():
        result[group] = {
            "events": len(group_rows),
            "median_channel_position": _median(
                [item.directional_channel_position for item in group_rows]
            ),
            "median_midline_distance": _median(
                [item.directional_midline_distance for item in group_rows]
            ),
            "favorable_breakout": sum(item.favorable_breakout for item in group_rows),
            "adverse_midline_break": sum(
                item.adverse_midline_break for item in group_rows
            ),
            "adverse_boundary_break": sum(
                item.adverse_boundary_break for item in group_rows
            ),
        }
    return result


def _snapshot_text(data: dict[str, Any]) -> str:
    return (
        f"events:{data['events']},"
        f"median_channel_position:{_number(data['median_channel_position'])},"
        f"median_midline_distance:{_number(data['median_midline_distance'])},"
        f"favorable_breakout:{data['favorable_breakout']},"
        f"adverse_midline_break:{data['adverse_midline_break']},"
        f"adverse_boundary_break:{data['adverse_boundary_break']}"
    )


def _paired_diagnostics(
    baseline: tuple[Any, ...],
    variants: tuple[ExitVariant, ...],
) -> dict[str, Any]:
    improved = 0
    worsened = 0
    unchanged = 0
    improved_delta = 0.0
    worsened_delta = 0.0
    improved_from_sl = 0
    worsened_from_tp = 0
    events = 0
    baseline_reasons: Counter[str] = Counter()

    for base_trade, variant in zip(baseline, variants):
        delta = variant.trade.pnl - base_trade.pnl
        if variant.event_index is not None:
            events += 1
            baseline_reasons[str(base_trade.close_reason)] += 1
        if delta > EPSILON:
            improved += 1
            improved_delta += delta
            if base_trade.close_reason == "STOP_LOSS":
                improved_from_sl += 1
        elif delta < -EPSILON:
            worsened += 1
            worsened_delta += delta
            if base_trade.close_reason == "TAKE_PROFIT":
                worsened_from_tp += 1
        else:
            unchanged += 1

    return {
        "events": events,
        "improved": improved,
        "worsened": worsened,
        "unchanged": unchanged,
        "improved_delta": improved_delta,
        "worsened_delta": worsened_delta,
        "improved_from_sl": improved_from_sl,
        "worsened_from_tp": worsened_from_tp,
        "baseline_reasons": baseline_reasons,
    }


def _paired_text(data: dict[str, Any]) -> str:
    reasons = "|".join(
        f"{key}:{value}" for key, value in sorted(data["baseline_reasons"].items())
    ) or "NONE"
    return (
        f"events:{data['events']},"
        f"improved:{data['improved']},worsened:{data['worsened']},"
        f"unchanged:{data['unchanged']},"
        f"improved_delta:{data['improved_delta']:+.2f},"
        f"worsened_delta:{data['worsened_delta']:+.2f},"
        f"improved_from_sl:{data['improved_from_sl']},"
        f"worsened_from_tp:{data['worsened_from_tp']},"
        f"baseline_event_outcomes:{reasons}"
    )


def _run_window(window: Any) -> dict[str, Any]:
    print(f"  running_period={window.label}", flush=True)
    run = _load_indicator_run(window)
    candidates, openings, invalidated, timed_out, aligned_at_start = (
        _confirmed_expansion_candidates(run)
    )
    baseline = tuple(
        _simulate_trade(run, item, macd_exit_enabled=False) for item in candidates
    )
    snapshots = {
        EVENT_HISTOGRAM_CONTRACTION: _snapshot_groups(
            run,
            candidates,
            baseline,
            EVENT_HISTOGRAM_CONTRACTION,
        ),
        EVENT_MACD_SLOPE_REVERSAL: _snapshot_groups(
            run,
            candidates,
            baseline,
            EVENT_MACD_SLOPE_REVERSAL,
        ),
    }
    variants: dict[str, tuple[ExitVariant, ...]] = {
        variant: tuple(_simulate_variant(run, item, variant) for item in candidates)
        for variant in VARIANTS
    }
    return {
        "run": run,
        "candidates": candidates,
        "openings": openings,
        "invalidated": invalidated,
        "timed_out": timed_out,
        "aligned_at_start": aligned_at_start,
        "baseline": baseline,
        "snapshots": snapshots,
        "variants": variants,
    }


def main() -> int:
    results = {window.label: _run_window(window) for window in WINDOWS}

    print("T104-04 Donchian Structure Exit Diagnostic result")
    print(f"  test_id={TEST_ID}")
    print(f"  roadmap_block={ROADMAP_BLOCK}")
    print("  mode=RM104_T104_04_8C5_DONCHIAN_STRUCTURE_EXIT_DIAGNOSTIC_TEST_ONLY")
    print("  base_test_id=T104-03")
    print("  production_candidate_f_logic_changed=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  green_8c1_entry_frozen=True")
    print("  donchian_definition=CANONICAL_PREVIOUS_COMPLETED_M15_BARS")
    print(f"  donchian_period={DONCHIAN_PERIOD}")
    print("  donchian_shift=0")
    print("  current_bar_excluded_from_channel_reference=True")
    print("  period_20_is_reference_not_universal_constant=True")
    print("  new_numeric_tuning=False")
    print("  future_price_used_for_donchian_event=False")
    print("  hard_sl_tp_checked_before_diagnostic_exit_on_same_bar=True")

    for window in WINDOWS:
        data = results[window.label]
        baseline = data["baseline"]
        print(
            f"  {window.label}/ENTRY="
            f"openings:{data['openings']},confirmed:{len(data['candidates'])},"
            f"invalidated:{data['invalidated']},timeout:{data['timed_out']},"
            f"aligned_at_start_not_used:{data['aligned_at_start']}"
        )
        print(
            f"  {window.label}/SLTP_BASELINE={_summary_text(_summary(baseline))}"
        )
        for event_type, groups in data["snapshots"].items():
            for group in ("STOP_LOSS", "TAKE_PROFIT", "OTHER"):
                if groups[group]["events"] == 0:
                    continue
                print(
                    f"  {window.label}/{event_type}/DONCHIAN_{group}="
                    f"{_snapshot_text(groups[group])}"
                )
        for variant in VARIANTS:
            rows = data["variants"][variant]
            trades = tuple(item.trade for item in rows)
            print(
                f"  {window.label}/{variant}={_summary_text(_summary(trades))}"
            )
            print(
                f"  {window.label}/{variant}_PAIRED="
                f"{_paired_text(_paired_diagnostics(baseline, rows))}"
            )

    assert all(len(results[window.label]["candidates"]) > 0 for window in WINDOWS)
    assert all(
        len(results[window.label]["baseline"])
        == len(results[window.label]["candidates"])
        for window in WINDOWS
    )
    print("  performance_is_diagnostic_not_pass_criterion=True")
    print("  causal_completed_m15_only=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T104_04_ALGORITHM_WORKSPACE_DONCHIAN_STRUCTURE_EXIT_DIAGNOSTIC_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
