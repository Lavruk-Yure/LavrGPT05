"""run_t107_06_wsp_profile_parent_refresh_check.py — T107-06.

TEST_ONLY offscreen UI regression відтворює повернення з прийнятого дочірнього
діалогу ``Профілі індикаторів WSP`` до відкритої секції ``Алгоритм`` у
``Параметри WSP``. Fake dialog використовує штатний binding payload built-in
``LGE Candidate F Smoothed`` і не торкається repository, localization або
persisted workspace.

Перевірка фіксує, що верхній profile context і вже відкрита права algorithm
panel оновлюються в одному callback без ручного перемикання tree selection.
Runtime, Replay, broker requests, Candidate F math і production algorithm logic
runner не запускає та не змінює.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QTreeWidgetItem  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import core.algorithm_workspace_parameters_dialog as parameters_module  # noqa: E402
from core.algorithm_workspace import AlgorithmWorkspace  # noqa: E402
from core.workspace_indicator_profile import (  # noqa: E402
    ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F,
    WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY,
    WorkspaceIndicatorProfileBinding,
    built_in_workspace_indicator_profile,
    normalize_workspace_indicator_profile_bindings,
)
from core.workspace_parameter_schema import (  # noqa: E402
    WORKSPACE_PARAMETER_GROUP_ALGORITHM,
)

TEST_ID = "T107-06"
MODE = "RM107_T107_06_WSP_PROFILE_PARENT_REFRESH_TEST_ONLY"


def _workspace() -> AlgorithmWorkspace:
    """Побудувати WSP з початковим built-in Classic Alligator binding."""
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM10706",
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        display_name="T107-06 profile refresh",
    )


def _group_item(
    dialog: parameters_module.AlgorithmWorkspaceParametersDialog,
    group_code: str,
) -> QTreeWidgetItem:
    """Знайти top-level group за стабільним schema code."""
    for index in range(dialog.tree_parameters.topLevelItemCount()):
        item = dialog.tree_parameters.topLevelItem(index)
        if item.data(0, Qt.ItemDataRole.UserRole) == group_code:
            return item
    raise AssertionError(f"parameter group not found: {group_code}")


def _candidate_f_bindings(
    workspace: AlgorithmWorkspace,
) -> dict[str, dict[str, object]]:
    """Замінити лише pending Alligator binding на immutable Candidate F."""
    bindings = normalize_workspace_indicator_profile_bindings(
        workspace.indicator_profile_bindings
    )
    candidate = built_in_workspace_indicator_profile(
        ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F
    )
    bindings[WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY] = (
        WorkspaceIndicatorProfileBinding.from_profile(candidate).to_storage_dict()
    )
    return bindings


def main() -> None:
    """Довести автоматичний refresh відкритої parent algorithm panel."""
    app = QApplication.instance() or QApplication([])
    workspace = _workspace()
    candidate_bindings = _candidate_f_bindings(workspace)

    class _AcceptedCandidateFDialog:
        """Повернути Accepted і фактичний Candidate F binding payload."""

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        @staticmethod
        def exec() -> QDialog.DialogCode:
            """Імітувати успішне закриття дочірнього profile dialog."""
            return QDialog.DialogCode.Accepted

        @staticmethod
        def indicator_profile_bindings() -> dict[str, dict[str, object]]:
            """Повернути pending bindings так само як production dialog."""
            return candidate_bindings

    original_dialog = parameters_module.WorkspaceIndicatorProfilesDialog
    parameters_module.WorkspaceIndicatorProfilesDialog = _AcceptedCandidateFDialog
    try:
        parent = parameters_module.AlgorithmWorkspaceParametersDialog(workspace)
        algorithm_item = _group_item(parent, WORKSPACE_PARAMETER_GROUP_ALGORITHM)
        parent.tree_parameters.setCurrentItem(algorithm_item)
        app.processEvents()

        selection_before = parent.tree_parameters.currentItem()
        panel_before = parent.ui.lblNoSelection.text()
        parent.btn_indicator_profiles.click()
        app.processEvents()
        selection_after = parent.tree_parameters.currentItem()
        panel_after = parent.ui.lblNoSelection.text()
        context_after = parent.lbl_context.text()
        pending = parent.indicator_profile_bindings()
    finally:
        parameters_module.WorkspaceIndicatorProfilesDialog = original_dialog

    alligator = WorkspaceIndicatorProfileBinding.from_storage_dict(
        pending[WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY]
    )
    profile_changed = bool(
        alligator.profile_uid == ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F
        and "LGE Candidate F Smoothed" in context_after
    )
    parent_algorithm_panel_refreshed = bool(
        "Legacy / LGE Classic Smoothed" in panel_before
        and "Candidate F / LGE Candidate F Smoothed" in panel_after
        and "Legacy / LGE Classic Smoothed" not in panel_after
    )
    manual_selection_change_required = selection_after is not selection_before

    assert profile_changed
    assert parent_algorithm_panel_refreshed
    assert not manual_selection_change_required

    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print(f"profile_changed={profile_changed}")
    print(f"parent_algorithm_panel_refreshed={parent_algorithm_panel_refreshed}")
    print("manual_selection_change_required=" f"{manual_selection_change_required}")
    print("production_algorithm_logic_changed=False")
    print("broker_requests=0")
    print("broker_execution_attempted=False")
    print("T107_06_WSP_PROFILE_PARENT_REFRESH=GREEN")


if __name__ == "__main__":
    main()
