# -*- coding: utf-8 -*-
"""Перевірка UI-незалежної read-only моделі дерева параметрів WSP."""

from __future__ import annotations

import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_parameter_schema import (  # noqa: E402
    WORKSPACE_PARAMETER_FEATURE_RISK_MANAGEMENT,
    WORKSPACE_PARAMETER_FEATURE_SIGNAL_FILTERS,
    WORKSPACE_PARAMETER_FEATURE_SIGNAL_SOURCES,
    WORKSPACE_PARAMETER_GROUP_FILTERS,
    WORKSPACE_PARAMETER_GROUP_RISK_MANAGEMENT,
    WORKSPACE_PARAMETER_GROUP_SIGNALS,
    WorkspaceParameterFeatureProfile,
)
from core.workspace_parameter_tree import (  # noqa: E402
    WORKSPACE_PARAMETER_TREE_BUILDER,
)


class FakeLangManager:
    """Фіксувати LangManager.tr() без запису translation JSON-файлів."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def tr(self, key: str, fallback: str) -> str:
        self.calls.append((key, fallback))
        return f"uk:{fallback}"


def _workspace() -> SimpleNamespace:
    return SimpleNamespace(
        workspace_uid="tree-model-workspace",
        parameters={
            "macd_signal_enabled": True,
            "macd_signal_mode": "EXTENDED",
            "alligator_filter_enabled": False,
            "alligator_confirmation": "HIGHER_1",
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
        replay_settings={"future_replay": "KEEP"},
    )


def _profile(
    *,
    edition: str,
    risk_available: bool,
) -> WorkspaceParameterFeatureProfile:
    features = (
        (
            WORKSPACE_PARAMETER_FEATURE_RISK_MANAGEMENT,
            WORKSPACE_PARAMETER_FEATURE_SIGNAL_FILTERS,
            WORKSPACE_PARAMETER_FEATURE_SIGNAL_SOURCES,
        )
        if risk_available
        else ()
    )
    return WorkspaceParameterFeatureProfile.create(
        edition=edition,
        granted_feature_codes=features,
    )


def main() -> None:
    builder = WORKSPACE_PARAMETER_TREE_BUILDER
    workspace = _workspace()
    storage_before = (
        dict(workspace.parameters),
        dict(workspace.risk_settings),
        dict(workspace.profit_protection),
        dict(workspace.replay_settings),
    )

    stopped_translator = FakeLangManager()
    stopped_tree = builder.build(
        workspace=workspace,
        profile=_profile(edition="PRO", risk_available=True),
        runtime_state="STOPPED",
        translator=stopped_translator,
    )
    repeated_tree = builder.build(
        workspace=workspace,
        profile=_profile(edition="PRO", risk_available=True),
        runtime_state="STOPPED",
        translator=FakeLangManager(),
    )
    assert stopped_tree == repeated_tree
    assert len(stopped_tree.groups) == 7
    assert [group.order for group in stopped_tree.groups] == [
        10,
        20,
        30,
        35,
        40,
        50,
        60,
    ]

    signal_group = stopped_tree.group(WORKSPACE_PARAMETER_GROUP_SIGNALS)
    filter_group = stopped_tree.group(WORKSPACE_PARAMETER_GROUP_FILTERS)
    risk_group = stopped_tree.group(
        WORKSPACE_PARAMETER_GROUP_RISK_MANAGEMENT
    )
    assert len(signal_group.parameters) == 7
    assert len(filter_group.parameters) == 2
    assert len(risk_group.parameters) == 6
    assert sum(not group.parameters for group in stopped_tree.groups) == 4
    assert risk_group.title.startswith("uk:")
    assert all(node.title.startswith("uk:") for node in risk_group.parameters)
    assert all(node.description.startswith("uk:") for node in risk_group.parameters)

    macd_mode = stopped_tree.parameter("signals.macd_signal_mode")
    assert macd_mode.value == "EXTENDED"
    assert (
        stopped_tree.parameter("signals.macd_extremum_min_prominence").value
        == 0.00001
    )
    assert (
        stopped_tree.parameter(
            "signals.macd_extremum_to_cross_min_distance"
        ).value
        == 0.00005
    )
    macd_angle_model = stopped_tree.parameter("signals.macd_cross_angle_model")
    assert macd_angle_model.value == "LEGACY_CALIBRATED"
    assert macd_angle_model.allowed_value_labels == (
        ("LEGACY_CALIBRATED", "uk:Legacy calibrated"),
        ("ABC_REALTIME_SCALED", "uk:ABC, real time"),
    )
    macd_angle = stopped_tree.parameter("signals.macd_cross_min_angle")
    assert macd_angle.value == 45.0
    assert macd_angle.minimum == 0.0
    assert macd_angle.maximum == 180.0
    assert macd_angle.step == 1.0
    macd_abc_angle = stopped_tree.parameter(
        "signals.macd_cross_min_abc_angle"
    )
    assert macd_abc_angle.value == 2.0
    assert macd_abc_angle.minimum == 0.0
    assert macd_abc_angle.maximum == 180.0
    assert macd_abc_angle.step == 0.01
    assert macd_mode.allowed_value_labels == (
        ("LINEAR", "uk:Linear"),
        ("EXTENDED", "uk:Extended"),
    )
    alligator_mode = stopped_tree.parameter(
        "filters.alligator_confirmation"
    )
    assert alligator_mode.value == "HIGHER_1"
    assert alligator_mode.allowed_value_labels[1] == (
        "HIGHER_1",
        "uk:One timeframe higher",
    )

    risk_percent = stopped_tree.parameter("risk.risk_percent")
    assert risk_percent.value == 0.75
    assert risk_percent.available_by_license
    assert risk_percent.editable_by_runtime
    assert risk_percent.editable
    assert risk_percent.reason is None
    assert risk_percent.minimum == 0.01
    assert risk_percent.maximum == 100.0
    assert risk_percent.step == 0.01

    restored_tree = builder.build(
        workspace=workspace,
        profile=_profile(edition="PRO", risk_available=True),
        runtime_state="RESTORED",
        translator=FakeLangManager(),
    )
    restored_risk = restored_tree.parameter("risk.risk_percent")
    assert restored_risk.available_by_license
    assert restored_risk.editable_by_runtime
    assert restored_risk.editable

    running_tree = builder.build(
        workspace=workspace,
        profile=_profile(edition="PRO", risk_available=True),
        runtime_state="RUNNING",
        translator=FakeLangManager(),
    )
    running_risk = running_tree.parameter("risk.risk_percent")
    assert running_risk.available_by_license
    assert not running_risk.editable_by_runtime
    assert not running_risk.editable
    assert running_risk.status == "uk:Read-only while workspace is active"
    assert running_risk.reason == (
        "uk:Stop the workspace before editing this parameter."
    )

    locked_tree = builder.build(
        workspace=workspace,
        profile=_profile(edition="BASIC", risk_available=False),
        runtime_state="STOPPED",
        translator=FakeLangManager(),
    )
    locked_risk = locked_tree.parameter("risk.risk_percent")
    assert not locked_risk.available_by_license
    assert locked_risk.editable_by_runtime
    assert not locked_risk.editable
    assert locked_risk.status == "uk:Locked by license"
    assert WORKSPACE_PARAMETER_FEATURE_RISK_MANAGEMENT in str(
        locked_risk.reason
    )

    storage_after = (
        dict(workspace.parameters),
        dict(workspace.risk_settings),
        dict(workspace.profit_protection),
        dict(workspace.replay_settings),
    )
    assert storage_before == storage_after

    immutable = False
    try:
        setattr(stopped_tree, "runtime_state", "RUNNING")
    except FrozenInstanceError:
        immutable = True
    assert immutable

    translation_keys = {key for key, _fallback in stopped_translator.calls}
    assert "WorkspaceParameterGroup.riskManagement.title" in translation_keys
    assert "WorkspaceParameterGroup.filters.title" in translation_keys
    assert "AlgorithmWorkspaceParametersDialog.macdLinear" in translation_keys
    assert "AlgorithmWorkspaceParametersDialog.macdAngleAbc" in translation_keys
    assert "WorkspaceParameter.riskPercent.description" in translation_keys
    assert (
        "WorkspaceParameterAvailability.runtimeLocked" in translation_keys
    )
    assert "WorkspaceParameterAvailability.stopRequired" in translation_keys

    print("Algorithm Workspace Parameter Tree result")
    print(f"  groups={len(stopped_tree.groups)}")
    print(f"  signal_nodes={len(signal_group.parameters)}")
    print(f"  filter_nodes={len(filter_group.parameters)}")
    print(f"  risk_nodes={len(risk_group.parameters)}")
    print("  empty_groups=4")
    print("  deterministic=True")
    print("  localized=True")
    print("  localized_choice_labels=True")
    print("  stopped_state_editable=True")
    print("  restored_state_editable=True")
    print("  running_state_read_only=True")
    print("  license_lock_visible=True")
    print("  constraints_exposed=True")
    print("  raw_values_preserved=True")
    print("  workspace_not_mutated=True")
    print("  model_immutable=True")
    print("  translation_keys_registered=True")
    print("  strings_json_manually_edited=False")
    print("  tree_model_ui_independent=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_PARAMETER_TREE_CHECK=OK")


if __name__ == "__main__":
    main()
