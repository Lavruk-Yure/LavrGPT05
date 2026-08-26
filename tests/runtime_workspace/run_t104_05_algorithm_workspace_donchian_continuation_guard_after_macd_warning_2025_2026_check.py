# -*- coding: utf-8 -*-
"""RoadMap104 / T104-05 / 8C.6: Donchian continuation guard після MACD warning.

TEST_ONLY runner не змінює production Candidate F, GREEN 8C.1 entry або exit.
Після T104-04 перевіряється не прямий Donchian exit і не same-bar conjunction,
а causal state machine:

1) early MACD reversal лише ARM-ить warning;
2) hard SL/TP завжди має пріоритет;
3) adverse Donchian midline break при armed warning -> diagnostic EXIT;
4) у continuation-guard variant favorable Donchian breakout скидає warning,
   бо price structure підтвердила продовження початкового тренду;
5) після reset новий early MACD warning може ARM-итися знову.

Порівнюються histogram contraction та MACD slope reversal.
Є parallel variant без favorable-breakout reset, щоб окремо виміряти саме користь
Donchian continuation guard. Numeric tuning не додається: Donchian Period=20
залишається canonical visual reference, midline і channel boundaries структурні.
Performance diagnostic-only і не є PASS-критерієм.
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
    "run_t104_04_algorithm_workspace_donchian_structure_exit_diagnostic_"
    "2025_2026_check.py"
)
TEST_ID = "T104-05"
ROADMAP_BLOCK = "8C.6"
EPSILON = 1e-12

POLICY_ARM_THEN_MIDLINE = "ARM_THEN_ADVERSE_MIDLINE"
POLICY_CONTINUATION_GUARD = "ARM_MIDLINE_WITH_FAVORABLE_BREAKOUT_RESET"
POLICIES = (
    POLICY_ARM_THEN_MIDLINE,
    POLICY_CONTINUATION_GUARD,
)


def _load_base_module() -> ModuleType:
    """Завантажити T104-04 як read-only diagnostic dependency."""
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm104_t104_05_donchian_base"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()
ENTRY_BASE = getattr(BASE, "ENTRY_BASE")
WINDOWS = getattr(BASE, "WINDOWS")
EVENT_HISTOGRAM_CONTRACTION = getattr(BASE, "EVENT_HISTOGRAM_CONTRACTION")
EVENT_MACD_SLOPE_REVERSAL = getattr(BASE, "EVENT_MACD_SLOPE_REVERSAL")
EVENT_TYPES = (
    EVENT_HISTOGRAM_CONTRACTION,
    EVENT_MACD_SLOPE_REVERSAL,
)
EXPECTED_M15_DELTA = getattr(BASE, "EXPECTED_M15_DELTA")
FIXED_VOLUME = float(getattr(BASE, "FIXED_VOLUME"))
DONCHIAN_PERIOD = int(getattr(BASE, "DONCHIAN_PERIOD"))
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
_protection_prices: Callable[..., Any] = getattr(BASE, "_protection_prices")
_protection_touched: Callable[..., Any] = getattr(BASE, "_protection_touched")
_close_at_market: Callable[..., float] = getattr(BASE, "_close_at_market")
_donchian_snapshot: Callable[..., Any] = getattr(BASE, "_donchian_snapshot")
_early_event_matches: Callable[..., bool] = getattr(BASE, "_early_event_matches")


@dataclass(frozen=True, slots=True)
class GuardResult:
    """Одна paired simulation для Donchian continuation guard."""

    trade: Any
    warning_arms: int
    favorable_resets: int
    diagnostic_exit_index: int | None
    first_warning_index: int | None
    first_reset_index: int | None


def _simulate_guard(
    run: Any,
    candidate: Any,
    event_type: str,
    policy: str,
) -> GuardResult:
    """Симулювати warning -> structural confirmation state machine causal-only."""
    assert policy in POLICIES
    entry_price, stop_price, take_price = _protection_prices(run, candidate)
    close_index = len(run.events) - 1
    close_price = _close_at_market(run.events[close_index], candidate.direction)
    close_reason = "SESSION_END"
    warning_armed = False
    warning_arms = 0
    favorable_resets = 0
    diagnostic_exit_index: int | None = None
    first_warning_index: int | None = None
    first_reset_index: int | None = None

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

        snapshot = _donchian_snapshot(run, candidate.direction, index)
        if snapshot is None:
            continue

        if not warning_armed and _early_event_matches(
            run,
            candidate.direction,
            index,
            event_type,
        ):
            warning_armed = True
            warning_arms += 1
            if first_warning_index is None:
                first_warning_index = index

        if not warning_armed:
            continue

        if (
            policy == POLICY_CONTINUATION_GUARD
            and snapshot.favorable_breakout
        ):
            warning_armed = False
            favorable_resets += 1
            if first_reset_index is None:
                first_reset_index = index
            continue

        if not snapshot.adverse_midline_break:
            continue

        close_index = index
        close_price = _close_at_market(event, candidate.direction)
        close_reason = f"{event_type}_{policy}"
        diagnostic_exit_index = index
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
    return GuardResult(
        trade=trade,
        warning_arms=warning_arms,
        favorable_resets=favorable_resets,
        diagnostic_exit_index=diagnostic_exit_index,
        first_warning_index=first_warning_index,
        first_reset_index=first_reset_index,
    )


def _paired_diagnostics(
    baseline: tuple[Any, ...],
    rows: tuple[GuardResult, ...],
) -> dict[str, Any]:
    improved = 0
    worsened = 0
    unchanged = 0
    improved_delta = 0.0
    worsened_delta = 0.0
    improved_from_sl = 0
    worsened_from_tp = 0
    warning_trades = 0
    exit_trades = 0
    reset_trades = 0
    total_arms = 0
    total_resets = 0
    reset_then_exit = 0
    reset_then_baseline_tp = 0
    reset_then_baseline_sl = 0
    baseline_exit_reasons: Counter[str] = Counter()

    for base_trade, row in zip(baseline, rows):
        delta = row.trade.pnl - base_trade.pnl
        total_arms += row.warning_arms
        total_resets += row.favorable_resets
        if row.warning_arms > 0:
            warning_trades += 1
        if row.diagnostic_exit_index is not None:
            exit_trades += 1
            baseline_exit_reasons[str(base_trade.close_reason)] += 1
        if row.favorable_resets > 0:
            reset_trades += 1
            if row.diagnostic_exit_index is not None:
                reset_then_exit += 1
            if base_trade.close_reason == "TAKE_PROFIT":
                reset_then_baseline_tp += 1
            elif base_trade.close_reason == "STOP_LOSS":
                reset_then_baseline_sl += 1

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
        "warning_trades": warning_trades,
        "exit_trades": exit_trades,
        "reset_trades": reset_trades,
        "total_arms": total_arms,
        "total_resets": total_resets,
        "reset_then_exit": reset_then_exit,
        "reset_then_baseline_tp": reset_then_baseline_tp,
        "reset_then_baseline_sl": reset_then_baseline_sl,
        "improved": improved,
        "worsened": worsened,
        "unchanged": unchanged,
        "improved_delta": improved_delta,
        "worsened_delta": worsened_delta,
        "improved_from_sl": improved_from_sl,
        "worsened_from_tp": worsened_from_tp,
        "baseline_exit_reasons": baseline_exit_reasons,
    }


def _paired_text(data: dict[str, Any]) -> str:
    reasons = "|".join(
        f"{key}:{value}"
        for key, value in sorted(data["baseline_exit_reasons"].items())
    ) or "NONE"
    return (
        f"warning_trades:{data['warning_trades']},"
        f"exit_trades:{data['exit_trades']},"
        f"reset_trades:{data['reset_trades']},"
        f"arms:{data['total_arms']},resets:{data['total_resets']},"
        f"reset_then_exit:{data['reset_then_exit']},"
        f"reset_baseline_tp:{data['reset_then_baseline_tp']},"
        f"reset_baseline_sl:{data['reset_then_baseline_sl']},"
        f"improved:{data['improved']},worsened:{data['worsened']},"
        f"unchanged:{data['unchanged']},"
        f"improved_delta:{data['improved_delta']:+.2f},"
        f"worsened_delta:{data['worsened_delta']:+.2f},"
        f"improved_from_sl:{data['improved_from_sl']},"
        f"worsened_from_tp:{data['worsened_from_tp']},"
        f"baseline_exit_outcomes:{reasons}"
    )


def _guard_benefit(
    plain: tuple[GuardResult, ...],
    guarded: tuple[GuardResult, ...],
) -> dict[str, Any]:
    better = 0
    worse = 0
    same = 0
    better_delta = 0.0
    worse_delta = 0.0
    exits_avoided = 0
    exits_delayed_or_changed = 0

    for plain_row, guarded_row in zip(plain, guarded):
        delta = guarded_row.trade.pnl - plain_row.trade.pnl
        if delta > EPSILON:
            better += 1
            better_delta += delta
        elif delta < -EPSILON:
            worse += 1
            worse_delta += delta
        else:
            same += 1
        if (
            plain_row.diagnostic_exit_index is not None
            and guarded_row.diagnostic_exit_index is None
        ):
            exits_avoided += 1
        elif (
            plain_row.diagnostic_exit_index is not None
            and guarded_row.diagnostic_exit_index is not None
            and plain_row.diagnostic_exit_index != guarded_row.diagnostic_exit_index
        ):
            exits_delayed_or_changed += 1

    return {
        "better": better,
        "worse": worse,
        "same": same,
        "better_delta": better_delta,
        "worse_delta": worse_delta,
        "exits_avoided": exits_avoided,
        "exits_delayed_or_changed": exits_delayed_or_changed,
    }


def _guard_benefit_text(data: dict[str, Any]) -> str:
    return (
        f"better:{data['better']},worse:{data['worse']},same:{data['same']},"
        f"better_delta:{data['better_delta']:+.2f},"
        f"worse_delta:{data['worse_delta']:+.2f},"
        f"exits_avoided:{data['exits_avoided']},"
        f"exits_delayed_or_changed:{data['exits_delayed_or_changed']}"
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
    variants: dict[tuple[str, str], tuple[GuardResult, ...]] = {}
    for event_type in EVENT_TYPES:
        for policy in POLICIES:
            variants[(event_type, policy)] = tuple(
                _simulate_guard(run, item, event_type, policy)
                for item in candidates
            )
    return {
        "run": run,
        "candidates": candidates,
        "openings": openings,
        "invalidated": invalidated,
        "timed_out": timed_out,
        "aligned_at_start": aligned_at_start,
        "baseline": baseline,
        "variants": variants,
    }


def main() -> int:
    results = {window.label: _run_window(window) for window in WINDOWS}

    print("T104-05 Donchian Continuation Guard after MACD Warning result")
    print(f"  test_id={TEST_ID}")
    print(f"  roadmap_block={ROADMAP_BLOCK}")
    print("  mode=RM104_T104_05_8C6_DONCHIAN_CONTINUATION_GUARD_TEST_ONLY")
    print("  base_test_id=T104-04")
    print("  production_candidate_f_logic_changed=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  green_8c1_entry_frozen=True")
    print("  macd_role=EARLY_WARNING_ONLY")
    print("  warning_sources=HISTOGRAM_CONTRACTION|MACD_SLOPE_REVERSAL")
    print("  donchian_role=STRUCTURAL_CONFIRMATION_AND_CONTINUATION_RESET")
    print("  exit_confirmation=ARMED_WARNING_THEN_ADVERSE_MIDLINE_BREAK")
    print("  continuation_reset=FAVORABLE_DONCHIAN_BOUNDARY_BREAKOUT")
    print(f"  donchian_period={DONCHIAN_PERIOD}")
    print("  donchian_current_bar_excluded_from_reference=True")
    print("  favorable_breakout_reset_is_structural_not_numeric_tuning=True")
    print("  new_numeric_tuning=False")
    print("  hard_sl_tp_checked_before_warning_or_exit_on_same_bar=True")
    print("  future_price_used_for_warning_reset_or_exit=False")

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
        for event_type in EVENT_TYPES:
            plain = data["variants"][(event_type, POLICY_ARM_THEN_MIDLINE)]
            guarded = data["variants"][(event_type, POLICY_CONTINUATION_GUARD)]
            for policy, rows in (
                (POLICY_ARM_THEN_MIDLINE, plain),
                (POLICY_CONTINUATION_GUARD, guarded),
            ):
                trades = tuple(item.trade for item in rows)
                print(
                    f"  {window.label}/{event_type}/{policy}="
                    f"{_summary_text(_summary(trades))}"
                )
                print(
                    f"  {window.label}/{event_type}/{policy}_PAIRED="
                    f"{_paired_text(_paired_diagnostics(baseline, rows))}"
                )
            print(
                f"  {window.label}/{event_type}/CONTINUATION_GUARD_VS_PLAIN="
                f"{_guard_benefit_text(_guard_benefit(plain, guarded))}"
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
    print("T104_05_ALGORITHM_WORKSPACE_DONCHIAN_CONTINUATION_GUARD_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
