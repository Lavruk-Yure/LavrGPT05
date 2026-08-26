# -*- coding: utf-8 -*-
"""Перевірка Alligator SAME_TIMEFRAME у Replay WSP.

Тест контролює causal ALLOW/REJECT, profile snapshot, warm-up, determinism і
SAME_TIMEFRAME phase-gate: лише ACTIVE у напрямі тренду може пройти;
STARTING, ENDING і FLAT відхиляються. HIGHER_1/HIGHER_2 тут не змінюються.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_MANUAL,
    WORKSPACE_DATA_MODE_REPLAY,
    WORKSPACE_STATE_RUNNING,
    AlgorithmWorkspace,
)
from core.workspace_algorithm import WorkspaceAlgorithmError  # noqa: E402
from core.workspace_broker_market import (  # noqa: E402
    WorkspaceBrokerMarketProviderProtocol,
)
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_COMPONENT_CODE,
    ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME_BEARISH,
    ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME_BULLISH,
    ALLIGATOR_REGIME_FLAT,
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_PHASE_ENDING,
    ALLIGATOR_REGIME_PHASE_NONE,
    ALLIGATOR_REGIME_PHASE_STARTING,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    ALLIGATOR_STATE_BEARISH,
    ALLIGATOR_STATE_BULLISH,
    WorkspaceAlligatorFilter,
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_indicator_profile import (  # noqa: E402
    default_workspace_indicator_profile_bindings,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_replay import (  # noqa: E402
    WorkspaceReplayService,
    WorkspaceReplaySession,
)
from core.workspace_runtime import (  # noqa: E402
    WorkspaceJournalEntry,
    WorkspaceRuntime,
)
from core.workspace_signal import (  # noqa: E402
    WORKSPACE_SIGNAL_FILTER_ALLOW,
    WORKSPACE_SIGNAL_FILTER_REJECT,
    WorkspaceSignalProposal,
    WorkspaceSignalRecord,
)


class BrokerRequestProbe(WorkspaceBrokerMarketProviderProtocol):
    def __init__(self) -> None:
        self.requests = 0

    def start_workspace(
        self,
        *,
        workspace_uid: str,
        broker: str,
        account_id: str | None,
        symbol: str,
        timeframe: str,
        warmup_bars: int,
        spread_limit: float,
    ) -> tuple[WorkspaceMarketEvent, ...]:
        _ = (
            workspace_uid,
            broker,
            account_id,
            symbol,
            timeframe,
            warmup_bars,
            spread_limit,
        )
        self.requests += 1
        return ()

    def poll_workspace(
        self,
        workspace_uid: str,
    ) -> WorkspaceMarketEvent | None:
        _ = workspace_uid
        self.requests += 1
        return None

    def is_workspace_broker_connected(self, workspace_uid: str) -> bool:
        _ = workspace_uid
        self.requests += 1
        return True

    def suspend_workspace(self, workspace_uid: str) -> None:
        _ = workspace_uid
        self.requests += 1

    def resume_workspace(
        self,
        workspace_uid: str,
    ) -> tuple[WorkspaceMarketEvent, ...]:
        _ = workspace_uid
        self.requests += 1
        return ()

    def stop_workspace(self, workspace_uid: str) -> None:
        _ = workspace_uid
        self.requests += 1


class FixedReplayService(WorkspaceReplayService):
    def __init__(
        self,
        events: tuple[WorkspaceMarketEvent, ...],
    ) -> None:
        super().__init__()
        self.events = events

    def create_synthetic_session(
        self,
        *,
        broker: str,
        symbol: str,
        timeframe: str,
        replay_settings: dict[str, Any] | None = None,
    ) -> WorkspaceReplaySession:
        _ = broker, symbol, timeframe
        settings = dict(replay_settings or {})
        return WorkspaceReplaySession(
            events=self.events,
            source_name="ALLIGATOR_SAME_TIMEFRAME_TEST",
            speed=int(settings.get("speed", 1)),
        )


def _event(index: int, close: float) -> WorkspaceMarketEvent:
    spread = 0.00012
    bid = close - spread / 2.0
    ask = close + spread / 2.0
    return WorkspaceMarketEvent(
        timestamp=datetime(2026, 7, 28, 8, 0, tzinfo=UTC)
        + timedelta(minutes=15 * index),
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        bid=bid,
        ask=ask,
        spread=ask - bid,
        open=close,
        high=close + 0.00020,
        low=close - 0.00020,
        close=close,
        volume=100.0 + index,
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
    )


def _closes() -> tuple[float, ...]:
    closes: list[float] = [1.2000] * 35
    closes.extend(1.2000 + index * 0.0005 for index in range(30))
    closes.extend(1.2150 - index * 0.0002 for index in range(8))
    closes.extend(1.2134 + index * 0.0004 for index in range(20))
    closes.extend(1.2214 - index * 0.0006 for index in range(40))

    last_close = closes[-1]
    closes.extend(
        last_close + (index + 1) * 0.00045
        for index in range(12)
    )
    last_close = closes[-1]
    closes.extend(
        last_close - (index + 1) * 0.0005
        for index in range(25)
    )
    return tuple(closes)


def _events() -> tuple[WorkspaceMarketEvent, ...]:
    return tuple(
        _event(index, close)
        for index, close in enumerate(_closes())
    )


def _workspace(
    *,
    filter_enabled: bool,
    speed: int = 1,
) -> AlgorithmWorkspace:
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_MANUAL,
        parameters={
            "macd_signal_enabled": True,
            "macd_signal_mode": "LINEAR",
            "alligator_filter_enabled": filter_enabled,
            "alligator_confirmation": (
                "SAME_TIMEFRAME" if filter_enabled else "DISABLED"
            ),
            "warmup_bars": 2,
            "spread_limit": 0.00020,
        },
        replay_settings={"speed": speed},
        indicator_profile_bindings=(
            default_workspace_indicator_profile_bindings()
        ),
    )


def _run(
    workspace: AlgorithmWorkspace,
    *,
    speed: int = 1,
    step_mode: bool = False,
) -> tuple[
    tuple[WorkspaceSignalRecord, ...],
    int,
    tuple[WorkspaceJournalEntry, ...],
    WorkspaceMacdAlligatorReplayAlgorithm,
    int,
]:
    events = _events()
    replay_settings = dict(workspace.replay_settings)
    replay_settings["speed"] = speed
    run_workspace = replace(workspace, replay_settings=replay_settings)
    algorithm = WorkspaceMacdAlligatorReplayAlgorithm(
        run_workspace.algorithm
    )
    broker_probe = BrokerRequestProbe()
    runtime = WorkspaceRuntime(
        run_workspace,
        replay_service=FixedReplayService(events),
        algorithm_factory=lambda _algorithm_id: algorithm,
        broker_market_provider=broker_probe,
    )
    runtime.begin_start()
    runtime.complete_start()
    computed_warmup = runtime.context.warmup_bars_required
    session = runtime.replay_session
    assert session is not None

    if step_mode:
        assert runtime.toggle_replay_pause()
        while not session.completed:
            assert runtime.step_replay() is not None
    else:
        while not session.completed:
            runtime.advance_replay()

    assert runtime.context.runtime_state == WORKSPACE_STATE_RUNNING
    return (
        runtime.signal_records(),
        computed_warmup,
        tuple(runtime.journal),
        algorithm,
        broker_probe.requests,
    )


def _assert_causal_history() -> None:
    events = _events()
    prefix_size = 90
    baseline = WorkspaceAlligatorFilter(
        enabled=True,
        confirmation_mode="SAME_TIMEFRAME",
    )
    changed_future = WorkspaceAlligatorFilter(
        enabled=True,
        confirmation_mode="SAME_TIMEFRAME",
    )
    for event in events[:prefix_size]:
        baseline.on_market_event(event)
        changed_future.on_market_event(event)

    future_start = events[prefix_size].timestamp
    for index, event in enumerate(events[prefix_size:]):
        changed_close = event.close + 0.0500 + index * 0.0010
        changed_future.on_market_event(
            replace(
                event,
                open=changed_close,
                high=changed_close + 0.00020,
                low=changed_close - 0.00020,
                close=changed_close,
                bid=changed_close - 0.00006,
                ask=changed_close + 0.00006,
                spread=0.00012,
            )
        )

    changed_prefix = changed_future.observations[:prefix_size]
    assert baseline.observations == changed_prefix
    assert changed_future.observations[prefix_size].timestamp == future_start


def _assert_same_timeframe_phase_gate(
    signal_filter: WorkspaceAlligatorFilter,
) -> None:
    """Перевірити phase-gate незалежно від випадкових MACD crossing."""
    latest = signal_filter.latest_observation
    assert latest is not None
    assert latest.warmed_up

    buy = WorkspaceSignalProposal(
        signal_type="MACD_CROSS",
        direction="BUY",
        strength=0.0001,
        macd_state="MACD_CROSS_UP",
        alligator_confirmation="DISABLED",
    )
    sell = replace(
        buy,
        direction="SELL",
        macd_state="MACD_CROSS_DOWN",
    )

    bullish_active = replace(
        latest,
        state=ALLIGATOR_STATE_BULLISH,
        regime=ALLIGATOR_REGIME_TREND_UP,
        regime_phase=ALLIGATOR_REGIME_PHASE_ACTIVE,
    )
    bearish_active = replace(
        latest,
        state=ALLIGATOR_STATE_BEARISH,
        regime=ALLIGATOR_REGIME_TREND_DOWN,
        regime_phase=ALLIGATOR_REGIME_PHASE_ACTIVE,
    )
    starting = replace(
        bullish_active,
        regime_phase=ALLIGATOR_REGIME_PHASE_STARTING,
    )
    ending = replace(
        bearish_active,
        regime_phase=ALLIGATOR_REGIME_PHASE_ENDING,
    )
    flat = replace(
        bullish_active,
        regime=ALLIGATOR_REGIME_FLAT,
        regime_phase=ALLIGATOR_REGIME_PHASE_NONE,
    )

    buy_active = signal_filter.evaluate(
        buy,
        bullish_active,
        proposal_timestamp=latest.timestamp,
    )
    sell_active = signal_filter.evaluate(
        sell,
        bearish_active,
        proposal_timestamp=latest.timestamp,
    )
    buy_starting = signal_filter.evaluate(
        buy,
        starting,
        proposal_timestamp=latest.timestamp,
    )
    sell_ending = signal_filter.evaluate(
        sell,
        ending,
        proposal_timestamp=latest.timestamp,
    )
    buy_flat = signal_filter.evaluate(
        buy,
        flat,
        proposal_timestamp=latest.timestamp,
    )

    assert buy_active.allowed
    assert sell_active.allowed
    assert not buy_starting.allowed
    assert not sell_ending.allowed
    assert not buy_flat.allowed
    assert (
        buy_starting.reason_code
        == "ALLIGATOR_SAME_TIMEFRAME_BUY_STARTING_REJECT"
    )
    assert (
        sell_ending.reason_code
        == "ALLIGATOR_SAME_TIMEFRAME_SELL_ENDING_REJECT"
    )
    assert buy_flat.reason_code == "ALLIGATOR_SAME_TIMEFRAME_BUY_REJECT"


def main() -> None:
    workspace = _workspace(filter_enabled=True)
    run_1x = _run(workspace, speed=1)
    run_10x = _run(workspace, speed=10)
    run_step = _run(workspace, speed=1, step_mode=True)

    records, computed_warmup, journal, algorithm, broker_requests = run_1x
    source = algorithm.source
    signal_filter = algorithm.signal_filter
    assert source is not None
    assert signal_filter is not None
    runtime_requirements = algorithm.warmup_requirements() or ()
    same_timeframe_requirements = tuple(
        requirement.required_bars
        for requirement in runtime_requirements
        if requirement.timeframe == workspace.timeframe
    )
    assert same_timeframe_requirements
    expected_runtime_warmup = max(same_timeframe_requirements)

    journal_events = tuple(entry.event for entry in journal)
    assert run_10x[0] == records
    assert run_step[0] == records
    assert computed_warmup == expected_runtime_warmup
    assert run_10x[1] == computed_warmup
    assert run_step[1] == computed_warmup
    assert len(records) == 6

    accepted = tuple(record for record in records if record.accepted)
    rejected = tuple(record for record in records if not record.accepted)
    assert len(accepted) == 1
    assert len(rejected) == 5
    assert [record.direction for record in accepted] == ["BUY"]
    assert [record.filter_decision for record in accepted] == [
        WORKSPACE_SIGNAL_FILTER_ALLOW,
    ]
    assert all(
        record.filter_decision == WORKSPACE_SIGNAL_FILTER_REJECT
        for record in rejected
    )
    bullish_confirmation = ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME_BULLISH
    bearish_confirmation = ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME_BEARISH
    assert accepted[0].alligator_confirmation == bullish_confirmation
    buy_allow_reason = "ALLIGATOR_SAME_TIMEFRAME_BUY_ALLOW"
    assert accepted[0].filter_reason_code == buy_allow_reason
    starting_sell = next(
        record
        for record in rejected
        if record.filter_reason_code
        == "ALLIGATOR_SAME_TIMEFRAME_SELL_STARTING_REJECT"
    )
    assert starting_sell.alligator_confirmation == bearish_confirmation
    assert all(record.risk_execution_attempted is False for record in records)
    alligator_contexts = tuple(
        record.filter_context
        for record in records
        if record.filter_context is not None
    )
    assert alligator_contexts
    assert all(context.regime is not None for context in alligator_contexts)
    assert all(context.regime_phase is not None for context in alligator_contexts)
    classified_contexts = tuple(
        context
        for context in alligator_contexts
        if context.regime != "ALLIGATOR_REGIME_WARMUP"
    )
    assert classified_contexts
    assert all(
        context.normalized_slope is not None
        for context in classified_contexts
    )
    assert all(
        context.normalized_opening is not None
        for context in classified_contexts
    )
    assert journal_events.count("SIGNAL_ACCEPTED") == 1
    assert journal_events.count("SIGNAL_REJECTED") == 5
    assert "WARMUP_REQUIREMENTS_APPLIED" in journal_events
    signal_journal = tuple(
        entry
        for entry in journal
        if entry.event in {"SIGNAL_ACCEPTED", "SIGNAL_REJECTED"}
    )
    assert len(signal_journal) == len(records)
    assert all(
        entry.details.get("filter_decision")
        in {WORKSPACE_SIGNAL_FILTER_ALLOW, WORKSPACE_SIGNAL_FILTER_REJECT}
        for entry in signal_journal
    )
    assert all(
        entry.details.get("filter_reason_code")
        for entry in signal_journal
    )
    assert broker_requests == 0
    assert run_10x[4] == 0
    assert run_step[4] == 0

    expected_macd_warmup = (
        source.runtime_profile.slow_period
        + source.runtime_profile.signal_period
        + source.runtime_profile.shift
    )
    expected_alligator_warmup = max(
        signal_filter.runtime_profile.jaw_period
        + signal_filter.runtime_profile.jaw_shift,
        signal_filter.runtime_profile.teeth_period
        + signal_filter.runtime_profile.teeth_shift,
        signal_filter.runtime_profile.lips_period
        + signal_filter.runtime_profile.lips_shift,
    )
    assert source.required_bars == expected_macd_warmup
    assert signal_filter.required_bars == expected_alligator_warmup
    assert any(
        observation.state == ALLIGATOR_STATE_BULLISH
        for observation in signal_filter.observations
    )
    assert any(
        observation.state == ALLIGATOR_STATE_BEARISH
        for observation in signal_filter.observations
    )

    _assert_same_timeframe_phase_gate(signal_filter)

    (
        disabled_records,
        disabled_warmup,
        _,
        disabled_algorithm,
        disabled_requests,
    ) = _run(_workspace(filter_enabled=False))
    disabled_source = disabled_algorithm.source
    assert disabled_source is not None
    assert disabled_warmup == disabled_source.required_bars
    assert len(disabled_records) == len(records)
    assert all(record.accepted for record in disabled_records)
    assert all(
        record.filter_decision == WORKSPACE_SIGNAL_FILTER_ALLOW
        for record in disabled_records
    )
    assert disabled_requests == 0

    duplicate_filter = WorkspaceAlligatorFilter(
        enabled=True,
        confirmation_mode="SAME_TIMEFRAME",
    )
    first_event = _events()[0]
    duplicate_filter.on_market_event(first_event)
    duplicate_blocked = False
    try:
        duplicate_filter.on_market_event(first_event)
    except WorkspaceAlgorithmError:
        duplicate_blocked = True
    assert duplicate_blocked

    unresolved_higher_filter = WorkspaceAlligatorFilter(
        enabled=True,
        confirmation_mode="HIGHER_1",
    )
    higher_1_requires_context = False
    try:
        _ = unresolved_higher_filter.required_bars
    except WorkspaceAlgorithmError:
        higher_1_requires_context = True
    assert higher_1_requires_context

    unresolved_higher_2_filter = WorkspaceAlligatorFilter(
        enabled=True,
        confirmation_mode="HIGHER_2",
    )
    higher_2_requires_context = False
    try:
        _ = unresolved_higher_2_filter.required_bars
    except WorkspaceAlgorithmError:
        higher_2_requires_context = True
    assert higher_2_requires_context

    _assert_causal_history()

    requirement_codes = tuple(
        requirement.component_code for requirement in runtime_requirements
    )
    assert requirement_codes == ("MACD", ALLIGATOR_COMPONENT_CODE)

    print("Algorithm Workspace Alligator SAME_TIMEFRAME result")
    print(f"  alligator_required_bars={signal_filter.required_bars}")
    print(f"  macd_required_bars={source.required_bars}")
    print(f"  runtime_required_bars={computed_warmup}")
    print(f"  signals={len(records)}")
    print(f"  allowed={len(accepted)}")
    print(f"  rejected={len(rejected)}")
    print("  active_bullish_buy_allowed=True")
    print("  active_bearish_sell_allowed=True")
    print("  starting_rejected=True")
    print("  ending_rejected=True")
    print("  flat_rejected=True")
    print("  opposite_or_neutral_rejected=True")
    print("  filter_disable_bypasses=True")
    print("  macd_alligator_warmup_aggregated=True")
    print("  profile_snapshot_pinned=True")
    print("  causal_shift_no_lookahead=True")
    print("  speed_1x_10x_step_deterministic=True")
    print("  duplicate_bar_blocked=True")
    print("  higher_1_requires_resolved_context=True")
    print("  higher_2_requires_resolved_context=True")
    print("  signal_journal_connected=True")
    print("  alligator_regime_context_attached=True")
    print("  alligator_regime_phase_context_attached=True")
    print("  same_timeframe_phase_gate_active=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_ALLIGATOR_SAME_TIMEFRAME_CHECK=OK")


if __name__ == "__main__":
    main()
