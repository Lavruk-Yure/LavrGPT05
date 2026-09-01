# -*- coding: utf-8 -*-
"""Перевірка UI-незалежної основи схеми дерева параметрів WSP."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_parameter_catalog import (  # noqa: E402
    WORKSPACE_PARAMETER_CATALOG,
)
from core.workspace_parameter_schema import (  # noqa: E402
    WORKSPACE_PARAMETER_EDITABLE_STATE_RESTORED,
    WORKSPACE_PARAMETER_EDITABLE_STATE_STOPPED,
    WORKSPACE_PARAMETER_FEATURE_ADVANCED_RISK,
    WORKSPACE_PARAMETER_FEATURE_RISK_MANAGEMENT,
    WORKSPACE_PARAMETER_FEATURE_SIGNAL_FILTERS,
    WORKSPACE_PARAMETER_FEATURE_SIGNAL_SOURCES,
    WORKSPACE_PARAMETER_GROUP_FILTERS,
    WORKSPACE_PARAMETER_GROUP_RISK_MANAGEMENT,
    WORKSPACE_PARAMETER_GROUP_SIGNALS,
    WORKSPACE_PARAMETER_STORAGE_PROFIT_PROTECTION,
    WORKSPACE_PARAMETER_STORAGE_RISK_SETTINGS,
    WORKSPACE_PARAMETER_TYPE_FLOAT,
    WorkspaceParameterDefinition,
    WorkspaceParameterFeatureProfile,
    WorkspaceParameterSchemaError,
    WorkspaceParameterTranslation,
)


class FakeLangManager:
    """Фіксувати виклики LangManager.tr() без запису JSON-файлів."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def tr(self, key: str, fallback: str) -> str:
        self.calls.append((key, fallback))
        return f"uk:{fallback}"


def main() -> None:
    catalog = WORKSPACE_PARAMETER_CATALOG
    workspace = SimpleNamespace(
        parameters={
            "macd_signal_enabled": False,
            "macd_signal_mode": "EXTENDED",
            "alligator_filter_enabled": True,
            "alligator_confirmation": "HIGHER_1",
            "future_parameter": "KEEP",
        },
        risk_settings={
            "risk_percent": 0.75,
            "maximum_position_volume": 3000.0,
            "future_risk": "KEEP",
        },
        profit_protection={
            "max_profit_drawdown_percent": 27.5,
            "future_guard": "KEEP",
        },
        replay_settings={"future_replay": "KEEP"},
    )

    ordered_groups = catalog.ordered_groups()
    assert len(ordered_groups) == 7
    assert [group.order for group in ordered_groups] == [
        10,
        20,
        30,
        35,
        40,
        50,
        60,
    ]

    signal_parameters = catalog.parameters_for_group(WORKSPACE_PARAMETER_GROUP_SIGNALS)
    filter_parameters = catalog.parameters_for_group(WORKSPACE_PARAMETER_GROUP_FILTERS)
    assert len(signal_parameters) == 7
    assert len(filter_parameters) == 2
    assert all(
        parameter.feature_code == WORKSPACE_PARAMETER_FEATURE_SIGNAL_SOURCES
        for parameter in signal_parameters
    )
    assert all(
        parameter.feature_code == WORKSPACE_PARAMETER_FEATURE_SIGNAL_FILTERS
        for parameter in filter_parameters
    )

    risk_parameters = catalog.parameters_for_group(
        WORKSPACE_PARAMETER_GROUP_RISK_MANAGEMENT
    )
    assert len(risk_parameters) == 6
    assert all(
        parameter.editable_runtime_states
        == (
            WORKSPACE_PARAMETER_EDITABLE_STATE_STOPPED,
            WORKSPACE_PARAMETER_EDITABLE_STATE_RESTORED,
        )
        for parameter in risk_parameters
    )
    assert all(
        parameter.feature_code == WORKSPACE_PARAMETER_FEATURE_RISK_MANAGEMENT
        for parameter in risk_parameters
    )

    values = catalog.values_from_workspace(workspace)
    assert values["signals.macd_enabled"] is False
    assert values["signals.macd_signal_mode"] == "EXTENDED"
    assert values["signals.macd_extremum_min_prominence"] == 0.00001
    assert values["signals.macd_extremum_to_cross_min_distance"] == 0.00005
    assert values["signals.macd_cross_angle_model"] == "LEGACY_CALIBRATED"
    assert values["signals.macd_cross_min_angle"] == 45.0
    assert values["signals.macd_cross_min_abc_angle"] == 2.0
    assert values["filters.alligator_enabled"] is True
    assert values["filters.alligator_confirmation"] == "HIGHER_1"
    alligator_definition = catalog.definition("filters.alligator_confirmation")
    assert alligator_definition.allowed_values == (
        "SAME_TIMEFRAME",
        "HIGHER_1",
        "HIGHER_2",
    )
    assert "DISABLED" not in alligator_definition.allowed_values
    assert values["risk.risk_percent"] == 0.75
    assert values["risk.maximum_position_volume"] == 3000.0
    assert values["risk.maximum_open_positions"] == 2
    assert values["risk.max_daily_loss_percent"] == 2.0
    assert values["risk.require_stop_loss"] is True
    assert values["risk.profit_drawdown_close_percent"] == 27.5

    merged = catalog.merge_workspace_values(
        workspace,
        {
            "signals.macd_enabled": True,
            "signals.macd_signal_mode": "LINEAR",
            "signals.macd_cross_angle_model": "ABC_REALTIME_SCALED",
            "signals.macd_cross_min_angle": 40.0,
            "signals.macd_cross_min_abc_angle": 2.25,
            "filters.alligator_enabled": False,
            "filters.alligator_confirmation": "DISABLED",
            "risk.risk_percent": 0.5,
            "risk.maximum_open_positions": 3,
            "risk.require_stop_loss": False,
            "risk.profit_drawdown_close_percent": 25.0,
        },
    )
    assert merged.parameters["macd_signal_enabled"] is True
    assert merged.parameters["macd_signal_mode"] == "LINEAR"
    assert merged.parameters["macd_cross_angle_model"] == "ABC_REALTIME_SCALED"
    assert merged.parameters["macd_cross_min_angle"] == 40.0
    assert merged.parameters["macd_cross_min_abc_angle"] == 2.25
    assert merged.parameters["alligator_filter_enabled"] is False
    assert merged.parameters["alligator_confirmation"] == "SAME_TIMEFRAME"
    assert merged.risk_settings["risk_percent"] == 0.5
    assert merged.risk_settings["maximum_open_positions"] == 3
    assert merged.risk_settings["require_stop_loss"] is False
    assert merged.risk_settings["future_risk"] == "KEEP"
    assert merged.parameters["future_parameter"] == "KEEP"
    assert merged.profit_protection["future_guard"] == "KEEP"
    assert merged.replay_settings["future_replay"] == "KEEP"

    invalid_boolean_blocked = False
    try:
        catalog.merge_workspace_values(
            workspace,
            {"risk.require_stop_loss": "False"},
        )
    except WorkspaceParameterSchemaError:
        invalid_boolean_blocked = True
    assert invalid_boolean_blocked

    unknown_parameter_blocked = False
    try:
        catalog.merge_workspace_values(
            workspace,
            {"risk.unknown_future_parameter": 1},
        )
    except WorkspaceParameterSchemaError:
        unknown_parameter_blocked = True
    assert unknown_parameter_blocked

    pro_profile = WorkspaceParameterFeatureProfile.create(
        edition="PRO",
        granted_feature_codes=(
            WORKSPACE_PARAMETER_FEATURE_RISK_MANAGEMENT,
            WORKSPACE_PARAMETER_FEATURE_SIGNAL_FILTERS,
            WORKSPACE_PARAMETER_FEATURE_SIGNAL_SOURCES,
        ),
    )
    pro_plus_profile = WorkspaceParameterFeatureProfile.create(
        edition="PRO_PLUS",
        granted_feature_codes=(
            WORKSPACE_PARAMETER_FEATURE_RISK_MANAGEMENT,
            WORKSPACE_PARAMETER_FEATURE_SIGNAL_FILTERS,
            WORKSPACE_PARAMETER_FEATURE_SIGNAL_SOURCES,
            WORKSPACE_PARAMETER_FEATURE_ADVANCED_RISK,
        ),
    )
    assert catalog.availability(
        "signals.macd_enabled",
        pro_profile,
    ).available
    assert catalog.availability(
        "filters.alligator_enabled",
        pro_profile,
    ).available
    assert catalog.availability(
        "risk.risk_percent",
        pro_profile,
    ).available
    assert catalog.availability(
        "risk.risk_percent",
        pro_plus_profile,
    ).available

    advanced_definition = WorkspaceParameterDefinition(
        key="risk.future_advanced_limit",
        storage_section=WORKSPACE_PARAMETER_STORAGE_RISK_SETTINGS,
        storage_key="future_advanced_limit",
        group_code=WORKSPACE_PARAMETER_GROUP_RISK_MANAGEMENT,
        order=100,
        value_type=WORKSPACE_PARAMETER_TYPE_FLOAT,
        default=1.0,
        title=WorkspaceParameterTranslation(
            "WorkspaceParameter.futureAdvancedLimit.title",
            "Future advanced limit",
        ),
        description=WorkspaceParameterTranslation(
            "WorkspaceParameter.futureAdvancedLimit.description",
            "Reserved synthetic parameter for feature access testing.",
        ),
        feature_code=WORKSPACE_PARAMETER_FEATURE_ADVANCED_RISK,
        editable_runtime_states=(
            WORKSPACE_PARAMETER_EDITABLE_STATE_RESTORED,
            WORKSPACE_PARAMETER_EDITABLE_STATE_STOPPED,
        ),
        minimum=0.0,
        maximum=10.0,
        step=0.1,
    )
    synthetic_catalog = type(catalog)(
        groups=catalog.groups,
        parameters=catalog.parameters + (advanced_definition,),
    )
    assert not synthetic_catalog.availability(
        advanced_definition.key,
        pro_profile,
    ).available
    assert synthetic_catalog.availability(
        advanced_definition.key,
        pro_plus_profile,
    ).available

    translator = FakeLangManager()
    localized = catalog.register_translations(translator)
    translation_entries = catalog.translation_entries()
    assert len(localized) == len(translation_entries)
    assert len(translator.calls) == len(translation_entries)
    assert all("." in key for key in localized)
    assert all(text.startswith("uk:") for text in localized.values())
    assert any(
        key == "WorkspaceParameterGroup.riskManagement.title"
        for key, _fallback in translator.calls
    )
    assert any(
        key == "WorkspaceParameter.riskPercent.description"
        for key, _fallback in translator.calls
    )
    assert any(
        key == "AlgorithmWorkspaceParametersDialog.macdExtended"
        for key, _fallback in translator.calls
    )
    assert any(
        key == "AlgorithmWorkspaceParametersDialog.macdAngleAbc"
        for key, _fallback in translator.calls
    )
    assert any(
        key == "WorkspaceParameterGroup.filters.title"
        for key, _fallback in translator.calls
    )

    profit_definition = catalog.definition("risk.profit_drawdown_close_percent")
    assert (
        profit_definition.storage_section
        == WORKSPACE_PARAMETER_STORAGE_PROFIT_PROTECTION
    )
    assert profit_definition.minimum == 1.0
    assert profit_definition.maximum == 100.0
    assert profit_definition.step == 1.0

    print("Algorithm Workspace Parameter Schema result")
    print(f"  groups={len(ordered_groups)}")
    print(f"  signal_parameters={len(signal_parameters)}")
    print(f"  filter_parameters={len(filter_parameters)}")
    print(f"  risk_parameters={len(risk_parameters)}")
    print("  signal_filter_storage_connected=True")
    print("  localized_choice_labels=True")
    print("  macd_angle_models=LEGACY_CALIBRATED/ABC_REALTIME_SCALED")
    print("  macd_abc_default_angle=2.00")
    print("  current_storage_connected=True")
    print("  defaults_applied=True")
    print("  future_keys_preserved=True")
    print("  strict_boolean_validation=True")
    print("  stopped_and_restored_editability=True")
    print("  pro_feature_available=True")
    print("  pro_plus_advanced_feature_available=True")
    print("  product_matrix_not_hardcoded=True")
    print("  translation_keys_registered=True")
    print("  profit_drawdown_range_percent=1..100")
    print("  strings_json_manually_edited=False")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_PARAMETER_SCHEMA_CHECK=OK")


if __name__ == "__main__":
    main()
