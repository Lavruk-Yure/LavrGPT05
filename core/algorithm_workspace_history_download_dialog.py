# -*- coding: utf-8 -*-
"""Діалог завантаження broker history для одного algorithm WSP.

Designer-based UI не змінює Replay settings до явної дії користувача.
Broker-history pages відображають реальний прогрес і періодично віддають
Qt event loop можливість перемалювати індикатор.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
import time
from typing import Callable

from PySide6.QtCore import QDate, QEventLoop, Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QMessageBox,
    QWidget,
)

from core.algorithm_workspace import AlgorithmWorkspace
from core.lang_manager import LangManager
from core.workspace_history_download_settings import (
    WorkspaceHistoryDownloadSettings,
)
from core.workspace_history_export import (
    WorkspaceHistoryCsvExportResult,
    WorkspaceHistoryCsvWriter,
)
from engine.ctrader_history import CTraderHistoryProgressCallback
from engine.runtime_constants import WORKSPACE_HISTORY_TIMEZONE_CHOICES
from ui.ui_algorithm_workspace_history_download_dialog import (
    Ui_AlgorithmWorkspaceHistoryDownloadDialog,
)


def format_history_download_duration(value: float | None) -> str:
    """Format broker-history download duration for user-facing summaries."""
    if value is None:
        return "—"
    total_seconds = max(0, int(round(value)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:d}:{seconds:02d}"


class AlgorithmWorkspaceHistoryDownloadDialog(QDialog):
    """Download broker history without changing Replay test settings."""

    def __init__(
        self,
        workspace: AlgorithmWorkspace,
        lang_mgr: LangManager | None = None,
        parent: QWidget | None = None,
        history_download: Callable[
            [datetime, datetime, CTraderHistoryProgressCallback | None],
            WorkspaceHistoryCsvExportResult,
        ]
        | None = None,
        history_root: str | Path | None = None,
    ) -> None:
        super().__init__(parent)
        self._workspace = workspace
        self._lang_mgr = lang_mgr
        self._download = history_download
        self._writer = WorkspaceHistoryCsvWriter(history_root)
        self._initial = WorkspaceHistoryDownloadSettings.from_workspace(
            workspace
        )
        self._downloaded_result: WorkspaceHistoryCsvExportResult | None = None
        self._requested_period_utc: tuple[datetime, datetime] | None = None
        self._download_started_utc: datetime | None = None
        self._download_finished_utc: datetime | None = None
        self._download_elapsed_seconds: float | None = None
        self._use_for_replay = False

        self.ui = Ui_AlgorithmWorkspaceHistoryDownloadDialog()
        self.ui.setupUi(self)

        self.dt_start_date = self.ui.dtStartDate
        self.dt_end_date = self.ui.dtEndDate
        self.cmb_timezone = self.ui.cmbTimezone
        self.edt_planned_file = self.ui.edtPlannedFile
        self.edt_destination_folder = self.ui.edtDestinationFolder
        self.progress_download = self.ui.progressDownload
        self.lbl_status = self.ui.lblStatus
        self.btn_download = self.ui.btnDownload
        self.btn_use_for_replay = self.ui.btnUseForReplay
        self.btn_close = self.ui.btnClose

        self.dt_start_date.dateChanged.connect(self._refresh_planned_path)
        self.dt_end_date.dateChanged.connect(self._refresh_planned_path)
        self.cmb_timezone.currentTextChanged.connect(
            self._refresh_planned_path
        )
        self.btn_download.clicked.connect(self._download_history)
        self.btn_use_for_replay.clicked.connect(self._accept_for_replay)
        self.btn_close.clicked.connect(self.reject)

        self._populate_choices()
        self._load_values()
        self.apply_translation()
        self._refresh_planned_path()
        self._set_idle_progress()

    @property
    def downloaded_result(self) -> WorkspaceHistoryCsvExportResult | None:
        """Return the most recent successful download result."""
        return self._downloaded_result

    @property
    def use_for_replay_requested(self) -> bool:
        """Return whether the user explicitly selected Replay use."""
        return self._use_for_replay

    def history_values(self) -> WorkspaceHistoryDownloadSettings:
        """Return validated downloader-only settings from the form."""
        return WorkspaceHistoryDownloadSettings(
            broker=self._workspace.broker,
            account_id=self._workspace.account_id,
            symbol=self._workspace.symbol,
            timeframe=self._workspace.timeframe,
            start_date=self._date(self.dt_start_date.date()).isoformat(),
            end_date=self._date(self.dt_end_date.date()).isoformat(),
            timezone=self.cmb_timezone.currentText().strip(),
            destination_folder=self.edt_destination_folder.text().strip(),
        )

    def apply_translation(self) -> None:
        """Apply fallback-backed labels without editing strings.json."""
        self.setWindowTitle(
            self._tr(
                "AlgorithmWorkspaceHistoryDownloadDialog.windowTitle",
                "Historical data download",
            )
        )
        self.ui.lblWorkspace.setText(
            self._tr(
                "AlgorithmWorkspaceHistoryDownloadDialog.workspace",
                "Workspace: {name}",
            ).format(name=self._workspace.display_name)
        )
        self.ui.grpBinding.setTitle(
            self._tr(
                "AlgorithmWorkspaceHistoryDownloadDialog.grpBinding",
                "Broker data source",
            )
        )
        self.ui.lblBrokerCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoryDownloadDialog.lblBroker",
                "Broker:",
            )
        )
        self.ui.lblAccountCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoryDownloadDialog.lblAccount",
                "Account:",
            )
        )
        self.ui.lblSymbolCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoryDownloadDialog.lblSymbol",
                "Symbol:",
            )
        )
        self.ui.lblTimeframeCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoryDownloadDialog.lblTimeframe",
                "Timeframe:",
            )
        )
        self.ui.grpRange.setTitle(
            self._tr(
                "AlgorithmWorkspaceHistoryDownloadDialog.grpRange",
                "Download period",
            )
        )
        self.ui.lblStartDate.setText(
            self._tr(
                "AlgorithmWorkspaceHistoryDownloadDialog.lblStartDate",
                "Start date:",
            )
        )
        self.ui.lblEndDate.setText(
            self._tr(
                "AlgorithmWorkspaceHistoryDownloadDialog.lblEndDate",
                "End date:",
            )
        )
        self.ui.lblTimezone.setText(
            self._tr(
                "AlgorithmWorkspaceHistoryDownloadDialog.lblTimezone",
                "Download period time zone:",
            )
        )
        self.ui.grpDestination.setTitle(
            self._tr(
                "AlgorithmWorkspaceHistoryDownloadDialog.grpDestination",
                "CSV destination",
            )
        )
        self.ui.lblPlannedFile.setText(
            self._tr(
                "AlgorithmWorkspaceHistoryDownloadDialog.lblPlannedFile",
                "Planned CSV file:",
            )
        )
        self.ui.lblDestinationFolder.setText(
            self._tr(
                "AlgorithmWorkspaceHistoryDownloadDialog.lblDestinationFolder",
                "Destination folder:",
            )
        )
        self.ui.grpProgress.setTitle(
            self._tr(
                "AlgorithmWorkspaceHistoryDownloadDialog.grpProgress",
                "Download status",
            )
        )
        self.ui.lblNote.setText(
            self._tr(
                "AlgorithmWorkspaceHistoryDownloadDialog.note",
                "The requested dates define the broker query. The final CSV "
                "name uses the first and last bars actually returned.",
            )
        )
        self.btn_download.setText(
            self._tr(
                "AlgorithmWorkspaceHistoryDownloadDialog.btnDownload",
                "Download",
            )
        )
        self.btn_use_for_replay.setText(
            self._tr(
                "AlgorithmWorkspaceHistoryDownloadDialog.btnUseForReplay",
                "Use for Replay",
            )
        )
        self.btn_close.setText(
            self._tr(
                "AlgorithmWorkspaceHistoryDownloadDialog.btnClose",
                "Close",
            )
        )
        if self._downloaded_result is None:
            self.lbl_status.setText(
                self._tr(
                    "AlgorithmWorkspaceHistoryDownloadDialog.statusReady",
                    "Ready to download.",
                )
            )

    def _populate_choices(self) -> None:
        for timezone_name in WORKSPACE_HISTORY_TIMEZONE_CHOICES:
            self.cmb_timezone.addItem(timezone_name, timezone_name)

    def _load_values(self) -> None:
        today = datetime.now(UTC).date()
        start_date = self._stored_date(
            self._initial.start_date,
            today - timedelta(days=30),
        )
        end_date = self._stored_date(self._initial.end_date, today)
        self.dt_start_date.setDate(
            QDate(start_date.year, start_date.month, start_date.day)
        )
        self.dt_end_date.setDate(
            QDate(end_date.year, end_date.month, end_date.day)
        )
        self.cmb_timezone.setCurrentText(self._initial.timezone)
        self.ui.lblBroker.setText(self._workspace.broker)
        self.ui.lblAccount.setText(self._workspace.account_id or "—")
        self.ui.lblSymbol.setText(self._workspace.symbol)
        self.ui.lblTimeframe.setText(self._workspace.timeframe)

    def _refresh_planned_path(self, _value: object = None) -> None:
        start_date = self._date(self.dt_start_date.date())
        end_date = self._date(self.dt_end_date.date())
        if start_date > end_date:
            self.edt_planned_file.clear()
            self.edt_destination_folder.clear()
            return
        planned_path = self._writer.planned_file_path_for_dates(
            broker=self._workspace.broker,
            symbol=self._workspace.symbol,
            timeframe=self._workspace.timeframe,
            start_date=start_date,
            end_date=end_date,
        )
        self.edt_planned_file.setText(str(planned_path))
        self.edt_destination_folder.setText(str(planned_path.parent))
        self._downloaded_result = None
        self._use_for_replay = False
        self.btn_use_for_replay.setEnabled(False)
        self._set_idle_progress()

    def _download_history(self) -> None:
        if self._download is None:
            self._show_warning(
                self._tr(
                    "AlgorithmWorkspaceHistoryDownloadDialog.unavailable",
                    "Broker history download is not available.",
                )
            )
            return
        try:
            values = self.history_values()
            start_utc, end_utc = values.period_utc()
        except ValueError as exc:
            self._show_warning(str(exc))
            return

        self._requested_period_utc = (start_utc, end_utc)
        self._download_started_utc = datetime.now(UTC)
        started_monotonic = time.monotonic()
        self._download_finished_utc = None
        self._download_elapsed_seconds = None
        self._set_downloading_progress()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        exported: WorkspaceHistoryCsvExportResult | None = None
        error_text = ""
        try:
            exported = self._download(
                start_utc,
                end_utc,
                self._on_download_progress,
            )
        except Exception as exc:  # noqa: BLE001
            error_text = self._format_download_error(exc)
        finally:
            self._download_finished_utc = datetime.now(UTC)
            self._download_elapsed_seconds = max(
                0.0,
                time.monotonic() - started_monotonic,
            )
            QApplication.restoreOverrideCursor()
            QApplication.processEvents()

        if error_text:
            self._set_failed_progress(error_text)
            self._show_warning(error_text)
            return
        if exported is None:
            return

        self._downloaded_result = exported
        self.edt_planned_file.setText(str(exported.file_path))
        self.edt_destination_folder.setText(str(exported.file_path.parent))
        self.btn_use_for_replay.setEnabled(True)
        self._set_completed_progress(exported)
        self._show_completed(exported)

    def _accept_for_replay(self) -> None:
        if self._downloaded_result is None:
            return
        self._use_for_replay = True
        self.accept()

    def _set_idle_progress(self) -> None:
        self.progress_download.setRange(0, 1)
        self.progress_download.setValue(0)
        self.btn_download.setEnabled(self._download is not None)
        if self._downloaded_result is None:
            self.lbl_status.setText(
                self._tr(
                    "AlgorithmWorkspaceHistoryDownloadDialog.statusReady",
                    "Ready to download.",
                )
            )

    def _set_downloading_progress(self) -> None:
        self.progress_download.setRange(0, 100)
        self.progress_download.setValue(0)
        self.btn_download.setEnabled(False)
        self.btn_use_for_replay.setEnabled(False)
        self.btn_close.setEnabled(False)
        self.lbl_status.setText(
            self._tr(
                "AlgorithmWorkspaceHistoryDownloadDialog.statusDownloading",
                "Downloading historical data from {broker}...",
            ).format(broker=self._workspace.broker)
        )

    def _on_download_progress(
        self,
        request_count: int,
        bar_count: int,
        covered_start: datetime | None,
    ) -> None:
        """Оновити determinate progress після завершеного broker page."""
        period = self._requested_period_utc
        if period is None or covered_start is None:
            return
        start_utc, end_utc = period
        total_seconds = max(1.0, (end_utc - start_utc).total_seconds())
        covered_seconds = (end_utc - covered_start).total_seconds()
        percent = int(covered_seconds * 100.0 / total_seconds)
        percent = max(1, min(99, percent))
        self.progress_download.setValue(percent)
        self.lbl_status.setText(
            self._tr(
                "AlgorithmWorkspaceHistoryDownloadDialog.statusProgress",
                "Downloading: {percent}% · requests {requests} · bars {bars} · "
                "earliest bar {covered_start} UTC",
            ).format(
                percent=percent,
                requests=request_count,
                bars=bar_count,
                covered_start=covered_start.astimezone(UTC).strftime(
                    "%Y-%m-%d %H:%M"
                ),
            )
        )
        QApplication.processEvents(
            QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
        )

    def _set_completed_progress(
        self,
        exported: WorkspaceHistoryCsvExportResult,
    ) -> None:
        self.progress_download.setRange(0, 1)
        self.progress_download.setValue(1)
        self.btn_download.setEnabled(True)
        self.btn_close.setEnabled(True)
        self.lbl_status.setText(
            self._tr(
                "AlgorithmWorkspaceHistoryDownloadDialog.statusCompleted",
                "Completed: {bars} bars in {requests} requests, "
                "{first} — {last}.",
            ).format(
                bars=exported.bar_count,
                requests=exported.request_count,
                first=exported.first_timestamp.isoformat(),
                last=exported.last_timestamp.isoformat(),
            )
        )

    def _set_failed_progress(self, error_text: str) -> None:
        self.progress_download.setRange(0, 1)
        self.progress_download.setValue(0)
        self.btn_download.setEnabled(True)
        self.btn_close.setEnabled(True)
        self.lbl_status.setText(error_text)

    def _show_completed(
        self,
        exported: WorkspaceHistoryCsvExportResult,
    ) -> None:
        self._show_message(
            QMessageBox.Icon.Information,
            self._tr(
                "AlgorithmWorkspaceHistoryDownloadDialog.completedTitle",
                "History download completed",
            ),
            self._completed_message(exported),
        )

    def _completed_message(
        self,
        exported: WorkspaceHistoryCsvExportResult,
    ) -> str:
        requested_start = "—"
        requested_end = "—"
        coverage_note = ""
        if self._requested_period_utc is not None:
            start_utc, end_utc = self._requested_period_utc
            requested_start = start_utc.isoformat()
            requested_end = end_utc.isoformat()
            if exported.first_timestamp > start_utc:
                coverage_note = "\n\n" + self._tr(
                    "AlgorithmWorkspaceHistoryDownloadDialog.coverageStartsLater",
                    "The broker returned no bars between the requested start "
                    "and the first actual bar. This is normal for weekends, "
                    "holidays, market closures, or unavailable broker history.",
                )

        started = self._format_download_time_utc(self._download_started_utc)
        finished = self._format_download_time_utc(
            self._download_finished_utc
        )
        duration = format_history_download_duration(
            self._download_elapsed_seconds
        )

        return self._tr(
            "AlgorithmWorkspaceHistoryDownloadDialog.completed",
            "Historical CSV saved: {file}\n\n"
            "Bars: {bars}\nRequests: {requests}\n"
            "Download started: {download_started}\n"
            "Download finished: {download_finished}\n"
            "Download duration: {download_duration}\n"
            "Requested period: {requested_first} — {requested_last}\n"
            "Actual period: {first} — {last}{coverage_note}",
        ).format(
            file=str(exported.file_path),
            bars=exported.bar_count,
            requests=exported.request_count,
            download_started=started,
            download_finished=finished,
            download_duration=duration,
            requested_first=requested_start,
            requested_last=requested_end,
            first=exported.first_timestamp.isoformat(),
            last=exported.last_timestamp.isoformat(),
            coverage_note=coverage_note,
        )

    @staticmethod
    def _format_download_time_utc(value: datetime | None) -> str:
        if value is None:
            return "—"
        return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    def _show_warning(self, text: str) -> None:
        self._show_message(
            QMessageBox.Icon.Warning,
            self._tr(
                "AlgorithmWorkspaceHistoryDownloadDialog.failedTitle",
                "History download failed",
            ),
            text,
        )

    def _show_message(
        self,
        icon: QMessageBox.Icon,
        title: str,
        text: str,
    ) -> None:
        message = QMessageBox(self)
        message.setIcon(icon)
        message.setWindowTitle(title)
        message.setText(text)
        message.setStandardButtons(QMessageBox.StandardButton.Ok)
        ok_button = message.button(QMessageBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText(
                self._tr(
                    "AlgorithmWorkspaceHistoryDownloadDialog.messageOk",
                    "OK",
                )
            )
        message.exec()

    def _format_download_error(self, error: Exception) -> str:
        details = str(error).strip() or error.__class__.__name__
        if "IB historical data error 10314" in details:
            return self._tr(
                "AlgorithmWorkspaceHistoryDownloadDialog.ibInvalidEndDateTime",
                "IB rejected the request because the end date or time "
                "format is invalid.\n\nTechnical details: {details}",
            ).format(details=details)
        return self._tr(
            "AlgorithmWorkspaceHistoryDownloadDialog.failed",
            "Historical data could not be downloaded.\n\n"
            "Technical details: {details}",
        ).format(details=details)

    def _tr(self, key: str, fallback: str) -> str:
        if self._lang_mgr is None:
            return fallback
        return self._lang_mgr.tr(key, fallback)

    @staticmethod
    def _date(value: QDate) -> date:
        return date(value.year(), value.month(), value.day())

    @staticmethod
    def _stored_date(value: str | None, default: date) -> date:
        if value is None or value == "":
            return default
        return date.fromisoformat(str(value))
