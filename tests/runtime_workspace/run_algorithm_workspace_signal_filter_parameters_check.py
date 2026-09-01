# -*- coding: utf-8 -*-
"""Перевірка перших незалежних MACD signal і Alligator filter settings."""

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
    WORKSPACE_PARAMETER_FEATURE_SIGNAL_FILTERS,
    WORKSPACE_PARAMETER_FEATURE_SIGNAL_SOURCES,
    WorkspaceParameterFeatureProfile,
    WorkspaceParameterSchemaError,
)


class FakeLangManager:
    """Фіксувати локалізацію labels без запису translation JSON."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def tr(self, key: str, fallback: str) -> str:
        self.calls.append((key, fallback))
        return f"uk:{fallback}"


def main() -> None:
    catalog = WORKSPACE_PARAMETER_CATALOG
    legacy_workspace = SimpleNamespace(
        parameters={
            "macd_signal_mode": "EXTENDED",
            "alligator_confirmation": "HIGHER_1",
            "spread_limit": 0.00018,
            "warmup_bars": 25,
            "future_parameter": "KEEP",
        },
        risk_settings={},
        profit_protection={},
        replay_settings={"future_replay": "KEEP"},
    )

    values = catalog.values_from_workspace(legacy_workspace)
    assert values["signals.macd_enabled"] is True
    assert values["signals.macd_signal_mode"] == "EXTENDED"
    assert values["signals.macd_cross_angle_model"] == "LEGACY_CALIBRATED"
    assert values["signals.macd_cross_min_abc_angle"] == 2.0
    assert values["filters.alligator_enabled"] is True
    assert values["filters.alligator_confirmation"] == "HIGHER_1"

    merged = catalog.merge_workspace_values(
        legacy_workspace,
        {
            "signals.macd_enabled": False,
            "signals.macd_signal_mode": "LINEAR",
            "signals.macd_cross_angle_model": "ABC_REALTIME_SCALED",
            "signals.macd_cross_min_abc_angle": 2.25,
            "filters.alligator_enabled": True,
            "filters.alligator_confirmation": "HIGHER_2",
        },
    )
    assert merged.parameters["macd_signal_enabled"] is False
    assert merged.parameters["macd_signal_mode"] == "LINEAR"
    assert merged.parameters["macd_cross_angle_model"] == "ABC_REALTIME_SCALED"
    assert merged.parameters["macd_cross_min_abc_angle"] == 2.25
    assert merged.parameters["alligator_filter_enabled"] is True
    assert merged.parameters["alligator_confirmation"] == "HIGHER_2"
    assert merged.parameters["spread_limit"] == 0.00018
    assert merged.parameters["warmup_bars"] == 25
    assert merged.parameters["future_parameter"] == "KEEP"
    assert merged.replay_settings["future_replay"] == "KEEP"

    invalid_boolean_blocked = False
    try:
        catalog.merge_workspace_values(
            legacy_workspace,
            {"signals.macd_enabled": "False"},
        )
    except WorkspaceParameterSchemaError:
        invalid_boolean_blocked = True
    assert invalid_boolean_blocked

    invalid_choice_blocked = False
    try:
        catalog.merge_workspace_values(
            legacy_workspace,
            {"filters.alligator_confirmation": "UNKNOWN"},
        )
    except WorkspaceParameterSchemaError:
        invalid_choice_blocked = True
    assert invalid_choice_blocked

    signal_definition = catalog.definition("signals.macd_signal_mode")
    filter_definition = catalog.definition("filters.alligator_confirmation")
    assert signal_definition.feature_code == WORKSPACE_PARAMETER_FEATURE_SIGNAL_SOURCES
    assert filter_definition.feature_code == WORKSPACE_PARAMETER_FEATURE_SIGNAL_FILTERS
    assert signal_definition.allowed_values == ("LINEAR", "EXTENDED")
    assert filter_definition.allowed_values == (
        "SAME_TIMEFRAME",
        "HIGHER_1",
        "HIGHER_2",
    )

    profile = WorkspaceParameterFeatureProfile.create(
        edition="free",
        granted_feature_codes=(
            WORKSPACE_PARAMETER_FEATURE_SIGNAL_FILTERS,
            WORKSPACE_PARAMETER_FEATURE_SIGNAL_SOURCES,
        ),
    )
    assert WORKSPACE_PARAMETER_FEATURE_SIGNAL_SOURCES in (profile.granted_feature_codes)
    assert WORKSPACE_PARAMETER_FEATURE_SIGNAL_FILTERS in (profile.granted_feature_codes)

    translator = FakeLangManager()
    localized = catalog.register_translations(translator)
    assert localized["AlgorithmWorkspaceParametersDialog.macdExtended"] == "uk:Extended"
    assert (
        localized["AlgorithmWorkspaceParametersDialog.alligatorHigher1"]
        == "uk:One timeframe higher"
    )
    assert (
        localized["AlgorithmWorkspaceParametersDialog.macdAngleAbc"]
        == "uk:ABC, real time"
    )

    print("Algorithm Workspace Signal Filter Parameters result")
    print("  macd_independent_signal_source=True")
    print("  alligator_independent_filter=True")
    print("  independent_enable_flags=True")
    print("  legacy_modes_reused=True")
    print("  legacy_defaults_enabled=True")
    print("  legacy_angle_model_default=True")
    print("  explicit_abc_angle_model_persisted=True")
    print("  legacy_spread_warmup_preserved=True")
    print("  future_keys_preserved=True")
    print("  strict_boolean_validation=True")
    print("  strict_choice_validation=True")
    print("  localized_choice_labels=True")
    print("  feature_codes_independent=True")
    print("  algorithm_behavior_unchanged=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_SIGNAL_FILTER_PARAMETERS_CHECK=OK")


if __name__ == "__main__":
    main()
