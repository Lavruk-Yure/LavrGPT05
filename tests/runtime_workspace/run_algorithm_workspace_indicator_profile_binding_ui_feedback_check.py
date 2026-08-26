# run_algorithm_workspace_indicator_profile_binding_ui_feedback_check.py
# RoadMap99_04F/04G — binding UI feedback regression
# -*- coding: utf-8 -*-
"""run_algorithm_workspace_indicator_profile_binding_ui_feedback_check.py.

RoadMap99_04F/04F.1/04G — явний GUI-feedback binding профілю до WSP.

Перевірка відтворює ручний сценарій Custom MACD без запуску торгового Runtime:
створює користувацький профіль ``8/17/5``, вибирає його в редакторі профілів,
натискає ``Use for this WSP`` і перевіряє, що pending binding містить точні
UID/revision/snapshot, а кнопка та рядок поточних профілів одразу показують
успішний вибір. Далі імітується повернення в ``Параметри WSP``: діалог має
показати назву профілю й revision та явно позначити binding як зміну, що
очікує спільного ``Save``. RoadMap99_04F.1 також контролює чистий helper fake
без IDE-попереджень про методи, які нібито можуть бути static.

Тест не змінює production signal logic, не запускає broker execution і не
редагує ``lang/strings.json``. Він контролює лише UX та правильну передачу
pending indicator-profile bindings між двома Designer-діалогами. RoadMap99_04G
додатково перевіряє, що повторне відкриття автоматично ставить selection на
поточний MACD-профіль WSP, а selected-state кнопки достатньо виразний: текст
не залежить від малої галочки, і повторне застосування exact revision вимкнено.
RoadMap99_04G.1 розділяє два незалежні сценарії тесту: persisted binding для
перевірки auto-selection і fresh WSP для перевірки pending Save. Це не дає
першому сценарію випадково прибрати pending-стан у другому.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QTreeWidgetItem  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import core.algorithm_workspace_parameters_dialog as parameters_module  # noqa: E402
from core.algorithm_workspace import AlgorithmWorkspace  # noqa: E402
from core.workspace_indicator_profile import (  # noqa: E402
    MACD_PROFILE_UID_LGE_CLASSIC,
    WORKSPACE_MACD_PROFILE_BINDING_KEY,
    WorkspaceIndicatorProfileBinding,
)
from core.workspace_indicator_profile_repository import (  # noqa: E402
    WorkspaceIndicatorProfileRepository,
)
from core.workspace_indicator_profiles_dialog import (  # noqa: E402
    WorkspaceIndicatorProfilesDialog,
)


def _workspace() -> AlgorithmWorkspace:
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM000001",
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        display_name="RoadMap99_04F profile UI",
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


def _tree_profile_item(
    dialog: WorkspaceIndicatorProfilesDialog,
    profile_uid: str,
) -> QTreeWidgetItem:
    root = dialog.tree_profiles.invisibleRootItem()
    item = _find_profile_item(root, profile_uid)
    if item is None:
        raise AssertionError(f"profile item not found: {profile_uid}")
    return item


def main() -> None:
    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory() as tmp_dir:
        repository = WorkspaceIndicatorProfileRepository(Path(tmp_dir))
        repository.ensure_storage()
        duplicate = repository.duplicate_profile(
            MACD_PROFILE_UID_LGE_CLASSIC,
            name="Custom MACD FAST",
        )
        fast_profile = repository.update_profile(
            duplicate.profile_uid,
            name="Custom MACD FAST",
            parameters={
                "source": "CLOSE",
                "fast_period": 8,
                "slow_period": 17,
                "signal_period": 5,
                "oscillator_ma_type": "EXPONENTIAL",
                "signal_ma_type": "EXPONENTIAL",
                "shift": 0,
            },
        )
        workspace = _workspace()
        profile_dialog = WorkspaceIndicatorProfilesDialog(
            workspace,
            repository=repository,
        )
        profile_dialog.tree_profiles.setCurrentItem(
            _tree_profile_item(profile_dialog, fast_profile.profile_uid)
        )
        app.processEvents()
        profile_dialog.ui.btnUseForWorkspace.click()
        app.processEvents()

        pending_bindings = profile_dialog.indicator_profile_bindings()
        macd_binding = WorkspaceIndicatorProfileBinding.from_storage_dict(
            pending_bindings[WORKSPACE_MACD_PROFILE_BINDING_KEY]
        )
        selected_button_visible = (
            "Selected for this WSP" in profile_dialog.ui.btnUseForWorkspace.text()
            and "✓" not in profile_dialog.ui.btnUseForWorkspace.text()
        )
        selected_button_emphasized = (
            not profile_dialog.ui.btnUseForWorkspace.isEnabled()
        )
        selected_label_visible = (
            "Custom MACD FAST" in profile_dialog.ui.lblCurrentBindings.text()
        )
        binding_exact_revision = (
            macd_binding.profile_uid == fast_profile.profile_uid
            and macd_binding.profile_revision == fast_profile.revision
            and macd_binding.profile.parameters["fast_period"] == 8
            and macd_binding.profile.parameters["slow_period"] == 17
            and macd_binding.profile.parameters["signal_period"] == 5
        )
        assert selected_button_visible
        assert selected_button_emphasized
        assert selected_label_visible
        assert binding_exact_revision

        persisted_workspace = _workspace()
        persisted_workspace.set_indicator_profile_bindings(pending_bindings)
        reopened_dialog = WorkspaceIndicatorProfilesDialog(
            persisted_workspace,
            repository=repository,
        )
        app.processEvents()
        current_item = reopened_dialog.tree_profiles.currentItem()
        current_profile_auto_selected = bool(
            current_item is not None
            and current_item.data(0, Qt.ItemDataRole.UserRole)
            == fast_profile.profile_uid
        )
        reopened_selected_state = (
            not reopened_dialog.ui.btnUseForWorkspace.isEnabled()
            and "Selected for this WSP" in reopened_dialog.ui.btnUseForWorkspace.text()
        )
        assert current_profile_auto_selected
        assert reopened_selected_state

        class _AcceptedProfilesDialog:
            def __init__(self, *_args: object, **_kwargs: object) -> None:
                self._accepted = QDialog.DialogCode.Accepted
                self._bindings = pending_bindings

            def exec(self) -> QDialog.DialogCode:
                return self._accepted

            def indicator_profile_bindings(self) -> dict[str, dict[str, object]]:
                return self._bindings

        original_dialog = parameters_module.WorkspaceIndicatorProfilesDialog
        parameters_module.WorkspaceIndicatorProfilesDialog = _AcceptedProfilesDialog
        try:
            pending_workspace = _workspace()
            parameters_dialog = parameters_module.AlgorithmWorkspaceParametersDialog(
                pending_workspace
            )
            parameters_dialog.btn_indicator_profiles.click()
            app.processEvents()
            context = parameters_dialog.lbl_context.text()
        finally:
            parameters_module.WorkspaceIndicatorProfilesDialog = original_dialog

        parameters_context_profile_visible = "Custom MACD FAST" in context
        parameters_context_revision_visible = f"r{fast_profile.revision}" in context
        parameters_context_pending_visible = "pending Save" in context
        assert parameters_context_profile_visible
        assert parameters_context_revision_visible
        assert parameters_context_pending_visible

    print("Algorithm Workspace Indicator Profile Binding UI Feedback result")
    print(f"  selected_button_visible={selected_button_visible}")
    print(f"  selected_button_emphasized={selected_button_emphasized}")
    print(f"  current_profile_auto_selected={current_profile_auto_selected}")
    print(f"  reopened_selected_state={reopened_selected_state}")
    print(f"  selected_label_visible={selected_label_visible}")
    print(f"  binding_exact_revision={binding_exact_revision}")
    print(
        "  parameters_context_profile_visible=" f"{parameters_context_profile_visible}"
    )
    print(
        "  parameters_context_revision_visible="
        f"{parameters_context_revision_visible}"
    )
    print(
        "  parameters_context_pending_visible=" f"{parameters_context_pending_visible}"
    )
    print("  production_signal_logic_changed=False")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_INDICATOR_PROFILE_BINDING_UI_FEEDBACK_CHECK=OK")


if __name__ == "__main__":
    main()
