# -*- coding: utf-8 -*-
"""Перевірка Alligator Runtime із profile snapshots WSP."""

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
    ALLIGATOR_REQUIRED_BARS,
    WorkspaceAlligatorFilter,
    WorkspaceAlligatorObservation,
    WorkspaceAlligatorRuntimeProfile,
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_broker_market import (  # noqa: E402
    WorkspaceBrokerMarketProviderProtocol,
)
from core.workspace_indicator_profile import (  # noqa: E402
    ALLIGATOR_PROFILE_UID_CTRADER_DEFAULT,
    ALLIGATOR_PROFILE_UID_LGE_CLASSIC,
    WORKSPACE_INDICATOR_ALLIGATOR,
    WORKSPACE_INDICATOR_MA_EXPONENTIAL,
    WORKSPACE_INDICATOR_MA_SIMPLE,
    WORKSPACE_INDICATOR_MA_SMOOTHED,
    WORKSPACE_INDICATOR_SOURCE_CLOSE,
    WORKSPACE_INDICATOR_SOURCE_MEDIAN,
    WorkspaceIndicatorProfile,
    WorkspaceIndicatorProfileBinding,
    built_in_workspace_indicator_profile,
    default_workspace_indicator_profile_bindings,
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
            source_name="ALLIGATOR_PROFILE_RUNTIME_TEST",
            speed=int(settings.get("speed", 1)),
        )


def _event(index: int, close: float) -> WorkspaceMarketEvent:
    spread = 0.00012
    bid = close - spread / 2.0
    ask = close + spread / 2.0
    open_value = close + (0.00018 if index % 2 == 0 else -0.00012)
    high = max(open_value, close) + 0.00020 + (index % 4) * 0.00005
    low = min(open_value, close) - 0.00013
    return WorkspaceMarketEvent(
        timestamp=datetime(2026, 7, 28, 8, 0, tzinfo=UTC)
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


def _closes() -> tuple[float, ...]:
    closes: list[float] = [1.2000] * 35
    closes.extend(1.2000 + index * 0.0005 for index in range(30))
    closes.extend(1.2150 - index * 0.0002 for index in range(8))
    closes.extend(1.2134 + index * 0.0004 for index in range(20))
    closes.extend(1.2214 - index * 0.0006 for index in range(40))
    last_close = closes[-1]
    closes.extend(last_close + (index + 1) * 0.00045 for index in range(12))
    last_close = closes[-1]
    closes.extend(last_close - (index + 1) * 0.0005 for index in range(25))
    return tuple(closes)


def _events() -> tuple[WorkspaceMarketEvent, ...]:
    return tuple(_event(index, close) for index, close in enumerate(_closes()))


def _revised_user_profile(
    *,
    name: str,
    parameters: dict[str, object],
) -> WorkspaceIndicatorProfile:
    built_in = built_in_workspace_indicator_profile(ALLIGATOR_PROFILE_UID_LGE_CLASSIC)
    duplicate = built_in.duplicate_as_user(name)
    return duplicate.revised(name=name, parameters=parameters)


def _workspace(
    binding: WorkspaceIndicatorProfileBinding | None,
    *,
    speed: int = 1,
    macd_enabled: bool = True,
) -> AlgorithmWorkspace:
    bindings = default_workspace_indicator_profile_bindings()
    if binding is not None:
        bindings[WORKSPACE_INDICATOR_ALLIGATOR] = binding.to_storage_dict()
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
            "macd_signal_enabled": macd_enabled,
            "macd_signal_mode": "LINEAR",
            "alligator_filter_enabled": True,
            "alligator_confirmation": "SAME_TIMEFRAME",
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
    speed: int = 1,
    step_mode: bool = False,
) -> tuple[
    tuple[WorkspaceSignalRecord, ...],
    int,
    WorkspaceAlligatorFilter,
    int,
    dict[str, dict[str, object]],
]:
    replay_settings = dict(workspace.replay_settings)
    replay_settings["speed"] = speed
    run_workspace = replace(workspace, replay_settings=replay_settings)
    algorithm = WorkspaceMacdAlligatorReplayAlgorithm(run_workspace.algorithm)
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

    signal_filter = algorithm.signal_filter
    assert signal_filter is not None
    return (
        runtime.signal_records(),
        runtime.context.warmup_bars_required,
        signal_filter,
        probe.requests,
        runtime.context.indicator_profile_bindings,
    )


def _direct_observations(
    profile: WorkspaceIndicatorProfile,
) -> tuple[WorkspaceAlligatorObservation, ...]:
    runtime_profile = WorkspaceAlligatorRuntimeProfile.from_binding(
        WorkspaceIndicatorProfileBinding.from_profile(profile)
    )
    signal_filter = WorkspaceAlligatorFilter(
        enabled=True,
        confirmation_mode="SAME_TIMEFRAME",
        runtime_profile=runtime_profile,
    )
    for event in _events():
        signal_filter.on_market_event(event)
    return signal_filter.observations


def _assert_profile_shift_is_causal(
    profile: WorkspaceIndicatorProfile,
) -> None:
    runtime_profile = WorkspaceAlligatorRuntimeProfile.from_binding(
        WorkspaceIndicatorProfileBinding.from_profile(profile)
    )
    baseline = WorkspaceAlligatorFilter(
        enabled=True,
        confirmation_mode="SAME_TIMEFRAME",
        runtime_profile=runtime_profile,
    )
    changed_future = WorkspaceAlligatorFilter(
        enabled=True,
        confirmation_mode="SAME_TIMEFRAME",
        runtime_profile=runtime_profile,
    )
    events = _events()
    prefix_size = 90
    for event in events[:prefix_size]:
        baseline.on_market_event(event)
        changed_future.on_market_event(event)

    for index, event in enumerate(events[prefix_size:]):
        changed_close = event.close + 0.0500 + index * 0.0010
        changed_future.on_market_event(
            replace(
                event,
                open=changed_close,
                high=changed_close + 0.00035,
                low=changed_close - 0.00015,
                close=changed_close,
                bid=changed_close - 0.00006,
                ask=changed_close + 0.00006,
                spread=0.00012,
            )
        )

    assert baseline.observations == changed_future.observations[:prefix_size]


def main() -> None:
    default_run = _run(_workspace(None, macd_enabled=False))
    _, default_runtime_warmup, default_filter, default_requests, _ = default_run
    assert default_filter.required_bars == ALLIGATOR_REQUIRED_BARS
    assert default_runtime_warmup == ALLIGATOR_REQUIRED_BARS
    assert default_filter.profile_uid == ALLIGATOR_PROFILE_UID_LGE_CLASSIC
    assert default_filter.profile_revision == 1
    assert default_requests == 0

    fast_profile = _revised_user_profile(
        name="Fast EMA Alligator",
        parameters={
            "source": WORKSPACE_INDICATOR_SOURCE_CLOSE,
            "jaw_period": 5,
            "jaw_shift": 1,
            "teeth_period": 3,
            "teeth_shift": 1,
            "lips_period": 2,
            "lips_shift": 0,
            "ma_type": WORKSPACE_INDICATOR_MA_EXPONENTIAL,
        },
    )
    fast_binding = WorkspaceIndicatorProfileBinding.from_profile(fast_profile)
    fast_workspace = _workspace(fast_binding, macd_enabled=False)
    fast_run = _run(fast_workspace)
    _, fast_runtime_warmup, fast_filter, fast_requests, fast_bindings = fast_run
    assert fast_filter.required_bars == 6
    assert fast_runtime_warmup == 6
    assert fast_filter.profile_uid == fast_profile.profile_uid
    assert fast_filter.profile_revision == fast_profile.revision
    assert fast_filter.runtime_profile.source == WORKSPACE_INDICATOR_SOURCE_CLOSE
    assert fast_filter.runtime_profile.ma_type == WORKSPACE_INDICATOR_MA_EXPONENTIAL
    assert fast_requests == 0
    assert fast_bindings["FUTURE_INDICATOR"] == {"future_key": "preserved"}
    assert fast_workspace.parameters["warmup_bars"] == 2
    assert fast_workspace.parameters["spread_limit"] == 0.00020
    assert fast_workspace.parameters["future_parameter"] == "preserved"

    tws_completed_profile = _revised_user_profile(
        name="TWS Completed EMA Test",
        parameters={
            "source": WORKSPACE_INDICATOR_SOURCE_CLOSE,
            "jaw_period": 21,
            "jaw_shift": 8,
            "teeth_period": 13,
            "teeth_shift": 5,
            "lips_period": 8,
            "lips_shift": 3,
            "ma_type": WORKSPACE_INDICATOR_MA_EXPONENTIAL,
        },
    )
    tws_binding = WorkspaceIndicatorProfileBinding.from_profile(tws_completed_profile)
    tws_run = _run(_workspace(tws_binding, macd_enabled=False))
    assert tws_run[1] == 29
    assert tws_run[2].required_bars == 29
    assert tws_run[3] == 0

    ctrader_profile = built_in_workspace_indicator_profile(
        ALLIGATOR_PROFILE_UID_CTRADER_DEFAULT
    )
    ctrader_binding = WorkspaceIndicatorProfileBinding.from_profile(ctrader_profile)
    combined_workspace = _workspace(ctrader_binding, macd_enabled=True)
    combined_1x = _run(combined_workspace, speed=1)
    combined_10x = _run(combined_workspace, speed=10)
    combined_step = _run(combined_workspace, step_mode=True)
    combined_records = combined_1x[0]
    assert combined_10x[0] == combined_records
    assert combined_step[0] == combined_records
    assert combined_1x[2].profile_uid == ctrader_profile.profile_uid
    assert combined_1x[2].runtime_profile.source == (WORKSPACE_INDICATOR_SOURCE_CLOSE)
    assert combined_1x[2].runtime_profile.ma_type == (WORKSPACE_INDICATOR_MA_SIMPLE)
    assert combined_records
    assert all(
        f"alligator_profile_uid={ctrader_profile.profile_uid}" in record.reason
        for record in combined_records
    )
    assert all(
        "alligator_profile_revision=1" in record.reason for record in combined_records
    )
    assert combined_1x[3] == 0
    assert combined_10x[3] == 0
    assert combined_step[3] == 0

    fast_revision_3 = fast_profile.revised(
        name="Fast EMA Alligator v3",
        parameters={
            "source": WORKSPACE_INDICATOR_SOURCE_MEDIAN,
            "jaw_period": 9,
            "jaw_shift": 2,
            "teeth_period": 6,
            "teeth_shift": 1,
            "lips_period": 4,
            "lips_shift": 0,
            "ma_type": WORKSPACE_INDICATOR_MA_SMOOTHED,
        },
    )
    assert fast_revision_3.revision == fast_profile.revision + 1
    old_snapshot_run = _run(fast_workspace)
    assert old_snapshot_run[2].profile_revision == fast_profile.revision
    assert old_snapshot_run[2].runtime_profile.jaw_period == 5
    assert old_snapshot_run[2].runtime_profile.source == (
        WORKSPACE_INDICATOR_SOURCE_CLOSE
    )

    common_parameters: dict[str, object] = {
        "source": WORKSPACE_INDICATOR_SOURCE_CLOSE,
        "jaw_period": 13,
        "jaw_shift": 8,
        "teeth_period": 8,
        "teeth_shift": 5,
        "lips_period": 5,
        "lips_shift": 3,
        "ma_type": WORKSPACE_INDICATOR_MA_SIMPLE,
    }
    simple_profile = _revised_user_profile(
        name="Simple Close Comparison",
        parameters=common_parameters,
    )
    smoothed_parameters = dict(common_parameters)
    smoothed_parameters["ma_type"] = WORKSPACE_INDICATOR_MA_SMOOTHED
    smoothed_profile = _revised_user_profile(
        name="Smoothed Close Comparison",
        parameters=smoothed_parameters,
    )
    ema_parameters = dict(common_parameters)
    ema_parameters["ma_type"] = WORKSPACE_INDICATOR_MA_EXPONENTIAL
    ema_profile = _revised_user_profile(
        name="EMA Close Comparison",
        parameters=ema_parameters,
    )
    median_parameters = dict(common_parameters)
    median_parameters["source"] = WORKSPACE_INDICATOR_SOURCE_MEDIAN
    median_profile = _revised_user_profile(
        name="Simple Median Comparison",
        parameters=median_parameters,
    )

    simple_observations = _direct_observations(simple_profile)
    smoothed_observations = _direct_observations(smoothed_profile)
    ema_observations = _direct_observations(ema_profile)
    median_observations = _direct_observations(median_profile)
    simple_lines = (
        simple_observations[-1].jaw,
        simple_observations[-1].teeth,
        simple_observations[-1].lips,
    )
    smoothed_lines = (
        smoothed_observations[-1].jaw,
        smoothed_observations[-1].teeth,
        smoothed_observations[-1].lips,
    )
    ema_lines = (
        ema_observations[-1].jaw,
        ema_observations[-1].teeth,
        ema_observations[-1].lips,
    )
    assert simple_lines != smoothed_lines
    assert ema_lines != smoothed_lines
    assert simple_observations[0].source_value == _events()[0].close
    assert (
        median_observations[0].source_value
        == (_events()[0].high + _events()[0].low) / 2.0
    )

    _assert_profile_shift_is_causal(fast_profile)

    print("Algorithm Workspace Alligator Profile Runtime result")
    print(f"  default_profile_warmup={default_filter.required_bars}")
    print(f"  fast_profile_warmup={fast_filter.required_bars}")
    print(f"  tws_completed_profile_warmup={tws_run[2].required_bars}")
    print("  resolved_profile_snapshot_used=True")
    print("  profile_uid_revision_visible=True")
    print("  profile_edit_does_not_mutate_workspace_snapshot=True")
    print("  custom_periods_change_runtime=True")
    print("  source_selection_connected=True")
    print("  ema_sma_smma_supported=True")
    print("  causal_line_shifts_supported=True")
    print("  speed_1x_10x_step_deterministic=True")
    print("  combined_macd_alligator_pipeline_uses_alligator_profile=True")
    print("  legacy_spread_warmup_preserved=True")
    print("  future_keys_preserved=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_ALLIGATOR_PROFILE_RUNTIME_CHECK=OK")


if __name__ == "__main__":
    main()
