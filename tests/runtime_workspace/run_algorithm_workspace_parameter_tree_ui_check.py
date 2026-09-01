# -*- coding: utf-8 -*-
"""Перевірка єдиного Designer-редактора параметрів WSP."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QTreeWidgetItem  # noqa: E402

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    WORKSPACE_STATE_RESTORED,
    AlgorithmWorkspace,
)
from core.algorithm_workspace_parameters_dialog import (  # noqa: E402
    AlgorithmWorkspaceParametersDialog,
)
from core.workspace_parameter_feature_policy import (  # noqa: E402
    workspace_parameter_feature_profile_for_edition,
)
from core.workspace_parameter_schema import (  # noqa: E402
    WORKSPACE_PARAMETER_FEATURE_ADVANCED_RISK,
    WORKSPACE_PARAMETER_FEATURE_RISK_MANAGEMENT,
    WORKSPACE_PARAMETER_FEATURE_SIGNAL_FILTERS,
    WORKSPACE_PARAMETER_FEATURE_SIGNAL_SOURCES,
    WORKSPACE_PARAMETER_GROUP_FILTERS,
    WORKSPACE_PARAMETER_GROUP_RISK_MANAGEMENT,
    WORKSPACE_PARAMETER_GROUP_SIGNALS,
    WorkspaceParameterFeatureProfile,
)
from ui.ui_algorithm_workspace_parameters_dialog import (  # noqa: E402
    Ui_AlgorithmWorkspaceParametersDialog,
)


class FakeLangManager:
    """Імітувати повторний переклад без запису localization JSON."""

    def __init__(self) -> None:
        self.language = "uk"
        self.calls: list[tuple[str, str]] = []

    def tr(self, key: str, fallback: str) -> str:
        self.calls.append((key, fallback))
        return f"{self.language}:{fallback}"


def _workspace() -> AlgorithmWorkspace:
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
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
            "require_stop_loss": True,
            "future_risk": "KEEP",
        },
        profit_protection={
            "max_profit_drawdown_percent": 27.5,
            "future_guard": "KEEP",
        },
    )


def _group_item(
    dialog: AlgorithmWorkspaceParametersDialog,
    code: str,
) -> QTreeWidgetItem:
    for index in range(dialog.tree_parameters.topLevelItemCount()):
        item = dialog.tree_parameters.topLevelItem(index)
        if item.data(0, Qt.ItemDataRole.UserRole) == code:
            return item
    raise AssertionError(f"group not found: {code}")


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)

    lang: Any = FakeLangManager()
    workspace = _workspace()
    pro_profile = workspace_parameter_feature_profile_for_edition("pro")

    dialog = AlgorithmWorkspaceParametersDialog(
        workspace,
        lang,
        feature_profile=pro_profile,
        runtime_state=WORKSPACE_STATE_RESTORED,
    )
    assert isinstance(dialog.ui, Ui_AlgorithmWorkspaceParametersDialog)

    parameters_ui_path = (
        PROJECT_ROOT / "ui" / "algorithm_workspace_parameters_dialog.ui"
    )
    assert parameters_ui_path.is_file()
    ui_root = ElementTree.parse(parameters_ui_path).getroot()
    for object_name in (
        "treeParameters",
        "stackValueEditor",
        "spnFloatValue",
        "spnIntegerValue",
        "cmbBooleanValue",
        "cmbChoiceValue",
        "btnSave",
        "btnClose",
    ):
        assert ui_root.find(f".//widget[@name='{object_name}']") is not None
    for obsolete_name in (
        "btnParameterTree",
        "cmbMacdSignalMode",
        "cmbAlligatorConfirmation",
        "spnSpreadLimit",
        "spnWarmupBars",
    ):
        assert ui_root.find(f".//widget[@name='{obsolete_name}']") is None

    source = (
        PROJECT_ROOT / "core" / "algorithm_workspace_parameters_dialog.py"
    ).read_text(encoding="utf-8")
    assert "AlgorithmWorkspaceParameterTreeDialog" not in source
    assert "create_parameter_tree_dialog" not in source
    for constructor in (
        "QVBoxLayout(",
        "QHBoxLayout(",
        "QLabel(",
        "QPushButton(",
        "QTreeWidget(",
    ):
        assert constructor not in source

    assert dialog.tree_parameters.topLevelItemCount() == 7
    signal_group = _group_item(dialog, WORKSPACE_PARAMETER_GROUP_SIGNALS)
    filter_group = _group_item(dialog, WORKSPACE_PARAMETER_GROUP_FILTERS)
    risk_group = _group_item(
        dialog,
        WORKSPACE_PARAMETER_GROUP_RISK_MANAGEMENT,
    )
    assert signal_group.childCount() == 7
    assert filter_group.childCount() == 2
    assert risk_group.childCount() == 6
    assert (
        sum(
            _group_item(dialog, code).childCount() == 0
            for code in (
                "DATA_REPLAY",
                "ALGORITHM",
                "EXECUTION",
                "DIAGNOSTICS",
            )
        )
        == 4
    )

    dialog.select_parameter("signals.macd_enabled")
    assert dialog.cmb_boolean_value.isEnabled()
    false_index = dialog.cmb_boolean_value.findData(False)
    dialog.cmb_boolean_value.setCurrentIndex(false_index)
    assert dialog.schema_updates()["signals.macd_enabled"] is False

    dialog.select_parameter("signals.macd_signal_mode")
    assert dialog.cmb_choice_value.isEnabled()
    assert dialog.cmb_choice_value.itemText(0) == "uk:Linear"
    linear_index = dialog.cmb_choice_value.findData("LINEAR")
    dialog.cmb_choice_value.setCurrentIndex(linear_index)
    assert dialog.schema_updates()["signals.macd_signal_mode"] == "LINEAR"

    dialog.select_parameter("signals.macd_extremum_min_prominence")
    assert dialog.spn_float_value.isEnabled()
    assert dialog.spn_float_value.decimals() == 6
    assert dialog.spn_float_value.singleStep() == 0.000001
    assert dialog.spn_float_value.value() == 0.00001
    dialog.spn_float_value.setValue(0.000012)
    assert dialog.schema_updates()["signals.macd_extremum_min_prominence"] == 0.000012

    dialog.select_parameter("signals.macd_extremum_to_cross_min_distance")
    assert dialog.spn_float_value.isEnabled()
    assert dialog.spn_float_value.decimals() == 6
    assert dialog.spn_float_value.singleStep() == 0.000001
    assert dialog.spn_float_value.value() == 0.00005
    dialog.spn_float_value.setValue(0.00006)
    assert (
        dialog.schema_updates()["signals.macd_extremum_to_cross_min_distance"]
        == 0.00006
    )

    dialog.select_parameter("signals.macd_cross_angle_model")
    assert dialog.cmb_choice_value.isEnabled()
    assert dialog.cmb_choice_value.itemText(0) == "uk:Legacy calibrated"
    abc_model_index = dialog.cmb_choice_value.findData("ABC_REALTIME_SCALED")
    dialog.cmb_choice_value.setCurrentIndex(abc_model_index)
    assert (
        dialog.schema_updates()["signals.macd_cross_angle_model"]
        == "ABC_REALTIME_SCALED"
    )

    dialog.select_parameter("signals.macd_cross_min_angle")
    assert dialog.spn_float_value.isEnabled()
    assert dialog.spn_float_value.decimals() == 0
    assert dialog.spn_float_value.singleStep() == 1.0
    assert dialog.spn_float_value.value() == 45.0
    dialog.spn_float_value.setValue(50.0)
    assert dialog.schema_updates()["signals.macd_cross_min_angle"] == 50.0

    dialog.select_parameter("signals.macd_cross_min_abc_angle")
    assert dialog.spn_float_value.isEnabled()
    assert dialog.spn_float_value.decimals() == 2
    assert dialog.spn_float_value.singleStep() == 0.01
    assert dialog.spn_float_value.value() == 2.0
    dialog.spn_float_value.setValue(2.25)
    assert dialog.schema_updates()["signals.macd_cross_min_abc_angle"] == 2.25

    dialog.select_parameter("filters.alligator_enabled")
    true_index = dialog.cmb_boolean_value.findData(True)
    dialog.cmb_boolean_value.setCurrentIndex(true_index)
    assert dialog.schema_updates()["filters.alligator_enabled"] is True

    dialog.select_parameter("filters.alligator_confirmation")
    assert dialog.cmb_choice_value.itemText(1) == "uk:One timeframe higher"
    higher_index = dialog.cmb_choice_value.findData("HIGHER_2")
    dialog.cmb_choice_value.setCurrentIndex(higher_index)
    assert dialog.schema_updates()["filters.alligator_confirmation"] == "HIGHER_2"

    dialog.select_parameter("risk.risk_percent")
    assert dialog.spn_float_value.isEnabled()
    dialog.spn_float_value.setValue(0.65)
    assert dialog.schema_updates()["risk.risk_percent"] == 0.65

    dialog.select_parameter("risk.maximum_open_positions")
    assert dialog.spn_integer_value.isEnabled()
    dialog.spn_integer_value.setValue(6)
    assert dialog.schema_updates()["risk.maximum_open_positions"] == 6
    assert dialog.schema_updates()["signals.macd_enabled"] is False
    assert dialog.schema_updates()["filters.alligator_confirmation"] == "HIGHER_2"

    dialog.select_parameter("risk.require_stop_loss")
    assert dialog.cmb_boolean_value.isEnabled()
    false_index = dialog.cmb_boolean_value.findData(False)
    dialog.cmb_boolean_value.setCurrentIndex(false_index)
    assert dialog.schema_updates()["risk.require_stop_loss"] is False
    assert dialog.has_unsaved_changes()

    legacy = dialog.parameter_values()
    assert legacy.macd_signal_mode == "LINEAR"
    assert legacy.alligator_confirmation == "HIGHER_2"
    assert legacy.spread_limit == 0.00018
    assert legacy.warmup_bars == 25
    assert legacy.risk_percent == 0.65

    lang.language = "de"
    dialog.apply_translation()
    assert dialog.windowTitle() == "de:Workspace parameters"
    assert dialog.schema_updates()["risk.maximum_open_positions"] == 6
    translated_item = dialog.parameter_item("risk.risk_percent")
    assert translated_item is not None
    assert translated_item.text(0).startswith("de:")

    locked_profile = WorkspaceParameterFeatureProfile.create(
        edition="free",
        granted_feature_codes=(),
    )
    locked_dialog = AlgorithmWorkspaceParametersDialog(
        workspace,
        lang,
        feature_profile=locked_profile,
        runtime_state=WORKSPACE_STATE_RESTORED,
    )
    locked_dialog.select_parameter("risk.risk_percent")
    assert not locked_dialog.spn_float_value.isEnabled()
    assert "Locked by license" in locked_dialog.lbl_status_value.text()

    free_profile = workspace_parameter_feature_profile_for_edition("free")
    pro_plus_profile = workspace_parameter_feature_profile_for_edition("pro_plus")
    assert (
        WORKSPACE_PARAMETER_FEATURE_RISK_MANAGEMENT
        in free_profile.granted_feature_codes
    )
    assert (
        WORKSPACE_PARAMETER_FEATURE_SIGNAL_SOURCES in free_profile.granted_feature_codes
    )
    assert (
        WORKSPACE_PARAMETER_FEATURE_SIGNAL_FILTERS in free_profile.granted_feature_codes
    )
    assert (
        WORKSPACE_PARAMETER_FEATURE_ADVANCED_RISK
        not in pro_profile.granted_feature_codes
    )
    assert (
        WORKSPACE_PARAMETER_FEATURE_ADVANCED_RISK
        in pro_plus_profile.granted_feature_codes
    )

    translation_keys = {key for key, _fallback in lang.calls}
    assert "AlgorithmWorkspaceParametersDialog.btnClose" in translation_keys
    assert "AlgorithmWorkspaceParametersDialog.context" in translation_keys
    assert "WorkspaceParameterGroup.riskManagement.title" in translation_keys
    assert "WorkspaceParameterGroup.filters.title" in translation_keys
    assert "AlgorithmWorkspaceParametersDialog.macdLinear" in translation_keys
    assert "WorkspaceParameter.riskPercent.description" in translation_keys
    assert "WorkspaceParameter.macdExtremumMinProminence.title" in translation_keys
    assert "WorkspaceParameter.macdExtremumToCrossMinDistance.title" in translation_keys
    assert "WorkspaceParameter.macdCrossMinAngle.title" in translation_keys
    assert "WorkspaceParameter.macdCrossAngleModel.title" in translation_keys
    assert "WorkspaceParameter.macdCrossMinAbcAngle.title" in translation_keys
    assert "AlgorithmWorkspaceParametersDialog.macdAngleAbc" in translation_keys

    locked_dialog.accept()
    dialog.accept()

    print("Algorithm Workspace Parameter Tree UI result")
    print("  groups=7")
    print("  signal_nodes=7")
    print("  filter_nodes=2")
    print("  risk_nodes=6")
    print("  empty_groups_visible=4")
    print("  single_designer_dialog=True")
    print("  tree_and_editor_unified=True")
    print("  separate_tree_dialog_unused=True")
    print("  schema_signal_filter_editing=True")
    print("  macd_quality_parameters_visible=True")
    print("  macd_quality_parameters_editable=True")
    print("  macd_quality_parameter_defaults=0.00001/0.00005/45/2.00")
    print("  macd_angle_model_choice_visible=True")
    print("  schema_risk_editing=True")
    print("  localized_choice_labels=True")
    print("  restored_state_editable=True")
    print("  legacy_signal_filter_values_preserved=True")
    print("  legacy_spread_warmup_values_preserved=True")
    print("  legacy_fields_hidden_from_ui=True")
    print("  license_lock_visible=True")
    print("  localized=True")
    print("  retranslation_supported=True")
    print("  translation_keys_registered=True")
    print("  strings_json_manually_edited=False")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_PARAMETER_TREE_UI_CHECK=OK")


if __name__ == "__main__":
    main()
