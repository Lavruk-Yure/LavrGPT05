# -*- coding: utf-8 -*-
"""tests.runtime_workspace.run_algorithm_workspace_parameters_check

Runtime check for validated per-WSP algorithm parameter persistence.
"""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    WORKSPACE_STATE_STOPPED,
)
from core.algorithm_workspace_controller import (  # noqa: E402
    AlgorithmWorkspaceController,
)
from core.session_repository import SessionRepository  # noqa: E402
from core.workspace_parameters import (  # noqa: E402
    WorkspaceAlgorithmParameters,
    WorkspaceParametersError,
)
from engine.runtime_constants import (  # noqa: E402
    DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT,
    WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_1,
    WORKSPACE_MACD_SIGNAL_MODE_EXTENDED,
)
from core.workspace_runtime import WorkspaceRuntimeError  # noqa: E402


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        repository = SessionRepository(Path(temp_dir) / "Session")
        controller = AlgorithmWorkspaceController(repository)

        first = controller.create_workspace(
            broker="IB",
            account_id="DUM513747",
            account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
            symbol="EURUSD",
            timeframe="M15",
            algorithm="RailAlgorithm",
            data_mode=WORKSPACE_DATA_MODE_REPLAY,
            control_mode=WORKSPACE_CONTROL_MODE_AUTO,
            parameters={"future_parameter": "KEEP"},
            risk_settings={"future_risk": "KEEP"},
            profit_protection={
                "enabled": True,
                "activation_mode": "AFTER_SPREAD",
                "minimum_profit": 20.0,
                "max_profit_drawdown_percent": 30.0,
                "future_profit_guard": "KEEP",
            },
            replay_settings={"speed": 2},
        )
        second = controller.create_workspace(
            broker="IB",
            account_id="DUM513747",
            account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
            symbol="GBPUSD",
            timeframe="H1",
            algorithm="RailAlgorithm",
            data_mode=WORKSPACE_DATA_MODE_REPLAY,
            control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        )

        defaults = WorkspaceAlgorithmParameters.from_workspace(second)
        assert defaults.macd_signal_mode == "EXTENDED"
        assert defaults.alligator_confirmation == "SAME_TIMEFRAME"
        assert defaults.warmup_bars == 3
        assert defaults.spread_limit == 0.00020
        assert defaults.risk_percent == 0.5
        assert defaults.maximum_position_volume == 1000.0
        assert (
            defaults.profit_drawdown_close_percent
            == DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT
        )

        custom = WorkspaceAlgorithmParameters(
            macd_signal_mode=WORKSPACE_MACD_SIGNAL_MODE_EXTENDED,
            alligator_confirmation=WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_1,
            spread_limit=0.00018,
            warmup_bars=25,
            risk_percent=0.75,
            maximum_position_volume=3000,
            profit_drawdown_close_percent=27.5,
        )
        updated = controller.update_workspace_parameters(
            first.workspace_uid,
            custom,
        )

        assert updated.parameters["macd_signal_mode"] == "EXTENDED"
        assert updated.parameters["alligator_confirmation"] == "HIGHER_1"
        assert updated.parameters["spread_limit"] == 0.00018
        assert updated.parameters["warmup_bars"] == 25
        assert updated.parameters["future_parameter"] == "KEEP"
        assert updated.risk_settings["risk_percent"] == 0.75
        assert updated.risk_settings["maximum_position_volume"] == 3000.0
        assert updated.risk_settings["future_risk"] == "KEEP"
        assert updated.profit_protection["max_profit_drawdown_percent"] == 27.5
        assert updated.profit_protection["minimum_profit"] == 20.0
        assert updated.profit_protection["future_profit_guard"] == "KEEP"

        persisted = repository.load_workspace(first.workspace_uid)
        restored_values = WorkspaceAlgorithmParameters.from_workspace(persisted)
        assert restored_values == custom

        second_persisted = repository.load_workspace(second.workspace_uid)
        assert WorkspaceAlgorithmParameters.from_workspace(second_persisted) == defaults

        runtime = controller.attach_workspace_runtime(persisted)
        assert runtime.context.runtime_state == WORKSPACE_STATE_STOPPED
        assert runtime.context.warmup_bars_required == 25
        assert runtime.context.spread_limit == 0.00018
        assert runtime.context.profit_drawdown_close_percent == 27.5
        assert runtime.algorithm_parameters["macd_signal_mode"] == "EXTENDED"
        assert runtime.algorithm_parameters["alligator_confirmation"] == ("HIGHER_1")

        controller.begin_workspace_runtime_start(first.workspace_uid)
        active_edit_blocked = False
        try:
            controller.update_workspace_parameters(
                first.workspace_uid,
                defaults,
            )
        except WorkspaceRuntimeError:
            active_edit_blocked = True
        assert active_edit_blocked

        controller.begin_workspace_runtime_stop(first.workspace_uid)
        controller.complete_workspace_runtime_stop(first.workspace_uid)
        assert runtime.context.runtime_state == WORKSPACE_STATE_STOPPED
        controller.update_workspace_parameters(first.workspace_uid, custom)

        assert (
            WorkspaceAlgorithmParameters(
                profit_drawdown_close_percent=1.0
            ).profit_drawdown_close_percent
            == 1.0
        )
        assert (
            WorkspaceAlgorithmParameters(
                profit_drawdown_close_percent=100.0
            ).profit_drawdown_close_percent
            == 100.0
        )

        invalid_values_blocked = 0
        invalid_payloads = (
            {"spread_limit": 0.0},
            {"warmup_bars": -1},
            {"risk_percent": 0.0},
            {"maximum_position_volume": 0.0},
            {"profit_drawdown_close_percent": 101.0},
            {"macd_signal_mode": "UNKNOWN"},
            {"alligator_confirmation": "UNKNOWN"},
        )
        for payload in invalid_payloads:
            values = {
                "macd_signal_mode": "LINEAR",
                "alligator_confirmation": "SAME_TIMEFRAME",
                "spread_limit": 0.00020,
                "warmup_bars": 3,
                "risk_percent": 0.5,
                "maximum_position_volume": 1000.0,
                "profit_drawdown_close_percent": 30.0,
            }
            values.update(payload)
            try:
                WorkspaceAlgorithmParameters(**values)
            except WorkspaceParametersError:
                invalid_values_blocked += 1
        assert invalid_values_blocked == len(invalid_payloads)

        print("Algorithm Workspace Parameters result")
        print(f"  workspace_uid={first.workspace_uid}")
        print(f"  macd_signal_mode={custom.macd_signal_mode}")
        print("  alligator_confirmation=" f"{custom.alligator_confirmation}")
        print(f"  spread_limit={custom.spread_limit:.6f}")
        print(f"  warmup_bars={custom.warmup_bars}")
        print(f"  risk_percent={custom.risk_percent:.2f}%")
        print("  maximum_position_volume=" f"{custom.maximum_position_volume:.2f}")
        print(
            "  profit_drawdown_close_percent="
            f"{custom.profit_drawdown_close_percent:.1f}%"
        )
        print("  independent_workspaces=True")
        print("  future_keys_preserved=True")
        print(f"  active_edit_blocked={active_edit_blocked}")
        print("  profit_drawdown_range_percent=1..100")
        print(f"  invalid_values_blocked={invalid_values_blocked}")
        print("ALGORITHM_WORKSPACE_PARAMETERS_CHECK=OK")


if __name__ == "__main__":
    main()
