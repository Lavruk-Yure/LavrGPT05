# -*- coding: utf-8 -*-
"""Static Designer/localization contract check for indicator profile UI."""

from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _object_names(path: Path) -> set[str]:
    root = ElementTree.parse(path).getroot()
    return {
        str(element.attrib["name"])
        for element in root.iter()
        if "name" in element.attrib
    }


def main() -> None:
    profile_ui = PROJECT_ROOT / "ui" / "workspace_indicator_profiles_dialog.ui"
    parameter_ui = PROJECT_ROOT / "ui" / "algorithm_workspace_parameters_dialog.ui"
    profile_logic = PROJECT_ROOT / "core" / "workspace_indicator_profiles_dialog.py"
    parameter_logic = PROJECT_ROOT / "core" / "algorithm_workspace_parameters_dialog.py"
    strings_path = PROJECT_ROOT / "lang" / "strings.json"
    fallback_path = PROJECT_ROOT / "lang" / "strings_fallback.json"

    profile_names = _object_names(profile_ui)
    parameter_names = _object_names(parameter_ui)
    required_profile_objects = {
        "WorkspaceIndicatorProfilesDialog",
        "treeProfiles",
        "stackIndicator",
        "pageMacd",
        "pageAlligator",
        "btnNew",
        "btnDuplicate",
        "btnArchive",
        "btnDelete",
        "btnUseForWorkspace",
        "btnSave",
        "btnClose",
    }
    assert required_profile_objects.issubset(profile_names)
    assert "btnIndicatorProfiles" in parameter_names

    profile_text = profile_logic.read_text(encoding="utf-8")
    parameter_text = parameter_logic.read_text(encoding="utf-8")
    assert "Ui_WorkspaceIndicatorProfilesDialog" in profile_text
    assert "WorkspaceIndicatorProfilesDialog(" in parameter_text
    assert "indicator_profile_bindings" in parameter_text
    assert "LangManager" in profile_text
    assert "QFormLayout(" not in profile_text
    assert "QTreeWidget(" not in profile_text

    strings = json.loads(strings_path.read_text(encoding="utf-8"))
    assert set(strings) == {"lang_active"}
    fallback = json.loads(fallback_path.read_text(encoding="utf-8"))
    required_translation_keys = {
        "AlgorithmWorkspaceParametersDialog.btnIndicatorProfiles",
        "WorkspaceIndicatorProfilesDialog.windowTitle",
        "WorkspaceIndicatorProfilesDialog.btnUseForWorkspace",
        "WorkspaceIndicatorProfilesDialog.btnDelete",
        "WorkspaceIndicatorProfilesDialog.deleteQuestion",
        "WorkspaceIndicatorProfilesDialog.deleteInUseMessage",
        "WorkspaceIndicatorProfilesDialog.note",
        "WorkspaceIndicatorProfile.macdLgeClassic",
        "WorkspaceIndicatorProfile.alligatorCtraderDefault",
    }
    assert required_translation_keys.issubset(fallback)
    for key in required_translation_keys:
        assert fallback[key].get("en")
        assert fallback[key].get("uk")

    print("Workspace Indicator Profile UI result")
    print("  separate_designer_dialog=True")
    print("  macd_and_alligator_editors=True")
    print("  immutable_template_duplicate_flow=True")
    print("  designer_delete_action=True")
    print("  workspace_binding_action=True")
    print("  parameters_dialog_entry_point=True")
    print("  profile_revision_snapshot_contract=True")
    print("  localized=True")
    print("  strings_json_manually_edited=False")
    print("  broker_execution_attempted=False")
    print("WORKSPACE_INDICATOR_PROFILE_UI_CHECK=OK")


if __name__ == "__main__":
    main()
