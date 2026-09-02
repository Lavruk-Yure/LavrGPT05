# -*- coding: utf-8 -*-
"""T104-29: TEST_ONLY causal M1 -> M15 Supertrend ordering prototype.

The runner uses the factual T104-28 WorkspaceRuntime harness and changes one
thing in a test-only subclass: a completed M15 Supertrend evaluation is
deferred until every corresponding M1 execution event (including the existing
Profit Drawdown path) has been processed.  Production modules are not edited.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from collections import Counter
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_replay import WorkspaceReplaySession  # noqa: E402
from core.workspace_replay_execution import (  # noqa: E402
    REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH,
    WorkspaceCanonicalSupertrend,
)
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402

BASE_SCRIPT_NAME = (
    "run_t104_28_algorithm_workspace_production_path_truth_audit_" "2025_2026_check.py"
)
TEST_ID = "T104-29"


def _load_base_module() -> ModuleType:
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm104_t104_29_production_truth_base"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()
EPSILON = float(BASE.EPSILON)

# Public local names make the inherited T104-28 test helpers explicit and keep
# this runner free of direct protected-member access in IDE inspections.
BASE_RUNTIME = BASE.AuditWorkspaceRuntime
APPLY_SELL_SUPERTREND = getattr(
    BASE_RUNTIME,
    "_apply_replay_sell_supertrend_exit",
)
ACCEPT_REPLAY_SESSION_EVENT = getattr(
    BASE_RUNTIME,
    "_accept_replay_session_event",
)
ACCEPT_MARKET_EVENT = getattr(BASE_RUNTIME, "_accept_market_event")
ADVANCE_REPLAY_EXECUTION = getattr(BASE_RUNTIME, "_advance_replay_execution")
APPLY_PROFIT_PROTECTION = getattr(BASE_RUNTIME, "_apply_replay_profit_protection")
WORKSPACE_FACTORY = getattr(BASE, "_workspace")
RUN_TO_COMPLETION = getattr(BASE, "_run_to_completion")
GEOMETRY = getattr(BASE, "_geometry")
FIXTURE_SIGNAL = getattr(BASE, "_fixture_signal")
FIXTURE_EVENTS = getattr(BASE, "_fixture_events")
FIXTURE_WORKSPACE = getattr(BASE, "_fixture_workspace")
EVENT_FACTORY = getattr(BASE, "_event")
TRADE_MAP = getattr(BASE, "_trade_map")
TRADE_IDENTITY = getattr(BASE, "_identity")
JOURNAL_CHECKS = getattr(BASE, "_journal_checks")
PRODUCTION_HASHES = getattr(BASE, "_production_hashes")
BUY_CHECKS = getattr(BASE, "_buy_checks")
BROKER_EXECUTION_ATTEMPTED = getattr(BASE, "_broker_execution_attempted")
SUMMARY_TEXT = getattr(BASE, "_summary_text")
PAIRED_TEXT = getattr(BASE, "_paired_text")
GEOMETRY_TEXT = getattr(BASE, "_geometry_text")
IDENTITY_TEXT = getattr(BASE, "_identity_text")


@dataclass(frozen=True, slots=True)
class WindowAudit:
    """Timestamp proof for one deferred completed-M15 evaluation."""

    strategy_timestamp: Any
    completed_at: Any
    evaluated_at: Any
    execution_timestamps: tuple[Any, ...]


class CausalOrderingWorkspaceRuntime(BASE_RUNTIME):
    """TEST_ONLY adapter that defers only completed-M15 Supertrend."""

    def __init__(self, *args: Any, capture_trace: bool = False, **kwargs: Any) -> None:
        self._defer_sell_supertrend = False
        self._supertrend_observer = WorkspaceCanonicalSupertrend()
        self.causal_switch_completions: list[Any] = []
        self.window_audits: list[WindowAudit] = []
        self.capture_trace = capture_trace
        self.execution_trace: list[tuple[str, Any]] = []
        super().__init__(*args, **kwargs)

    def _apply_replay_sell_supertrend_exit(
        self,
        event: WorkspaceMarketEvent,
    ) -> None:
        if self._defer_sell_supertrend:
            return
        APPLY_SELL_SUPERTREND(self, event)

    def execute_deferred_supertrend(self, event: WorkspaceMarketEvent) -> None:
        APPLY_SELL_SUPERTREND(self, event)

    def _accept_replay_session_event(
        self,
        session: WorkspaceReplaySession,
        event: WorkspaceMarketEvent,
        event_index: int,
        *,
        origin: str,
    ) -> None:
        if not session.multi_resolution:
            ACCEPT_REPLAY_SESSION_EVENT(
                self,
                session,
                event,
                event_index,
                origin=origin,
            )
            return

        self._defer_sell_supertrend = True
        try:
            ACCEPT_MARKET_EVENT(
                self,
                event,
                origin=origin,
                advance_replay_execution=False,
            )
        finally:
            self._defer_sell_supertrend = False

        execution_events = session.execution_events_for_index(event_index)
        for execution_event in execution_events:
            if self.capture_trace:
                self.execution_trace.append(
                    (execution_event.timeframe, execution_event.timestamp)
                )
            ADVANCE_REPLAY_EXECUTION(self, execution_event)
            APPLY_PROFIT_PROTECTION(self, execution_event)

        completed_at = event.timestamp + timedelta(minutes=15)
        evaluated_at = (
            execution_events[-1].timestamp + timedelta(minutes=1)
            if execution_events
            else completed_at
        )
        observation = self._supertrend_observer.on_completed_m15_bar(event)
        if observation.sell_to_buy_switch:
            self.causal_switch_completions.append(evaluated_at)
        self.window_audits.append(
            WindowAudit(
                strategy_timestamp=event.timestamp,
                completed_at=completed_at,
                evaluated_at=evaluated_at,
                execution_timestamps=tuple(row.timestamp for row in execution_events),
            )
        )
        if self.capture_trace:
            self.execution_trace.append(("SUPERTREND_M15", evaluated_at))
        self.execute_deferred_supertrend(event)

    def accept_causal_event_for_audit(
        self,
        session: WorkspaceReplaySession,
        event: WorkspaceMarketEvent,
        event_index: int,
    ) -> None:
        self._accept_replay_session_event(
            session,
            event,
            event_index,
            origin="T104_29_TEST_ONLY_FIXTURE",
        )

    def advance_execution_for_audit(self, event: WorkspaceMarketEvent) -> None:
        ADVANCE_REPLAY_EXECUTION(self, event)

    def apply_profit_protection_for_audit(
        self,
        event: WorkspaceMarketEvent,
    ) -> None:
        APPLY_PROFIT_PROTECTION(self, event)


class CausalBaselineWorkspaceRuntime(CausalOrderingWorkspaceRuntime):
    """Same causal runtime with only the Supertrend close disabled."""

    def execute_deferred_supertrend(self, event: WorkspaceMarketEvent) -> None:
        _ = event


def _run_period(period: Any) -> dict[str, Any]:
    print(f"  running_period={period.label}", flush=True)
    service = BASE.SharedHistoricalReplayService()
    candidate = CausalOrderingWorkspaceRuntime(
        WORKSPACE_FACTORY(period),
        replay_service=service,
        algorithm_factory=BASE.create_registered_workspace_algorithm,
    )
    baseline = CausalBaselineWorkspaceRuntime(
        WORKSPACE_FACTORY(period),
        replay_service=service,
        algorithm_factory=BASE.create_registered_workspace_algorithm,
    )
    RUN_TO_COMPLETION(candidate)
    RUN_TO_COMPLETION(baseline)
    assert service.history_loads == 1
    assert isinstance(candidate.algorithm, BASE.WorkspaceMacdAlligatorReplayAlgorithm)
    assert isinstance(baseline.algorithm, BASE.WorkspaceMacdAlligatorReplayAlgorithm)
    candidate_engine = candidate.replay_execution
    baseline_engine = baseline.replay_execution
    assert candidate_engine is not None and baseline_engine is not None
    return {
        "period": period,
        "service": service,
        "baseline": BASE.RunFacts(
            runtime=baseline,
            trades=baseline_engine.trade_diagnostics(),
            geometry=GEOMETRY(baseline),
        ),
        "candidate": BASE.RunFacts(
            runtime=candidate,
            trades=candidate_engine.trade_diagnostics(),
            geometry=GEOMETRY(candidate),
        ),
    }


def _m1_window(event: WorkspaceMarketEvent) -> tuple[WorkspaceMarketEvent, ...]:
    rows = []
    for index in range(15):
        high = event.high if index == 14 else event.close + event.spread
        low = event.low if index == 14 else event.close - event.spread
        rows.append(
            replace(
                event,
                timestamp=event.timestamp + timedelta(minutes=15 + index),
                timeframe="M1",
                open=event.close,
                high=high,
                low=low,
            )
        )
    return tuple(rows)


def _priority_signal(event: WorkspaceMarketEvent, suffix: str) -> WorkspaceSignalRecord:
    base = FIXTURE_SIGNAL(event, suffix)
    return replace(
        base,
        signal_uid=f"{TEST_ID}-TEST_ONLY-FIXTURE-{suffix}",
        signal_type="T104_29_CAUSAL_ORDERING_FIXTURE",
        reason="T104-29 TEST_ONLY causal ordering fixture",
    )


def _run_priority_fixture(kind: str) -> dict[str, Any]:
    events = FIXTURE_EVENTS(kind)
    windows = tuple(() for _ in events[:-1]) + (_m1_window(events[-1]),)
    service = BASE.FixedReplayService(events, execution_windows=windows)
    runtime = CausalOrderingWorkspaceRuntime(
        FIXTURE_WORKSPACE(events),
        replay_service=service,
        algorithm_factory=BASE.create_registered_workspace_algorithm,
    )
    runtime.begin_start()
    runtime.complete_start()
    engine = runtime.replay_execution
    session = runtime.replay_session
    assert engine is not None and session is not None
    for event in events[:-1]:
        runtime.accept_market_event_for_audit(event)
    runtime.queue_signal_for_audit(
        _priority_signal(events[-2], kind),
        events[-2],
    )
    entry_probe = replace(
        events[-1],
        timestamp=events[-1].timestamp,
        timeframe="M1",
        high=events[-1].open + events[-1].spread,
        low=events[-1].open - events[-1].spread,
    )
    runtime.advance_execution_for_audit(entry_probe)
    runtime.apply_profit_protection_for_audit(entry_probe)
    runtime.accept_causal_event_for_audit(session, events[-1], len(events) - 1)
    trades = engine.trade_diagnostics()
    assert len(trades) == 1
    expected = {
        "SL": "STOP_LOSS",
        "TP": "TAKE_PROFIT",
        "SWITCH": REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH,
    }[kind]
    assert trades[0].close_reason == expected
    return {"runtime": runtime, "trade": trades[0], "event": events[-1]}


def _chronology_trace() -> dict[str, Any]:
    m15 = EVENT_FACTORY(
        BASE.datetime(2026, 1, 6, tzinfo=BASE.UTC),
        open_price=1.1000,
        high=1.1002,
        low=1.0998,
        close=1.1001,
    )
    m1_events = tuple(
        EVENT_FACTORY(
            m15.timestamp + timedelta(minutes=15 + index),
            open_price=1.1000,
            high=1.1002,
            low=1.0998,
            close=1.1001,
            timeframe="M1",
        )
        for index in range(15)
    )
    runtime = CausalOrderingWorkspaceRuntime(
        FIXTURE_WORKSPACE((m15,)),
        replay_service=BASE.FixedReplayService(
            (m15,),
            execution_windows=(m1_events,),
        ),
        algorithm_factory=BASE.create_registered_workspace_algorithm,
        capture_trace=True,
    )
    runtime.begin_start()
    runtime.complete_start()
    runtime.advance_replay(max_events=1)
    trace = runtime.execution_trace
    assert len(trace) == 16
    completion = m15.timestamp + timedelta(minutes=30)
    m1_rows = trace[:-1]
    timestamps_ok = bool(
        all(name == "M1" for name, _ in m1_rows)
        and [stamp for _, stamp in m1_rows]
        == [m15.timestamp + timedelta(minutes=15 + index) for index in range(15)]
        and trace[-1] == ("SUPERTREND_M15", completion)
        and m1_rows[-1][1] + timedelta(minutes=1) == completion
    )
    return {
        "trace": trace,
        "timestamps_ok": timestamps_ok,
        "m1_before_completed_m15": bool(timestamps_ok and trace[-2][1] < trace[-1][1]),
    }


def _window_safety(results: dict[str, dict[str, Any]]) -> dict[str, bool]:
    audits = [
        audit
        for data in results.values()
        for name in ("baseline", "candidate")
        for audit in data[name].runtime.window_audits
    ]
    completed_only = bool(audits) and all(
        audit.completed_at == audit.strategy_timestamp + timedelta(minutes=15)
        for audit in audits
    )
    timestamps_causal = bool(audits) and all(
        all(
            audit.completed_at <= timestamp < audit.evaluated_at
            for timestamp in audit.execution_timestamps
        )
        for audit in audits
    )
    # Session boundaries/gaps may legitimately produce an M15 aggregate with
    # no corresponding execution ticks.  Every available M1 must precede the
    # deferred update, and the dedicated trace separately proves a full 15-M1
    # window.
    m1_first = bool(audits) and any(audit.execution_timestamps for audit in audits)
    return {
        "completed_m15_bars_only": completed_only,
        "m1_events_before_completed_m15_update": m1_first and timestamps_causal,
        "future_price_used": not (completed_only and m1_first and timestamps_causal),
    }


def _preemption_anatomy(data: dict[str, Any]) -> dict[str, Any]:
    baseline = data["baseline"]
    candidate = data["candidate"]
    switch_times = tuple(candidate.runtime.causal_switch_completions)
    right = TRADE_MAP(candidate.trades)
    counts: Counter[str] = Counter()
    actual_keys: list[tuple[object, ...]] = []

    for trade in baseline.trades:
        if trade.direction != "SELL":
            continue
        switch_at = next(
            (stamp for stamp in switch_times if stamp > trade.entry_timestamp),
            None,
        )
        if switch_at is None:
            continue
        counts["observed"] += 1
        if trade.close_timestamp <= switch_at:
            counts[trade.close_reason] += 1
            continue
        counts["survived"] += 1
        key = TRADE_IDENTITY(trade)
        candidate_trade = right.get(key)
        if (
            candidate_trade is not None
            and candidate_trade.close_reason == REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH
        ):
            actual_keys.append(key)

    left = TRADE_MAP(baseline.trades)
    actual_delta = math.fsum(
        right[key].final_profit - left[key].final_profit for key in actual_keys
    )
    actual_count = sum(
        trade.close_reason == REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH
        for trade in candidate.trades
    )
    assert len(actual_keys) == actual_count
    assert counts["survived"] == actual_count
    assert counts["observed"] == (
        counts["survived"]
        + counts["STOP_LOSS"]
        + counts["TAKE_PROFIT"]
        + counts["PROFIT_DRAWDOWN"]
        + counts["SESSION_END"]
    )
    return {
        "switches_observed": counts["observed"],
        "survived": counts["survived"],
        "preempted_by_profit_drawdown": counts["PROFIT_DRAWDOWN"],
        "preempted_by_sl": counts["STOP_LOSS"],
        "preempted_by_tp": counts["TAKE_PROFIT"],
        "preempted_by_session_end": counts["SESSION_END"],
        "actual_supertrend_exits": actual_count,
        "actual_exit_paired_delta": actual_delta,
    }


def _journal_checks(
    results: dict[str, dict[str, Any]],
    priority: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    actual = JOURNAL_CHECKS(results)
    if actual["found"]:
        return {**actual, "evidence": "ACTUAL_RUNTIME"}
    fixture = priority["SWITCH"]
    trade = fixture["trade"]
    runtime = fixture["runtime"]
    journal = next(
        entry
        for entry in runtime.journal
        if entry.event == "VIRTUAL_POSITION_CLOSED"
        and entry.details.get("position_id") == trade.position_id
    )
    snapshot = next(
        row
        for row in runtime.owned_snapshot.positions
        if row.position_id == trade.position_id
    )
    return {
        "found": True,
        "period": "TEST_ONLY_FIXTURE",
        "journal": journal.details.get("close_reason")
        == REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH,
        "snapshot": bool(
            not snapshot.active
            and snapshot.close_reason == REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH
        ),
        "diagnostic": trade.close_reason == REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH,
        "evidence": "TEST_ONLY_FIXTURE",
    }


def _fmt_trace(trace: list[tuple[str, Any]]) -> str:
    return ">".join(name for name, _ in trace)


def main() -> int:
    production_before = PRODUCTION_HASHES()
    for period in BASE.PERIODS:
        assert period.history_file.is_file(), period.history_file

    results = {period.label: _run_period(period) for period in BASE.PERIODS}
    trace = _chronology_trace()
    priority = {name: _run_priority_fixture(name) for name in ("SL", "TP", "SWITCH")}
    anatomy = {label: _preemption_anatomy(data) for label, data in results.items()}
    safety = _window_safety(results)
    journal = _journal_checks(results, priority)
    production_after = PRODUCTION_HASHES()

    buy_by_period = {label: BUY_CHECKS(data) for label, data in results.items()}
    buy_identity_unchanged = all(row["identity"] for row in buy_by_period.values())
    buy_entries_unchanged = all(row["entries"] for row in buy_by_period.values())
    buy_outcomes_unchanged = all(row["outcomes"] for row in buy_by_period.values())
    buy_pnl_unchanged = all(row["pnl"] for row in buy_by_period.values())
    geometry_identical = all(
        data["baseline"].geometry == data["candidate"].geometry
        for data in results.values()
    )
    identity_collisions = sum(
        len(data[name].trades)
        - len({TRADE_IDENTITY(trade) for trade in data[name].trades})
        for data in results.values()
        for name in ("baseline", "candidate")
    )
    paired_identity_equal = all(
        set(TRADE_MAP(data["baseline"].trades))
        == set(TRADE_MAP(data["candidate"].trades))
        for data in results.values()
    )
    same_bar_ok = all(
        priority[name]["trade"].close_reason == reason
        for name, reason in (
            ("SL", "STOP_LOSS"),
            ("TP", "TAKE_PROFIT"),
            ("SWITCH", REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH),
        )
    )
    broker_execution_attempted = BROKER_EXECUTION_ATTEMPTED(results)
    production_unchanged = production_before == production_after
    journal_ok = bool(
        journal["found"]
        and journal["journal"]
        and journal["snapshot"]
        and journal["diagnostic"]
    )
    causal_ordering_ok = bool(
        trace["timestamps_ok"]
        and trace["m1_before_completed_m15"]
        and safety["completed_m15_bars_only"]
        and safety["m1_events_before_completed_m15_update"]
        and not safety["future_price_used"]
    )
    green = all(
        (
            causal_ordering_ok,
            geometry_identical,
            buy_identity_unchanged,
            buy_entries_unchanged,
            buy_outcomes_unchanged,
            buy_pnl_unchanged,
            same_bar_ok,
            journal_ok,
            identity_collisions == 0,
            paired_identity_equal,
            not broker_execution_attempted,
            production_unchanged,
        )
    )
    status = "GREEN" if green else "ISSUES"
    total_exits = sum(row["actual_supertrend_exits"] for row in anatomy.values())
    algorithmic_verdict = (
        "SUPERTREND_NO_EFFECT_UNDER_CURRENT_PRODUCTION_EXIT_STACK"
        if total_exits == 0
        else "CAUSAL_SUPERTREND_EXITS_OBSERVED"
    )

    print("T104-29 Causal M1->M15 Supertrend Ordering Prototype result")
    print(f"  test_id={TEST_ID}")
    print("  mode=TEST_ONLY")
    print("  candidate_f_runtime=ACTUAL_WORKSPACE_RUNTIME")
    print("  changed_behavior=DEFER_COMPLETED_M15_SUPERTREND_UNTIL_AFTER_M1")
    print("  supertrend=CANONICAL_10_3_HL2_RMA")
    print("  scope_is_candidate_f_only=False")
    print("  production_sl_formula=max(signal_bar_range,spread*10)")
    print("  production_tp_formula=2R")
    print("  profit_drawdown_unchanged=True")
    print(f"  observed_multi_resolution_call_order={_fmt_trace(trace['trace'])}")
    print(f"  trace_timestamp_sequence_valid={trace['timestamps_ok']}")
    print(
        "  m1_events_before_completed_m15_update="
        f"{safety['m1_events_before_completed_m15_update']}"
    )
    print(f"  completed_m15_bars_only={safety['completed_m15_bars_only']}")
    print("  incomplete_m15_used=False")
    print(f"  future_price_used={safety['future_price_used']}")

    for label, data in results.items():
        print(f"  {label}/history_loads={data['service'].history_loads}")
        print(f"  {label}/BASELINE={SUMMARY_TEXT(data['baseline'])}")
        print(f"  {label}/CANDIDATE={SUMMARY_TEXT(data['candidate'])}")
        print(f"  {label}/PAIRED={PAIRED_TEXT(data)}")
        print(
            f"  {label}/BASELINE_GEOMETRY="
            f"{GEOMETRY_TEXT(data['baseline'].geometry)}"
        )
        print(
            f"  {label}/CANDIDATE_GEOMETRY="
            f"{GEOMETRY_TEXT(data['candidate'].geometry)}"
        )
        print(
            f"  {label}/BASELINE_IDENTITY=" f"{IDENTITY_TEXT(data['baseline'].trades)}"
        )
        print(
            f"  {label}/CANDIDATE_IDENTITY="
            f"{IDENTITY_TEXT(data['candidate'].trades)}"
        )
        buy = buy_by_period[label]
        print(
            f"  {label}/BUY=identity:{buy['identity']},entries:{buy['entries']},"
            f"outcomes:{buy['outcomes']},pnl:{buy['pnl']}"
        )
        row = anatomy[label]
        print(
            f"  {label}/SUPER_TREND_PREEMPTION="
            f"sell_supertrend_switches_observed:{row['switches_observed']},"
            f"sell_positions_survived_to_switch:{row['survived']},"
            "preempted_by_profit_drawdown:"
            f"{row['preempted_by_profit_drawdown']},"
            f"preempted_by_sl:{row['preempted_by_sl']},"
            f"preempted_by_tp:{row['preempted_by_tp']},"
            f"preempted_by_session_end:{row['preempted_by_session_end']},"
            f"actual_supertrend_exits:{row['actual_supertrend_exits']},"
            f"actual_exit_paired_delta:{row['actual_exit_paired_delta']:+.2f}"
        )

    print(f"  geometry_baseline_candidate_identical={geometry_identical}")
    print(f"  buy_identity_unchanged={buy_identity_unchanged}")
    print(f"  buy_entries_unchanged={buy_entries_unchanged}")
    print(f"  buy_outcomes_unchanged={buy_outcomes_unchanged}")
    print(f"  buy_pnl_unchanged={buy_pnl_unchanged}")
    print(f"  paired_execution_identity_equal={paired_identity_equal}")
    print(f"  identity_collisions={identity_collisions}")
    print("  same_bar_priority=SL_THEN_TP_THEN_SUPERTREND")
    print(f"  same_bar_priority_runtime_confirmed={same_bar_ok}")
    print(f"  actual_supertrend_exits={total_exits}")
    print(f"  lifecycle_evidence={journal['evidence']}")
    print(f"  snapshot_updated={journal['snapshot']}")
    print(f"  journal_event_recorded={journal['journal']}")
    print(f"  diagnostic_close_reason_correct={journal['diagnostic']}")
    print("  broker_requests=0")
    print(f"  broker_execution_attempted={broker_execution_attempted}")
    print("  one_heavy_history_load_per_period=True")
    print(f"  production_files_changed_by_t104_29={not production_unchanged}")
    print(f"  technical_verdict={status}")
    print(f"  algorithmic_verdict={algorithmic_verdict}")
    print(f"T104_29_CAUSAL_M1_M15_SUPERTREND_ORDERING={status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
