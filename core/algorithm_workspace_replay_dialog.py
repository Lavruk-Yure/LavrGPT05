# -*- coding: utf-8 -*-
"""core.algorithm_workspace_replay_dialog

Designer-based editor for one WSP Replay source and exact test period.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QDateTime, QTimeZone, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QFileDialog,
    QMessageBox,
    QWidget,
)

from core.algorithm_workspace import AlgorithmWorkspace
from core.timeframes import get_timeframe, list_enabled_timeframes
from core.lang_manager import LangManager
from core.workspace_history import (
    WorkspaceCsvHistoryLoader,
    WorkspaceHistoryError,
    WorkspaceHistoryRange,
)
from core.workspace_replay_settings import WorkspaceReplaySettings
from engine.runtime_constants import (
    WORKSPACE_HISTORY_DECIMAL_SEPARATORS,
    WORKSPACE_HISTORY_DELIMITERS,
    WORKSPACE_HISTORY_TIMEZONE_CHOICES,
    WORKSPACE_REPLAY_SOURCE_CSV,
    WORKSPACE_REPLAY_SOURCE_SYNTHETIC,
)
from ui.ui_algorithm_workspace_replay_dialog import (
    Ui_AlgorithmWorkspaceReplayDialog,
)


class AlgorithmWorkspaceReplayDialog(QDialog):
    """Edit validated Replay source, CSV format and exact test period."""

    def __init__(
        self,
        workspace: AlgorithmWorkspace,
        lang_mgr: LangManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._lang_mgr = lang_mgr
        self._workspace = workspace
        self.workspace_uid = workspace.workspace_uid
        self._initial = WorkspaceReplaySettings.from_workspace(workspace)
        self._history_loader = WorkspaceCsvHistoryLoader()
        self._detected_history_signature: tuple[Path, str, str] | None = None
        self._detected_history_range: WorkspaceHistoryRange | None = None

        self.ui = Ui_AlgorithmWorkspaceReplayDialog()
        self.ui.setupUi(self)

        self.cmb_source_type = self.ui.cmbSourceType
        self.edt_source_name = self.ui.edtSourceName
        self.edt_file_path = self.ui.edtFilePath
        self.btn_browse = self.ui.btnBrowse
        self.chk_start_enabled = self.ui.chkStartEnabled
        self.dt_start_utc = self.ui.dtStartUtc
        self.chk_end_enabled = self.ui.chkEndEnabled
        self.dt_end_utc = self.ui.dtEndUtc
        self.cmb_source_timezone = self.ui.cmbSourceTimezone
        self.cmb_delimiter = self.ui.cmbDelimiter
        self.cmb_decimal_separator = self.ui.cmbDecimalSeparator
        self.cmb_source_timeframe = self.ui.cmbSourceTimeframe
        self.spn_spread = self.ui.spnSpread
        self.spn_initial_balance = self.ui.spnInitialBalance
        self.btn_save = self.ui.btnSave
        self.btn_cancel = self.ui.btnCancel

        self.dt_start_utc.setTimeSpec(Qt.TimeSpec.UTC)
        self.dt_end_utc.setTimeSpec(Qt.TimeSpec.UTC)

        self.btn_browse.clicked.connect(self._browse_csv)
        self.btn_save.clicked.connect(self._save)
        self.btn_cancel.clicked.connect(self.reject)
        self.cmb_source_type.currentIndexChanged.connect(
            self._refresh_source_controls
        )
        self.chk_start_enabled.toggled.connect(
            self.dt_start_utc.setEnabled
        )
        self.chk_end_enabled.toggled.connect(self.dt_end_utc.setEnabled)

        self._populate_choices()
        self._load_values(self._initial)
        self._load_detected_period_if_needed()
        self.apply_translation(workspace)
        self._refresh_source_controls()

    def replay_values(self) -> WorkspaceReplaySettings:
        """Return the current validated Replay-only settings."""
        start_utc = self._optional_datetime(
            self.chk_start_enabled.isChecked(),
            self.dt_start_utc.dateTime(),
        )
        end_utc = self._optional_datetime(
            self.chk_end_enabled.isChecked(),
            self.dt_end_utc.dateTime(),
        )
        return WorkspaceReplaySettings(
            source_type=str(self.cmb_source_type.currentData()),
            file_path=self.edt_file_path.text().strip() or None,
            start_utc=start_utc,
            end_utc=end_utc,
            source_timezone=self.cmb_source_timezone.currentText().strip(),
            delimiter=str(self.cmb_delimiter.currentData()),
            decimal_separator=str(
                self.cmb_decimal_separator.currentData()
            ),
            spread=self.spn_spread.value(),
            source_name=self.edt_source_name.text().strip(),
            source_timeframe=str(self.cmb_source_timeframe.currentData()),
            initial_balance=self.spn_initial_balance.value(),
            speed=self._initial.speed,
        )

    def set_csv_file_path(
        self,
        file_path: str | Path,
        *,
        detect_period: bool = True,
        update_source_name: bool = True,
    ) -> None:
        """Select one CSV and optionally detect its full UTC range."""
        path = Path(file_path).expanduser().resolve()
        self.edt_file_path.setText(str(path))
        if update_source_name:
            self.edt_source_name.setText(path.stem.upper())
        if detect_period:
            self._detect_csv_period(path)

    def apply_translation(self, workspace: AlgorithmWorkspace) -> None:
        """Apply fallback-backed labels without editing localization JSON."""
        self.setWindowTitle(
            self._tr(
                "AlgorithmWorkspaceReplayDialog.windowTitle",
                "Replay test settings",
            )
        )
        self.ui.lblWorkspace.setText(
            self._tr(
                "AlgorithmWorkspaceReplayDialog.workspace",
                "Workspace: {name}",
            ).format(name=workspace.display_name)
        )
        self.ui.grpSource.setTitle(
            self._tr(
                "AlgorithmWorkspaceReplayDialog.grpSource",
                "Replay source",
            )
        )
        self.ui.lblSourceType.setText(
            self._tr(
                "AlgorithmWorkspaceReplayDialog.lblSourceType",
                "Source type:",
            )
        )
        self.ui.lblSourceName.setText(
            self._tr(
                "AlgorithmWorkspaceReplayDialog.lblSourceName",
                "Source label:",
            )
        )
        self.ui.lblFilePath.setText(
            self._tr(
                "AlgorithmWorkspaceReplayDialog.lblFilePath",
                "Historical CSV file:",
            )
        )
        self.btn_browse.setText(
            self._tr(
                "AlgorithmWorkspaceReplayDialog.btnBrowse",
                "Browse...",
            )
        )
        self.ui.grpRange.setTitle(
            self._tr(
                "AlgorithmWorkspaceReplayDialog.grpRange",
                "Replay test period and source time zone",
            )
        )
        self.chk_start_enabled.setText(
            self._tr(
                "AlgorithmWorkspaceReplayDialog.chkStartEnabled",
                "Test start UTC:",
            )
        )
        self.chk_end_enabled.setText(
            self._tr(
                "AlgorithmWorkspaceReplayDialog.chkEndEnabled",
                "Test end UTC:",
            )
        )
        self.ui.lblSourceTimezone.setText(
            self._tr(
                "AlgorithmWorkspaceReplayDialog.lblSourceTimezone",
                "CSV source time zone:",
            )
        )
        self.ui.grpCsv.setTitle(
            self._tr(
                "AlgorithmWorkspaceReplayDialog.grpCsv",
                "CSV format and market values",
            )
        )
        self.ui.lblSourceTimeframe.setText(
            self._tr(
                "AlgorithmWorkspaceReplayDialog.lblSourceTimeframe",
                "CSV source timeframe (auto-detected):",
            )
        )
        self.ui.lblDelimiter.setText(
            self._tr(
                "AlgorithmWorkspaceReplayDialog.lblDelimiter",
                "Column separator:",
            )
        )
        self.ui.lblDecimalSeparator.setText(
            self._tr(
                "AlgorithmWorkspaceReplayDialog.lblDecimalSeparator",
                "Decimal separator:",
            )
        )
        self.ui.lblSpread.setText(
            self._tr(
                "AlgorithmWorkspaceReplayDialog.lblSpread",
                "Default spread:",
            )
        )
        self.ui.grpAccount.setTitle(
            self._tr(
                "AlgorithmWorkspaceReplayDialog.grpAccount",
                "Virtual Replay account",
            )
        )
        self.ui.lblInitialBalance.setText(
            self._tr(
                "AlgorithmWorkspaceReplayDialog.lblInitialBalance",
                "Initial Replay balance, USD:",
            )
        )
        self.ui.lblAccountNote.setText(
            self._tr(
                "AlgorithmWorkspaceReplayDialog.accountNote",
                "This balance exists only inside Replay. It is not linked "
                "to an IB or cTrader account and cannot create broker "
                "orders.",
            )
        )
        self.ui.lblNote.setText(
            self._tr(
                "AlgorithmWorkspaceReplayDialog.note",
                "The Replay test period filters accepted CSV rows. Naive "
                "CSV timestamps are interpreted in the selected source "
                "time zone.",
            )
        )
        self.btn_save.setText(
            self._tr(
                "AlgorithmWorkspaceReplayDialog.btnSave",
                "Save",
            )
        )
        self.btn_cancel.setText(
            self._tr(
                "AlgorithmWorkspaceReplayDialog.btnCancel",
                "Cancel",
            )
        )
        self._translate_choice_texts()

    def _populate_choices(self) -> None:
        self.cmb_source_type.addItem(
            WORKSPACE_REPLAY_SOURCE_SYNTHETIC,
            WORKSPACE_REPLAY_SOURCE_SYNTHETIC,
        )
        self.cmb_source_type.addItem(
            WORKSPACE_REPLAY_SOURCE_CSV,
            WORKSPACE_REPLAY_SOURCE_CSV,
        )
        strategy = get_timeframe(self._workspace.timeframe)
        for timeframe_name in list_enabled_timeframes():
            source = get_timeframe(timeframe_name)
            if source.minutes > strategy.minutes:
                continue
            if strategy.minutes % source.minutes != 0:
                continue
            self.cmb_source_timeframe.addItem(source.name, source.name)
        for timezone_name in WORKSPACE_HISTORY_TIMEZONE_CHOICES:
            self.cmb_source_timezone.addItem(timezone_name, timezone_name)
        for value in WORKSPACE_HISTORY_DELIMITERS:
            self.cmb_delimiter.addItem(value, value)
        for value in WORKSPACE_HISTORY_DECIMAL_SEPARATORS:
            self.cmb_decimal_separator.addItem(value, value)

    def _translate_choice_texts(self) -> None:
        source_labels = {
            WORKSPACE_REPLAY_SOURCE_SYNTHETIC: self._tr(
                "AlgorithmWorkspaceReplayDialog.sourceSynthetic",
                "Synthetic test data",
            ),
            WORKSPACE_REPLAY_SOURCE_CSV: self._tr(
                "AlgorithmWorkspaceReplayDialog.sourceCsv",
                "Historical CSV",
            ),
        }
        delimiter_labels = {
            "AUTO": self._tr(
                "AlgorithmWorkspaceReplayDialog.delimiterAuto",
                "Detect automatically",
            ),
            ",": self._tr(
                "AlgorithmWorkspaceReplayDialog.delimiterComma",
                "Comma (,)",
            ),
            ";": self._tr(
                "AlgorithmWorkspaceReplayDialog.delimiterSemicolon",
                "Semicolon (;)",
            ),
            "\t": self._tr(
                "AlgorithmWorkspaceReplayDialog.delimiterTab",
                "Tab",
            ),
            "|": self._tr(
                "AlgorithmWorkspaceReplayDialog.delimiterPipe",
                "Vertical bar (|)",
            ),
        }
        decimal_labels = {
            ".": self._tr(
                "AlgorithmWorkspaceReplayDialog.decimalDot",
                "Dot (.)",
            ),
            ",": self._tr(
                "AlgorithmWorkspaceReplayDialog.decimalComma",
                "Comma (,)",
            ),
        }
        self._apply_combo_labels(self.cmb_source_type, source_labels)
        self._apply_combo_labels(self.cmb_delimiter, delimiter_labels)
        self._apply_combo_labels(
            self.cmb_decimal_separator,
            decimal_labels,
        )

    def _load_values(self, values: WorkspaceReplaySettings) -> None:
        self._set_combo_by_data(self.cmb_source_type, values.source_type)
        self.edt_source_name.setText(values.source_name)
        self.edt_file_path.setText(values.file_path or "")
        self._set_combo_by_data(
            self.cmb_source_timeframe,
            values.source_timeframe or self._workspace.timeframe,
        )
        self._load_optional_datetime(
            self.chk_start_enabled,
            self.dt_start_utc,
            values.start_utc,
            datetime.now(UTC) - timedelta(days=30),
        )
        self._load_optional_datetime(
            self.chk_end_enabled,
            self.dt_end_utc,
            values.end_utc,
            datetime.now(UTC),
        )
        self.cmb_source_timezone.setCurrentText(values.source_timezone)
        self._set_combo_by_data(self.cmb_delimiter, values.delimiter)
        self._set_combo_by_data(
            self.cmb_decimal_separator,
            values.decimal_separator,
        )
        self.spn_spread.setValue(values.spread)
        self.spn_initial_balance.setValue(values.initial_balance)

    def _refresh_source_controls(self, _index: int = -1) -> None:
        is_csv = (
            self.cmb_source_type.currentData()
            == WORKSPACE_REPLAY_SOURCE_CSV
        )
        self.edt_file_path.setEnabled(is_csv)
        self.btn_browse.setEnabled(is_csv)
        self.ui.grpRange.setEnabled(is_csv)
        self.cmb_source_timeframe.setEnabled(is_csv)
        self.cmb_delimiter.setEnabled(is_csv)
        self.cmb_decimal_separator.setEnabled(is_csv)
        self.spn_spread.setEnabled(True)

    def _browse_csv(self) -> None:
        current_path = Path(self.edt_file_path.text().strip() or ".")
        start_dir = current_path.parent if current_path.suffix else current_path
        file_path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            self._tr(
                "AlgorithmWorkspaceReplayDialog.selectCsv",
                "Select historical CSV",
            ),
            str(start_dir),
            "CSV files (*.csv *.txt);;All files (*.*)",
        )
        if file_path:
            try:
                self.set_csv_file_path(file_path)
            except WorkspaceHistoryError as exc:
                self.edt_file_path.setText(file_path)
                QMessageBox.warning(self, "LGE", str(exc))

    def _load_detected_period_if_needed(self) -> None:
        if self._initial.source_type != WORKSPACE_REPLAY_SOURCE_CSV:
            return
        if not self._initial.file_path:
            return
        update_period = (
            self._initial.start_utc is None and self._initial.end_utc is None
        )
        try:
            self._detect_csv_metadata(
                Path(self._initial.file_path).expanduser().resolve(),
                update_period=update_period,
            )
        except WorkspaceHistoryError:
            return

    def _detect_csv_period(self, file_path: Path) -> None:
        self._detect_csv_metadata(file_path, update_period=True)

    def _detect_csv_metadata(
        self,
        file_path: Path,
        *,
        update_period: bool,
    ) -> WorkspaceHistoryRange:
        path = file_path.expanduser().resolve()
        source_timezone = self.cmb_source_timezone.currentText().strip()
        delimiter = str(self.cmb_delimiter.currentData())
        signature = (path, source_timezone, delimiter)
        if self._detected_history_signature == signature:
            detected = self._detected_history_range
        else:
            detected = self._history_loader.inspect_range(
                file_path=path,
                source_timezone=source_timezone,
                delimiter=delimiter,
            )
            self._detected_history_signature = signature
            self._detected_history_range = detected
        if detected is None:
            raise WorkspaceHistoryError("Historical CSV metadata is unavailable")

        self._apply_detected_source_timeframe(detected)
        if update_period:
            self._load_optional_datetime(
                self.chk_start_enabled,
                self.dt_start_utc,
                detected.first_timestamp.isoformat(),
                detected.first_timestamp,
            )
            self._load_optional_datetime(
                self.chk_end_enabled,
                self.dt_end_utc,
                detected.last_timestamp.isoformat(),
                detected.last_timestamp,
            )
        period_text = (
            f"{detected.first_timestamp.isoformat()} — "
            f"{detected.last_timestamp.isoformat()} "
            f"({detected.row_count})"
        )
        if detected.detected_timeframe is not None:
            period_text = (
                f"{period_text}; timeframe={detected.detected_timeframe} "
                "(auto)"
            )
        self.edt_file_path.setToolTip(period_text)
        return detected

    def _apply_detected_source_timeframe(
        self,
        detected: WorkspaceHistoryRange,
    ) -> None:
        timeframe = detected.detected_timeframe
        if timeframe is None:
            self.cmb_source_timeframe.setToolTip(
                self._tr(
                    "AlgorithmWorkspaceReplayDialog.sourceTimeframeManualFallback",
                    "The CSV timeframe could not be detected reliably. "
                    "Select it manually.",
                )
            )
            return
        index = self.cmb_source_timeframe.findData(timeframe)
        if index < 0:
            raise WorkspaceHistoryError(
                f"CSV source timeframe {timeframe} is incompatible with "
                f"WSP timeframe {self._workspace.timeframe}"
            )
        self.cmb_source_timeframe.setCurrentIndex(index)
        self.cmb_source_timeframe.setToolTip(
            self._tr(
                "AlgorithmWorkspaceReplayDialog.sourceTimeframeDetected",
                "Detected automatically from CSV timestamps: {timeframe}",
            ).format(timeframe=timeframe)
        )

    def _save(self) -> None:
        try:
            if (
                self.cmb_source_type.currentData()
                == WORKSPACE_REPLAY_SOURCE_CSV
            ):
                file_path = Path(self.edt_file_path.text().strip())
                self._detect_csv_metadata(file_path, update_period=False)
            values = self.replay_values()
            if values.source_type == WORKSPACE_REPLAY_SOURCE_CSV:
                values.require_existing_csv()
        except ValueError as exc:
            QMessageBox.warning(self, "LGE", str(exc))
            return
        self.accept()

    def _tr(self, key: str, fallback: str) -> str:
        if self._lang_mgr is None:
            return fallback
        return self._lang_mgr.tr(key, fallback)

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    @staticmethod
    def _apply_combo_labels(
        combo: QComboBox,
        labels: dict[str, str],
    ) -> None:
        for index in range(combo.count()):
            value = str(combo.itemData(index))
            if value in labels:
                combo.setItemText(index, labels[value])

    @staticmethod
    def _optional_datetime(
        enabled: bool,
        value: QDateTime,
    ) -> datetime | None:
        if not enabled:
            return None
        return datetime.fromtimestamp(value.toSecsSinceEpoch(), tz=UTC)

    @staticmethod
    def _load_optional_datetime(
        checkbox: QCheckBox,
        editor: QDateTimeEdit,
        value: str | None,
        default: datetime,
    ) -> None:
        normalized = datetime.fromisoformat(value) if value else default
        if normalized.tzinfo is None:
            normalized = normalized.replace(tzinfo=UTC)
        normalized = normalized.astimezone(UTC)
        editor.setDateTime(
            QDateTime.fromSecsSinceEpoch(
                int(normalized.timestamp()),
                QTimeZone.utc(),
            )
        )
        checkbox.setChecked(value is not None)
        editor.setEnabled(value is not None)
