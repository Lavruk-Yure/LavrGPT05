# run_workspace_indicator_profile_revision_save_ui_check.py
# RoadMap101 — безпечне створення нової revision профілю індикатора
# -*- coding: utf-8 -*-
"""Перевірка UX створення нової редакції профілю індикатора.

RoadMap101 після ручного ABC persistence acceptance уточнює семантику кнопки
збереження у ``Профілі індикаторів WSP``. Користувацький профіль, який лише
відкрили для перегляду, не повинен створювати нову revision випадковим
натисканням. Кнопка ``Зберегти як нову редакцію`` активується тільки після
реальної зміни полів, а після успішного revision-save знову вимикається.

Тест працює з тимчасовим repository, не запускає Replay, broker runtime чи
торгову логіку. Інваріанти binding/snapshot не змінюються: revision створює
лише явна зміна глобального користувацького профілю, а прив'язка до WSP
залишається окремою дією. Неочікуваний modal під час save перетворюється на
негайний assert замість зависання offscreen-тесту.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QMessageBox,
    QTreeWidgetItem,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import AlgorithmWorkspace  # noqa: E402
from core.workspace_indicator_profile import MACD_PROFILE_UID_LGE_CLASSIC  # noqa: E402
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
        display_name="RoadMap101 revision-save UI",
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
    """Негайно провалити тест, якщо save відкриває неочікуваний modal."""
    raise AssertionError(
        "Unexpected QMessageBox.question during revision-save UI check"
    )


def main() -> None:
    app = QApplication.instance() or QApplication([])
    original_question = QMessageBox.question
    QMessageBox.question = _unexpected_question
    try:
        with TemporaryDirectory() as tmp_dir:
            repository = WorkspaceIndicatorProfileRepository(Path(tmp_dir))
            repository.ensure_storage()
            profile = repository.duplicate_profile(
                MACD_PROFILE_UID_LGE_CLASSIC,
                name="Custom MACD VERY FAST",
            )
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

            save_disabled_without_changes = not dialog.ui.btnSave.isEnabled()
            initial_revision = repository.load_profile(profile.profile_uid).revision
            dialog.ui.btnSave.click()
            app.processEvents()
            revision_unchanged_after_noop_click = (
                repository.load_profile(profile.profile_uid).revision
                == initial_revision
            )

            dialog.ui.spnMacdFast.setValue(dialog.ui.spnMacdFast.value() + 1)
            app.processEvents()
            save_enabled_after_change = dialog.ui.btnSave.isEnabled()
            dialog.ui.btnSave.click()
            app.processEvents()

            revised = repository.load_profile(profile.profile_uid)
            revision_incremented_once = revised.revision == initial_revision + 1
            save_disabled_after_revision = not dialog.ui.btnSave.isEnabled()

            assert save_disabled_without_changes
            assert revision_unchanged_after_noop_click
            assert save_enabled_after_change
            assert revision_incremented_once
            assert save_disabled_after_revision

    finally:
        QMessageBox.question = original_question

    print("Workspace Indicator Profile Revision Save UI result")
    print(f"  save_disabled_without_changes={save_disabled_without_changes}")
    print(
        "  revision_unchanged_after_noop_click="
        f"{revision_unchanged_after_noop_click}"
    )
    print(f"  save_enabled_after_change={save_enabled_after_change}")
    print(f"  revision_incremented_once={revision_incremented_once}")
    print(f"  save_disabled_after_revision={save_disabled_after_revision}")
    print("WORKSPACE_INDICATOR_PROFILE_REVISION_SAVE_UI_CHECK=OK")


if __name__ == "__main__":
    main()
