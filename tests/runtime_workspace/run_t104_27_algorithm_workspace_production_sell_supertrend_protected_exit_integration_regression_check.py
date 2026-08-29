# -*- coding: utf-8 -*-
"""T104-27: production SELL Supertrend protected-exit integration regression.

The heavy history/indicator run is loaded exactly once for each period. The
frozen T104-15 execution inventory and its 12/24-pip hard protection remain
unchanged. Only SELL exits receive the production incremental canonical
Supertrend(10, 3) completed-M15 SELL->BUY switch. A disclosed 2026 losing
switch case is additionally replayed through WorkspaceReplayExecutionEngine.
"""

from __future__ import annotations

import importlib.util
import inspect
import math
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_replay_execution import (  # noqa: E402
    REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH,
    SELL_SUPERTREND_ATR_LENGTH,
    SELL_SUPERTREND_ATR_SMOOTHING,
    SELL_SUPERTREND_FACTOR,
    SELL_SUPERTREND_SOURCE,
    WorkspaceCanonicalSupertrend,
    WorkspaceReplayExecutionEngine,
    WorkspaceReplayExecutionPolicy,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402

BASE_SCRIPT_NAME = (
    "run_t104_25_algorithm_workspace_sell_supertrend_protected_exit_"
    "diagnostic_2025_2026_check.py"
)
TEST_ID = "T104-27"
EPSILON = 1e-12
WORKSPACE_UID = "00000000-0000-0000-0000-000000010427"


def _load_base_module() -> ModuleType:
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm104_t104_27_protected_exit_base"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()
WINDOWS = getattr(BASE, "WINDOWS")
PIP_SIZE = float(getattr(BASE, "PIP_SIZE"))
_load_indicator_run: Callable[..., Any] = getattr(BASE, "_load_indicator_run")
_confirmed_candidates: Callable[..., Any] = getattr(BASE, "_confirmed_candidates")
_first_leg_survivor_indices: Callable[..., Any] = getattr(
    BASE, "_first_leg_survivor_indices"
)
_simulate_baseline: Callable[..., Any] = getattr(BASE, "_simulate_baseline")
_diagnostic_supertrend: Callable[..., Any] = getattr(BASE, "_canonical_supertrend")
_first_opposite_switch: Callable[..., Any] = getattr(BASE, "_first_opposite_switch")
_protected_switch_trade: Callable[..., Any] = getattr(BASE, "_protected_switch_trade")
_close_at_market: Callable[..., float] = getattr(BASE.BASE, "_close_at_market")
_summary: Callable[..., Any] = getattr(BASE, "_summary")


EXPECTED = {
    "2025": {
        "baseline_net": 4.80,
        "baseline_pf": 1.0513,
        "baseline_dd": 13.20,
        "candidate_net": 12.41,
        "candidate_pf": 1.1443,
        "candidate_dd": 10.92,
        "sell_delta": 7.61,
    },
    "2026": {
        "baseline_net": 27.87,
        "baseline_pf": 1.4762,
        "baseline_dd": 13.20,
        "candidate_net": 34.87,
        "candidate_pf": 1.6934,
        "candidate_dd": 8.99,
        "sell_delta": 7.00,
    },
}


def _expected_for(label: str) -> dict[str, float]:
    return EXPECTED["2025" if label == "2025" else "2026"]


def _assert_near(actual: float | None, expected: float, tolerance: float) -> None:
    assert actual is not None
    assert math.isclose(actual, expected, rel_tol=0.0, abs_tol=tolerance), (
        actual,
        expected,
    )


def _production_supertrend(events: tuple[Any, ...]) -> tuple[Any, ...]:
    tracker = WorkspaceCanonicalSupertrend()
    return tuple(tracker.on_completed_m15_bar(event) for event in events)


def _assert_switch_close_is_causal(
    events: tuple[Any, ...],
    points: tuple[Any, ...],
    candidate: Any,
    trade: Any,
) -> None:
    if trade.close_reason != REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH:
        return
    switch_index = _first_opposite_switch(points, candidate)
    assert switch_index is not None and switch_index > 0
    assert points[switch_index - 1].state == "SELL"
    assert points[switch_index].state == "BUY"
    assert points[switch_index].sell_to_buy_switch
    assert trade.close_timestamp == events[switch_index].timestamp + getattr(
        BASE.BASE, "EXPECTED_M15_DELTA"
    )
    assert trade.close_price == _close_at_market(events[switch_index], "SELL")


def _run_period(window: Any) -> dict[str, Any]:
    print(f"  running_period={window.label}", flush=True)
    run = _load_indicator_run(window)
    events = tuple(run.events)
    candidates = tuple(_confirmed_candidates(run)[0])
    survivor_indices = tuple(_first_leg_survivor_indices(candidates))
    selected = tuple(candidates[index] for index in survivor_indices)
    raw_baseline = tuple(
        _simulate_baseline(run, candidate, macd_exit_enabled=False)
        for candidate in candidates
    )
    baseline = tuple(raw_baseline[index] for index in survivor_indices)

    production_points = _production_supertrend(events)
    diagnostic_points = tuple(_diagnostic_supertrend(events))
    assert len(production_points) == len(diagnostic_points)
    for production, diagnostic in zip(
        production_points,
        diagnostic_points,
        strict=True,
    ):
        assert production.state == diagnostic.state
        assert production.switched == diagnostic.switched
        if diagnostic.atr is None:
            assert production.atr is None
        else:
            _assert_near(production.atr, float(diagnostic.atr), EPSILON)
        if diagnostic.line is None:
            assert production.line is None
        else:
            _assert_near(production.line, float(diagnostic.line), EPSILON)

    combined: list[Any] = []
    sell_baseline: list[Any] = []
    sell_protected: list[Any] = []
    for candidate, baseline_trade in zip(selected, baseline, strict=True):
        if candidate.direction == "BUY":
            policy_trade = baseline_trade
        else:
            switch_index = _first_opposite_switch(production_points, candidate)
            policy_trade = _protected_switch_trade(events, candidate, switch_index)
            sell_baseline.append(baseline_trade)
            sell_protected.append(policy_trade)
            _assert_switch_close_is_causal(
                events,
                production_points,
                candidate,
                policy_trade,
            )
        combined.append(policy_trade)

    combined_tuple = tuple(combined)
    sell_baseline_tuple = tuple(sell_baseline)
    sell_protected_tuple = tuple(sell_protected)
    keys = [(str(row.direction), int(row.entry_index)) for row in selected]
    collisions = len(keys) - len(set(keys))
    assert collisions == 0
    assert all(
        left is right
        for candidate, left, right in zip(
            selected,
            baseline,
            combined_tuple,
            strict=True,
        )
        if candidate.direction == "BUY"
    )

    baseline_summary = _summary(baseline)
    candidate_summary = _summary(combined_tuple)
    buy_baseline = tuple(
        trade
        for candidate, trade in zip(selected, baseline, strict=True)
        if candidate.direction == "BUY"
    )
    buy_candidate = tuple(
        trade
        for candidate, trade in zip(selected, combined_tuple, strict=True)
        if candidate.direction == "BUY"
    )
    sell_delta = sum(
        float(right.pnl) - float(left.pnl)
        for left, right in zip(
            sell_baseline_tuple,
            sell_protected_tuple,
            strict=True,
        )
    )
    expected = _expected_for(window.label)
    _assert_near(float(baseline_summary.net), expected["baseline_net"], 0.01)
    _assert_near(baseline_summary.profit_factor, expected["baseline_pf"], 0.0001)
    _assert_near(
        float(baseline_summary.maximum_drawdown),
        expected["baseline_dd"],
        0.01,
    )
    _assert_near(float(candidate_summary.net), expected["candidate_net"], 0.01)
    _assert_near(candidate_summary.profit_factor, expected["candidate_pf"], 0.0001)
    _assert_near(
        float(candidate_summary.maximum_drawdown),
        expected["candidate_dd"],
        0.01,
    )
    _assert_near(sell_delta, expected["sell_delta"], 0.01)
    assert buy_candidate == buy_baseline
    assert _summary(buy_candidate) == _summary(buy_baseline)
    return {
        "run": run,
        "events": events,
        "points": production_points,
        "candidates": selected,
        "baseline": baseline,
        "combined": combined_tuple,
        "sell_baseline": sell_baseline_tuple,
        "sell_protected": sell_protected_tuple,
        "baseline_summary": baseline_summary,
        "candidate_summary": candidate_summary,
        "sell_delta": sell_delta,
        "collisions": collisions,
    }


def _signal_record(candidate: Any, event: Any) -> WorkspaceSignalRecord:
    return WorkspaceSignalRecord(
        timestamp=candidate.confirm_timestamp,
        signal_uid=f"T104-27-SELL-{candidate.entry_index}",
        workspace_uid=WORKSPACE_UID,
        broker=event.broker,
        account_id=None,
        symbol=event.symbol,
        timeframe=event.timeframe,
        source_mode=event.source_mode,
        signal_type="T104_27_REGRESSION",
        direction="SELL",
        strength=1.0,
        macd_state="CROSS_DOWN",
        alligator_confirmation="BEARISH",
        spread_status="OK",
        accepted=True,
        reason="T104-27 disclosed production wiring case",
    )


def _replay_disclosed_negative_case(data: dict[str, Any]) -> dict[str, Any]:
    candidates = data["candidates"]
    baseline = data["baseline"]
    combined = data["combined"]
    matches = [
        (candidate, left, right)
        for candidate, left, right in zip(
            candidates,
            baseline,
            combined,
            strict=True,
        )
        if candidate.direction == "SELL"
        and candidate.entry_timestamp.strftime("%Y-%m-%d %H:%M") == "2026-02-18 07:15"
    ]
    assert len(matches) == 1
    candidate, baseline_trade, protected_trade = matches[0]
    assert baseline_trade.close_reason == "TAKE_PROFIT"
    _assert_near(float(baseline_trade.pnl), 2.40, 0.005)
    assert protected_trade.close_reason == REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH
    _assert_near(float(protected_trade.pnl), -0.66, 0.005)
    _assert_near(
        float(protected_trade.pnl) - float(baseline_trade.pnl),
        -3.06,
        0.005,
    )

    events = data["events"]
    engine = WorkspaceReplayExecutionEngine(
        workspace_uid=WORKSPACE_UID,
        broker=events[0].broker,
        account_id=None,
        symbol=events[0].symbol,
        policy=WorkspaceReplayExecutionPolicy(
            fixed_volume=1000.0,
            maximum_open_positions=1,
        ),
    )
    confirm_end = int(candidate.confirm_index) + 1
    entry_index = int(candidate.entry_index)
    for event in events[:confirm_end]:
        assert not engine.on_completed_m15_bar(event)
    signal_event = events[candidate.confirm_index]
    engine.queue_signal(_signal_record(candidate, signal_event), signal_event)

    lifecycle = []
    for event in events[entry_index:]:
        lifecycle.extend(engine.on_market_event(event))
        lifecycle.extend(engine.on_completed_m15_bar(event))
        if engine.closed_trades:
            break
    close_events = [
        item for item in lifecycle if item.event == "VIRTUAL_POSITION_CLOSED"
    ]
    assert len(close_events) == 1
    close_event = close_events[0]
    assert (
        close_event.details["close_reason"] == REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH
    )
    _assert_near(float(close_event.details["realized_profit"]), -0.66, 0.005)
    _assert_near(
        float(close_event.details["close_price"]), protected_trade.close_price, EPSILON
    )
    assert close_event.details["completed_m15_bars_only"] is True
    assert close_event.details["future_price_used"] is False
    assert close_event.details["hard_sl_tp_priority_on_same_bar"] is True
    assert close_event.details["switch_exit_equals_switch_bar_close"] is True
    return {
        "candidate": candidate,
        "baseline": baseline_trade,
        "protected": protected_trade,
        "close_event": close_event,
    }


def _assert_production_wiring() -> None:
    accept_market_event = getattr(WorkspaceRuntime, "_accept_market_event")
    apply_sell_exit = getattr(
        WorkspaceRuntime,
        "_apply_replay_sell_supertrend_exit",
    )
    accept_source = inspect.getsource(accept_market_event)
    route_source = inspect.getsource(apply_sell_exit)
    assert "self._apply_replay_sell_supertrend_exit(event)" in accept_source
    assert "engine.on_completed_m15_bar(event)" in route_source
    assert "self._append_replay_execution_events(lifecycle)" in route_source
    assert "self._sync_replay_execution_snapshot" in route_source


def _fmt_pf(value: float | None) -> str:
    return "NONE" if value is None else f"{value:.4f}"


def main() -> int:
    _assert_production_wiring()
    results = {window.label: _run_period(window) for window in WINDOWS}
    y2026_label = next(label for label in results if label != "2025")
    negative = _replay_disclosed_negative_case(results[y2026_label])

    print("T104-27 Production SELL Supertrend Protected Exit result")
    print(f"  test_id={TEST_ID}")
    print("  mode=PRODUCTION_INTEGRATION_REGRESSION")
    print(
        "  production_call_path=SIGNAL_POSITION_STATE->EXIT_EVALUATION->"
        "CANONICAL_SUPERTREND_SWITCH->VIRTUAL_CLOSE_POSITION"
    )
    print("  production_runtime_method_calls_execution_engine=True")
    print("  production_close_path_records_snapshot_journal_diagnostic=True")
    print(f"  supertrend_atr_length={SELL_SUPERTREND_ATR_LENGTH}")
    print(f"  supertrend_factor={SELL_SUPERTREND_FACTOR:.1f}")
    print(f"  supertrend_source={SELL_SUPERTREND_SOURCE}")
    print(f"  supertrend_atr_smoothing={SELL_SUPERTREND_ATR_SMOOTHING}")
    print("  sell_hard_sl_pips=12.0")
    print("  sell_hard_tp_pips=24.0")
    print("  same_bar_policy=SL->TP->SUPERTREND_SWITCH")

    for window in WINDOWS:
        data = results[window.label]
        baseline_summary = data["baseline_summary"]
        candidate_summary = data["candidate_summary"]
        switches = Counter(trade.close_reason for trade in data["sell_protected"])[
            REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH
        ]
        print(
            f"  {window.label}/BASELINE_ALL="
            f"net:{baseline_summary.net:+.2f},"
            f"pf:{_fmt_pf(baseline_summary.profit_factor)},"
            f"dd:{baseline_summary.maximum_drawdown:.2f}"
        )
        print(
            f"  {window.label}/PRODUCTION_CANDIDATE="
            f"net:{candidate_summary.net:+.2f},"
            f"pf:{_fmt_pf(candidate_summary.profit_factor)},"
            f"dd:{candidate_summary.maximum_drawdown:.2f},"
            f"sell_delta:{data['sell_delta']:+.2f},"
            f"sell_switches:{switches}"
        )
        print(
            f"  {window.label}/IDENTITY="
            f"executions:{len(data['candidates'])},"
            f"unique:{len(data['candidates'])},collisions:{data['collisions']}"
        )
        print(f"  {window.label}/BUY_BASELINE_IDENTICAL=True")

    candidate = negative["candidate"]
    baseline_trade = negative["baseline"]
    protected_trade = negative["protected"]
    print(
        "  CONTROL_NEGATIVE_CASE="
        f"entry:{candidate.entry_timestamp.isoformat()},direction:SELL,"
        f"baseline:{baseline_trade.close_reason} {baseline_trade.pnl:+.2f},"
        f"production:{protected_trade.close_reason} {protected_trade.pnl:+.2f},"
        f"delta:{protected_trade.pnl - baseline_trade.pnl:+.2f},"
        "hidden:False,replayed_through_production_execution_engine:True"
    )
    print("  completed_m15_bars_only=True")
    print("  future_price_used=False")
    print("  hard_sl_tp_priority_on_same_bar=True")
    print("  switch_exit_equals_switch_bar_close=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  production_sell_exit_logic_changed=True")
    print("  buy_exit_logic_changed=False")
    print("  candidate_f_entry_logic_changed=False")
    print("  supertrend_parameters_optimized=False")
    print("  regression_status=GREEN")
    print("T104_27_PRODUCTION_SELL_SUPERTREND_PROTECTED_EXIT_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
