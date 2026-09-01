# -*- coding: utf-8 -*-
"""Runtime check for safe WSP Session restore without automatic start."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_DEMO,
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_CONTROL_MODE_MANUAL,
    WORKSPACE_DATA_MODE_BROKER,
    WORKSPACE_DATA_MODE_REPLAY,
    WORKSPACE_PANEL_POSITION,
    WORKSPACE_PANEL_SIGNALS,
    WORKSPACE_STATE_RESTORED,
    WORKSPACE_STATE_STOPPED,
)
from core.algorithm_workspace_controller import (  # noqa: E402
    AlgorithmWorkspaceController,
)
from core.session_repository import SessionRepository  # noqa: E402
from core.workspace_algorithm import (  # noqa: E402
    WorkspaceAlgorithm,
    WorkspaceSignalOutput,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_replay import (  # noqa: E402
    REPLAY_SPEED_MAX,
    replay_speed_label,
)
from core.workspace_runtime import WorkspaceRuntimeContext  # noqa: E402


class RestoreProbeAlgorithm(WorkspaceAlgorithm):
    """Algorithm probe that must not be created during Session restore."""

    factory_calls = 0
    start_calls = 0

    def __init__(self) -> None:
        type(self).factory_calls += 1

    def configure(
        self,
        context: WorkspaceRuntimeContext,
        parameters: Mapping[str, Any],
    ) -> None:
        _ = context, parameters

    def start(self) -> None:
        type(self).start_calls += 1

    def on_market_event(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalOutput:
        _ = event
        return None

    def on_order_event(self, event: object) -> None:
        _ = event

    def stop(self) -> None:
        return


def algorithm_factory(_algorithm_id: str) -> WorkspaceAlgorithm:
    return RestoreProbeAlgorithm()


def main() -> None:
    RestoreProbeAlgorithm.factory_calls = 0
    RestoreProbeAlgorithm.start_calls = 0

    with TemporaryDirectory() as temp_dir:
        repository = SessionRepository(Path(temp_dir) / "Session")
        initial_controller = AlgorithmWorkspaceController(repository)

        first = initial_controller.create_workspace(
            broker="IB",
            account_id="DUM513747",
            account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
            symbol="EURUSD",
            timeframe="M15",
            algorithm="RailAlgorithm",
            display_name="EURUSD Rails M15",
            data_mode=WORKSPACE_DATA_MODE_REPLAY,
            control_mode=WORKSPACE_CONTROL_MODE_AUTO,
            parameters={
                "warmup_bars": 25,
                "spread_limit": 0.00018,
                "macd_signal_mode": "EXTENDED",
                "alligator_confirmation": "HIGHER_1",
            },
            risk_settings={
                "risk_percent": 0.5,
                "maximum_position_volume": 3000,
            },
            profit_protection={
                "enabled": True,
                "activation_mode": "AFTER_SPREAD",
                "max_profit_drawdown_percent": 30.0,
                "minimum_profit": 20.0,
            },
            replay_settings={
                "speed": 2,
                "source": "SYNTHETIC_TEST",
                "start_utc": "2026-07-01T08:00:00Z",
                "end_utc": "2026-07-01T12:15:00Z",
            },
            ui_state={
                "geometry": {
                    "x": 75,
                    "y": 65,
                    "width": 780,
                    "height": 510,
                },
                "window_state": "MINIMIZED",
                "active_panel": WORKSPACE_PANEL_SIGNALS,
            },
        )
        second = initial_controller.create_workspace(
            broker="CTRADER",
            account_id="123456",
            account_mode=WORKSPACE_ACCOUNT_MODE_DEMO,
            symbol="GBPUSD",
            timeframe="H1",
            algorithm="RailAlgorithm",
            display_name="GBPUSD Manual H1",
            data_mode=WORKSPACE_DATA_MODE_BROKER,
            control_mode=WORKSPACE_CONTROL_MODE_MANUAL,
            parameters={"warmup_bars": 10},
            replay_settings={"speed": 1},
            ui_state={
                "geometry": {
                    "x": 140,
                    "y": 90,
                    "width": 720,
                    "height": 480,
                },
                "window_state": "MAXIMIZED",
                "active_panel": WORKSPACE_PANEL_POSITION,
            },
        )

        initial_controller.set_workspace_replay_speed(
            first.workspace_uid,
            REPLAY_SPEED_MAX,
        )
        initial_controller.set_active_workspace(first.workspace_uid)

        first_path = repository.workspace_path(first.workspace_uid)
        first_payload = json.loads(first_path.read_text(encoding="utf-8"))
        first_payload["runtime_state"] = "RUNNING"
        first_payload["broker_order_id"] = "MUST_NOT_RESTORE"
        first_payload["position_id"] = "MUST_NOT_RESTORE"
        first_path.write_text(
            json.dumps(first_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        restored_controller = AlgorithmWorkspaceController(
            repository,
            algorithm_factory=algorithm_factory,
        )
        restored = restored_controller.restore_workspaces()
        manifest = repository.load_manifest()

        assert [item.workspace_uid for item in restored] == [
            first.workspace_uid,
            second.workspace_uid,
        ]
        assert manifest["active_workspace_uid"] == first.workspace_uid
        assert all(item.runtime_state == WORKSPACE_STATE_RESTORED for item in restored)

        restored_first = restored[0]
        restored_second = restored[1]
        assert restored_first.data_mode == WORKSPACE_DATA_MODE_REPLAY
        assert restored_first.control_mode == WORKSPACE_CONTROL_MODE_AUTO
        assert restored_first.parameters["warmup_bars"] == 25
        assert restored_first.parameters["spread_limit"] == 0.00018
        assert restored_first.parameters["macd_signal_mode"] == "EXTENDED"
        assert restored_first.risk_settings["risk_percent"] == 0.5
        assert restored_first.profit_protection["minimum_profit"] == 20.0
        assert restored_first.replay_settings["speed"] == REPLAY_SPEED_MAX
        assert restored_first.ui_state["window_state"] == "MINIMIZED"
        assert restored_first.ui_state["active_panel"] == WORKSPACE_PANEL_SIGNALS
        assert restored_first.ui_state["geometry"]["width"] == 780
        assert restored_second.data_mode == WORKSPACE_DATA_MODE_BROKER
        assert restored_second.control_mode == WORKSPACE_CONTROL_MODE_MANUAL
        assert restored_second.ui_state["window_state"] == "MAXIMIZED"
        assert restored_second.ui_state["active_panel"] == WORKSPACE_PANEL_POSITION

        first_runtime = restored_controller.attach_workspace_runtime(restored_first)
        second_runtime = restored_controller.attach_workspace_runtime(restored_second)

        assert first_runtime.context.restored_from_session
        assert second_runtime.context.restored_from_session
        assert first_runtime.context.runtime_state == WORKSPACE_STATE_STOPPED
        assert second_runtime.context.runtime_state == WORKSPACE_STATE_STOPPED
        assert first_runtime.replay_settings["speed"] == REPLAY_SPEED_MAX
        assert first_runtime.algorithm_parameters["warmup_bars"] == 25
        assert first_runtime.algorithm is None
        assert first_runtime.replay_session is None
        assert first_runtime.context.market_event_count == 0
        assert first_runtime.context.active_orders_count == 0
        assert first_runtime.context.positions_count == 0
        assert not first_runtime.signals
        assert not first_runtime.profit_decisions
        assert first_runtime.close_guard_result().allowed
        assert RestoreProbeAlgorithm.factory_calls == 0
        assert RestoreProbeAlgorithm.start_calls == 0

        restore_transition = any(
            entry.event == "STATE_CHANGED"
            and entry.details.get("previous_state") == "RESTORED"
            and entry.details.get("target_state") == "STOPPED"
            for entry in first_runtime.journal
        )
        session_restored_logged = any(
            entry.event == "SESSION_RESTORED" for entry in first_runtime.journal
        )
        assert restore_transition
        assert session_restored_logged

        print("Algorithm Workspace Restore result")
        print(f"  workspaces={len(restored)}")
        print("  workspace_order_preserved=True")
        print("  active_workspace_restored=True")
        print("  modes_parameters_restored=True")
        print("  ui_state_restored=True")
        print(
            "  replay_speed="
            f"{replay_speed_label(first_runtime.replay_settings['speed'])}"
        )
        print(f"  loaded_state={restored_first.runtime_state}")
        print(f"  final_runtime_state={first_runtime.context.runtime_state}")
        print(f"  restore_transition={restore_transition}")
        print(f"  session_restore_logged={session_restored_logged}")
        print("  automatic_start_blocked=True")
        print("  volatile_runtime_cleared=True")
        print("ALGORITHM_WORKSPACE_RESTORE_CHECK=OK")


if __name__ == "__main__":
    main()
