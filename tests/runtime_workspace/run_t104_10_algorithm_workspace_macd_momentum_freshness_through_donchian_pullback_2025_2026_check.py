# -*- coding: utf-8 -*-
"""RoadMap104 / T104-10 / 8C.11: MACD momentum freshness through Donchian pullback.

TEST_ONLY runner не змінює production Candidate F, GREEN 8C.1 entry або
T104-08 re-entry logic. Базою є T104-08: після baseline TAKE_PROFIT потрібні
Donchian pullback у сприятливій половині каналу та новий favorable boundary
re-breakout; re-entry виконується на NEXT M15 OPEN з незмінними SL=12 / TP=24.

T104-10 не вводить filter або numeric threshold. Для кожного фактичного
T104-08 re-entry signal він аналізує causal MACD path від completed pullback
bar до completed Donchian re-breakout bar та групує його за результатом
другого leg: TAKE_PROFIT проти STOP_LOSS.

Вимірюються directional histogram/MACD slope на pullback, перед signal і на
signal; histogram trough та відновлення після нього; довжина поточного
послідовного favorable MACD momentum streak на signal; початок цього streak
та відстань від нього до Donchian re-breakout. Усі boolean predicates
використовують лише знак відносно нуля, без tuned threshold. Performance
залишається diagnostic-only і не є PASS-критерієм.
"""

from __future__ import annotations

import importlib.util
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
    "run_t104_08_algorithm_workspace_donchian_pullback_rebreakout_reentry_"
    "2025_2026_check.py"
)
MACD_HELPER_SCRIPT_NAME = (
    "run_algorithm_workspace_alligator_opening_exit_momentum_reversal_"
    "anatomy_2025_2026_check.py"
)
TEST_ID = "T104-10"
ROADMAP_BLOCK = "8C.11"
EPSILON = 1e-12


def _load_module(file_name: str, module_name: str) -> ModuleType:
    """Завантажити sibling TEST_ONLY runner як read-only dependency."""
    file_path = Path(__file__).with_name(file_name)
    assert file_path.is_file(), file_path
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_module(BASE_SCRIPT_NAME, "rm104_t104_10_reentry_base")
MACD_HELPER = _load_module(
    MACD_HELPER_SCRIPT_NAME,
    "rm104_t104_10_macd_helper",
)
WINDOWS = getattr(BASE, "WINDOWS")
_run_base_window: Callable[..., Any] = getattr(BASE, "_run_window")
_load_indicator_run: Callable[..., Any] = getattr(BASE, "_load_indicator_run")
_directional_macd_metrics: Callable[..., Any] = getattr(
    MACD_HELPER,
    "_directional_metrics",
)


@dataclass(frozen=True, slots=True)
class MomentumFreshnessAnatomy:
    """Causal MACD path від Donchian pullback до re-breakout signal."""

    outcome: str
    pullback_to_signal_bars: int
    pullback_histogram: float
    pullback_histogram_delta: float
    pullback_macd_slope: float
    pre_signal_histogram: float
    pre_signal_histogram_delta: float
    pre_signal_macd_slope: float
    signal_histogram: float
    signal_histogram_delta: float
    signal_macd_slope: float
    signal_previous_macd_slope: float
    histogram_trough: float
    histogram_recovery_from_trough: float
    trough_to_signal_bars: int
    favorable_streak_bars: int
    favorable_streak_start_to_signal_bars: int
    signal_histogram_delta_share: float | None
    pullback_momentum_favorable: bool
    pre_signal_momentum_favorable: bool
    signal_momentum_favorable: bool


def _momentum_favorable(metrics: tuple[float, ...]) -> bool:
    """Directional MACD consensus за знаком; threshold tuning відсутній."""
    histogram, histogram_delta, macd_slope, _ = metrics
    return bool(
        histogram > EPSILON
        and histogram_delta > EPSILON
        and macd_slope > EPSILON
    )


def _anatomy(run: Any, candidate: Any, row: Any) -> MomentumFreshnessAnatomy:
    """Зняти MACD freshness path лише до completed re-breakout signal bar."""
    assert row.pullback_index is not None
    assert row.signal_index is not None
    assert row.reentry_trade is not None
    pullback_index = int(row.pullback_index)
    signal_index = int(row.signal_index)
    assert signal_index > pullback_index
    assert pullback_index >= 2

    pullback = _directional_macd_metrics(
        run,
        candidate.direction,
        pullback_index,
    )
    pre_signal = _directional_macd_metrics(
        run,
        candidate.direction,
        signal_index - 1,
    )
    signal = _directional_macd_metrics(
        run,
        candidate.direction,
        signal_index,
    )

    path_metrics = [
        _directional_macd_metrics(run, candidate.direction, index)
        for index in range(pullback_index, signal_index + 1)
    ]
    histograms = [float(metrics[0]) for metrics in path_metrics]
    trough_offset = min(range(len(histograms)), key=histograms.__getitem__)
    trough_index = pullback_index + trough_offset
    histogram_trough = histograms[trough_offset]

    favorable_streak_bars = 0
    for metrics in reversed(path_metrics):
        if not _momentum_favorable(metrics):
            break
        favorable_streak_bars += 1

    delta_share = None
    if abs(float(signal[0])) > EPSILON:
        delta_share = float(signal[1]) / abs(float(signal[0]))

    return MomentumFreshnessAnatomy(
        outcome=str(row.reentry_trade.close_reason),
        pullback_to_signal_bars=signal_index - pullback_index,
        pullback_histogram=float(pullback[0]),
        pullback_histogram_delta=float(pullback[1]),
        pullback_macd_slope=float(pullback[2]),
        pre_signal_histogram=float(pre_signal[0]),
        pre_signal_histogram_delta=float(pre_signal[1]),
        pre_signal_macd_slope=float(pre_signal[2]),
        signal_histogram=float(signal[0]),
        signal_histogram_delta=float(signal[1]),
        signal_macd_slope=float(signal[2]),
        signal_previous_macd_slope=float(signal[3]),
        histogram_trough=histogram_trough,
        histogram_recovery_from_trough=float(signal[0]) - histogram_trough,
        trough_to_signal_bars=signal_index - trough_index,
        favorable_streak_bars=favorable_streak_bars,
        favorable_streak_start_to_signal_bars=max(favorable_streak_bars - 1, 0),
        signal_histogram_delta_share=delta_share,
        pullback_momentum_favorable=_momentum_favorable(pullback),
        pre_signal_momentum_favorable=_momentum_favorable(pre_signal),
        signal_momentum_favorable=_momentum_favorable(signal),
    )


def _median(values: list[float | int]) -> float | None:
    return float(statistics.median(values)) if values else None


def _number(value: float | None, digits: int = 4) -> str:
    return "NONE" if value is None else f"{value:+.{digits}f}"


def _summary(rows: list[MomentumFreshnessAnatomy]) -> dict[str, Any]:
    return {
        "events": len(rows),
        "median_pullback_to_signal": _median(
            [row.pullback_to_signal_bars for row in rows]
        ),
        "median_pullback_hist": _median(
            [row.pullback_histogram for row in rows]
        ),
        "median_pullback_hist_delta": _median(
            [row.pullback_histogram_delta for row in rows]
        ),
        "median_pullback_macd_slope": _median(
            [row.pullback_macd_slope for row in rows]
        ),
        "median_pre_signal_hist": _median(
            [row.pre_signal_histogram for row in rows]
        ),
        "median_pre_signal_hist_delta": _median(
            [row.pre_signal_histogram_delta for row in rows]
        ),
        "median_pre_signal_macd_slope": _median(
            [row.pre_signal_macd_slope for row in rows]
        ),
        "median_signal_hist": _median([row.signal_histogram for row in rows]),
        "median_signal_hist_delta": _median(
            [row.signal_histogram_delta for row in rows]
        ),
        "median_signal_macd_slope": _median(
            [row.signal_macd_slope for row in rows]
        ),
        "median_signal_previous_macd_slope": _median(
            [row.signal_previous_macd_slope for row in rows]
        ),
        "median_histogram_trough": _median(
            [row.histogram_trough for row in rows]
        ),
        "median_histogram_recovery": _median(
            [row.histogram_recovery_from_trough for row in rows]
        ),
        "median_trough_to_signal": _median(
            [row.trough_to_signal_bars for row in rows]
        ),
        "median_favorable_streak": _median(
            [row.favorable_streak_bars for row in rows]
        ),
        "median_favorable_streak_start_to_signal": _median(
            [row.favorable_streak_start_to_signal_bars for row in rows]
        ),
        "median_signal_hist_delta_share": _median(
            [
                row.signal_histogram_delta_share
                for row in rows
                if row.signal_histogram_delta_share is not None
            ]
        ),
        "pullback_momentum_favorable": sum(
            row.pullback_momentum_favorable for row in rows
        ),
        "pre_signal_momentum_favorable": sum(
            row.pre_signal_momentum_favorable for row in rows
        ),
        "signal_momentum_favorable": sum(
            row.signal_momentum_favorable for row in rows
        ),
        "fresh_restart_on_signal": sum(
            row.signal_momentum_favorable
            and not row.pre_signal_momentum_favorable
            for row in rows
        ),
        "already_favorable_before_signal": sum(
            row.signal_momentum_favorable
            and row.pre_signal_momentum_favorable
            for row in rows
        ),
    }


def _summary_text(data: dict[str, Any]) -> str:
    return (
        f"events:{data['events']},"
        "median_pullback_to_signal_bars:"
        f"{_number(data['median_pullback_to_signal'])},"
        f"median_pullback_hist:{_number(data['median_pullback_hist'], 8)},"
        "median_pullback_hist_delta:"
        f"{_number(data['median_pullback_hist_delta'], 8)},"
        "median_pullback_macd_slope:"
        f"{_number(data['median_pullback_macd_slope'], 8)},"
        f"median_pre_signal_hist:{_number(data['median_pre_signal_hist'], 8)},"
        "median_pre_signal_hist_delta:"
        f"{_number(data['median_pre_signal_hist_delta'], 8)},"
        "median_pre_signal_macd_slope:"
        f"{_number(data['median_pre_signal_macd_slope'], 8)},"
        f"median_signal_hist:{_number(data['median_signal_hist'], 8)},"
        "median_signal_hist_delta:"
        f"{_number(data['median_signal_hist_delta'], 8)},"
        "median_signal_macd_slope:"
        f"{_number(data['median_signal_macd_slope'], 8)},"
        "median_signal_prev_macd_slope:"
        f"{_number(data['median_signal_previous_macd_slope'], 8)},"
        "median_hist_trough:"
        f"{_number(data['median_histogram_trough'], 8)},"
        "median_hist_recovery:"
        f"{_number(data['median_histogram_recovery'], 8)},"
        "median_trough_to_signal_bars:"
        f"{_number(data['median_trough_to_signal'])},"
        "median_favorable_streak_bars:"
        f"{_number(data['median_favorable_streak'])},"
        "median_favorable_streak_start_to_signal_bars:"
        f"{_number(data['median_favorable_streak_start_to_signal'])},"
        "median_signal_hist_delta_share:"
        f"{_number(data['median_signal_hist_delta_share'], 4)},"
        "pullback_momentum_favorable:"
        f"{data['pullback_momentum_favorable']},"
        "pre_signal_momentum_favorable:"
        f"{data['pre_signal_momentum_favorable']},"
        f"signal_momentum_favorable:{data['signal_momentum_favorable']},"
        f"fresh_restart_on_signal:{data['fresh_restart_on_signal']},"
        "already_favorable_before_signal:"
        f"{data['already_favorable_before_signal']}"
    )


def _run_window(window: Any) -> dict[str, Any]:
    base = _run_base_window(window)
    run = _load_indicator_run(window)
    groups: dict[str, list[MomentumFreshnessAnatomy]] = {
        "TAKE_PROFIT": [],
        "STOP_LOSS": [],
        "OTHER": [],
    }

    for candidate, row in zip(base["candidates"], base["rows"]):
        if (
            row.reentry_trade is None
            or row.pullback_index is None
            or row.signal_index is None
        ):
            continue
        anatomy = _anatomy(run, candidate, row)
        key = anatomy.outcome if anatomy.outcome in groups else "OTHER"
        groups[key].append(anatomy)

    return {
        "base": base,
        "TAKE_PROFIT": _summary(groups["TAKE_PROFIT"]),
        "STOP_LOSS": _summary(groups["STOP_LOSS"]),
        "OTHER": _summary(groups["OTHER"]),
    }


def main() -> int:
    results = {window.label: _run_window(window) for window in WINDOWS}

    print("T104-10 MACD Momentum Freshness through Donchian Pullback result")
    print(f"  test_id={TEST_ID}")
    print(f"  roadmap_block={ROADMAP_BLOCK}")
    print(
        "  mode=RM104_T104_10_8C11_MACD_MOMENTUM_FRESHNESS_THROUGH_"
        "DONCHIAN_PULLBACK_TEST_ONLY"
    )
    print("  base_test_id=T104-08")
    print("  production_candidate_f_logic_changed=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  green_8c1_entry_frozen=True")
    print("  t104_08_reentry_logic_changed=False")
    print("  anatomy_window=DONCHIAN_PULLBACK_TO_DONCHIAN_REBREAKOUT")
    print("  outcome_groups=REENTRY_TAKE_PROFIT_VS_STOP_LOSS")
    print(
        "  macd_metrics=PULLBACK_PRE_SIGNAL_SIGNAL_HISTOGRAM_SLOPE_"
        "TROUGH_RECOVERY_STREAK"
    )
    print("  favorable_momentum_definition=HIST_GT_0_AND_DELTA_GT_0_AND_SLOPE_GT_0")
    print("  structural_boolean_tests_use_zero_sign_only=True")
    print("  signal_hist_delta_share_is_diagnostic_not_threshold=True")
    print("  new_numeric_tuning=False")
    print("  future_price_used_for_momentum_anatomy=False")

    for window in WINDOWS:
        data = results[window.label]
        base = data["base"]
        print(
            f"  {window.label}/REENTRY_INVENTORY="
            f"signals:{len(base['reentry_trades'])},"
            f"take_profit:{data['TAKE_PROFIT']['events']},"
            f"stop_loss:{data['STOP_LOSS']['events']},"
            f"other:{data['OTHER']['events']}"
        )
        print(
            f"  {window.label}/TAKE_PROFIT_FRESHNESS="
            f"{_summary_text(data['TAKE_PROFIT'])}"
        )
        print(
            f"  {window.label}/STOP_LOSS_FRESHNESS="
            f"{_summary_text(data['STOP_LOSS'])}"
        )
        if data["OTHER"]["events"]:
            print(
                f"  {window.label}/OTHER_FRESHNESS="
                f"{_summary_text(data['OTHER'])}"
            )

    assert all(
        results[window.label]["TAKE_PROFIT"]["events"]
        + results[window.label]["STOP_LOSS"]["events"]
        + results[window.label]["OTHER"]["events"]
        == len(results[window.label]["base"]["reentry_trades"])
        for window in WINDOWS
    )
    print("  performance_is_diagnostic_not_pass_criterion=True")
    print("  causal_completed_m15_only=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print(
        "T104_10_ALGORITHM_WORKSPACE_MACD_MOMENTUM_FRESHNESS_THROUGH_"
        "DONCHIAN_PULLBACK_CHECK=OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
