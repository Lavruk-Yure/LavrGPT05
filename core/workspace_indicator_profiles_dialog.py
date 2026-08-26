# workspace_indicator_profiles_dialog.py — профілі індикаторів WSP
# -*- coding: utf-8 -*-
"""workspace_indicator_profiles_dialog.py — профілі індикаторів WSP.

Редактор, revisioning і явне binding-підтвердження для одного workspace.

Модуль керує глобальними профілями MACD та Alligator, їх незмінними
вбудованими шаблонами, користувацькими редакціями та snapshot-прив'язкою
конкретного профілю до одного Algorithm Workspace. RoadMap99_04F робить
ручний GUI acceptance однозначним: незбережений профіль не можна випадково
прив'язати, а успішно вибраний профіль має видимий стан кнопки та оновлений
рядок поточних bindings. RoadMap99_04G при відкритті автоматично виділяє
поточний MACD-профіль WSP і показує стан «Вибрано для цього WSP» виразним
вимкненим станом кнопки без малопомітної галочки. Саме збереження binding у
WSP, як і раніше, відбувається лише після ``Зберегти`` у батьківському
діалозі параметрів.

Інваріанти: built-in профілі не редагуються; binding містить точний UID,
revision і resolved snapshot; зміна глобального профілю після binding не
переписує вже зафіксований snapshot; торгову логіку Runtime модуль не змінює.
"""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QMessageBox,
    QTreeWidgetItem,
    QWidget,
)

from core.algorithm_workspace import AlgorithmWorkspace
from core.lang_manager import LangManager
from core.workspace_indicator_profile import (
    ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F,
    ALLIGATOR_PROFILE_UID_LGE_CLASSIC,
    MACD_PROFILE_UID_LGE_CLASSIC,
    MACD_PROFILE_UID_LGE_DEFAULT,
    WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY,
    WORKSPACE_INDICATOR_ALLIGATOR,
    WORKSPACE_INDICATOR_MACD,
    WORKSPACE_INDICATOR_MA_EXPONENTIAL,
    WORKSPACE_INDICATOR_MA_SIMPLE,
    WORKSPACE_INDICATOR_MA_SMOOTHED,
    WORKSPACE_INDICATOR_MA_TYPES,
    WORKSPACE_INDICATOR_PROFILE_BINDING_KEYS,
    WORKSPACE_INDICATOR_SOURCE_CLOSE,
    WORKSPACE_INDICATOR_SOURCE_HIGH,
    WORKSPACE_INDICATOR_SOURCE_LOW,
    WORKSPACE_INDICATOR_SOURCE_MEDIAN,
    WORKSPACE_INDICATOR_SOURCE_OPEN,
    WORKSPACE_INDICATOR_SOURCE_TYPICAL,
    WORKSPACE_INDICATOR_SOURCE_WEIGHTED,
    WORKSPACE_INDICATOR_SOURCES,
    WORKSPACE_MACD_PROFILE_BINDING_KEY,
    WorkspaceIndicatorProfile,
    WorkspaceIndicatorProfileBinding,
    WorkspaceIndicatorProfileError,
    normalize_workspace_indicator_profile_bindings,
)
from core.workspace_indicator_profile_repository import (
    WorkspaceIndicatorProfileLifecycle,
    WorkspaceIndicatorProfileLifecycleService,
    WorkspaceIndicatorProfileRepository,
    WorkspaceIndicatorProfileRepositoryError,
)
from ui.ui_workspace_indicator_profiles_dialog import (
    Ui_WorkspaceIndicatorProfilesDialog,
)


class _FallbackTranslator:
    @staticmethod
    def tr(_key: str, fallback: str) -> str:
        return fallback


_FALLBACK_TRANSLATOR = _FallbackTranslator()

_PROFILE_NAME_KEYS = {
    MACD_PROFILE_UID_LGE_CLASSIC: (
        "WorkspaceIndicatorProfile.macdLgeClassic",
        "LGE Classic EMA 12/26/9 Close",
    ),
    MACD_PROFILE_UID_LGE_DEFAULT: (
        "WorkspaceIndicatorProfile.macdLgeDefault",
        "LGE Default EMA 8/17/5 Close",
    ),
    "00000000-0000-5000-8000-000000000002": (
        "WorkspaceIndicatorProfile.macdTwsDefault",
        "TWS Default MACD",
    ),
    "00000000-0000-5000-8000-000000000003": (
        "WorkspaceIndicatorProfile.macdCtraderReference",
        "cTrader Default MACD Reference",
    ),
    ALLIGATOR_PROFILE_UID_LGE_CLASSIC: (
        "WorkspaceIndicatorProfile.alligatorLgeClassic",
        "LGE Classic Smoothed",
    ),
    ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F: (
        "WorkspaceIndicatorProfile.alligatorLgeCandidateF",
        "LGE Candidate F Smoothed",
    ),
    "00000000-0000-5000-8000-000000000012": (
        "WorkspaceIndicatorProfile.alligatorCtraderDefault",
        "cTrader Default Simple Close",
    ),
    "00000000-0000-5000-8000-000000000013": (
        "WorkspaceIndicatorProfile.alligatorTwsReference",
        "TWS Default Alligator Reference",
    ),
}


class WorkspaceIndicatorProfilesDialog(QDialog):
    """Керувати глобальними профілями та pending bindings одного WSP."""

    def __init__(
        self,
        workspace: AlgorithmWorkspace,
        lang_mgr: LangManager | None = None,
        parent: QWidget | None = None,
        *,
        repository: WorkspaceIndicatorProfileRepository | None = None,
        lifecycle_service: WorkspaceIndicatorProfileLifecycleService | None = None,
        initial_bindings: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(parent)
        self._workspace = workspace
        self._lang_mgr = lang_mgr
        self._repository = repository or WorkspaceIndicatorProfileRepository()
        self._lifecycle_service = (
            lifecycle_service
            or WorkspaceIndicatorProfileLifecycleService(self._repository)
        )
        self._pending_bindings = normalize_workspace_indicator_profile_bindings(
            initial_bindings
            if initial_bindings is not None
            else workspace.indicator_profile_bindings
        )
        self._profile_items: dict[str, QTreeWidgetItem] = {}
        self._selected_profile: WorkspaceIndicatorProfile | None = None
        self._loaded_editor_state: tuple[object, ...] | None = None
        self._selection_guard = False
        self._allow_close = False

        self.ui = Ui_WorkspaceIndicatorProfilesDialog()
        self.ui.setupUi(self)
        self.tree_profiles = self.ui.treeProfiles
        self.edt_name = self.ui.edtName
        self.stack_indicator = self.ui.stackIndicator

        self._configure_choices()
        self.tree_profiles.currentItemChanged.connect(
            self._on_profile_selection_changed
        )
        self.ui.btnNew.clicked.connect(self._create_profile)
        self.ui.btnDuplicate.clicked.connect(self._duplicate_profile)
        self.ui.btnArchive.clicked.connect(self._archive_profile)
        self.ui.btnDelete.clicked.connect(self._delete_profile)
        self.ui.btnUseForWorkspace.clicked.connect(self._use_for_workspace)
        self.ui.btnSave.clicked.connect(self._save_profile)
        self._connect_editor_dirty_tracking()
        self.ui.btnClose.clicked.connect(self._request_close)

        self.apply_translation()
        self._rebuild_tree(self._current_macd_profile_uid())

    def indicator_profile_bindings(self) -> dict[str, dict[str, object]]:
        """Повернути bindings, які слід зберегти разом із параметрами WSP."""
        return normalize_workspace_indicator_profile_bindings(
            self._pending_bindings
        )

    def apply_translation(self) -> None:
        """Перекласти статичні тексти та combo labels без зміни data."""
        self.setWindowTitle(
            self._tr(
                "WorkspaceIndicatorProfilesDialog.windowTitle",
                "Indicator profiles",
            )
        )
        self.ui.lblWorkspace.setText(
            self._tr(
                "WorkspaceIndicatorProfilesDialog.workspace",
                "Workspace: {name}",
            ).format(name=self._workspace.display_name)
        )
        header = self.tree_profiles.headerItem()
        header.setText(
            0,
            self._tr(
                "WorkspaceIndicatorProfilesDialog.columnProfile",
                "Profile",
            ),
        )
        header.setText(
            1,
            self._tr(
                "WorkspaceIndicatorProfilesDialog.columnRevision",
                "Revision",
            ),
        )
        header.setText(
            2,
            self._tr(
                "WorkspaceIndicatorProfilesDialog.columnStatus",
                "Status",
            ),
        )
        self.ui.btnNew.setText(
            self._tr("WorkspaceIndicatorProfilesDialog.btnNew", "New")
        )
        self.ui.btnDuplicate.setText(
            self._tr(
                "WorkspaceIndicatorProfilesDialog.btnDuplicate",
                "Duplicate",
            )
        )
        self.ui.btnArchive.setText(
            self._tr("WorkspaceIndicatorProfilesDialog.btnArchive", "Archive")
        )
        self.ui.btnDelete.setText(
            self._tr("WorkspaceIndicatorProfilesDialog.btnDelete", "Delete")
        )
        self.ui.grpProfile.setTitle(
            self._tr(
                "WorkspaceIndicatorProfilesDialog.grpProfile",
                "Profile",
            )
        )
        labels = (
            (self.ui.lblNameCaption, "lblName", "Name:"),
            (self.ui.lblIndicatorCaption, "lblIndicator", "Indicator:"),
            (
                self.ui.lblSourceReferenceCaption,
                "lblSourceReference",
                "Source reference:",
            ),
            (self.ui.lblRevisionCaption, "lblRevision", "Revision:"),
            (self.ui.lblProfileStatusCaption, "lblStatus", "Status:"),
            (self.ui.lblMacdSource, "lblSource", "Source:"),
            (self.ui.lblMacdFast, "lblFastPeriod", "Fast period:"),
            (self.ui.lblMacdSlow, "lblSlowPeriod", "Slow period:"),
            (self.ui.lblMacdSignal, "lblSignalPeriod", "Signal period:"),
            (
                self.ui.lblMacdOscillatorMa,
                "lblOscillatorMa",
                "Oscillator MA type:",
            ),
            (self.ui.lblMacdSignalMa, "lblSignalMa", "Signal MA type:"),
            (self.ui.lblMacdShift, "lblShift", "Shift:"),
            (self.ui.lblAlligatorSource, "lblSource", "Source:"),
            (self.ui.lblJawPeriod, "lblJawPeriod", "Jaw period:"),
            (self.ui.lblJawShift, "lblJawShift", "Jaw shift:"),
            (self.ui.lblTeethPeriod, "lblTeethPeriod", "Teeth period:"),
            (self.ui.lblTeethShift, "lblTeethShift", "Teeth shift:"),
            (self.ui.lblLipsPeriod, "lblLipsPeriod", "Lips period:"),
            (self.ui.lblLipsShift, "lblLipsShift", "Lips shift:"),
            (self.ui.lblAlligatorMa, "lblMaType", "MA type:"),
        )
        for widget, suffix, fallback in labels:
            widget.setText(
                self._tr(
                    f"WorkspaceIndicatorProfilesDialog.{suffix}",
                    fallback,
                )
            )
        self.ui.lblNoSelection.setText(
            self._tr(
                "WorkspaceIndicatorProfilesDialog.noSelection",
                "Select an indicator profile on the left.",
            )
        )
        self.ui.lblNote.setText(
            self._tr(
                "WorkspaceIndicatorProfilesDialog.note",
                "Built-in profiles are immutable templates. Duplicate a "
                "template to edit it. A WSP stores the selected revision and "
                "a resolved snapshot for deterministic Replay.",
            )
        )
        self.ui.btnUseForWorkspace.setText(
            self._tr(
                "WorkspaceIndicatorProfilesDialog.btnUseForWorkspace",
                "Use for this WSP",
            )
        )
        self.ui.btnSave.setText(
            self._tr(
                "WorkspaceIndicatorProfilesDialog.btnSave",
                "Save as new revision",
            )
        )
        self.ui.btnClose.setText(
            self._tr("WorkspaceIndicatorProfilesDialog.btnClose", "Close")
        )
        self._translate_choices()
        self._refresh_bindings_label()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Не втрачати незбережені правки профілю без підтвердження."""
        if self._allow_close or not self._editor_dirty():
            event.accept()
            return
        if self._confirm_discard_editor_changes():
            self._allow_close = True
            event.accept()
            return
        event.ignore()

    def reject(self) -> None:
        self._request_close()

    def _configure_choices(self) -> None:
        combos = (
            self.ui.cmbMacdSource,
            self.ui.cmbAlligatorSource,
        )
        for combo in combos:
            combo.clear()
            for value in WORKSPACE_INDICATOR_SOURCES:
                combo.addItem(value, value)
        ma_combos = (
            self.ui.cmbMacdOscillatorMa,
            self.ui.cmbMacdSignalMa,
            self.ui.cmbAlligatorMa,
        )
        for combo in ma_combos:
            combo.clear()
            for value in WORKSPACE_INDICATOR_MA_TYPES:
                combo.addItem(value, value)

    def _translate_choices(self) -> None:
        source_labels = {
            WORKSPACE_INDICATOR_SOURCE_CLOSE: ("sourceClose", "Close"),
            WORKSPACE_INDICATOR_SOURCE_OPEN: ("sourceOpen", "Open"),
            WORKSPACE_INDICATOR_SOURCE_HIGH: ("sourceHigh", "High"),
            WORKSPACE_INDICATOR_SOURCE_LOW: ("sourceLow", "Low"),
            WORKSPACE_INDICATOR_SOURCE_MEDIAN: ("sourceMedian", "Median price"),
            WORKSPACE_INDICATOR_SOURCE_TYPICAL: ("sourceTypical", "Typical price"),
            WORKSPACE_INDICATOR_SOURCE_WEIGHTED: (
                "sourceWeighted",
                "Weighted close",
            ),
        }
        for combo in (self.ui.cmbMacdSource, self.ui.cmbAlligatorSource):
            for index in range(combo.count()):
                value = str(combo.itemData(index))
                suffix, fallback = source_labels[value]
                combo.setItemText(
                    index,
                    self._tr(
                        f"WorkspaceIndicatorProfilesDialog.{suffix}",
                        fallback,
                    ),
                )
        ma_labels = {
            WORKSPACE_INDICATOR_MA_SIMPLE: ("maSimple", "Simple"),
            WORKSPACE_INDICATOR_MA_EXPONENTIAL: ("maExponential", "Exponential"),
            WORKSPACE_INDICATOR_MA_SMOOTHED: ("maSmoothed", "Smoothed"),
        }
        for combo in (
            self.ui.cmbMacdOscillatorMa,
            self.ui.cmbMacdSignalMa,
            self.ui.cmbAlligatorMa,
        ):
            for index in range(combo.count()):
                value = str(combo.itemData(index))
                suffix, fallback = ma_labels[value]
                combo.setItemText(
                    index,
                    self._tr(
                        f"WorkspaceIndicatorProfilesDialog.{suffix}",
                        fallback,
                    ),
                )

    def _current_macd_profile_uid(self) -> str:
        """Повернути UID поточного pending MACD binding для початкового selection."""
        bindings = normalize_workspace_indicator_profile_bindings(
            self._pending_bindings
        )
        binding = WorkspaceIndicatorProfileBinding.from_storage_dict(
            bindings[WORKSPACE_MACD_PROFILE_BINDING_KEY]
        )
        return binding.profile_uid

    def _rebuild_tree(self, selected_uid: str | None = None) -> None:
        self.tree_profiles.clear()
        self._profile_items.clear()
        groups = {
            WORKSPACE_INDICATOR_MACD: QTreeWidgetItem(["MACD", "", ""]),
            WORKSPACE_INDICATOR_ALLIGATOR: QTreeWidgetItem(
                ["Alligator", "", ""]
            ),
        }
        for code, item in groups.items():
            item.setData(0, Qt.ItemDataRole.UserRole, code)
            self.tree_profiles.addTopLevelItem(item)
            item.setExpanded(True)
        for profile in self._repository.list_profiles(include_archived=True):
            status = self._profile_status(profile)
            item = QTreeWidgetItem(
                [
                    self._profile_display_name(profile),
                    str(profile.revision),
                    status,
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, profile.profile_uid)
            groups[profile.indicator_code].addChild(item)
            self._profile_items[profile.profile_uid] = item
        self.tree_profiles.resizeColumnToContents(0)
        if selected_uid and selected_uid in self._profile_items:
            self.tree_profiles.setCurrentItem(self._profile_items[selected_uid])
        elif self._profile_items:
            first_uid = next(iter(self._profile_items))
            self.tree_profiles.setCurrentItem(self._profile_items[first_uid])
        else:
            self._show_no_selection()

    def _on_profile_selection_changed(
        self,
        current: QTreeWidgetItem | None,
        previous: QTreeWidgetItem | None,
    ) -> None:
        if self._selection_guard:
            return
        if self._editor_dirty() and not self._confirm_discard_editor_changes():
            self._selection_guard = True
            try:
                self.tree_profiles.setCurrentItem(previous)
            finally:
                self._selection_guard = False
            return
        if current is None:
            self._show_no_selection()
            return
        profile_uid = current.data(0, Qt.ItemDataRole.UserRole)
        if (
            not isinstance(profile_uid, str)
            or profile_uid in WORKSPACE_INDICATOR_PROFILE_BINDING_KEYS
        ):
            self._show_no_selection()
            return
        try:
            profile = self._repository.load_profile(profile_uid)
        except WorkspaceIndicatorProfileRepositoryError as exc:
            QMessageBox.warning(self, "LGE", str(exc))
            self._show_no_selection()
            return
        self._load_profile(profile)

    def _load_profile(self, profile: WorkspaceIndicatorProfile) -> None:
        self._selected_profile = profile
        self.edt_name.setText(self._profile_display_name(profile))
        self.edt_name.setReadOnly(profile.built_in)
        self.ui.lblIndicatorValue.setText(profile.indicator_code)
        self.ui.lblSourceReferenceValue.setText(profile.source_reference)
        self.ui.lblRevisionValue.setText(str(profile.revision))
        self.ui.lblProfileStatusValue.setText(self._profile_status(profile))
        self.ui.btnSave.setEnabled(False)
        self.ui.btnArchive.setEnabled(not profile.built_in and not profile.archived)
        try:
            lifecycle = self._profile_lifecycle(profile.profile_uid)
        except WorkspaceIndicatorProfileRepositoryError as exc:
            self.ui.btnDelete.setEnabled(False)
            self.ui.btnDelete.setToolTip(str(exc))
        else:
            self.ui.btnDelete.setEnabled(lifecycle.can_delete)
            self._apply_delete_tooltip(lifecycle)
        self.ui.btnDuplicate.setEnabled(True)
        self.ui.btnUseForWorkspace.setEnabled(profile.usable)
        parameters = profile.parameters
        if profile.indicator_code == WORKSPACE_INDICATOR_MACD:
            self.stack_indicator.setCurrentWidget(self.ui.pageMacd)
            self._set_combo_data(
                self.ui.cmbMacdSource,
                parameters.get("source", WORKSPACE_INDICATOR_SOURCE_CLOSE),
            )
            self.ui.spnMacdFast.setValue(
                self._profile_integer(parameters, "fast_period", 12)
            )
            self.ui.spnMacdSlow.setValue(
                self._profile_integer(parameters, "slow_period", 26)
            )
            self.ui.spnMacdSignal.setValue(
                self._profile_integer(parameters, "signal_period", 9)
            )
            self._set_combo_data(
                self.ui.cmbMacdOscillatorMa,
                parameters.get(
                    "oscillator_ma_type",
                    WORKSPACE_INDICATOR_MA_EXPONENTIAL,
                ),
            )
            self._set_combo_data(
                self.ui.cmbMacdSignalMa,
                parameters.get("signal_ma_type", WORKSPACE_INDICATOR_MA_EXPONENTIAL),
            )
            self.ui.spnMacdShift.setValue(
                self._profile_integer(parameters, "shift", 0)
            )
        else:
            self.stack_indicator.setCurrentWidget(self.ui.pageAlligator)
            self._set_combo_data(
                self.ui.cmbAlligatorSource,
                parameters.get("source", WORKSPACE_INDICATOR_SOURCE_MEDIAN),
            )
            self.ui.spnJawPeriod.setValue(
                self._profile_integer(parameters, "jaw_period", 13)
            )
            self.ui.spnJawShift.setValue(
                self._profile_integer(parameters, "jaw_shift", 8)
            )
            self.ui.spnTeethPeriod.setValue(
                self._profile_integer(parameters, "teeth_period", 8)
            )
            self.ui.spnTeethShift.setValue(
                self._profile_integer(parameters, "teeth_shift", 5)
            )
            self.ui.spnLipsPeriod.setValue(
                self._profile_integer(parameters, "lips_period", 5)
            )
            self.ui.spnLipsShift.setValue(
                self._profile_integer(parameters, "lips_shift", 3)
            )
            self._set_combo_data(
                self.ui.cmbAlligatorMa,
                parameters.get("ma_type", WORKSPACE_INDICATOR_MA_SMOOTHED),
            )
        self._set_editor_enabled(not profile.built_in and not profile.archived)
        self._loaded_editor_state = self._editor_state()
        self._refresh_save_state()
        self._refresh_use_for_workspace_state()

    def _show_no_selection(self) -> None:
        self._selected_profile = None
        self.edt_name.clear()
        self.ui.lblIndicatorValue.setText("—")
        self.ui.lblSourceReferenceValue.setText("—")
        self.ui.lblRevisionValue.setText("—")
        self.ui.lblProfileStatusValue.setText("—")
        self.stack_indicator.setCurrentWidget(self.ui.pageNoSelection)
        self._set_editor_enabled(False)
        self.ui.btnDuplicate.setEnabled(False)
        self.ui.btnArchive.setEnabled(False)
        self.ui.btnDelete.setEnabled(False)
        self.ui.btnDelete.setToolTip("")
        self.ui.btnSave.setEnabled(False)
        self.ui.btnUseForWorkspace.setEnabled(False)
        self._loaded_editor_state = None
        self._refresh_use_for_workspace_state()

    def _create_profile(self) -> None:
        indicator_code = self._selected_indicator_code()
        source_uid = (
            MACD_PROFILE_UID_LGE_CLASSIC
            if indicator_code == WORKSPACE_INDICATOR_MACD
            else ALLIGATOR_PROFILE_UID_LGE_CLASSIC
        )
        fallback = (
            "Custom MACD"
            if indicator_code == WORKSPACE_INDICATOR_MACD
            else "Custom Alligator"
        )
        name = self._unique_user_name(fallback)
        try:
            profile = self._repository.duplicate_profile(source_uid, name=name)
        except WorkspaceIndicatorProfileRepositoryError as exc:
            QMessageBox.warning(self, "LGE", str(exc))
            return
        self._rebuild_tree(profile.profile_uid)

    def _duplicate_profile(self) -> None:
        profile = self._selected_profile
        if profile is None:
            return
        name = self._unique_user_name(
            self._tr(
                "WorkspaceIndicatorProfilesDialog.copyName",
                "{name} copy",
            ).format(name=self._profile_display_name(profile))
        )
        try:
            duplicate = self._repository.duplicate_profile(
                profile.profile_uid,
                name=name,
            )
        except WorkspaceIndicatorProfileRepositoryError as exc:
            QMessageBox.warning(self, "LGE", str(exc))
            return
        self._rebuild_tree(duplicate.profile_uid)

    def _save_profile(self) -> None:
        profile = self._selected_profile
        if profile is None or profile.built_in or profile.archived:
            return
        try:
            updated = self._repository.update_profile(
                profile.profile_uid,
                name=self.edt_name.text(),
                parameters=self._collect_parameters(profile.indicator_code),
            )
        except (
            WorkspaceIndicatorProfileError,
            WorkspaceIndicatorProfileRepositoryError,
        ) as exc:
            QMessageBox.warning(self, "LGE", str(exc))
            return
        # Після успішного збереження поточний стан редактора вже відповідає
        # збереженій revision. Внутрішня перебудова дерева не повинна
        # трактувати цей стан як незбережені зміни та відкривати confirmation.
        self._loaded_editor_state = self._editor_state()
        self._rebuild_tree(updated.profile_uid)

    def _archive_profile(self) -> None:
        profile = self._selected_profile
        if profile is None or profile.built_in or profile.archived:
            return
        answer = QMessageBox.question(
            self,
            self._tr(
                "WorkspaceIndicatorProfilesDialog.archiveTitle",
                "Archive profile",
            ),
            self._tr(
                "WorkspaceIndicatorProfilesDialog.archiveQuestion",
                "Archive profile '{name}'? Existing WSP snapshots remain valid.",
            ).format(name=profile.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            archived = self._repository.archive_profile(profile.profile_uid)
        except WorkspaceIndicatorProfileRepositoryError as exc:
            QMessageBox.warning(self, "LGE", str(exc))
            return
        self._rebuild_tree(archived.profile_uid)

    def _delete_profile(self) -> None:
        profile = self._selected_profile
        if profile is None or profile.built_in:
            return
        try:
            lifecycle = self._profile_lifecycle(profile.profile_uid)
        except WorkspaceIndicatorProfileRepositoryError as exc:
            QMessageBox.warning(self, "LGE", str(exc))
            return
        if not lifecycle.can_delete:
            QMessageBox.warning(
                self,
                self._tr(
                    "WorkspaceIndicatorProfilesDialog.deleteBlockedTitle",
                    "Profile cannot be deleted",
                ),
                self._delete_blocked_message(lifecycle),
            )
            return
        answer = QMessageBox.question(
            self,
            self._tr(
                "WorkspaceIndicatorProfilesDialog.deleteTitle",
                "Delete profile",
            ),
            self._tr(
                "WorkspaceIndicatorProfilesDialog.deleteQuestion",
                "Delete unused profile '{name}' permanently?",
            ).format(name=profile.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        next_uid = self._neighbor_profile_uid(profile.profile_uid)
        try:
            self._lifecycle_service.delete_unused_profile(
                profile.profile_uid,
                pending_workspace=self._workspace,
                pending_bindings=self._pending_bindings,
            )
        except WorkspaceIndicatorProfileRepositoryError as exc:
            QMessageBox.warning(self, "LGE", str(exc))
            return
        self._rebuild_tree(next_uid)

    def _use_for_workspace(self) -> None:
        profile = self._selected_profile
        if profile is None or not profile.usable:
            return
        if self._editor_dirty():
            QMessageBox.warning(
                self,
                self._tr(
                    "WorkspaceIndicatorProfilesDialog.saveBeforeUseTitle",
                    "Save profile first",
                ),
                self._tr(
                    "WorkspaceIndicatorProfilesDialog.saveBeforeUseMessage",
                    "Save the edited profile before selecting it for this WSP.",
                ),
            )
            return
        binding = WorkspaceIndicatorProfileBinding.from_profile(profile)
        self._pending_bindings[binding.indicator_code] = binding.to_storage_dict()
        self._refresh_bindings_label()
        self._load_profile(profile)

    def _refresh_bindings_label(self) -> None:
        bindings = normalize_workspace_indicator_profile_bindings(
            self._pending_bindings
        )
        macd = WorkspaceIndicatorProfileBinding.from_storage_dict(
            bindings[WORKSPACE_MACD_PROFILE_BINDING_KEY]
        ).profile
        alligator = WorkspaceIndicatorProfileBinding.from_storage_dict(
            bindings[WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY]
        ).profile
        self.ui.lblCurrentBindings.setText(
            self._tr(
                "WorkspaceIndicatorProfilesDialog.currentBindings",
                "Current WSP profiles: MACD — {macd}; Alligator — {alligator}",
            ).format(
                macd=self._profile_display_name(macd),
                alligator=self._profile_display_name(alligator),
            )
        )
        self._refresh_use_for_workspace_state()

    def _refresh_use_for_workspace_state(self) -> None:
        """Показати, чи вибрана редакція вже є pending binding цього WSP."""
        profile = self._selected_profile
        if profile is None or not profile.usable:
            self.ui.btnUseForWorkspace.setText(
                self._tr(
                    "WorkspaceIndicatorProfilesDialog.btnUseForWorkspace",
                    "Use for this WSP",
                )
            )
            self.ui.btnUseForWorkspace.setEnabled(False)
            self.ui.btnUseForWorkspace.setToolTip("")
            return
        bindings = normalize_workspace_indicator_profile_bindings(
            self._pending_bindings
        )
        binding = WorkspaceIndicatorProfileBinding.from_storage_dict(
            bindings[profile.indicator_code]
        )
        selected = (
            binding.profile_uid == profile.profile_uid
            and binding.profile_revision == profile.revision
        )
        if selected:
            self.ui.btnUseForWorkspace.setText(
                self._tr(
                    "WorkspaceIndicatorProfilesDialog.btnSelectedForWorkspace",
                    "Selected for this WSP",
                )
            )
            self.ui.btnUseForWorkspace.setEnabled(False)
            self.ui.btnUseForWorkspace.setToolTip(
                self._tr(
                    "WorkspaceIndicatorProfilesDialog.selectedForWorkspaceTooltip",
                    "Close this window and click Save in WSP Parameters "
                    "to persist this binding.",
                )
            )
            return
        self.ui.btnUseForWorkspace.setText(
            self._tr(
                "WorkspaceIndicatorProfilesDialog.btnUseForWorkspace",
                "Use for this WSP",
            )
        )
        self.ui.btnUseForWorkspace.setEnabled(profile.usable)
        self.ui.btnUseForWorkspace.setToolTip(
            self._tr(
                "WorkspaceIndicatorProfilesDialog.btnUseForWorkspaceTooltip",
                "Select this exact profile revision for the current WSP.",
            )
        )

    def _profile_lifecycle(
        self,
        profile_uid: str,
    ) -> WorkspaceIndicatorProfileLifecycle:
        return self._lifecycle_service.inspect(
            profile_uid,
            pending_workspace=self._workspace,
            pending_bindings=self._pending_bindings,
        )

    def _apply_delete_tooltip(
        self,
        lifecycle: WorkspaceIndicatorProfileLifecycle,
    ) -> None:
        if lifecycle.profile.built_in:
            text = self._tr(
                "WorkspaceIndicatorProfilesDialog.deleteBuiltInTooltip",
                "Built-in templates cannot be deleted.",
            )
        elif lifecycle.in_use:
            text = self._tr(
                "WorkspaceIndicatorProfilesDialog.deleteInUseTooltip",
                "Used by {count} WSP binding(s); archive instead.",
            ).format(count=len(lifecycle.usages))
        else:
            text = self._tr(
                "WorkspaceIndicatorProfilesDialog.deleteUnusedTooltip",
                "Delete this unused user profile permanently.",
            )
        self.ui.btnDelete.setToolTip(text)

    def _delete_blocked_message(
        self,
        lifecycle: WorkspaceIndicatorProfileLifecycle,
    ) -> str:
        if lifecycle.profile.built_in:
            return self._tr(
                "WorkspaceIndicatorProfilesDialog.deleteBuiltInMessage",
                "Built-in templates cannot be deleted.",
            )
        names = ", ".join(
            sorted({usage.workspace_name for usage in lifecycle.usages})
        )
        return self._tr(
            "WorkspaceIndicatorProfilesDialog.deleteInUseMessage",
            "Profile is used by {count} WSP binding(s): {names}. "
            "It can only be archived.",
        ).format(count=len(lifecycle.usages), names=names)

    def _neighbor_profile_uid(self, profile_uid: str) -> str | None:
        item = self._profile_items.get(profile_uid)
        if item is None:
            return None
        parent = item.parent()
        if parent is None:
            return None
        index = parent.indexOfChild(item)
        sibling = parent.child(index + 1)
        if sibling is None and index > 0:
            sibling = parent.child(index - 1)
        if sibling is None:
            return None
        value = sibling.data(0, Qt.ItemDataRole.UserRole)
        return value if isinstance(value, str) else None

    def _collect_parameters(self, indicator_code: str) -> dict[str, object]:
        if indicator_code == WORKSPACE_INDICATOR_MACD:
            return {
                "source": self.ui.cmbMacdSource.currentData(),
                "fast_period": self.ui.spnMacdFast.value(),
                "slow_period": self.ui.spnMacdSlow.value(),
                "signal_period": self.ui.spnMacdSignal.value(),
                "oscillator_ma_type": self.ui.cmbMacdOscillatorMa.currentData(),
                "signal_ma_type": self.ui.cmbMacdSignalMa.currentData(),
                "shift": self.ui.spnMacdShift.value(),
            }
        preserved = {}
        profile = self._selected_profile
        if (
            profile is not None
            and profile.indicator_code == WORKSPACE_INDICATOR_ALLIGATOR
        ):
            preserved = {
                key: value
                for key, value in profile.parameters.items()
                if key
                not in {
                    "source",
                    "jaw_period",
                    "jaw_shift",
                    "teeth_period",
                    "teeth_shift",
                    "lips_period",
                    "lips_shift",
                    "ma_type",
                }
            }
        preserved.update(
            {
                "source": self.ui.cmbAlligatorSource.currentData(),
                "jaw_period": self.ui.spnJawPeriod.value(),
                "jaw_shift": self.ui.spnJawShift.value(),
                "teeth_period": self.ui.spnTeethPeriod.value(),
                "teeth_shift": self.ui.spnTeethShift.value(),
                "lips_period": self.ui.spnLipsPeriod.value(),
                "lips_shift": self.ui.spnLipsShift.value(),
                "ma_type": self.ui.cmbAlligatorMa.currentData(),
            }
        )
        return preserved

    def _selected_indicator_code(self) -> str:
        profile = self._selected_profile
        if profile is not None:
            return profile.indicator_code
        current = self.tree_profiles.currentItem()
        if current is not None:
            code = current.data(0, Qt.ItemDataRole.UserRole)
            if code in (WORKSPACE_INDICATOR_MACD, WORKSPACE_INDICATOR_ALLIGATOR):
                return str(code)
        return WORKSPACE_INDICATOR_MACD

    def _set_editor_enabled(self, enabled: bool) -> None:
        self.edt_name.setEnabled(enabled or self._selected_profile is not None)
        for widget in (
            self.ui.cmbMacdSource,
            self.ui.spnMacdFast,
            self.ui.spnMacdSlow,
            self.ui.spnMacdSignal,
            self.ui.cmbMacdOscillatorMa,
            self.ui.cmbMacdSignalMa,
            self.ui.spnMacdShift,
            self.ui.cmbAlligatorSource,
            self.ui.spnJawPeriod,
            self.ui.spnJawShift,
            self.ui.spnTeethPeriod,
            self.ui.spnTeethShift,
            self.ui.spnLipsPeriod,
            self.ui.spnLipsShift,
            self.ui.cmbAlligatorMa,
        ):
            widget.setEnabled(enabled)

    def _connect_editor_dirty_tracking(self) -> None:
        """Оновлювати доступність revision-save лише після реальної зміни."""
        widgets_and_signals = (
            (self.edt_name, "textChanged"),
            (self.ui.cmbMacdSource, "currentIndexChanged"),
            (self.ui.spnMacdFast, "valueChanged"),
            (self.ui.spnMacdSlow, "valueChanged"),
            (self.ui.spnMacdSignal, "valueChanged"),
            (self.ui.cmbMacdOscillatorMa, "currentIndexChanged"),
            (self.ui.cmbMacdSignalMa, "currentIndexChanged"),
            (self.ui.spnMacdShift, "valueChanged"),
            (self.ui.cmbAlligatorSource, "currentIndexChanged"),
            (self.ui.spnJawPeriod, "valueChanged"),
            (self.ui.spnJawShift, "valueChanged"),
            (self.ui.spnTeethPeriod, "valueChanged"),
            (self.ui.spnTeethShift, "valueChanged"),
            (self.ui.spnLipsPeriod, "valueChanged"),
            (self.ui.spnLipsShift, "valueChanged"),
            (self.ui.cmbAlligatorMa, "currentIndexChanged"),
        )
        for widget, signal_name in widgets_and_signals:
            signal = getattr(widget, signal_name)
            signal.connect(lambda *_args: self._refresh_save_state())

    def _refresh_save_state(self) -> None:
        """Дозволити нову revision тільки для зміненого user-профілю."""
        profile = self._selected_profile
        self.ui.btnSave.setEnabled(
            bool(
                profile is not None
                and not profile.built_in
                and not profile.archived
                and self._editor_dirty()
            )
        )

    def _editor_state(self) -> tuple[object, ...] | None:
        profile = self._selected_profile
        if profile is None or profile.built_in or profile.archived:
            return None
        parameters = self._collect_parameters(profile.indicator_code)
        return (
            self.edt_name.text().strip(),
            tuple(sorted(parameters.items())),
        )

    def _editor_dirty(self) -> bool:
        current = self._editor_state()
        return current is not None and current != self._loaded_editor_state

    def _confirm_discard_editor_changes(self) -> bool:
        answer = QMessageBox.question(
            self,
            self._tr(
                "WorkspaceIndicatorProfilesDialog.unsavedTitle",
                "Unsaved profile changes",
            ),
            self._tr(
                "WorkspaceIndicatorProfilesDialog.unsavedQuestion",
                "Discard unsaved profile changes?",
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _request_close(self) -> None:
        if self._editor_dirty() and not self._confirm_discard_editor_changes():
            return
        self._allow_close = True
        self.accept()

    def _profile_display_name(self, profile: WorkspaceIndicatorProfile) -> str:
        if not profile.built_in:
            return profile.name
        key_fallback = _PROFILE_NAME_KEYS.get(profile.profile_uid)
        if key_fallback is None:
            return profile.name
        key, fallback = key_fallback
        return self._tr(key, fallback)

    def _profile_status(self, profile: WorkspaceIndicatorProfile) -> str:
        if profile.archived:
            return self._tr(
                "WorkspaceIndicatorProfilesDialog.statusArchived",
                "Archived",
            )
        if not profile.complete:
            return self._tr(
                "WorkspaceIndicatorProfilesDialog.statusReferenceOnly",
                "Reference only — incomplete",
            )
        if profile.built_in:
            return self._tr(
                "WorkspaceIndicatorProfilesDialog.statusBuiltIn",
                "Built-in template",
            )
        return self._tr(
            "WorkspaceIndicatorProfilesDialog.statusUser",
            "User profile",
        )

    def _unique_user_name(self, base: str) -> str:
        names = {
            profile.name.casefold()
            for profile in self._repository.list_profiles(include_archived=True)
            if not profile.built_in
        }
        candidate = base.strip() or "Custom profile"
        if candidate.casefold() not in names:
            return candidate
        index = 2
        while f"{candidate} {index}".casefold() in names:
            index += 1
        return f"{candidate} {index}"

    @staticmethod
    def _profile_integer(
        parameters: Mapping[str, object],
        key: str,
        default: int,
    ) -> int:
        value = parameters.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int):
            raise WorkspaceIndicatorProfileError(
                f"profile parameter {key} must be integer"
            )
        return value

    @staticmethod
    def _set_combo_data(
        combo: QComboBox,
        value: object,
    ) -> None:
        index = combo.findData(value)
        if index < 0:
            index = 0
        combo.setCurrentIndex(index)

    def _translator(self) -> LangManager | _FallbackTranslator:
        return self._lang_mgr or _FALLBACK_TRANSLATOR

    def _tr(self, key: str, fallback: str) -> str:
        return self._translator().tr(key, fallback)
