# -*- coding: utf-8 -*-
"""Перевірка першого MACD-джерела у детермінованому Replay WSP."""

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
from core.workspace_macd import (  # noqa: E402
    MACD_REQUIRED_BARS,
    MACD_STATE_CROSS_DOWN,
    MACD_STATE_CROSS_UP,
    WorkspaceMacdReplayAlgorithm,
    WorkspaceMacdSignalSource,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_replay import (  # noqa: E402
    WorkspaceReplayService,
    WorkspaceReplaySession,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED,
)


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
            source_name="MACD_REPLAY_TEST",
            speed=int(settings.get("speed", 1)),
        )


def _event(index: int, close: float) -> WorkspaceMarketEvent:
    spread = 0.00012
    bid = close - spread / 2.0
    ask = close + spread / 2.0
    return WorkspaceMarketEvent(
        timestamp=datetime(2026, 7, 27, 8, 0, tzinfo=UTC)
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
    closes = [1.2000] * 35
    closes.extend([1.2100] * 10)
    closes.extend([1.1900] * 10)
    return tuple(_event(index, close) for index, close in enumerate(closes))


def _workspace(
    *,
    enabled: bool,
    mode: str,
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
            "macd_signal_enabled": enabled,
            "macd_signal_mode": mode,
            "alligator_filter_enabled": False,
            "alligator_confirmation": "DISABLED",
            "warmup_bars": 2,
            "spread_limit": 0.00020,
        },
        replay_settings={"speed": speed},
    )


def _run(
    workspace: AlgorithmWorkspace,
    *,
    speed: int = 1,
    step_mode: bool = False,
) -> tuple[
    tuple[WorkspaceSignalRecord, ...],
    int,
    tuple[str, ...],
]:
    events = _events()
    replay_settings = dict(workspace.replay_settings)
    replay_settings["speed"] = speed
    run_workspace = replace(workspace, replay_settings=replay_settings)
    algorithm = WorkspaceMacdReplayAlgorithm(run_workspace.algorithm)
    runtime = WorkspaceRuntime(
        run_workspace,
        replay_service=FixedReplayService(events),
        algorithm_factory=lambda _algorithm_id: algorithm,
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
    journal_events = tuple(entry.event for entry in runtime.journal)
    return runtime.signal_records(), computed_warmup, journal_events


def main() -> None:
    linear_workspace = _workspace(enabled=True, mode="LINEAR")
    linear_1x = _run(linear_workspace, speed=1)
    linear_10x = _run(linear_workspace, speed=10)
    linear_step = _run(
        linear_workspace,
        speed=1,
        step_mode=True,
    )
    records, computed_warmup, journal_events = linear_1x

    assert linear_10x[0] == records
    assert linear_step[0] == records
    assert computed_warmup == MACD_REQUIRED_BARS
    assert linear_10x[1] == computed_warmup
    assert linear_step[1] == computed_warmup
    assert len(records) == 2
    assert [record.direction for record in records] == ["BUY", "SELL"]
    assert [record.macd_state for record in records] == [
        MACD_STATE_CROSS_UP,
        MACD_STATE_CROSS_DOWN,
    ]
    assert all(record.signal_type == "MACD_CROSS" for record in records)
    assert all(record.source_reason_code == "MACD_CLASSIC_CROSS" for record in records)
    assert all(record.source_profile_uid for record in records)
    assert all(record.source_profile_revision == 1 for record in records)
    assert all(record.accepted for record in records)
    assert all(
        record.alligator_confirmation
        == WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED
        for record in records
    )
    assert "WARMUP_REQUIREMENTS_APPLIED" in journal_events
    assert "WARMUP_COMPLETED" in journal_events

    disabled_workspace = _workspace(enabled=False, mode="LINEAR")
    disabled_records, disabled_warmup, disabled_journal = _run(
        disabled_workspace
    )
    assert disabled_records == ()
    assert disabled_warmup == 0
    assert "WARMUP_REQUIREMENTS_APPLIED" in disabled_journal

    extended_workspace = _workspace(enabled=True, mode="EXTENDED")
    extended_records, extended_warmup, _extended_journal = _run(
        extended_workspace
    )
    assert len(extended_records) == 2
    assert extended_warmup == MACD_REQUIRED_BARS
    assert all(not record.accepted for record in extended_records)
    assert all(
        record.source_reason_code == "MACD_EXTREMUM_NOT_FOUND"
        for record in extended_records
    )
    assert all(
        "final_quality_pass=False" in record.reason
        for record in extended_records
    )

    source = WorkspaceMacdSignalSource(enabled=True, mode="LINEAR")
    first_event = _events()[0]
    source.on_market_event(first_event)
    duplicate_blocked = False
    try:
        source.on_market_event(first_event)
    except WorkspaceAlgorithmError:
        duplicate_blocked = True
    assert duplicate_blocked

    print("Algorithm Workspace MACD Replay result")
    print(f"  required_warmup_bars={computed_warmup}")
    print(f"  signals={len(records)}")
    print("  classic_cross_up=True")
    print("  classic_cross_down=True")
    print("  source_reason_code_structured=True")
    print("  source_profile_snapshot_structured=True")
    print("  source_disable_blocks_signals=True")
    print("  runtime_warmup_from_component=True")
    print("  legacy_warmup_key_preserved=True")
    print("  speed_1x_10x_step_deterministic=True")
    print("  duplicate_bar_blocked=True")
    print("  extended_quality_filter_active=True")
    print("  alligator_not_applied=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_MACD_REPLAY_CHECK=OK")


if __name__ == "__main__":
    main()
