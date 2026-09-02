# -*- coding: utf-8 -*-
"""RoadMap104 / T104-06 / 8C.7: Donchian breakout TP-release diagnostic.

TEST_ONLY runner не змінює production Candidate F, GREEN 8C.1 entry або exit.
Після T104-04..05 Donchian використовується не як ранній прямий EXIT, а як
підтвердження сильного continuation у напрямку вже відкритої позиції.

Causal state machine:
1) до favorable Donchian breakout працюють стандартні hard SL=12 / TP=24;
2) favorable breakout визначається close завершеного M15 за межею Donchian,
   побудованою тільки з попередніх 20 завершених M15 bars;
3) якщо на тому самому bar уже торкнуто hard SL/TP, protection має пріоритет,
   тому breakout не може заднім числом скасувати виконаний TP;
4) після causal favorable breakout фіксований TP вимикається з наступного bar;
5) continuation закривається на adverse Donchian midline break;
6) parallel variant після breakout також переносить hard SL у break-even.

Мета — перевірити, чи Donchian breakout доречніше використовувати для
продовження вже сильного руху, а не для спроби передбачити кожен ранній exit.
Нових tuned numeric thresholds немає. Period=20 — canonical visual reference.
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
    "run_t104_04_algorithm_workspace_donchian_structure_exit_diagnostic_"
    "2025_2026_check.py"
)
TEST_ID = "T104-06"
ROADMAP_BLOCK = "8C.7"
EPSILON = 1e-12

POLICY_RELEASE_TP_KEEP_SL = "BREAKOUT_RELEASE_TP_KEEP_ORIGINAL_SL"
POLICY_RELEASE_TP_BREAKEVEN = "BREAKOUT_RELEASE_TP_MOVE_SL_TO_BREAKEVEN"
POLICIES = (
    POLICY_RELEASE_TP_KEEP_SL,
    POLICY_RELEASE_TP_BREAKEVEN,
)


def _load_base_module() -> ModuleType:
    """Завантажити T104-04 як read-only Donchian dependency."""
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm104_t104_06_donchian_base"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()
WINDOWS = getattr(BASE, "WINDOWS")
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


@dataclass(frozen=True, slots=True)
class ContinuationResult:
    """Один paired Donchian breakout-continuation result."""

    trade: Any
    breakout_index: int | None
    exit_index: int | None
    exit_kind: str | None
    breakout_pnl: float | None


def _breakeven_stop(direction: str, entry_price: float, original_stop: float) -> float:
    """Повернути causal break-even stop без додаткового numeric buffer."""
    if direction == "BUY":
        return max(original_stop, entry_price)
    return min(original_stop, entry_price)


def _stop_touched(event: Any, direction: str, stop_price: float) -> bool:
    """Перевірити тільки stop side після переходу в continuation mode."""
    if direction == "BUY":
        return float(event.low) <= stop_price + EPSILON
    return float(event.high) >= stop_price - EPSILON


def _simulate_continuation(
    run: Any,
    candidate: Any,
    policy: str,
) -> ContinuationResult:
    """Симулювати TP release лише після causal favorable Donchian breakout."""
    assert policy in POLICIES
    entry_price, original_stop, take_price = _protection_prices(run, candidate)
    active_stop = original_stop
    continuation_mode = False
    breakout_index: int | None = None
    breakout_pnl: float | None = None
    diagnostic_exit_index: int | None = None
    diagnostic_exit_kind: str | None = None
    close_index = len(run.events) - 1
    close_price = _close_at_market(run.events[close_index], candidate.direction)
    close_reason = "SESSION_END"
    sign = _direction_sign(candidate.direction)

    for index in range(candidate.entry_index, len(run.events)):
        event = run.events[index]

        if not continuation_mode:
            protection = _protection_touched(
                event,
                candidate.direction,
                original_stop,
                take_price,
            )
            if protection is not None:
                close_index = index
                close_price = original_stop if protection == "STOP_LOSS" else take_price
                close_reason = protection
                break

            snapshot = _donchian_snapshot(run, candidate.direction, index)
            if snapshot is None or not snapshot.favorable_breakout:
                continue

            continuation_mode = True
            breakout_index = index
            breakout_close = _close_at_market(event, candidate.direction)
            breakout_pnl = (breakout_close - entry_price) * FIXED_VOLUME * sign
            if policy == POLICY_RELEASE_TP_BREAKEVEN:
                active_stop = _breakeven_stop(
                    candidate.direction,
                    entry_price,
                    original_stop,
                )
            continue

        if _stop_touched(event, candidate.direction, active_stop):
            close_index = index
            close_price = active_stop
            close_reason = (
                "STOP_LOSS"
                if abs(active_stop - original_stop) <= EPSILON
                else "BREAK_EVEN_STOP"
            )
            diagnostic_exit_kind = close_reason
            diagnostic_exit_index = index
            break

        snapshot = _donchian_snapshot(run, candidate.direction, index)
        if snapshot is None or not snapshot.adverse_midline_break:
            continue

        close_index = index
        close_price = _close_at_market(event, candidate.direction)
        close_reason = f"{policy}_ADVERSE_MIDLINE_EXIT"
        diagnostic_exit_kind = "ADVERSE_MIDLINE_EXIT"
        diagnostic_exit_index = index
        break

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
    return ContinuationResult(
        trade=trade,
        breakout_index=breakout_index,
        exit_index=diagnostic_exit_index,
        exit_kind=diagnostic_exit_kind,
        breakout_pnl=breakout_pnl,
    )


def _paired_diagnostics(
    baseline: tuple[Any, ...],
    rows: tuple[ContinuationResult, ...],
) -> dict[str, Any]:
    improved = 0
    worsened = 0
    unchanged = 0
    improved_delta = 0.0
    worsened_delta = 0.0
    baseline_outcomes_with_breakout: Counter[str] = Counter()
    variant_exit_reasons: Counter[str] = Counter()
    breakout_trades = 0
    breakout_then_improved = 0
    breakout_then_worsened = 0
    breakout_then_same = 0
    baseline_tp_with_breakout = 0
    baseline_sl_with_breakout = 0
    baseline_other_with_breakout = 0
    former_tp_improved = 0
    former_tp_worsened = 0
    former_sl_improved = 0
    former_sl_worsened = 0
    breakout_pnls: list[float] = []

    for base_trade, row in zip(baseline, rows):
        delta = row.trade.pnl - base_trade.pnl
        if delta > EPSILON:
            improved += 1
            improved_delta += delta
        elif delta < -EPSILON:
            worsened += 1
            worsened_delta += delta
        else:
            unchanged += 1

        if row.breakout_index is None:
            continue

        breakout_trades += 1
        baseline_reason = str(base_trade.close_reason)
        baseline_outcomes_with_breakout[baseline_reason] += 1
        if row.breakout_pnl is not None:
            breakout_pnls.append(row.breakout_pnl)
        variant_exit_reasons[str(row.trade.close_reason)] += 1

        if baseline_reason == "TAKE_PROFIT":
            baseline_tp_with_breakout += 1
            if delta > EPSILON:
                former_tp_improved += 1
            elif delta < -EPSILON:
                former_tp_worsened += 1
        elif baseline_reason == "STOP_LOSS":
            baseline_sl_with_breakout += 1
            if delta > EPSILON:
                former_sl_improved += 1
            elif delta < -EPSILON:
                former_sl_worsened += 1
        else:
            baseline_other_with_breakout += 1

        if delta > EPSILON:
            breakout_then_improved += 1
        elif delta < -EPSILON:
            breakout_then_worsened += 1
        else:
            breakout_then_same += 1

    return {
        "improved": improved,
        "worsened": worsened,
        "unchanged": unchanged,
        "improved_delta": improved_delta,
        "worsened_delta": worsened_delta,
        "breakout_trades": breakout_trades,
        "breakout_then_improved": breakout_then_improved,
        "breakout_then_worsened": breakout_then_worsened,
        "breakout_then_same": breakout_then_same,
        "baseline_tp_with_breakout": baseline_tp_with_breakout,
        "baseline_sl_with_breakout": baseline_sl_with_breakout,
        "baseline_other_with_breakout": baseline_other_with_breakout,
        "former_tp_improved": former_tp_improved,
        "former_tp_worsened": former_tp_worsened,
        "former_sl_improved": former_sl_improved,
        "former_sl_worsened": former_sl_worsened,
        "median_breakout_pnl": (
            statistics.median(breakout_pnls) if breakout_pnls else 0.0
        ),
        "baseline_outcomes_with_breakout": baseline_outcomes_with_breakout,
        "variant_exit_reasons": variant_exit_reasons,
    }


def _counter_text(counter: Counter[str]) -> str:
    items = (f"{key}:{value}" for key, value in sorted(counter.items()))
    return "|".join(items) or "NONE"


def _paired_text(data: dict[str, Any]) -> str:
    return (
        f"breakout_trades:{data['breakout_trades']},"
        f"baseline_tp:{data['baseline_tp_with_breakout']},"
        f"baseline_sl:{data['baseline_sl_with_breakout']},"
        f"baseline_other:{data['baseline_other_with_breakout']},"
        f"breakout_improved:{data['breakout_then_improved']},"
        f"breakout_worsened:{data['breakout_then_worsened']},"
        f"breakout_same:{data['breakout_then_same']},"
        f"former_tp_improved:{data['former_tp_improved']},"
        f"former_tp_worsened:{data['former_tp_worsened']},"
        f"former_sl_improved:{data['former_sl_improved']},"
        f"former_sl_worsened:{data['former_sl_worsened']},"
        f"median_breakout_pnl:{data['median_breakout_pnl']:+.2f},"
        f"all_improved:{data['improved']},all_worsened:{data['worsened']},"
        f"all_unchanged:{data['unchanged']},"
        f"improved_delta:{data['improved_delta']:+.2f},"
        f"worsened_delta:{data['worsened_delta']:+.2f},"
        f"baseline_breakout_outcomes:"
        f"{_counter_text(data['baseline_outcomes_with_breakout'])},"
        f"variant_exit_reasons:{_counter_text(data['variant_exit_reasons'])}"
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
    variants = {
        policy: tuple(_simulate_continuation(run, item, policy) for item in candidates)
        for policy in POLICIES
    }
    return {
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

    print("T104-06 Donchian Breakout TP Release result")
    print(f"  test_id={TEST_ID}")
    print(f"  roadmap_block={ROADMAP_BLOCK}")
    print("  mode=RM104_T104_06_8C7_DONCHIAN_BREAKOUT_TP_RELEASE_TEST_ONLY")
    print("  base_test_id=T104-05")
    print("  production_candidate_f_logic_changed=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  green_8c1_entry_frozen=True")
    print("  donchian_role=FAVORABLE_BREAKOUT_CONFIRMS_CONTINUATION")
    print("  continuation_activation=FIRST_CAUSAL_FAVORABLE_BOUNDARY_BREAKOUT")
    print("  fixed_tp_disabled_only_after_completed_breakout_bar=True")
    print("  hard_sl_tp_has_priority_on_breakout_bar=True")
    print("  continuation_exit=ADVERSE_DONCHIAN_MIDLINE_BREAK")
    print("  parallel_risk_policy=KEEP_ORIGINAL_SL|MOVE_SL_TO_BREAKEVEN")
    print(f"  donchian_period={DONCHIAN_PERIOD}")
    print("  donchian_current_bar_excluded_from_reference=True")
    print("  break_even_has_no_numeric_buffer=True")
    print("  new_numeric_tuning=False")
    print("  future_price_used_for_activation_or_exit=False")

    for window in WINDOWS:
        data = results[window.label]
        baseline = data["baseline"]
        print(
            f"  {window.label}/ENTRY="
            f"openings:{data['openings']},confirmed:{len(data['candidates'])},"
            f"invalidated:{data['invalidated']},timeout:{data['timed_out']},"
            f"aligned_at_start_not_used:{data['aligned_at_start']}"
        )
        print(f"  {window.label}/SLTP_BASELINE=" f"{_summary_text(_summary(baseline))}")
        for policy in POLICIES:
            rows = data["variants"][policy]
            trades = tuple(item.trade for item in rows)
            print(f"  {window.label}/{policy}=" f"{_summary_text(_summary(trades))}")
            print(
                f"  {window.label}/{policy}_PAIRED="
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
    print("T104_06_ALGORITHM_WORKSPACE_DONCHIAN_BREAKOUT_TP_RELEASE_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
