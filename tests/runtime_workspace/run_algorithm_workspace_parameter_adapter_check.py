# -*- coding: utf-8 -*-
"""Перевірка мосту між schema storage і чинними параметрами WSP."""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace_controller import (  # noqa: E402
    AlgorithmWorkspaceController,
)
from core.session_repository import SessionRepository  # noqa: E402
from core.workspace_parameter_adapter import (  # noqa: E402
    WORKSPACE_ALGORITHM_PARAMETER_ADAPTER,
)
from core.workspace_parameter_schema import (  # noqa: E402
    WorkspaceParameterSchemaError,
)
from core.workspace_parameters import (  # noqa: E402
    WorkspaceAlgorithmParameters,
)


def _workspace_view() -> SimpleNamespace:
    return SimpleNamespace(
        parameters={
            "macd_signal_enabled": True,
            "macd_signal_mode": "EXTENDED",
            "alligator_filter_enabled": False,
            "alligator_confirmation": "HIGHER_1",
            "spread_limit": 0.00018,
            "warmup_bars": 25,
            "future_parameter": "KEEP",
        },
        risk_settings={
            "risk_percent": 0.75,
            "maximum_position_volume": 3000.0,
            "maximum_open_positions": 4,
            "max_daily_loss_percent": 1.5,
            "require_stop_loss": False,
            "future_risk": "KEEP",
        },
        profit_protection={
            "max_profit_drawdown_percent": 27.5,
            "future_guard": "KEEP",
        },
        replay_settings={
            "speed": 5,
            "future_replay": "KEEP",
        },
    )


def main() -> None:
    adapter = WORKSPACE_ALGORITHM_PARAMETER_ADAPTER
    workspace = _workspace_view()

    legacy = adapter.legacy_values_from_workspace(workspace)
    assert legacy.macd_signal_mode == "EXTENDED"
    assert legacy.alligator_confirmation == "HIGHER_1"
    assert legacy.spread_limit == 0.00018
    assert legacy.warmup_bars == 25
    assert legacy.risk_percent == 0.75
    assert legacy.maximum_position_volume == 3000.0
    assert legacy.profit_drawdown_close_percent == 27.5

    schema_values = adapter.schema_values_from_workspace(workspace)
    assert len(schema_values) == 15
    assert schema_values["signals.macd_enabled"] is True
    assert schema_values["signals.macd_signal_mode"] == "EXTENDED"
    assert schema_values["signals.macd_cross_angle_model"] == "LEGACY_CALIBRATED"
    assert schema_values["signals.macd_cross_min_abc_angle"] == 2.0
    assert schema_values["filters.alligator_enabled"] is False
    assert schema_values["filters.alligator_confirmation"] == "HIGHER_1"
    assert schema_values["risk.maximum_open_positions"] == 4
    assert schema_values["risk.max_daily_loss_percent"] == 1.5
    assert schema_values["risk.require_stop_loss"] is False

    updated_legacy = WorkspaceAlgorithmParameters(
        macd_signal_mode="LINEAR",
        alligator_confirmation="SAME_TIMEFRAME",
        spread_limit=0.0002,
        warmup_bars=30,
        risk_percent=0.5,
        maximum_position_volume=2500.0,
        profit_drawdown_close_percent=25.0,
    )
    legacy_updates = adapter.schema_updates_from_legacy(updated_legacy)
    assert len(legacy_updates) == 5

    merged = adapter.merge_legacy_values(workspace, updated_legacy)
    assert merged.parameters["macd_signal_enabled"] is True
    assert merged.parameters["macd_signal_mode"] == "LINEAR"
    assert merged.parameters["alligator_filter_enabled"] is False
    assert merged.parameters["alligator_confirmation"] == "SAME_TIMEFRAME"
    assert merged.parameters["spread_limit"] == 0.0002
    assert merged.parameters["warmup_bars"] == 30
    assert merged.parameters["future_parameter"] == "KEEP"
    assert merged.risk_settings["risk_percent"] == 0.5
    assert merged.risk_settings["maximum_position_volume"] == 2500.0
    assert merged.risk_settings["maximum_open_positions"] == 4
    assert merged.risk_settings["max_daily_loss_percent"] == 1.5
    assert merged.risk_settings["require_stop_loss"] is False
    assert merged.risk_settings["future_risk"] == "KEEP"
    assert merged.profit_protection["max_profit_drawdown_percent"] == 25.0
    assert merged.profit_protection["future_guard"] == "KEEP"
    assert merged.replay_settings["speed"] == 5
    assert merged.replay_settings["future_replay"] == "KEEP"

    projected = adapter.legacy_values_after_schema_updates(
        workspace,
        {
            "signals.macd_signal_mode": "LINEAR",
            "signals.macd_cross_angle_model": "ABC_REALTIME_SCALED",
            "signals.macd_cross_min_abc_angle": 2.25,
            "filters.alligator_confirmation": "HIGHER_2",
            "risk.risk_percent": 0.25,
            "risk.maximum_open_positions": 6,
            "risk.profit_drawdown_close_percent": 20.0,
        },
    )
    assert projected.risk_percent == 0.25
    assert projected.profit_drawdown_close_percent == 20.0
    assert projected.macd_signal_mode == "LINEAR"
    assert projected.alligator_confirmation == "HIGHER_2"
    assert projected.warmup_bars == 25

    invalid_boolean_blocked = False
    try:
        adapter.legacy_values_after_schema_updates(
            workspace,
            {"risk.require_stop_loss": "False"},
        )
    except WorkspaceParameterSchemaError:
        invalid_boolean_blocked = True
    assert invalid_boolean_blocked

    dialog_updates: dict[str, object] = dict(schema_values)
    dialog_updates.update(
        {
            "signals.macd_enabled": False,
            "signals.macd_signal_mode": "LINEAR",
            "signals.macd_cross_angle_model": "ABC_REALTIME_SCALED",
            "signals.macd_cross_min_abc_angle": 2.25,
            "filters.alligator_enabled": True,
            "filters.alligator_confirmation": "HIGHER_2",
            "risk.risk_percent": 0.4,
            "risk.maximum_position_volume": 2200.0,
            "risk.maximum_open_positions": 6,
            "risk.max_daily_loss_percent": 1.25,
            "risk.require_stop_loss": True,
            "risk.profit_drawdown_close_percent": 22.5,
        }
    )
    dialog_legacy = adapter.legacy_values_after_schema_updates(
        workspace,
        dialog_updates,
    )
    dialog_merged = adapter.merge_dialog_values(
        workspace,
        dialog_legacy,
        dialog_updates,
    )
    assert dialog_merged.parameters["macd_signal_enabled"] is False
    assert dialog_merged.parameters["macd_signal_mode"] == "LINEAR"
    assert dialog_merged.parameters["macd_cross_angle_model"] == (
        "ABC_REALTIME_SCALED"
    )
    assert dialog_merged.parameters["macd_cross_min_abc_angle"] == 2.25
    assert dialog_merged.parameters["alligator_filter_enabled"] is True
    assert dialog_merged.parameters["alligator_confirmation"] == "HIGHER_2"
    assert dialog_merged.parameters["spread_limit"] == 0.00018
    assert dialog_merged.parameters["warmup_bars"] == 25
    assert dialog_merged.risk_settings["maximum_open_positions"] == 6
    assert dialog_merged.risk_settings["max_daily_loss_percent"] == 1.25
    assert dialog_merged.risk_settings["require_stop_loss"] is True

    with TemporaryDirectory() as temp_dir:
        repository = SessionRepository(Path(temp_dir) / "Session")
        controller = AlgorithmWorkspaceController(repository)
        persisted = controller.create_workspace(
            broker="IB",
            account_id="DUM513747",
            symbol="EURUSD",
            timeframe="M15",
            algorithm="ParameterAdapterProbe",
            parameters=dict(workspace.parameters),
            risk_settings=dict(workspace.risk_settings),
            profit_protection=dict(workspace.profit_protection),
            replay_settings=dict(workspace.replay_settings),
        )
        controller.update_workspace_parameters(
            persisted.workspace_uid,
            dialog_legacy,
            schema_updates=dialog_updates,
        )
        restored = controller.load_workspace(persisted.workspace_uid)
        assert restored.parameters["future_parameter"] == "KEEP"
        assert restored.parameters["macd_signal_enabled"] is False
        assert restored.parameters["macd_signal_mode"] == "LINEAR"
        assert restored.parameters["macd_cross_angle_model"] == (
            "ABC_REALTIME_SCALED"
        )
        assert restored.parameters["macd_cross_min_abc_angle"] == 2.25
        assert restored.parameters["alligator_filter_enabled"] is True
        assert restored.parameters["alligator_confirmation"] == "HIGHER_2"
        assert restored.risk_settings["maximum_open_positions"] == 6
        assert restored.risk_settings["max_daily_loss_percent"] == 1.25
        assert restored.risk_settings["require_stop_loss"] is True
        assert restored.risk_settings["future_risk"] == "KEEP"
        assert restored.profit_protection["future_guard"] == "KEEP"
        assert restored.risk_settings["risk_percent"] == 0.4
        assert restored.risk_settings["maximum_position_volume"] == 2200.0

    assert adapter.catalog.translation_entries()

    print("Algorithm Workspace Parameter Adapter result")
    print("  legacy_fields=7")
    print(f"  schema_parameters={len(schema_values)}")
    print(f"  overlapping_schema_fields={len(legacy_updates)}")
    print("  current_dialog_model_connected=True")
    print("  controller_update_connected=True")
    print("  schema_to_legacy_projection=True")
    print("  advanced_risk_keys_preserved=True")
    print("  future_keys_preserved=True")
    print("  replay_settings_preserved=True")
    print("  strict_boolean_validation=True")
    print("  translation_schema_preserved=True")
    print("  strings_json_manually_edited=False")
    print("  unified_schema_editor_connected=True")
    print("  signal_filter_settings_connected=True")
    print("  macd_angle_model_schema_connected=True")
    print("  macd_abc_angle_save_restore=True")
    print("  legacy_hidden_keys_preserved=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_PARAMETER_ADAPTER_CHECK=OK")


if __name__ == "__main__":
    main()
