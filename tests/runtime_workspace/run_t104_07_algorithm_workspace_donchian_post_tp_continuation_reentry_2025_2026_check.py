# -*- coding: utf-8 -*-
"""RoadMap104 / T104-07 / 8C.8: Donchian post-TP continuation re-entry.

TEST_ONLY runner не змінює production Candidate F, GREEN 8C.1 entry або exit.
T104-06 показав, що fixed TP=24 pip не варто знімати заради continuation.
Тому перша позиція тут завжди завершується за незмінним SL=12 / TP=24.

Лише після фактично взятого TAKE_PROFIT відкривається окрема causal opportunity:
1) на completed M15 bar після/на bar TP шукаємо перший favorable Donchian breakout;
2) якщо раніше відбувся adverse Donchian midline break — continuation скасовано;
3) favorable breakout рахується від каналу з попередніх 20 completed M15 bars;
4) re-entry виконується тільки на NEXT M15 OPEN після breakout;
5) друга позиція має той самий fixed SL=12 / TP=24 і той самий volume;
6) максимум один continuation re-entry на один baseline TAKE_PROFIT.

Breakout на тому самому M15 bar, де intrabar був узятий TP, дозволений лише як
completed-bar signal для входу на НАСТУПНОМУ M15 open. Це causal і не скасовує
вже виконаний TP заднім числом.

Нових numeric thresholds/window немає. Period=20 — canonical visual reference.
Мета — перевірити, чи Donchian може додати другий прибутковий leg, не віддаючи
перші гарантовані 2R. Performance diagnostic-only і не є PASS-критерієм.
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
TEST_ID = "T104-07"
ROADMAP_BLOCK = "8C.8"
EPSILON = 1e-12


def _load_base_module() -> ModuleType:
    """Завантажити T104-04 як read-only Donchian dependency."""
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm104_t104_07_donchian_base"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()
MOMENTUM_BASE = getattr(BASE, "BASE")
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
_entry_price: Callable[..., float] = getattr(MOMENTUM_BASE, "_entry_price")


@dataclass(frozen=True, slots=True)
class ReentryResult:
    """Один post-TP continuation opportunity та optional second leg."""

    baseline_trade: Any
    tp_index: int | None
    signal_index: int | None
    reentry_trade: Any | None
    cancel_kind: str | None
    signal_on_tp_bar: bool


def _baseline_protection_index(
    run: Any, candidate: Any
) -> tuple[int | None, str | None]:
    """Знайти causal hard SL/TP baseline bar."""
    _, stop_price, take_price = _protection_prices(run, candidate)
    for index in range(candidate.entry_index, len(run.events)):
        protection = _protection_touched(
            run.events[index],
            candidate.direction,
            stop_price,
            take_price,
        )
        if protection is not None:
            return index, str(protection)
    return None, None


def _reentry_protection_prices(
    run: Any,
    candidate: Any,
    entry_index: int,
) -> tuple[float, float, float]:
    """Повторити 12/24 pip geometry GREEN 8C.1 без нових constants."""
    initial_entry, initial_stop, initial_take = _protection_prices(run, candidate)
    stop_distance = abs(initial_entry - initial_stop)
    take_distance = abs(initial_take - initial_entry)
    entry_price = _entry_price(run.events[entry_index], candidate.direction)
    if candidate.direction == "BUY":
        return (
            entry_price,
            entry_price - stop_distance,
            entry_price + take_distance,
        )
    return (
        entry_price,
        entry_price + stop_distance,
        entry_price - take_distance,
    )


def _simulate_second_leg(
    run: Any, candidate: Any, entry_index: int, signal_index: int
) -> Any:
    """Симулювати один continuation re-entry із незмінним hard SL/TP."""
    entry_price, stop_price, take_price = _reentry_protection_prices(
        run,
        candidate,
        entry_index,
    )
    close_index = len(run.events) - 1
    close_price = _close_at_market(run.events[close_index], candidate.direction)
    close_reason = "SESSION_END"

    for index in range(entry_index, len(run.events)):
        protection = _protection_touched(
            run.events[index],
            candidate.direction,
            stop_price,
            take_price,
        )
        if protection is None:
            continue
        close_index = index
        close_price = stop_price if protection == "STOP_LOSS" else take_price
        close_reason = str(protection)
        break

    sign = _direction_sign(candidate.direction)
    pnl = (close_price - entry_price) * FIXED_VOLUME * sign
    signal_timestamp = run.events[signal_index].timestamp + EXPECTED_M15_DELTA
    return TradeResult(
        direction=candidate.direction,
        start_timestamp=signal_timestamp,
        confirm_timestamp=signal_timestamp,
        entry_timestamp=run.events[entry_index].timestamp,
        close_timestamp=run.events[close_index].timestamp + EXPECTED_M15_DELTA,
        entry_price=entry_price,
        close_price=close_price,
        close_reason=close_reason,
        pnl=pnl,
        holding_bars=close_index - entry_index + 1,
    )


def _simulate_post_tp_reentry(
    run: Any,
    candidate: Any,
    baseline_trade: Any,
) -> ReentryResult:
    """Після baseline TP шукати breakout до структурного cancel."""
    tp_index, protection = _baseline_protection_index(run, candidate)
    if protection != "TAKE_PROFIT" or tp_index is None:
        return ReentryResult(
            baseline_trade=baseline_trade,
            tp_index=None,
            signal_index=None,
            reentry_trade=None,
            cancel_kind="BASELINE_NOT_TAKE_PROFIT",
            signal_on_tp_bar=False,
        )

    for index in range(tp_index, len(run.events)):
        snapshot = _donchian_snapshot(run, candidate.direction, index)
        if snapshot is None:
            continue
        if snapshot.favorable_breakout:
            entry_index = index + 1
            if entry_index >= len(run.events):
                return ReentryResult(
                    baseline_trade=baseline_trade,
                    tp_index=tp_index,
                    signal_index=index,
                    reentry_trade=None,
                    cancel_kind="NEXT_M15_OPEN_UNAVAILABLE",
                    signal_on_tp_bar=index == tp_index,
                )
            reentry_trade = _simulate_second_leg(
                run,
                candidate,
                entry_index,
                index,
            )
            return ReentryResult(
                baseline_trade=baseline_trade,
                tp_index=tp_index,
                signal_index=index,
                reentry_trade=reentry_trade,
                cancel_kind=None,
                signal_on_tp_bar=index == tp_index,
            )
        if snapshot.adverse_midline_break:
            return ReentryResult(
                baseline_trade=baseline_trade,
                tp_index=tp_index,
                signal_index=None,
                reentry_trade=None,
                cancel_kind="ADVERSE_MIDLINE_BEFORE_BREAKOUT",
                signal_on_tp_bar=False,
            )

    return ReentryResult(
        baseline_trade=baseline_trade,
        tp_index=tp_index,
        signal_index=None,
        reentry_trade=None,
        cancel_kind="SESSION_END_WITHOUT_BREAKOUT",
        signal_on_tp_bar=False,
    )


def _diagnostics(rows: tuple[ReentryResult, ...]) -> dict[str, Any]:
    tp_baseline = 0
    signals = 0
    reentries = 0
    signal_on_tp_bar = 0
    cancel_reasons: Counter[str] = Counter()
    reentry_reasons: Counter[str] = Counter()
    incremental_positive = 0
    incremental_negative = 0
    incremental_flat = 0

    for row in rows:
        if row.tp_index is not None:
            tp_baseline += 1
        if row.signal_index is not None:
            signals += 1
        if row.signal_on_tp_bar:
            signal_on_tp_bar += 1
        if row.cancel_kind is not None:
            cancel_reasons[row.cancel_kind] += 1
        if row.reentry_trade is None:
            continue
        reentries += 1
        reentry_reasons[str(row.reentry_trade.close_reason)] += 1
        if row.reentry_trade.pnl > EPSILON:
            incremental_positive += 1
        elif row.reentry_trade.pnl < -EPSILON:
            incremental_negative += 1
        else:
            incremental_flat += 1

    return {
        "tp_baseline": tp_baseline,
        "signals": signals,
        "reentries": reentries,
        "signal_on_tp_bar": signal_on_tp_bar,
        "cancel_reasons": cancel_reasons,
        "reentry_reasons": reentry_reasons,
        "incremental_positive": incremental_positive,
        "incremental_negative": incremental_negative,
        "incremental_flat": incremental_flat,
    }


def _counter_text(counter: Counter[str]) -> str:
    return (
        "|".join(f"{key}:{value}" for key, value in sorted(counter.items())) or "NONE"
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
    rows = tuple(
        _simulate_post_tp_reentry(run, candidate, baseline_trade)
        for candidate, baseline_trade in zip(candidates, baseline)
    )
    reentry_trades = tuple(
        row.reentry_trade for row in rows if row.reentry_trade is not None
    )
    return {
        "candidates": candidates,
        "openings": openings,
        "invalidated": invalidated,
        "timed_out": timed_out,
        "aligned_at_start": aligned_at_start,
        "baseline": baseline,
        "rows": rows,
        "reentry_trades": reentry_trades,
    }


def main() -> int:
    results = {window.label: _run_window(window) for window in WINDOWS}

    print("T104-07 Donchian Post-TP Continuation Re-entry result")
    print(f"  test_id={TEST_ID}")
    print(f"  roadmap_block={ROADMAP_BLOCK}")
    print("  mode=RM104_T104_07_8C8_DONCHIAN_POST_TP_CONTINUATION_REENTRY_TEST_ONLY")
    print("  base_test_id=T104-06")
    print("  production_candidate_f_logic_changed=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  green_8c1_entry_frozen=True")
    print("  first_leg_sl_tp_unchanged=True")
    print("  first_leg_stop_loss_pips=12.0")
    print("  first_leg_take_profit_pips=24.0")
    print("  reentry_eligible_only_after_baseline_take_profit=True")
    print("  reentry_signal=FIRST_FAVORABLE_DONCHIAN_BREAKOUT_BEFORE_ADVERSE_MIDLINE")
    print("  breakout_on_tp_bar_can_signal_next_m15_open=True")
    print("  reentry_policy=NEXT_M15_OPEN")
    print("  reentry_max_legs_per_baseline_tp=1")
    print("  reentry_sl_tp_same_as_green_8c1=True")
    print(f"  donchian_period={DONCHIAN_PERIOD}")
    print("  donchian_current_bar_excluded_from_reference=True")
    print("  new_numeric_tuning=False")
    print("  future_price_used_for_reentry_signal=False")

    for window in WINDOWS:
        data = results[window.label]
        baseline_summary = _summary(data["baseline"])
        reentry_summary = _summary(data["reentry_trades"])
        diagnostics = _diagnostics(data["rows"])
        combined_net = baseline_summary.net + reentry_summary.net
        print(
            f"  {window.label}/ENTRY="
            f"openings:{data['openings']},confirmed:{len(data['candidates'])},"
            f"invalidated:{data['invalidated']},timeout:{data['timed_out']},"
            f"aligned_at_start_not_used:{data['aligned_at_start']}"
        )
        print(f"  {window.label}/SLTP_BASELINE=" f"{_summary_text(baseline_summary)}")
        print(
            f"  {window.label}/DONCHIAN_POST_TP_REENTRY_LEGS="
            f"{_summary_text(reentry_summary)}"
        )
        print(
            f"  {window.label}/DONCHIAN_POST_TP_REENTRY_DIAGNOSTIC="
            f"baseline_tp:{diagnostics['tp_baseline']},"
            f"signals:{diagnostics['signals']},reentries:{diagnostics['reentries']},"
            f"signal_on_tp_bar:{diagnostics['signal_on_tp_bar']},"
            f"reentry_positive:{diagnostics['incremental_positive']},"
            f"reentry_negative:{diagnostics['incremental_negative']},"
            f"reentry_flat:{diagnostics['incremental_flat']},"
            f"cancel_reasons:{_counter_text(diagnostics['cancel_reasons'])},"
            f"reentry_exit_reasons:{_counter_text(diagnostics['reentry_reasons'])}"
        )
        print(
            f"  {window.label}/BASELINE_PLUS_REENTRY="
            f"baseline_net:{baseline_summary.net:+.2f},"
            f"incremental_reentry_net:{reentry_summary.net:+.2f},"
            f"combined_net:{combined_net:+.2f}"
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
    print("T104_07_ALGORITHM_WORKSPACE_DONCHIAN_POST_TP_CONTINUATION_REENTRY_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
