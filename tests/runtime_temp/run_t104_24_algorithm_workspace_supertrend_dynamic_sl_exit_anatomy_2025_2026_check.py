# -*- coding: utf-8 -*-
"""RoadMap104 / T104-24: canonical Supertrend dynamic SL/exit anatomy.

TEST_ONLY anatomy over the T104-15 identity-normalized GREEN 8C.1 first-leg
inventory. Canonical Supertrend uses HL2, True Range, Wilder RMA(10), factor 3,
and the standard carried-band state machine. Entry state and line come from
entry_index - 1, the last M15 bar completed before NEXT_M15_OPEN execution.

The first post-entry opposite-state switch is evaluated only when its M15 bar
has completed. It never selects a trade. Switch-only PnL is descriptive; a
second paired replay preserves the fixed 12-pip SL and 24-pip TP and checks
them before a switch exit on the same bar, with SL first when both are touched.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

IDENTITY_SCRIPT_NAME = (
    "run_t104_15_algorithm_workspace_causal_execution_identity_normalization_"
    "2025_2026_check.py"
)
OPENING_SCRIPT_NAME = (
    "run_algorithm_workspace_alligator_opening_expansion_2025_2026_check.py"
)
TEST_ID = "T104-24"
ATR_LENGTH = 10
FACTOR = 3.0
STOP_LOSS_PIPS = 12.0
TAKE_PROFIT_PIPS = 24.0
EPSILON = 1e-12


def _load_module(file_name: str, module_name: str) -> ModuleType:
    file_path = Path(__file__).with_name(file_name)
    assert file_path.is_file(), file_path
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


IDENTITY = _load_module(
    IDENTITY_SCRIPT_NAME,
    "rm104_t104_24_identity_normalized_base",
)
OPENING = _load_module(
    OPENING_SCRIPT_NAME,
    "rm104_t104_24_green_8c1_opening_base",
)
CORE = getattr(OPENING, "BASE")
WINDOWS = getattr(IDENTITY, "WINDOWS")
PIP_SIZE = float(getattr(CORE, "PIP_SIZE"))
FIXED_VOLUME = float(getattr(CORE, "FIXED_VOLUME"))
EXPECTED_M15_DELTA = getattr(CORE, "EXPECTED_M15_DELTA")
TradeResult = getattr(CORE, "TradeResult")
_first_leg_survivor_indices: Callable[..., Any] = getattr(
    IDENTITY, "_first_leg_survivor_indices"
)
_load_indicator_run: Callable[..., Any] = getattr(OPENING, "_load_indicator_run")
_confirmed_candidates: Callable[..., Any] = getattr(
    OPENING, "_confirmed_expansion_candidates"
)
_simulate_baseline: Callable[..., Any] = getattr(OPENING, "_simulate_trade")
_entry_price: Callable[..., float] = getattr(CORE, "_entry_price")
_close_at_market: Callable[..., float] = getattr(CORE, "_close_at_market")
_summary: Callable[..., Any] = getattr(OPENING, "_summary")
_summary_text: Callable[..., str] = getattr(OPENING, "_summary_text")


@dataclass(frozen=True, slots=True)
class SupertrendPoint:
    """One completed-bar canonical Supertrend observation."""

    atr: float | None
    upper_band: float | None
    lower_band: float | None
    line: float | None
    state: str | None
    switched: bool


@dataclass(frozen=True, slots=True)
class EntryAnatomy:
    """Supertrend information causally available at one GREEN entry."""

    direction: str
    outcome: str
    entry_index: int
    source_index: int
    state: str | None
    alignment: str
    line: float | None
    distance_pips: float | None
    protective: bool
    trade_direction_switch_timing: str


@dataclass(frozen=True, slots=True)
class ExitAnatomy:
    """First causal opposite switch and paired exit diagnostics."""

    direction: str
    outcome: str
    relation_to_baseline: str
    switch_index: int | None
    switch_only_trade: Any
    protected_switch_trade: Any
    baseline_pnl: float


def _canonical_atr(events: tuple[Any, ...]) -> tuple[float | None, ...]:
    """Return canonical True Range with Wilder RMA(10)."""
    result: list[float | None] = []
    true_ranges: list[float] = []
    previous_close: float | None = None
    rma: float | None = None
    for index, event in enumerate(events):
        high = float(event.high)
        low = float(event.low)
        if previous_close is None:
            true_range = high - low
        else:
            true_range = max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )
        assert true_range >= 0.0 and math.isfinite(true_range)
        true_ranges.append(true_range)
        if index == ATR_LENGTH - 1:
            rma = sum(true_ranges) / ATR_LENGTH
        elif index >= ATR_LENGTH:
            assert rma is not None
            rma = ((ATR_LENGTH - 1) * rma + true_range) / ATR_LENGTH
        result.append(rma)
        previous_close = float(event.close)
    return tuple(result)


def _canonical_supertrend(events: tuple[Any, ...]) -> tuple[SupertrendPoint, ...]:
    """Return standard carried-band Supertrend(10, 3) on completed bars."""
    atr = _canonical_atr(events)
    points: list[SupertrendPoint] = []
    previous_upper: float | None = None
    previous_lower: float | None = None
    previous_line: float | None = None
    previous_state: str | None = None

    for index, event in enumerate(events):
        current_atr = atr[index]
        if current_atr is None:
            points.append(SupertrendPoint(None, None, None, None, None, False))
            continue

        midpoint = (float(event.high) + float(event.low)) / 2.0
        basic_upper = midpoint + FACTOR * current_atr
        basic_lower = midpoint - FACTOR * current_atr
        if previous_upper is None or previous_lower is None:
            upper = basic_upper
            lower = basic_lower
        else:
            previous_close = float(events[index - 1].close)
            upper = (
                basic_upper
                if basic_upper < previous_upper or previous_close > previous_upper
                else previous_upper
            )
            lower = (
                basic_lower
                if basic_lower > previous_lower or previous_close < previous_lower
                else previous_lower
            )

        if previous_line is None:
            # Canonical state-machine initialization: upper band / downtrend.
            state = "SELL"
        elif math.isclose(
            previous_line,
            float(previous_upper),
            rel_tol=0.0,
            abs_tol=EPSILON,
        ):
            state = "BUY" if float(event.close) > upper else "SELL"
        else:
            state = "SELL" if float(event.close) < lower else "BUY"
        line = lower if state == "BUY" else upper
        switched = previous_state is not None and state != previous_state
        points.append(SupertrendPoint(current_atr, upper, lower, line, state, switched))
        previous_upper = upper
        previous_lower = lower
        previous_line = line
        previous_state = state

    return tuple(points)


def _state_start(points: tuple[SupertrendPoint, ...], index: int) -> bool:
    state = points[index].state
    if state is None:
        return False
    return index == 0 or points[index - 1].state != state


def _trade_direction_switch_timing(
    points: tuple[SupertrendPoint, ...], direction: str, source_index: int
) -> str:
    """Locate the state-start that establishes the trade-direction state."""
    if points[source_index].state == direction:
        for index in range(source_index, -1, -1):
            if points[index].state == direction and _state_start(points, index):
                return "SAME_BAR" if index == source_index else "BEFORE"
        raise AssertionError("aligned state must have a causal state start")

    for index in range(source_index + 1, len(points)):
        if points[index].state == direction and _state_start(points, index):
            return "AFTER"
    return "NONE"


def _entry_anatomy(
    events: tuple[Any, ...],
    points: tuple[SupertrendPoint, ...],
    candidate: Any,
    baseline: Any,
) -> EntryAnatomy:
    entry_index = int(candidate.entry_index)
    source_index = entry_index - 1
    point = points[source_index]
    entry = _entry_price(events[entry_index], str(candidate.direction))
    line = point.line
    if line is None:
        distance = None
        protective = False
        alignment = "MISSING"
        switch_timing = "NONE"
    else:
        direction = str(candidate.direction)
        distance = abs(entry - line) / PIP_SIZE
        protective_distance = entry - line if direction == "BUY" else line - entry
        protective = protective_distance > EPSILON
        alignment = "ALIGNED" if point.state == direction else "OPPOSITE"
        switch_timing = _trade_direction_switch_timing(points, direction, source_index)
    return EntryAnatomy(
        direction=str(candidate.direction),
        outcome=str(baseline.close_reason),
        entry_index=entry_index,
        source_index=source_index,
        state=point.state,
        alignment=alignment,
        line=line,
        distance_pips=distance,
        protective=protective,
        trade_direction_switch_timing=switch_timing,
    )


def _first_opposite_switch(
    points: tuple[SupertrendPoint, ...], candidate: Any
) -> int | None:
    opposite = "SELL" if candidate.direction == "BUY" else "BUY"
    for index in range(int(candidate.entry_index), len(points)):
        if points[index].state == opposite and points[index].switched:
            return index
    return None


def _trade_result(
    events: tuple[Any, ...],
    candidate: Any,
    close_index: int,
    close_price: float,
    close_reason: str,
) -> Any:
    entry_index = int(candidate.entry_index)
    entry = _entry_price(events[entry_index], str(candidate.direction))
    sign = 1.0 if candidate.direction == "BUY" else -1.0
    return TradeResult(
        direction=candidate.direction,
        start_timestamp=candidate.start_timestamp,
        confirm_timestamp=candidate.confirm_timestamp,
        entry_timestamp=candidate.entry_timestamp,
        close_timestamp=events[close_index].timestamp + EXPECTED_M15_DELTA,
        entry_price=entry,
        close_price=close_price,
        close_reason=close_reason,
        pnl=(close_price - entry) * FIXED_VOLUME * sign,
        holding_bars=close_index - entry_index + 1,
    )


def _switch_only_trade(
    events: tuple[Any, ...], candidate: Any, switch_index: int | None
) -> Any:
    close_index = len(events) - 1 if switch_index is None else switch_index
    reason = "SESSION_END" if switch_index is None else "SUPERTREND_OPPOSITE_SWITCH"
    close_price = _close_at_market(events[close_index], str(candidate.direction))
    return _trade_result(events, candidate, close_index, close_price, reason)


def _protected_switch_trade(
    events: tuple[Any, ...], candidate: Any, switch_index: int | None
) -> Any:
    entry_index = int(candidate.entry_index)
    entry = _entry_price(events[entry_index], str(candidate.direction))
    sign = 1.0 if candidate.direction == "BUY" else -1.0
    stop = entry - sign * STOP_LOSS_PIPS * PIP_SIZE
    take = entry + sign * TAKE_PROFIT_PIPS * PIP_SIZE
    close_index = len(events) - 1
    close_price = _close_at_market(events[close_index], str(candidate.direction))
    close_reason = "SESSION_END"
    for index in range(entry_index, len(events)):
        event = events[index]
        if candidate.direction == "BUY":
            stop_touched = float(event.low) <= stop
            take_touched = float(event.high) >= take
        else:
            stop_touched = float(event.high) >= stop
            take_touched = float(event.low) <= take
        if stop_touched:
            close_index, close_price, close_reason = index, stop, "STOP_LOSS"
            break
        if take_touched:
            close_index, close_price, close_reason = index, take, "TAKE_PROFIT"
            break
        if switch_index == index:
            close_index = index
            close_price = _close_at_market(event, str(candidate.direction))
            close_reason = "SUPERTREND_OPPOSITE_SWITCH"
            break
    return _trade_result(events, candidate, close_index, close_price, close_reason)


def _exit_anatomy(
    events: tuple[Any, ...],
    points: tuple[SupertrendPoint, ...],
    candidate: Any,
    baseline: Any,
) -> ExitAnatomy:
    switch_index = _first_opposite_switch(points, candidate)
    if switch_index is None:
        relation = "MISSING"
    else:
        switch_timestamp = events[switch_index].timestamp + EXPECTED_M15_DELTA
        if switch_timestamp < baseline.close_timestamp:
            relation = "BEFORE_SL_TP"
        elif switch_timestamp == baseline.close_timestamp:
            relation = "SAME_BAR"
        else:
            relation = "AFTER_SL_TP"
    return ExitAnatomy(
        direction=str(candidate.direction),
        outcome=str(baseline.close_reason),
        relation_to_baseline=relation,
        switch_index=switch_index,
        switch_only_trade=_switch_only_trade(events, candidate, switch_index),
        protected_switch_trade=_protected_switch_trade(events, candidate, switch_index),
        baseline_pnl=float(baseline.pnl),
    )


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _fmt(value: float | None) -> str:
    return "NONE" if value is None else f"{value:.3f}"


def _counter_text(values: Any) -> str:
    counter = Counter(values)
    return "|".join(f"{key}:{counter[key]}" for key in sorted(counter)) or "NONE"


def _entry_state_text(rows: tuple[EntryAnatomy, ...]) -> str:
    return (
        f"trades:{len(rows)},"
        f"alignment:{_counter_text(row.alignment for row in rows)},"
        f"state:{_counter_text(str(row.state) for row in rows)},"
        "switch_to_trade_direction_timing:"
        f"{_counter_text(row.trade_direction_switch_timing for row in rows)}"
    )


def _distance_text(rows: tuple[EntryAnatomy, ...]) -> str:
    protective = [
        float(row.distance_pips)
        for row in rows
        if row.protective and row.distance_pips is not None
    ]
    below = sum(value < STOP_LOSS_PIPS for value in protective)
    inside = sum(STOP_LOSS_PIPS <= value <= TAKE_PROFIT_PIPS for value in protective)
    above = sum(value > TAKE_PROFIT_PIPS for value in protective)
    denominator = len(rows)

    def fraction(count: int) -> float:
        return count / denominator if denominator else 0.0

    missing = sum(row.line is None for row in rows)
    non_protective = sum(row.line is not None and not row.protective for row in rows)
    return (
        f"protective:{len(protective)},median:{_fmt(_percentile(protective, 0.50))},"
        f"p25:{_fmt(_percentile(protective, 0.25))},"
        f"p75:{_fmt(_percentile(protective, 0.75))},"
        f"lt_12:{below},lt_12_fraction_all:{fraction(below):.6f},"
        f"from_12_to_24:{inside},from_12_to_24_fraction_all:{fraction(inside):.6f},"
        f"gt_24:{above},gt_24_fraction_all:{fraction(above):.6f},"
        f"missing:{missing},missing_fraction_all:{fraction(missing):.6f},"
        f"non_protective:{non_protective},"
        f"non_protective_fraction_all:{fraction(non_protective):.6f}"
    )


def _paired_text(rows: tuple[ExitAnatomy, ...], attribute: str) -> str:
    variant = tuple(getattr(row, attribute) for row in rows)
    baseline_net = sum(row.baseline_pnl for row in rows)
    variant_net = sum(float(trade.pnl) for trade in variant)
    improved = sum(
        float(trade.pnl) > row.baseline_pnl + EPSILON
        for row, trade in zip(rows, variant, strict=True)
    )
    worsened = sum(
        float(trade.pnl) < row.baseline_pnl - EPSILON
        for row, trade in zip(rows, variant, strict=True)
    )
    return (
        f"{_summary_text(_summary(variant))},baseline_net:{baseline_net:+.2f},"
        f"paired_delta:{variant_net - baseline_net:+.2f},"
        f"improved:{improved},worsened:{worsened},"
        f"unchanged:{len(rows) - improved - worsened}"
    )


def _exit_text(rows: tuple[ExitAnatomy, ...]) -> str:
    return (
        f"trades:{len(rows)},"
        f"switch_vs_baseline:{_counter_text(row.relation_to_baseline for row in rows)},"
        f"switch_only:{_paired_text(rows, 'switch_only_trade')};"
        f"protected_switch:{_paired_text(rows, 'protected_switch_trade')}"
    )


def _scope_indices(
    candidates: tuple[Any, ...], direction: str | None
) -> tuple[int, ...]:
    return tuple(
        index
        for index, candidate in enumerate(candidates)
        if direction is None or candidate.direction == direction
    )


def _subset(rows: tuple[Any, ...], indices: tuple[int, ...]) -> tuple[Any, ...]:
    return tuple(rows[index] for index in indices)


def _report_period(
    label: str,
    candidates: tuple[Any, ...],
    entries: tuple[EntryAnatomy, ...],
    exits: tuple[ExitAnatomy, ...],
) -> None:
    for direction in (None, "BUY", "SELL"):
        indices = _scope_indices(candidates, direction)
        scope = "ALL" if direction is None else direction
        entry_rows = _subset(entries, indices)
        exit_rows = _subset(exits, indices)
        print(f"  {label}/{scope}/ENTRY_STATE={_entry_state_text(entry_rows)}")
        print(f"  {label}/{scope}/DYNAMIC_SL={_distance_text(entry_rows)}")
        print(f"  {label}/{scope}/EXIT={_exit_text(exit_rows)}")

    for outcome in ("TAKE_PROFIT", "STOP_LOSS", "SESSION_END"):
        indices = tuple(
            index for index, row in enumerate(entries) if row.outcome == outcome
        )
        if not indices:
            continue
        entry_rows = _subset(entries, indices)
        print(f"  {label}/{outcome}/ENTRY_STATE={_entry_state_text(entry_rows)}")
        print(f"  {label}/{outcome}/DYNAMIC_SL={_distance_text(entry_rows)}")
        for direction in ("BUY", "SELL"):
            combined = tuple(
                index for index in indices if candidates[index].direction == direction
            )
            print(
                f"  {label}/{direction}/{outcome}/ENTRY_STATE="
                f"{_entry_state_text(_subset(entries, combined))}"
            )


def main() -> int:
    results: dict[str, dict[str, Any]] = {}
    for window in WINDOWS:
        print(f"  running_period={window.label}", flush=True)
        run = _load_indicator_run(window)
        events = tuple(run.events)
        candidates = tuple(_confirmed_candidates(run)[0])
        survivor_indices = tuple(_first_leg_survivor_indices(candidates))
        selected = tuple(candidates[index] for index in survivor_indices)
        baseline_all = tuple(
            _simulate_baseline(run, candidate, macd_exit_enabled=False)
            for candidate in candidates
        )
        baseline = tuple(baseline_all[index] for index in survivor_indices)
        points = _canonical_supertrend(events)
        entries = tuple(
            _entry_anatomy(events, points, candidate, trade)
            for candidate, trade in zip(selected, baseline, strict=True)
        )
        exits = tuple(
            _exit_anatomy(events, points, candidate, trade)
            for candidate, trade in zip(selected, baseline, strict=True)
        )
        assert len(selected) == len(
            {(row.direction, row.entry_index) for row in selected}
        )
        assert len(entries) == len(exits) == len(baseline)
        assert all(row.source_index == row.entry_index - 1 for row in entries)
        assert all(points[row.source_index].state is not None for row in entries)
        assert all(
            row.protected_switch_trade.close_timestamp
            <= row.switch_only_trade.close_timestamp
            or row.switch_index is None
            for row in exits
        )
        results[window.label] = {
            "run": run,
            "candidates": selected,
            "entries": entries,
            "exits": exits,
        }

    print("T104-24 Supertrend Dynamic SL/Exit Anatomy result")
    print(f"  test_id={TEST_ID}")
    print("  mode=TEST_ONLY")
    print("  inventory=T104_15_IDENTITY_NORMALIZED_GREEN_8C1_FIRST_LEG")
    print("  period_run_loads=ONE_PER_PERIOD")
    print("  timeframe=M15")
    print(f"  atr_length={ATR_LENGTH}")
    print(f"  factor={FACTOR:.1f}")
    print("  source=HL2")
    print("  true_range=MAX_HIGH_LOW_HIGH_PREV_CLOSE_LOW_PREV_CLOSE")
    print("  smoothing=WILDER_RMA")
    print("  rma_seed=SMA_OF_FIRST_10_TRUE_RANGES")
    print("  semantics=STANDARD_CARRIED_FINAL_BANDS_STATE_MACHINE")
    print("  initial_warmed_state=UPPER_BAND_SELL")
    print("  entry_supertrend_source=ENTRY_INDEX_MINUS_1_COMPLETED_M15_BAR")
    print("  protective_definition=BUY_LINE_BELOW_ENTRY_SELL_LINE_ABOVE_ENTRY")
    print("  fixed_sl_pips=12.0")
    print("  baseline_tp_pips=24.0")
    print("  first_exit_switch=FIRST_CAUSAL_POST_ENTRY_STATE_CHANGE_TO_OPPOSITE")
    print("  switch_timestamp=SWITCH_M15_BAR_COMPLETION")
    print("  switch_only_exit_price=SWITCH_BAR_MARKET_CLOSE")
    print("  protected_switch_policy=FIXED_SL_TP_BEFORE_SWITCH_ON_SAME_BAR")
    print("  same_bar_policy=SL_FIRST_CONSERVATIVE")
    for window in WINDOWS:
        data = results[window.label]
        run = data["run"]
        print(
            f"  {window.label}/DATA=m1:{run.accepted_m1_rows},"
            f"m15:{run.completed_m15_bars},"
            f"dropped_incomplete:{run.dropped_incomplete_buckets}"
        )
        _report_period(
            window.label,
            data["candidates"],
            data["entries"],
            data["exits"],
        )

    print("  outcome_used_for_selection=False")
    print("  tuned_thresholds_added=False")
    print("  atr_length_or_factor_optimized=False")
    print("  supertrend_policy_added_to_production=False")
    print("  production_logic_changed=False")
    print("  candidate_f_changed=False")
    print("  entry_logic_changed=False")
    print("  exit_logic_changed=False")
    print("  sl_logic_changed=False")
    print("  tp_logic_changed=False")
    print("  bbw_changed=False")
    print("  ac_changed=False")
    print("  stochastic_changed=False")
    print("  dmi_adx_changed=False")
    print("  fractal_changed=False")
    print("  pivot_changed=False")
    print("  completed_bars_only=True")
    print("  future_price_used=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  diagnostic_status=GREEN")
    print("T104_24_SUPERTREND_DYNAMIC_SL_EXIT_ANATOMY_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
