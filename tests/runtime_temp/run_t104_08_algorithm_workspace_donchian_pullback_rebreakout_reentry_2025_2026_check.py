# -*- coding: utf-8 -*-
"""RoadMap104 / T104-08 / 8C.9: Donchian pullback -> re-breakout re-entry.

TEST_ONLY runner не змінює production Candidate F, GREEN 8C.1 entry або exit.
T104-07 показав, що перший Donchian breakout після baseline TAKE_PROFIT
майже завжди є продовженням уже розігнаного імпульсу й дає слабкий
second leg.

Тут continuation re-entry дозволяється лише після нової causal структури:
1) перша позиція незмінно завершується fixed SL=12 / TP=24;
2) після фактично взятого TAKE_PROFIT чекаємо completed M15 pullback;
3) pullback = close повернувся всередину Donchian, але залишився у
   сприятливій половині каналу (між midline та favorable boundary);
4) adverse midline break до або після pullback скасовує opportunity;
5) після pullback потрібен НОВИЙ favorable Donchian boundary breakout;
6) re-entry виконується на NEXT M15 OPEN після re-breakout;
7) друга позиція має той самий fixed SL=12 / TP=24 і той самий volume;
8) максимум один continuation re-entry на один baseline TAKE_PROFIT.

Midline/favorable half є геометрією самого Donchian, а не tuned
threshold. Нових numeric thresholds або часових window немає. Period=20
лишається canonical visual reference. Performance diagnostic-only і не є
PASS-критерієм.
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
    "run_t104_07_algorithm_workspace_donchian_post_tp_continuation_reentry_"
    "2025_2026_check.py"
)
TEST_ID = "T104-08"
ROADMAP_BLOCK = "8C.9"
EPSILON = 1e-12


def _load_base_module() -> ModuleType:
    """Завантажити T104-07 як read-only dependency."""
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm104_t104_08_reentry_base"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()
DONCHIAN_BASE = getattr(BASE, "BASE")
WINDOWS = getattr(BASE, "WINDOWS")
DONCHIAN_PERIOD = int(getattr(BASE, "DONCHIAN_PERIOD"))
_load_indicator_run: Callable[..., Any] = getattr(BASE, "_load_indicator_run")
_confirmed_expansion_candidates: Callable[..., Any] = getattr(
    BASE,
    "_confirmed_expansion_candidates",
)
_simulate_trade: Callable[..., Any] = getattr(BASE, "_simulate_trade")
_summary: Callable[..., Any] = getattr(BASE, "_summary")
_summary_text: Callable[..., str] = getattr(BASE, "_summary_text")
_baseline_protection_index: Callable[..., Any] = getattr(
    BASE,
    "_baseline_protection_index",
)
_simulate_second_leg: Callable[..., Any] = getattr(BASE, "_simulate_second_leg")
_donchian_snapshot: Callable[..., Any] = getattr(DONCHIAN_BASE, "_donchian_snapshot")


@dataclass(frozen=True, slots=True)
class PullbackReentryResult:
    """Post-TP pullback/re-breakout opportunity та optional second leg."""

    baseline_trade: Any
    tp_index: int | None
    pullback_index: int | None
    signal_index: int | None
    reentry_trade: Any | None
    cancel_kind: str | None
    pre_pullback_breakouts: int
    pullback_channel_position: float | None


def _is_favorable_half_pullback(snapshot: Any) -> bool:
    """Close у сприятливій половині Donchian без breakout."""
    return bool(
        not snapshot.favorable_breakout
        and not snapshot.adverse_midline_break
        and snapshot.directional_channel_position >= 0.5 - EPSILON
    )


def _simulate_pullback_rebreakout_reentry(
    run: Any,
    candidate: Any,
    baseline_trade: Any,
) -> PullbackReentryResult:
    """Вимагати post-TP pullback, а потім новий breakout."""
    tp_index, protection = _baseline_protection_index(run, candidate)
    if protection != "TAKE_PROFIT" or tp_index is None:
        return PullbackReentryResult(
            baseline_trade=baseline_trade,
            tp_index=None,
            pullback_index=None,
            signal_index=None,
            reentry_trade=None,
            cancel_kind="BASELINE_NOT_TAKE_PROFIT",
            pre_pullback_breakouts=0,
            pullback_channel_position=None,
        )

    pullback_index: int | None = None
    pullback_channel_position: float | None = None
    pre_pullback_breakouts = 0

    # TP-bar виключено: після TP має виникнути нова completed-bar структура.
    for index in range(tp_index + 1, len(run.events)):
        snapshot = _donchian_snapshot(run, candidate.direction, index)
        if snapshot is None:
            continue

        if pullback_index is None:
            if snapshot.adverse_midline_break:
                return PullbackReentryResult(
                    baseline_trade=baseline_trade,
                    tp_index=tp_index,
                    pullback_index=None,
                    signal_index=None,
                    reentry_trade=None,
                    cancel_kind="ADVERSE_MIDLINE_BEFORE_PULLBACK",
                    pre_pullback_breakouts=pre_pullback_breakouts,
                    pullback_channel_position=None,
                )
            if snapshot.favorable_breakout:
                pre_pullback_breakouts += 1
                continue
            if _is_favorable_half_pullback(snapshot):
                pullback_index = index
                pullback_channel_position = float(snapshot.directional_channel_position)
            continue

        if snapshot.adverse_midline_break:
            return PullbackReentryResult(
                baseline_trade=baseline_trade,
                tp_index=tp_index,
                pullback_index=pullback_index,
                signal_index=None,
                reentry_trade=None,
                cancel_kind="ADVERSE_MIDLINE_AFTER_PULLBACK",
                pre_pullback_breakouts=pre_pullback_breakouts,
                pullback_channel_position=pullback_channel_position,
            )
        if not snapshot.favorable_breakout:
            continue

        entry_index = index + 1
        if entry_index >= len(run.events):
            return PullbackReentryResult(
                baseline_trade=baseline_trade,
                tp_index=tp_index,
                pullback_index=pullback_index,
                signal_index=index,
                reentry_trade=None,
                cancel_kind="NEXT_M15_OPEN_UNAVAILABLE",
                pre_pullback_breakouts=pre_pullback_breakouts,
                pullback_channel_position=pullback_channel_position,
            )
        reentry_trade = _simulate_second_leg(
            run,
            candidate,
            entry_index,
            index,
        )
        return PullbackReentryResult(
            baseline_trade=baseline_trade,
            tp_index=tp_index,
            pullback_index=pullback_index,
            signal_index=index,
            reentry_trade=reentry_trade,
            cancel_kind=None,
            pre_pullback_breakouts=pre_pullback_breakouts,
            pullback_channel_position=pullback_channel_position,
        )

    return PullbackReentryResult(
        baseline_trade=baseline_trade,
        tp_index=tp_index,
        pullback_index=pullback_index,
        signal_index=None,
        reentry_trade=None,
        cancel_kind="SESSION_END_WITHOUT_REBREAKOUT",
        pre_pullback_breakouts=pre_pullback_breakouts,
        pullback_channel_position=pullback_channel_position,
    )


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _number(value: float | None) -> str:
    return "NONE" if value is None else f"{value:+.4f}"


def _counter_text(counter: Counter[str]) -> str:
    text = "|".join(f"{key}:{value}" for key, value in sorted(counter.items()))
    return text or "NONE"


def _diagnostics(rows: tuple[PullbackReentryResult, ...]) -> dict[str, Any]:
    baseline_tp = 0
    pullbacks = 0
    signals = 0
    reentries = 0
    positive = 0
    negative = 0
    flat = 0
    pre_pullback_breakouts = 0
    cancel_reasons: Counter[str] = Counter()
    exit_reasons: Counter[str] = Counter()
    tp_to_pullback_bars: list[float] = []
    pullback_to_signal_bars: list[float] = []
    pullback_positions: list[float] = []

    for row in rows:
        if row.tp_index is not None:
            baseline_tp += 1
        pre_pullback_breakouts += row.pre_pullback_breakouts
        if row.pullback_index is not None:
            pullbacks += 1
            assert row.tp_index is not None
            tp_to_pullback_bars.append(float(row.pullback_index - row.tp_index))
        if row.pullback_channel_position is not None:
            pullback_positions.append(row.pullback_channel_position)
        if row.signal_index is not None:
            signals += 1
            assert row.pullback_index is not None
            pullback_to_signal_bars.append(float(row.signal_index - row.pullback_index))
        if row.cancel_kind is not None:
            cancel_reasons[row.cancel_kind] += 1
        if row.reentry_trade is None:
            continue
        reentries += 1
        exit_reasons[str(row.reentry_trade.close_reason)] += 1
        if row.reentry_trade.pnl > EPSILON:
            positive += 1
        elif row.reentry_trade.pnl < -EPSILON:
            negative += 1
        else:
            flat += 1

    return {
        "baseline_tp": baseline_tp,
        "pullbacks": pullbacks,
        "signals": signals,
        "reentries": reentries,
        "positive": positive,
        "negative": negative,
        "flat": flat,
        "pre_pullback_breakouts": pre_pullback_breakouts,
        "cancel_reasons": cancel_reasons,
        "exit_reasons": exit_reasons,
        "median_tp_to_pullback": _median(tp_to_pullback_bars),
        "median_pullback_to_signal": _median(pullback_to_signal_bars),
        "median_pullback_position": _median(pullback_positions),
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
    rows = tuple(
        _simulate_pullback_rebreakout_reentry(run, candidate, baseline_trade)
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

    print("T104-08 Donchian Pullback Re-breakout Re-entry result")
    print(f"  test_id={TEST_ID}")
    print(f"  roadmap_block={ROADMAP_BLOCK}")
    print("  mode=RM104_T104_08_8C9_DONCHIAN_PULLBACK_REBREAKOUT_REENTRY_TEST_ONLY")
    print("  base_test_id=T104-07")
    print("  production_candidate_f_logic_changed=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  green_8c1_entry_frozen=True")
    print("  first_leg_sl_tp_unchanged=True")
    print("  first_leg_stop_loss_pips=12.0")
    print("  first_leg_take_profit_pips=24.0")
    print("  reentry_eligible_only_after_baseline_take_profit=True")
    print("  tp_bar_excluded_from_pullback_and_rebreakout_search=True")
    print("  pullback_definition=INSIDE_DONCHIAN_FAVORABLE_HALF")
    print("  favorable_half_boundary=DONCHIAN_MIDLINE_STRUCTURAL_NOT_TUNED")
    print("  continuation_invalidated_by=ADVERSE_DONCHIAN_MIDLINE_BREAK")
    print("  reentry_signal=NEW_FAVORABLE_BREAKOUT_AFTER_PULLBACK")
    print("  reentry_policy=NEXT_M15_OPEN")
    print("  reentry_max_legs_per_baseline_tp=1")
    print("  reentry_sl_tp_same_as_green_8c1=True")
    print(f"  donchian_period={DONCHIAN_PERIOD}")
    print("  donchian_current_bar_excluded_from_reference=True")
    print("  new_numeric_tuning=False")
    print("  future_price_used_for_pullback_or_rebreakout=False")

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
        print(f"  {window.label}/SLTP_BASELINE={_summary_text(baseline_summary)}")
        print(
            f"  {window.label}/DONCHIAN_PULLBACK_REBREAKOUT_REENTRY_LEGS="
            f"{_summary_text(reentry_summary)}"
        )
        print(
            f"  {window.label}/DONCHIAN_PULLBACK_REBREAKOUT_DIAGNOSTIC="
            f"baseline_tp:{diagnostics['baseline_tp']},"
            f"pullbacks:{diagnostics['pullbacks']},signals:{diagnostics['signals']},"
            f"reentries:{diagnostics['reentries']},"
            f"reentry_positive:{diagnostics['positive']},"
            f"reentry_negative:{diagnostics['negative']},"
            f"reentry_flat:{diagnostics['flat']},"
            f"pre_pullback_breakouts:{diagnostics['pre_pullback_breakouts']},"
            "median_tp_to_pullback_bars:"
            f"{_number(diagnostics['median_tp_to_pullback'])},"
            "median_pullback_to_signal_bars:"
            f"{_number(diagnostics['median_pullback_to_signal'])},"
            "median_pullback_position:"
            f"{_number(diagnostics['median_pullback_position'])},"
            f"cancel_reasons:{_counter_text(diagnostics['cancel_reasons'])},"
            f"reentry_exit_reasons:{_counter_text(diagnostics['exit_reasons'])}"
        )
        print(
            f"  {window.label}/BASELINE_PLUS_PULLBACK_REENTRY="
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
    print("T104_08_ALGORITHM_WORKSPACE_DONCHIAN_PULLBACK_REBREAKOUT_REENTRY_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
