# -*- coding: utf-8 -*-
"""RoadMap104 / T104-09 / 8C.10: Alligator + MACD anatomy at Donchian re-breakout.

TEST_ONLY runner не змінює production Candidate F, GREEN 8C.1 entry або exit.
Базою є T104-08: після baseline TAKE_PROFIT потрібні Donchian pullback у
сприятливій половині каналу та новий favorable boundary re-breakout;
re-entry виконується на NEXT M15 OPEN з незмінними SL=12 / TP=24.

T104-09 не вводить нового filter або threshold. Для кожного фактично
сформованого T104-08 re-entry signal на completed M15 bar він знімає causal
snapshot Alligator і MACD та групує його за результатом другого leg:
TAKE_PROFIT проти STOP_LOSS.

Alligator: normalized opening/delta, directional center slope/delta,
Lips/Jaw gap, line order, regime/phase. MACD: directional histogram/delta
та directional MACD slopes. Додаткові boolean counts використовують лише
нуль/знак і логічні структурні відношення, а не tuned numeric thresholds.
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
    "run_t104_08_algorithm_workspace_donchian_pullback_rebreakout_reentry_"
    "2025_2026_check.py"
)
ALLIGATOR_HELPER_SCRIPT_NAME = (
    "run_t104_02_algorithm_workspace_alligator_state_at_early_macd_reversal_"
    "2025_2026_check.py"
)
MACD_HELPER_SCRIPT_NAME = (
    "run_algorithm_workspace_alligator_opening_exit_momentum_reversal_"
    "anatomy_2025_2026_check.py"
)
TEST_ID = "T104-09"
ROADMAP_BLOCK = "8C.10"
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


BASE = _load_module(BASE_SCRIPT_NAME, "rm104_t104_09_reentry_base")
ALLIGATOR_HELPER = _load_module(
    ALLIGATOR_HELPER_SCRIPT_NAME,
    "rm104_t104_09_alligator_helper",
)
MACD_HELPER = _load_module(
    MACD_HELPER_SCRIPT_NAME,
    "rm104_t104_09_macd_helper",
)
WINDOWS = getattr(BASE, "WINDOWS")
_run_base_window: Callable[..., Any] = getattr(BASE, "_run_window")
_alligator_snapshot: Callable[..., Any] = getattr(ALLIGATOR_HELPER, "_snapshot")
_directional_macd_metrics: Callable[..., Any] = getattr(
    MACD_HELPER,
    "_directional_metrics",
)


@dataclass(frozen=True, slots=True)
class RebreakoutAnatomy:
    """Causal Alligator+MACD snapshot на T104-08 re-breakout signal bar."""

    outcome: str
    opening: float
    opening_delta: float
    directional_center_slope: float
    directional_center_slope_delta: float
    directional_lips_jaw: float
    mouth_contracting: bool
    center_direction_broken: bool
    lips_jaw_broken: bool
    full_order_holds: bool
    regime_aligned: bool
    regime: str
    phase: str
    directional_histogram: float
    histogram_delta: float
    directional_macd_slope: float
    previous_directional_macd_slope: float
    histogram_aligned: bool
    histogram_expanding: bool
    macd_slope_favorable: bool
    alligator_structure_favorable: bool
    macd_momentum_favorable: bool
    alligator_and_macd_favorable: bool
    active_regime_macd_consensus: bool


def _anatomy(run: Any, candidate: Any, row: Any) -> RebreakoutAnatomy:
    """Зняти threshold-free snapshot на completed Donchian re-breakout bar."""
    assert row.signal_index is not None
    assert row.reentry_trade is not None
    index = int(row.signal_index)
    alligator = _alligator_snapshot(run, candidate.direction, index)
    histogram, histogram_delta, macd_slope, previous_macd_slope = (
        _directional_macd_metrics(run, candidate.direction, index)
    )

    histogram_aligned = histogram > EPSILON
    histogram_expanding = histogram_delta > EPSILON
    macd_slope_favorable = macd_slope > EPSILON
    alligator_structure_favorable = bool(
        alligator.full_order_holds
        and not alligator.center_direction_broken
        and not alligator.lips_jaw_broken
    )
    macd_momentum_favorable = bool(
        histogram_aligned and histogram_expanding and macd_slope_favorable
    )

    return RebreakoutAnatomy(
        outcome=str(row.reentry_trade.close_reason),
        opening=float(alligator.normalized_opening),
        opening_delta=float(alligator.normalized_opening_delta),
        directional_center_slope=float(
            alligator.directional_normalized_center_slope
        ),
        directional_center_slope_delta=float(
            alligator.directional_normalized_center_slope_delta
        ),
        directional_lips_jaw=float(alligator.directional_lips_jaw_gap),
        mouth_contracting=bool(alligator.mouth_contracting),
        center_direction_broken=bool(alligator.center_direction_broken),
        lips_jaw_broken=bool(alligator.lips_jaw_broken),
        full_order_holds=bool(alligator.full_order_holds),
        regime_aligned=bool(alligator.regime_aligned),
        regime=str(alligator.regime),
        phase=str(alligator.phase),
        directional_histogram=float(histogram),
        histogram_delta=float(histogram_delta),
        directional_macd_slope=float(macd_slope),
        previous_directional_macd_slope=float(previous_macd_slope),
        histogram_aligned=histogram_aligned,
        histogram_expanding=histogram_expanding,
        macd_slope_favorable=macd_slope_favorable,
        alligator_structure_favorable=alligator_structure_favorable,
        macd_momentum_favorable=macd_momentum_favorable,
        alligator_and_macd_favorable=(
            alligator_structure_favorable and macd_momentum_favorable
        ),
        active_regime_macd_consensus=bool(
            alligator_structure_favorable
            and alligator.regime_aligned
            and str(alligator.phase) == "ALLIGATOR_REGIME_PHASE_ACTIVE"
            and macd_momentum_favorable
        ),
    )


def _median(values: list[float]) -> float | None:
    return float(statistics.median(values)) if values else None


def _number(value: float | None, digits: int = 4) -> str:
    return "NONE" if value is None else f"{value:+.{digits}f}"


def _counter_text(counter: Counter[str]) -> str:
    if not counter:
        return "NONE"
    return "|".join(f"{key}:{counter[key]}" for key in sorted(counter))


def _summary(rows: list[RebreakoutAnatomy]) -> dict[str, Any]:
    return {
        "events": len(rows),
        "median_opening": _median([row.opening for row in rows]),
        "median_opening_delta": _median([row.opening_delta for row in rows]),
        "median_center_slope": _median(
            [row.directional_center_slope for row in rows]
        ),
        "median_center_slope_delta": _median(
            [row.directional_center_slope_delta for row in rows]
        ),
        "median_lips_jaw": _median(
            [row.directional_lips_jaw for row in rows]
        ),
        "mouth_contracting": sum(row.mouth_contracting for row in rows),
        "center_direction_broken": sum(
            row.center_direction_broken for row in rows
        ),
        "lips_jaw_broken": sum(row.lips_jaw_broken for row in rows),
        "full_order_holds": sum(row.full_order_holds for row in rows),
        "regime_aligned": sum(row.regime_aligned for row in rows),
        "regimes": Counter(row.regime for row in rows),
        "phases": Counter(row.phase for row in rows),
        "median_histogram": _median(
            [row.directional_histogram for row in rows]
        ),
        "median_histogram_delta": _median(
            [row.histogram_delta for row in rows]
        ),
        "median_macd_slope": _median(
            [row.directional_macd_slope for row in rows]
        ),
        "median_previous_macd_slope": _median(
            [row.previous_directional_macd_slope for row in rows]
        ),
        "histogram_aligned": sum(row.histogram_aligned for row in rows),
        "histogram_expanding": sum(row.histogram_expanding for row in rows),
        "macd_slope_favorable": sum(
            row.macd_slope_favorable for row in rows
        ),
        "alligator_structure_favorable": sum(
            row.alligator_structure_favorable for row in rows
        ),
        "macd_momentum_favorable": sum(
            row.macd_momentum_favorable for row in rows
        ),
        "alligator_and_macd_favorable": sum(
            row.alligator_and_macd_favorable for row in rows
        ),
        "active_regime_macd_consensus": sum(
            row.active_regime_macd_consensus for row in rows
        ),
    }


def _summary_text(data: dict[str, Any]) -> str:
    return (
        f"events:{data['events']},"
        f"median_opening:{_number(data['median_opening'])},"
        f"median_opening_delta:{_number(data['median_opening_delta'])},"
        f"median_dir_slope:{_number(data['median_center_slope'], 6)},"
        "median_dir_slope_delta:"
        f"{_number(data['median_center_slope_delta'], 6)},"
        f"median_lips_jaw:{_number(data['median_lips_jaw'])},"
        f"mouth_contracting:{data['mouth_contracting']},"
        f"center_direction_broken:{data['center_direction_broken']},"
        f"lips_jaw_broken:{data['lips_jaw_broken']},"
        f"full_order_holds:{data['full_order_holds']},"
        f"regime_aligned:{data['regime_aligned']},"
        f"regimes:{_counter_text(data['regimes'])},"
        f"phases:{_counter_text(data['phases'])},"
        f"median_hist:{_number(data['median_histogram'], 8)},"
        f"median_hist_delta:{_number(data['median_histogram_delta'], 8)},"
        f"median_macd_slope:{_number(data['median_macd_slope'], 8)},"
        "median_prev_macd_slope:"
        f"{_number(data['median_previous_macd_slope'], 8)},"
        f"histogram_aligned:{data['histogram_aligned']},"
        f"histogram_expanding:{data['histogram_expanding']},"
        f"macd_slope_favorable:{data['macd_slope_favorable']},"
        "alligator_structure_favorable:"
        f"{data['alligator_structure_favorable']},"
        f"macd_momentum_favorable:{data['macd_momentum_favorable']},"
        "alligator_and_macd_favorable:"
        f"{data['alligator_and_macd_favorable']},"
        "active_regime_macd_consensus:"
        f"{data['active_regime_macd_consensus']}"
    )


def _run_window(window: Any) -> dict[str, Any]:
    data = _run_base_window(window)
    run = data.get("run")
    if run is None:
        # T104-08 _run_window does not expose run; reload deterministic indicators.
        load_indicator_run: Callable[..., Any] = getattr(BASE, "_load_indicator_run")
        run = load_indicator_run(window)

    groups: dict[str, list[RebreakoutAnatomy]] = {
        "TAKE_PROFIT": [],
        "STOP_LOSS": [],
        "OTHER": [],
    }
    for candidate, row in zip(data["candidates"], data["rows"]):
        if row.reentry_trade is None or row.signal_index is None:
            continue
        anatomy = _anatomy(run, candidate, row)
        key = anatomy.outcome if anatomy.outcome in groups else "OTHER"
        groups[key].append(anatomy)

    return {
        "base": data,
        "TAKE_PROFIT": _summary(groups["TAKE_PROFIT"]),
        "STOP_LOSS": _summary(groups["STOP_LOSS"]),
        "OTHER": _summary(groups["OTHER"]),
    }


def main() -> int:
    results = {window.label: _run_window(window) for window in WINDOWS}

    print("T104-09 Alligator + MACD Anatomy at Donchian Re-breakout result")
    print(f"  test_id={TEST_ID}")
    print(f"  roadmap_block={ROADMAP_BLOCK}")
    print(
        "  mode=RM104_T104_09_8C10_ALLIGATOR_MACD_ANATOMY_AT_"
        "DONCHIAN_REBREAKOUT_TEST_ONLY"
    )
    print("  base_test_id=T104-08")
    print("  production_candidate_f_logic_changed=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  green_8c1_entry_frozen=True")
    print("  t104_08_reentry_logic_changed=False")
    print("  anatomy_event=COMPLETED_M15_DONCHIAN_REBREAKOUT_SIGNAL_BAR")
    print("  outcome_groups=REENTRY_TAKE_PROFIT_VS_STOP_LOSS")
    print(
        "  alligator_metrics=OPENING_DELTA_CENTER_SLOPE_LINE_ORDER_REGIME_PHASE"
    )
    print("  macd_metrics=HISTOGRAM_DELTA_MACD_SLOPE")
    print("  structural_boolean_tests_use_zero_sign_only=True")
    print("  active_regime_macd_consensus_is_structural_not_tuned=True")
    print("  new_numeric_tuning=False")
    print("  future_price_used_for_anatomy_snapshot=False")

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
            f"  {window.label}/TAKE_PROFIT_ANATOMY="
            f"{_summary_text(data['TAKE_PROFIT'])}"
        )
        print(
            f"  {window.label}/STOP_LOSS_ANATOMY="
            f"{_summary_text(data['STOP_LOSS'])}"
        )
        if data["OTHER"]["events"]:
            print(
                f"  {window.label}/OTHER_ANATOMY="
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
        "T104_09_ALGORITHM_WORKSPACE_ALLIGATOR_MACD_ANATOMY_AT_"
        "DONCHIAN_REBREAKOUT_CHECK=OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
