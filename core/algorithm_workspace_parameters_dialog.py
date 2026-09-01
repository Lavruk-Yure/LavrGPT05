"""algorithm_workspace_parameters_dialog.py — параметри WSP.

Schema-редактор і контроль профільних bindings індикаторів одного workspace.

Діалог редагує schema-параметри алгоритму, ризику й Replay-поведінки та разом
із ними переносить pending bindings профілів MACD/Alligator до єдиного save
WSP. RoadMap99_04F/04F.1 додає видимий контекст активних профілів: після
вибору Custom MACD/Alligator користувач одразу бачить назву та revision у
головному вікні параметрів, а до натискання ``Зберегти`` стан явно позначений
як такий, що очікує збереження. Це усуває неоднозначність ручного GUI
acceptance та не залишає прихованого profile binding.

Інваріанти: дочірній редактор профілів не змінює persisted WSP самостійно;
усі schema values і profile bindings зберігаються одним підтвердженням;
Runtime не може бути активним під час зміни параметрів; trading logic і
детермінізм Replay цим UI-шаром не змінюються. RoadMap100 додатково перевіряє
фактичну геометрію останнього видимого item дерева вже після показу dialog і
завершення Qt layout. RoadMap100 також стабілізує вертикальну геометрію
``splitParameters``: права панель редактора має vertical policy ``Ignored``,
центральний splitter отримує єдиний stretch, а нижня примітка не забирає
вільну висоту. Тому перемикання між FLOAT/CHOICE/BOOLEAN/group editor більше
не змінює висоту дерева. Щоб унизу не лишався обрізаний параметр, tree
резервує у нижньому viewport рівно видиму частину item, яку реально обрізає
нижня межа. Reserve перераховується після layout/resize/selection-проходів і
не розтягує діалог. Trading logic і детермінізм Replay не змінюються.
RoadMap102 додає read-only snapshot для порожніх груп ``Дані та Replay``,
``Алгоритм``, ``Виконання`` і ``Діагностика та графік``. Snapshot-и показують
лише вже наявні WSP/runtime facts і не створюють нових execution/diagnostic
settings; для Replay збережено штатний перехід у ``Налаштування Replay``.
"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QMessageBox,
    QSizePolicy,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QWidget,
)

from core.algorithm_workspace import (
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    WORKSPACE_PANEL_CHART,
    WORKSPACE_PANEL_LOG,
    WORKSPACE_PANEL_ORDERS,
    WORKSPACE_PANEL_POSITION,
    WORKSPACE_PANEL_SIGNALS,
    AlgorithmWorkspace,
)
from core.lang_manager import LangManager
from core.workspace_indicator_profile import (
    ALLIGATOR_LOGIC_MODE_CANDIDATE_F,
    ALLIGATOR_LOGIC_MODE_LEGACY,
    WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY,
    WORKSPACE_MACD_PROFILE_BINDING_KEY,
    WorkspaceIndicatorProfileBinding,
    normalize_workspace_indicator_profile_bindings,
)
from core.workspace_indicator_profiles_dialog import (
    WorkspaceIndicatorProfilesDialog,
)
from core.workspace_parameter_adapter import (
    WORKSPACE_ALGORITHM_PARAMETER_ADAPTER,
)
from core.workspace_parameter_catalog import WORKSPACE_PARAMETER_CATALOG
from core.workspace_parameter_feature_policy import (
    current_workspace_parameter_feature_profile,
    workspace_parameter_edition_label,
)
from core.workspace_parameter_schema import (
    WORKSPACE_PARAMETER_GROUP_ALGORITHM,
    WORKSPACE_PARAMETER_GROUP_DATA_REPLAY,
    WORKSPACE_PARAMETER_GROUP_DIAGNOSTICS,
    WORKSPACE_PARAMETER_GROUP_EXECUTION,
    WORKSPACE_PARAMETER_TYPE_BOOLEAN,
    WORKSPACE_PARAMETER_TYPE_CHOICE,
    WORKSPACE_PARAMETER_TYPE_FLOAT,
    WORKSPACE_PARAMETER_TYPE_INTEGER,
    WorkspaceParameterFeatureProfile,
)
from core.workspace_parameter_tree import (
    WORKSPACE_PARAMETER_TREE_BUILDER,
    WorkspaceParameterTreeGroup,
    WorkspaceParameterTreeModel,
    WorkspaceParameterTreeNode,
)
from core.workspace_parameters import WorkspaceAlgorithmParameters
from core.workspace_replay_margin import HISTORICAL_REPLAY_LEVERAGE
from core.workspace_replay_settings import WorkspaceReplaySettings
from ui.ui_algorithm_workspace_parameters_dialog import (
    Ui_AlgorithmWorkspaceParametersDialog,
)


class _FallbackTranslator:
    """Повернути fallback-текст без запису localization JSON."""

    @staticmethod
    def tr(_key: str, fallback: str) -> str:
        return fallback


_FALLBACK_TRANSLATOR = _FallbackTranslator()


class AlgorithmWorkspaceParametersDialog(QDialog):
    """Показати дерево та редактор schema-параметрів в одному вікні."""

    replay_settings_requested = Signal(str)

    def __init__(
        self,
        workspace: AlgorithmWorkspace,
        lang_mgr: LangManager | None = None,
        parent: QWidget | None = None,
        *,
        feature_profile: WorkspaceParameterFeatureProfile | None = None,
        runtime_state: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._workspace = workspace
        self._lang_mgr = lang_mgr
        self._feature_profile = (
            feature_profile or current_workspace_parameter_feature_profile()
        )
        self._runtime_state = (
            str(runtime_state or workspace.runtime_state or "STOPPED").strip().upper()
        )
        self.workspace_uid = workspace.workspace_uid
        self._initial_indicator_profile_bindings = (
            normalize_workspace_indicator_profile_bindings(
                workspace.indicator_profile_bindings
            )
        )
        self._pending_indicator_profile_bindings = (
            normalize_workspace_indicator_profile_bindings(
                self._initial_indicator_profile_bindings
            )
        )
        self._initial_legacy = (
            WORKSPACE_ALGORITHM_PARAMETER_ADAPTER.legacy_values_from_workspace(
                workspace
            )
        )
        self._initial_schema_values = (
            WORKSPACE_ALGORITHM_PARAMETER_ADAPTER.schema_values_from_workspace(
                workspace
            )
        )
        self._pending_schema_values = dict(self._initial_schema_values)
        self._tree_model: WorkspaceParameterTreeModel | None = None
        self._parameter_items: dict[str, QTreeWidgetItem] = {}
        self._selected_parameter_key: str | None = None
        self._loading_editor = False
        self._allow_close = False
        self._tree_alignment_passes_remaining = 0
        self._tree_alignment_timer_armed = False
        self._tree_viewport_bottom_reserve = 0

        self.ui = Ui_AlgorithmWorkspaceParametersDialog()
        self.ui.setupUi(self)

        self.lbl_workspace = self.ui.lblWorkspace
        self.lbl_context = self.ui.lblContext
        self.split_parameters = self.ui.splitParameters
        self.tree_parameters = self.ui.treeParameters
        self.pnl_editor = self.ui.pnlEditor
        self.lbl_parameter_title = self.ui.lblParameterTitle
        self.lbl_parameter_description = self.ui.lblParameterDescription
        self.grp_value_editor = self.ui.grpValueEditor
        self.stack_value_editor = self.ui.stackValueEditor
        self.spn_float_value = self.ui.spnFloatValue
        self.spn_integer_value = self.ui.spnIntegerValue
        self.cmb_boolean_value = self.ui.cmbBooleanValue
        self.cmb_choice_value = self.ui.cmbChoiceValue
        self.grp_parameter_details = self.ui.grpParameterDetails
        self.lbl_status_value = self.ui.lblStatusValue
        self.lbl_feature_value = self.ui.lblFeatureValue
        self.lbl_constraints_value = self.ui.lblConstraintsValue
        self.lbl_note = self.ui.lblNote
        self.btn_indicator_profiles = self.ui.btnIndicatorProfiles
        self.btn_replay_settings = self.ui.btnReplaySettings
        self.btn_save = self.ui.btnSave
        self.btn_close = self.ui.btnClose

        self._stabilize_parameter_splitter_height()

        self.tree_parameters.currentItemChanged.connect(self._on_tree_selection_changed)
        self.spn_float_value.valueChanged.connect(self._on_float_changed)
        self.spn_integer_value.valueChanged.connect(self._on_integer_changed)
        self.cmb_boolean_value.currentIndexChanged.connect(self._on_boolean_changed)
        self.cmb_choice_value.currentIndexChanged.connect(self._on_choice_changed)
        self.btn_indicator_profiles.clicked.connect(self._open_indicator_profiles)
        self.btn_replay_settings.clicked.connect(self._request_replay_settings)
        self.btn_save.clicked.connect(self._accept_changes)
        self.btn_close.clicked.connect(self._request_close)

        self.apply_translation(workspace)

    def _stabilize_parameter_splitter_height(self) -> None:
        """Не дозволяти правому editor змінювати вертикальну висоту дерева.

        ``splitParameters`` горизонтальний, але його ``sizeHint`` по вертикалі
        залежить від поточного child праворуч. Word-wrap description/constraints
        та різні сторінки stacked editor тому раніше змінювали висоту splitter і
        залишали внизу tree то повний, то половинний, то чверть рядка.

        Центральний splitter тепер є єдиним вертикально розтяжним елементом
        root layout. Вертикальний sizeHint ``pnlEditor`` ігнорується, а ``lblNote``
        бере лише потрібну їй висоту. Перемикання параметра може перебудувати
        праву панель, але не геометрію дерева.
        """
        split_policy = self.split_parameters.sizePolicy()
        split_policy.setVerticalPolicy(QSizePolicy.Policy.Expanding)
        self.split_parameters.setSizePolicy(split_policy)

        editor_policy = self.pnl_editor.sizePolicy()
        editor_policy.setVerticalPolicy(QSizePolicy.Policy.Ignored)
        self.pnl_editor.setSizePolicy(editor_policy)

        note_policy = self.lbl_note.sizePolicy()
        note_policy.setVerticalPolicy(QSizePolicy.Policy.Maximum)
        self.lbl_note.setSizePolicy(note_policy)

        self.ui.verticalLayout.setStretchFactor(self.split_parameters, 1)
        self.ui.verticalLayout.setStretchFactor(self.lbl_note, 0)

    def parameter_values(self) -> WorkspaceAlgorithmParameters:
        """Повернути legacy-проєкцію зі збереженими прихованими ключами."""
        adapter = WORKSPACE_ALGORITHM_PARAMETER_ADAPTER
        return adapter.legacy_values_after_schema_updates(
            self._workspace,
            self._pending_schema_values,
        )

    def schema_updates(self) -> dict[str, object]:
        """Повернути перевірені значення єдиного schema-редактора."""
        return {
            key: WORKSPACE_PARAMETER_CATALOG.definition(key).normalize_value(value)
            for key, value in self._pending_schema_values.items()
        }

    def indicator_profile_bindings(self) -> dict[str, dict[str, object]]:
        """Повернути pending profile bindings для спільного збереження WSP."""
        return normalize_workspace_indicator_profile_bindings(
            self._pending_indicator_profile_bindings
        )

    def refresh_replay_snapshot(self, workspace: AlgorithmWorkspace) -> None:
        """Оновити read-only Replay snapshot після дочірнього редактора."""
        if workspace.workspace_uid != self.workspace_uid:
            raise ValueError("workspace_uid does not match parameters dialog")
        self._workspace.replay_settings = dict(workspace.replay_settings)
        current = self.tree_parameters.currentItem()
        if current is None:
            return
        code = current.data(0, Qt.ItemDataRole.UserRole)
        if code == WORKSPACE_PARAMETER_GROUP_DATA_REPLAY:
            self._show_group(WORKSPACE_PARAMETER_GROUP_DATA_REPLAY)

    def has_unsaved_changes(self) -> bool:
        """Повернути True, якщо змінено параметри або bindings профілів."""
        return bool(
            self._pending_schema_values != self._initial_schema_values
            or self._pending_indicator_profile_bindings
            != self._initial_indicator_profile_bindings
        )

    def parameter_item(self, key: str) -> QTreeWidgetItem | None:
        """Повернути tree item параметра для UI-перевірок."""
        return self._parameter_items.get(str(key))

    def select_parameter(self, key: str) -> None:
        """Вибрати параметр за стабільним schema key."""
        item = self.parameter_item(key)
        if item is None:
            raise KeyError(key)
        self.tree_parameters.setCurrentItem(item)

    def apply_translation(
        self,
        workspace: AlgorithmWorkspace | None = None,
    ) -> None:
        """Повторно перекласти форму й перебудувати дерево без втрати змін."""
        workspace = workspace or self._workspace
        selected_key = self._selected_parameter_key
        expanded_groups = self._expanded_group_codes()

        self.setWindowTitle(
            self._tr(
                "AlgorithmWorkspaceParametersDialog.windowTitle",
                "Workspace parameters",
            )
        )
        self.lbl_workspace.setText(
            self._tr(
                "AlgorithmWorkspaceParametersDialog.workspace",
                "Workspace: {name}",
            ).format(name=workspace.display_name)
        )
        self._refresh_context_label()
        header = self.tree_parameters.headerItem()
        header.setText(
            0,
            self._tr(
                "AlgorithmWorkspaceParametersDialog.columnParameter",
                "Parameter",
            ),
        )
        header.setText(
            1,
            self._tr(
                "AlgorithmWorkspaceParametersDialog.columnValue",
                "Value",
            ),
        )
        self.grp_value_editor.setTitle(
            self._tr(
                "AlgorithmWorkspaceParametersDialog.grpValueEditor",
                "Value",
            )
        )
        self.grp_parameter_details.setTitle(
            self._tr(
                "AlgorithmWorkspaceParametersDialog.grpParameterDetails",
                "Parameter details",
            )
        )
        self.ui.lblStatusCaption.setText(
            self._tr(
                "AlgorithmWorkspaceParametersDialog.lblStatus",
                "Status:",
            )
        )
        self.ui.lblFeatureCaption.setText(
            self._tr(
                "AlgorithmWorkspaceParametersDialog.lblFeature",
                "Feature:",
            )
        )
        self.ui.lblConstraintsCaption.setText(
            self._tr(
                "AlgorithmWorkspaceParametersDialog.lblConstraints",
                "Constraints:",
            )
        )
        self.lbl_note.setText(
            self._tr(
                "AlgorithmWorkspaceParametersDialog.note",
                "MACD and Alligator are the first independent test components. "
                "Other signals and filters will be added one by one. Spread "
                "policy and warm-up are calculated by Runtime; legacy values "
                "remain stored for compatibility.",
            )
        )
        self.btn_indicator_profiles.setText(
            self._tr(
                "AlgorithmWorkspaceParametersDialog.btnIndicatorProfiles",
                "Indicator profiles...",
            )
        )
        self.btn_replay_settings.setText(
            self._tr(
                "AlgorithmWorkspaceParametersDialog.btnReplaySettings",
                "Replay settings...",
            )
        )
        self.btn_save.setText(
            self._tr(
                "AlgorithmWorkspaceParametersDialog.btnSave",
                "Save",
            )
        )
        self.btn_close.setText(
            self._tr(
                "AlgorithmWorkspaceParametersDialog.btnClose",
                "Close",
            )
        )
        self._translate_boolean_choices()
        self._build_tree(expanded_groups)
        self._prepare_tree_viewport_alignment()

        if selected_key and selected_key in self._parameter_items:
            self.select_parameter(selected_key)
        else:
            self._show_no_selection()

    def _refresh_context_label(self) -> None:
        """Показати edition/runtime та точні pending профілі MACD/Alligator."""
        base = self._tr(
            "AlgorithmWorkspaceParametersDialog.context",
            "Edition: {edition} | Runtime: {runtime_state}",
        ).format(
            edition=workspace_parameter_edition_label(self._feature_profile.edition),
            runtime_state=self._runtime_state,
        )
        bindings = normalize_workspace_indicator_profile_bindings(
            self._pending_indicator_profile_bindings
        )
        macd = WorkspaceIndicatorProfileBinding.from_storage_dict(
            bindings[WORKSPACE_MACD_PROFILE_BINDING_KEY]
        )
        alligator = WorkspaceIndicatorProfileBinding.from_storage_dict(
            bindings[WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY]
        )
        pending = bindings != normalize_workspace_indicator_profile_bindings(
            self._initial_indicator_profile_bindings
        )
        key = (
            "AlgorithmWorkspaceParametersDialog.indicatorProfilesPending"
            if pending
            else "AlgorithmWorkspaceParametersDialog.indicatorProfiles"
        )
        fallback = (
            "Indicator profiles pending Save: MACD — {macd}; " "Alligator — {alligator}"
            if pending
            else "Indicator profiles: MACD — {macd}; Alligator — {alligator}"
        )
        profiles = self._tr(key, fallback).format(
            macd=f"{macd.profile.name} r{macd.profile_revision}",
            alligator=f"{alligator.profile.name} r{alligator.profile_revision}",
        )
        self.lbl_context.setText(f"{base}\n{profiles}")

    def _open_indicator_profiles(self) -> None:
        """Відкрити Designer-редактор профілів без негайної зміни WSP."""
        dialog = WorkspaceIndicatorProfilesDialog(
            self._workspace,
            self._lang_mgr,
            self,
            initial_bindings=self._pending_indicator_profile_bindings,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._pending_indicator_profile_bindings = dialog.indicator_profile_bindings()
        self._refresh_context_label()
        current = self.tree_parameters.currentItem()
        if (
            current is not None
            and current.data(0, Qt.ItemDataRole.UserRole)
            == WORKSPACE_PARAMETER_GROUP_ALGORITHM
        ):
            self._show_algorithm_snapshot()

    def _request_replay_settings(self) -> None:
        """Передати area запит на штатний редактор Replay для цього WSP."""
        self.replay_settings_requested.emit(self.workspace_uid)

    def showEvent(self, event: QShowEvent) -> None:
        """Повторно вирівняти tree вже після фактичного показу dialog."""
        super().showEvent(event)
        self._prepare_tree_viewport_alignment()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Перерахувати нижній reserve після реальної зміни висоти dialog."""
        super().resizeEvent(event)
        self._prepare_tree_viewport_alignment()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Не втрачати непідтверджені зміни без явної згоди."""
        if self._allow_close or not self.has_unsaved_changes():
            event.accept()
            return
        if self._confirm_discard_changes():
            self._allow_close = True
            event.accept()
            return
        event.ignore()

    def reject(self) -> None:
        """Закрити діалог через Esc із захистом незбережених змін."""
        self._request_close()

    def _build_tree(self, expanded_groups: set[str]) -> None:
        self._tree_model = WORKSPACE_PARAMETER_TREE_BUILDER.build(
            workspace=self._workspace,
            profile=self._feature_profile,
            runtime_state=self._runtime_state,
            translator=self._translator(),
        )
        self.tree_parameters.clear()
        self._parameter_items.clear()

        for group in self._tree_model.groups:
            group_item = QTreeWidgetItem([group.title, ""])
            group_item.setData(0, Qt.ItemDataRole.UserRole, group.code)
            group_item.setToolTip(0, group.description)
            self.tree_parameters.addTopLevelItem(group_item)
            for node in group.parameters:
                item = QTreeWidgetItem(
                    [
                        node.title,
                        self._format_node_value(
                            node,
                            self._pending_schema_values[node.key],
                        ),
                    ]
                )
                item.setData(0, Qt.ItemDataRole.UserRole, node.key)
                item.setToolTip(0, node.description)
                item.setToolTip(1, self._constraints_text(node))
                group_item.addChild(item)
                self._parameter_items[node.key] = item
            group_item.setExpanded(
                group.code in expanded_groups or bool(group.parameters)
            )

        self.tree_parameters.resizeColumnToContents(0)
        self.tree_parameters.header().setStretchLastSection(True)

    def _prepare_tree_viewport_alignment(self, passes: int = 4) -> None:
        """Скинути старий reserve і запустити вимір уже нової геометрії.

        Reserve залежить від фактичної висоти viewport. Після resize/show старий
        reserve спочатку прибирається, а вимір відкладається на event loop, щоб
        Qt устиг завершити layout і повернув реальні ``visualItemRect``.
        """
        self._clear_tree_viewport_bottom_reserve()
        self._schedule_tree_viewport_alignment(passes)

    def _clear_tree_viewport_bottom_reserve(self) -> None:
        """Прибрати тільки margin, який додав цей dialog для full-row UI."""
        reserve = self._tree_viewport_bottom_reserve
        if reserve <= 0:
            return
        margins = self.tree_parameters.viewportMargins()
        self.tree_parameters.setViewportMargins(
            margins.left(),
            margins.top(),
            margins.right(),
            max(0, margins.bottom() - reserve),
        )
        self._tree_viewport_bottom_reserve = 0

    def _schedule_tree_viewport_alignment(self, passes: int = 4) -> None:
        """Запланувати post-layout перевірки нижнього видимого row дерева.

        ``apply_translation()`` викликається ще під час ``__init__``, коли Qt
        може мати лише попередню геометрію. ``showEvent`` і ``resizeEvent``
        повторюють перевірку вже для реального dialog. Кілька нульових
        ``singleShot`` проходів потрібні, бо зміна viewport margin сама проходить
        через layout перед наступним точним ``visualItemRect``.
        """
        requested = max(1, int(passes))
        self._tree_alignment_passes_remaining = max(
            self._tree_alignment_passes_remaining,
            requested,
        )
        if self._tree_alignment_timer_armed:
            return
        self._tree_alignment_timer_armed = True
        QTimer.singleShot(0, self._run_tree_viewport_alignment_pass)

    def _run_tree_viewport_alignment_pass(self) -> None:
        """Виконати один вимір і за потреби запланувати наступний."""
        self._tree_alignment_timer_armed = False
        if self._tree_alignment_passes_remaining <= 0:
            return

        self._tree_alignment_passes_remaining -= 1
        self._align_tree_viewport_to_full_rows()

        if self._tree_alignment_passes_remaining <= 0:
            return
        self._tree_alignment_timer_armed = True
        QTimer.singleShot(0, self._run_tree_viewport_alignment_pass)

    def _align_tree_viewport_to_full_rows(self) -> None:
        """Сховати лише видиму частину row, обрізаного нижньою межею.

        Висота viewport не зобов'язана бути кратною висоті row: frame, header і
        native Windows style додають власні пікселі. Тому modulo-підхід давав
        хибну геометрію. Канонічний критерій тепер прямий: знаходимо через
        ``visualItemRect`` item, який реально перетинає нижню межу viewport, і
        резервуємо рівно ту його частину, яка вже видима. Повністю видимі rows
        не чіпаються, а наступний post-layout pass перевіряє результат.
        """
        viewport_height = self.tree_parameters.viewport().height()
        if viewport_height <= 0:
            return

        iterator = QTreeWidgetItemIterator(self.tree_parameters)
        while iterator.value() is not None:
            rect = self.tree_parameters.visualItemRect(iterator.value())
            if (
                rect.isValid()
                and rect.height() > 0
                and 0 <= rect.top() < viewport_height <= rect.bottom()
            ):
                visible_partial_height = viewport_height - rect.top()
                if 0 < visible_partial_height < rect.height():
                    margins = self.tree_parameters.viewportMargins()
                    self.tree_parameters.setViewportMargins(
                        margins.left(),
                        margins.top(),
                        margins.right(),
                        margins.bottom() + visible_partial_height,
                    )
                    self._tree_viewport_bottom_reserve += visible_partial_height
                return
            iterator += 1

    def _on_tree_selection_changed(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None,
    ) -> None:
        if current is None:
            self._show_no_selection()
            self._prepare_tree_viewport_alignment()
            return
        code = current.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(code, str) or "." not in code:
            self._show_group(code)
        else:
            self._show_parameter(code)
        self._prepare_tree_viewport_alignment()

    def _show_group(self, code: object) -> None:
        self._selected_parameter_key = None
        group = self._group(str(code or ""))
        if group is None:
            self._show_no_selection()
            return
        self.lbl_parameter_title.setText(group.title)
        self.lbl_parameter_description.setText(group.description)
        if group.code == WORKSPACE_PARAMETER_GROUP_DATA_REPLAY:
            self._show_data_replay_snapshot()
            return
        if group.code == WORKSPACE_PARAMETER_GROUP_ALGORITHM:
            self._show_algorithm_snapshot()
            return
        if group.code == WORKSPACE_PARAMETER_GROUP_EXECUTION:
            self._show_execution_snapshot()
            return
        if group.code == WORKSPACE_PARAMETER_GROUP_DIAGNOSTICS:
            self._show_diagnostics_snapshot()
            return
        self._restore_parameter_editor_chrome()
        self.ui.lblNoSelection.setText(
            self._tr(
                "AlgorithmWorkspaceParametersDialog.emptyGroup",
                "No parameters are defined for this group yet.",
            )
            if not group.parameters
            else self._tr(
                "AlgorithmWorkspaceParametersDialog.selectParameter",
                "Select a parameter in this group.",
            )
        )
        self.stack_value_editor.setCurrentWidget(self.ui.pageNoSelection)
        self._clear_details()

    def _show_data_replay_snapshot(self) -> None:
        """Показати read-only snapshot джерела й Replay WSP."""
        self._prepare_group_snapshot_view(show_replay_button=True)
        replay = WorkspaceReplaySettings.from_workspace(self._workspace)
        if self._workspace.data_mode == WORKSPACE_DATA_MODE_REPLAY:
            current_source = f"{WORKSPACE_DATA_MODE_REPLAY} / {replay.source_type}"
        else:
            current_source = (
                f"{self._workspace.data_mode} / Replay {replay.source_type}"
            )

        dataset = replay.source_name or "—"
        if replay.file_path:
            file_name = Path(replay.file_path).name
            if dataset == "—":
                dataset = file_name
            elif file_name and file_name != dataset:
                dataset = f"{dataset} ({file_name})"
            self.ui.lblNoSelection.setToolTip(replay.file_path)
        else:
            self.ui.lblNoSelection.setToolTip("")

        period_lines = self._replay_period_lines(replay)
        replay_leverage = f"1:{HISTORICAL_REPLAY_LEVERAGE:g}"
        lines = (
            self._snapshot_line(
                "AlgorithmWorkspaceParametersDialog.snapshotCurrentSource",
                "Current source",
                current_source,
            ),
            self._snapshot_line(
                "AlgorithmWorkspaceParametersDialog.snapshotCsvDataset",
                "CSV dataset",
                dataset,
            ),
            self._snapshot_multiline_value(
                "AlgorithmWorkspaceParametersDialog.snapshotReplayPeriod",
                "Replay period",
                period_lines,
            ),
            self._snapshot_line(
                "AlgorithmWorkspaceParametersDialog.snapshotSpread",
                "Spread",
                format(replay.spread, ".12g"),
            ),
            self._snapshot_line(
                "AlgorithmWorkspaceParametersDialog.snapshotInitialBalance",
                "Initial balance",
                f"{replay.initial_balance:.2f} USD",
            ),
            self._snapshot_line(
                "AlgorithmWorkspaceParametersDialog.snapshotReplayLeverage",
                "Replay leverage",
                replay_leverage,
            ),
        )
        self.ui.lblNoSelection.setText("\n".join(lines))

    def _show_algorithm_snapshot(self) -> None:
        """Показати production/profile snapshot без другого редактора."""
        self._prepare_group_snapshot_view(show_replay_button=False)
        bindings = normalize_workspace_indicator_profile_bindings(
            self._pending_indicator_profile_bindings
        )
        macd = WorkspaceIndicatorProfileBinding.from_storage_dict(
            bindings[WORKSPACE_MACD_PROFILE_BINDING_KEY]
        )
        alligator = WorkspaceIndicatorProfileBinding.from_storage_dict(
            bindings[WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY]
        )
        logic_mode = str(
            alligator.profile.parameters.get(
                "logic_mode",
                ALLIGATOR_LOGIC_MODE_LEGACY,
            )
        )
        logic_label = self._alligator_logic_label(logic_mode)
        confirmation = self._choice_display_value(
            "filters.alligator_confirmation",
            self._pending_schema_values.get("filters.alligator_confirmation"),
        )
        profile_text = (
            f"{logic_label} / {alligator.profile.name} "
            f"r{alligator.profile_revision}"
        )
        lines = (
            self._snapshot_line(
                "AlgorithmWorkspaceParametersDialog.snapshotAlgorithm",
                "Algorithm",
                self._workspace.algorithm,
            ),
            self._snapshot_line(
                "AlgorithmWorkspaceParametersDialog.snapshotProductionLogic",
                "Production logic / profile",
                profile_text,
            ),
            self._snapshot_line(
                "AlgorithmWorkspaceParametersDialog.snapshotMacdProfile",
                "MACD profile / revision",
                f"{macd.profile.name} r{macd.profile_revision}",
            ),
            self._snapshot_line(
                "AlgorithmWorkspaceParametersDialog.snapshotAlligatorProfile",
                "Alligator profile / revision",
                f"{alligator.profile.name} r{alligator.profile_revision}",
            ),
            self._snapshot_line(
                "AlgorithmWorkspaceParametersDialog.snapshotConfirmationMode",
                "Confirmation mode",
                confirmation,
            ),
            self._snapshot_line(
                "AlgorithmWorkspaceParametersDialog.snapshotLogicMode",
                "Candidate F / legacy mode",
                logic_label,
            ),
        )
        self.ui.lblNoSelection.setToolTip("")
        self.ui.lblNoSelection.setText("\n".join(lines))

    def _show_execution_snapshot(self) -> None:
        """Показати фактичний execution context WSP без нових settings."""
        self._prepare_group_snapshot_view(show_replay_button=False)
        account_mode = self._workspace.account_mode or "—"
        account_id = self._workspace.account_id or "—"
        broker_account = f"{self._workspace.broker} / {account_id}"
        lines = [
            self._snapshot_line(
                "AlgorithmWorkspaceParametersDialog.snapshotDataMode",
                "Data mode",
                self._workspace.data_mode,
            ),
            self._snapshot_line(
                "AlgorithmWorkspaceParametersDialog.snapshotAccountMode",
                "Account mode",
                account_mode,
            ),
            self._snapshot_line(
                "AlgorithmWorkspaceParametersDialog.snapshotControlMode",
                "Control mode",
                self._workspace.control_mode,
            ),
            self._snapshot_line(
                "AlgorithmWorkspaceParametersDialog.snapshotBrokerAccount",
                "Broker / account",
                broker_account,
            ),
            self._snapshot_line(
                "AlgorithmWorkspaceParametersDialog.snapshotRuntimeState",
                "WSP runtime state",
                self._runtime_state,
            ),
        ]
        if self._workspace.data_mode == WORKSPACE_DATA_MODE_REPLAY:
            if self._workspace.control_mode == WORKSPACE_CONTROL_MODE_AUTO:
                execution_mode = self._tr(
                    "AlgorithmWorkspaceParametersDialog.executionVirtualReplayAuto",
                    "Virtual Replay execution (AUTO)",
                )
            else:
                execution_mode = self._tr(
                    "AlgorithmWorkspaceParametersDialog.executionReplaySignalsOnly",
                    "Replay signals only; virtual execution requires AUTO",
                )
            lines.extend(
                (
                    self._snapshot_line(
                        "AlgorithmWorkspaceParametersDialog.snapshotExecutionMode",
                        "Execution mode",
                        execution_mode,
                    ),
                    self._snapshot_line(
                        "AlgorithmWorkspaceParametersDialog.snapshotReplayEntryPolicy",
                        "Replay entry policy",
                        "NEXT_BAR_OPEN",
                    ),
                    self._snapshot_line(
                        "AlgorithmWorkspaceParametersDialog.snapshotBrokerExecution",
                        "Broker execution",
                        self._tr(
                            "AlgorithmWorkspaceParametersDialog."
                            "brokerExecutionDisabledReplay",
                            "Disabled in Historical Replay",
                        ),
                    ),
                )
            )
        self.ui.lblNoSelection.setToolTip("")
        self.ui.lblNoSelection.setText("\n".join(lines))

    def _show_diagnostics_snapshot(self) -> None:
        """Показати фактичний runtime/chart context WSP без нових settings."""
        self._prepare_group_snapshot_view(show_replay_button=False)
        active_panel = str(
            self._workspace.ui_state.get("active_panel") or WORKSPACE_PANEL_CHART
        ).upper()
        lines = (
            self._snapshot_line(
                "AlgorithmWorkspaceParametersDialog.snapshotRuntimeState",
                "WSP runtime state",
                self._runtime_state,
            ),
            self._snapshot_line(
                "AlgorithmWorkspaceParametersDialog.snapshotMarketContext",
                "Instrument / timeframe",
                f"{self._workspace.symbol} / {self._workspace.timeframe}",
            ),
            self._snapshot_line(
                "AlgorithmWorkspaceParametersDialog.snapshotActivePanel",
                "Active WSP panel",
                self._panel_display_value(active_panel),
            ),
            self._snapshot_line(
                "AlgorithmWorkspaceParametersDialog.snapshotDiagnosticSurfaces",
                "Diagnostic surfaces",
                self._tr(
                    "AlgorithmWorkspaceParametersDialog.diagnosticSurfacesValue",
                    "Signals / Journal / Chart",
                ),
            ),
            self._snapshot_line(
                "AlgorithmWorkspaceParametersDialog.snapshotStartedOnce",
                "WSP started before",
                self._yes_no(self._workspace.has_started_once),
            ),
            self._snapshot_line(
                "AlgorithmWorkspaceParametersDialog.snapshotUpdatedUtc",
                "WSP snapshot updated UTC",
                self._workspace.updated_utc,
            ),
        )
        self.ui.lblNoSelection.setToolTip("")
        self.ui.lblNoSelection.setText("\n".join(lines))

    def _panel_display_value(self, panel: str) -> str:
        """Повернути читабельну назву збереженої WSP panel."""
        labels = {
            WORKSPACE_PANEL_CHART: (
                "AlgorithmWorkspaceParametersDialog.panelChart",
                "Chart",
            ),
            WORKSPACE_PANEL_POSITION: (
                "AlgorithmWorkspaceParametersDialog.panelPosition",
                "Position",
            ),
            WORKSPACE_PANEL_SIGNALS: (
                "AlgorithmWorkspaceParametersDialog.panelSignals",
                "Signals",
            ),
            WORKSPACE_PANEL_ORDERS: (
                "AlgorithmWorkspaceParametersDialog.panelOrders",
                "Orders",
            ),
            WORKSPACE_PANEL_LOG: (
                "AlgorithmWorkspaceParametersDialog.panelJournal",
                "Journal",
            ),
        }
        key, fallback = labels.get(
            panel,
            ("AlgorithmWorkspaceParametersDialog.panelUnknown", panel or "—"),
        )
        return self._tr(key, fallback)

    def _yes_no(self, value: bool) -> str:
        """Повернути локалізоване Так/Ні для snapshot."""
        if value:
            return self._tr(
                "AlgorithmWorkspaceParametersDialog.booleanYes",
                "Yes",
            )
        return self._tr(
            "AlgorithmWorkspaceParametersDialog.booleanNo",
            "No",
        )

    def _prepare_group_snapshot_view(self, *, show_replay_button: bool) -> None:
        """Налаштувати Designer-page як компактний snapshot."""
        self.grp_value_editor.setTitle(
            self._tr(
                "AlgorithmWorkspaceParametersDialog.grpWorkspaceSnapshot",
                "Workspace snapshot",
            )
        )
        self.ui.lblNoSelection.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self.stack_value_editor.setCurrentWidget(self.ui.pageNoSelection)
        self.grp_parameter_details.setVisible(False)
        self.btn_replay_settings.setVisible(show_replay_button)
        self.btn_replay_settings.setEnabled(
            self._workspace.data_mode == WORKSPACE_DATA_MODE_REPLAY
        )
        self._clear_details()

    def _restore_parameter_editor_chrome(self) -> None:
        """Повернути стандартне оформлення редактора параметра."""
        self.grp_value_editor.setTitle(
            self._tr(
                "AlgorithmWorkspaceParametersDialog.grpValueEditor",
                "Value",
            )
        )
        self.ui.lblNoSelection.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ui.lblNoSelection.setToolTip("")
        self.grp_parameter_details.setVisible(True)
        self.btn_replay_settings.setVisible(False)

    def _snapshot_line(self, key: str, fallback: str, value: object) -> str:
        """Сформувати локалізований рядок read-only snapshot."""
        label = self._tr(key, fallback)
        return f"{label}: {self._format_value(value)}"

    def _snapshot_multiline_value(
        self,
        key: str,
        fallback: str,
        values: tuple[str, ...],
    ) -> str:
        """Сформувати label і значення snapshot окремими рядками."""
        label = self._tr(key, fallback)
        rendered = "\n".join(self._format_value(value) for value in values)
        return f"{label}:\n{rendered}"

    @staticmethod
    def _replay_period_lines(
        replay: WorkspaceReplaySettings,
    ) -> tuple[str, str]:
        """Показати межі Replay окремими рядками без зміни UTC semantics."""
        start = replay.start_utc or "—"
        end = replay.end_utc or "—"
        return start, end

    def _alligator_logic_label(self, logic_mode: str) -> str:
        """Повернути читабельний production mode Alligator."""
        if logic_mode == ALLIGATOR_LOGIC_MODE_CANDIDATE_F:
            return self._tr(
                "AlgorithmWorkspaceParametersDialog.logicCandidateF",
                "Candidate F",
            )
        return self._tr(
            "AlgorithmWorkspaceParametersDialog.logicLegacy",
            "Legacy",
        )

    def _choice_display_value(self, key: str, value: object) -> str:
        """Показати локалізований label schema-choice."""
        if self._tree_model is None:
            return self._format_value(value)
        try:
            node = self._tree_model.parameter(key)
        except ValueError:
            return self._format_value(value)
        normalized = str(value)
        for option, label in node.allowed_value_labels:
            if option == normalized:
                return label
        return self._format_value(value)

    def _show_parameter(self, key: str) -> None:
        if self._tree_model is None:
            return
        self._restore_parameter_editor_chrome()
        node = self._tree_model.parameter(key)
        self._selected_parameter_key = node.key
        self.lbl_parameter_title.setText(node.title)
        self.lbl_parameter_description.setText(node.description)
        self.lbl_status_value.setText(
            node.status if node.reason is None else f"{node.status}. {node.reason}"
        )
        self.lbl_feature_value.setText(node.feature_code)
        self.lbl_constraints_value.setText(self._constraints_text(node))
        self._load_editor(node)

    def _load_editor(self, node: WorkspaceParameterTreeNode) -> None:
        self._loading_editor = True
        try:
            value = self._pending_schema_values[node.key]
            if node.value_type == WORKSPACE_PARAMETER_TYPE_FLOAT:
                self._configure_float_editor(node, value)
            elif node.value_type == WORKSPACE_PARAMETER_TYPE_INTEGER:
                self._configure_integer_editor(node, value)
            elif node.value_type == WORKSPACE_PARAMETER_TYPE_BOOLEAN:
                self._configure_boolean_editor(value)
            elif node.value_type == WORKSPACE_PARAMETER_TYPE_CHOICE:
                self._configure_choice_editor(node, value)
            else:
                self.stack_value_editor.setCurrentWidget(self.ui.pageNoSelection)
            self.stack_value_editor.currentWidget().setEnabled(node.editable)
        finally:
            self._loading_editor = False

    def _configure_float_editor(
        self,
        node: WorkspaceParameterTreeNode,
        value: object,
    ) -> None:
        minimum = float(node.minimum) if node.minimum is not None else -1e12
        maximum = float(node.maximum) if node.maximum is not None else 1e12
        step = float(node.step) if node.step is not None else 0.01
        self.spn_float_value.setDecimals(self._float_decimals(step))
        self.spn_float_value.setRange(minimum, maximum)
        self.spn_float_value.setSingleStep(step)
        number = self._parameter_float(value, node.key)
        self.spn_float_value.setValue(number)
        self.stack_value_editor.setCurrentWidget(self.ui.pageFloat)

    def _configure_integer_editor(
        self,
        node: WorkspaceParameterTreeNode,
        value: object,
    ) -> None:
        minimum = int(node.minimum) if node.minimum is not None else -2147483647
        maximum = int(node.maximum) if node.maximum is not None else 2147483647
        step = int(node.step) if node.step is not None else 1
        self.spn_integer_value.setRange(minimum, maximum)
        self.spn_integer_value.setSingleStep(step)
        number = self._parameter_integer(value, node.key)
        self.spn_integer_value.setValue(number)
        self.stack_value_editor.setCurrentWidget(self.ui.pageInteger)

    def _configure_boolean_editor(self, value: object) -> None:
        self._translate_boolean_choices()
        index = self.cmb_boolean_value.findData(bool(value))
        self.cmb_boolean_value.setCurrentIndex(max(index, 0))
        self.stack_value_editor.setCurrentWidget(self.ui.pageBoolean)

    def _configure_choice_editor(
        self,
        node: WorkspaceParameterTreeNode,
        value: object,
    ) -> None:
        self.cmb_choice_value.clear()
        for option, label in node.allowed_value_labels:
            self.cmb_choice_value.addItem(label, option)
        index = self.cmb_choice_value.findData(str(value))
        self.cmb_choice_value.setCurrentIndex(max(index, 0))
        self.stack_value_editor.setCurrentWidget(self.ui.pageChoice)

    def _on_float_changed(self, value: float) -> None:
        self._store_editor_value(value)

    def _on_integer_changed(self, value: int) -> None:
        self._store_editor_value(value)

    def _on_boolean_changed(self, _index: int) -> None:
        self._store_editor_value(self.cmb_boolean_value.currentData())

    def _on_choice_changed(self, _index: int) -> None:
        self._store_editor_value(self.cmb_choice_value.currentData())

    def _store_editor_value(self, value: object) -> None:
        if self._loading_editor or self._selected_parameter_key is None:
            return
        if self._tree_model is None:
            return
        node = self._tree_model.parameter(self._selected_parameter_key)
        if not node.editable:
            return
        definition = WORKSPACE_PARAMETER_CATALOG.definition(node.key)
        normalized = definition.normalize_value(value)
        self._pending_schema_values[node.key] = normalized
        item = self._parameter_items.get(node.key)
        if item is not None:
            item.setText(1, self._format_node_value(node, normalized))

    def _accept_changes(self) -> None:
        self.schema_updates()
        self._allow_close = True
        self.accept()

    def _request_close(self) -> None:
        if self.has_unsaved_changes() and not self._confirm_discard_changes():
            return
        self._allow_close = True
        super().reject()

    def _confirm_discard_changes(self) -> bool:
        answer = QMessageBox.question(
            self,
            self._tr(
                "AlgorithmWorkspaceParametersDialog.unsavedTitle",
                "Unsaved changes",
            ),
            self._tr(
                "AlgorithmWorkspaceParametersDialog.unsavedQuestion",
                "Close without saving the parameter changes?",
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _show_no_selection(self) -> None:
        self._selected_parameter_key = None
        self._restore_parameter_editor_chrome()
        self.lbl_parameter_title.setText(
            self._tr(
                "AlgorithmWorkspaceParametersDialog.selectParameterTitle",
                "Select a parameter",
            )
        )
        self.lbl_parameter_description.setText(
            self._tr(
                "AlgorithmWorkspaceParametersDialog.selectParameterDescription",
                "Choose a group and parameter in the tree.",
            )
        )
        self.ui.lblNoSelection.setText(
            self._tr(
                "AlgorithmWorkspaceParametersDialog.noSelection",
                "No parameter is selected.",
            )
        )
        self.stack_value_editor.setCurrentWidget(self.ui.pageNoSelection)
        self._clear_details()

    def _clear_details(self) -> None:
        self.lbl_status_value.setText("—")
        self.lbl_feature_value.setText("—")
        self.lbl_constraints_value.setText("—")

    def _constraints_text(self, node: WorkspaceParameterTreeNode) -> str:
        parts = [
            self._tr(
                "AlgorithmWorkspaceParametersDialog.valueType",
                "Type: {value_type}",
            ).format(value_type=node.value_type)
        ]
        if node.minimum is not None:
            parts.append(
                self._tr(
                    "AlgorithmWorkspaceParametersDialog.minimum",
                    "Minimum: {value}",
                ).format(value=self._format_node_number(node, node.minimum))
            )
        if node.maximum is not None:
            parts.append(
                self._tr(
                    "AlgorithmWorkspaceParametersDialog.maximum",
                    "Maximum: {value}",
                ).format(value=self._format_node_number(node, node.maximum))
            )
        if node.step is not None:
            parts.append(
                self._tr(
                    "AlgorithmWorkspaceParametersDialog.step",
                    "Step: {value}",
                ).format(value=self._format_node_number(node, node.step))
            )
        if node.allowed_values:
            parts.append(
                self._tr(
                    "AlgorithmWorkspaceParametersDialog.allowedValues",
                    "Allowed values: {values}",
                ).format(
                    values=", ".join(
                        label for _value, label in node.allowed_value_labels
                    )
                )
            )
        return " | ".join(parts)

    def _format_node_value(
        self,
        node: WorkspaceParameterTreeNode,
        value: object,
    ) -> str:
        if node.value_type == WORKSPACE_PARAMETER_TYPE_CHOICE:
            normalized = str(value)
            for option, label in node.allowed_value_labels:
                if option == normalized:
                    return label
        if node.value_type == WORKSPACE_PARAMETER_TYPE_FLOAT:
            return self._format_node_number(node, value)
        return self._format_value(value)

    def _format_node_number(
        self,
        node: WorkspaceParameterTreeNode,
        value: object,
    ) -> str:
        if node.value_type != WORKSPACE_PARAMETER_TYPE_FLOAT:
            return self._format_value(value)
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            return self._format_value(value)
        try:
            number = float(value)
        except ValueError:
            return self._format_value(value)
        if not math.isfinite(number):
            return self._format_value(value)
        step = float(node.step) if node.step is not None else 0.0
        decimals = self._float_decimals(step)
        return f"{number:.{decimals}f}"

    def _format_value(self, value: object) -> str:
        if value is None:
            return "—"
        if isinstance(value, bool):
            return self._tr(
                (
                    "AlgorithmWorkspaceParametersDialog.booleanYes"
                    if value
                    else "AlgorithmWorkspaceParametersDialog.booleanNo"
                ),
                "Yes" if value else "No",
            )
        if isinstance(value, float):
            return format(value, ".12g")
        return str(value)

    def _translate_boolean_choices(self) -> None:
        current = self.cmb_boolean_value.currentData()
        self._loading_editor = True
        try:
            self.cmb_boolean_value.clear()
            self.cmb_boolean_value.addItem(
                self._tr(
                    "AlgorithmWorkspaceParametersDialog.booleanNo",
                    "No",
                ),
                False,
            )
            self.cmb_boolean_value.addItem(
                self._tr(
                    "AlgorithmWorkspaceParametersDialog.booleanYes",
                    "Yes",
                ),
                True,
            )
            index = self.cmb_boolean_value.findData(current)
            self.cmb_boolean_value.setCurrentIndex(max(index, 0))
        finally:
            self._loading_editor = False

    def _expanded_group_codes(self) -> set[str]:
        result: set[str] = set()
        for index in range(self.tree_parameters.topLevelItemCount()):
            item = self.tree_parameters.topLevelItem(index)
            if item.isExpanded():
                code = item.data(0, Qt.ItemDataRole.UserRole)
                if isinstance(code, str) and code:
                    result.add(code)
        return result

    def _group(self, code: str) -> WorkspaceParameterTreeGroup | None:
        if self._tree_model is None:
            return None
        for group in self._tree_model.groups:
            if group.code == code:
                return group
        return None

    @staticmethod
    def _float_decimals(step: float) -> int:
        if step <= 0.0 or not math.isfinite(step):
            return 6
        text = f"{step:.12f}".rstrip("0")
        if "." not in text:
            return 0
        return min(8, len(text.split(".", 1)[1]))

    def _translator(self) -> LangManager | _FallbackTranslator:
        if self._lang_mgr is not None:
            return self._lang_mgr
        return _FALLBACK_TRANSLATOR

    def _tr(self, key: str, fallback: str) -> str:
        if self._lang_mgr is None:
            return fallback
        return self._lang_mgr.tr(key, fallback)

    @staticmethod
    def _parameter_float(value: object, field_name: str) -> float:
        if isinstance(value, bool):
            raise ValueError(f"{field_name} must be a number")

        if isinstance(value, (int, float)):
            return float(value)

        if isinstance(value, str):
            text = value.strip()
            if not text:
                raise ValueError(f"{field_name} must be a number")
            try:
                return float(text)
            except ValueError as exc:
                raise ValueError(f"{field_name} must be a number") from exc

        raise ValueError(f"{field_name} must be a number")

    @staticmethod
    def _parameter_integer(value: object, field_name: str) -> int:
        if isinstance(value, bool):
            raise ValueError(f"{field_name} must be an integer")

        if isinstance(value, int):
            return value

        if isinstance(value, str):
            text = value.strip()
            if not text:
                raise ValueError(f"{field_name} must be an integer")
            try:
                return int(text)
            except ValueError as exc:
                raise ValueError(f"{field_name} must be an integer") from exc

        raise ValueError(f"{field_name} must be an integer")
