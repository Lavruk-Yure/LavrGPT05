# -*- coding: utf-8 -*-
"""RoadMap104 / T104-11 / 8C.12: MACD relative restart discriminator.

TEST_ONLY runner не змінює production Candidate F, GREEN 8C.1 entry або
T104-08 Donchian pullback/re-breakout re-entry logic. Базою є фактичні
T104-08 re-entry candidates; T104-10 показав, що абсолютний MACD level сам
по собі слабкий discriminator, але відносна сила нового прискорення після
pullback має однаковий напрям у 2025 і 2026.

T104-11 перевіряє три causal structural predicates без tuned numeric
thresholds:
1) FRESH_RESTART_ONLY: favorable MACD momentum з'явився саме на signal bar;
2) DOMINANT_ACCELERATION_ONLY: directional histogram delta на signal bar
   більший за абсолютний directional histogram цього ж bar;
3) FRESH_RESTART_AND_DOMINANT_ACCELERATION: обидві умови разом.

Порівняння delta > abs(histogram) є відносним structural relation, а не
підібраним коефіцієнтом: воно означає, що приріст поточного bar більший за
вже накопичений directional histogram level. First leg, Donchian pullback,
re-breakout, NEXT M15 OPEN і SL=12 / TP=24 залишаються незмінними.
Performance diagnostic-only і не є PASS-критерієм.
"""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BASE_SCRIPT_NAME = (
    "run_t104_10_algorithm_workspace_macd_momentum_freshness_through_"
    "donchian_pullback_2025_2026_check.py"
)
TEST_ID = "T104-11"
ROADMAP_BLOCK = "8C.12"
EPSILON = 1e-12


def _load_base_module() -> ModuleType:
    """Завантажити T104-10 як read-only dependency."""
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm104_t104_11_freshness_base"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()
WINDOWS = getattr(BASE, "WINDOWS")
_run_base_window: Callable[..., Any] = getattr(BASE, "_run_base_window")
_load_indicator_run: Callable[..., Any] = getattr(BASE, "_load_indicator_run")
_anatomy: Callable[..., Any] = getattr(BASE, "_anatomy")
REENTRY_BASE = getattr(BASE, "BASE")
_summary: Callable[..., Any] = getattr(REENTRY_BASE, "_summary")
_summary_text: Callable[..., str] = getattr(REENTRY_BASE, "_summary_text")


def _fresh_restart(anatomy: Any) -> bool:
    """Favorable momentum виник саме на causal Donchian signal bar."""
    return bool(
        anatomy.signal_momentum_favorable and not anatomy.pre_signal_momentum_favorable
    )


def _dominant_acceleration(anatomy: Any) -> bool:
    """Новий histogram increment домінує над накопиченим histogram level."""
    return bool(
        anatomy.signal_momentum_favorable
        and anatomy.signal_histogram_delta > abs(anatomy.signal_histogram) + EPSILON
    )


def _selected_summary(trades: list[Any]) -> Any:
    return _summary(tuple(trades))


def _outcome_text(counter: Counter[str]) -> str:
    if not counter:
        return "NONE"
    return "|".join(f"{key}:{counter[key]}" for key in sorted(counter))


def _variant(
    rows: list[tuple[Any, Any]], predicate: Callable[[Any], bool]
) -> dict[str, Any]:
    selected_trades: list[Any] = []
    selected_outcomes: Counter[str] = Counter()
    rejected_outcomes: Counter[str] = Counter()

    for anatomy, trade in rows:
        outcome = str(trade.close_reason)
        if predicate(anatomy):
            selected_trades.append(trade)
            selected_outcomes[outcome] += 1
        else:
            rejected_outcomes[outcome] += 1

    return {
        "summary": _selected_summary(selected_trades),
        "selected": len(selected_trades),
        "rejected": len(rows) - len(selected_trades),
        "selected_outcomes": selected_outcomes,
        "rejected_outcomes": rejected_outcomes,
    }


def _run_window(window: Any) -> dict[str, Any]:
    base = _run_base_window(window)
    run = _load_indicator_run(window)
    rows: list[tuple[Any, Any]] = []

    for candidate, row in zip(base["candidates"], base["rows"]):
        if (
            row.reentry_trade is None
            or row.pullback_index is None
            or row.signal_index is None
        ):
            continue
        rows.append((_anatomy(run, candidate, row), row.reentry_trade))

    return {
        "base": base,
        "rows": rows,
        "fresh_restart": _variant(rows, _fresh_restart),
        "dominant_acceleration": _variant(rows, _dominant_acceleration),
        "combined": _variant(
            rows,
            lambda anatomy: _fresh_restart(anatomy) and _dominant_acceleration(anatomy),
        ),
    }


def _variant_text(data: dict[str, Any], baseline_net: float) -> str:
    summary = data["summary"]
    return (
        f"selected:{data['selected']},rejected:{data['rejected']},"
        f"selected_outcomes:{_outcome_text(data['selected_outcomes'])},"
        f"rejected_outcomes:{_outcome_text(data['rejected_outcomes'])},"
        f"legs:{_summary_text(summary)},"
        f"incremental_net:{summary.net:+.2f},"
        f"combined_net:{baseline_net + summary.net:+.2f}"
    )


def main() -> int:
    results = {window.label: _run_window(window) for window in WINDOWS}

    print("T104-11 MACD Relative Restart Discriminator result")
    print(f"  test_id={TEST_ID}")
    print(f"  roadmap_block={ROADMAP_BLOCK}")
    print("  mode=RM104_T104_11_8C12_MACD_RELATIVE_RESTART_DISCRIMINATOR_" "TEST_ONLY")
    print("  base_test_id=T104-10")
    print("  production_candidate_f_logic_changed=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  green_8c1_entry_frozen=True")
    print("  t104_08_reentry_logic_changed=False")
    print("  first_leg_sl_tp_unchanged=True")
    print("  donchian_pullback_rebreakout_unchanged=True")
    print("  discriminator_scope=SECOND_LEG_REENTRY_PERMISSION_ONLY")
    print(
        "  fresh_restart_definition=SIGNAL_MOMENTUM_FAVORABLE_AND_PRE_SIGNAL_"
        "NOT_FAVORABLE"
    )
    print("  dominant_acceleration_definition=SIGNAL_HIST_DELTA_GT_ABS_SIGNAL_HIST")
    print("  dominant_acceleration_ratio_constant_used=False")
    print("  new_numeric_tuning=False")
    print("  future_price_used_for_discriminator=False")

    combined_positive_both = True
    combined_improves_unfiltered_both = True

    for window in WINDOWS:
        data = results[window.label]
        base = data["base"]
        baseline_summary = _summary(base["baseline"])
        unfiltered_summary = _summary(base["reentry_trades"])
        combined_summary = data["combined"]["summary"]
        combined_positive_both = combined_positive_both and combined_summary.net > 0
        combined_improves_unfiltered_both = (
            combined_improves_unfiltered_both
            and combined_summary.net > unfiltered_summary.net
        )

        print(
            f"  {window.label}/INVENTORY="
            f"baseline_trades:{len(base['baseline'])},"
            f"unfiltered_reentries:{len(base['reentry_trades'])},"
            f"baseline_net:{baseline_summary.net:+.2f},"
            f"unfiltered_reentry_net:{unfiltered_summary.net:+.2f},"
            f"unfiltered_combined_net:"
            f"{baseline_summary.net + unfiltered_summary.net:+.2f}"
        )
        print(
            f"  {window.label}/FRESH_RESTART_ONLY="
            f"{_variant_text(data['fresh_restart'], baseline_summary.net)}"
        )
        print(
            f"  {window.label}/DOMINANT_ACCELERATION_ONLY="
            f"{_variant_text(data['dominant_acceleration'], baseline_summary.net)}"
        )
        print(
            f"  {window.label}/FRESH_RESTART_AND_DOMINANT_ACCELERATION="
            f"{_variant_text(data['combined'], baseline_summary.net)}"
        )

    print(
        "  combined_incremental_net_positive_both_periods=" f"{combined_positive_both}"
    )
    print(
        "  combined_improves_unfiltered_reentry_net_both_periods="
        f"{combined_improves_unfiltered_both}"
    )
    assert all(
        len(results[window.label]["rows"])
        == len(results[window.label]["base"]["reentry_trades"])
        for window in WINDOWS
    )
    print("  performance_is_diagnostic_not_pass_criterion=True")
    print("  causal_completed_m15_only=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T104_11_ALGORITHM_WORKSPACE_MACD_RELATIVE_RESTART_DISCRIMINATOR_" "CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
