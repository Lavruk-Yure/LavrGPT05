# -*- coding: utf-8 -*-
"""Регресія RoadMap101 для ABC persistence/restore і MACD revision binding.

Перевірка моделює канонічний цикл Parameters WSP -> Save -> Session -> новий
AlgorithmWorkspaceController -> restore після повного restart. Вона фіксує
окреме збереження legacy 45° та ABC 2.00°, exact profile UID/revision snapshot
для користувацького MACD 6/13/4 і доводить поведінково, що зміна legacy кута не
впливає на EXTENDED MACD, коли активна модель ``ABC_REALTIME_SCALED``.

Тест не запускає broker services і не виконує broker requests/execution. Усі
ринкові події синтетичні, завершені M15 bars у строгій хронології без
look-ahead.
"""

from __future__ import annotations

import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_MANUAL,
    WORKSPACE_DATA_MODE_REPLAY,
)
from core.algorithm_workspace_controller import (  # noqa: E402
    AlgorithmWorkspaceController,
)
from core.session_repository import SessionRepository  # noqa: E402
from core.workspace_indicator_profile import (  # noqa: E402
    MACD_PROFILE_UID_LGE_CLASSIC,
    WORKSPACE_INDICATOR_MACD,
    WORKSPACE_INDICATOR_MA_EXPONENTIAL,
    WORKSPACE_INDICATOR_SOURCE_CLOSE,
    WorkspaceIndicatorProfileBinding,
    default_workspace_indicator_profile_bindings,
    merge_workspace_indicator_profile_binding,
    workspace_indicator_profile_binding,
)
from core.workspace_indicator_profile_repository import (  # noqa: E402
    WorkspaceIndicatorProfileRepository,
)
from core.workspace_macd import WorkspaceMacdSignalSource  # noqa: E402
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_parameter_adapter import (  # noqa: E402
    WORKSPACE_ALGORITHM_PARAMETER_ADAPTER,
)
from core.workspace_runtime import WorkspaceRuntimeContext  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_MACD_CROSS_ANGLE_MODEL_ABC,
    WORKSPACE_MACD_CROSS_ANGLE_MODEL_KEY,
    WORKSPACE_MACD_CROSS_MIN_ABC_ANGLE_KEY,
    WORKSPACE_MACD_CROSS_MIN_ANGLE_KEY,
    WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE_KEY,
    WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE_KEY,
)


def _very_fast_parameters() -> dict[str, object]:
    return {
        "source": WORKSPACE_INDICATOR_SOURCE_CLOSE,
        "fast_period": 6,
        "slow_period": 13,
        "signal_period": 4,
        "oscillator_ma_type": WORKSPACE_INDICATOR_MA_EXPONENTIAL,
        "signal_ma_type": WORKSPACE_INDICATOR_MA_EXPONENTIAL,
        "shift": 0,
    }


def _event(index: int) -> WorkspaceMarketEvent:
    timestamp = datetime(2026, 1, 2, 0, 0, tzinfo=UTC) + timedelta(minutes=15 * index)
    close = 1.1000 + 0.0015 * math.sin(index * 0.35) + 0.0003 * math.sin(index * 0.07)
    open_value = close + (0.00008 if index % 2 == 0 else -0.00008)
    high = max(open_value, close) + 0.00020
    low = min(open_value, close) - 0.00020
    spread = 0.00012
    return WorkspaceMarketEvent(
        timestamp=timestamp,
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        bid=close - spread / 2.0,
        ask=close + spread / 2.0,
        spread=spread,
        open=open_value,
        high=high,
        low=low,
        close=close,
        volume=100.0 + index,
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
    )


def _abc_signature(
    context: WorkspaceRuntimeContext,
    parameters: dict[str, object],
) -> tuple[tuple[object, ...], ...]:
    source = WorkspaceMacdSignalSource.from_runtime_context(context, parameters)
    proposals: list[tuple[object, ...]] = []
    for index in range(160):
        proposal = source.on_market_event(_event(index))
        if proposal is None:
            continue
        diagnostic = source.quality_diagnostics[-1]
        proposals.append(
            (
                proposal.direction,
                proposal.source_reason_code,
                proposal.filter_decision,
                round(diagnostic.effective_angle_degrees, 8),
                diagnostic.criterion_angle_pass,
                diagnostic.final_quality_pass,
            )
        )
    assert proposals
    return tuple(proposals)


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        session_dir = Path(temp_dir) / "Session"
        profile_repository = WorkspaceIndicatorProfileRepository(session_dir)

        revision_1 = profile_repository.duplicate_profile(
            MACD_PROFILE_UID_LGE_CLASSIC,
            name="Custom MACD VERY FAST",
        )
        revision_2 = profile_repository.update_profile(
            revision_1.profile_uid,
            name="Custom MACD VERY FAST",
            parameters={
                **_very_fast_parameters(),
                "fast_period": 8,
                "slow_period": 17,
                "signal_period": 5,
            },
        )
        revision_3 = profile_repository.update_profile(
            revision_2.profile_uid,
            name="Custom MACD VERY FAST",
            parameters=_very_fast_parameters(),
        )
        assert revision_3.revision == 3

        macd_binding = WorkspaceIndicatorProfileBinding.from_profile(revision_3)
        bindings = merge_workspace_indicator_profile_binding(
            default_workspace_indicator_profile_bindings(),
            macd_binding,
        )

        repository = SessionRepository(session_dir)
        controller = AlgorithmWorkspaceController(repository)
        workspace = controller.create_workspace(
            broker="IB",
            account_id="DUM513747",
            account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
            symbol="EURUSD",
            timeframe="M15",
            algorithm="RailAlgorithm",
            display_name="RoadMap101 ABC Persistence Probe",
            data_mode=WORKSPACE_DATA_MODE_REPLAY,
            control_mode=WORKSPACE_CONTROL_MODE_MANUAL,
            parameters={
                "warmup_bars": 35,
                "spread_limit": 0.00020,
            },
            indicator_profile_bindings=bindings,
        )

        schema_updates = (
            WORKSPACE_ALGORITHM_PARAMETER_ADAPTER.schema_values_from_workspace(
                workspace
            )
        )
        schema_updates.update(
            {
                "signals.macd_enabled": True,
                "signals.macd_signal_mode": "EXTENDED",
                "signals.macd_extremum_min_prominence": 0.000005,
                "signals.macd_extremum_to_cross_min_distance": 0.000050,
                "signals.macd_cross_angle_model": (
                    WORKSPACE_MACD_CROSS_ANGLE_MODEL_ABC
                ),
                "signals.macd_cross_min_angle": 45.0,
                "signals.macd_cross_min_abc_angle": 2.00,
            }
        )
        dialog_values = (
            WORKSPACE_ALGORITHM_PARAMETER_ADAPTER.legacy_values_after_schema_updates(
                workspace,
                schema_updates,
            )
        )
        saved = controller.update_workspace_parameters(
            workspace.workspace_uid,
            dialog_values,
            schema_updates=schema_updates,
            indicator_profile_bindings=bindings,
        )

        saved_binding = workspace_indicator_profile_binding(
            saved,
            WORKSPACE_INDICATOR_MACD,
        )
        assert saved.parameters[WORKSPACE_MACD_CROSS_ANGLE_MODEL_KEY] == (
            WORKSPACE_MACD_CROSS_ANGLE_MODEL_ABC
        )
        assert saved.parameters[WORKSPACE_MACD_CROSS_MIN_ABC_ANGLE_KEY] == 2.0
        assert saved.parameters[WORKSPACE_MACD_CROSS_MIN_ANGLE_KEY] == 45.0
        assert saved.parameters[WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE_KEY] == (
            0.000005
        )
        assert (
            saved.parameters[WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE_KEY]
            == 0.000050
        )
        assert saved_binding.profile_uid == revision_3.profile_uid
        assert saved_binding.profile_revision == 3
        assert saved_binding.profile.parameters == _very_fast_parameters()

        restarted_controller = AlgorithmWorkspaceController(
            SessionRepository(session_dir)
        )
        restored_workspaces = restarted_controller.restore_workspaces()
        assert len(restored_workspaces) == 1
        restored = restored_workspaces[0]
        restored_binding = workspace_indicator_profile_binding(
            restored,
            WORKSPACE_INDICATOR_MACD,
        )

        assert restored.parameters[WORKSPACE_MACD_CROSS_ANGLE_MODEL_KEY] == (
            WORKSPACE_MACD_CROSS_ANGLE_MODEL_ABC
        )
        assert restored.parameters[WORKSPACE_MACD_CROSS_MIN_ABC_ANGLE_KEY] == 2.0
        assert restored.parameters[WORKSPACE_MACD_CROSS_MIN_ANGLE_KEY] == 45.0
        assert restored.parameters[WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE_KEY] == (
            0.000005
        )
        assert (
            restored.parameters[WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE_KEY]
            == 0.000050
        )
        assert restored_binding.profile_uid == saved_binding.profile_uid
        assert restored_binding.profile_revision == saved_binding.profile_revision
        assert restored_binding.profile.parameters == _very_fast_parameters()

        context = WorkspaceRuntimeContext.from_workspace(restored)
        restored_source = WorkspaceMacdSignalSource.from_runtime_context(
            context,
            restored.parameters,
        )
        assert restored_source.profile_uid == revision_3.profile_uid
        assert restored_source.profile_revision == 3
        assert restored_source.runtime_profile.fast_period == 6
        assert restored_source.runtime_profile.slow_period == 13
        assert restored_source.runtime_profile.signal_period == 4
        assert restored_source.angle_model == WORKSPACE_MACD_CROSS_ANGLE_MODEL_ABC
        assert restored_source.cross_min_abc_angle_degrees == 2.0
        assert restored_source.cross_min_angle_degrees == 45.0

        legacy_changed = dict(restored.parameters)
        legacy_changed[WORKSPACE_MACD_CROSS_MIN_ANGLE_KEY] = 179.0
        baseline_signature = _abc_signature(context, dict(restored.parameters))
        changed_legacy_signature = _abc_signature(context, legacy_changed)
        assert baseline_signature == changed_legacy_signature

        print("Algorithm Workspace MACD ABC Persistence Restore result")
        print("  save_restore_cycle=True")
        print("  full_controller_restart_restore=True")
        print("  macd_signal_mode=EXTENDED")
        print(f"  angle_model={restored_source.angle_model}")
        print(f"  abc_min_angle={restored_source.cross_min_abc_angle_degrees:.2f}")
        print(f"  legacy_min_angle={restored_source.cross_min_angle_degrees:.2f}")
        print("  prominence=0.000005")
        print("  distance=0.000050")
        print(f"  profile_uid={restored_source.profile_uid}")
        print(f"  profile_revision={restored_source.profile_revision}")
        print("  profile_periods=6/13/4")
        print("  legacy_angle_not_used_in_abc_mode=True")
        print(f"  abc_behavioral_signals={len(baseline_signature)}")
        print("  no_look_ahead_completed_m15_only=True")
        print("  broker_requests=0")
        print("  broker_execution_attempted=False")
        print("ALGORITHM_WORKSPACE_MACD_ABC_PERSISTENCE_RESTORE_CHECK=OK")


if __name__ == "__main__":
    main()
