# -*- coding: utf-8 -*-
"""Перевірка порівняльної Replay-статистики Alligator режимів."""

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
from core.workspace_alligator import (  # noqa: E402
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_broker_market import (  # noqa: E402
    WorkspaceBrokerMarketProviderProtocol,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_replay import (  # noqa: E402
    WorkspaceReplayService,
    WorkspaceReplaySession,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402
from core.workspace_signal_statistics import (  # noqa: E402
    WorkspaceSignalComparisonReport,
    WorkspaceSignalQualityPolicy,
    WorkspaceSignalStatisticsError,
    WorkspaceSignalVariantStatistics,
    build_workspace_signal_comparison,
)
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_1,
    WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2,
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
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
            source_name="ALLIGATOR_STATISTICS_TEST",
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
    closes.extend([closes[-1]] * 16)
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


def _workspace(mode: str) -> AlgorithmWorkspace:
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
            "alligator_confirmation": mode,
            "warmup_bars": 2,
            "spread_limit": 0.00020,
        },
        replay_settings={"speed": 1},
    )


def _run(
    workspace: AlgorithmWorkspace,
    events: tuple[WorkspaceMarketEvent, ...],
    *,
    speed: int,
    step_mode: bool = False,
) -> tuple[tuple[WorkspaceSignalRecord, ...], int]:
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
    return runtime.signal_records(), broker_probe.requests


def _records_by_mode(
    events: tuple[WorkspaceMarketEvent, ...],
) -> tuple[
    tuple[tuple[WorkspaceSignalRecord, ...], ...],
    int,
]:
    variants: list[tuple[WorkspaceSignalRecord, ...]] = []
    broker_requests = 0
    for mode in (
        WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
        WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_1,
        WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2,
    ):
        workspace = _workspace(mode)
        records_1x, requests_1x = _run(workspace, events, speed=1)
        records_10x, requests_10x = _run(workspace, events, speed=10)
        records_step, requests_step = _run(
            workspace,
            events,
            speed=1,
            step_mode=True,
        )
        assert records_1x == records_10x == records_step
        variants.append(records_1x)
        broker_requests += requests_1x + requests_10x + requests_step
    return tuple(variants), broker_requests


def _assert_input_guards(
    variants: tuple[tuple[WorkspaceSignalRecord, ...], ...],
    events: tuple[WorkspaceMarketEvent, ...],
    policy: WorkspaceSignalQualityPolicy,
) -> None:
    duplicate_uid_blocked = False
    try:
        build_workspace_signal_comparison(
            (variants[0] + (variants[0][0],),),
            events,
            policy,
        )
    except WorkspaceSignalStatisticsError:
        duplicate_uid_blocked = True
    assert duplicate_uid_blocked

    duplicate_variant_blocked = False
    try:
        build_workspace_signal_comparison(
            (variants[0], variants[0]),
            events,
            policy,
        )
    except WorkspaceSignalStatisticsError:
        duplicate_variant_blocked = True
    assert duplicate_variant_blocked

    foreign_binding_blocked = False
    foreign_record = replace(variants[0][0], symbol="GBPUSD")
    try:
        build_workspace_signal_comparison(
            ((foreign_record,) + variants[0][1:],),
            events,
            policy,
        )
    except WorkspaceSignalStatisticsError:
        foreign_binding_blocked = True
    assert foreign_binding_blocked


def main() -> None:
    events = _events()
    record_variants, broker_requests = _records_by_mode(events)
    policy = WorkspaceSignalQualityPolicy(
        horizon_bars=8,
        minimum_directional_move=0.00020,
    )
    report: WorkspaceSignalComparisonReport = build_workspace_signal_comparison(
        record_variants,
        events,
        policy,
    )
    repeat: WorkspaceSignalComparisonReport = build_workspace_signal_comparison(
        record_variants,
        events,
        policy,
    )
    statistics: tuple[WorkspaceSignalVariantStatistics, ...] = report.variants
    assert report == repeat
    assert report.proposal_signatures_identical
    assert report.deterministic
    assert len(statistics) == 3
    assert {item.mode for item in statistics} == {
        WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
        WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_1,
        WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2,
    }
    signal_counts = {item.signals for item in statistics}
    assert len(signal_counts) == 1
    assert all(item.allowed + item.rejected == item.signals for item in statistics)
    assert all(item.profile_uid for item in statistics)
    assert all(item.profile_revision > 0 for item in statistics)
    by_mode = {item.mode: item for item in statistics}
    assert (
        by_mode[
            WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME
        ].confirmation_delay_average_seconds
        == 0.0
    )
    assert (
        by_mode[
            WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_1
        ].confirmation_delay_average_seconds
        == 3600.0
    )
    assert (
        by_mode[
            WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2
        ].confirmation_delay_average_seconds
        == 14400.0
    )
    assert report.broker_requests == 0
    assert not report.broker_execution_attempted
    assert broker_requests == 0
    _assert_input_guards(record_variants, events, policy)

    print("Algorithm Workspace Signal Statistics result")
    print(f"  policy_horizon_bars={report.policy.horizon_bars}")
    print(
        "  policy_minimum_directional_move="
        f"{report.policy.minimum_directional_move:.5f}"
    )
    print(f"  variants={len(statistics)}")
    print(f"  signals_per_variant={signal_counts.pop()}")
    for item in statistics:
        print(
            f"  {item.mode}: signals={item.signals}, "
            f"allow={item.allowed}, reject={item.rejected}, "
            f"delay_avg_s={item.confirmation_delay_average_seconds}, "
            f"missed={item.missed_signals}, "
            f"quality_before={item.quality_before_filter}, "
            f"quality_after={item.quality_after_filter}"
        )
    print("  profile_uid_revision_preserved=True")
    print("  proposal_signatures_identical=True")
    print("  duplicate_signal_uid_blocked=True")
    print("  duplicate_variant_blocked=True")
    print("  foreign_binding_blocked=True")
    print("  speed_1x_10x_step_deterministic=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_SIGNAL_STATISTICS_CHECK=OK")


if __name__ == "__main__":
    main()
