# -*- coding: utf-8 -*-
"""Check per-WSP risk_settings binding to WorkspaceRuntime policy."""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
)
from core.algorithm_workspace_controller import (  # noqa: E402
    AlgorithmWorkspaceController,
)
from core.session_repository import SessionRepository  # noqa: E402
from engine.risk.constants import (  # noqa: E402
    DEFAULT_WORKSPACE_MAX_DAILY_LOSS_PERCENT,
    DEFAULT_WORKSPACE_MAXIMUM_OPEN_POSITIONS,
    DEFAULT_WORKSPACE_MAXIMUM_POSITION_VOLUME,
    DEFAULT_WORKSPACE_REQUIRE_STOP_LOSS,
    DEFAULT_WORKSPACE_RISK_PERCENT,
    RISK_REASON_ACCOUNT_BINDING_MISMATCH,
    RISK_REASON_APPROVED,
    RISK_REASON_STOP_LOSS_REQUIRED,
)
from engine.risk.risk_model import (  # noqa: E402
    WorkspaceRiskPolicy,
    WorkspaceRiskRequest,
)


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
            risk_settings={
                "risk_percent": 0.75,
                "maximum_position_volume": 3000.0,
                "maximum_open_positions": 2,
                "max_daily_loss_percent": 2.5,
                "require_stop_loss": True,
                "future_risk": "KEEP",
            },
        )
        second = controller.create_workspace(
            broker="IB",
            account_id="DUM513747",
            account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
            symbol="GBPUSD",
            timeframe="M15",
            algorithm="RailAlgorithm",
            data_mode=WORKSPACE_DATA_MODE_REPLAY,
            control_mode=WORKSPACE_CONTROL_MODE_AUTO,
            risk_settings={
                "risk_percent": 0.25,
                "maximum_position_volume": 500.0,
                "maximum_open_positions": 1,
                "max_daily_loss_percent": 1.0,
                "require_stop_loss": False,
            },
        )
        legacy = controller.create_workspace(
            broker="IB",
            account_id="DUM513747",
            account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
            symbol="USDJPY",
            timeframe="M15",
            algorithm="RailAlgorithm",
            data_mode=WORKSPACE_DATA_MODE_REPLAY,
            control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        )

        persisted_first = repository.load_workspace(first.workspace_uid)
        persisted_second = repository.load_workspace(second.workspace_uid)
        persisted_legacy = repository.load_workspace(legacy.workspace_uid)

        first_runtime = controller.attach_workspace_runtime(persisted_first)
        second_runtime = controller.attach_workspace_runtime(persisted_second)
        legacy_runtime = controller.attach_workspace_runtime(persisted_legacy)

        assert first_runtime.risk_settings["future_risk"] == "KEEP"
        assert first_runtime.risk_policy.max_risk_percent == 0.75
        assert first_runtime.risk_policy.maximum_position_volume == 3000.0
        assert first_runtime.risk_policy.maximum_open_positions == 2
        assert first_runtime.risk_policy.max_daily_loss_percent == 2.5
        assert first_runtime.risk_policy.require_stop_loss

        assert second_runtime.risk_policy.max_risk_percent == 0.25
        assert second_runtime.risk_policy.maximum_position_volume == 500.0
        assert second_runtime.risk_policy.maximum_open_positions == 1
        assert second_runtime.risk_policy.max_daily_loss_percent == 1.0
        assert not second_runtime.risk_policy.require_stop_loss

        legacy_policy = legacy_runtime.risk_policy
        assert legacy_policy.max_risk_percent == DEFAULT_WORKSPACE_RISK_PERCENT
        assert legacy_policy.maximum_position_volume == (
            DEFAULT_WORKSPACE_MAXIMUM_POSITION_VOLUME
        )
        assert legacy_policy.maximum_open_positions == (
            DEFAULT_WORKSPACE_MAXIMUM_OPEN_POSITIONS
        )
        assert legacy_policy.max_daily_loss_percent == (
            DEFAULT_WORKSPACE_MAX_DAILY_LOSS_PERCENT
        )
        assert legacy_policy.require_stop_loss is (
            DEFAULT_WORKSPACE_REQUIRE_STOP_LOSS
        )

        request = WorkspaceRiskRequest(
            timestamp=datetime(2026, 7, 30, 6, 30, tzinfo=UTC),
            workspace_uid=first.workspace_uid,
            broker="IB",
            account_id="DUM513747",
            symbol="EURUSD",
            side="BUY",
            source_mode=WORKSPACE_DATA_MODE_REPLAY,
            requested_volume=400.0,
            equity=100_000.0,
            estimated_loss_at_stop=200.0,
            stop_loss=None,
            open_positions_count=0,
            daily_realized_pnl=0.0,
            runtime_ready=True,
            binding_verified=True,
            market_valid=True,
            spread_guard_passed=True,
            signal_uid="risk-settings-signal",
        )

        first_decision = first_runtime.evaluate_risk_request(request)
        assert first_decision.blocked
        assert first_decision.reason_code == RISK_REASON_STOP_LOSS_REQUIRED

        second_request = replace(
            request,
            workspace_uid=second.workspace_uid,
            symbol="GBPUSD",
        )
        second_decision = second_runtime.evaluate_risk_request(second_request)
        second_repeat = second_runtime.evaluate_risk_request(second_request)
        assert second_decision == second_repeat
        assert second_decision.allowed
        assert second_decision.reason_code == RISK_REASON_APPROVED

        mismatched = first_runtime.evaluate_risk_request(second_request)
        assert mismatched.blocked
        assert mismatched.reason_code == RISK_REASON_ACCOUNT_BINDING_MISMATCH

        invalid_boolean_blocked = False
        try:
            WorkspaceRiskPolicy.from_risk_settings(
                {"require_stop_loss": "False"}
            )
        except ValueError:
            invalid_boolean_blocked = True
        assert invalid_boolean_blocked

        decisions = (first_decision, second_decision, mismatched)
        assert all(not item.execution_attempted for item in decisions)

        print("Algorithm Workspace Risk Settings result")
        print(f"  first_workspace_uid={first.workspace_uid}")
        print("  first_risk_percent=0.7500%")
        print("  first_maximum_position_volume=3000.00")
        print("  first_require_stop_loss=True")
        print(f"  second_workspace_uid={second.workspace_uid}")
        print("  second_risk_percent=0.2500%")
        print("  second_maximum_position_volume=500.00")
        print("  second_require_stop_loss=False")
        print("  legacy_defaults_applied=True")
        print("  future_keys_preserved=True")
        print("  workspace_binding_guard=True")
        print(f"  invalid_boolean_blocked={invalid_boolean_blocked}")
        print("  deterministic=True")
        print("  broker_execution_attempted=False")
        print("ALGORITHM_WORKSPACE_RISK_SETTINGS_CHECK=OK")


if __name__ == "__main__":
    main()
