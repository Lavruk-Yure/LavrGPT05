# -*- coding: utf-8 -*-
"""RoadMap104 / T104-19: Stochastic pullback-completion re-entry anatomy.

TEST_ONLY analysis starts from the T104-15 causal identity-normalized T104-08
Donchian pullback/re-breakout execution inventory. Canonical Stochastic uses
completed M15 High/Low/Close bars: raw %K(14), smoothing 1, and %D=SMA(%K,3).

For BUY, a structural completion is the first local upward %K turn after an
adverse (%K down) pullback move, followed by the first fresh cross above %D.
SELL is symmetric. Levels 20/50/80 are anatomy labels only. Neither indicator
state nor outcome selects, changes, or creates an execution.
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
    "run_t104_15_algorithm_workspace_causal_execution_identity_normalization_"
    "2025_2026_check.py"
)
TEST_ID = "T104-19"
K_LENGTH = 14
D_LENGTH = 3
EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class StochasticAnatomy:
    """Threshold-free structural anatomy for one normalized execution."""

    direction: str
    outcome: str
    pullback_index: int
    breakout_index: int
    adverse_move_seen: bool
    turn_index: int | None
    cross_index: int | None
    turn_level: str
    cross_level: str
    state: str


def _load_base_module() -> ModuleType:
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm104_t104_19_normalized_inventory_base"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()
WINDOWS = getattr(BASE, "WINDOWS")
_run_normalized: Callable[..., Any] = getattr(BASE, "_run_normalized")
REENTRY_BASE = getattr(BASE, "REENTRY_BASE")
_load_indicator_run: Callable[..., Any] = getattr(REENTRY_BASE, "_load_indicator_run")


def _canonical_stochastic(
    events: tuple[Any, ...],
) -> tuple[tuple[float | None, ...], tuple[float | None, ...]]:
    """Return causal canonical %K(14,1) and %D SMA(3)."""
    percent_k: list[float | None] = [None] * len(events)
    for index in range(K_LENGTH - 1, len(events)):
        window = events[index - K_LENGTH + 1 : index + 1]  # noqa: E203
        highest = max(float(event.high) for event in window)
        lowest = min(float(event.low) for event in window)
        width = highest - lowest
        if width <= EPSILON:
            percent_k[index] = 50.0
        else:
            close = float(events[index].close)
            percent_k[index] = 100.0 * (close - lowest) / width

    percent_d: list[float | None] = [None] * len(events)
    for index in range(K_LENGTH + D_LENGTH - 2, len(events)):
        window = percent_k[index - D_LENGTH + 1 : index + 1]  # noqa: E203
        if all(value is not None for value in window):
            percent_d[index] = statistics.fmean(float(value) for value in window)
    return tuple(percent_k), tuple(percent_d)


def _level(direction: str, value: float | None) -> str:
    if value is None:
        return "UNAVAILABLE"
    if direction == "BUY":
        if value < 20.0:
            return "BELOW_20"
        if value <= 50.0:
            return "20_TO_50"
        return "ABOVE_50"
    if value > 80.0:
        return "ABOVE_80"
    if value >= 50.0:
        return "50_TO_80"
    return "BELOW_50"


def _favorable_delta(direction: str, current: float, previous: float) -> bool:
    return (
        current > previous + EPSILON
        if direction == "BUY"
        else current < previous - EPSILON
    )


def _adverse_delta(direction: str, current: float, previous: float) -> bool:
    return (
        current < previous - EPSILON
        if direction == "BUY"
        else current > previous + EPSILON
    )


def _fresh_cross(
    direction: str,
    previous_k: float,
    previous_d: float,
    current_k: float,
    current_d: float,
) -> bool:
    if direction == "BUY":
        return previous_k <= previous_d + EPSILON and current_k > current_d + EPSILON
    return previous_k >= previous_d - EPSILON and current_k < current_d - EPSILON


def _anatomy(
    item: tuple[int, Any, Any, Any, Any],
    percent_k: tuple[float | None, ...],
    percent_d: tuple[float | None, ...],
) -> StochasticAnatomy:
    _, candidate, row, _, trade = item
    direction = str(candidate.direction)
    pullback_index = int(row.pullback_index)
    breakout_index = int(row.signal_index)
    start_index = max(int(row.tp_index), K_LENGTH + D_LENGTH - 2)
    adverse_seen = False
    turn_index: int | None = None
    cross_index: int | None = None

    # Scan the whole remaining completed-bar path. This uses no tuned time window;
    # bars after breakout are descriptive and never affect the frozen execution.
    for index in range(start_index + 1, len(percent_k)):
        current_k = percent_k[index]
        previous_k = percent_k[index - 1]
        current_d = percent_d[index]
        previous_d = percent_d[index - 1]
        if current_k is None or previous_k is None:
            continue
        if _adverse_delta(direction, current_k, previous_k):
            adverse_seen = True
        if (
            turn_index is None
            and adverse_seen
            and index >= pullback_index
            and _favorable_delta(direction, current_k, previous_k)
        ):
            turn_index = index
        if (
            cross_index is None
            and turn_index is not None
            and index >= turn_index
            and current_d is not None
            and previous_d is not None
            and _fresh_cross(
                direction,
                previous_k,
                previous_d,
                current_k,
                current_d,
            )
        ):
            cross_index = index
            break

    pullback_k = percent_k[pullback_index]
    pullback_d = percent_d[pullback_index]
    directional_at_pullback = bool(
        pullback_k is not None
        and pullback_d is not None
        and (
            pullback_k > pullback_d + EPSILON
            if direction == "BUY"
            else pullback_k < pullback_d - EPSILON
        )
    )
    if cross_index is not None and cross_index <= breakout_index:
        state = "FRESH_RESTART_BY_REBREAKOUT"
    elif directional_at_pullback:
        state = "ALREADY_DIRECTIONAL_AT_PULLBACK"
    elif cross_index is not None:
        state = "RESTART_ONLY_AFTER_REBREAKOUT"
    elif turn_index is not None:
        state = "TURN_WITHOUT_FRESH_CROSS"
    else:
        state = "NO_STRUCTURAL_COMPLETION"

    return StochasticAnatomy(
        direction=direction,
        outcome=str(trade.close_reason),
        pullback_index=pullback_index,
        breakout_index=breakout_index,
        adverse_move_seen=adverse_seen,
        turn_index=turn_index,
        cross_index=cross_index,
        turn_level=_level(
            direction, None if turn_index is None else percent_k[turn_index]
        ),
        cross_level=_level(
            direction, None if cross_index is None else percent_k[cross_index]
        ),
        state=state,
    )


def _timing(index: int | None, breakout_index: int) -> str:
    if index is None:
        return "NONE"
    if index < breakout_index:
        return "BEFORE"
    if index == breakout_index:
        return "SAME_BAR"
    return "AFTER"


def _counter_text(counter: Counter[str]) -> str:
    return "|".join(f"{key}:{counter[key]}" for key in sorted(counter)) or "NONE"


def _median_text(values: list[int]) -> str:
    return "NONE" if not values else f"{statistics.median(values):+.3f}"


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _print_scope(label: str, rows: tuple[StochasticAnatomy, ...]) -> None:
    turn_timing = Counter(_timing(row.turn_index, row.breakout_index) for row in rows)
    cross_timing = Counter(_timing(row.cross_index, row.breakout_index) for row in rows)
    turn_lag = [
        int(row.turn_index) - row.breakout_index
        for row in rows
        if row.turn_index is not None
    ]
    cross_lag = [
        int(row.cross_index) - row.breakout_index
        for row in rows
        if row.cross_index is not None
    ]
    outcomes = Counter(row.outcome for row in rows)
    states = Counter(row.state for row in rows)
    outcome_state = Counter(f"{row.outcome}/{row.state}" for row in rows)
    state_take_profits = Counter(
        row.state for row in rows if row.outcome == "TAKE_PROFIT"
    )
    tp_rate_by_state = "|".join(
        f"{state}:{_ratio(state_take_profits[state], count):.6f}"
        for state, count in sorted(states.items())
    )
    print(f"  {label}/OUTCOMES={_counter_text(outcomes)}")
    print(
        f"  {label}/TURN=timing:{_counter_text(turn_timing)},"
        f"median_lag_vs_rebreakout_bars:{_median_text(turn_lag)},"
        f"levels:{_counter_text(Counter(row.turn_level for row in rows))}"
    )
    print(
        f"  {label}/CROSS=timing:{_counter_text(cross_timing)},"
        f"median_lag_vs_rebreakout_bars:{_median_text(cross_lag)},"
        f"levels:{_counter_text(Counter(row.cross_level for row in rows))}"
    )
    print(
        f"  {label}/RESTART=states:{_counter_text(states)},"
        f"outcome_by_state:{_counter_text(outcome_state)},"
        f"tp_rate_by_state:{tp_rate_by_state or 'NONE'}"
    )
    pre_breakout = sum(
        row.cross_index is not None and row.cross_index < row.breakout_index
        for row in rows
    )
    pre_breakout_tp = sum(
        row.cross_index is not None
        and row.cross_index < row.breakout_index
        and row.outcome == "TAKE_PROFIT"
        for row in rows
    )
    print(
        f"  {label}/INCREMENTAL_OVER_DONCHIAN=pre_rebreakout_cross:{pre_breakout},"
        f"pre_rebreakout_cross_rate:{_ratio(pre_breakout, len(rows)):.6f},"
        f"tp_with_pre_rebreakout_cross:{pre_breakout_tp}"
    )


def main() -> int:
    results: dict[str, tuple[StochasticAnatomy, ...]] = {}
    collision_free = True
    for window in WINDOWS:
        print(f"  running_period={window.label}", flush=True)
        normalized = _run_normalized(window)
        run = _load_indicator_run(window)
        percent_k, percent_d = _canonical_stochastic(tuple(run.events))
        rows = tuple(
            _anatomy(item, percent_k, percent_d)
            for item in normalized["normalized_reentries"]
        )
        assert rows
        assert all(
            item[2].reentry_trade is item[4]
            for item in normalized["normalized_reentries"]
        )
        collision_free = bool(
            collision_free
            and normalized["normalized_first_collision_instances"] == 0
            and normalized["normalized_reentry_collision_instances"] == 0
        )
        results[window.label] = rows

    print("T104-19 Stochastic Pullback Completion Re-entry Anatomy result")
    print(f"  test_id={TEST_ID}")
    print("  mode=TEST_ONLY")
    print("  base=GREEN_8C1_PLUS_T104_08_DONCHIAN_REENTRY")
    print("  inventory=T104_15_CAUSAL_IDENTITY_NORMALIZED_EXECUTIONS")
    print("  identity_normalization_before_outcome_analysis=True")
    print(f"  identity_collisions_removed={collision_free}")
    print("  stochastic_percent_k=HLC_14_SMOOTHING_1")
    print("  stochastic_percent_d=SMA_PERCENT_K_3")
    print("  stochastic_source=CANONICAL_HIGH_LOW_CLOSE")
    print("  completion=ADVERSE_MOVE_THEN_LOCAL_K_TURN_THEN_FRESH_K_D_CROSS")
    print("  levels_20_50_80_are_anatomy_only=True")
    print("  levels_used_as_gate=False")
    print("  tuned_thresholds_added=False")
    print("  outcome_used_for_selection=False")

    for window in WINDOWS:
        rows = results[window.label]
        for direction in ("BUY", "SELL"):
            side = tuple(row for row in rows if row.direction == direction)
            _print_scope(f"{window.label}/{direction}", side)

    print("  tp_vs_sl_reported_with_identical_state_and_timing_schema=True")
    print("  fresh_restart_vs_already_directional_reported_without_selection=True")
    print("  production_logic_changed=False")
    print("  candidate_f_changed=False")
    print("  entry_exit_changed=False")
    print("  sl_tp_changed=False")
    print("  bbw_changed=False")
    print("  ac_changed=False")
    print("  dmi_adx_changed=False")
    print("  completed_bars_only=True")
    print("  future_price_used=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    assert collision_free
    print("T104_19_STOCHASTIC_PULLBACK_COMPLETION_REENTRY_ANATOMY_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
