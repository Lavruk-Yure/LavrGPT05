"""Синтетична UI-перевірка MDI AlgorithmWorkspaceArea.

Перевіряє WSP create/restore, geometry, modes, dialog bindings та відсутність
неочікуваних broker-history викликів у UI-only сценаріях.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import (  # noqa: E402
    QDate,
    QDateTime,
    QRect,
    QTimeZone,
)
from PySide6.QtWidgets import QApplication  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_DEMO,
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    WORKSPACE_PANEL_CHART,
    WORKSPACE_PANEL_POSITION,
    WORKSPACE_STATE_RUNNING,
    WORKSPACE_STATE_STARTING,
    WORKSPACE_STATE_STOPPED,
)
from core.algorithm_workspace_area import (  # noqa: E402
    ORDER_TABLE_COLUMNS,
    POSITION_TABLE_COLUMNS,
    SIGNAL_TABLE_COLUMNS,
    AlgorithmWorkspaceArea,
    AlgorithmWorkspaceWindow,
)
from core.algorithm_workspace_controller import (  # noqa: E402
    AlgorithmWorkspaceController,
)
from core.algorithm_workspace_history_download_dialog import (  # noqa: E402
    AlgorithmWorkspaceHistoryDownloadDialog,
)
from core.algorithm_workspace_parameters_dialog import (  # noqa: E402
    AlgorithmWorkspaceParametersDialog,
)
from core.algorithm_workspace_replay_dialog import (  # noqa: E402
    AlgorithmWorkspaceReplayDialog,
)
from core.session_repository import SessionRepository  # noqa: E402
from core.workspace_algorithm import (  # noqa: E402
    WorkspaceAlgorithm,
    WorkspaceSignalOutput,
)
from core.workspace_history_export import (  # noqa: E402
    WorkspaceHistoryCsvExportResult,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_parameters import (  # noqa: E402
    WorkspaceAlgorithmParameters,
)
from core.workspace_replay import (  # noqa: E402
    REPLAY_SPEED_MAX,
    REPLAY_SPEED_MAX_FAST,
    REPLAY_SPEEDS,
)
from core.workspace_replay_settings import (  # noqa: E402
    WorkspaceReplaySettings,
)
from core.workspace_runtime import (  # noqa: E402
    WORKSPACE_STARTUP_PHASE_IDLE,
    WORKSPACE_STARTUP_PHASE_WAIT_BROKER,
    WorkspaceRuntimeContext,
    WorkspaceRuntimeError,
)
from core.workspace_signal import WorkspaceSignalProposal  # noqa: E402
from engine.ctrader_history import CTraderHistoryProgressCallback  # noqa: E402
from engine.runtime_account_state import RuntimeAccountState  # noqa: E402


class AreaSignalAlgorithm(WorkspaceAlgorithm):
    def __init__(self) -> None:
        self.context: WorkspaceRuntimeContext | None = None
        self.parameters: dict[str, Any] = {}
        self.started = False

    def configure(
        self,
        context: WorkspaceRuntimeContext,
        parameters: Mapping[str, Any],
    ) -> None:
        self.context = context
        self.parameters = dict(parameters)

    def start(self) -> None:
        assert self.context is not None
        self.started = True

    def on_market_event(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalOutput:
        assert self.started
        return WorkspaceSignalProposal(
            signal_type="UI_TEST",
            direction="BUY",
            strength=0.80,
            macd_state="LINEAR_UP",
            alligator_confirmation="SAME_TIMEFRAME",
        )

    def on_order_event(self, event: object) -> None:
        _ = event
        assert self.started

    def stop(self) -> None:
        self.started = False


class FakeIbService:
    @staticmethod
    def get_managed_accounts() -> list[str]:
        return ["DUM513747"]

    @staticmethod
    def get_account_state() -> RuntimeAccountState:
        return RuntimeAccountState(
            account_id="DUM513747",
            broker_name="IB",
            currency="USD",
            balance=125000.50,
        )


class FakeCtraderService:
    @staticmethod
    def get_account_list() -> list[dict]:
        return [
            {
                "account_id": "123456",
                "trader_login": "demo-login",
                "account_mode": "DEMO",
            }
        ]

    @staticmethod
    def get_account_state() -> RuntimeAccountState:
        return RuntimeAccountState(
            account_id="123456",
            broker_name="CTRADER",
            currency="USD",
            balance=2500.75,
        )


def _unused_history_download(
    start_utc: datetime,
    end_utc: datetime,
    progress_callback: CTraderHistoryProgressCallback | None = None,
) -> WorkspaceHistoryCsvExportResult:
    """Завершити тест помилкою при неочікуваному broker download."""
    _ = start_utc, end_utc, progress_callback
    raise AssertionError("History download must not run in the area check")


def main() -> None:
    """Check MDI create, geometry, modes, start/stop, lock and restore."""
    app = QApplication.instance() or QApplication([])

    with TemporaryDirectory() as temp_dir:
        history_path = Path(temp_dir) / "eurusd_m15_dialog.csv"
        history_path.write_text(
            "timestamp,open,high,low,close,volume\n"
            "2026-07-20T08:00:00Z,1.1700,1.1710,1.1695,1.1705,100\n"
            "2026-07-20T08:15:00Z,1.1705,1.1715,1.1700,1.1710,110\n"
            "2026-07-20T08:30:00Z,1.1710,1.1720,1.1705,1.1715,120\n",
            encoding="utf-8",
        )
        repository = SessionRepository(Path(temp_dir) / "Session")
        controller = AlgorithmWorkspaceController(
            repository,
            algorithm_factory=lambda _algorithm_id: AreaSignalAlgorithm(),
        )
        area = AlgorithmWorkspaceArea(controller=controller)
        area.set_runtime_engine(
            SimpleNamespace(
                ib_runtime_service=FakeIbService(),
                ctrader_runtime_service=FakeCtraderService(),
            )
        )
        area.resize(1280, 820)
        area.show()
        app.processEvents()

        assert area.workspace_count() == 0
        assert area.stack_workspace_state.currentWidget() is area.ui.pageEmpty

        workspace = area.create_workspace(
            broker="IB",
            account_id="DUM513747",
            account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
            symbol="EURUSD",
            timeframe="M15",
            algorithm="RailAlgorithm",
            data_mode=WORKSPACE_DATA_MODE_REPLAY,
            control_mode=WORKSPACE_CONTROL_MODE_AUTO,
            parameters={
                "warmup_bars": 2,
                "spread_limit": 0.00020,
            },
            replay_settings={"speed": 2},
        )
        app.processEvents()

        assert area.workspace_count() == 1
        assert area.current_workspace_uid() == workspace.workspace_uid
        assert area.stack_workspace_state.currentWidget() is area.ui.pageMdi

        window = area.workspace_window(workspace.workspace_uid)
        subwindow = area.workspace_subwindow(workspace.workspace_uid)
        assert isinstance(window, AlgorithmWorkspaceWindow)
        assert subwindow is not None
        assert window.cmb_data_mode.currentData() == WORKSPACE_DATA_MODE_REPLAY
        assert window.cmb_control_mode.currentData() == WORKSPACE_CONTROL_MODE_AUTO
        assert window.ui.lblAccount.text() == "Virtual Replay account"
        assert window.ui.lblBalance.text() == "1 000.00 USD"
        assert window.ui.lblCurrentProfitCaption.text() == "Closed PnL:"
        assert window.ui.lblPeakProfitCaption.text() == "Replay balance:"
        assert window.ui.lblProfitDrawdownCaption.text() == "Replay equity:"
        assert window.btn_parameters.isEnabled()
        assert window.btn_replay_settings.isVisible()
        assert window.btn_replay_settings.isEnabled()
        assert window.property("activeWorkspace") is True
        assert not hasattr(window.ui, "lblActive")
        active_badge_text_removed = True
        assert window.ui.lblState.minimumWidth() >= 104
        polish_runtime_state_fits = True

        window.set_runtime_status(
            WORKSPACE_STATE_STARTING,
            WORKSPACE_STARTUP_PHASE_WAIT_BROKER,
        )
        assert window.ui.lblState.text() == "WAIT_BROKER"
        wait_broker_badge_visible = True
        window.set_runtime_status(
            WORKSPACE_STATE_STOPPED,
            WORKSPACE_STARTUP_PHASE_IDLE,
        )

        preview_history_root = Path(temp_dir) / "history_preview"
        assert window.btn_history_download.isVisible()
        assert window.btn_history_download.isEnabled()

        history_dialog = AlgorithmWorkspaceHistoryDownloadDialog(
            repository.load_workspace(workspace.workspace_uid),
            history_download=_unused_history_download,
            history_root=preview_history_root,
        )
        assert history_dialog.ui.btnDownload is history_dialog.btn_download
        assert history_dialog.btn_download.isEnabled()
        assert not history_dialog.btn_use_for_replay.isEnabled()
        history_dialog.dt_start_date.setDate(QDate(2026, 1, 1))
        history_dialog.dt_end_date.setDate(QDate(2026, 7, 27))
        planned_ib_path = Path(history_dialog.edt_planned_file.text())
        assert (
            planned_ib_path.parent
            == (preview_history_root / "IB" / "EURUSD" / "M15").resolve()
        )
        expected_ib_name = "2026-01-01_2026-07-27_IB_EURUSD_M15.csv"
        assert planned_ib_path.name == expected_ib_name
        assert history_dialog.edt_destination_folder.text() == str(
            planned_ib_path.parent
        )
        assert planned_ib_path.parent.is_dir()
        assert not planned_ib_path.exists()
        history_dialog.cmb_timezone.setCurrentText("Europe/Kyiv")
        history_values = history_dialog.history_values()
        assert history_values.start_date == "2026-01-01"
        assert history_values.end_date == "2026-07-27"
        assert history_values.timezone == "Europe/Kyiv"
        download_start_utc, download_end_utc = history_values.period_utc()
        expected_download_start = "2025-12-31T22:00:00+00:00"
        expected_download_end = "2026-07-27T20:59:59+00:00"
        assert download_start_utc.isoformat() == expected_download_start
        assert download_end_utc.isoformat() == expected_download_end
        history_dialog.close()
        history_download_dialog_designer_ui = True
        planned_name_updates_immediately = True
        download_timezone_connected = True
        broker_history_defaults_prefilled = True
        ib_history_download_dialog_connected = True

        replay_dialog = AlgorithmWorkspaceReplayDialog(
            repository.load_workspace(workspace.workspace_uid),
        )
        assert replay_dialog.cmb_source_type.currentData() == "SYNTHETIC"
        assert not hasattr(replay_dialog.ui, "grpDownloadRange")
        assert not hasattr(replay_dialog.ui, "btnDownloadIb")
        assert replay_dialog.cmb_source_type is replay_dialog.ui.cmbSourceType
        assert replay_dialog.btn_save is replay_dialog.ui.btnSave
        assert replay_dialog.btn_save.isDefault()
        assert not replay_dialog.ui.grpRange.isEnabled()
        csv_index = replay_dialog.cmb_source_type.findData("CSV")
        assert csv_index >= 0
        replay_dialog.cmb_source_type.setCurrentIndex(csv_index)
        replay_dialog.set_csv_file_path(history_path)
        assert replay_dialog.chk_start_enabled.isChecked()
        assert replay_dialog.chk_end_enabled.isChecked()
        assert replay_dialog.dt_start_utc.dateTime().toSecsSinceEpoch() == int(
            datetime(2026, 7, 20, 8, 0, tzinfo=UTC).timestamp()
        )
        assert replay_dialog.dt_end_utc.dateTime().toSecsSinceEpoch() == int(
            datetime(2026, 7, 20, 8, 30, tzinfo=UTC).timestamp()
        )
        assert replay_dialog.edt_source_name.text() == "EURUSD_M15_DIALOG"
        assert replay_dialog.spn_initial_balance.minimum() == 100.0
        assert replay_dialog.spn_initial_balance.maximum() == 100_000.0
        assert replay_dialog.spn_initial_balance.value() == 1_000.0
        replay_dialog.spn_initial_balance.setValue(2_500.0)
        replay_dialog.chk_start_enabled.setChecked(True)
        replay_dialog.dt_start_utc.setDateTime(
            QDateTime.fromSecsSinceEpoch(
                int(datetime(2026, 7, 20, 8, 15, tzinfo=UTC).timestamp()),
                QTimeZone.utc(),
            )
        )
        replay_dialog.chk_end_enabled.setChecked(True)
        replay_dialog.dt_end_utc.setDateTime(
            QDateTime.fromSecsSinceEpoch(
                int(datetime(2026, 7, 20, 8, 30, tzinfo=UTC).timestamp()),
                QTimeZone.utc(),
            )
        )
        dialog_values = replay_dialog.replay_values()
        assert dialog_values.start_utc == "2026-07-20T08:15:00+00:00"
        assert dialog_values.end_utc == "2026-07-20T08:30:00+00:00"
        assert dialog_values.initial_balance == 2_500.0
        replay_csv_period_detected = True
        independent_replay_periods = True
        separate_history_and_replay_dialogs = True
        replay_dialog.close()

        csv_replay_values = WorkspaceReplaySettings(
            source_type="CSV",
            file_path=str(history_path),
            spread=0.00012,
            source_name="AREA_CSV",
            initial_balance=2_500.0,
            speed=2,
        )
        area.update_workspace_replay_settings(
            workspace.workspace_uid,
            csv_replay_values,
        )
        app.processEvents()
        assert window.property("replayConfigured") is True
        assert window.lbl_name.property("replayConfigured") is True
        assert window.btn_replay_settings.property("replayConfigured") is True
        assert "AREA_CSV" in window.btn_replay_settings.toolTip()
        assert window.ui.lblAccount.text() == "Virtual Replay account"
        assert window.ui.lblBalance.text() == "2 500.00 USD"
        replay_configured_indicator = True

        replay_values = WorkspaceReplaySettings(
            source_type="SYNTHETIC",
            spread=0.00012,
            source_name="AREA_SYNTHETIC",
            speed=2,
        )
        replay_workspace = area.update_workspace_replay_settings(
            workspace.workspace_uid,
            replay_values,
        )
        assert replay_workspace.replay_settings["source"] == "AREA_SYNTHETIC"
        assert replay_workspace.replay_settings["speed"] == 2
        assert window.property("replayConfigured") is False

        parameter_dialog = AlgorithmWorkspaceParametersDialog(
            repository.load_workspace(workspace.workspace_uid)
        )
        legacy_values = parameter_dialog.parameter_values()
        assert legacy_values.macd_signal_mode == "LINEAR"
        assert legacy_values.alligator_confirmation == "SAME_TIMEFRAME"
        assert legacy_values.warmup_bars == 2
        assert legacy_values.spread_limit == 0.00020
        assert parameter_dialog.tree_parameters is parameter_dialog.ui.treeParameters
        assert parameter_dialog.btn_save is parameter_dialog.ui.btnSave
        assert parameter_dialog.btn_save.isDefault()
        parameter_dialog.accept()

        parameter_values = WorkspaceAlgorithmParameters(
            macd_signal_mode="EXTENDED",
            alligator_confirmation="HIGHER_1",
            spread_limit=0.00020,
            warmup_bars=2,
            risk_percent=0.75,
            maximum_position_volume=2500,
            profit_drawdown_close_percent=25.0,
        )
        updated_workspace = area.update_workspace_parameters(
            workspace.workspace_uid,
            parameter_values,
        )
        assert updated_workspace.parameters["macd_signal_mode"] == "EXTENDED"
        assert updated_workspace.parameters["alligator_confirmation"] == "HIGHER_1"
        assert updated_workspace.risk_settings["risk_percent"] == 0.75
        assert updated_workspace.risk_settings["maximum_position_volume"] == 2500.0
        assert (
            updated_workspace.profit_protection["max_profit_drawdown_percent"] == 25.0
        )

        renamed = area.rename_workspace(
            workspace.workspace_uid,
            "EURUSD Rails M15",
        )
        assert renamed.display_name == "EURUSD Rails M15"
        assert subwindow.windowTitle() == "EURUSD Rails M15"
        assert not subwindow.toolTip()
        assert window.lbl_name.toolTip() == "EURUSD Rails M15"

        requested_geometry = QRect(75, 65, 780, 510)
        subwindow.setGeometry(requested_geometry)
        chart_index = window.tabs_workspace.indexOf(window.ui.tabChart)
        assert chart_index >= 0
        window.tabs_workspace.setCurrentIndex(chart_index)
        app.processEvents()
        area.flush_pending_ui_state()

        stored = repository.load_workspace(workspace.workspace_uid)
        assert stored.ui_state["active_panel"] == WORKSPACE_PANEL_CHART
        assert stored.ui_state["geometry"]["x"] == requested_geometry.x()
        assert stored.ui_state["geometry"]["y"] == requested_geometry.y()

        window.btn_start_stop.click()
        assert window.runtime_state == WORKSPACE_STATE_STARTING
        assert not window.btn_rename.isEnabled()
        assert not window.btn_parameters.isEnabled()
        assert not window.btn_replay_settings.isEnabled()
        active_replay_settings_edit_blocked = False
        try:
            controller.update_workspace_replay_settings(
                workspace.workspace_uid,
                replay_values,
            )
        except WorkspaceRuntimeError:
            active_replay_settings_edit_blocked = True
        assert active_replay_settings_edit_blocked
        active_parameter_edit_blocked = False
        try:
            controller.update_workspace_parameters(
                workspace.workspace_uid,
                parameter_values,
            )
        except WorkspaceRuntimeError:
            active_parameter_edit_blocked = True
        assert active_parameter_edit_blocked
        runtime = controller.workspace_runtime(workspace.workspace_uid)
        assert runtime is not None
        assert runtime.replay_session is None

        app.processEvents()
        assert runtime.replay_session is not None
        runtime_log = window.ui.txtLog.toPlainText()
        assert "SESSION_STARTED" in runtime_log
        assert "WARMUP" in runtime_log
        assert window.cmb_journal_category.count() == 7
        assert window.cmb_journal_level.count() == 4
        assert not window.chk_journal_market_ticks.isChecked()

        area.advance_replay_runtimes()
        app.processEvents()
        assert window.runtime_state == WORKSPACE_STATE_RUNNING
        assert runtime.can_form_signal()
        assert "RUNNING" in window.ui.lblReplayStatus.text()
        signals = runtime.signal_records()
        assert len(signals) >= 2
        assert any(not signal.accepted for signal in signals)
        assert any(signal.accepted for signal in signals)
        assert window.tbl_signals.columnCount() == len(SIGNAL_TABLE_COLUMNS)
        assert window.tbl_signals.rowCount() == len(signals)
        signals_index = window.tabs_workspace.indexOf(window.ui.tabSignals)
        assert signals_index >= 0
        window.tabs_workspace.setCurrentIndex(signals_index)
        app.processEvents()
        assert not window.tbl_signals.isHidden()
        assert window.ui.lblSignalsPlaceholder.isHidden()
        assert window.tbl_signals.item(0, 1).text() == "UI_TEST"
        chart_snapshot = runtime.chart_snapshot()
        assert chart_snapshot.total_events == runtime.context.market_event_count
        assert chart_snapshot.total_events >= 2
        assert window.chart_widget.snapshot == chart_snapshot
        window.tabs_workspace.setCurrentIndex(chart_index)
        app.processEvents()
        assert not window.chart_widget.isHidden()
        assert window.ui.lblChartPlaceholder.isHidden()
        assert "close" in window.chart_widget.lbl_status.text()
        assert "spread" in window.chart_widget.lbl_status.text()

        window.ui.btnReplayPause.click()
        app.processEvents()
        assert runtime.replay_session.paused
        paused_index = runtime.replay_session.index

        window.ui.btnReplayStep.click()
        app.processEvents()
        assert runtime.replay_session.index == paused_index + 1

        replay_speed_values = tuple(
            window.ui.cmbReplaySpeed.itemData(index)
            for index in range(window.ui.cmbReplaySpeed.count())
        )
        assert replay_speed_values == tuple(str(speed) for speed in REPLAY_SPEEDS)
        max_speed_index = window.ui.cmbReplaySpeed.findData(str(REPLAY_SPEED_MAX))
        assert max_speed_index >= 0
        assert window.ui.cmbReplaySpeed.itemText(max_speed_index) == "MAX"
        max_fast_speed_index = window.ui.cmbReplaySpeed.findData(
            str(REPLAY_SPEED_MAX_FAST)
        )
        assert max_fast_speed_index >= 0
        assert window.ui.cmbReplaySpeed.itemText(max_fast_speed_index) == "MAX FAST"

        speed_index = window.ui.cmbReplaySpeed.findData("5")
        assert speed_index >= 0
        window.ui.cmbReplaySpeed.setCurrentIndex(speed_index)
        app.processEvents()
        assert runtime.replay_session.speed == 5

        window.ui.btnReplayPause.click()
        app.processEvents()
        assert not runtime.replay_session.paused

        area.advance_replay_runtimes()
        area.advance_replay_runtimes()
        app.processEvents()
        window.chart_widget.visible_count_requested.emit(12)
        app.processEvents()
        zoomed_chart = runtime.chart_snapshot()
        assert zoomed_chart.visible_count == 12
        assert zoomed_chart.total_events > zoomed_chart.visible_count
        assert window.chart_widget.scrollbar.maximum() > 0

        window.chart_widget.visible_start_requested.emit(0)
        app.processEvents()
        scrolled_chart = runtime.chart_snapshot()
        assert scrolled_chart.visible_start == 0
        assert not scrolled_chart.at_latest

        window.chart_widget.btn_latest.click()
        app.processEvents()
        latest_chart = runtime.chart_snapshot()
        assert latest_chart.at_latest
        assert latest_chart.visible_end == latest_chart.total_events
        assert window.chart_widget.snapshot == latest_chart

        can_close_running, _reason = area.can_close_workspace(workspace.workspace_uid)
        assert not can_close_running

        window.btn_start_stop.click()
        app.processEvents()
        assert window.runtime_state == WORKSPACE_STATE_STOPPED
        assert window.btn_parameters.isEnabled()
        assert window.btn_replay_settings.isEnabled()

        owned_snapshot = area.set_workspace_owned_snapshots(
            workspace.workspace_uid,
            order_rows=[
                {
                    "workspace_uid": workspace.workspace_uid,
                    "broker": "IB",
                    "account_id": "DUM513747",
                    "symbol": "EURUSD",
                    "order_id": "ORDER-1",
                    "broker_order_id": "501",
                    "side": "BUY",
                    "order_type": "LIMIT",
                    "volume": 1000,
                    "price": 1.1380,
                    "stop_loss": 1.1350,
                    "take_profit": 1.1440,
                    "status": "WORKING",
                    "created_at": "2026-07-25T08:00:00Z",
                    "profit": 0.0,
                },
                {
                    "workspace_uid": workspace.workspace_uid,
                    "broker": "IB",
                    "account_id": "DUM513747",
                    "symbol": "EURUSD",
                    "order_id": "ORDER-2",
                    "broker_order_id": "502",
                    "side": "SELL",
                    "order_type": "MARKET",
                    "volume": 1000,
                    "price": 1.1400,
                    "status": "FILLED",
                    "created_at": "2026-07-25T08:15:00Z",
                    "profit": 12.5,
                },
            ],
            position_rows=[
                {
                    "workspace_uid": workspace.workspace_uid,
                    "broker": "IB",
                    "account_id": "DUM513747",
                    "symbol": "EURUSD",
                    "position_id": "POSITION-1",
                    "broker_position_id": "IB:DUM513747:EURUSD:LEG-1",
                    "side": "BUY",
                    "volume": 1000,
                    "entry_price": 1.1380,
                    "current_price": 1.1389,
                    "current_profit": 69.0,
                    "peak_profit": 100.0,
                    "stop_loss": 1.1350,
                    "take_profit": 1.1440,
                    "opened_at": "2026-07-25T08:00:00Z",
                    "reconciliation_status": "RECONCILED",
                },
                {
                    "workspace_uid": workspace.workspace_uid,
                    "broker": "IB",
                    "account_id": "DUM513747",
                    "symbol": "EURUSD",
                    "position_id": "POSITION-CLOSED",
                    "side": "SELL",
                    "volume": 0,
                    "current_profit": 10.0,
                    "peak_profit": 10.0,
                    "reconciliation_status": "CLOSED",
                },
            ],
        )
        assert len(owned_snapshot.orders) == 2
        assert len(owned_snapshot.positions) == 2
        assert window.tbl_orders.columnCount() == len(ORDER_TABLE_COLUMNS)
        assert window.tbl_orders.rowCount() == 2
        assert window.tbl_orders.item(0, 0).text() == "ORDER-1"
        assert window.tbl_orders.item(0, 1).text() == "501"
        assert window.tbl_orders.item(0, 4).text() == "1 000"
        assert window.tbl_orders.item(1, 11).text() == "+12.50"
        assert window.tbl_positions.columnCount() == len(POSITION_TABLE_COLUMNS)
        assert window.tbl_positions.rowCount() == 2
        assert window.tbl_positions.item(0, 0).text() == "BUY"
        assert window.tbl_positions.item(0, 4).text() == "+69.00"
        assert window.tbl_positions.item(0, 6).text() == "31.0%"
        assert "RECONCILED" in window.tbl_positions.item(0, 11).toolTip()
        position_index = window.tabs_workspace.indexOf(window.ui.tabPosition)
        assert position_index >= 0
        window.tabs_workspace.setCurrentIndex(position_index)
        app.processEvents()
        assert not window.tbl_positions.isHidden()
        assert window.ui.lblPositionPlaceholder.isHidden()
        assert window.ui.lblOrdersCount.text() == "1"
        assert window.ui.lblPositionsCount.text() == "1"
        assert window.ui.lblCurrentProfit.text() == "+0.00"
        assert window.ui.lblPeakProfit.text() == "1 000.00 USD"
        assert window.ui.lblProfitDrawdown.text() == "1 000.00 USD"

        cleared_snapshot = area.set_workspace_owned_snapshots(
            workspace.workspace_uid,
            order_rows=[],
            position_rows=[],
        )
        assert not cleared_snapshot.orders
        assert not cleared_snapshot.positions
        assert window.tbl_orders.rowCount() == 0
        assert window.tbl_positions.rowCount() == 0
        assert window.tbl_positions.isHidden()
        assert not window.ui.lblPositionPlaceholder.isHidden()

        area.set_runtime_snapshot(
            workspace.workspace_uid,
            active_orders_count=2,
            active_positions_count=1,
            current_profit=70.0,
            peak_profit=100.0,
        )
        assert window.ui.lblOrdersCount.text() == "2"
        assert window.ui.lblPositionsCount.text() == "1"
        assert window.ui.lblCurrentProfit.text() == "+0.00"
        assert window.ui.lblPeakProfit.text() == "1 000.00 USD"
        assert window.ui.lblProfitDrawdown.text() == "1 000.00 USD"
        can_close_orders, _reason = area.can_close_workspace(workspace.workspace_uid)
        assert not can_close_orders

        area.set_runtime_snapshot(workspace.workspace_uid)
        area.set_layout_locked(True)
        app.processEvents()
        assert controller.is_layout_locked()
        assert not area.btn_new.isEnabled()
        assert not area.btn_cascade.isEnabled()
        assert not area.btn_tile.isEnabled()

        locked_geometry = QRect(subwindow.geometry())
        subwindow.move(locked_geometry.x() + 80, locked_geometry.y() + 60)
        app.processEvents()
        app.processEvents()
        assert subwindow.geometry() == locked_geometry

        can_close_locked, _reason = area.can_close_workspace(workspace.workspace_uid)
        assert not can_close_locked

        area.set_layout_locked(False)
        app.processEvents()
        second_workspace = area.create_workspace(
            broker="CTRADER",
            account_id="123456",
            account_mode=WORKSPACE_ACCOUNT_MODE_DEMO,
            symbol="GBPUSD",
            timeframe="H1",
            algorithm="RailAlgorithm",
        )
        app.processEvents()
        second_window = area.workspace_window(second_workspace.workspace_uid)
        assert isinstance(second_window, AlgorithmWorkspaceWindow)
        assert second_window.ui.lblAccount.text() == "demo-login • Demo account"
        assert second_window.ui.lblAccount.toolTip() == "Runtime account ID: 123456"
        assert second_window.ui.lblBalance.text() == "2 500.75 USD"
        second_window.set_account_identity(
            "123456",
            WORKSPACE_ACCOUNT_MODE_DEMO,
            preserve_public_name=True,
        )
        assert second_window.ui.lblAccount.text() == "demo-login • Demo account"
        public_account_name_preserved_on_disconnect = True
        assert second_window.property("activeWorkspace") is True
        assert window.property("activeWorkspace") is False

        area.mdi.setActiveSubWindow(subwindow)
        app.processEvents()
        assert window.property("activeWorkspace") is True
        assert second_window.property("activeWorkspace") is False
        second_subwindow = area.workspace_subwindow(second_workspace.workspace_uid)
        assert second_subwindow is not None
        area.mdi.setActiveSubWindow(second_subwindow)
        app.processEvents()
        assert second_window.property("activeWorkspace") is True
        active_workspace_indicator = True

        normal_second_geometry = QRect(second_subwindow.geometry())
        second_subwindow.show_workspace_maximized()
        app.processEvents()
        assert second_subwindow.is_workspace_maximized()
        assert not second_subwindow.isMaximized()
        assert second_subwindow.geometry() == area.mdi.viewport().rect()
        area.flush_pending_ui_state()
        maximized_state = repository.load_workspace(
            second_workspace.workspace_uid
        ).ui_state
        assert maximized_state["window_state"] == "MAXIMIZED"
        assert maximized_state["geometry"] == {
            "x": normal_second_geometry.x(),
            "y": normal_second_geometry.y(),
            "width": normal_second_geometry.width(),
            "height": normal_second_geometry.height(),
        }
        second_subwindow.restore_workspace_normal()
        app.processEvents()
        assert second_subwindow.geometry() == normal_second_geometry
        mdi_safe_maximize = True

        ctrader_history_dialog = AlgorithmWorkspaceHistoryDownloadDialog(
            repository.load_workspace(second_workspace.workspace_uid),
            history_download=_unused_history_download,
            history_root=preview_history_root,
        )
        ctrader_history_dialog.dt_start_date.setDate(QDate(2026, 1, 1))
        ctrader_history_dialog.dt_end_date.setDate(QDate(2026, 7, 27))
        planned_ctrader_path = Path(ctrader_history_dialog.edt_planned_file.text())
        assert planned_ctrader_path.name == (
            "2026-01-01_2026-07-27_CTRADER_GBPUSD_H1.csv"
        )
        assert ctrader_history_dialog.btn_download.isEnabled()
        ctrader_history_dialog.close()
        ctrader_history_download_dialog_connected = True

        area.tile_windows()
        app.processEvents()
        tiled_second_geometry = QRect(second_subwindow.geometry())
        second_subwindow.showMaximized()
        for _ in range(4):
            app.processEvents()
        assert second_subwindow.is_workspace_maximized()
        assert not second_subwindow.isMaximized()
        tiled_maximized_geometry = QRect(second_subwindow.geometry())
        tiled_viewport_geometry = QRect(area.mdi.viewport().rect())
        assert tiled_maximized_geometry == tiled_viewport_geometry, (
            "Tile maximize geometry mismatch: "
            f"window={tiled_maximized_geometry.getRect()} "
            f"viewport={tiled_viewport_geometry.getRect()}"
        )
        second_subwindow.showMaximized()
        for _ in range(4):
            app.processEvents()
        assert not second_subwindow.is_workspace_maximized()
        assert second_subwindow.geometry() == tiled_second_geometry
        mdi_titlebar_maximize_after_tile = True

        area.cascade_windows()
        app.processEvents()
        cascaded_second_geometry = QRect(second_subwindow.geometry())
        second_subwindow.showMaximized()
        for _ in range(4):
            app.processEvents()
        assert second_subwindow.is_workspace_maximized()
        cascaded_maximized_geometry = QRect(second_subwindow.geometry())
        cascaded_viewport_geometry = QRect(area.mdi.viewport().rect())
        assert cascaded_maximized_geometry == cascaded_viewport_geometry, (
            "Cascade maximize geometry mismatch: "
            f"window={cascaded_maximized_geometry.getRect()} "
            f"viewport={cascaded_viewport_geometry.getRect()}"
        )
        second_subwindow.showMaximized()
        for _ in range(4):
            app.processEvents()
        assert not second_subwindow.is_workspace_maximized()
        assert second_subwindow.geometry() == cascaded_second_geometry
        mdi_titlebar_maximize_after_cascade = True

        area.tile_windows()
        app.processEvents()
        area.flush_pending_ui_state()
        assert area.workspace_count() == 2
        assert area.current_workspace_uid() == second_workspace.workspace_uid

        saved_first_before_restore = repository.load_workspace(workspace.workspace_uid)
        saved_first_panel = saved_first_before_restore.ui_state["active_panel"]
        assert saved_first_panel == WORKSPACE_PANEL_POSITION

        tiled_first = repository.load_workspace(workspace.workspace_uid)
        tiled_second = repository.load_workspace(second_workspace.workspace_uid)
        tiled_geometries = {
            workspace.workspace_uid: tiled_first.ui_state["geometry"],
            second_workspace.workspace_uid: tiled_second.ui_state["geometry"],
        }

        restored_area = AlgorithmWorkspaceArea(controller=controller)
        restored_area.set_runtime_engine(
            SimpleNamespace(
                ib_runtime_service=FakeIbService(),
                ctrader_runtime_service=FakeCtraderService(),
            )
        )
        restored_area.resize(700, 520)
        restored_area.show()
        app.processEvents()
        assert restored_area.workspace_count() == 0
        restored_area.restore_from_session_after_layout()
        restored_area.resize(1280, 820)
        app.processEvents()
        restored_area.finalize_session_layout()
        app.processEvents()
        app.processEvents()

        assert restored_area.workspace_count() == 2
        assert restored_area.current_workspace_uid() == second_workspace.workspace_uid
        restored_window = restored_area.workspace_window(workspace.workspace_uid)
        restored_second_window = restored_area.workspace_window(
            second_workspace.workspace_uid
        )
        assert isinstance(restored_window, AlgorithmWorkspaceWindow)
        assert isinstance(restored_second_window, AlgorithmWorkspaceWindow)
        assert restored_window.property("activeWorkspace") is False
        assert restored_second_window.property("activeWorkspace") is True
        assert restored_window.runtime_state == WORKSPACE_STATE_STOPPED
        restored_runtime = controller.workspace_runtime(workspace.workspace_uid)
        assert restored_runtime is not None
        restore_transition = any(
            entry.event == "STATE_CHANGED"
            and entry.details.get("previous_state") == "RESTORED"
            and entry.details.get("target_state") == "STOPPED"
            for entry in restored_runtime.journal
        )
        assert restore_transition
        assert restored_window.active_panel() == WORKSPACE_PANEL_POSITION
        assert restored_window.ui.lblAccount.text() == "Virtual Replay account"
        assert restored_window.ui.lblBalance.text() == "1 000.00 USD"

        viewport = restored_area.mdi.viewport().rect()
        restored_geometry_keys: set[tuple[int, int, int, int]] = set()
        for restored_subwindow in restored_area.mdi.subWindowList():
            geometry = restored_subwindow.geometry()
            restored_geometry_keys.add(
                (
                    geometry.x(),
                    geometry.y(),
                    geometry.width(),
                    geometry.height(),
                )
            )
            assert geometry.left() >= viewport.left()
            assert geometry.top() >= viewport.top()
            assert geometry.right() <= viewport.right()
            assert geometry.bottom() <= viewport.bottom()
        assert len(restored_geometry_keys) == 2

        for workspace_uid, saved_geometry in tiled_geometries.items():
            restored_subwindow = restored_area.workspace_subwindow(workspace_uid)
            assert restored_subwindow is not None
            restored_geometry = restored_subwindow.geometry()
            assert restored_geometry.x() == saved_geometry["x"]
            assert restored_geometry.y() == saved_geometry["y"]

        second_subwindow = restored_area.workspace_subwindow(
            second_workspace.workspace_uid
        )
        assert second_subwindow is not None
        can_close_second, _reason = restored_area.can_close_workspace(
            second_workspace.workspace_uid
        )
        assert can_close_second
        second_subwindow.close()
        app.processEvents()
        assert restored_area.workspace_count() == 1
        assert not repository.workspace_path(second_workspace.workspace_uid).exists()

        print("Algorithm Workspace MDI Area result")
        print(f"  workspace_uid={workspace.workspace_uid}")
        print(f"  display_name={renamed.display_name}")
        print(f"  data_mode={window.cmb_data_mode.currentData()}")
        print(f"  control_mode={window.cmb_control_mode.currentData()}")
        print(f"  saved_geometry={stored.ui_state['geometry']}")
        print(f"  active_panel={stored.ui_state['active_panel']}")
        print(f"  restored_state={restored_window.runtime_state}")
        print(f"  restore_transition={restore_transition}")
        print(f"  close_running_blocked={not can_close_running}")
        print("  replay_pause_step_speed=True")
        print("  replay_speeds_100x_1000x_max_max_fast_visible=True")
        print("  warmup_spread_guard_connected=True")
        print("  order_position_tabs_connected=True")
        print("  signals_tab_connected=True")
        print("  chart_foundation_connected=True")
        print("  replay_settings_dialog_connected=True")
        print("  replay_settings_dialog_designer_ui=True")
        print(
            "  ctrader_history_download_dialog_connected="
            f"{ctrader_history_download_dialog_connected}"
        )
        print(
            "  ib_history_download_dialog_connected="
            f"{ib_history_download_dialog_connected}"
        )
        print(
            "  broker_history_defaults_prefilled="
            f"{broker_history_defaults_prefilled}"
        )
        print(
            "  history_download_dialog_designer_ui="
            f"{history_download_dialog_designer_ui}"
        )
        print(
            "  separate_history_and_replay_dialogs="
            f"{separate_history_and_replay_dialogs}"
        )
        print(
            "  planned_name_updates_immediately=" f"{planned_name_updates_immediately}"
        )
        print(f"  replay_csv_period_detected={replay_csv_period_detected}")
        print(f"  independent_replay_periods={independent_replay_periods}")
        print(f"  download_timezone_connected={download_timezone_connected}")
        print(f"  active_workspace_indicator={active_workspace_indicator}")
        print(f"  active_badge_text_removed={active_badge_text_removed}")
        print(f"  polish_runtime_state_fits={polish_runtime_state_fits}")
        print(f"  wait_broker_badge_visible={wait_broker_badge_visible}")
        print(
            "  public_account_name_preserved_on_disconnect="
            f"{public_account_name_preserved_on_disconnect}"
        )
        print(f"  mdi_safe_maximize={mdi_safe_maximize}")
        print(
            "  mdi_titlebar_maximize_after_tile=" f"{mdi_titlebar_maximize_after_tile}"
        )
        print(
            "  mdi_titlebar_maximize_after_cascade="
            f"{mdi_titlebar_maximize_after_cascade}"
        )
        print(f"  replay_configured_indicator={replay_configured_indicator}")
        print("  parameters_dialog_connected=True")
        print("  parameters_dialog_designer_ui=True")
        print(
            "  active_replay_settings_edit_blocked="
            f"{active_replay_settings_edit_blocked}"
        )
        print("  active_parameter_edit_blocked=" f"{active_parameter_edit_blocked}")
        print("  workspace_journal_connected=True")
        print(f"  close_active_orders_blocked={not can_close_orders}")
        print(f"  layout_locked={controller.is_layout_locked()}")
        print("  delayed_restore=True")
        print("  restored_geometry_clamped=True")
        print("  saved_geometry_reapplied=True")
        print("  restored_windows_distinct=True")
        print(f"  account_balance={second_window.ui.lblBalance.text()}")
        print(f"  remaining_workspaces={restored_area.workspace_count()}")
        print("ALGORITHM_WORKSPACE_MDI_AREA_CHECK=OK")

        restored_area.close()
        area.close()


if __name__ == "__main__":
    main()
