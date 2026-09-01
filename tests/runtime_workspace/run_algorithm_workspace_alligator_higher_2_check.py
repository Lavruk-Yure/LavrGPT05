# -*- coding: utf-8 -*-
"""Перевірка експериментального Alligator HIGHER_2 у Replay."""

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
    AlgorithmWorkspace,
)
from core.timeframes import (  # noqa: E402
    WorkspaceTimeframeResolutionError,
)
from core.workspace_algorithm import WorkspaceAlgorithmError  # noqa: E402
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_CONFIRMATION_HIGHER_2_BEARISH,
    ALLIGATOR_CONFIRMATION_HIGHER_2_BULLISH,
    ALLIGATOR_CONFIRMATION_HIGHER_2_WARMUP,
    ALLIGATOR_REASON_HIGHER_2_BUY_ALLOW,
    ALLIGATOR_REASON_HIGHER_2_BUY_REJECT,
    ALLIGATOR_REASON_HIGHER_2_NOT_READY,
    ALLIGATOR_REASON_HIGHER_2_SELL_ALLOW,
    ALLIGATOR_REASON_HIGHER_2_SELL_REJECT,
    ALLIGATOR_REQUIRED_BARS,
    WorkspaceAlligatorFilter,
    WorkspaceAlligatorObservation,
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_broker_market import (  # noqa: E402
    WorkspaceBrokerMarketProviderProtocol,
)
from core.workspace_macd import MACD_REQUIRED_BARS  # noqa: E402
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_replay import (  # noqa: E402
    WorkspaceReplayService,
    WorkspaceReplaySession,
)
from core.workspace_runtime import (  # noqa: E402
    WorkspaceJournalEntry,
    WorkspaceRuntime,
    WorkspaceRuntimeContext,
)
from core.workspace_signal import (  # noqa: E402
    WORKSPACE_SIGNAL_FILTER_ALLOW,
    WORKSPACE_SIGNAL_FILTER_REJECT,
    WorkspaceSignalRecord,
)
from engine.runtime_constants import (  # noqa: E402
    DEFAULT_WORKSPACE_ALLIGATOR_CONFIRMATION,
    WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2,
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
    WORKSPACE_ALLIGATOR_HIGHER_2_EXPERIMENTAL,
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
            source_name="ALLIGATOR_HIGHER_2_TEST",
            speed=int(settings.get("speed", 1)),
        )


def _append_segment(
    closes: list[float],
    count: int,
    delta: float,
) -> None:
    start = closes[-1]
    closes.extend(start + (index + 1) * delta for index in range(count))


def _closes() -> tuple[float, ...]:
    closes: list[float] = [1.2000] * 35
    _append_segment(closes, 24, 0.00015)
    _append_segment(closes, 24, -0.00015)
    closes.extend([closes[-1]] * (336 - len(closes)))
    _append_segment(closes, 96, 0.00008)
    _append_segment(closes, 24, -0.00005)
    _append_segment(closes, 64, 0.00007)
    _append_segment(closes, 192, -0.00010)
    _append_segment(closes, 24, 0.00005)
    _append_segment(closes, 64, -0.00008)
    return tuple(closes)


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


def _events() -> tuple[WorkspaceMarketEvent, ...]:
    return tuple(_event(index, close) for index, close in enumerate(_closes()))


def _workspace(*, speed: int = 1) -> AlgorithmWorkspace:
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
            "alligator_filter_enabled": True,
            "alligator_confirmation": WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2,
            "warmup_bars": 2,
            "spread_limit": 0.00020,
        },
        replay_settings={"speed": speed},
    )


def _run(
    events: tuple[WorkspaceMarketEvent, ...],
    *,
    workspace: AlgorithmWorkspace,
    speed: int,
    step_mode: bool = False,
) -> tuple[
    tuple[WorkspaceSignalRecord, ...],
    tuple[WorkspaceJournalEntry, ...],
    WorkspaceMacdAlligatorReplayAlgorithm,
    WorkspaceRuntime,
    int,
]:
    replay_settings = dict(workspace.replay_settings)
    replay_settings["speed"] = speed
    run_workspace = replace(workspace, replay_settings=replay_settings)
    algorithm = WorkspaceMacdAlligatorReplayAlgorithm(run_workspace.algorithm)
    broker_probe = BrokerRequestProbe()
    runtime = WorkspaceRuntime(
        run_workspace,
        replay_service=FixedReplayService(events),
        algorithm_factory=lambda _algorithm_id: algorithm,
        broker_market_provider=broker_probe,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    if step_mode:
        assert runtime.toggle_replay_pause()
        while not session.completed:
            assert runtime.step_replay() is not None
    else:
        while not session.completed:
            runtime.advance_replay()
    return (
        runtime.signal_records(),
        tuple(runtime.journal),
        algorithm,
        runtime,
        broker_probe.requests,
    )


def _assert_future_change_is_causal(
    baseline_records: tuple[WorkspaceSignalRecord, ...],
    workspace: AlgorithmWorkspace,
) -> None:
    events = _events()
    prefix_size = 650
    future_start = events[prefix_size].timestamp
    changed_events = list(events[:prefix_size])
    for index, event in enumerate(events[prefix_size:]):
        changed_close = event.close + 0.0500 + index * 0.0010
        changed_events.append(
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
    changed_records = _run(
        tuple(changed_events),
        workspace=workspace,
        speed=1,
    )[0]
    baseline_prefix = tuple(
        record for record in baseline_records if record.timestamp < future_start
    )
    changed_prefix = tuple(
        record for record in changed_records if record.timestamp < future_start
    )
    assert changed_prefix == baseline_prefix


def _feed_public_algorithm_path(
    algorithm: WorkspaceMacdAlligatorReplayAlgorithm,
    event: WorkspaceMarketEvent,
) -> WorkspaceAlligatorObservation | None:
    """Повернути доступний Alligator стан через public Replay pipeline."""
    algorithm.on_market_event(event)
    if not algorithm.higher_timeframe_synchronized:
        return None
    signal_filter = algorithm.signal_filter
    assert signal_filter is not None
    return signal_filter.latest_observation


def _assert_incomplete_higher_bucket_breaks_sync(
    workspace: AlgorithmWorkspace,
) -> None:
    algorithm = WorkspaceMacdAlligatorReplayAlgorithm(workspace.algorithm)
    context = WorkspaceRuntimeContext.from_workspace(workspace)
    algorithm.configure(context, workspace.parameters)
    algorithm.start()

    observation = None
    for index in range(353):
        observation = _feed_public_algorithm_path(
            algorithm,
            _event(index, 1.2000),
        )
    assert observation is not None
    assert algorithm.higher_timeframe_synchronized

    for index in range(354, 368):
        assert _feed_public_algorithm_path(algorithm, _event(index, 1.2000)) is not None
        assert algorithm.higher_timeframe_synchronized

    assert _feed_public_algorithm_path(algorithm, _event(368, 1.2000)) is None
    assert not algorithm.higher_timeframe_synchronized

    for index in range(369, 384):
        assert _feed_public_algorithm_path(algorithm, _event(index, 1.2000)) is None
        assert not algorithm.higher_timeframe_synchronized

    recovered = _feed_public_algorithm_path(
        algorithm,
        _event(384, 1.2000),
    )
    assert recovered is not None
    assert algorithm.higher_timeframe_synchronized


def _assert_unavailable_pair_has_no_fallback(
    workspace: AlgorithmWorkspace,
) -> None:
    unavailable_workspace = replace(workspace, timeframe="H4")
    algorithm = WorkspaceMacdAlligatorReplayAlgorithm(unavailable_workspace.algorithm)
    context = WorkspaceRuntimeContext.from_workspace(unavailable_workspace)
    blocked = False
    try:
        algorithm.configure(context, unavailable_workspace.parameters)
    except WorkspaceTimeframeResolutionError:
        blocked = True
    assert blocked


def _assert_disabled_filter_ignores_stale_mode(
    workspace: AlgorithmWorkspace,
) -> None:
    parameters = dict(workspace.parameters)
    parameters["alligator_filter_enabled"] = False
    disabled_workspace = replace(
        workspace,
        timeframe="H4",
        parameters=parameters,
    )
    algorithm = WorkspaceMacdAlligatorReplayAlgorithm(disabled_workspace.algorithm)
    context = WorkspaceRuntimeContext.from_workspace(disabled_workspace)
    algorithm.configure(context, disabled_workspace.parameters)
    assert algorithm.signal_filter is not None
    assert not algorithm.signal_filter.active
    assert algorithm.signal_filter.timeframe == "H4"
    assert algorithm.timeframe_aggregator is None


def _assert_unresolved_direct_filter_is_blocked() -> None:
    signal_filter = WorkspaceAlligatorFilter(
        enabled=True,
        confirmation_mode=WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2,
    )
    blocked = False
    try:
        _ = signal_filter.required_bars
    except WorkspaceAlgorithmError:
        blocked = True
    assert blocked


def main() -> None:
    events = _events()
    workspace = _workspace()
    run_1x = _run(events, workspace=workspace, speed=1)
    run_10x = _run(events, workspace=workspace, speed=10)
    run_step = _run(
        events,
        workspace=workspace,
        speed=1,
        step_mode=True,
    )

    records, journal, algorithm, runtime, broker_requests = run_1x
    assert run_10x[0] == records
    assert run_step[0] == records
    assert len(records) == 8
    assert broker_requests == 0
    assert run_10x[4] == 0
    assert run_step[4] == 0

    signal_filter = algorithm.signal_filter
    aggregator = algorithm.timeframe_aggregator
    assert signal_filter is not None
    assert aggregator is not None
    assert signal_filter.confirmation_mode == WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2
    assert signal_filter.timeframe == "H4"
    assert signal_filter.required_bars == ALLIGATOR_REQUIRED_BARS
    assert aggregator.source_timeframe == "M15"
    assert aggregator.target_timeframe == "H4"
    assert aggregator.expected_source_bars == 16
    assert len(signal_filter.observations) == aggregator.completed_bars
    assert aggregator.completed_bars == 49
    assert aggregator.dropped_incomplete_buckets == 0
    assert aggregator.active_source_bars == 16
    assert all(item.timeframe == "H4" for item in signal_filter.observations)
    assert all(
        item.available_at == item.timestamp + timedelta(hours=4)
        for item in signal_filter.observations
    )

    assert runtime.context.warmup_bars_required == MACD_REQUIRED_BARS
    assert runtime.context.warmup_required_by_timeframe == {
        "H4": ALLIGATOR_REQUIRED_BARS,
        "M15": MACD_REQUIRED_BARS,
    }
    assert runtime.context.warmup_components_by_timeframe == {
        "H4": ("ALLIGATOR",),
        "M15": ("MACD",),
    }
    requirements = algorithm.warmup_requirements() or ()
    assert tuple(
        (item.component_code, item.timeframe, item.required_bars)
        for item in requirements
    ) == (
        ("MACD", "M15", MACD_REQUIRED_BARS),
        ("ALLIGATOR", "H4", ALLIGATOR_REQUIRED_BARS),
    )

    expected_reasons = {
        ALLIGATOR_REASON_HIGHER_2_NOT_READY: 3,
        ALLIGATOR_REASON_HIGHER_2_BUY_ALLOW: 1,
        ALLIGATOR_REASON_HIGHER_2_SELL_REJECT: 2,
        ALLIGATOR_REASON_HIGHER_2_BUY_REJECT: 1,
        ALLIGATOR_REASON_HIGHER_2_SELL_ALLOW: 1,
    }
    actual_reasons = {
        reason: sum(record.filter_reason_code == reason for record in records)
        for reason in expected_reasons
    }
    assert actual_reasons == expected_reasons
    accepted = tuple(record for record in records if record.accepted)
    rejected = tuple(record for record in records if not record.accepted)
    assert len(accepted) == 2
    assert len(rejected) == 6
    assert [record.direction for record in accepted] == ["BUY", "SELL"]
    assert [record.alligator_confirmation for record in accepted] == [
        ALLIGATOR_CONFIRMATION_HIGHER_2_BULLISH,
        ALLIGATOR_CONFIRMATION_HIGHER_2_BEARISH,
    ]
    assert (
        sum(
            record.alligator_confirmation == ALLIGATOR_CONFIRMATION_HIGHER_2_WARMUP
            for record in rejected
        )
        == 3
    )
    assert all(
        record.filter_decision
        in {WORKSPACE_SIGNAL_FILTER_ALLOW, WORKSPACE_SIGNAL_FILTER_REJECT}
        for record in records
    )
    assert all(record.risk_execution_attempted is False for record in records)
    assert all("alligator_timeframe=H4" in record.reason for record in records)

    signal_journal = tuple(
        entry
        for entry in journal
        if entry.event in {"SIGNAL_ACCEPTED", "SIGNAL_REJECTED"}
    )
    assert len(signal_journal) == len(records)
    assert all(entry.details.get("filter_reason_code") for entry in signal_journal)
    warmup_journal = next(
        entry for entry in journal if entry.event == "WARMUP_REQUIREMENTS_APPLIED"
    )
    assert warmup_journal.details["required_by_timeframe"] == {
        "H4": ALLIGATOR_REQUIRED_BARS,
        "M15": MACD_REQUIRED_BARS,
    }

    assert WORKSPACE_ALLIGATOR_HIGHER_2_EXPERIMENTAL is True
    assert (
        DEFAULT_WORKSPACE_ALLIGATOR_CONFIRMATION
        == WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME
    )
    _assert_future_change_is_causal(records, workspace)
    _assert_incomplete_higher_bucket_breaks_sync(workspace)
    _assert_unavailable_pair_has_no_fallback(workspace)
    _assert_disabled_filter_ignores_stale_mode(workspace)
    _assert_unresolved_direct_filter_is_blocked()

    print("Algorithm Workspace Alligator HIGHER_2 result")
    print("  experimental_mode=True")
    print("  default_unchanged=SAME_TIMEFRAME")
    print("  base_timeframe=M15")
    print("  macd_timeframe=M15")
    print("  alligator_timeframe=H4")
    print(f"  macd_warmup={MACD_REQUIRED_BARS}")
    print(f"  alligator_warmup={ALLIGATOR_REQUIRED_BARS}")
    print("  source_bars_per_higher_bar=16")
    print("  completed_higher_bars=49")
    print("  final_higher_bar_waits_for_close_boundary=True")
    print("  signals=8")
    print("  allowed=2")
    print("  rejected=6")
    print("  higher_warmup_rejected=3")
    print("  allow_reject_reason_codes=True")
    print("  signal_journal_connected=True")
    print("  no_look_ahead=True")
    print("  future_change_does_not_change_past=True")
    print("  incomplete_higher_bucket_breaks_sync=True")
    print("  sync_recovers_on_next_complete_higher_bar=True")
    print("  unavailable_pair_blocked_without_fallback=True")
    print("  disabled_filter_ignores_stale_higher_mode=True")
    print("  speed_1x_10x_step_deterministic=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_ALLIGATOR_HIGHER_2_CHECK=OK")


if __name__ == "__main__":
    main()
