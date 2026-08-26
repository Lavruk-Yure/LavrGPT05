# -*- coding: utf-8 -*-
"""UI-check збереження Candidate F policy у user profile revision.

RoadMap101 №38 зберігає trade-gate thresholds у Alligator profile snapshot,
але поточний редактор показує лише математичні Jaw/Teeth/Lips поля. Тест
дублює immutable Candidate F, змінює Jaw через штатний UI та перевіряє, що
нова user revision не втрачає ``logic_mode`` і жоден прихований threshold.
Broker/runtime/Replay не запускаються.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QTreeWidgetItem  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import AlgorithmWorkspace  # noqa: E402
from core.workspace_indicator_profile import (  # noqa: E402
    ALLIGATOR_LOGIC_MODE_CANDIDATE_F,
    ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F,
)
from core.workspace_indicator_profile_repository import (  # noqa: E402
    WorkspaceIndicatorProfileRepository,
)
from core.workspace_indicator_profiles_dialog import (  # noqa: E402
    WorkspaceIndicatorProfilesDialog,
)

CANDIDATE_POLICY_KEYS = (
    "logic_mode",
    "trend_start_confirmation_bars",
    "deferred_expiry_bars",
    "opening_collapse_threshold",
    "volatility_lookback_bars",
    "weak_max_active_age",
    "weak_max_opening",
    "spike_min_range_ratio",
    "spike_max_opening_delta",
    "spike_max_slope_delta",
    "overextended_min_slope",
    "overextended_min_opening",
)


def _workspace() -> AlgorithmWorkspace:
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM000001",
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        display_name="RoadMap101 Candidate F revision UI",
    )


def _find_profile_item(
    parent: QTreeWidgetItem,
    profile_uid: str,
) -> QTreeWidgetItem | None:
    for index in range(parent.childCount()):
        child = parent.child(index)
        if child.data(0, Qt.ItemDataRole.UserRole) == profile_uid:
            return child
        nested = _find_profile_item(child, profile_uid)
        if nested is not None:
            return nested
    return None


def _unexpected_question(
    *_args: object,
    **_kwargs: object,
) -> QMessageBox.StandardButton:
    raise AssertionError("Unexpected modal during Candidate F revision UI check")


def main() -> None:
    app = QApplication.instance() or QApplication([])
    original_question = QMessageBox.question
    QMessageBox.question = _unexpected_question
    try:
        with TemporaryDirectory() as tmp_dir:
            repository = WorkspaceIndicatorProfileRepository(Path(tmp_dir))
            repository.ensure_storage()
            profile = repository.duplicate_profile(
                ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F,
                name="Candidate F User Copy",
            )
            assert profile.parameters["logic_mode"] == (
                ALLIGATOR_LOGIC_MODE_CANDIDATE_F
            )
            frozen_policy = {
                key: profile.parameters[key] for key in CANDIDATE_POLICY_KEYS
            }

            dialog = WorkspaceIndicatorProfilesDialog(
                _workspace(),
                repository=repository,
            )
            item = _find_profile_item(
                dialog.tree_profiles.invisibleRootItem(),
                profile.profile_uid,
            )
            assert item is not None
            dialog.tree_profiles.setCurrentItem(item)
            app.processEvents()

            original_jaw = dialog.ui.spnJawPeriod.value()
            dialog.ui.spnJawPeriod.setValue(original_jaw + 1)
            app.processEvents()
            assert dialog.ui.btnSave.isEnabled()
            dialog.ui.btnSave.click()
            app.processEvents()

            revised = repository.load_profile(profile.profile_uid)
            assert revised.revision == 2
            assert revised.parameters["jaw_period"] == original_jaw + 1
            preserved_policy = {
                key: revised.parameters[key] for key in CANDIDATE_POLICY_KEYS
            }
            assert preserved_policy == frozen_policy
            assert not dialog.ui.btnSave.isEnabled()
    finally:
        QMessageBox.question = original_question

    print("Workspace Indicator Profile Candidate F Revision UI result")
    print("  candidate_f_duplicate_editable=True")
    print("  jaw_revision_incremented=True")
    print("  candidate_logic_mode_preserved=True")
    print("  candidate_threshold_snapshot_preserved=True")
    print("  broker_execution_attempted=False")
    print("WORKSPACE_INDICATOR_PROFILE_CANDIDATE_F_REVISION_UI_CHECK=OK")


if __name__ == "__main__":
    main()
