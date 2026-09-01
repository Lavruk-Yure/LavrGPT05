# -*- coding: utf-8 -*-
"""Перевірка MACD Runtime із зафіксованими profile snapshots WSP."""

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
from core.workspace_indicator_profile import (  # noqa: E402
    MACD_PROFILE_UID_LGE_CLASSIC,
    WORKSPACE_INDICATOR_MACD,
    WORKSPACE_INDICATOR_MA_EXPONENTIAL,
    WORKSPACE_INDICATOR_MA_SIMPLE,
    WORKSPACE_INDICATOR_MA_SMOOTHED,
    WORKSPACE_INDICATOR_SOURCE_CLOSE,
    WORKSPACE_INDICATOR_SOURCE_TYPICAL,
    WorkspaceIndicatorProfile,
    WorkspaceIndicatorProfileBinding,
    built_in_workspace_indicator_profile,
    default_workspace_indicator_profile_bindings,
)
from core.workspace_macd import (  # noqa: E402
    MACD_REQUIRED_BARS,
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
            source_name="MACD_PROFILE_RUNTIME_TEST",
            speed=int(settings.get("speed", 1)),
        )


def _event(index: int, close: float) -> WorkspaceMarketEvent:
    spread = 0.00012
    bid = close - spread / 2.0
    ask = close + spread / 2.0
    open_value = close + (0.00018 if index % 2 == 0 else -0.00012)
    high = max(open_value, close) + 0.00031
    low = min(open_value, close) - 0.00017
    return WorkspaceMarketEvent(
        timestamp=datetime(2026, 7, 27, 8, 0, tzinfo=UTC)
        + timedelta(minutes=15 * index),
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        bid=bid,
        ask=ask,
        spread=ask - bid,
        open=open_value,
        high=high,
        low=low,
        close=close,
        volume=100.0 + index,
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
    )


def _events() -> tuple[WorkspaceMarketEvent, ...]:
    closes = [1.2000] * 35
    closes.extend([1.2100] * 8)
    closes.extend([1.1900] * 8)
    closes.extend([1.2080] * 8)
    closes.extend([1.1920] * 8)
    closes.extend([1.2110] * 8)
    return tuple(_event(index, close) for index, close in enumerate(closes))


def _revised_user_profile(
    *,
    name: str,
    parameters: dict[str, object],
) -> WorkspaceIndicatorProfile:
    built_in = built_in_workspace_indicator_profile(MACD_PROFILE_UID_LGE_CLASSIC)
    duplicate = built_in.duplicate_as_user(name)
    return duplicate.revised(name=name, parameters=parameters)


def _workspace(
    binding: WorkspaceIndicatorProfileBinding | None,
    *,
    speed: int = 1,
    filter_enabled: bool = False,
) -> AlgorithmWorkspace:
    bindings = default_workspace_indicator_profile_bindings()
    if binding is not None:
        bindings[WORKSPACE_INDICATOR_MACD] = binding.to_storage_dict()
    bindings["FUTURE_INDICATOR"] = {"future_key": "preserved"}
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
            "future_parameter": "preserved",
        },
        replay_settings={"speed": speed},
        indicator_profile_bindings=bindings,
    )


def _run(
    workspace: AlgorithmWorkspace,
    *,
    speed: int,
    step_mode: bool = False,
    combined_algorithm: bool = False,
) -> tuple[
    tuple[WorkspaceSignalRecord, ...],
    int,
    WorkspaceMacdSignalSource,
    int,
    dict[str, dict[str, object]],
]:
    replay_settings = dict(workspace.replay_settings)
    replay_settings["speed"] = speed
    run_workspace = replace(workspace, replay_settings=replay_settings)
    if combined_algorithm:
        algorithm = WorkspaceMacdAlligatorReplayAlgorithm(run_workspace.algorithm)
    else:
        algorithm = WorkspaceMacdReplayAlgorithm(run_workspace.algorithm)
    probe = BrokerRequestProbe()
    runtime = WorkspaceRuntime(
        run_workspace,
        replay_service=FixedReplayService(_events()),
        algorithm_factory=lambda _algorithm_id: algorithm,
        broker_market_provider=probe,
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

    source = algorithm.source
    assert source is not None
    return (
        runtime.signal_records(),
        runtime.context.warmup_bars_required,
        source,
        probe.requests,
        runtime.context.indicator_profile_bindings,
    )


def main() -> None:
    default_run = _run(_workspace(None), speed=1)
    default_records, default_warmup, default_source, default_requests, _ = default_run
    assert default_warmup == MACD_REQUIRED_BARS
    assert default_source.profile_uid == MACD_PROFILE_UID_LGE_CLASSIC
    assert default_source.profile_revision == 1
    assert len(default_records) >= 2
    assert default_requests == 0

    fast_profile = _revised_user_profile(
        name="Fast EMA Test",
        parameters={
            "source": WORKSPACE_INDICATOR_SOURCE_CLOSE,
            "fast_period": 3,
            "slow_period": 6,
            "signal_period": 2,
            "oscillator_ma_type": WORKSPACE_INDICATOR_MA_EXPONENTIAL,
            "signal_ma_type": WORKSPACE_INDICATOR_MA_EXPONENTIAL,
            "shift": 0,
        },
    )
    fast_binding = WorkspaceIndicatorProfileBinding.from_profile(fast_profile)
    fast_workspace = _workspace(fast_binding)
    fast_1x = _run(fast_workspace, speed=1)
    fast_10x = _run(fast_workspace, speed=10)
    fast_step = _run(fast_workspace, speed=1, step_mode=True)
    fast_records, fast_warmup, fast_source, fast_requests, fast_bindings = fast_1x
    assert fast_10x[0] == fast_records
    assert fast_step[0] == fast_records
    assert fast_warmup == 8
    assert fast_10x[1] == fast_warmup
    assert fast_step[1] == fast_warmup
    assert fast_source.profile_uid == fast_profile.profile_uid
    assert fast_source.profile_revision == fast_profile.revision
    assert fast_source.runtime_profile.fast_period == 3
    assert fast_source.runtime_profile.slow_period == 6
    assert len(fast_records) > len(default_records)
    assert all(
        f"profile_uid={fast_profile.profile_uid}" in record.reason
        for record in fast_records
    )
    assert all(
        f"profile_revision={fast_profile.revision}" in record.reason
        for record in fast_records
    )
    assert fast_requests == 0
    assert fast_10x[3] == 0
    assert fast_step[3] == 0
    assert fast_bindings["FUTURE_INDICATOR"] == {"future_key": "preserved"}
    assert fast_workspace.parameters["warmup_bars"] == 2
    assert fast_workspace.parameters["future_parameter"] == "preserved"

    revised_fast_profile = fast_profile.revised(
        name="Fast EMA Test",
        parameters={
            "source": WORKSPACE_INDICATOR_SOURCE_CLOSE,
            "fast_period": 4,
            "slow_period": 10,
            "signal_period": 3,
            "oscillator_ma_type": WORKSPACE_INDICATOR_MA_EXPONENTIAL,
            "signal_ma_type": WORKSPACE_INDICATOR_MA_EXPONENTIAL,
            "shift": 0,
        },
    )
    assert revised_fast_profile.revision == fast_profile.revision + 1
    snapshot_run = _run(fast_workspace, speed=1)
    snapshot_source = snapshot_run[2]
    assert snapshot_source.profile_revision == fast_profile.revision
    assert snapshot_source.runtime_profile.fast_period == 3
    assert snapshot_source.runtime_profile.slow_period == 6
    assert snapshot_run[1] == 8

    mixed_profile = _revised_user_profile(
        name="Mixed MA Typical Shift",
        parameters={
            "source": WORKSPACE_INDICATOR_SOURCE_TYPICAL,
            "fast_period": 4,
            "slow_period": 9,
            "signal_period": 3,
            "oscillator_ma_type": WORKSPACE_INDICATOR_MA_SIMPLE,
            "signal_ma_type": WORKSPACE_INDICATOR_MA_SMOOTHED,
            "shift": 2,
        },
    )
    mixed_binding = WorkspaceIndicatorProfileBinding.from_profile(mixed_profile)
    mixed_workspace = _workspace(mixed_binding)
    mixed_1x = _run(mixed_workspace, speed=1)
    mixed_10x = _run(mixed_workspace, speed=10)
    mixed_records, mixed_warmup, mixed_source, mixed_requests, _ = mixed_1x
    assert mixed_10x[0] == mixed_records
    assert mixed_warmup == 14
    assert mixed_10x[1] == mixed_warmup
    assert mixed_source.runtime_profile.oscillator_ma_type == (
        WORKSPACE_INDICATOR_MA_SIMPLE
    )
    assert mixed_source.runtime_profile.signal_ma_type == (
        WORKSPACE_INDICATOR_MA_SMOOTHED
    )
    assert mixed_source.runtime_profile.shift == 2
    first_event = _events()[0]
    expected_typical = (first_event.high + first_event.low + first_event.close) / 3.0
    assert math_is_close(
        mixed_source.observations[0].source_value,
        expected_typical,
    )
    assert mixed_requests == 0
    assert mixed_10x[3] == 0

    combined_run = _run(
        fast_workspace,
        speed=1,
        combined_algorithm=True,
    )
    combined_source = combined_run[2]
    assert combined_source.profile_uid == fast_profile.profile_uid
    assert combined_source.profile_revision == fast_profile.revision
    assert combined_run[1] == 8
    assert combined_run[3] == 0

    print("Algorithm Workspace MACD Profile Runtime result")
    print(f"  default_profile_warmup={default_warmup}")
    print(f"  custom_profile_warmup={fast_warmup}")
    print(f"  mixed_profile_warmup={mixed_warmup}")
    print("  resolved_profile_snapshot_used=True")
    print("  profile_uid_revision_visible=True")
    print("  profile_edit_does_not_mutate_workspace_snapshot=True")
    print("  custom_periods_change_runtime=True")
    print("  source_selection_connected=True")
    print("  ema_sma_smma_supported=True")
    print("  causal_shift_supported=True")
    print("  speed_1x_10x_step_deterministic=True")
    print("  combined_macd_alligator_pipeline_uses_macd_profile=True")
    print("  legacy_warmup_key_preserved=True")
    print("  future_keys_preserved=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_MACD_PROFILE_RUNTIME_CHECK=OK")


def math_is_close(left: float, right: float) -> bool:
    return abs(left - right) <= 1e-12


if __name__ == "__main__":
    main()
