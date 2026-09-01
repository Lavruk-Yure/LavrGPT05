"""core/algorithm_workspace_area.py — MDI UI та diagnostics algorithm WSP.

Модуль відображає Orders/Chart/Positions/Signals/Journal, Replay controls,
параметри, фільтри та локалізовані snapshot-таблиці без прямого доступу до
broker adapters. RoadMap100 додає position overlay на price chart і передає
manual drag SL/TP через Window -> Area -> Controller -> WorkspaceRuntime.
Також додається окрема кнопка ``Тік``: у multi-resolution Replay вона
проводить рівно одну вже staged найдрібнішу execution-подію (для M1 -> M15
це один M1 bar) і ніколи сама не виконує strategy ``Крок``. ``Крок``
зупиняється на strategy bar перед його execution window.
Drag доступний лише для paused Historical Replay; read-only Entry/SL/TP
overlay при цьому може відображати будь-які exact WSP-owned active positions.
RoadMap101 додає в Signals окрему diagnostic колонку та фільтр режиму
Alligator, переходи Signal -> Position/Journal і точне позначення цільового
бару після навігації без впливу на торгове рішення. Journal search враховує
structured details, тому працює і для сигналів з вимкненим Alligator.
Signal Journal entries показуються повними читабельними блоками, а Signals
tooltip лишається коротким summary без raw diagnostics. RoadMap102 тим самим
formatter показує Candidate F RELEASE/CANCEL/EXPIRE terminal events без нових
trading rows; перехід Signal -> Journal позиціонує view на початок знайденого
блоку, а не на останній запис. RoadMap102/3E додає PageUp/PageDown/Home/End
навігацію саме між compact summary у Journal, пропускаючи raw technical blocks.
RoadMap102/3H додає календарний перехід лише за датою в Signals і
Positions. Таблиці при цьому не фільтруються, а selection переходить до
першого видимого запису на вибрану або найближчу наступну доступну дату.
RoadMap102/3I робить date-jump та пов'язані navigation buttons компактними,
щоб вони не розтягувалися на всю ширину вкладки.
Ручна ширина Orders/Positions/Signals
зберігається в Session і не змінює runtime evidence.
Для multi-resolution diagnostics UI окремо показує останній M1 execution time,
Bid/Ask та Tick-price line, не підміняючи strategy M15 chart. High-speed
Replay 100x/1000x/MAX виконується короткими bounded chunks із поверненням
керування Qt між ними. MAX FAST не пропускає Replay events, але адаптивно
збільшує compute batch лише в межах короткого часового бюджету, після чого
обов'язково повертає керування Qt. Важкий chart/table/journal refresh у MAX FAST
виконується окремо й відлічує interval від завершення попереднього refresh, а
не від його початку; це не дає дорогому UI sync перетворитися на безперервний.
UI не змінює execution snapshot напряму і не виконує broker operation.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from time import monotonic
from typing import Any

from PySide6.QtCore import QDate, QEvent, QObject, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QIcon, QKeyEvent, QMoveEvent, QResizeEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMdiSubWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from core.algorithm_workspace import (
    WORKSPACE_ACCOUNT_MODE_DEMO,
    WORKSPACE_ACCOUNT_MODE_LIVE,
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_CONTROL_MODE_MANUAL,
    WORKSPACE_CONTROL_MODE_SEMI,
    WORKSPACE_DATA_MODE_BACKTEST,
    WORKSPACE_DATA_MODE_BROKER,
    WORKSPACE_DATA_MODE_REPLAY,
    WORKSPACE_PANEL_CHART,
    WORKSPACE_PANEL_LOG,
    WORKSPACE_PANEL_ORDERS,
    WORKSPACE_PANEL_POSITION,
    WORKSPACE_PANEL_SIGNALS,
    WORKSPACE_STATE_ERROR,
    WORKSPACE_STATE_RESTORED,
    WORKSPACE_STATE_RUNNING,
    WORKSPACE_STATE_STARTING,
    WORKSPACE_STATE_STOPPED,
    WORKSPACE_STATE_STOPPING,
    AlgorithmWorkspace,
    AlgorithmWorkspaceError,
)
from core.algorithm_workspace_catalog import (
    AlgorithmWorkspaceCatalog,
    WorkspaceAccountOption,
    format_workspace_balance,
)
from core.algorithm_workspace_controller import (
    AlgorithmWorkspaceController,
    WorkspaceLayoutLockedError,
)
from core.algorithm_workspace_history_download_dialog import (
    AlgorithmWorkspaceHistoryDownloadDialog,
)
from core.algorithm_workspace_historical_summary_dialog import (
    AlgorithmWorkspaceHistoricalSummaryDialog,
)
from core.algorithm_workspace_parameters_dialog import (
    AlgorithmWorkspaceParametersDialog,
)
from core.algorithm_workspace_replay_dialog import (
    AlgorithmWorkspaceReplayDialog,
)
from core.lang_manager import LangManager
from core.table_column_widths import TableColumnWidthPersistence
from core.timeframes import list_enabled_timeframes
from core.ui_translator import UITranslator
from core.workspace_algorithm import create_registered_workspace_algorithm
from core.workspace_chart import WorkspaceChartSnapshot
from core.workspace_chart_widget import WorkspaceChartWidget
from core.workspace_close_guard import (
    WORKSPACE_CLOSE_BLOCK_ACTIVE_ORDERS,
    WORKSPACE_CLOSE_BLOCK_BROKER_OPERATION,
    WORKSPACE_CLOSE_BLOCK_MARKET_EVENT,
    WORKSPACE_CLOSE_BLOCK_OPEN_POSITIONS,
    WORKSPACE_CLOSE_BLOCK_PENDING_CLOSE,
    WORKSPACE_CLOSE_BLOCK_REPLAY_STEP,
    WORKSPACE_CLOSE_BLOCK_RUNTIME_ACTIVE,
    WorkspaceCloseBlocker,
)
from core.workspace_history_download_settings import (
    WorkspaceHistoryDownloadSettings,
)
from core.workspace_market_event import WorkspaceMarketEvent
from core.workspace_ownership import (
    WorkspaceOrderSnapshot,
    WorkspaceOwnedSnapshot,
    WorkspacePositionSnapshot,
)
from core.workspace_parameters import WorkspaceAlgorithmParameters
from core.workspace_replay import (
    REPLAY_MAX_FAST_TIME_BUDGET_SECONDS,
    REPLAY_SPEED_MAX,
    REPLAY_SPEED_MAX_FAST,
    REPLAY_SPEEDS,
    REPLAY_STATE_COMPLETED,
    REPLAY_STATE_PAUSED,
    REPLAY_STATE_READY,
    REPLAY_STATE_RUNNING,
    REPLAY_STATE_STOPPED,
    WorkspaceReplayError,
    replay_max_fast_next_batch_size,
    replay_speed_label,
    replay_ui_batch_size,
    replay_ui_cycle_quota,
    replay_ui_should_refresh,
)
from core.workspace_replay_settings import WorkspaceReplaySettings
from core.workspace_runtime import (
    WORKSPACE_STARTUP_PHASE_IDLE,
    WORKSPACE_STARTUP_PHASE_LOAD_DATA,
    WORKSPACE_STARTUP_PHASE_READY,
    WORKSPACE_STARTUP_PHASE_RUNNING,
    WORKSPACE_STARTUP_PHASE_SAFETY_HOLD_EXTERNAL_EXPOSURE,
    WORKSPACE_STARTUP_PHASE_WAIT_BROKER,
    WORKSPACE_STARTUP_PHASE_WAIT_SPREAD,
    WORKSPACE_STARTUP_PHASE_WARMUP,
    WorkspaceJournalEntry,
    WorkspaceRuntimeError,
)
from core.workspace_signal import WorkspaceSignalRecord
from core.workspace_signal_presentation import (
    build_workspace_signal_journal_text,
    build_workspace_signal_presentation,
    workspace_signal_i18n_entries,
    workspace_signal_alligator_regime_text,
    workspace_signal_profile_revision_text,
    workspace_signal_reason_code_text,
    workspace_signal_timeframe_mode_text,
)
from engine.runtime_constants import WORKSPACE_REPLAY_SOURCE_CSV
from ui.ui_algorithm_workspace_area import Ui_AlgorithmWorkspaceArea
from ui.ui_algorithm_workspace_create_dialog import (
    Ui_AlgorithmWorkspaceCreateDialog,
)
from ui.ui_algorithm_workspace_window import Ui_AlgorithmWorkspaceWindow

logger = logging.getLogger(__name__)

LOCK_OPEN_ICON = ":/icons/lock_open.png"
LOCK_CLOSE_ICON = ":/icons/lock_close.png"

ACTIVE_RUNTIME_STATES = {
    WORKSPACE_STATE_STARTING,
    WORKSPACE_STATE_RUNNING,
    WORKSPACE_STATE_STOPPING,
}

WORKSPACE_STATE_LABELS = {
    WORKSPACE_STATE_RESTORED: (
        "AlgorithmWorkspaceState.restored",
        "RESTORED",
    ),
    WORKSPACE_STATE_STOPPED: (
        "AlgorithmWorkspaceState.stopped",
        "STOPPED",
    ),
    WORKSPACE_STATE_STARTING: (
        "AlgorithmWorkspaceState.starting",
        "STARTING",
    ),
    WORKSPACE_STATE_RUNNING: (
        "AlgorithmWorkspaceState.running",
        "RUNNING",
    ),
    WORKSPACE_STATE_STOPPING: (
        "AlgorithmWorkspaceState.stopping",
        "STOPPING",
    ),
    WORKSPACE_STATE_ERROR: (
        "AlgorithmWorkspaceState.error",
        "ERROR",
    ),
}

REPLAY_STATE_LABELS = {
    REPLAY_STATE_READY: ("AlgorithmReplayState.ready", "READY"),
    REPLAY_STATE_RUNNING: ("AlgorithmReplayState.running", "RUNNING"),
    REPLAY_STATE_PAUSED: ("AlgorithmReplayState.paused", "PAUSED"),
    REPLAY_STATE_COMPLETED: (
        "AlgorithmReplayState.completed",
        "COMPLETED",
    ),
    REPLAY_STATE_STOPPED: ("AlgorithmReplayState.stopped", "STOPPED"),
}

WORKSPACE_STARTUP_PHASE_LABELS = {
    WORKSPACE_STARTUP_PHASE_IDLE: (
        "AlgorithmWorkspaceStartupPhase.idle",
        "IDLE",
    ),
    WORKSPACE_STARTUP_PHASE_LOAD_DATA: (
        "AlgorithmWorkspaceStartupPhase.loadData",
        "LOAD_DATA",
    ),
    WORKSPACE_STARTUP_PHASE_WARMUP: (
        "AlgorithmWorkspaceStartupPhase.warmup",
        "WARMUP",
    ),
    WORKSPACE_STARTUP_PHASE_WAIT_BROKER: (
        "AlgorithmWorkspaceStartupPhase.waitBroker",
        "WAIT_BROKER",
    ),
    WORKSPACE_STARTUP_PHASE_SAFETY_HOLD_EXTERNAL_EXPOSURE: (
        "AlgorithmWorkspaceStartupPhase.safetyHoldExternalExposure",
        "SAFETY HOLD",
    ),
    WORKSPACE_STARTUP_PHASE_WAIT_SPREAD: (
        "AlgorithmWorkspaceStartupPhase.waitSpread",
        "WAIT_SPREAD",
    ),
    WORKSPACE_STARTUP_PHASE_READY: (
        "AlgorithmWorkspaceStartupPhase.ready",
        "READY",
    ),
    WORKSPACE_STARTUP_PHASE_RUNNING: (
        "AlgorithmWorkspaceStartupPhase.running",
        "RUNNING",
    ),
}

POSITION_STATUS_LABELS = {
    "OPEN": (
        "AlgorithmWorkspacePositionStatus.open",
        "Open",
    ),
    "CLOSED": (
        "AlgorithmWorkspacePositionStatus.closed",
        "Closed",
    ),
}

POSITION_CLOSE_REASON_LABELS = {
    "STOP_LOSS": (
        "AlgorithmWorkspacePositionCloseReason.stopLoss",
        "Stop Loss",
    ),
    "TAKE_PROFIT": (
        "AlgorithmWorkspacePositionCloseReason.takeProfit",
        "Take Profit",
    ),
    "PROFIT_DRAWDOWN": (
        "AlgorithmWorkspacePositionCloseReason.profitDrawdown",
        "Profit drawdown",
    ),
    "SESSION_END": (
        "AlgorithmWorkspacePositionCloseReason.sessionEnd",
        "Replay end",
    ),
}

PANEL_BY_INDEX = {
    0: WORKSPACE_PANEL_CHART,
    1: WORKSPACE_PANEL_POSITION,
    2: WORKSPACE_PANEL_SIGNALS,
    3: WORKSPACE_PANEL_ORDERS,
    4: WORKSPACE_PANEL_LOG,
}
INDEX_BY_PANEL = {value: key for key, value in PANEL_BY_INDEX.items()}

ORDER_TABLE_COLUMNS = (
    ("AlgorithmWorkspaceWindow.colOrderId", "Order ID"),
    ("AlgorithmWorkspaceWindow.colBrokerOrderId", "Broker order ID"),
    ("AlgorithmWorkspaceWindow.colSide", "Side"),
    ("AlgorithmWorkspaceWindow.colOrderType", "Type"),
    ("AlgorithmWorkspaceWindow.colVolume", "Volume"),
    ("AlgorithmWorkspaceWindow.colPrice", "Price"),
    ("AlgorithmWorkspaceWindow.colStopLoss", "SL"),
    ("AlgorithmWorkspaceWindow.colTakeProfit", "TP"),
    ("AlgorithmWorkspaceWindow.colStatus", "Status"),
    ("AlgorithmWorkspaceWindow.colCloseReason", "Close reason"),
    ("AlgorithmWorkspaceWindow.colCreatedAt", "Created"),
    ("AlgorithmWorkspaceWindow.colProfit", "Profit"),
)

POSITION_TABLE_COLUMNS = (
    ("AlgorithmWorkspaceWindow.colSide", "Side"),
    ("AlgorithmWorkspaceWindow.colVolume", "Volume"),
    ("AlgorithmWorkspaceWindow.colEntryPrice", "Entry"),
    ("AlgorithmWorkspaceWindow.colCurrentPrice", "Current"),
    ("AlgorithmWorkspaceWindow.colProfit", "Profit"),
    ("AlgorithmWorkspaceWindow.colPeakProfit", "Peak"),
    ("AlgorithmWorkspaceWindow.colProfitDrawdown", "Pullback"),
    ("AlgorithmWorkspaceWindow.colStopLoss", "SL"),
    ("AlgorithmWorkspaceWindow.colTakeProfit", "TP"),
    ("AlgorithmWorkspaceWindow.colPositionSignalTime", "Signal"),
    ("AlgorithmWorkspaceWindow.colOpenedAt", "Opened"),
    ("AlgorithmWorkspaceWindow.colClosedAt", "Closed"),
    ("AlgorithmWorkspaceWindow.colStatus", "Status"),
    ("AlgorithmWorkspaceWindow.colCloseReason", "Close reason"),
)

ORDER_TABLE_WIDTHS = (110, 105, 60, 100, 74, 82, 82, 82, 86, 130, 145, 76)
POSITION_TABLE_WIDTHS = (54, 74, 82, 82, 72, 72, 74, 82, 82, 145, 145, 145, 84, 150)

SIGNAL_TABLE_COLUMNS = (
    ("AlgorithmWorkspaceWindow.colSignalTime", "Time"),
    ("AlgorithmWorkspaceWindow.colSignalType", "Signal"),
    ("AlgorithmWorkspaceWindow.colDirection", "Direction"),
    ("AlgorithmWorkspaceWindow.colStrength", "Strength"),
    ("AlgorithmWorkspaceWindow.colMacdState", "MACD"),
    ("AlgorithmWorkspaceWindow.colAlligator", "Alligator"),
    ("AlgorithmWorkspaceWindow.colAlligatorRegime", "Regime"),
    ("AlgorithmWorkspaceWindow.colSignalTimeframeMode", "TF / mode"),
    ("AlgorithmWorkspaceWindow.colSignalProfileRevision", "Profile rev."),
    ("AlgorithmWorkspaceWindow.colSpreadStatus", "Spread"),
    ("AlgorithmWorkspaceWindow.colFilterResult", "Filter / result"),
    ("AlgorithmWorkspaceWindow.colReason", "Reason"),
)

SIGNAL_TABLE_WIDTHS = (142, 96, 82, 92, 122, 168, 156, 176, 156, 82, 154, 340)
SIGNAL_TABLE_REASON_COLUMN = 11

JOURNAL_CATEGORY_GROUPS = {
    "ALL": frozenset(),
    "RUNTIME": frozenset({"LIFECYCLE", "ALGORITHM", "REPLAY", "HISTORY"}),
    "MARKET": frozenset({"MARKET"}),
    "SIGNAL": frozenset({"SIGNAL"}),
    "GUARD": frozenset({"GUARD", "RISK"}),
    "BROKER": frozenset({"BROKER"}),
    "ERROR": frozenset({"ERROR"}),
}

JOURNAL_LEVEL_ALL = "ALL"
JOURNAL_LEVEL_INFO = "INFO"
JOURNAL_LEVEL_WARNING = "WARNING"
JOURNAL_LEVEL_ERROR = "ERROR"

WSP_FILTER_ALL = "ALL"
WSP_FILTER_ACCEPTED = "ACCEPTED"
WSP_FILTER_REJECTED = "REJECTED"
WSP_FILTER_PROFIT = "PROFIT"
WSP_FILTER_LOSS = "LOSS"
WSP_FILTER_ZERO = "ZERO"
WSP_FILTER_OPEN = "OPEN"
WSP_FILTER_CLOSED = "CLOSED"
WSP_FILTER_REGIME_UNDEFINED = "REGIME_UNDEFINED"

ALLIGATOR_REGIME_FLAT = "ALLIGATOR_REGIME_FLAT"
ALLIGATOR_REGIME_TREND_UP = "ALLIGATOR_REGIME_TREND_UP"
ALLIGATOR_REGIME_TREND_DOWN = "ALLIGATOR_REGIME_TREND_DOWN"
ALLIGATOR_REGIME_WARMUP = "ALLIGATOR_REGIME_WARMUP"
ALLIGATOR_REGIME_DISABLED = "ALLIGATOR_REGIME_DISABLED"


def workspace_mode_i18n_entries() -> dict[str, str]:
    """Return shared translation keys for WSP modes."""
    return {
        "WorkspaceDataSource.broker": "Broker data",
        "WorkspaceDataSource.replay": "Historical replay",
        "WorkspaceDataSource.backtest": "Backtest",
        "WorkspaceControlMode.manualControl": "Manual control",
        "WorkspaceControlMode.semiAutomatic": "Semi-automatic control",
        "WorkspaceControlMode.automatic": "Automatic control",
        "WorkspaceAccountMode.live": "Live account",
        "WorkspaceAccountMode.demo": "Demo account",
        "WorkspaceAccountMode.paper": "Paper account",
    }


def workspace_account_mode_key(account_mode: str | None) -> tuple[str, str]:
    """Return translation key/fallback for an account mode."""
    normalized = str(account_mode or "").strip().upper()
    mapping = {
        WORKSPACE_ACCOUNT_MODE_LIVE: (
            "WorkspaceAccountMode.live",
            "Live account",
        ),
        WORKSPACE_ACCOUNT_MODE_DEMO: (
            "WorkspaceAccountMode.demo",
            "Demo account",
        ),
        WORKSPACE_ACCOUNT_MODE_PAPER: (
            "WorkspaceAccountMode.paper",
            "Paper account",
        ),
    }
    return mapping.get(normalized, ("", ""))


class AlgorithmWorkspaceCreateDialog(QDialog):
    """Dialog for creating one AlgorithmWorkspace configuration."""

    def __init__(
        self,
        lang_mgr: LangManager | None = None,
        catalog: AlgorithmWorkspaceCatalog | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._lang_mgr = lang_mgr
        self._translator = UITranslator(lang_mgr) if lang_mgr is not None else None
        self._catalog = catalog or AlgorithmWorkspaceCatalog()

        self.ui = Ui_AlgorithmWorkspaceCreateDialog()
        self.ui.setupUi(self)

        self.edt_display_name = self.ui.edtDisplayName
        self.cmb_broker = self.ui.cmbBroker
        self.cmb_account = self.ui.cmbAccount
        self.lbl_account_mode = self.ui.lblAccountModeValue
        self.cmb_symbol = self.ui.cmbSymbol
        self.cmb_timeframe = self.ui.cmbTimeframe
        self.cmb_algorithm = self.ui.cmbAlgorithm
        self.cmb_data_mode = self.ui.cmbDataMode
        self.cmb_control_mode = self.ui.cmbControlMode

        self.cmb_broker.addItem("IB", "IB")
        self.cmb_broker.addItem("cTrader", "CTRADER")
        self.cmb_timeframe.addItems(list_enabled_timeframes())
        self.cmb_timeframe.setCurrentText("M15")
        self.cmb_algorithm.addItem("RailAlgorithm")

        self.ui.btnCreate.clicked.connect(self.accept)
        self.ui.btnCancel.clicked.connect(self.reject)
        self.cmb_broker.currentIndexChanged.connect(
            self._refresh_account_and_symbol_options
        )
        self.cmb_account.currentIndexChanged.connect(self._refresh_account_mode)
        self.cmb_data_mode.currentIndexChanged.connect(self._refresh_data_mode_controls)

        self.apply_translation()
        data_mode, control_mode = self._default_modes()
        self._set_combo_by_data(self.cmb_data_mode, data_mode)
        self._set_combo_by_data(self.cmb_control_mode, control_mode)
        self._refresh_account_and_symbol_options()
        self._refresh_data_mode_controls()

    def _register_i18n_keys(self) -> None:
        if self._lang_mgr is None:
            return

        entries = {
            "AlgorithmWorkspaceCreateDialog.windowTitle": "New algorithm workspace",
            "AlgorithmWorkspaceCreateDialog.lblDisplayName": "Name:",
            "AlgorithmWorkspaceCreateDialog.phDisplayName": (
                "Optional — a name will be generated automatically"
            ),
            "AlgorithmWorkspaceCreateDialog.lblBroker": "Broker:",
            "AlgorithmWorkspaceCreateDialog.lblAccount": "Account:",
            "AlgorithmWorkspaceCreateDialog.lblAccountMode": "Account type:",
            "AlgorithmWorkspaceCreateDialog.lblSymbol": "Symbol:",
            "AlgorithmWorkspaceCreateDialog.lblTimeframe": "Timeframe:",
            "AlgorithmWorkspaceCreateDialog.lblAlgorithm": "Algorithm:",
            "AlgorithmWorkspaceCreateDialog.lblDataMode": "Data source:",
            "AlgorithmWorkspaceCreateDialog.lblControlMode": "Control mode:",
            "AlgorithmWorkspaceCreateDialog.lblNote": (
                "Only the workspace configuration is created. No orders are sent."
            ),
            "AlgorithmWorkspaceCreateDialog.btnCreate": "Create",
            "AlgorithmWorkspaceCreateDialog.btnCancel": "Cancel",
            "AlgorithmWorkspaceCreateDialog.errAccountRequired": (
                "Select a broker account for broker data."
            ),
            "AlgorithmWorkspaceCreateDialog.errSymbolRequired": "Select a symbol.",
            "AlgorithmWorkspaceCreateDialog.errAlgorithmRequired": (
                "Select an algorithm."
            ),
            "AlgorithmWorkspaceCreateDialog.noAccounts": (
                "No configured broker accounts"
            ),
        }
        entries.update(workspace_mode_i18n_entries())
        for key, fallback in entries.items():
            self._lang_mgr.tr(key, fallback)

    def apply_translation(self) -> None:
        """Apply current language to the Designer form and lists."""
        if self._lang_mgr is not None:
            self._register_i18n_keys()

        if self._translator is not None:
            self._translator.apply(self)
        else:
            self.setWindowTitle("New algorithm workspace")
            self.ui.lblDisplayName.setText("Name:")
            self.ui.edtDisplayName.setPlaceholderText(
                "Optional — a name will be generated automatically"
            )
            self.ui.lblBroker.setText("Broker:")
            self.ui.lblAccount.setText("Account:")
            self.ui.lblAccountMode.setText("Account type:")
            self.ui.lblSymbol.setText("Symbol:")
            self.ui.lblTimeframe.setText("Timeframe:")
            self.ui.lblAlgorithm.setText("Algorithm:")
            self.ui.lblDataMode.setText("Data source:")
            self.ui.lblControlMode.setText("Control mode:")
            self.ui.lblNote.setText(
                "Only the workspace configuration is created. No orders are sent."
            )
            self.ui.btnCreate.setText("Create")
            self.ui.btnCancel.setText("Cancel")

        self._populate_mode_combos()
        self._refresh_account_and_symbol_options()
        self._refresh_data_mode_controls()

    def accept(self) -> None:
        """Validate required fields before closing the dialog."""
        if (
            self.cmb_data_mode.currentData() == WORKSPACE_DATA_MODE_BROKER
            and self.selected_account_option() is None
        ):
            QMessageBox.warning(
                self,
                "LGE",
                self._tr(
                    "AlgorithmWorkspaceCreateDialog.errAccountRequired",
                    "Select a broker account for broker data.",
                ),
            )
            self.cmb_account.setFocus()
            return

        if not self.cmb_symbol.currentText().strip():
            QMessageBox.warning(
                self,
                "LGE",
                self._tr(
                    "AlgorithmWorkspaceCreateDialog.errSymbolRequired",
                    "Select a symbol.",
                ),
            )
            self.cmb_symbol.setFocus()
            return

        if not self.cmb_algorithm.currentText().strip():
            QMessageBox.warning(
                self,
                "LGE",
                self._tr(
                    "AlgorithmWorkspaceCreateDialog.errAlgorithmRequired",
                    "Select an algorithm.",
                ),
            )
            self.cmb_algorithm.setFocus()
            return

        super().accept()

    def selected_account_option(self) -> WorkspaceAccountOption | None:
        """Return the selected account option, if any."""
        data = self.cmb_account.currentData()
        return data if isinstance(data, WorkspaceAccountOption) else None

    @staticmethod
    def _account_display_text(account: WorkspaceAccountOption) -> str:
        parts = [account.display_name]
        if account.balance is not None:
            parts.append(format_workspace_balance(account.balance, account.currency))
        return " • ".join(parts)

    def workspace_values(self) -> dict[str, Any]:
        """Return normalized values from the form."""
        display_name = self.edt_display_name.text().strip()
        account = self.selected_account_option()
        uses_broker_account = (
            self.cmb_data_mode.currentData() == WORKSPACE_DATA_MODE_BROKER
        )

        return {
            "broker": str(self.cmb_broker.currentData() or "").strip(),
            "account_id": (
                account.account_id
                if uses_broker_account and account is not None
                else None
            ),
            "account_mode": (
                account.account_mode
                if uses_broker_account and account is not None
                else None
            ),
            "symbol": self.cmb_symbol.currentText().strip().upper(),
            "timeframe": self.cmb_timeframe.currentText().strip().upper(),
            "algorithm": self.cmb_algorithm.currentText().strip(),
            "display_name": display_name or None,
            "data_mode": str(self.cmb_data_mode.currentData()),
            "control_mode": str(self.cmb_control_mode.currentData()),
        }

    def _populate_mode_combos(self) -> None:
        current_data_mode = self.cmb_data_mode.currentData()
        current_control_mode = self.cmb_control_mode.currentData()

        self.cmb_data_mode.clear()
        self.cmb_data_mode.addItem(
            self._tr("WorkspaceDataSource.broker", "Broker data"),
            WORKSPACE_DATA_MODE_BROKER,
        )
        self.cmb_data_mode.addItem(
            self._tr("WorkspaceDataSource.replay", "Historical replay"),
            WORKSPACE_DATA_MODE_REPLAY,
        )
        self.cmb_data_mode.addItem(
            self._tr("WorkspaceDataSource.backtest", "Backtest"),
            WORKSPACE_DATA_MODE_BACKTEST,
        )

        self.cmb_control_mode.clear()
        self.cmb_control_mode.addItem(
            self._tr("WorkspaceControlMode.manualControl", "Manual control"),
            WORKSPACE_CONTROL_MODE_MANUAL,
        )
        self.cmb_control_mode.addItem(
            self._tr(
                "WorkspaceControlMode.semiAutomatic",
                "Semi-automatic control",
            ),
            WORKSPACE_CONTROL_MODE_SEMI,
        )
        self.cmb_control_mode.addItem(
            self._tr("WorkspaceControlMode.automatic", "Automatic control"),
            WORKSPACE_CONTROL_MODE_AUTO,
        )

        if current_data_mode is not None:
            self._set_combo_by_data(self.cmb_data_mode, str(current_data_mode))
        if current_control_mode is not None:
            self._set_combo_by_data(
                self.cmb_control_mode,
                str(current_control_mode),
            )

    def _refresh_account_and_symbol_options(self, _index: int = -1) -> None:
        broker = str(self.cmb_broker.currentData() or "").strip().upper()
        selected_account_id = None
        selected = self.selected_account_option()
        if selected is not None:
            selected_account_id = selected.account_id

        self.cmb_account.blockSignals(True)
        self.cmb_account.clear()
        accounts = self._catalog.list_accounts(broker)
        for account in accounts:
            self.cmb_account.addItem(
                self._account_display_text(account),
                account,
            )
        if not accounts:
            self.cmb_account.addItem(
                self._tr(
                    "AlgorithmWorkspaceCreateDialog.noAccounts",
                    "No configured broker accounts",
                ),
                None,
            )
        if selected_account_id:
            for index in range(self.cmb_account.count()):
                data = self.cmb_account.itemData(index)
                if (
                    isinstance(data, WorkspaceAccountOption)
                    and data.account_id == selected_account_id
                ):
                    self.cmb_account.setCurrentIndex(index)
                    break
        self.cmb_account.blockSignals(False)

        current_symbol = self.cmb_symbol.currentText().strip().upper()
        self.cmb_symbol.clear()
        self.cmb_symbol.addItems(
            self._catalog.list_symbols(broker, selected_account_id)
        )
        if current_symbol and self.cmb_symbol.findText(current_symbol) >= 0:
            self.cmb_symbol.setCurrentText(current_symbol)
        elif self.cmb_symbol.findText("EURUSD") >= 0:
            self.cmb_symbol.setCurrentText("EURUSD")

        self._refresh_account_mode()
        self._refresh_data_mode_controls()

    def _refresh_account_mode(self, _index: int = -1) -> None:
        account = self.selected_account_option()
        if account is None:
            self.lbl_account_mode.setText("—")
            return
        key, fallback = workspace_account_mode_key(account.account_mode)
        self.lbl_account_mode.setText(self._tr(key, fallback))

    def _refresh_data_mode_controls(self, _index: int = -1) -> None:
        uses_broker_account = (
            self.cmb_data_mode.currentData() == WORKSPACE_DATA_MODE_BROKER
        )
        self.cmb_account.setEnabled(
            uses_broker_account and self.selected_account_option() is not None
        )
        self.ui.lblAccount.setEnabled(uses_broker_account)
        self.ui.lblAccountMode.setEnabled(uses_broker_account)
        self.lbl_account_mode.setEnabled(uses_broker_account)

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    @staticmethod
    def _default_modes() -> tuple[str, str]:
        data_mode = WORKSPACE_DATA_MODE_BROKER
        control_mode = WORKSPACE_CONTROL_MODE_SEMI
        try:
            from core import session_state

            config = session_state.CURRENT_CONFIG
            if config is None:
                return data_mode, control_mode

            execution_mode = str(config.get("engine", "execution_mode", "SEMI")).upper()
            if execution_mode in {
                WORKSPACE_CONTROL_MODE_MANUAL,
                WORKSPACE_CONTROL_MODE_SEMI,
                WORKSPACE_CONTROL_MODE_AUTO,
            }:
                control_mode = execution_mode
        except Exception:  # noqa
            pass
        return data_mode, control_mode

    def _tr(self, key: str, fallback: str) -> str:
        if self._lang_mgr is None:
            return fallback
        return self._lang_mgr.tr(key, fallback)


class AlgorithmWorkspaceWindow(QFrame):
    """Visible WSP content embedded into one QMdiSubWindow."""

    rename_requested = Signal(str)
    start_requested = Signal(str)
    stop_requested = Signal(str)
    parameters_requested = Signal(str)
    replay_settings_requested = Signal(str)
    history_download_requested = Signal(str)
    modes_changed = Signal(str, str, str)
    replay_pause_requested = Signal(str)
    replay_step_requested = Signal(str)
    replay_tick_requested = Signal(str)
    replay_speed_changed = Signal(str, int)
    chart_visible_count_requested = Signal(str, int)
    chart_visible_start_requested = Signal(str, int)
    chart_timestamp_requested = Signal(str, object, bool)
    chart_latest_requested = Signal(str)
    chart_protection_change_requested = Signal(str, str, str, float)
    active_panel_changed = Signal(str, str)

    def __init__(
        self,
        workspace: AlgorithmWorkspace,
        lang_mgr: LangManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._lang_mgr = lang_mgr
        self._translator = UITranslator(lang_mgr) if lang_mgr is not None else None
        self.workspace_uid = workspace.workspace_uid
        self._has_started_once = workspace.has_started_once
        self._layout_locked = False
        self._runtime_state = workspace.runtime_state
        self._startup_phase = WORKSPACE_STARTUP_PHASE_IDLE
        self._safety_hold_active = False
        self._safety_hold_message = ""
        self._safety_hold_account_id = str(workspace.account_id or "").strip()
        self._safety_hold_symbol = str(workspace.symbol or "").strip().upper()
        self._safety_hold_signed_volume = 0.0
        self._safety_hold_evidence_status = ""
        self._safety_hold_confirmation_required = False
        self._active_orders_count = 0
        self._active_positions_count = 0
        self._current_profit = 0.0
        self._peak_profit = 0.0
        self._profit_drawdown_percent = 0.0
        self._updating_modes = False
        self._broker = workspace.broker
        self._account_id = workspace.account_id
        self._account_mode = workspace.account_mode
        self._account_display_name = workspace.account_id or "—"
        self._data_mode = workspace.data_mode
        self._replay_paused = False
        self._replay_speed = 1
        self._replay_configured = False
        self._is_active_workspace = False
        self._owned_snapshot = WorkspaceOwnedSnapshot(orders=(), positions=())
        self._signal_records: tuple[WorkspaceSignalRecord, ...] = ()
        self._journal_entries: list[WorkspaceJournalEntry] = []

        self.ui = Ui_AlgorithmWorkspaceWindow()
        self.ui.setupUi(self)

        self._full_display_name = ""
        self.lbl_name = self.ui.lblName
        self.lbl_state = self.ui.lblState
        self.btn_start_stop = self.ui.btnStartStop
        self.btn_history_download = self.ui.btnHistoryDownload
        self.btn_replay_settings = self.ui.btnReplaySettings
        self.btn_parameters = self.ui.btnParameters
        self.btn_rename = self.ui.btnRename
        self.cmb_data_mode = self.ui.cmbDataMode
        self.cmb_control_mode = self.ui.cmbControlMode
        self.tabs_workspace = self.ui.tabsWorkspace
        self._apply_workspace_tab_order()
        self.frame_replay_controls = self.ui.frameReplayControls
        self.btn_replay_tick = QPushButton(self.frame_replay_controls)
        self.btn_replay_tick.setObjectName("btnReplayTick")
        self.btn_replay_tick.setMaximumSize(self.ui.btnReplayStep.maximumSize())
        self.btn_replay_tick.setSizePolicy(self.ui.btnReplayStep.sizePolicy())
        self.btn_replay_tick.setFont(self.ui.btnReplayStep.font())
        self.btn_replay_tick.setStyleSheet(
            "min-height: 0px; max-height: 18px; "
            "padding: 0px 6px; font: 8pt 'Segoe UI';"
        )
        replay_layout = self.ui.horizontalLayoutReplay
        step_index = replay_layout.indexOf(self.ui.btnReplayStep)
        replay_layout.insertWidget(step_index + 1, self.btn_replay_tick)
        self.tbl_orders = self.ui.tblOrders
        self.chart_widget = WorkspaceChartWidget(self.ui.tabChart)
        self.chart_widget.setObjectName("workspaceChart")
        self.ui.verticalLayoutChart.insertWidget(0, self.chart_widget, 1)
        self.ui.lblChartPlaceholder.setVisible(False)
        self.tbl_positions = QTableWidget(self.ui.tabPosition)
        self.tbl_positions.setObjectName("tblPositions")
        self.ui.verticalLayoutPosition.addWidget(self.tbl_positions)
        self.tbl_signals = QTableWidget(self.ui.tabSignals)
        self.tbl_signals.setObjectName("tblSignals")
        self.ui.verticalLayoutSignals.addWidget(self.tbl_signals)
        self._table_column_width_persistence: tuple[
            TableColumnWidthPersistence, ...
        ] = ()
        self._configure_snapshot_tables()
        self._setup_snapshot_filters()
        self._setup_journal_filters()

        self.btn_rename.clicked.connect(
            lambda: self.rename_requested.emit(self.workspace_uid)
        )
        self.btn_history_download.clicked.connect(
            lambda: self.history_download_requested.emit(self.workspace_uid)
        )
        self.btn_replay_settings.clicked.connect(
            lambda: self.replay_settings_requested.emit(self.workspace_uid)
        )
        self.btn_parameters.clicked.connect(
            lambda: self.parameters_requested.emit(self.workspace_uid)
        )
        self.btn_start_stop.clicked.connect(self._on_start_stop_clicked)
        self.ui.btnReplayPause.clicked.connect(self._on_replay_pause_clicked)
        self.ui.btnReplayStep.clicked.connect(self._on_replay_step_clicked)
        self.btn_replay_tick.clicked.connect(self._on_replay_tick_clicked)
        self.ui.cmbReplaySpeed.currentIndexChanged.connect(
            self._on_replay_speed_changed
        )
        self.cmb_data_mode.currentIndexChanged.connect(self._on_modes_changed)
        self.cmb_control_mode.currentIndexChanged.connect(self._on_modes_changed)
        self.tabs_workspace.currentChanged.connect(self._on_panel_changed)
        self.chart_widget.visible_count_requested.connect(
            lambda visible_count: self.chart_visible_count_requested.emit(
                self.workspace_uid,
                visible_count,
            )
        )
        self.chart_widget.visible_start_requested.connect(
            lambda visible_start: self.chart_visible_start_requested.emit(
                self.workspace_uid,
                visible_start,
            )
        )
        self.chart_widget.latest_requested.connect(
            lambda: self.chart_latest_requested.emit(self.workspace_uid)
        )
        self.chart_widget.protection_change_requested.connect(
            self._forward_chart_protection_change
        )

        self.apply_translation()
        self.update_workspace(workspace)
        self.set_runtime_snapshot()
        self.set_owned_snapshot(WorkspaceOwnedSnapshot(orders=(), positions=()))

    def _apply_workspace_tab_order(self) -> None:
        """Встановити канонічний порядок вкладок WSP для аналізу.

        Аналіз починається з діаграми, далі йдуть позиції та сигнали.
        Замовлення розташовані після сигналів, журнал лишається останнім.
        """
        ordered_tabs = (
            self.ui.tabChart,
            self.ui.tabPosition,
            self.ui.tabSignals,
            self.ui.tabOrders,
            self.ui.tabLog,
        )
        for tab in ordered_tabs:
            index = self.tabs_workspace.indexOf(tab)
            if index >= 0:
                self.tabs_workspace.removeTab(index)
        for tab in ordered_tabs:
            self.tabs_workspace.addTab(tab, "")

    def _forward_chart_protection_change(
        self,
        position_id: str,
        field_name: str,
        price: float,
    ) -> None:
        """Додати workspace_uid до Replay protection request від chart."""
        self.chart_protection_change_requested.emit(
            self.workspace_uid,
            position_id,
            field_name,
            price,
        )

    @property
    def runtime_state(self) -> str:
        return self._runtime_state

    @property
    def active_orders_count(self) -> int:
        return self._active_orders_count

    def _configure_snapshot_tables(self) -> None:
        self._configure_snapshot_table(
            self.tbl_orders,
            len(ORDER_TABLE_COLUMNS),
            ORDER_TABLE_WIDTHS,
        )
        self._configure_snapshot_table(
            self.tbl_positions,
            len(POSITION_TABLE_COLUMNS),
            POSITION_TABLE_WIDTHS,
        )
        self._configure_snapshot_table(
            self.tbl_signals,
            len(SIGNAL_TABLE_COLUMNS),
            SIGNAL_TABLE_WIDTHS,
        )
        self._table_column_width_persistence = (
            TableColumnWidthPersistence(
                self.tbl_orders,
                "algorithm_workspace.orders",
                ORDER_TABLE_WIDTHS,
            ),
            TableColumnWidthPersistence(
                self.tbl_positions,
                "algorithm_workspace.positions",
                POSITION_TABLE_WIDTHS,
            ),
            TableColumnWidthPersistence(
                self.tbl_signals,
                "algorithm_workspace.signals",
                SIGNAL_TABLE_WIDTHS,
            ),
        )
        self.tbl_positions.setVisible(False)
        self.tbl_signals.setVisible(False)

    @staticmethod
    def _configure_snapshot_table(
        table: QTableWidget,
        column_count: int,
        widths: tuple[int, ...],
    ) -> None:
        table.setColumnCount(column_count)
        table.setRowCount(0)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(False)
        table.setWordWrap(False)
        table.setTextElideMode(Qt.TextElideMode.ElideRight)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.verticalHeader().setVisible(False)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(42)
        for column, width in enumerate(widths):
            header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.Interactive,
            )
            table.setColumnWidth(column, width)

    def _setup_snapshot_filters(self) -> None:
        self._setup_order_filters()
        self._setup_position_filters()
        self._setup_signal_filters()

    def _setup_order_filters(self) -> None:
        self.frame_order_filters = QFrame(self.ui.tabOrders)
        self.frame_order_filters.setObjectName("frameOrderFilters")
        layout = QGridLayout(self.frame_order_filters)
        layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_order_status_filter = QLabel(self.frame_order_filters)
        self.cmb_order_status_filter = QComboBox(self.frame_order_filters)
        self.cmb_order_status_filter.setObjectName("cmbOrderStatusFilter")
        self.lbl_order_direction_filter = QLabel(self.frame_order_filters)
        self.cmb_order_direction_filter = QComboBox(self.frame_order_filters)
        self.cmb_order_direction_filter.setObjectName("cmbOrderDirectionFilter")
        self.lbl_order_pnl_filter = QLabel(self.frame_order_filters)
        self.cmb_order_pnl_filter = QComboBox(self.frame_order_filters)
        self.cmb_order_pnl_filter.setObjectName("cmbOrderPnlFilter")
        self.lbl_order_reason_filter = QLabel(self.frame_order_filters)
        self.cmb_order_reason_filter = QComboBox(self.frame_order_filters)
        self.cmb_order_reason_filter.setObjectName("cmbOrderReasonFilter")

        layout.addWidget(self.lbl_order_status_filter, 0, 0)
        layout.addWidget(self.cmb_order_status_filter, 0, 1)
        layout.addWidget(self.lbl_order_direction_filter, 0, 2)
        layout.addWidget(self.cmb_order_direction_filter, 0, 3)
        layout.addWidget(self.lbl_order_pnl_filter, 1, 0)
        layout.addWidget(self.cmb_order_pnl_filter, 1, 1)
        layout.addWidget(self.lbl_order_reason_filter, 1, 2)
        layout.addWidget(self.cmb_order_reason_filter, 1, 3)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(3, 2)
        self.ui.verticalLayoutOrders.insertWidget(0, self.frame_order_filters)

        for combo in (
            self.cmb_order_status_filter,
            self.cmb_order_direction_filter,
            self.cmb_order_pnl_filter,
            self.cmb_order_reason_filter,
        ):
            combo.currentIndexChanged.connect(self._refresh_order_view)

    def _setup_position_filters(self) -> None:
        self.frame_position_filters = QFrame(self.ui.tabPosition)
        self.frame_position_filters.setObjectName("framePositionFilters")
        layout = QGridLayout(self.frame_position_filters)
        layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_position_pnl_filter = QLabel(self.frame_position_filters)
        self.cmb_position_pnl_filter = QComboBox(self.frame_position_filters)
        self.cmb_position_pnl_filter.setObjectName("cmbPositionPnlFilter")
        self.lbl_position_reason_filter = QLabel(self.frame_position_filters)
        self.cmb_position_reason_filter = QComboBox(self.frame_position_filters)
        self.cmb_position_reason_filter.setObjectName("cmbPositionReasonFilter")
        self.lbl_position_direction_filter = QLabel(self.frame_position_filters)
        self.cmb_position_direction_filter = QComboBox(self.frame_position_filters)
        self.cmb_position_direction_filter.setObjectName("cmbPositionDirectionFilter")
        self.lbl_position_status_filter = QLabel(self.frame_position_filters)
        self.cmb_position_status_filter = QComboBox(self.frame_position_filters)
        self.cmb_position_status_filter.setObjectName("cmbPositionStatusFilter")
        self.lbl_position_date_jump = QLabel(self.frame_position_filters)
        self.dte_position_date_jump = QDateEdit(self.frame_position_filters)
        self.dte_position_date_jump.setObjectName("dtePositionDateJump")
        self.dte_position_date_jump.setCalendarPopup(True)
        self.dte_position_date_jump.setDisplayFormat("yyyy-MM-dd")
        self.btn_position_date_jump = QPushButton(self.frame_position_filters)
        self.btn_position_date_jump.setObjectName("btnPositionDateJump")
        self.btn_position_date_jump.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )

        layout.addWidget(self.lbl_position_pnl_filter, 0, 0)
        layout.addWidget(self.cmb_position_pnl_filter, 0, 1)
        layout.addWidget(self.lbl_position_reason_filter, 0, 2)
        layout.addWidget(self.cmb_position_reason_filter, 0, 3)
        layout.addWidget(self.lbl_position_direction_filter, 1, 0)
        layout.addWidget(self.cmb_position_direction_filter, 1, 1)
        layout.addWidget(self.lbl_position_status_filter, 1, 2)
        layout.addWidget(self.cmb_position_status_filter, 1, 3)
        layout.addWidget(self.lbl_position_date_jump, 2, 0)
        layout.addWidget(self.dte_position_date_jump, 2, 1)
        layout.addWidget(self.btn_position_date_jump, 2, 2, 1, 2)

        self.frame_position_time_actions = QFrame(self.frame_position_filters)
        self.frame_position_time_actions.setObjectName("framePositionTimeActions")
        button_layout = QHBoxLayout(self.frame_position_time_actions)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(layout.horizontalSpacing())

        self.btn_position_go_signal = QPushButton(self.frame_position_time_actions)
        self.btn_position_go_signal.setObjectName("btnPositionGoSignal")
        self.btn_position_go_signal.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )
        self.btn_position_go_entry = QPushButton(self.frame_position_time_actions)
        self.btn_position_go_entry.setObjectName("btnPositionGoEntry")
        self.btn_position_go_entry.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )
        button_layout.addStretch(1)
        button_layout.addWidget(self.btn_position_go_signal)
        button_layout.addWidget(self.btn_position_go_entry)
        button_layout.addStretch(1)
        layout.addWidget(self.frame_position_time_actions, 3, 0, 1, 4)

        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(3, 2)
        self.ui.verticalLayoutPosition.insertWidget(0, self.frame_position_filters)

        for combo in (
            self.cmb_position_pnl_filter,
            self.cmb_position_reason_filter,
            self.cmb_position_direction_filter,
            self.cmb_position_status_filter,
        ):
            combo.currentIndexChanged.connect(self._refresh_position_view)
        self.tbl_positions.itemSelectionChanged.connect(
            self._refresh_position_time_actions
        )
        self.btn_position_go_signal.clicked.connect(self._on_position_go_signal_clicked)
        self.btn_position_go_entry.clicked.connect(self._on_position_go_entry_clicked)
        self.btn_position_date_jump.clicked.connect(self._on_position_date_jump_clicked)
        self._refresh_position_time_actions()
        self._sync_position_date_jump(())

    def _setup_signal_filters(self) -> None:
        self.frame_signal_filters = QFrame(self.ui.tabSignals)
        self.frame_signal_filters.setObjectName("frameSignalFilters")
        layout = QGridLayout(self.frame_signal_filters)
        layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_signal_result_filter = QLabel(self.frame_signal_filters)
        self.cmb_signal_result_filter = QComboBox(self.frame_signal_filters)
        self.cmb_signal_result_filter.setObjectName("cmbSignalResultFilter")
        self.lbl_signal_direction_filter = QLabel(self.frame_signal_filters)
        self.cmb_signal_direction_filter = QComboBox(self.frame_signal_filters)
        self.cmb_signal_direction_filter.setObjectName("cmbSignalDirectionFilter")
        self.lbl_signal_regime_filter = QLabel(self.frame_signal_filters)
        self.cmb_signal_regime_filter = QComboBox(self.frame_signal_filters)
        self.cmb_signal_regime_filter.setObjectName("cmbSignalRegimeFilter")
        self.lbl_signal_reason_filter = QLabel(self.frame_signal_filters)
        self.cmb_signal_reason_filter = QComboBox(self.frame_signal_filters)
        self.cmb_signal_reason_filter.setObjectName("cmbSignalReasonFilter")
        self.lbl_signal_date_jump = QLabel(self.frame_signal_filters)
        self.dte_signal_date_jump = QDateEdit(self.frame_signal_filters)
        self.dte_signal_date_jump.setObjectName("dteSignalDateJump")
        self.dte_signal_date_jump.setCalendarPopup(True)
        self.dte_signal_date_jump.setDisplayFormat("yyyy-MM-dd")
        self.btn_signal_date_jump = QPushButton(self.frame_signal_filters)
        self.btn_signal_date_jump.setObjectName("btnSignalDateJump")
        self.btn_signal_date_jump.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )

        layout.addWidget(self.lbl_signal_result_filter, 0, 0)
        layout.addWidget(self.cmb_signal_result_filter, 0, 1)
        layout.addWidget(self.lbl_signal_direction_filter, 0, 2)
        layout.addWidget(self.cmb_signal_direction_filter, 0, 3)
        layout.addWidget(self.lbl_signal_regime_filter, 0, 4)
        layout.addWidget(self.cmb_signal_regime_filter, 0, 5)
        layout.addWidget(self.lbl_signal_reason_filter, 1, 0)
        layout.addWidget(self.cmb_signal_reason_filter, 1, 1, 1, 5)
        layout.addWidget(self.lbl_signal_date_jump, 2, 0)
        layout.addWidget(self.dte_signal_date_jump, 2, 1, 1, 2)
        layout.addWidget(self.btn_signal_date_jump, 2, 3, 1, 3)

        self.frame_signal_actions = QFrame(self.frame_signal_filters)
        self.frame_signal_actions.setObjectName("frameSignalActions")
        button_layout = QHBoxLayout(self.frame_signal_actions)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(layout.horizontalSpacing())

        self.btn_signal_go_position = QPushButton(self.frame_signal_actions)
        self.btn_signal_go_position.setObjectName("btnSignalGoPosition")
        self.btn_signal_go_position.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )
        self.btn_signal_go_chart = QPushButton(self.frame_signal_actions)
        self.btn_signal_go_chart.setObjectName("btnSignalGoChart")
        self.btn_signal_go_chart.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )
        self.btn_signal_go_journal = QPushButton(self.frame_signal_actions)
        self.btn_signal_go_journal.setObjectName("btnSignalGoJournal")
        self.btn_signal_go_journal.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )
        button_layout.addStretch(1)
        button_layout.addWidget(self.btn_signal_go_position)
        button_layout.addWidget(self.btn_signal_go_chart)
        button_layout.addWidget(self.btn_signal_go_journal)
        button_layout.addStretch(1)
        layout.addWidget(self.frame_signal_actions, 3, 0, 1, 6)

        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(3, 1)
        layout.setColumnStretch(5, 1)
        self.ui.verticalLayoutSignals.insertWidget(0, self.frame_signal_filters)

        for combo in (
            self.cmb_signal_result_filter,
            self.cmb_signal_direction_filter,
            self.cmb_signal_regime_filter,
            self.cmb_signal_reason_filter,
        ):
            combo.currentIndexChanged.connect(self._refresh_signal_view)
        self.tbl_signals.itemSelectionChanged.connect(self._refresh_signal_actions)
        self.btn_signal_go_position.clicked.connect(self._on_signal_go_position_clicked)
        self.btn_signal_go_chart.clicked.connect(self._on_signal_go_chart_clicked)
        self.btn_signal_go_journal.clicked.connect(self._on_signal_go_journal_clicked)
        self.btn_signal_date_jump.clicked.connect(self._on_signal_date_jump_clicked)
        self._refresh_signal_actions()
        self._sync_signal_date_jump(())

    @staticmethod
    def _set_filter_combo_items(
        combo: QComboBox,
        entries: Iterable[tuple[str, str]],
    ) -> None:
        current = str(combo.currentData() or WSP_FILTER_ALL)
        combo.blockSignals(True)
        try:
            combo.clear()
            for text, data in entries:
                combo.addItem(text, data)
            index = combo.findData(current)
            if index < 0:
                index = combo.findData(WSP_FILTER_ALL)
            combo.setCurrentIndex(max(index, 0))
        finally:
            combo.blockSignals(False)

    def _populate_snapshot_filters(self) -> None:
        all_text = self._tr("AlgorithmWorkspaceFilter.all", "All")
        direction_entries = (
            (all_text, WSP_FILTER_ALL),
            ("BUY", "BUY"),
            ("SELL", "SELL"),
        )
        pnl_entries = (
            (all_text, WSP_FILTER_ALL),
            (
                self._tr("AlgorithmWorkspaceFilter.pnlProfit", "Profit +"),
                WSP_FILTER_PROFIT,
            ),
            (self._tr("AlgorithmWorkspaceFilter.pnlLoss", "Loss -"), WSP_FILTER_LOSS),
            (self._tr("AlgorithmWorkspaceFilter.pnlZero", "Zero"), WSP_FILTER_ZERO),
        )

        self.lbl_signal_result_filter.setText(
            self._tr("AlgorithmWorkspaceFilter.result", "Result:")
        )
        self.lbl_signal_direction_filter.setText(
            self._tr("AlgorithmWorkspaceFilter.direction", "Direction:")
        )
        self.lbl_signal_reason_filter.setText(
            self._tr("AlgorithmWorkspaceFilter.reason", "Reason:")
        )
        self.lbl_signal_regime_filter.setText(
            self._tr("AlgorithmWorkspaceFilter.regime", "Regime:")
        )
        self._set_filter_combo_items(
            self.cmb_signal_result_filter,
            (
                (all_text, WSP_FILTER_ALL),
                (
                    self._tr("AlgorithmWorkspaceFilter.accepted", "Accepted"),
                    WSP_FILTER_ACCEPTED,
                ),
                (
                    self._tr("AlgorithmWorkspaceFilter.rejected", "Rejected"),
                    WSP_FILTER_REJECTED,
                ),
            ),
        )
        self._set_filter_combo_items(
            self.cmb_signal_direction_filter,
            direction_entries,
        )
        self._set_filter_combo_items(
            self.cmb_signal_regime_filter,
            (
                (all_text, WSP_FILTER_ALL),
                (
                    self._tr("AlgorithmWorkspaceAlligatorRegime.flat", "Flat"),
                    ALLIGATOR_REGIME_FLAT,
                ),
                (
                    self._tr(
                        "AlgorithmWorkspaceAlligatorRegime.trendUp",
                        "Trend up",
                    ),
                    ALLIGATOR_REGIME_TREND_UP,
                ),
                (
                    self._tr(
                        "AlgorithmWorkspaceAlligatorRegime.trendDown",
                        "Trend down",
                    ),
                    ALLIGATOR_REGIME_TREND_DOWN,
                ),
                (
                    self._tr(
                        "AlgorithmWorkspaceAlligatorRegime.warmup",
                        "Warm-up",
                    ),
                    ALLIGATOR_REGIME_WARMUP,
                ),
                (
                    self._tr(
                        "AlgorithmWorkspaceFilter.regimeUndefined",
                        "Not defined",
                    ),
                    WSP_FILTER_REGIME_UNDEFINED,
                ),
            ),
        )
        signal_codes = sorted(
            {
                code
                for record in self._signal_records
                for code in (
                    record.source_reason_code,
                    record.filter_reason_code,
                    record.risk_reason_code,
                )
                if code
            }
        )
        self._set_filter_combo_items(
            self.cmb_signal_reason_filter,
            ((all_text, WSP_FILTER_ALL),)
            + tuple(
                (workspace_signal_reason_code_text(code, self._tr), code)
                for code in signal_codes
            ),
        )

        self.lbl_position_pnl_filter.setText(
            self._tr("AlgorithmWorkspaceFilter.pnl", "PnL:")
        )
        self.lbl_position_reason_filter.setText(
            self._tr("AlgorithmWorkspaceFilter.closeReason", "Close reason:")
        )
        self.lbl_position_direction_filter.setText(
            self._tr("AlgorithmWorkspaceFilter.direction", "Direction:")
        )
        self.lbl_position_status_filter.setText(
            self._tr("AlgorithmWorkspaceFilter.status", "Status:")
        )
        self._set_filter_combo_items(self.cmb_position_pnl_filter, pnl_entries)
        self._set_filter_combo_items(
            self.cmb_position_direction_filter,
            direction_entries,
        )
        self._set_filter_combo_items(
            self.cmb_position_status_filter,
            (
                (all_text, WSP_FILTER_ALL),
                (
                    self._translated_code("OPEN", POSITION_STATUS_LABELS),
                    WSP_FILTER_OPEN,
                ),
                (
                    self._translated_code("CLOSED", POSITION_STATUS_LABELS),
                    WSP_FILTER_CLOSED,
                ),
            ),
        )
        position_reasons = sorted(
            {
                reason
                for position in self._owned_snapshot.positions
                if (reason := self._position_close_reason_code(position))
            }
        )
        self._set_filter_combo_items(
            self.cmb_position_reason_filter,
            ((all_text, WSP_FILTER_ALL),)
            + tuple(
                (
                    self._translated_code(reason, POSITION_CLOSE_REASON_LABELS),
                    reason,
                )
                for reason in position_reasons
            ),
        )

        self.lbl_order_status_filter.setText(
            self._tr("AlgorithmWorkspaceFilter.status", "Status:")
        )
        self.lbl_order_direction_filter.setText(
            self._tr("AlgorithmWorkspaceFilter.direction", "Direction:")
        )
        self.lbl_order_pnl_filter.setText(
            self._tr("AlgorithmWorkspaceFilter.pnl", "PnL:")
        )
        self.lbl_order_reason_filter.setText(
            self._tr("AlgorithmWorkspaceFilter.reason", "Reason:")
        )
        self._set_filter_combo_items(
            self.cmb_order_direction_filter,
            direction_entries,
        )
        self._set_filter_combo_items(self.cmb_order_pnl_filter, pnl_entries)
        order_statuses = sorted({order.status for order in self._owned_snapshot.orders})
        self._set_filter_combo_items(
            self.cmb_order_status_filter,
            ((all_text, WSP_FILTER_ALL),)
            + tuple((status, status) for status in order_statuses),
        )
        order_reasons = sorted(
            {
                str(order.close_reason).strip().upper()
                for order in self._owned_snapshot.orders
                if str(order.close_reason or "").strip()
            }
        )
        self._set_filter_combo_items(
            self.cmb_order_reason_filter,
            ((all_text, WSP_FILTER_ALL),)
            + tuple(
                (
                    self._translated_code(reason, POSITION_CLOSE_REASON_LABELS),
                    reason,
                )
                for reason in order_reasons
            ),
        )

    @staticmethod
    def _matches_pnl_filter(value: float, filter_code: str) -> bool:
        if filter_code == WSP_FILTER_ALL:
            return True
        if filter_code == WSP_FILTER_PROFIT:
            return value > 1e-12
        if filter_code == WSP_FILTER_LOSS:
            return value < -1e-12
        if filter_code == WSP_FILTER_ZERO:
            return abs(value) <= 1e-12
        return True

    @staticmethod
    def _signal_regime_code(record: WorkspaceSignalRecord) -> str | None:
        context = record.filter_context
        if context is None:
            return None
        regime = str(context.regime or "").strip().upper()
        if not regime or regime == ALLIGATOR_REGIME_DISABLED:
            return None
        return regime

    @classmethod
    def _matches_signal_regime_filter(
        cls,
        record: WorkspaceSignalRecord,
        filter_code: str,
    ) -> bool:
        if filter_code == WSP_FILTER_ALL:
            return True
        regime = cls._signal_regime_code(record)
        if filter_code == WSP_FILTER_REGIME_UNDEFINED:
            return regime is None
        return regime == filter_code

    def _refresh_signal_view(self, *_args: object) -> None:
        self.frame_signal_filters.setVisible(bool(self._signal_records))
        result_filter = str(
            self.cmb_signal_result_filter.currentData() or WSP_FILTER_ALL
        )
        direction_filter = str(
            self.cmb_signal_direction_filter.currentData() or WSP_FILTER_ALL
        )
        regime_filter = str(
            self.cmb_signal_regime_filter.currentData() or WSP_FILTER_ALL
        )
        reason_filter = str(
            self.cmb_signal_reason_filter.currentData() or WSP_FILTER_ALL
        )
        records = tuple(
            record
            for record in self._signal_records
            if (
                result_filter == WSP_FILTER_ALL
                or (result_filter == WSP_FILTER_ACCEPTED and record.accepted)
                or (result_filter == WSP_FILTER_REJECTED and not record.accepted)
            )
            and (
                direction_filter == WSP_FILTER_ALL
                or record.direction == direction_filter
            )
            and self._matches_signal_regime_filter(record, regime_filter)
            and (
                reason_filter == WSP_FILTER_ALL
                or reason_filter
                in {
                    record.source_reason_code,
                    record.filter_reason_code,
                    record.risk_reason_code,
                }
            )
        )
        self._populate_signal_rows(records)
        self._refresh_signal_actions()

    @staticmethod
    def _qdate_to_date(value: QDate) -> date:
        """Перетворити календарну QDate у date без часу й timezone."""
        return date(value.year(), value.month(), value.day())

    @staticmethod
    def _date_jump_target_row(
        row_dates: tuple[date | None, ...],
        target_date: date,
    ) -> int | None:
        """Знайти перший рядок на дату, інакше найближчий наступний."""
        exact_rows = [
            row for row, row_date in enumerate(row_dates) if row_date == target_date
        ]
        if exact_rows:
            return exact_rows[0]

        future = [
            (row_date, row)
            for row, row_date in enumerate(row_dates)
            if row_date is not None and row_date > target_date
        ]
        if future:
            _, row = min(future, key=lambda item: (item[0], item[1]))
            return row

        past = [
            (row_date, row)
            for row, row_date in enumerate(row_dates)
            if row_date is not None and row_date < target_date
        ]
        if not past:
            return None
        _, row = max(past, key=lambda item: (item[0], item[1]))
        return row

    @staticmethod
    def _sync_date_jump_widget(
        editor: QDateEdit,
        button: QPushButton,
        dates: tuple[date, ...],
    ) -> None:
        """Обмежити календар реально видимим діапазоном таблиці."""
        if not dates:
            editor.setEnabled(False)
            button.setEnabled(False)
            return

        first_date = min(dates)
        last_date = max(dates)
        minimum = QDate(first_date.year, first_date.month, first_date.day)
        maximum = QDate(last_date.year, last_date.month, last_date.day)
        editor.setDateRange(minimum, maximum)
        if not bool(editor.property("lgeDateJumpInitialized")):
            editor.setDate(minimum)
            editor.setProperty("lgeDateJumpInitialized", True)
        editor.setEnabled(True)
        button.setEnabled(True)

    @staticmethod
    def _select_date_jump_row(table: QTableWidget, row: int | None) -> bool:
        """Виділити й прокрутити таблицю до знайденого date-jump рядка."""
        if row is None or row < 0 or row >= table.rowCount():
            return False
        item = table.item(row, 0)
        if item is None:
            return False
        table.selectRow(row)
        table.setCurrentCell(row, 0)
        table.scrollToItem(
            item,
            QAbstractItemView.ScrollHint.PositionAtCenter,
        )
        table.setFocus()
        return True

    def _sync_signal_date_jump(
        self,
        records: tuple[WorkspaceSignalRecord, ...],
    ) -> None:
        has_records = bool(records)
        self.lbl_signal_date_jump.setVisible(has_records)
        self.dte_signal_date_jump.setVisible(has_records)
        self.btn_signal_date_jump.setVisible(has_records)
        self.frame_signal_actions.setVisible(has_records)
        dates = tuple(record.timestamp.date() for record in records)
        self._sync_date_jump_widget(
            self.dte_signal_date_jump,
            self.btn_signal_date_jump,
            dates,
        )

    def _on_signal_date_jump_clicked(self) -> None:
        """Перейти до першого видимого signal на вибрану календарну дату."""
        record_by_uid = {record.signal_uid: record for record in self._signal_records}
        row_dates: list[date | None] = []
        for row in range(self.tbl_signals.rowCount()):
            item = self.tbl_signals.item(row, 0)
            signal_uid = (
                str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
                if item is not None
                else ""
            )
            record = record_by_uid.get(signal_uid)
            row_dates.append(record.timestamp.date() if record is not None else None)
        target_row = self._date_jump_target_row(
            tuple(row_dates),
            self._qdate_to_date(self.dte_signal_date_jump.date()),
        )
        self._select_date_jump_row(self.tbl_signals, target_row)

    def _selected_signal_record(self) -> WorkspaceSignalRecord | None:
        row = self.tbl_signals.currentRow()
        if row < 0:
            return None
        item = self.tbl_signals.item(row, 0)
        if item is None:
            return None
        signal_uid = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
        if not signal_uid:
            return None
        return next(
            (
                record
                for record in self._signal_records
                if record.signal_uid == signal_uid
            ),
            None,
        )

    def _position_for_signal(
        self,
        signal_uid: str,
    ) -> WorkspacePositionSnapshot | None:
        normalized_uid = str(signal_uid or "").strip()
        if not normalized_uid:
            return None
        return next(
            (
                position
                for position in self._owned_snapshot.positions
                if str(position.signal_uid or "").strip() == normalized_uid
            ),
            None,
        )

    def _refresh_signal_actions(self) -> None:
        record = self._selected_signal_record()
        has_record = record is not None
        self.btn_signal_go_chart.setEnabled(has_record)
        self.btn_signal_go_journal.setEnabled(has_record)
        self.btn_signal_go_position.setEnabled(
            has_record and self._position_for_signal(record.signal_uid) is not None
        )

    def _on_signal_go_position_clicked(self) -> None:
        record = self._selected_signal_record()
        if record is None:
            return
        position = self._position_for_signal(record.signal_uid)
        if position is None:
            return

        for combo in (
            self.cmb_position_pnl_filter,
            self.cmb_position_reason_filter,
            self.cmb_position_direction_filter,
            self.cmb_position_status_filter,
        ):
            self._set_combo_by_data(combo, WSP_FILTER_ALL)
        self._refresh_position_view()
        self.tabs_workspace.setCurrentIndex(INDEX_BY_PANEL[WORKSPACE_PANEL_POSITION])

        for row in range(self.tbl_positions.rowCount()):
            item = self.tbl_positions.item(row, 0)
            if item is None:
                continue
            row_id = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
            if row_id != position.position_id:
                continue
            self.tbl_positions.selectRow(row)
            self.tbl_positions.scrollToItem(item)
            break

    def _on_signal_go_chart_clicked(self) -> None:
        """Перейти на exact signal candle і зафіксувати crosshair."""
        record = self._selected_signal_record()
        if record is None:
            return
        self.chart_timestamp_requested.emit(
            self.workspace_uid,
            record.timestamp,
            True,
        )

    @staticmethod
    def _signal_journal_search_text(record: WorkspaceSignalRecord) -> str:
        """Повернути читабельний UTC-час сигналу для пошуку в Journal."""
        return record.timestamp.strftime("%Y-%m-%d %H:%M:%S")

    def _on_signal_go_journal_clicked(self) -> None:
        record = self._selected_signal_record()
        if record is None:
            return
        self._set_combo_by_data(self.cmb_journal_category, "ALL")
        self._set_combo_by_data(self.cmb_journal_level, JOURNAL_LEVEL_ALL)
        self.tabs_workspace.setCurrentIndex(INDEX_BY_PANEL[WORKSPACE_PANEL_LOG])
        self.edt_journal_search.setText(self._signal_journal_search_text(record))
        self.edt_journal_search.setFocus()
        self._refresh_journal_view()
        scrollbar = self.ui.txtLog.verticalScrollBar()
        scrollbar.setValue(scrollbar.minimum())
        self.ui.txtLog.setFocus()

    def _refresh_position_view(self, *_args: object) -> None:
        self.frame_position_filters.setVisible(bool(self._owned_snapshot.positions))
        pnl_filter = str(self.cmb_position_pnl_filter.currentData() or WSP_FILTER_ALL)
        reason_filter = str(
            self.cmb_position_reason_filter.currentData() or WSP_FILTER_ALL
        )
        direction_filter = str(
            self.cmb_position_direction_filter.currentData() or WSP_FILTER_ALL
        )
        status_filter = str(
            self.cmb_position_status_filter.currentData() or WSP_FILTER_ALL
        )
        positions = tuple(
            position
            for position in self._owned_snapshot.positions
            if self._matches_pnl_filter(position.current_profit, pnl_filter)
            and (
                reason_filter == WSP_FILTER_ALL
                or self._position_close_reason_code(position) == reason_filter
            )
            and (
                direction_filter == WSP_FILTER_ALL or position.side == direction_filter
            )
            and (
                status_filter == WSP_FILTER_ALL
                or (status_filter == WSP_FILTER_OPEN and position.active)
                or (status_filter == WSP_FILTER_CLOSED and not position.active)
            )
        )
        self._populate_position_rows(positions)
        self._refresh_position_time_actions()

    def _sync_position_date_jump(
        self,
        positions: tuple[WorkspacePositionSnapshot, ...],
    ) -> None:
        has_positions = bool(positions)
        self.lbl_position_date_jump.setVisible(has_positions)
        self.dte_position_date_jump.setVisible(has_positions)
        self.btn_position_date_jump.setVisible(has_positions)
        self.frame_position_time_actions.setVisible(has_positions)
        dates = tuple(
            timestamp.date()
            for position in positions
            if (timestamp := self._position_timestamp(position.opened_at)) is not None
        )
        self._sync_date_jump_widget(
            self.dte_position_date_jump,
            self.btn_position_date_jump,
            dates,
        )

    def _on_position_date_jump_clicked(self) -> None:
        """Перейти до position за датою фактичного відкриття."""
        position_by_id = {
            position.position_id: position
            for position in self._owned_snapshot.positions
        }
        row_dates: list[date | None] = []
        for row in range(self.tbl_positions.rowCount()):
            item = self.tbl_positions.item(row, 0)
            position_id = (
                str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
                if item is not None
                else ""
            )
            position = position_by_id.get(position_id)
            timestamp = (
                self._position_timestamp(position.opened_at)
                if position is not None
                else None
            )
            row_dates.append(timestamp.date() if timestamp is not None else None)
        target_row = self._date_jump_target_row(
            tuple(row_dates),
            self._qdate_to_date(self.dte_position_date_jump.date()),
        )
        self._select_date_jump_row(self.tbl_positions, target_row)

    def _selected_position_snapshot(self) -> WorkspacePositionSnapshot | None:
        row = self.tbl_positions.currentRow()
        if row < 0:
            return None
        item = self.tbl_positions.item(row, 0)
        if item is None:
            return None
        position_id = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
        if not position_id:
            return None
        return next(
            (
                position
                for position in self._owned_snapshot.positions
                if position.position_id == position_id
            ),
            None,
        )

    @staticmethod
    def _position_timestamp(value: str | None) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _signal_for_position(
        self,
        position: WorkspacePositionSnapshot,
    ) -> WorkspaceSignalRecord | None:
        """Знайти signal для position за UID або часом і напрямком."""
        signal_uid = str(position.signal_uid or "").strip()
        if signal_uid:
            match = next(
                (
                    record
                    for record in self._signal_records
                    if record.signal_uid == signal_uid
                ),
                None,
            )
            if match is not None:
                return match

        timestamp = self._position_timestamp(position.signal_timestamp)
        if timestamp is None:
            return None
        return next(
            (
                record
                for record in self._signal_records
                if record.timestamp == timestamp and record.direction == position.side
            ),
            None,
        )

    def _refresh_position_time_actions(self) -> None:
        position = self._selected_position_snapshot()
        signal = self._signal_for_position(position) if position is not None else None
        entry_timestamp = (
            self._position_timestamp(position.opened_at)
            if position is not None
            else None
        )
        self.btn_position_go_signal.setEnabled(signal is not None)
        self.btn_position_go_entry.setEnabled(entry_timestamp is not None)

    def _on_position_go_signal_clicked(self) -> None:
        """Перейти з position до exact signal row, а не одразу на chart."""
        position = self._selected_position_snapshot()
        if position is None:
            return
        record = self._signal_for_position(position)
        if record is None:
            return

        for combo in (
            self.cmb_signal_result_filter,
            self.cmb_signal_direction_filter,
            self.cmb_signal_regime_filter,
            self.cmb_signal_reason_filter,
        ):
            self._set_combo_by_data(combo, WSP_FILTER_ALL)
        self._refresh_signal_view()
        self.tabs_workspace.setCurrentIndex(INDEX_BY_PANEL[WORKSPACE_PANEL_SIGNALS])

        for row in range(self.tbl_signals.rowCount()):
            item = self.tbl_signals.item(row, 0)
            if item is None:
                continue
            row_id = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
            if row_id != record.signal_uid:
                continue
            self.tbl_signals.selectRow(row)
            self.tbl_signals.scrollToItem(item)
            break

    def _on_position_go_entry_clicked(self) -> None:
        position = self._selected_position_snapshot()
        if position is None:
            return
        timestamp = self._position_timestamp(position.opened_at)
        if timestamp is not None:
            self.chart_timestamp_requested.emit(self.workspace_uid, timestamp, False)

    def _refresh_order_view(self, *_args: object) -> None:
        self.frame_order_filters.setVisible(bool(self._owned_snapshot.orders))
        status_filter = str(
            self.cmb_order_status_filter.currentData() or WSP_FILTER_ALL
        )
        direction_filter = str(
            self.cmb_order_direction_filter.currentData() or WSP_FILTER_ALL
        )
        pnl_filter = str(self.cmb_order_pnl_filter.currentData() or WSP_FILTER_ALL)
        reason_filter = str(
            self.cmb_order_reason_filter.currentData() or WSP_FILTER_ALL
        )
        orders = tuple(
            order
            for order in self._owned_snapshot.orders
            if (status_filter == WSP_FILTER_ALL or order.status == status_filter)
            and (direction_filter == WSP_FILTER_ALL or order.side == direction_filter)
            and self._matches_pnl_filter(order.profit, pnl_filter)
            and (
                reason_filter == WSP_FILTER_ALL
                or str(order.close_reason or "").strip().upper() == reason_filter
            )
        )
        self._populate_order_rows(orders)

    def _setup_journal_filters(self) -> None:
        self.frame_journal_filters = QFrame(self.ui.tabLog)
        self.frame_journal_filters.setObjectName("frameJournalFilters")
        layout = QGridLayout(self.frame_journal_filters)
        layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_journal_category = QLabel(self.frame_journal_filters)
        self.lbl_journal_category.setObjectName("lblJournalCategory")
        self.cmb_journal_category = QComboBox(self.frame_journal_filters)
        self.cmb_journal_category.setObjectName("cmbJournalCategory")

        self.lbl_journal_level = QLabel(self.frame_journal_filters)
        self.lbl_journal_level.setObjectName("lblJournalLevel")
        self.cmb_journal_level = QComboBox(self.frame_journal_filters)
        self.cmb_journal_level.setObjectName("cmbJournalLevel")

        self.lbl_journal_search = QLabel(self.frame_journal_filters)
        self.lbl_journal_search.setObjectName("lblJournalSearch")
        self.edt_journal_search = QLineEdit(self.frame_journal_filters)
        self.edt_journal_search.setObjectName("edtJournalSearch")
        self.edt_journal_search.setClearButtonEnabled(True)

        self.chk_journal_market_ticks = QCheckBox(self.frame_journal_filters)
        self.chk_journal_market_ticks.setObjectName("chkJournalMarketTicks")
        self.chk_journal_market_ticks.setChecked(False)

        layout.addWidget(self.lbl_journal_category, 0, 0)
        layout.addWidget(self.cmb_journal_category, 0, 1)
        layout.addWidget(self.lbl_journal_level, 0, 2)
        layout.addWidget(self.cmb_journal_level, 0, 3)
        layout.addWidget(self.lbl_journal_search, 1, 0)
        layout.addWidget(self.edt_journal_search, 1, 1, 1, 3)
        layout.addWidget(self.chk_journal_market_ticks, 2, 0, 1, 4)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(3, 1)
        self.ui.verticalLayoutLog.insertWidget(0, self.frame_journal_filters)

        self.ui.txtLog.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.ui.txtLog.installEventFilter(self)
        self.cmb_journal_category.currentIndexChanged.connect(
            self._refresh_journal_view
        )
        self.cmb_journal_level.currentIndexChanged.connect(self._refresh_journal_view)
        self.chk_journal_market_ticks.toggled.connect(self._refresh_journal_view)
        self.edt_journal_search.textChanged.connect(self._refresh_journal_view)

    def _populate_journal_filters(self) -> None:
        category_data = self.cmb_journal_category.currentData() or "ALL"
        level_data = self.cmb_journal_level.currentData() or JOURNAL_LEVEL_ALL

        self.cmb_journal_category.blockSignals(True)
        self.cmb_journal_level.blockSignals(True)
        try:
            self.cmb_journal_category.clear()
            category_entries = (
                ("AlgorithmWorkspaceJournal.categoryAll", "All", "ALL"),
                (
                    "AlgorithmWorkspaceJournal.categoryRuntime",
                    "Runtime",
                    "RUNTIME",
                ),
                (
                    "AlgorithmWorkspaceJournal.categoryMarket",
                    "Market",
                    "MARKET",
                ),
                (
                    "AlgorithmWorkspaceJournal.categorySignal",
                    "Signal",
                    "SIGNAL",
                ),
                (
                    "AlgorithmWorkspaceJournal.categoryGuard",
                    "Guard",
                    "GUARD",
                ),
                (
                    "AlgorithmWorkspaceJournal.categoryBroker",
                    "Broker",
                    "BROKER",
                ),
                (
                    "AlgorithmWorkspaceJournal.categoryError",
                    "Error",
                    "ERROR",
                ),
            )
            for key, fallback, value in category_entries:
                self.cmb_journal_category.addItem(
                    self._tr(key, fallback),
                    value,
                )

            self.cmb_journal_level.clear()
            level_entries = (
                (
                    "AlgorithmWorkspaceJournal.levelAll",
                    "All",
                    JOURNAL_LEVEL_ALL,
                ),
                (
                    "AlgorithmWorkspaceJournal.levelInfo",
                    "Information",
                    JOURNAL_LEVEL_INFO,
                ),
                (
                    "AlgorithmWorkspaceJournal.levelWarning",
                    "Warning",
                    JOURNAL_LEVEL_WARNING,
                ),
                (
                    "AlgorithmWorkspaceJournal.levelError",
                    "Error",
                    JOURNAL_LEVEL_ERROR,
                ),
            )
            for key, fallback, value in level_entries:
                self.cmb_journal_level.addItem(
                    self._tr(key, fallback),
                    value,
                )

            self._set_combo_by_data(
                self.cmb_journal_category,
                str(category_data),
            )
            self._set_combo_by_data(
                self.cmb_journal_level,
                str(level_data),
            )
        finally:
            self.cmb_journal_category.blockSignals(False)
            self.cmb_journal_level.blockSignals(False)

        self.lbl_journal_category.setText(
            self._tr("AlgorithmWorkspaceJournal.lblCategory", "Category:")
        )
        self.lbl_journal_level.setText(
            self._tr("AlgorithmWorkspaceJournal.lblLevel", "Level:")
        )
        self.lbl_journal_search.setText(
            self._tr("AlgorithmWorkspaceJournal.lblSearch", "Search:")
        )
        self.edt_journal_search.setPlaceholderText(
            self._tr(
                "AlgorithmWorkspaceJournal.searchPlaceholder",
                "Event, code or text...",
            )
        )
        self.chk_journal_market_ticks.setText(
            self._tr(
                "AlgorithmWorkspaceJournal.showMarketTicks",
                "Show every market tick",
            )
        )

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Перехопити navigation keys Journal для переходу між compact summary."""
        if (
            watched is self.ui.txtLog
            and isinstance(event, QKeyEvent)
            and event.type() == QEvent.Type.KeyPress
            and event.modifiers() == Qt.KeyboardModifier.NoModifier
        ):
            action_by_key: dict[int, str] = {
                Qt.Key.Key_PageUp.value: "PAGE_UP",
                Qt.Key.Key_PageDown.value: "PAGE_DOWN",
                Qt.Key.Key_Home.value: "HOME",
                Qt.Key.Key_End.value: "END",
            }
            action = action_by_key.get(event.key())
            if action is not None and self._navigate_journal_summary(action):
                return True
        return super().eventFilter(watched, event)

    @staticmethod
    def _journal_summary_positions(text: str, marker: str) -> tuple[int, ...]:
        """Повернути offsets усіх compact summary у поточному Journal text."""
        if not text or not marker:
            return ()
        positions: list[int] = []
        offset = 0
        while True:
            position = text.find(marker, offset)
            if position < 0:
                break
            positions.append(position)
            offset = position + len(marker)
        return tuple(positions)

    @staticmethod
    def _journal_summary_target_position(
        positions: tuple[int, ...],
        current_position: int,
        action: str,
    ) -> int | None:
        """Обрати compact summary для PageUp/PageDown/Home/End."""
        if not positions:
            return None
        normalized_action = str(action or "").strip().upper()
        if normalized_action == "HOME":
            return positions[0]
        if normalized_action == "END":
            return positions[-1]
        if normalized_action == "PAGE_DOWN":
            return next(
                (position for position in positions if position > current_position),
                positions[-1],
            )
        if normalized_action == "PAGE_UP":
            return next(
                (
                    position
                    for position in reversed(positions)
                    if position < current_position
                ),
                positions[0],
            )
        return None

    def _navigate_journal_summary(self, action: str) -> bool:
        """Перемістити cursor Journal на потрібний compact summary."""
        text = self.ui.txtLog.toPlainText()
        marker = self._tr(
            "AlgorithmWorkspaceSignalSummary.header",
            "************************************ DECISION SUMMARY "
            "************************************",
        )
        positions = self._journal_summary_positions(text, marker)
        cursor = self.ui.txtLog.textCursor()
        target = self._journal_summary_target_position(
            positions,
            cursor.position(),
            action,
        )
        if target is None:
            return False
        cursor.setPosition(target)
        self.ui.txtLog.setTextCursor(cursor)
        self.ui.txtLog.centerCursor()
        return True

    def clear_journal(self) -> None:
        """Clear the WSP-local journal cache and visible text."""
        self._journal_entries.clear()
        self._refresh_journal_view()

    def append_journal_entries(
        self,
        entries: Iterable[WorkspaceJournalEntry],
    ) -> None:
        """Append immutable runtime entries and reapply visible filters."""
        self._journal_entries.extend(entries)
        self._refresh_journal_view()

    @staticmethod
    def _journal_search_variants(value: str) -> tuple[str, ...]:
        text = str(value or "").strip().casefold()
        if not text:
            return ()
        variants = {text}
        if (
            len(text) > 10
            and text[4:5] == "-"
            and text[7:8] == "-"
            and text[10:11] in {" ", "t"}
        ):
            variants.add(text[:10] + "t" + text[11:])
            variants.add(text[:10] + " " + text[11:])
        return tuple(variants)

    @staticmethod
    def _journal_entry_search_text(
        entry: WorkspaceJournalEntry,
        line: str,
    ) -> str:
        """Додати structured details до пошукового індексу без зміни Journal UI."""
        detail_text = " ".join(f"{key}={value}" for key, value in entry.details.items())
        return f"{line} {detail_text}".casefold()

    def _refresh_journal_view(self, *_args: object) -> None:
        category_filter = str(self.cmb_journal_category.currentData() or "ALL")
        level_filter = str(self.cmb_journal_level.currentData() or JOURNAL_LEVEL_ALL)
        show_market_ticks = self.chk_journal_market_ticks.isChecked()
        search_variants = self._journal_search_variants(self.edt_journal_search.text())

        visible_lines: list[str] = []
        allowed_categories = JOURNAL_CATEGORY_GROUPS.get(
            category_filter,
            frozenset(),
        )
        for entry in self._journal_entries:
            if allowed_categories and entry.category not in allowed_categories:
                continue
            if (
                level_filter != JOURNAL_LEVEL_ALL
                and self._journal_entry_level(entry) != level_filter
            ):
                continue
            if not show_market_ticks and self._is_live_tick_entry(entry):
                continue
            line = self._format_journal_entry_for_display(entry)
            searchable_text = self._journal_entry_search_text(entry, line)
            if search_variants and not any(
                variant in searchable_text for variant in search_variants
            ):
                continue
            visible_lines.append(line)

        if visible_lines:
            self.ui.txtLog.setPlainText("\n\n".join(visible_lines))
            scrollbar = self.ui.txtLog.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            return

        self.ui.txtLog.setPlainText(
            self._tr(
                "AlgorithmWorkspaceJournal.empty",
                "No journal entries match the selected filters.",
            )
        )

    def _format_journal_entry_for_display(
        self,
        entry: WorkspaceJournalEntry,
    ) -> str:
        """Translate safety-critical journal records at the UI boundary."""
        timestamp_text = entry.timestamp.astimezone(UTC).isoformat(
            timespec="milliseconds"
        )
        event = str(entry.event or "").strip().upper()
        details = entry.details

        if event in {"SAFETY_HOLD_ENTERED", "SAFETY_HOLD_UPDATED"}:
            category = self._tr(
                "AlgorithmWorkspaceJournal.categorySafety",
                "Safety",
            )
            event_text = self._tr(
                (
                    "AlgorithmWorkspaceJournal.safetyHoldEntered"
                    if event == "SAFETY_HOLD_ENTERED"
                    else "AlgorithmWorkspaceJournal.safetyHoldUpdated"
                ),
                (
                    "SAFETY HOLD ENTERED"
                    if event == "SAFETY_HOLD_ENTERED"
                    else "SAFETY HOLD UPDATED"
                ),
            )
            account_id = str(
                details.get("account_id") or self._safety_hold_account_id or "—"
            )
            symbol = str(
                details.get("symbol") or self._safety_hold_symbol or "—"
            ).upper()
            signed_volume = self._safe_float(
                details.get(
                    "signed_volume",
                    self._safety_hold_signed_volume,
                )
            )
            side, volume = self._safety_side_and_volume(signed_volume)
            evidence = self._safety_evidence_text(
                details.get("evidence_status") or self._safety_hold_evidence_status
            )
            message = self._tr(
                "AlgorithmWorkspaceJournal.safetyHoldActiveMessage",
                "Account {account_id}, symbol {symbol}: external exposure "
                "{side} {volume}; evidence {evidence}. New LGE signals and "
                "orders are blocked; market data continues. Open Orders, "
                "select the external exposure row and click Resolve "
                "reconciliation.",
            ).format(
                account_id=account_id,
                symbol=symbol,
                side=side,
                volume=volume,
                evidence=evidence,
            )
            return f"{timestamp_text} [{category}] {event_text}: {message}"

        if event == "SAFETY_HOLD_CLEARED":
            category = self._tr(
                "AlgorithmWorkspaceJournal.categorySafety",
                "Safety",
            )
            event_text = self._tr(
                "AlgorithmWorkspaceJournal.safetyHoldCleared",
                "SAFETY HOLD CLEARED",
            )
            message = self._tr(
                "AlgorithmWorkspaceJournal.safetyHoldClearedMessage",
                "Current broker evidence cleared the external exposure. "
                "LGE is waiting for a fresh live spread before execution "
                "can resume.",
            )
            return f"{timestamp_text} [{category}] {event_text}: {message}"

        if entry.category == "SIGNAL" and event in {
            "SIGNAL_ACCEPTED",
            "SIGNAL_REJECTED",
            "CANDIDATE_F_RELEASE",
            "CANDIDATE_F_CANCEL",
            "CANDIDATE_F_EXPIRE",
        }:
            signal_uid = str(details.get("signal_uid") or "").strip()
            record = self._signal_record_by_uid(signal_uid)
            if record is not None:
                return build_workspace_signal_journal_text(
                    record,
                    self._tr,
                    journal_timestamp=entry.timestamp,
                    event=event,
                )

        if event == "STARTUP_PHASE_CHANGED":
            previous_phase = str(details.get("previous_phase") or "")
            target_phase = str(details.get("target_phase") or "")
            safety_phase = WORKSPACE_STARTUP_PHASE_SAFETY_HOLD_EXTERNAL_EXPOSURE
            if target_phase == safety_phase or previous_phase == safety_phase:
                category = self._tr(
                    "AlgorithmWorkspaceJournal.categorySafety",
                    "Safety",
                )
                previous_text = self._translated_code(
                    previous_phase,
                    WORKSPACE_STARTUP_PHASE_LABELS,
                )
                target_text = self._translated_code(
                    target_phase,
                    WORKSPACE_STARTUP_PHASE_LABELS,
                )
                event_text = self._tr(
                    "AlgorithmWorkspaceJournal.safetyPhaseChanged",
                    "SAFETY PHASE CHANGED",
                )
                message = self._tr(
                    "AlgorithmWorkspaceJournal.safetyPhaseChangedMessage",
                    "{previous_phase} → {target_phase}. New LGE execution is "
                    "blocked while read-only market data continues.",
                ).format(
                    previous_phase=previous_text,
                    target_phase=target_text,
                )
                return f"{timestamp_text} [{category}] {event_text}: {message}"

        return entry.format_line()

    def _signal_record_by_uid(
        self,
        signal_uid: str,
    ) -> WorkspaceSignalRecord | None:
        """Знайти immutable signal evidence для читабельного Journal block."""
        normalized_uid = str(signal_uid or "").strip()
        if not normalized_uid:
            return None
        for record in reversed(self._signal_records):
            if record.signal_uid == normalized_uid:
                return record
        return None

    def _execution_safety_hold_tooltip(self) -> str:
        """Build actionable localized guidance for a WSP safety hold."""
        side, volume = self._safety_side_and_volume(self._safety_hold_signed_volume)
        evidence = self._safety_evidence_text(self._safety_hold_evidence_status)
        return self._tr(
            "AlgorithmWorkspaceWindow.safetyHoldTooltip",
            "LGE EXCLUSIVE paused new LGE signals and orders; market data "
            "continues. Account: {account_id}; symbol: {symbol}; external "
            "exposure: {side} {volume}; evidence: {evidence}. Open Orders, "
            "select the external exposure row and click Resolve "
            "reconciliation to see the exact TWS identifiers. After resolving "
            "the position or orphaned protection in TWS, press Refresh. Use "
            "Monitoring to return to this WSP and inspect its journal.",
        ).format(
            account_id=self._safety_hold_account_id or "—",
            symbol=self._safety_hold_symbol or "—",
            side=side,
            volume=volume,
            evidence=evidence,
        )

    def _safety_side_and_volume(self, signed_volume: float) -> tuple[str, str]:
        value = self._safe_float(signed_volume)
        if value > 0.0:
            side = self._tr("AlgorithmWorkspaceSafety.sideBuy", "BUY")
        elif value < 0.0:
            side = self._tr("AlgorithmWorkspaceSafety.sideSell", "SELL")
        else:
            side = self._tr("AlgorithmWorkspaceSafety.sideUnknown", "UNKNOWN")
        volume = f"{abs(value):,.10f}".rstrip("0").rstrip(".")
        return side, volume.replace(",", " ") or "0"

    def _safety_evidence_text(self, value: object) -> str:
        status = str(value or "").strip().upper()
        mapping = {
            "CONFIRMED": (
                "AlgorithmWorkspaceSafety.evidenceConfirmed",
                "Confirmed",
            ),
            "STALE": (
                "AlgorithmWorkspaceSafety.evidenceStale",
                "Needs broker confirmation",
            ),
            "CLEARED": (
                "AlgorithmWorkspaceSafety.evidenceCleared",
                "Cleared",
            ),
            "EVIDENCE_UNAVAILABLE": (
                "AlgorithmWorkspaceSafety.evidenceUnavailable",
                "Evidence unavailable",
            ),
        }
        key_fallback = mapping.get(status)
        if key_fallback is None:
            return status or "—"
        return self._tr(*key_fallback)

    @staticmethod
    def _safe_float(value: object) -> float:
        try:
            numeric = float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0
        return numeric if math.isfinite(numeric) else 0.0

    @staticmethod
    def _is_live_tick_entry(entry: WorkspaceJournalEntry) -> bool:
        return bool(
            entry.category == "MARKET"
            and entry.event == "EVENT_ACCEPTED"
            and entry.details.get("origin") == "LIVE_READ_ONLY"
        )

    @staticmethod
    def _journal_entry_level(entry: WorkspaceJournalEntry) -> str:
        event = entry.event.upper()
        if entry.category == "ERROR" or any(
            token in event for token in ("ERROR", "FAILED", "FAILURE")
        ):
            return JOURNAL_LEVEL_ERROR
        if any(
            token in event
            for token in (
                "BLOCKED",
                "REJECTED",
                "STALE",
                "DISCONNECT",
                "TIMEOUT",
            )
        ):
            return JOURNAL_LEVEL_WARNING
        return JOURNAL_LEVEL_INFO

    def set_owned_snapshot(self, snapshot: WorkspaceOwnedSnapshot) -> None:
        """Show only exact WSP-owned order and position rows."""
        self._owned_snapshot = snapshot
        self.chart_widget.set_owned_snapshot(snapshot)
        self._populate_snapshot_filters()
        self._refresh_order_view()
        self._refresh_position_view()
        self._refresh_signal_actions()

    def set_signal_records(
        self,
        records: tuple[WorkspaceSignalRecord, ...],
    ) -> None:
        """Show the current-run accepted and rejected WSP signals."""
        self._signal_records = tuple(records)
        self._populate_snapshot_filters()
        self._refresh_signal_view()

    def set_chart_snapshot(self, snapshot: WorkspaceChartSnapshot) -> None:
        """Render bounded WSP market history supplied by WorkspaceRuntime."""
        self.chart_widget.set_snapshot(snapshot)

    def set_chart_execution_event(
        self,
        event: WorkspaceMarketEvent | None,
    ) -> None:
        """Передати M1 execution event у diagnostic overlay price chart."""
        self.chart_widget.set_execution_event(event)

    def _populate_signal_rows(
        self,
        records: tuple[WorkspaceSignalRecord, ...],
    ) -> None:
        table = self.tbl_signals
        first_population = table.rowCount() == 0 and bool(records)
        table.setUpdatesEnabled(False)
        try:
            table.clearContents()
            table.setRowCount(len(records))
            for row, record in enumerate(records):
                decision = self._tr(
                    "AlgorithmWorkspaceWindow.signalAccepted",
                    "Accepted",
                )
                if not record.accepted:
                    decision = self._tr(
                        "AlgorithmWorkspaceWindow.signalRejected",
                        "Rejected",
                    )
                presentation = build_workspace_signal_presentation(
                    record,
                    self._tr,
                )
                values = (
                    record.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    record.signal_type,
                    record.direction,
                    self._format_number(record.strength),
                    record.macd_state,
                    record.alligator_confirmation,
                    workspace_signal_alligator_regime_text(record, self._tr),
                    workspace_signal_timeframe_mode_text(record),
                    workspace_signal_profile_revision_text(record),
                    record.spread_status,
                    f"{record.filter_decision} / {decision}",
                    presentation.reason_text,
                )
                self._set_table_row(
                    table,
                    row,
                    values,
                    numeric_columns={3},
                    row_id=record.signal_uid,
                )
                reason_item = table.item(row, SIGNAL_TABLE_REASON_COLUMN)
                if reason_item is not None:
                    reason_item.setToolTip(presentation.tooltip_text)
        finally:
            table.setUpdatesEnabled(True)

        has_signals = bool(records)
        self._sync_signal_date_jump(records)
        if first_population:
            table.horizontalScrollBar().setValue(0)
        table.setVisible(has_signals)
        self.ui.lblSignalsPlaceholder.setVisible(not has_signals)

    def _populate_order_rows(
        self,
        orders: tuple[WorkspaceOrderSnapshot, ...],
    ) -> None:
        table = self.tbl_orders
        first_population = table.rowCount() == 0 and bool(orders)
        table.setUpdatesEnabled(False)
        try:
            table.clearContents()
            table.setRowCount(len(orders))
            for row, order in enumerate(orders):
                values = (
                    order.order_id,
                    self._display_text(order.broker_order_id),
                    order.side,
                    order.order_type,
                    self._format_number(order.volume),
                    self._format_number(order.price),
                    self._format_number(order.stop_loss),
                    self._format_number(order.take_profit),
                    order.status,
                    self._display_text(order.close_reason),
                    self._display_text(order.created_at),
                    self._format_profit(order.profit),
                )
                self._set_table_row(
                    table,
                    row,
                    values,
                    numeric_columns={4, 5, 6, 7, 11},
                    row_id=order.order_id,
                )
        finally:
            table.setUpdatesEnabled(True)

        broker_ids_visible = any(
            str(order.broker_order_id or "").strip() for order in orders
        )
        table.setColumnHidden(1, bool(orders) and not broker_ids_visible)
        if first_population:
            table.horizontalScrollBar().setValue(0)

    def _populate_position_rows(
        self,
        positions: tuple[WorkspacePositionSnapshot, ...],
    ) -> None:
        table = self.tbl_positions
        first_population = table.rowCount() == 0 and bool(positions)
        table.setUpdatesEnabled(False)
        try:
            table.clearContents()
            table.setRowCount(len(positions))
            for row, position in enumerate(positions):
                state_code = "OPEN" if position.active else "CLOSED"
                state_text = self._translated_code(
                    state_code,
                    POSITION_STATUS_LABELS,
                )
                close_reason_code = self._position_close_reason_code(position)
                close_reason_text = self._display_text(
                    self._translated_code(
                        close_reason_code,
                        POSITION_CLOSE_REASON_LABELS,
                    )
                    if close_reason_code
                    else ""
                )
                values = (
                    position.side,
                    self._format_number(position.volume),
                    self._format_number(position.entry_price),
                    self._format_number(position.current_price),
                    self._format_profit(position.current_profit),
                    self._format_profit(position.peak_profit),
                    f"{position.profit_drawdown:.1f}%",
                    self._format_number(position.stop_loss),
                    self._format_number(position.take_profit),
                    self._display_text(position.signal_timestamp),
                    self._display_text(position.opened_at),
                    self._display_text(position.closed_at),
                    state_text,
                    close_reason_text,
                )
                self._set_table_row(
                    table,
                    row,
                    values,
                    numeric_columns={1, 2, 3, 4, 5, 6, 7, 8},
                    row_id=position.position_id,
                )
                self._set_position_diagnostic_tooltips(
                    table,
                    row,
                    position,
                    state_text=state_text,
                    close_reason_code=close_reason_code,
                    close_reason_text=close_reason_text,
                )
        finally:
            table.setUpdatesEnabled(True)

        has_positions = bool(positions)
        self._sync_position_date_jump(positions)
        if first_population:
            table.horizontalScrollBar().setValue(0)
        table.setVisible(has_positions)
        self.ui.lblPositionPlaceholder.setVisible(not has_positions)
        self._refresh_position_time_actions()

    @staticmethod
    def _position_close_reason_code(
        position: WorkspacePositionSnapshot,
    ) -> str:
        reason = str(position.close_reason or "").strip().upper()
        if reason:
            return reason
        prefix = "REPLAY_VIRTUAL_CLOSED_"
        status = str(position.reconciliation_status or "").strip().upper()
        if status.startswith(prefix):
            return status[len(prefix) :]  # noqa
        return ""

    def _set_position_diagnostic_tooltips(
        self,
        table: QTableWidget,
        row: int,
        position: WorkspacePositionSnapshot,
        *,
        state_text: str,
        close_reason_code: str,
        close_reason_text: str,
    ) -> None:
        status_label = self._tr(
            "AlgorithmWorkspacePositionTooltip.status",
            "Status",
        )
        reason_label = self._tr(
            "AlgorithmWorkspacePositionTooltip.closeReason",
            "Close reason",
        )
        technical_status_label = self._tr(
            "AlgorithmWorkspacePositionTooltip.technicalStatus",
            "Technical status",
        )
        technical_reason_label = self._tr(
            "AlgorithmWorkspacePositionTooltip.technicalReason",
            "Reason code",
        )
        lines = [
            f"{status_label}: {state_text}",
            f"{technical_status_label}: {position.reconciliation_status}",
        ]
        if close_reason_code:
            lines.insert(1, f"{reason_label}: {close_reason_text}")
            lines.append(f"{technical_reason_label}: {close_reason_code}")
        tooltip = "\n".join(lines)
        for column in (12, 13):
            item = table.item(row, column)
            if item is not None:
                item.setToolTip(tooltip)

    @staticmethod
    def _set_table_row(
        table: QTableWidget,
        row: int,
        values: tuple[str, ...],
        *,
        numeric_columns: set[int],
        row_id: str,
    ) -> None:
        for column, text in enumerate(values):
            item = QTableWidgetItem(text)
            if text:
                item.setToolTip(text)
            if column in numeric_columns:
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
            if column == 0:
                item.setData(Qt.ItemDataRole.UserRole, row_id)
            table.setItem(row, column, item)

    @staticmethod
    def _display_text(value: object) -> str:
        text = str(value or "").strip()
        return text or "—"

    @staticmethod
    def _format_number(value: float | None) -> str:
        if value is None or not math.isfinite(value):
            return "—"
        rounded = round(value)
        if math.isclose(value, rounded, rel_tol=0.0, abs_tol=1e-12):
            return f"{int(rounded):,}".replace(",", " ")
        return f"{value:.8f}".rstrip("0").rstrip(".")

    @staticmethod
    def _format_profit(value: float) -> str:
        if not math.isfinite(value):
            return "—"
        return f"{value:+.2f}"

    def active_panel(self) -> str:
        return PANEL_BY_INDEX.get(
            self.tabs_workspace.currentIndex(),
            WORKSPACE_PANEL_CHART,
        )

    def _register_i18n_keys(self) -> None:
        if self._lang_mgr is None:
            return

        entries = {
            "AlgorithmWorkspaceWindow.btnStart": "START",
            "AlgorithmWorkspaceWindow.btnStop": "STOP",
            "AlgorithmWorkspaceWindow.btnHistoryDownload": "Download history",
            "AlgorithmWorkspaceWindow.btnReplaySettings": "Replay settings",
            "AlgorithmWorkspaceWindow.replayConfiguredTooltip": (
                "Historical Replay configured: {source}"
            ),
            "AlgorithmWorkspaceWindow.btnParameters": "Parameters",
            "AlgorithmWorkspaceWindow.btnRename": "Rename",
            "AlgorithmWorkspaceWindow.lblBroker": "Broker:",
            "AlgorithmWorkspaceWindow.lblAccount": "Account:",
            "AlgorithmWorkspaceWindow.accountRuntimeIdTooltip": (
                "Runtime account ID: {account_id}"
            ),
            "AlgorithmWorkspaceWindow.lblBalance": "Balance:",
            "AlgorithmWorkspaceWindow.replaySyntheticAccount": "Virtual Replay account",
            "AlgorithmWorkspaceWindow.replayAccountTooltip": (
                "This account exists only inside Replay and is not linked "
                "to IB or cTrader."
            ),
            "AlgorithmWorkspaceWindow.lblReplayEquity": "Replay equity:",
            "AlgorithmWorkspaceWindow.lblSymbol": "Symbol:",
            "AlgorithmWorkspaceWindow.lblTimeframe": "Timeframe:",
            "AlgorithmWorkspaceWindow.lblAlgorithm": "Algorithm:",
            "AlgorithmWorkspaceWindow.lblDataMode": "Data source:",
            "AlgorithmWorkspaceWindow.lblControlMode": "Control mode:",
            "AlgorithmWorkspaceWindow.lblOrders": "Orders:",
            "AlgorithmWorkspaceWindow.lblPositions": "Positions:",
            "AlgorithmWorkspaceWindow.lblCurrentProfit": "Profit:",
            "AlgorithmWorkspaceWindow.lblPeakProfit": "Peak:",
            "AlgorithmWorkspaceWindow.lblProfitDrawdown": "Pullback:",
            "AlgorithmWorkspaceWindow.lblReplayRealizedPnl": "Closed PnL:",
            "AlgorithmWorkspaceWindow.lblReplayBalance": "Replay balance:",
            "AlgorithmWorkspaceWindow.lblReplaySummaryEquity": "Replay equity:",
            "AlgorithmWorkspaceWindow.lblReplay": "Replay:",
            "AlgorithmWorkspaceWindow.btnReplayPause": "Pause",
            "AlgorithmWorkspaceWindow.btnReplayResume": "Resume",
            "AlgorithmWorkspaceWindow.btnReplayStep": "Step",
            "AlgorithmWorkspaceWindow.btnReplayTick": "Tick",
            "AlgorithmWorkspaceWindow.replayTickHint": (
                "Process one smallest Replay execution event."
            ),
            "AlgorithmWorkspaceWindow.replayTickLabel": "Tick",
            "AlgorithmWorkspaceWindow.lblReplaySpeed": "Speed:",
            "AlgorithmWorkspaceWindow.replaySpeedMax": "MAX",
            "AlgorithmWorkspaceWindow.replaySpeedMaxFast": "MAX FAST",
            "AlgorithmWorkspaceWindow.replayNotConnected": (
                "Historical Replay is stopped."
            ),
            "AlgorithmWorkspaceWindow.historyQuality": (
                "skipped {filtered} • gaps {gaps} • quotes {quotes}"
            ),
            "AlgorithmWorkspaceWindow.tabOrders": "Orders",
            "AlgorithmWorkspaceWindow.tabChart": "Chart",
            "AlgorithmWorkspaceWindow.tabPosition": "Position",
            "AlgorithmWorkspaceWindow.tabSignals": "Signals",
            "AlgorithmWorkspaceWindow.tabLog": "Log",
            "AlgorithmWorkspaceJournal.lblCategory": "Category:",
            "AlgorithmWorkspaceJournal.lblLevel": "Level:",
            "AlgorithmWorkspaceJournal.lblSearch": "Search:",
            "AlgorithmWorkspaceJournal.searchPlaceholder": "Event, code or text...",
            "AlgorithmWorkspaceFilter.all": "All",
            "AlgorithmWorkspaceFilter.result": "Result:",
            "AlgorithmWorkspaceFilter.direction": "Direction:",
            "AlgorithmWorkspaceFilter.reason": "Reason:",
            "AlgorithmWorkspaceFilter.regime": "Regime:",
            "AlgorithmWorkspaceFilter.regimeUndefined": "Not defined",
            "AlgorithmWorkspaceFilter.closeReason": "Close reason:",
            "AlgorithmWorkspaceFilter.status": "Status:",
            "AlgorithmWorkspaceFilter.pnl": "PnL:",
            "AlgorithmWorkspaceFilter.accepted": "Accepted",
            "AlgorithmWorkspaceFilter.rejected": "Rejected",
            "AlgorithmWorkspaceFilter.pnlProfit": "Profit +",
            "AlgorithmWorkspaceFilter.pnlLoss": "Loss -",
            "AlgorithmWorkspaceFilter.pnlZero": "Zero",
            "AlgorithmWorkspaceJournal.categoryAll": "All",
            "AlgorithmWorkspaceJournal.categoryRuntime": "Runtime",
            "AlgorithmWorkspaceJournal.categoryMarket": "Market",
            "AlgorithmWorkspaceJournal.categorySignal": "Signal",
            "AlgorithmWorkspaceJournal.categoryGuard": "Guard",
            "AlgorithmWorkspaceJournal.categoryBroker": "Broker",
            "AlgorithmWorkspaceJournal.categoryError": "Error",
            "AlgorithmWorkspaceJournal.levelAll": "All",
            "AlgorithmWorkspaceJournal.levelInfo": "Information",
            "AlgorithmWorkspaceJournal.levelWarning": "Warning",
            "AlgorithmWorkspaceJournal.levelError": "Error",
            "AlgorithmWorkspaceJournal.showMarketTicks": "Show every market tick",
            "AlgorithmWorkspaceJournal.empty": (
                "No journal entries match the selected filters."
            ),
            "AlgorithmWorkspaceWindow.colOrderId": "Order ID",
            "AlgorithmWorkspaceWindow.colBrokerOrderId": "Broker order ID",
            "AlgorithmWorkspaceWindow.colSide": "Side",
            "AlgorithmWorkspaceWindow.colOrderType": "Type",
            "AlgorithmWorkspaceWindow.colVolume": "Volume",
            "AlgorithmWorkspaceWindow.colPrice": "Price",
            "AlgorithmWorkspaceWindow.colStopLoss": "SL",
            "AlgorithmWorkspaceWindow.colTakeProfit": "TP",
            "AlgorithmWorkspaceWindow.colStatus": "Status",
            "AlgorithmWorkspaceWindow.colCreatedAt": "Created",
            "AlgorithmWorkspaceWindow.colProfit": "Profit",
            "AlgorithmWorkspaceWindow.colEntryPrice": "Entry",
            "AlgorithmWorkspaceWindow.colCurrentPrice": "Current",
            "AlgorithmWorkspaceWindow.colPeakProfit": "Peak",
            "AlgorithmWorkspaceWindow.colProfitDrawdown": "Pullback",
            "AlgorithmWorkspaceWindow.colPositionSignalTime": "Signal",
            "AlgorithmWorkspaceWindow.colOpenedAt": "Opened",
            "AlgorithmWorkspaceWindow.colClosedAt": "Closed",
            "AlgorithmWorkspaceWindow.btnPositionGoSignal": "Go to signal",
            "AlgorithmWorkspaceWindow.btnPositionGoEntry": "Go to chart",
            "AlgorithmWorkspaceWindow.btnSignalGoPosition": "Go to position",
            "AlgorithmWorkspaceWindow.btnSignalGoChart": "Go to chart",
            "AlgorithmWorkspaceWindow.btnSignalGoJournal": "Go to journal",
            "AlgorithmWorkspaceWindow.signalGoPositionHint": (
                "Open the position created from the selected accepted signal."
            ),
            "AlgorithmWorkspaceWindow.signalGoChartHint": (
                "Show and mark the chart bar of the selected signal."
            ),
            "AlgorithmWorkspaceWindow.signalGoJournalHint": (
                "Open journal records for the selected signal UID."
            ),
            "AlgorithmWorkspaceWindow.positionGoSignalHint": (
                "Go to the signal that created the selected position."
            ),
            "AlgorithmWorkspaceWindow.positionGoEntryHint": (
                "Show and mark the chart bar where NEXT_BAR_OPEN entry was executed."
            ),
            "AlgorithmWorkspaceWindow.colReconciliation": "Runtime status",
            "AlgorithmWorkspaceWindow.colSignalTime": "Time",
            "AlgorithmWorkspaceWindow.colSignalType": "Signal",
            "AlgorithmWorkspaceWindow.colDirection": "Direction",
            "AlgorithmWorkspaceWindow.colStrength": "Strength",
            "AlgorithmWorkspaceWindow.colMacdState": "MACD",
            "AlgorithmWorkspaceWindow.colAlligator": "Alligator",
            "AlgorithmWorkspaceWindow.colAlligatorRegime": "Regime",
            "AlgorithmWorkspaceWindow.colSignalTimeframeMode": "TF / mode",
            "AlgorithmWorkspaceWindow.colSignalProfileRevision": "Profile rev.",
            "AlgorithmWorkspaceWindow.colSpreadStatus": "Spread",
            "AlgorithmWorkspaceWindow.colFilterResult": "Filter / result",
            "AlgorithmWorkspaceWindow.colReason": "Reason",
            "AlgorithmWorkspaceWindow.signalAccepted": "Accepted",
            "AlgorithmWorkspaceWindow.signalRejected": "Rejected",
            "AlgorithmWorkspaceWindow.signalsEmpty": (
                "No algorithm signals for the current run."
            ),
            "AlgorithmWorkspaceWindow.positionEmpty": "No WSP-owned positions.",
            "AlgorithmWorkspaceWindow.statusActive": "Active",
            "AlgorithmWorkspaceWindow.statusClosed": "Closed",
            "AlgorithmWorkspacePositionStatus.open": "Open",
            "AlgorithmWorkspacePositionStatus.closed": "Closed",
            "AlgorithmWorkspacePositionCloseReason.stopLoss": "Stop Loss",
            "AlgorithmWorkspacePositionCloseReason.takeProfit": "Take Profit",
            "AlgorithmWorkspacePositionCloseReason.profitDrawdown": "Profit drawdown",
            "AlgorithmWorkspacePositionCloseReason.sessionEnd": "Replay end",
            "AlgorithmWorkspacePositionTooltip.status": "Status",
            "AlgorithmWorkspacePositionTooltip.closeReason": "Close reason",
            "AlgorithmWorkspacePositionTooltip.technicalStatus": "Technical status",
            "AlgorithmWorkspacePositionTooltip.technicalReason": "Reason code",
            "AlgorithmWorkspaceWindow.chartPlaceholder": (
                "No WSP market data for the current run."
            ),
            "AlgorithmWorkspaceWindow.chartLatest": "Current",
            "AlgorithmWorkspaceWindow.positionPlaceholder": (
                "Position snapshot is not connected yet."
            ),
            "AlgorithmWorkspaceWindow.signalsPlaceholder": (
                "Algorithm signals will be shown here."
            ),
            "AlgorithmWorkspaceWindow.logPlaceholder": (
                "Replay and algorithm events will be shown here."
            ),
        }
        entries.update(workspace_mode_i18n_entries())
        entries.update(workspace_signal_i18n_entries())
        entries.update(
            {key: fallback for key, fallback in WORKSPACE_STATE_LABELS.values()}
        )
        entries.update(
            {key: fallback for key, fallback in REPLAY_STATE_LABELS.values()}
        )
        self._lang_mgr.tr(
            "AlgorithmWorkspaceStartupPhase.waitBroker",
            "WAIT_BROKER",
        )
        entries.update(
            {key: fallback for key, fallback in WORKSPACE_STARTUP_PHASE_LABELS.values()}
        )
        for key, fallback in entries.items():
            self._lang_mgr.tr(key, fallback)

    def apply_translation(self) -> None:
        """Apply translations, mode options, tabs and table headers."""
        if self._lang_mgr is not None:
            self._register_i18n_keys()

        if self._translator is not None:
            self._translator.apply(self)

        self._populate_mode_combos()
        self._populate_replay_speed_combo()
        self._populate_journal_filters()
        self._populate_snapshot_filters()
        self.btn_replay_tick.setText(
            self._tr("AlgorithmWorkspaceWindow.btnReplayTick", "Tick")
        )
        self.btn_replay_tick.setToolTip(
            self._tr(
                "AlgorithmWorkspaceWindow.replayTickHint",
                "Process one smallest Replay execution event.",
            )
        )
        replay_step_width = max(
            self.ui.btnReplayStep.sizeHint().width(),
            self.btn_replay_tick.sizeHint().width(),
        )
        self.ui.btnReplayStep.setMinimumWidth(replay_step_width)
        self.btn_replay_tick.setMinimumWidth(replay_step_width)
        self.lbl_position_date_jump.setText(
            self._tr(
                "AlgorithmWorkspaceWindow.lblPositionDateJump",
                "Go to date",
            )
        )
        self.btn_position_date_jump.setText(
            self._tr(
                "AlgorithmWorkspaceWindow.btnPositionDateJump",
                "Go",
            )
        )
        position_date_jump_hint = self._tr(
            "AlgorithmWorkspaceWindow.positionDateJumpHint",
            (
                "Select an opening date from the calendar and go to the first "
                "visible position on that date, or the next available date."
            ),
        )
        self.dte_position_date_jump.setToolTip(position_date_jump_hint)
        self.btn_position_date_jump.setToolTip(position_date_jump_hint)
        self.btn_position_go_signal.setText(
            self._tr(
                "AlgorithmWorkspaceWindow.btnPositionGoSignal",
                "Go to signal",
            )
        )
        self.btn_position_go_signal.setToolTip(
            self._tr(
                "AlgorithmWorkspaceWindow.positionGoSignalHint",
                "Go to the signal that created the selected position.",
            )
        )
        self.btn_position_go_entry.setText(
            self._tr(
                "AlgorithmWorkspaceWindow.btnPositionGoEntry",
                "Go to chart",
            )
        )
        self.btn_position_go_entry.setToolTip(
            self._tr(
                "AlgorithmWorkspaceWindow.positionGoEntryHint",
                (
                    "Show and mark the chart bar where NEXT_BAR_OPEN "
                    "entry was executed."
                ),
            )
        )
        self.lbl_signal_date_jump.setText(
            self._tr(
                "AlgorithmWorkspaceWindow.lblSignalDateJump",
                "Go to date",
            )
        )
        self.btn_signal_date_jump.setText(
            self._tr(
                "AlgorithmWorkspaceWindow.btnSignalDateJump",
                "Go",
            )
        )
        signal_date_jump_hint = self._tr(
            "AlgorithmWorkspaceWindow.signalDateJumpHint",
            (
                "Select a signal date from the calendar and go to the first "
                "visible signal on that date, or the next available date."
            ),
        )
        self.dte_signal_date_jump.setToolTip(signal_date_jump_hint)
        self.btn_signal_date_jump.setToolTip(signal_date_jump_hint)
        self.btn_signal_go_position.setText(
            self._tr(
                "AlgorithmWorkspaceWindow.btnSignalGoPosition",
                "Go to position",
            )
        )
        self.btn_signal_go_position.setToolTip(
            self._tr(
                "AlgorithmWorkspaceWindow.signalGoPositionHint",
                "Open the position created from the selected accepted signal.",
            )
        )
        self.btn_signal_go_chart.setText(
            self._tr(
                "AlgorithmWorkspaceWindow.btnSignalGoChart",
                "Go to chart",
            )
        )
        self.btn_signal_go_chart.setToolTip(
            self._tr(
                "AlgorithmWorkspaceWindow.signalGoChartHint",
                "Show and mark the chart bar of the selected signal.",
            )
        )
        self.btn_signal_go_journal.setText(
            self._tr(
                "AlgorithmWorkspaceWindow.btnSignalGoJournal",
                "Go to journal",
            )
        )
        self.btn_signal_go_journal.setToolTip(
            self._tr(
                "AlgorithmWorkspaceWindow.signalGoJournalHint",
                "Open journal records for the selected signal timestamp.",
            )
        )
        self.set_account_identity(
            self._account_display_name,
            self._account_mode,
        )
        tab_translations = (
            (
                self.ui.tabChart,
                "AlgorithmWorkspaceWindow.tabChart",
                "Chart",
            ),
            (
                self.ui.tabPosition,
                "AlgorithmWorkspaceWindow.tabPosition",
                "Position",
            ),
            (
                self.ui.tabSignals,
                "AlgorithmWorkspaceWindow.tabSignals",
                "Signals",
            ),
            (
                self.ui.tabOrders,
                "AlgorithmWorkspaceWindow.tabOrders",
                "Orders",
            ),
            (
                self.ui.tabLog,
                "AlgorithmWorkspaceWindow.tabLog",
                "Log",
            ),
        )
        for tab, key, fallback in tab_translations:
            index = self.tabs_workspace.indexOf(tab)
            if index >= 0:
                self.tabs_workspace.setTabText(
                    index,
                    self._tr(key, fallback),
                )

        self._apply_table_headers(self.tbl_orders, ORDER_TABLE_COLUMNS)
        self._apply_table_headers(self.tbl_positions, POSITION_TABLE_COLUMNS)
        self._apply_table_headers(self.tbl_signals, SIGNAL_TABLE_COLUMNS)
        self.ui.lblPositionPlaceholder.setText(
            self._tr(
                "AlgorithmWorkspaceWindow.positionEmpty",
                "No WSP-owned positions.",
            )
        )
        self.ui.lblSignalsPlaceholder.setText(
            self._tr(
                "AlgorithmWorkspaceWindow.signalsEmpty",
                "No algorithm signals for the current run.",
            )
        )
        self.chart_widget.set_texts(
            latest_text=self._tr(
                "AlgorithmWorkspaceWindow.chartLatest",
                "Current",
            ),
            empty_text=self._tr(
                "AlgorithmWorkspaceWindow.chartPlaceholder",
                "No WSP market data for the current run.",
            ),
        )
        self.chart_widget.set_control_hints(
            horizontal_zoom_out=self._tr(
                "AlgorithmWorkspaceWindow.chartZoomOutHint",
                "Horizontal zoom out. Keyboard: -. Mouse wheel down.",
            ),
            horizontal_zoom_in=self._tr(
                "AlgorithmWorkspaceWindow.chartZoomInHint",
                "Horizontal zoom in. Keyboard: +. Mouse wheel up.",
            ),
            vertical_zoom_out=self._tr(
                "AlgorithmWorkspaceWindow.chartVerticalZoomOutHint",
                "Vertical zoom out. Keyboard: Ctrl+-. Ctrl+mouse wheel down.",
            ),
            vertical_zoom_in=self._tr(
                "AlgorithmWorkspaceWindow.chartVerticalZoomInHint",
                "Vertical zoom in. Keyboard: Ctrl++. Ctrl+mouse wheel up.",
            ),
            vertical_pan=self._tr(
                "AlgorithmWorkspaceWindow.chartVerticalPanHint",
                "Vertical pan. Keyboard: Up/Down.",
            ),
            latest=self._tr(
                "AlgorithmWorkspaceWindow.chartLatestHint",
                "Jump to the last already processed bar. Keyboard: End.",
            ),
            canvas=self._tr(
                "AlgorithmWorkspaceWindow.chartNavigationHint",
                "Drag: horizontal pan. Left/Right: horizontal keyboard pan. "
                "Up/Down: vertical pan. Mouse wheel: horizontal zoom. "
                "Ctrl+mouse wheel: vertical zoom. +/-: horizontal zoom. "
                "Ctrl++/Ctrl+-: vertical zoom. Home: first bars. "
                "End: current processed bar. Replay SL/TP: hover the SL or TP line and "
                "drag it vertically; available only while Replay is paused. "
                "Entry cannot be moved.",
            ),
            protection_stop=self._tr(
                "AlgorithmWorkspaceWindow.chartStopLossDragHint",
                "Drag vertically to change Stop Loss. Replay must be paused.",
            ),
            protection_take=self._tr(
                "AlgorithmWorkspaceWindow.chartTakeProfitDragHint",
                "Drag vertically to change Take Profit. Replay must be paused.",
            ),
            draw_segment=self._tr(
                "AlgorithmWorkspaceWindow.chartDrawSegmentHint",
                "Slanted segment. Click to enable or disable. Right click: first "
                "point. Move the mouse. Right click: finish. Left click while "
                "drawing: finish this segment and continue a polyline from the "
                "same point.",
            ),
            draw_horizontal=self._tr(
                "AlgorithmWorkspaceWindow.chartDrawHorizontalHint",
                "Horizontal segment. Click to enable or disable. Right click: "
                "first point. Move the mouse. Right click: second point.",
            ),
            draw_vertical=self._tr(
                "AlgorithmWorkspaceWindow.chartDrawVerticalHint",
                "Vertical segment. Click to enable or disable. Right click: "
                "first point. Move the mouse. Right click: second point.",
            ),
            draw_clear=self._tr(
                "AlgorithmWorkspaceWindow.chartDrawClearHint",
                "Clear all temporary manual lines from the current chart.",
            ),
            drawing_start_label=self._tr(
                "AlgorithmWorkspaceWindow.chartDrawingStartLabel",
                "Start",
            ),
            drawing_end_label=self._tr(
                "AlgorithmWorkspaceWindow.chartDrawingEndLabel",
                "End",
            ),
            drawing_line_label=self._tr(
                "AlgorithmWorkspaceWindow.chartDrawingLineLabel",
                "Line",
            ),
            drawing_time_label=self._tr(
                "AlgorithmWorkspaceWindow.chartDrawingTimeLabel",
                "Time UTC",
            ),
            drawing_value_label=self._tr(
                "AlgorithmWorkspaceWindow.chartDrawingValueLabel",
                "Value",
            ),
        )
        self._populate_position_rows(self._owned_snapshot.positions)
        self._populate_signal_rows(self._signal_records)
        self._refresh_journal_view()

        self._refresh_runtime_ui()
        self._refresh_data_mode_ui()

    def _apply_table_headers(
        self,
        table: QTableWidget,
        columns: tuple[tuple[str, str], ...],
    ) -> None:
        table.setColumnCount(len(columns))
        for column, (key, fallback) in enumerate(columns):
            item = table.horizontalHeaderItem(column)
            if item is None:
                item = QTableWidgetItem()
                table.setHorizontalHeaderItem(column, item)
            item.setText(self._tr(key, fallback))

    def _translated_code(
        self,
        value: str,
        labels: dict[str, tuple[str, str]],
    ) -> str:
        key, fallback = labels.get(value, ("", value))
        return self._tr(key, fallback) if key else fallback

    def update_workspace(self, workspace: AlgorithmWorkspace) -> None:
        """Update visible configuration without starting the algorithm."""
        same_account_binding = (
            workspace.broker == self._broker
            and workspace.account_id == self._account_id
        )
        account_display_name = (
            self._account_display_name
            if same_account_binding
            else workspace.account_id or "—"
        )
        self.workspace_uid = workspace.workspace_uid
        self._has_started_once = workspace.has_started_once
        self._set_display_name(workspace.display_name)
        self.ui.lblBroker.setText(workspace.broker)
        self._broker = workspace.broker
        self._account_id = workspace.account_id
        self._account_mode = workspace.account_mode
        self._data_mode = workspace.data_mode
        self.set_account_identity(
            account_display_name,
            workspace.account_mode,
        )
        self.set_account_balance(None)
        replay_settings = dict(workspace.replay_settings)
        replay_source_type = (
            str(replay_settings.get("source_type") or "").strip().upper()
        )
        replay_file_path = str(replay_settings.get("file_path") or "").strip()
        replay_source_name = str(replay_settings.get("source") or "").strip()
        if not replay_source_name and replay_file_path:
            replay_source_name = Path(replay_file_path).name
        self.set_replay_configured(
            workspace.data_mode == WORKSPACE_DATA_MODE_REPLAY
            and replay_source_type == WORKSPACE_REPLAY_SOURCE_CSV
            and bool(replay_file_path),
            replay_source_name,
        )
        self.ui.lblSymbol.setText(workspace.symbol)
        self.ui.lblTimeframe.setText(workspace.timeframe)
        self.ui.lblAlgorithm.setText(workspace.algorithm)

        self._updating_modes = True
        try:
            self._set_combo_by_data(self.cmb_data_mode, workspace.data_mode)
            self._set_combo_by_data(
                self.cmb_control_mode,
                workspace.control_mode,
            )
        finally:
            self._updating_modes = False

        panel_index = INDEX_BY_PANEL.get(
            str(workspace.ui_state.get("active_panel") or "").upper(),
            0,
        )
        self.tabs_workspace.setCurrentIndex(panel_index)
        self.set_runtime_state(workspace.runtime_state)
        self._refresh_data_mode_ui()
        self._refresh_rename_enabled()

    def account_binding(self) -> tuple[str, str | None, str]:
        """Return broker/account/data-source binding for read-only snapshots."""
        return self._broker, self._account_id, self._data_mode

    def set_account_balance(
        self,
        balance: float | None,
        currency: str = "",
    ) -> None:
        """Show a volatile broker balance without persisting it to Session."""
        self.ui.lblBalance.setText(format_workspace_balance(balance, currency))

    def set_account_identity(
        self,
        display_name: str,
        account_mode: str | None = None,
        *,
        preserve_public_name: bool = False,
    ) -> None:
        """Show the public account name while retaining internal binding ID."""
        public_name = str(display_name or "").strip() or "—"
        if (
            preserve_public_name
            and public_name == self._account_id
            and self._account_display_name not in {"—", self._account_id}
        ):
            public_name = self._account_display_name
        self._account_display_name = public_name
        visible_name = public_name
        normalized_mode = (
            account_mode if account_mode is not None else self._account_mode
        )
        account_key, account_fallback = workspace_account_mode_key(normalized_mode)
        if visible_name != "—" and account_key:
            visible_name = (
                f"{visible_name} • " f"{self._tr(account_key, account_fallback)}"
            )
        self.ui.lblAccount.setText(visible_name)
        if self._account_id and public_name != self._account_id:
            self.ui.lblAccount.setToolTip(
                self._tr(
                    "AlgorithmWorkspaceWindow.accountRuntimeIdTooltip",
                    "Runtime account ID: {account_id}",
                ).format(account_id=self._account_id)
            )
        else:
            self.ui.lblAccount.setToolTip("")

    def set_runtime_state(self, runtime_state: str) -> None:
        """Update the temporary state and state-dependent WSP appearance."""
        self._runtime_state = runtime_state
        self._refresh_runtime_ui()

    def set_runtime_status(
        self,
        runtime_state: str,
        startup_phase: str,
    ) -> None:
        """Update runtime state and its detailed startup phase together."""
        self._runtime_state = runtime_state
        self._startup_phase = startup_phase
        self._refresh_runtime_ui()

    def set_execution_safety_hold(
        self,
        *,
        active: bool,
        message: str | None,
        account_id: str = "",
        symbol: str = "",
        signed_volume: float = 0.0,
        evidence_status: str = "",
        confirmation_required: bool = False,
    ) -> None:
        """Show a recoverable execution hold without hiding market data."""
        self._safety_hold_active = bool(active)
        self._safety_hold_message = str(message or "").strip()
        self._safety_hold_account_id = str(account_id or "").strip()
        self._safety_hold_symbol = str(symbol or "").strip().upper()
        self._safety_hold_signed_volume = float(signed_volume or 0.0)
        self._safety_hold_evidence_status = str(evidence_status or "").strip().upper()
        self._safety_hold_confirmation_required = bool(confirmation_required)
        self._refresh_runtime_ui()

    def set_runtime_snapshot(
        self,
        *,
        active_orders_count: int = 0,
        active_positions_count: int = 0,
        current_profit: float = 0.0,
        peak_profit: float = 0.0,
    ) -> None:
        """Apply a read-only runtime snapshot; no broker call is made."""
        self._active_orders_count = max(0, int(active_orders_count))
        self._active_positions_count = max(0, int(active_positions_count))
        self._current_profit = float(current_profit)
        self._peak_profit = max(float(peak_profit), self._current_profit, 0.0)

        if self._peak_profit > 0.0:
            pullback = self._peak_profit - self._current_profit
            self._profit_drawdown_percent = max(
                0.0,
                pullback / self._peak_profit * 100.0,
            )
        else:
            self._profit_drawdown_percent = 0.0

        self.ui.lblOrdersCount.setText(str(self._active_orders_count))
        self.ui.lblPositionsCount.setText(str(self._active_positions_count))
        self.ui.lblCurrentProfit.setText(f"{self._current_profit:+.2f}")
        self.ui.lblPeakProfit.setText(f"{self._peak_profit:+.2f}")
        self.ui.lblProfitDrawdown.setText(f"{self._profit_drawdown_percent:.1f}%")
        if self._data_mode != WORKSPACE_DATA_MODE_REPLAY:
            self._apply_standard_summary_labels()

    def set_replay_financial_snapshot(
        self,
        *,
        initial_balance: float | None,
        balance: float | None,
        equity: float | None,
        currency: str = "USD",
    ) -> None:
        """Show the virtual Replay account and live financial state."""
        self.set_account_identity(
            self._tr(
                "AlgorithmWorkspaceWindow.replaySyntheticAccount",
                "Virtual Replay account",
            ),
            "REPLAY",
        )
        account_tooltip = self._tr(
            "AlgorithmWorkspaceWindow.replayAccountTooltip",
            "This account exists only inside Replay and is not linked to "
            "IB or cTrader.",
        )
        if initial_balance is not None:
            account_tooltip = (
                f"{account_tooltip} "
                f"Initial balance: "
                f"{format_workspace_balance(initial_balance, currency)}"
            )
        self.ui.lblAccount.setToolTip(account_tooltip)
        self.ui.lblBalanceCaption.setText(
            self._tr(
                "AlgorithmWorkspaceWindow.lblReplayEquity",
                "Replay equity:",
            )
        )
        self.set_account_balance(equity, currency)
        self.ui.lblCurrentProfitCaption.setText(
            self._tr(
                "AlgorithmWorkspaceWindow.lblReplayRealizedPnl",
                "Closed PnL:",
            )
        )
        self.ui.lblPeakProfitCaption.setText(
            self._tr(
                "AlgorithmWorkspaceWindow.lblReplayBalance",
                "Replay balance:",
            )
        )
        self.ui.lblProfitDrawdownCaption.setText(
            self._tr(
                "AlgorithmWorkspaceWindow.lblReplaySummaryEquity",
                "Replay equity:",
            )
        )
        realized_profit = None
        if initial_balance is not None and balance is not None:
            realized_profit = balance - initial_balance
        self.ui.lblCurrentProfit.setText(
            self._format_profit(realized_profit) if realized_profit is not None else "—"
        )
        self.ui.lblPeakProfit.setText(format_workspace_balance(balance, currency))
        self.ui.lblProfitDrawdown.setText(format_workspace_balance(equity, currency))

    def _apply_standard_summary_labels(self) -> None:
        self.ui.lblBalanceCaption.setText(
            self._tr("AlgorithmWorkspaceWindow.lblBalance", "Balance:")
        )
        self.ui.lblCurrentProfitCaption.setText(
            self._tr(
                "AlgorithmWorkspaceWindow.lblCurrentProfit",
                "Profit:",
            )
        )
        self.ui.lblPeakProfitCaption.setText(
            self._tr(
                "AlgorithmWorkspaceWindow.lblPeakProfit",
                "Peak:",
            )
        )
        self.ui.lblProfitDrawdownCaption.setText(
            self._tr(
                "AlgorithmWorkspaceWindow.lblProfitDrawdown",
                "Pullback:",
            )
        )

    def set_replay_snapshot(
        self,
        *,
        status_text: str,
        paused: bool,
        speed: int,
        active: bool,
        tick_available: bool = False,
    ) -> None:
        """Apply volatile Replay status without persisting it to Session."""
        self._replay_paused = bool(paused)
        self._replay_speed = int(speed)
        self.ui.lblReplayStatus.setText(status_text)
        self.ui.lblReplayStatus.setToolTip(status_text)
        self.ui.btnReplayPause.setText(
            self._tr("AlgorithmWorkspaceWindow.btnReplayResume", "Resume")
            if self._replay_paused
            else self._tr("AlgorithmWorkspaceWindow.btnReplayPause", "Pause")
        )
        self.ui.cmbReplaySpeed.blockSignals(True)
        try:
            self._set_combo_by_data(
                self.ui.cmbReplaySpeed,
                str(self._replay_speed),
            )
        finally:
            self.ui.cmbReplaySpeed.blockSignals(False)
        self.ui.btnReplayPause.setEnabled(active)
        self.ui.btnReplayStep.setEnabled(active and self._replay_paused)
        self.btn_replay_tick.setEnabled(
            active and self._replay_paused and bool(tick_available)
        )
        self._refresh_chart_protection_drag_state(active=active)

    def _refresh_chart_protection_drag_state(
        self,
        *,
        active: bool | None = None,
    ) -> None:
        """Дозволити SL/TP drag тільки у paused active Historical Replay."""
        replay_active = (
            self._runtime_state in {WORKSPACE_STATE_STARTING, WORKSPACE_STATE_RUNNING}
            if active is None
            else bool(active)
        )
        enabled = bool(
            replay_active
            and self._data_mode == WORKSPACE_DATA_MODE_REPLAY
            and self._replay_paused
        )
        self.chart_widget.set_protection_drag_enabled(enabled)

    def set_active_workspace(self, active: bool) -> None:
        """Show whether this WSP is the active MDI workspace."""
        self._is_active_workspace = bool(active)
        self.setProperty("activeWorkspace", self._is_active_workspace)
        self.lbl_name.setProperty(
            "activeWorkspace",
            self._is_active_workspace,
        )
        for widget in (self, self.lbl_name):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()

    def set_replay_configured(
        self,
        configured: bool,
        source: str = "",
    ) -> None:
        """Mark a stopped WSP whose Historical CSV source is configured."""
        self._replay_configured = bool(configured)
        for widget in (self, self.lbl_name, self.btn_replay_settings):
            widget.setProperty("replayConfigured", self._replay_configured)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()

        if self._replay_configured:
            source_text = source.strip() or "CSV"
            tooltip = self._tr(
                "AlgorithmWorkspaceWindow.replayConfiguredTooltip",
                "Historical Replay configured: {source}",
            ).format(source=source_text)
            self.btn_replay_settings.setToolTip(tooltip)
        else:
            self.btn_replay_settings.setToolTip("")

    def set_layout_locked(self, locked: bool) -> None:
        """Lock structural edits but keep runtime controls available."""
        self._layout_locked = bool(locked)
        self._refresh_rename_enabled()

    def set_has_started_once(self, has_started_once: bool) -> None:
        self._has_started_once = bool(has_started_once)
        self._refresh_rename_enabled()

    def _refresh_rename_enabled(self) -> None:
        self.btn_rename.setEnabled(
            not self._layout_locked and not self._has_started_once
        )

    def _refresh_runtime_ui(self) -> None:
        self.setProperty("runtimeState", self._runtime_state)
        self.setProperty("safetyHold", self._safety_hold_active)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

        state_text = self._translated_code(
            self._runtime_state,
            WORKSPACE_STATE_LABELS,
        )
        if self._safety_hold_active:
            state_text = self._translated_code(
                WORKSPACE_STARTUP_PHASE_SAFETY_HOLD_EXTERNAL_EXPOSURE,
                WORKSPACE_STARTUP_PHASE_LABELS,
            )
        elif (
            self._runtime_state == WORKSPACE_STATE_STARTING
            and self._startup_phase != WORKSPACE_STARTUP_PHASE_IDLE
        ):
            state_text = self._translated_code(
                self._startup_phase,
                WORKSPACE_STARTUP_PHASE_LABELS,
            )
        self.lbl_state.setText(state_text)
        self.lbl_state.setToolTip(
            self._execution_safety_hold_tooltip() if self._safety_hold_active else ""
        )
        is_stop_action = self._runtime_state in {
            WORKSPACE_STATE_STARTING,
            WORKSPACE_STATE_RUNNING,
            WORKSPACE_STATE_ERROR,
        }
        is_transition = self._runtime_state == WORKSPACE_STATE_STOPPING

        self.btn_start_stop.setProperty(
            "actionMode",
            "STOP" if is_stop_action else "START",
        )
        self.btn_start_stop.setText(
            self._tr("AlgorithmWorkspaceWindow.btnStop", "STOP")
            if is_stop_action
            else self._tr("AlgorithmWorkspaceWindow.btnStart", "START")
        )
        self.btn_start_stop.setEnabled(not is_transition)
        self.btn_start_stop.style().unpolish(self.btn_start_stop)
        self.btn_start_stop.style().polish(self.btn_start_stop)

        modes_enabled = (
            self._runtime_state not in ACTIVE_RUNTIME_STATES
            and self._runtime_state != WORKSPACE_STATE_ERROR
        )
        self.cmb_data_mode.setEnabled(modes_enabled)
        self.cmb_control_mode.setEnabled(modes_enabled)
        self.btn_parameters.setEnabled(modes_enabled)
        self.btn_history_download.setEnabled(modes_enabled)
        self.btn_replay_settings.setEnabled(
            modes_enabled
            and self.cmb_data_mode.currentData() == WORKSPACE_DATA_MODE_REPLAY
        )
        replay_active = (
            self._runtime_state
            in {
                WORKSPACE_STATE_STARTING,
                WORKSPACE_STATE_RUNNING,
            }
            and self.cmb_data_mode.currentData() == WORKSPACE_DATA_MODE_REPLAY
        )
        self.ui.btnReplayPause.setEnabled(replay_active)
        self.ui.btnReplayStep.setEnabled(replay_active and self._replay_paused)
        self.btn_replay_tick.setEnabled(False)
        self.ui.cmbReplaySpeed.setEnabled(
            self.cmb_data_mode.currentData() == WORKSPACE_DATA_MODE_REPLAY
            and not is_transition
            and self._runtime_state != WORKSPACE_STATE_ERROR
        )

    def _populate_mode_combos(self) -> None:
        current_data_mode = self.cmb_data_mode.currentData()
        current_control_mode = self.cmb_control_mode.currentData()

        self._updating_modes = True
        try:
            self.cmb_data_mode.clear()
            self.cmb_data_mode.addItem(
                self._tr("WorkspaceDataSource.broker", "Broker data"),
                WORKSPACE_DATA_MODE_BROKER,
            )
            self.cmb_data_mode.addItem(
                self._tr("WorkspaceDataSource.replay", "Historical replay"),
                WORKSPACE_DATA_MODE_REPLAY,
            )
            self.cmb_data_mode.addItem(
                self._tr("WorkspaceDataSource.backtest", "Backtest"),
                WORKSPACE_DATA_MODE_BACKTEST,
            )

            self.cmb_control_mode.clear()
            self.cmb_control_mode.addItem(
                self._tr("WorkspaceControlMode.manualControl", "Manual control"),
                WORKSPACE_CONTROL_MODE_MANUAL,
            )
            self.cmb_control_mode.addItem(
                self._tr(
                    "WorkspaceControlMode.semiAutomatic",
                    "Semi-automatic control",
                ),
                WORKSPACE_CONTROL_MODE_SEMI,
            )
            self.cmb_control_mode.addItem(
                self._tr("WorkspaceControlMode.automatic", "Automatic control"),
                WORKSPACE_CONTROL_MODE_AUTO,
            )

            if current_data_mode is not None:
                self._set_combo_by_data(
                    self.cmb_data_mode,
                    str(current_data_mode),
                )
            if current_control_mode is not None:
                self._set_combo_by_data(
                    self.cmb_control_mode,
                    str(current_control_mode),
                )
        finally:
            self._updating_modes = False

    def _populate_replay_speed_combo(self) -> None:
        current_speed = self.ui.cmbReplaySpeed.currentData()
        if current_speed is None:
            current_speed = str(self._replay_speed)
        self.ui.cmbReplaySpeed.blockSignals(True)
        try:
            self.ui.cmbReplaySpeed.clear()
            for speed in REPLAY_SPEEDS:
                label = replay_speed_label(speed)
                if speed == REPLAY_SPEED_MAX:
                    label = self._tr(
                        "AlgorithmWorkspaceWindow.replaySpeedMax",
                        label,
                    )
                elif speed == REPLAY_SPEED_MAX_FAST:
                    label = self._tr(
                        "AlgorithmWorkspaceWindow.replaySpeedMaxFast",
                        label,
                    )
                self.ui.cmbReplaySpeed.addItem(label, str(speed))
            self._set_combo_by_data(
                self.ui.cmbReplaySpeed,
                str(current_speed),
            )
        finally:
            self.ui.cmbReplaySpeed.blockSignals(False)

    def _on_start_stop_clicked(self) -> None:
        if self._runtime_state in {
            WORKSPACE_STATE_STARTING,
            WORKSPACE_STATE_RUNNING,
            WORKSPACE_STATE_ERROR,
        }:
            self.stop_requested.emit(self.workspace_uid)
            return
        self.start_requested.emit(self.workspace_uid)

    def _on_modes_changed(self, _index: int) -> None:
        if self._updating_modes:
            return
        data_mode = self.cmb_data_mode.currentData()
        control_mode = self.cmb_control_mode.currentData()
        if data_mode is None or control_mode is None:
            return
        self._refresh_data_mode_ui()
        self.modes_changed.emit(
            self.workspace_uid,
            str(data_mode),
            str(control_mode),
        )

    def _on_replay_pause_clicked(self) -> None:
        self.replay_pause_requested.emit(self.workspace_uid)

    def _on_replay_step_clicked(self) -> None:
        self.replay_step_requested.emit(self.workspace_uid)

    def _on_replay_tick_clicked(self) -> None:
        self.replay_tick_requested.emit(self.workspace_uid)

    def _on_replay_speed_changed(self, _index: int) -> None:
        speed = self.ui.cmbReplaySpeed.currentData()
        if speed is None:
            return
        self.replay_speed_changed.emit(self.workspace_uid, int(speed))

    def _refresh_data_mode_ui(self) -> None:
        is_replay = self.cmb_data_mode.currentData() == WORKSPACE_DATA_MODE_REPLAY
        self.frame_replay_controls.setVisible(is_replay)
        self.btn_replay_settings.setVisible(is_replay)
        self.btn_replay_settings.setEnabled(
            is_replay
            and self._runtime_state not in ACTIVE_RUNTIME_STATES
            and self._runtime_state != WORKSPACE_STATE_ERROR
        )

    def _on_panel_changed(self, index: int) -> None:
        panel = PANEL_BY_INDEX.get(index)
        if panel is not None:
            self.active_panel_changed.emit(self.workspace_uid, panel)

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    @property
    def full_display_name(self) -> str:
        """Return the complete, non-elided WSP name."""
        return self._full_display_name

    def _set_display_name(self, display_name: str) -> None:
        """Store the full name and display an elided version when necessary."""
        self._full_display_name = str(display_name or "").strip()
        self.lbl_name.setToolTip(self._full_display_name)
        self._refresh_display_name()

    def _refresh_display_name(self) -> None:
        """Fit the WSP name into the currently available label width."""
        available_width = self.lbl_name.contentsRect().width()
        if available_width <= 0:
            return

        visible_name = self.lbl_name.fontMetrics().elidedText(
            self._full_display_name,
            Qt.TextElideMode.ElideRight,
            max(40, available_width - 8),
        )
        self.lbl_name.setText(visible_name)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._refresh_display_name()

    def _tr(self, key: str, fallback: str) -> str:
        if self._lang_mgr is None:
            return fallback
        return self._lang_mgr.tr(key, fallback)


class AlgorithmMdiSubWindow(QMdiSubWindow):
    """QMdiSubWindow with layout-lock and guarded close behavior."""

    geometry_changed = Signal(str)
    close_blocked = Signal(str, str)
    user_closed = Signal(str)

    def __init__(
        self,
        workspace_uid: str,
        close_guard: Callable[[], tuple[bool, str]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.workspace_uid = workspace_uid
        self._close_guard = close_guard
        self._layout_locked = False
        self._locked_geometry = QRect()
        self._restoring_locked_geometry = False
        self._closing_from_area = False
        self._workspace_maximized = False
        self._normal_geometry_before_maximize = QRect()
        self._handling_workspace_maximize = False
        self._workspace_maximize_request_pending = False
        self._workspace_geometry_refresh_pending = False
        self._workspace_geometry_refresh_passes = 0
        self._workspace_geometry_refresh_maximized = False
        self._workspace_geometry_refresh_target = QRect()
        self._workspace_tiled = False
        self._normal_minimum_size = QSize()
        self._normal_widget_minimum_size = QSize()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

    def set_layout_locked(self, locked: bool) -> None:
        self._layout_locked = bool(locked)
        if self._layout_locked:
            self._locked_geometry = QRect(self.geometry())

    def apply_system_geometry(self, geometry: QRect) -> None:
        """Apply Session geometry even when the user layout is locked."""
        self._restoring_locked_geometry = True
        try:
            self.setGeometry(geometry)
            if self._layout_locked:
                self._locked_geometry = QRect(geometry)
        finally:
            self._restoring_locked_geometry = False

    def close_from_area(self) -> None:
        self._closing_from_area = True
        self.close()

    def is_workspace_maximized(self) -> bool:
        """Return whether the WSP uses the MDI-safe maximized geometry."""
        return self._workspace_maximized

    def normal_workspace_geometry(self) -> QRect:
        """Return the geometry to persist for later normal restoration."""
        if (
            self._workspace_maximized
            and self._normal_geometry_before_maximize.isValid()
        ):
            return QRect(self._normal_geometry_before_maximize)
        geometry = self.normalGeometry()
        if geometry.isValid() and geometry.width() > 0:
            return QRect(geometry)
        return QRect(self.geometry())

    def show_workspace_maximized(self) -> None:
        """Fill the MDI viewport while preserving the child title bar."""
        if self._workspace_maximized:
            self._apply_workspace_maximized_geometry()
            self._schedule_workspace_geometry_refresh(
                maximized=True,
                passes=2,
            )
            return
        self._handling_workspace_maximize = True
        try:
            if self.isMaximized():
                self.showNormal()
            current = self.geometry()
            if current.isValid() and current.width() > 0:
                self._normal_geometry_before_maximize = QRect(current)
            self._workspace_maximized = True
            self._apply_workspace_maximized_geometry()
        finally:
            self._handling_workspace_maximize = False
        self._schedule_workspace_geometry_refresh(
            maximized=True,
            passes=2,
        )

    def restore_workspace_normal(self) -> None:
        """Відновити normal state після minimize або MDI-safe maximize."""
        was_minimized = self.isMinimized()
        was_maximized = self._workspace_maximized or self.isMaximized()
        if not was_minimized and not was_maximized:
            return
        self._workspace_maximize_request_pending = False
        self._handling_workspace_maximize = True
        geometry = QRect()
        try:
            if self.isMinimized() or self.isMaximized():
                self.showNormal()
            if was_maximized:
                geometry = QRect(self._normal_geometry_before_maximize)
                self._workspace_maximized = False
                self._normal_geometry_before_maximize = QRect()
                if geometry.isValid() and geometry.width() > 0:
                    self.apply_system_geometry(geometry)
        finally:
            self._handling_workspace_maximize = False
        if geometry.isValid() and geometry.width() > 0:
            self._schedule_workspace_geometry_refresh(
                maximized=False,
                geometry=geometry,
                passes=2,
            )
        self.geometry_changed.emit(self.workspace_uid)

    def set_workspace_tiled(self, tiled: bool) -> None:
        """Перемкнути minimum-size contract між normal і tiled layout."""
        tiled = bool(tiled)
        if tiled == self._workspace_tiled:
            return

        widget = self.widget()
        if tiled:
            self._normal_minimum_size = QSize(self.minimumSize())
            if widget is not None:
                self._normal_widget_minimum_size = QSize(widget.minimumSize())
                widget.setMinimumSize(0, 0)
            self.setMinimumSize(0, 0)
        else:
            if self._normal_minimum_size.isValid():
                self.setMinimumSize(self._normal_minimum_size)
            if widget is not None and self._normal_widget_minimum_size.isValid():
                widget.setMinimumSize(self._normal_widget_minimum_size)
            self._normal_minimum_size = QSize()
            self._normal_widget_minimum_size = QSize()
        self._workspace_tiled = tiled

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if self._handling_workspace_maximize:
            return
        if event.type() != QEvent.Type.WindowStateChange:
            return
        if not self.isMaximized():
            return
        if self._workspace_maximize_request_pending:
            return
        self._workspace_maximize_request_pending = True
        QTimer.singleShot(0, self._handle_native_maximize_request)

    def _handle_native_maximize_request(self) -> None:
        """Convert one native title-bar maximize request into a safe toggle."""
        if not self._workspace_maximize_request_pending:
            return
        self._workspace_maximize_request_pending = False
        self._handling_workspace_maximize = True
        geometry = QRect()
        try:
            native_normal = QRect(self.normalGeometry())
            if self.isMaximized():
                self.showNormal()
            if self._workspace_maximized:
                geometry = QRect(self._normal_geometry_before_maximize)
                self._workspace_maximized = False
                self._normal_geometry_before_maximize = QRect()
                if geometry.isValid() and geometry.width() > 0:
                    self.apply_system_geometry(geometry)
            else:
                if native_normal.isValid() and native_normal.width() > 0:
                    self._normal_geometry_before_maximize = QRect(native_normal)
                else:
                    self._normal_geometry_before_maximize = QRect(self.geometry())
                self._workspace_maximized = True
                self._apply_workspace_maximized_geometry()
        finally:
            self._handling_workspace_maximize = False
        if self._workspace_maximized:
            self._schedule_workspace_geometry_refresh(
                maximized=True,
                passes=2,
            )
        elif geometry.isValid() and geometry.width() > 0:
            self._schedule_workspace_geometry_refresh(
                maximized=False,
                geometry=geometry,
                passes=2,
            )
        self.geometry_changed.emit(self.workspace_uid)

    def _schedule_workspace_geometry_refresh(
        self,
        *,
        maximized: bool,
        geometry: QRect | None = None,
        passes: int = 2,
    ) -> None:
        """Reapply safe MDI geometry after Qt finishes native state changes."""
        self._workspace_geometry_refresh_maximized = bool(maximized)
        self._workspace_geometry_refresh_target = QRect(geometry or QRect())
        self._workspace_geometry_refresh_passes = max(
            self._workspace_geometry_refresh_passes,
            int(passes),
        )
        if self._workspace_geometry_refresh_pending:
            return
        self._workspace_geometry_refresh_pending = True
        QTimer.singleShot(0, self._refresh_workspace_geometry)

    def _refresh_workspace_geometry(self) -> None:
        """Finish one deferred geometry-stabilization pass."""
        self._workspace_geometry_refresh_pending = False
        if self._workspace_geometry_refresh_passes <= 0:
            return

        maximized = self._workspace_geometry_refresh_maximized
        target = QRect(self._workspace_geometry_refresh_target)
        valid_request = (maximized and self._workspace_maximized) or (
            not maximized
            and not self._workspace_maximized
            and target.isValid()
            and target.width() > 0
        )
        if not valid_request:
            self._workspace_geometry_refresh_passes = 0
            return

        self._handling_workspace_maximize = True
        try:
            if self.isMaximized():
                self.showNormal()
            if maximized:
                self._apply_workspace_maximized_geometry()
            else:
                self.apply_system_geometry(target)
        finally:
            self._handling_workspace_maximize = False

        self._workspace_geometry_refresh_passes -= 1
        if self._workspace_geometry_refresh_passes > 0:
            self._workspace_geometry_refresh_pending = True
            QTimer.singleShot(0, self._refresh_workspace_geometry)

    def _apply_workspace_maximized_geometry(self) -> None:
        mdi_area = self.mdiArea()
        if mdi_area is None:
            return
        self.apply_system_geometry(QRect(mdi_area.viewport().rect()))

    def moveEvent(self, event: QMoveEvent) -> None:
        super().moveEvent(event)
        self._handle_geometry_event()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._handle_geometry_event()

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._closing_from_area:
            allowed, reason = self._close_guard()
            if not allowed:
                event.ignore()
                self.close_blocked.emit(self.workspace_uid, reason)
                return

        super().closeEvent(event)
        if event.isAccepted() and not self._closing_from_area:
            self.user_closed.emit(self.workspace_uid)

    def _handle_geometry_event(self) -> None:
        if self._restoring_locked_geometry:
            return

        if self._layout_locked and self._locked_geometry.isValid():
            if self.geometry() != self._locked_geometry:
                QTimer.singleShot(0, self._restore_locked_geometry)
            return

        self.geometry_changed.emit(self.workspace_uid)

    def _restore_locked_geometry(self) -> None:
        if not self._layout_locked or not self._locked_geometry.isValid():
            return
        self._restoring_locked_geometry = True
        try:
            self.setGeometry(self._locked_geometry)
        finally:
            self._restoring_locked_geometry = False


class AlgorithmWorkspaceArea(QWidget):
    """MDI workspace desktop for the Monitoring page."""

    external_exposure_resolution_requested = Signal(str, str, str)

    def __init__(
        self,
        lang_mgr: LangManager | None = None,
        controller: AlgorithmWorkspaceController | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._lang_mgr = lang_mgr
        self._translator = UITranslator(lang_mgr) if lang_mgr is not None else None
        self.controller = controller or AlgorithmWorkspaceController(
            algorithm_factory=create_registered_workspace_algorithm
        )
        self._catalog = AlgorithmWorkspaceCatalog()
        self._runtime_engine: Any | None = None
        self._session_restored = False
        self._restoring = False
        self._closing_area = False
        self._shutdown_complete = False
        self._windows: dict[str, AlgorithmWorkspaceWindow] = {}
        self._subwindows: dict[str, AlgorithmMdiSubWindow] = {}
        self._restore_geometries: dict[str, QRect] = {}
        self._restore_window_states: dict[str, str] = {}
        self._restore_active_workspace_uid: str | None = None
        self._pending_ui_state: set[str] = set()
        self._runtime_log_offsets: dict[str, int] = {}
        self._external_hold_notified: set[str] = set()
        self._historical_summary_shown: set[str] = set()
        self._replay_burst_state: dict[str, tuple[int, int | None]] = {}
        self._replay_fast_ui_last_sync: dict[str, float] = {}

        self.ui = Ui_AlgorithmWorkspaceArea()
        self.ui.setupUi(self)

        self.lbl_title = self.ui.lblTitle
        self.btn_new = self.ui.btnNew
        self.btn_cascade = self.ui.btnCascade
        self.btn_tile = self.ui.btnTile
        self.btn_lock = self.ui.btnWorkspaceLock
        self.lbl_empty = self.ui.lblEmpty
        self.mdi = self.ui.mdiWorkspaces
        self.stack_workspace_state = self.ui.stackWorkspaceState

        self._save_ui_timer = QTimer(self)
        self._save_ui_timer.setSingleShot(True)
        self._save_ui_timer.setInterval(180)
        self._save_ui_timer.timeout.connect(self.flush_pending_ui_state)

        self._balance_timer = QTimer(self)
        self._balance_timer.setInterval(10_000)
        self._balance_timer.timeout.connect(self.refresh_account_balances)

        self._replay_timer = QTimer(self)
        self._replay_timer.setInterval(250)
        self._replay_timer.timeout.connect(self.advance_replay_runtimes)
        self._replay_timer.start()

        self.btn_new.clicked.connect(self._open_create_dialog)
        self.btn_cascade.clicked.connect(self.cascade_windows)
        self.btn_tile.clicked.connect(self.tile_windows)
        self.btn_lock.toggled.connect(self._on_lock_toggled)
        self.mdi.subWindowActivated.connect(self._on_subwindow_activated)

        self.apply_translation()
        self._update_empty_state()

    def _register_i18n_keys(self) -> None:
        if self._lang_mgr is None:
            return

        entries = {
            "AlgorithmWorkspaceArea.lblTitle": "Algorithm desktop",
            "AlgorithmWorkspaceArea.btnNew": "Create",
            "AlgorithmWorkspaceArea.btnCascade": "Cascade",
            "AlgorithmWorkspaceArea.btnTile": "Tile",
            "AlgorithmWorkspaceArea.lblEmpty": (
                "No workspace windows yet. Click “Create”."
            ),
            "AlgorithmWorkspaceStartupPhase.safetyHoldExternalExposure": (
                "SAFETY HOLD"
            ),
            "AlgorithmWorkspaceWindow.safetyHoldExternalExposureStatus": (
                "SAFETY HOLD • {symbol} • new LGE execution is blocked • "
                "Orders → Resolve reconciliation"
            ),
            "AlgorithmWorkspaceWindow.safetyHoldTooltip": (
                "LGE EXCLUSIVE paused new LGE signals and orders; market data "
                "continues. Account: {account_id}; symbol: {symbol}; external "
                "exposure: {side} {volume}; evidence: {evidence}. Open Orders, "
                "select the external exposure row and click Resolve "
                "reconciliation to see the exact TWS identifiers. After "
                "resolving the position or orphaned protection in TWS, press "
                "Refresh. Use Monitoring to return to this WSP and inspect "
                "its journal."
            ),
            "AlgorithmWorkspaceJournal.categorySafety": "Safety",
            "AlgorithmWorkspaceJournal.safetyHoldEntered": "SAFETY HOLD ENTERED",
            "AlgorithmWorkspaceJournal.safetyHoldUpdated": "SAFETY HOLD UPDATED",
            "AlgorithmWorkspaceJournal.safetyHoldCleared": "SAFETY HOLD CLEARED",
            "AlgorithmWorkspaceJournal.safetyHoldActiveMessage": (
                "Account {account_id}, symbol {symbol}: external exposure "
                "{side} {volume}; evidence {evidence}. New LGE signals and "
                "orders are blocked; market data continues. Open Orders, "
                "select the external exposure row and click Resolve "
                "reconciliation."
            ),
            "AlgorithmWorkspaceJournal.safetyHoldClearedMessage": (
                "Current broker evidence cleared the external exposure. LGE "
                "is waiting for a fresh live spread before execution can "
                "resume."
            ),
            "AlgorithmWorkspaceJournal.safetyPhaseChanged": "SAFETY PHASE CHANGED",
            "AlgorithmWorkspaceJournal.safetyPhaseChangedMessage": (
                "{previous_phase} → {target_phase}. New LGE execution is "
                "blocked while read-only market data continues."
            ),
            "AlgorithmWorkspaceSafety.sideBuy": "BUY",
            "AlgorithmWorkspaceSafety.sideSell": "SELL",
            "AlgorithmWorkspaceSafety.sideUnknown": "UNKNOWN",
            "AlgorithmWorkspaceSafety.evidenceConfirmed": "Confirmed",
            "AlgorithmWorkspaceSafety.evidenceStale": "Needs broker confirmation",
            "AlgorithmWorkspaceSafety.evidenceCleared": "Cleared",
            "AlgorithmWorkspaceSafety.evidenceUnavailable": "Evidence unavailable",
            "AlgorithmWorkspaceArea.externalExposureDetectedTitle": (
                "External IB FX exposure"
            ),
            "AlgorithmWorkspaceArea.externalExposureDetectedMessage": (
                "LGE EXCLUSIVE placed workspace {workspace} on SAFETY HOLD "
                "for {symbol}. The Orders page was opened automatically. "
                "Select the external exposure row and click Resolve "
                "reconciliation to see the exact TWS order identifiers. "
                "After resolving the position or orphaned protection in TWS, "
                "press Refresh. Go to Monitoring to inspect the WSP and its "
                "journal."
            ),
            "AlgorithmWorkspaceArea.tipUnlocked": (
                "Unlocked. Click to lock the workspace layout."
            ),
            "AlgorithmWorkspaceArea.tipLocked": (
                "Locked. Click to allow workspace layout changes."
            ),
            "AlgorithmWorkspaceArea.errLayoutLocked": (
                "The workspace layout is locked."
            ),
            "AlgorithmWorkspaceArea.renameTitle": "Rename algorithm workspace",
            "AlgorithmWorkspaceArea.renamePrompt": "New name:",
            "AlgorithmWorkspaceArea.closeBlockedLocked": (
                "The WSP cannot be closed while the layout is locked."
            ),
            "AlgorithmWorkspaceArea.closeBlockedRunning": (
                "Stop the algorithm before closing the WSP."
            ),
            "AlgorithmWorkspaceArea.closeBlockedOrders": (
                "The WSP cannot be closed while it contains active orders: {count}."
            ),
            "AlgorithmWorkspaceArea.runtimeError": "Workspace runtime error: {error}",
            "AlgorithmWorkspaceArea.closeBlockedPositions": (
                "The WSP cannot be closed while it contains open positions: " "{count}."
            ),
            "AlgorithmWorkspaceArea.closeBlockedBrokerOperation": (
                "The WSP cannot be closed during a broker operation."
            ),
            "AlgorithmWorkspaceArea.closeBlockedEvent": (
                "The WSP cannot be closed while a market event is processed."
            ),
            "AlgorithmWorkspaceArea.startBlockedAccount": (
                "Select a broker account before starting broker data mode."
            ),
            "AlgorithmWorkspaceArea.historyDownloadActive": (
                "Stop the WSP runtime before downloading history."
            ),
            "AlgorithmWorkspaceArea.replaySettingsActive": (
                "Stop the WSP runtime before changing Replay settings."
            ),
            "AlgorithmWorkspaceArea.parametersActive": (
                "Stop the WSP runtime before changing algorithm parameters."
            ),
        }
        for key, fallback in entries.items():
            self._lang_mgr.tr(key, fallback)

    def text(self) -> str:
        """Compatibility with MainAppWindow._switch_page()."""
        return self.lbl_title.text()

    def apply_translation(self) -> None:
        """Apply current language to the desktop and all WSP windows."""
        if self._lang_mgr is not None:
            self._register_i18n_keys()

        if self._translator is not None:
            self._translator.apply(self)
        else:
            self.lbl_title.setText("Algorithm desktop")
            self.btn_new.setText("Create")
            self.btn_cascade.setText("Cascade")
            self.btn_tile.setText("Tile")
            self.lbl_empty.setText("No workspace windows yet. Click “Create”.")

        self._refresh_lock_ui(self.btn_lock.isChecked())
        for window in self._windows.values():
            window.apply_translation()

    def restore_from_session_after_layout(self) -> None:
        """Restore WSP only after MainAppWindow and QMdiArea are laid out."""
        if self._session_restored:
            return
        self.refresh_from_session()
        self._session_restored = True
        self.finalize_session_layout()
        QTimer.singleShot(0, self.finalize_session_layout)
        QTimer.singleShot(120, self._finish_session_layout_restore)
        QTimer.singleShot(0, self.refresh_account_balances)

    def finalize_session_layout(self) -> None:
        """Reapply saved WSP geometry against the current MDI viewport."""
        self._reclamp_all_windows(persist=False)

    def refresh_from_session(self) -> None:
        """Restore WSP windows and geometry without starting algorithms."""
        self._restoring = True
        try:
            self.controller.clear_workspace_runtimes()
            self._runtime_log_offsets.clear()
            self._historical_summary_shown.clear()
            for subwindow in list(self._subwindows.values()):
                subwindow.close_from_area()
            self._windows.clear()
            self._subwindows.clear()
            self._restore_geometries.clear()
            self._restore_window_states.clear()
            self._restore_active_workspace_uid = None

            workspaces = self.controller.restore_workspaces()
            for index, workspace in enumerate(workspaces):
                self._append_workspace(
                    workspace,
                    make_active=False,
                    default_index=index,
                )

            manifest = self.controller.repository.load_manifest()
            active_uid = manifest.get("active_workspace_uid")
            self._restore_active_workspace_uid = str(active_uid or "") or None
            active_subwindow = self._subwindows.get(str(active_uid))
            if active_subwindow is not None:
                self.mdi.setActiveSubWindow(active_subwindow)
            elif self.mdi.subWindowList():
                self.mdi.setActiveSubWindow(self.mdi.subWindowList()[0])

            locked = bool(manifest.get("layout_locked", False))
            self.btn_lock.blockSignals(True)
            self.btn_lock.setChecked(locked)
            self.btn_lock.blockSignals(False)
            self._refresh_lock_ui(locked)
            self._update_empty_state()
            self._session_restored = True
        finally:
            self._restoring = False

    def create_workspace(
        self,
        *,
        broker: str,
        account_id: str | None,
        symbol: str,
        timeframe: str,
        algorithm: str,
        display_name: str | None = None,
        data_mode: str = WORKSPACE_DATA_MODE_BROKER,
        account_mode: str | None = None,
        control_mode: str = WORKSPACE_CONTROL_MODE_SEMI,
        parameters: dict[str, Any] | None = None,
        risk_settings: dict[str, Any] | None = None,
        profit_protection: dict[str, Any] | None = None,
        replay_settings: dict[str, Any] | None = None,
        history_download_settings: dict[str, Any] | None = None,
        ui_state: dict[str, Any] | None = None,
    ) -> AlgorithmWorkspace:
        """Create a workspace configuration and one movable WSP."""
        workspace = self.controller.create_workspace(
            broker=broker,
            account_id=account_id,
            symbol=symbol,
            timeframe=timeframe,
            algorithm=algorithm,
            display_name=display_name,
            data_mode=data_mode,
            account_mode=account_mode,
            control_mode=control_mode,
            parameters=parameters,
            risk_settings=risk_settings,
            profit_protection=profit_protection,
            replay_settings=replay_settings,
            history_download_settings=history_download_settings,
            ui_state=ui_state,
        )
        self._append_workspace(
            workspace,
            make_active=True,
            default_index=self.workspace_count(),
        )
        self._update_empty_state()
        self._schedule_ui_state_save(workspace.workspace_uid)
        return workspace

    def rename_workspace(
        self,
        workspace_uid: str,
        display_name: str,
    ) -> AlgorithmWorkspace:
        """Rename a WSP and its MDI title."""
        workspace = self.controller.rename_workspace(
            workspace_uid,
            display_name,
        )
        window = self._windows[workspace.workspace_uid]
        window.update_workspace(workspace)
        subwindow = self._subwindows[workspace.workspace_uid]
        self._apply_subwindow_title(
            subwindow,
            workspace.display_name,
        )
        return workspace

    def update_workspace_history_download_settings(
        self,
        workspace_uid: str,
        values: WorkspaceHistoryDownloadSettings,
    ) -> AlgorithmWorkspace:
        """Persist one WSP broker-history download configuration."""
        workspace = self.controller.update_workspace_history_download_settings(
            workspace_uid,
            values,
        )
        window = self._windows.get(workspace_uid)
        if window is not None:
            window.update_workspace(workspace)
        return workspace

    def update_workspace_replay_settings(
        self,
        workspace_uid: str,
        values: WorkspaceReplaySettings,
    ) -> AlgorithmWorkspace:
        """Persist Replay settings and rebuild the stopped WSP runtime."""
        workspace = self.controller.update_workspace_replay_settings(
            workspace_uid,
            values,
        )
        self.controller.attach_workspace_runtime(workspace)
        self._runtime_log_offsets[workspace_uid] = 0
        self._historical_summary_shown.discard(workspace_uid)
        window = self._windows.get(workspace_uid)
        if window is not None:
            window.update_workspace(workspace)
            self._sync_workspace_runtime(workspace_uid)
        return workspace

    def update_workspace_parameters(
        self,
        workspace_uid: str,
        values: WorkspaceAlgorithmParameters,
        *,
        schema_updates: Mapping[str, object] | None = None,
        indicator_profile_bindings: Mapping[str, object] | None = None,
    ) -> AlgorithmWorkspace:
        """Persist one WSP parameter set and rebuild its stopped runtime."""
        workspace = self.controller.update_workspace_parameters(
            workspace_uid,
            values,
            schema_updates=schema_updates,
            indicator_profile_bindings=indicator_profile_bindings,
        )
        self.controller.attach_workspace_runtime(workspace)
        self._runtime_log_offsets[workspace_uid] = 0
        self._historical_summary_shown.discard(workspace_uid)
        window = self._windows.get(workspace_uid)
        if window is not None:
            window.update_workspace(workspace)
            self._sync_workspace_runtime(workspace_uid)
        return workspace

    def set_layout_locked(self, locked: bool) -> None:
        """Public UI entry point for the workspace layout lock."""
        self.btn_lock.setChecked(bool(locked))

    def set_runtime_engine(self, runtime_engine: Any | None) -> None:
        """Attach shared RuntimeEngine for read-only account/balance discovery."""
        self._runtime_engine = runtime_engine
        self.controller.set_runtime_engine(runtime_engine)
        self._catalog.set_runtime_engine(runtime_engine)
        if runtime_engine is None:
            self._balance_timer.stop()
        else:
            self._balance_timer.start()
            QTimer.singleShot(0, self.refresh_account_balances)

    def refresh_account_balances(self) -> None:
        """Refresh public account names and balances for broker-data WSPs."""
        for workspace_uid in tuple(self._windows):
            self._refresh_workspace_account_balance(workspace_uid)

    def current_workspace_uid(self) -> str | None:
        """Return the active MDI workspace UID."""
        subwindow = self.mdi.activeSubWindow()
        if isinstance(subwindow, AlgorithmMdiSubWindow):
            return subwindow.workspace_uid
        return None

    def workspace_count(self) -> int:
        """Return the number of WSP subwindows."""
        return len(self._subwindows)

    def can_close_workspace(self, workspace_uid: str) -> tuple[bool, str]:
        """Return the guarded close decision for one WSP."""
        return self._can_close_workspace(workspace_uid)

    def workspace_window(
        self,
        workspace_uid: str,
    ) -> AlgorithmWorkspaceWindow | None:
        """Return WSP content for tests and read-only integration."""
        return self._windows.get(workspace_uid)

    def workspace_subwindow(
        self,
        workspace_uid: str,
    ) -> AlgorithmMdiSubWindow | None:
        """Return the QMdiSubWindow wrapper for a WSP."""
        return self._subwindows.get(workspace_uid)

    def set_runtime_snapshot(
        self,
        workspace_uid: str,
        *,
        active_orders_count: int = 0,
        active_positions_count: int = 0,
        current_profit: float = 0.0,
        peak_profit: float = 0.0,
    ) -> None:
        """Apply synthetic/read-only runtime values to one WSP."""
        self.controller.set_workspace_runtime_snapshot(
            workspace_uid,
            active_orders_count=active_orders_count,
            positions_count=active_positions_count,
            current_profit=current_profit,
            peak_profit=peak_profit,
        )
        self._sync_workspace_runtime(workspace_uid)

    def set_workspace_owned_snapshots(
        self,
        workspace_uid: str,
        *,
        order_rows: Iterable[WorkspaceOrderSnapshot | Mapping[str, Any]],
        position_rows: Iterable[WorkspacePositionSnapshot | Mapping[str, Any]],
    ) -> WorkspaceOwnedSnapshot:
        """Filter shared rows and refresh the WSP orders/position tabs."""
        snapshot = self.controller.set_workspace_owned_snapshots(
            workspace_uid,
            order_rows=order_rows,
            position_rows=position_rows,
        )
        self._sync_workspace_runtime(workspace_uid)
        return snapshot

    def cascade_windows(self) -> None:
        """Розкласти normal WSP каскадом у межах актуального MDI viewport."""
        if self.btn_lock.isChecked():
            return
        for subwindow in self._subwindows.values():
            subwindow.restore_workspace_normal()
            subwindow.set_workspace_tiled(False)
        self._cascade_workspaces_in_viewport()
        self._schedule_all_ui_state_save()

    def tile_windows(self) -> None:
        if self.btn_lock.isChecked():
            return
        self._tile_workspaces_equal_grid()
        self._schedule_all_ui_state_save()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Keep MDI-safe maximized WSP windows fitted to the viewport."""
        super().resizeEvent(event)
        QTimer.singleShot(0, self._refresh_maximized_workspace_geometries)

    def _refresh_maximized_workspace_geometries(self) -> None:
        for subwindow in self._subwindows.values():
            if subwindow.is_workspace_maximized():
                subwindow.show_workspace_maximized()

    def flush_pending_ui_state(self) -> None:
        """Persist pending geometry/panel state immediately."""
        pending = list(self._pending_ui_state)
        self._pending_ui_state.clear()
        for workspace_uid in pending:
            window = self._windows.get(workspace_uid)
            subwindow = self._subwindows.get(workspace_uid)
            if window is None or subwindow is None:
                continue
            try:
                self.controller.update_workspace_ui_state(
                    workspace_uid,
                    self._collect_ui_state(window, subwindow),
                )
            except (AlgorithmWorkspaceError, KeyError, ValueError):
                continue

    def shutdown_all_workspaces(self) -> None:
        """Synchronously stop every WSP and close all MDI child windows."""
        if self._shutdown_complete:
            return

        self._shutdown_complete = True
        self._closing_area = True
        self._save_ui_timer.stop()
        self._balance_timer.stop()
        self._replay_timer.stop()
        self.flush_pending_ui_state()

        for workspace_uid in tuple(self._windows):
            runtime = self.controller.workspace_runtime(workspace_uid)
            if runtime is None:
                continue

            try:
                runtime_state = runtime.context.runtime_state
                if runtime_state in {
                    WORKSPACE_STATE_STARTING,
                    WORKSPACE_STATE_RUNNING,
                    WORKSPACE_STATE_ERROR,
                }:
                    runtime.stop("Application shutdown.")
                elif runtime_state == WORKSPACE_STATE_STOPPING:
                    runtime.complete_stop()
                self._sync_workspace_runtime(workspace_uid)
            except WorkspaceRuntimeError:
                logger.exception(
                    "Cannot stop workspace during application shutdown: %s",
                    workspace_uid,
                )

        self.controller.set_runtime_engine(None)
        self._runtime_engine = None

        subwindows: list[AlgorithmMdiSubWindow] = list(self._subwindows.values())
        for subwindow in subwindows:
            if isinstance(subwindow, AlgorithmMdiSubWindow):
                subwindow.close_from_area()

    def shutdown_diagnostics(self) -> dict[str, bool]:
        """Return public shutdown state for diagnostics and regression tests."""
        timers = (
            self._save_ui_timer,
            self._balance_timer,
            self._replay_timer,
        )
        return {
            "timers_stopped": all(not timer.isActive() for timer in timers),
            "runtime_engine_detached": self._runtime_engine is None,
        }

    def closeEvent(self, event: QCloseEvent) -> None:
        self.shutdown_all_workspaces()
        super().closeEvent(event)

    def _open_create_dialog(self) -> None:
        dialog = AlgorithmWorkspaceCreateDialog(
            self._lang_mgr,
            self._catalog,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            self.create_workspace(**dialog.workspace_values())
        except WorkspaceLayoutLockedError:
            QMessageBox.warning(
                self,
                "LGE",
                self._tr(
                    "AlgorithmWorkspaceArea.errLayoutLocked",
                    "The workspace layout is locked.",
                ),
            )
        except (AlgorithmWorkspaceError, KeyError, ValueError) as exc:
            QMessageBox.warning(self, "LGE", str(exc))

    def _append_workspace(
        self,
        workspace: AlgorithmWorkspace,
        *,
        make_active: bool,
        default_index: int,
    ) -> None:
        window = AlgorithmWorkspaceWindow(
            workspace,
            self._lang_mgr,
            self.mdi,
        )
        subwindow = AlgorithmMdiSubWindow(
            workspace.workspace_uid,
            lambda uid=workspace.workspace_uid: self._can_close_workspace(uid),
            self.mdi,
        )
        subwindow.setWidget(window)
        self._apply_subwindow_title(
            subwindow,
            workspace.display_name,
        )
        subwindow.setMinimumSize(500, 390)

        window.rename_requested.connect(self._on_rename_requested)
        window.start_requested.connect(self._on_start_requested)
        window.stop_requested.connect(self._on_stop_requested)
        window.history_download_requested.connect(self._on_history_download_requested)
        window.replay_settings_requested.connect(self._on_replay_settings_requested)
        window.parameters_requested.connect(self._on_parameters_requested)
        window.modes_changed.connect(self._on_modes_changed)
        window.replay_pause_requested.connect(self._on_replay_pause_requested)
        window.replay_step_requested.connect(self._on_replay_step_requested)
        window.replay_tick_requested.connect(self._on_replay_tick_requested)
        window.replay_speed_changed.connect(self._on_replay_speed_changed)
        window.chart_visible_count_requested.connect(
            self._on_chart_visible_count_requested
        )
        window.chart_visible_start_requested.connect(
            self._on_chart_visible_start_requested
        )
        window.chart_timestamp_requested.connect(self._on_chart_timestamp_requested)
        window.chart_latest_requested.connect(self._on_chart_latest_requested)
        window.chart_protection_change_requested.connect(
            self._on_chart_protection_change_requested
        )
        window.active_panel_changed.connect(self._schedule_ui_state_save)
        subwindow.geometry_changed.connect(self._schedule_ui_state_save)
        subwindow.close_blocked.connect(self._on_close_blocked)
        subwindow.user_closed.connect(self._on_user_closed)

        self._windows[workspace.workspace_uid] = window
        self._subwindows[workspace.workspace_uid] = subwindow
        self.controller.attach_workspace_runtime(workspace)
        self._runtime_log_offsets[workspace.workspace_uid] = 0
        self.mdi.addSubWindow(subwindow)
        subwindow.show()

        requested_geometry = self._requested_geometry(workspace, default_index)
        window_state = str(workspace.ui_state.get("window_state") or "NORMAL").upper()
        if self._restoring:
            self._restore_geometries[workspace.workspace_uid] = QRect(
                requested_geometry
            )
            self._restore_window_states[workspace.workspace_uid] = window_state

        subwindow.apply_system_geometry(self._clamp_geometry(requested_geometry))
        subwindow.set_layout_locked(self.btn_lock.isChecked())
        window.set_layout_locked(self.btn_lock.isChecked())

        if window_state == "MINIMIZED":
            subwindow.showMinimized()
        elif window_state == "MAXIMIZED":
            subwindow.show_workspace_maximized()

        if make_active:
            self.mdi.setActiveSubWindow(subwindow)
            if window_state == "MINIMIZED":
                subwindow.restore_workspace_normal()
            self._refresh_active_workspace_indicators(workspace.workspace_uid)

        self._refresh_workspace_account_balance(workspace.workspace_uid)
        self._sync_workspace_runtime(workspace.workspace_uid)

    def _on_rename_requested(self, workspace_uid: str) -> None:
        window = self._windows.get(workspace_uid)
        if window is None:
            return

        display_name, accepted = QInputDialog.getText(
            self,
            self._tr(
                "AlgorithmWorkspaceArea.renameTitle",
                "Rename algorithm workspace",
            ),
            self._tr(
                "AlgorithmWorkspaceArea.renamePrompt",
                "New name:",
            ),
            text=window.full_display_name,
        )
        if not accepted:
            return

        try:
            self.rename_workspace(workspace_uid, display_name)
        except (
            AlgorithmWorkspaceError,
            WorkspaceLayoutLockedError,
            ValueError,
        ) as exc:
            QMessageBox.warning(self, "LGE", str(exc))

    def _on_start_requested(self, workspace_uid: str) -> None:
        window = self._windows.get(workspace_uid)
        if window is None:
            return

        workspace = self.controller.repository.load_workspace(workspace_uid)
        if (
            workspace.data_mode == WORKSPACE_DATA_MODE_BROKER
            and not workspace.account_id
        ):
            QMessageBox.warning(
                self,
                "LGE",
                self._tr(
                    "AlgorithmWorkspaceArea.startBlockedAccount",
                    "Select a broker account before starting broker data mode.",
                ),
            )
            return

        self._historical_summary_shown.discard(workspace_uid)
        try:
            workspace = self.controller.mark_workspace_started_once(workspace_uid)
            window.set_has_started_once(workspace.has_started_once)
            self.controller.begin_workspace_runtime_start(workspace_uid)
            self._sync_workspace_runtime(workspace_uid)
        except (WorkspaceReplayError, WorkspaceRuntimeError, ValueError) as exc:
            self._show_runtime_error(workspace_uid, exc)
            return

        QTimer.singleShot(
            0,
            lambda uid=workspace_uid: self._complete_runtime_start(uid),
        )

    def _complete_runtime_start(self, workspace_uid: str) -> None:
        try:
            self.controller.complete_workspace_runtime_start(workspace_uid)
        except (WorkspaceReplayError, WorkspaceRuntimeError, ValueError) as exc:
            self._show_runtime_error(workspace_uid, exc)
            return
        self._sync_workspace_runtime(workspace_uid)

    def _on_stop_requested(self, workspace_uid: str) -> None:
        self._replay_fast_ui_last_sync.pop(workspace_uid, None)
        try:
            self.controller.begin_workspace_runtime_stop(workspace_uid)
            self._sync_workspace_runtime(workspace_uid)
        except WorkspaceRuntimeError as exc:
            self._show_runtime_error(workspace_uid, exc)
            return

        QTimer.singleShot(
            0,
            lambda uid=workspace_uid: self._complete_runtime_stop(uid),
        )

    def _complete_runtime_stop(self, workspace_uid: str) -> None:
        try:
            self.controller.complete_workspace_runtime_stop(workspace_uid)
        except WorkspaceRuntimeError as exc:
            self._show_runtime_error(workspace_uid, exc)
            return
        self._sync_workspace_runtime(workspace_uid)

    def _on_replay_pause_requested(self, workspace_uid: str) -> None:
        self._replay_fast_ui_last_sync.pop(workspace_uid, None)
        try:
            self.controller.toggle_workspace_replay_pause(workspace_uid)
        except (WorkspaceReplayError, WorkspaceRuntimeError) as exc:
            self._show_runtime_error(workspace_uid, exc)
            return
        self._sync_workspace_runtime(workspace_uid)

    def _on_replay_step_requested(self, workspace_uid: str) -> None:
        try:
            self.controller.step_workspace_replay_strategy_bar(workspace_uid)
        except (WorkspaceReplayError, WorkspaceRuntimeError) as exc:
            self._show_runtime_error(workspace_uid, exc)
            return
        self._sync_workspace_runtime(workspace_uid)

    def _on_replay_tick_requested(self, workspace_uid: str) -> None:
        try:
            self.controller.step_workspace_replay_tick(workspace_uid)
        except (WorkspaceReplayError, WorkspaceRuntimeError) as exc:
            self._show_runtime_error(workspace_uid, exc)
            return
        self._sync_workspace_runtime(workspace_uid)

    def _on_replay_speed_changed(
        self,
        workspace_uid: str,
        speed: int,
    ) -> None:
        self._replay_fast_ui_last_sync.pop(workspace_uid, None)
        try:
            self.controller.set_workspace_replay_speed(workspace_uid, speed)
        except (WorkspaceReplayError, WorkspaceRuntimeError) as exc:
            self._show_runtime_error(workspace_uid, exc)
            return
        self._sync_workspace_runtime(workspace_uid)

    def _on_chart_visible_count_requested(
        self,
        workspace_uid: str,
        visible_count: int,
    ) -> None:
        self.controller.set_workspace_chart_visible_count(
            workspace_uid,
            visible_count,
        )
        self._sync_workspace_runtime(workspace_uid)

    def _on_chart_visible_start_requested(
        self,
        workspace_uid: str,
        visible_start: int,
    ) -> None:
        self.controller.scroll_workspace_chart_to(
            workspace_uid,
            visible_start,
        )
        self._sync_workspace_runtime(workspace_uid)

    def _on_chart_timestamp_requested(
        self,
        workspace_uid: str,
        timestamp: object,
        exact: bool,
    ) -> None:
        if not isinstance(timestamp, datetime):
            return
        try:
            self.controller.scroll_workspace_chart_to_timestamp(
                workspace_uid,
                timestamp,
                exact=exact,
            )
        except WorkspaceRuntimeError as exc:
            self._show_runtime_error(workspace_uid, exc)
            return
        window = self._windows.get(workspace_uid)
        if window is not None:
            window.tabs_workspace.setCurrentIndex(INDEX_BY_PANEL[WORKSPACE_PANEL_CHART])
        self._sync_workspace_runtime(workspace_uid)
        if window is not None:
            window.chart_widget.focus_timestamp(timestamp, exact=exact)

    def _on_chart_latest_requested(self, workspace_uid: str) -> None:
        self.controller.scroll_workspace_chart_to_latest(workspace_uid)
        self._sync_workspace_runtime(workspace_uid)

    def _on_chart_protection_change_requested(
        self,
        workspace_uid: str,
        position_id: str,
        field_name: str,
        price: float,
    ) -> None:
        """Commit one validated paused-Replay SL/TP drag through runtime."""
        try:
            self.controller.modify_workspace_replay_position_protection(
                workspace_uid,
                position_id,
                field_name,
                price,
                source="CHART_DRAG",
            )
        except WorkspaceRuntimeError as exc:
            self._show_runtime_error(workspace_uid, exc)
            return
        self._sync_workspace_runtime(workspace_uid)

    def advance_replay_runtimes(self) -> None:
        """Advance Replay in responsive chunks and poll Live Read-only feeds."""
        for workspace_uid in tuple(self._windows):
            runtime = self.controller.workspace_runtime(workspace_uid)
            if runtime is None:
                continue
            if runtime.context.data_mode == WORKSPACE_DATA_MODE_BROKER:
                if runtime.context.runtime_state not in {
                    WORKSPACE_STATE_STARTING,
                    WORKSPACE_STATE_RUNNING,
                }:
                    continue
                if (
                    runtime.context.runtime_state == WORKSPACE_STATE_STARTING
                    and runtime.context.startup_phase
                    not in {
                        WORKSPACE_STARTUP_PHASE_WAIT_BROKER,
                        WORKSPACE_STARTUP_PHASE_SAFETY_HOLD_EXTERNAL_EXPOSURE,
                        WORKSPACE_STARTUP_PHASE_WAIT_SPREAD,
                        WORKSPACE_STARTUP_PHASE_READY,
                        WORKSPACE_STARTUP_PHASE_RUNNING,
                    }
                ):
                    continue
                previous_state = runtime.context.runtime_state
                previous_phase = runtime.context.startup_phase
                previous_safety_revision = runtime.context.safety_hold_revision
                try:
                    event = self.controller.advance_workspace_broker_market(
                        workspace_uid
                    )
                except WorkspaceRuntimeError as exc:
                    self._show_runtime_error(workspace_uid, exc)
                    continue
                if (
                    event is not None
                    or runtime.context.runtime_state != previous_state
                    or runtime.context.startup_phase != previous_phase
                    or runtime.context.safety_hold_revision != previous_safety_revision
                ):
                    self._sync_workspace_runtime(workspace_uid)
                continue

            session = runtime.replay_session
            if session is None or session.completed:
                self._replay_burst_state.pop(workspace_uid, None)
                continue
            if workspace_uid in self._replay_burst_state:
                continue
            quota = replay_ui_cycle_quota(session.speed)
            self._replay_burst_state[workspace_uid] = (session.speed, quota)
            if session.speed == REPLAY_SPEED_MAX_FAST:
                self._replay_fast_ui_last_sync[workspace_uid] = monotonic()
            else:
                self._replay_fast_ui_last_sync.pop(workspace_uid, None)
            self._advance_replay_burst(workspace_uid)

    def _advance_replay_burst(self, workspace_uid: str) -> None:
        """Process one responsive Replay burst and yield back to Qt.

        Normal high speeds keep the conservative 16-event scheduler rail.
        MAX FAST may execute several adaptive compute batches in one callback,
        but stops when its short wall-clock budget is exhausted. This reduces
        QTimer round-trips without turning Pause/Stop into a long GUI-thread
        wait. Heavy MAX FAST UI synchronization is timed from the *end* of the
        previous sync so an expensive repaint cannot immediately trigger the
        next repaint.
        """
        state = self._replay_burst_state.get(workspace_uid)
        runtime = self.controller.workspace_runtime(workspace_uid)
        if state is None or runtime is None:
            self._replay_burst_state.pop(workspace_uid, None)
            return
        session = runtime.replay_session
        burst_speed, remaining = state
        if (
            session is None
            or session.completed
            or session.state != REPLAY_STATE_RUNNING
            or session.speed != burst_speed
            or runtime.context.runtime_state
            not in {WORKSPACE_STATE_STARTING, WORKSPACE_STATE_RUNNING}
        ):
            self._replay_burst_state.pop(workspace_uid, None)
            self._replay_fast_ui_last_sync.pop(workspace_uid, None)
            if session is not None and session.completed:
                self._show_historical_summary_if_ready(workspace_uid)
            return

        batch_size = replay_ui_batch_size(remaining)
        if batch_size <= 0:
            self._replay_burst_state.pop(workspace_uid, None)
            return

        processed_events = 0
        burst_started = monotonic()
        while True:
            batch_started = monotonic()
            try:
                events = self.controller.advance_workspace_replay(
                    workspace_uid,
                    max_events=batch_size,
                )
            except (WorkspaceReplayError, WorkspaceRuntimeError) as exc:
                self._replay_burst_state.pop(workspace_uid, None)
                runtime.fail(exc)
                self._show_runtime_error(workspace_uid, exc)
                return

            processed_events += len(events)
            session = runtime.replay_session
            completed = session is not None and session.completed
            if (
                burst_speed != REPLAY_SPEED_MAX_FAST
                or not events
                or completed
                or session is None
                or session.state != REPLAY_STATE_RUNNING
                or session.speed != burst_speed
            ):
                break

            batch_elapsed = monotonic() - batch_started
            if monotonic() - burst_started >= REPLAY_MAX_FAST_TIME_BUDGET_SECONDS:
                break
            batch_size = replay_max_fast_next_batch_size(
                len(events),
                batch_elapsed,
            )

        session = runtime.replay_session
        completed = session is not None and session.completed
        should_sync = processed_events > 0 or completed
        if should_sync and burst_speed == REPLAY_SPEED_MAX_FAST and not completed:
            now = monotonic()
            last_sync = self._replay_fast_ui_last_sync.get(workspace_uid, now)
            should_sync = replay_ui_should_refresh(
                burst_speed,
                now - last_sync,
            )
        if should_sync:
            self._sync_workspace_runtime(workspace_uid)
            if burst_speed == REPLAY_SPEED_MAX_FAST and not completed:
                self._replay_fast_ui_last_sync[workspace_uid] = monotonic()
        if session is None or session.completed:
            self._replay_burst_state.pop(workspace_uid, None)
            self._replay_fast_ui_last_sync.pop(workspace_uid, None)
            self._show_historical_summary_if_ready(workspace_uid)
            return
        if session.state != REPLAY_STATE_RUNNING or session.speed != burst_speed:
            self._replay_burst_state.pop(workspace_uid, None)
            self._replay_fast_ui_last_sync.pop(workspace_uid, None)
            return

        next_remaining = None if remaining is None else remaining - processed_events
        if processed_events <= 0 or (
            next_remaining is not None and next_remaining <= 0
        ):
            self._replay_burst_state.pop(workspace_uid, None)
            return
        self._replay_burst_state[workspace_uid] = (burst_speed, next_remaining)
        QTimer.singleShot(0, lambda uid=workspace_uid: self._advance_replay_burst(uid))

    def _show_historical_summary_if_ready(self, workspace_uid: str) -> None:
        runtime = self.controller.workspace_runtime(workspace_uid)
        if runtime is None or runtime.historical_summary is None:
            return
        session = runtime.replay_session
        if session is None or session.history_report is None:
            return
        if workspace_uid in self._historical_summary_shown:
            return
        self._historical_summary_shown.add(workspace_uid)
        dialog = AlgorithmWorkspaceHistoricalSummaryDialog(
            runtime.historical_summary,
            self._lang_mgr,
            self,
        )
        dialog.exec()

    def _show_runtime_error(
        self,
        workspace_uid: str,
        error: Exception,
    ) -> None:
        runtime = self.controller.workspace_runtime(workspace_uid)
        if (
            runtime is not None
            and runtime.context.runtime_state != WORKSPACE_STATE_ERROR
        ):
            runtime.fail(error)
        self._sync_workspace_runtime(workspace_uid)
        message = self._tr(
            "AlgorithmWorkspaceArea.runtimeError",
            "Workspace runtime error: {error}",
        ).format(error=str(error))
        QMessageBox.warning(self, "LGE", message)

    @staticmethod
    def _play_external_exposure_alert() -> None:
        """Play one system warning sound for a newly entered safety hold."""
        QApplication.beep()

    def _sync_workspace_runtime(self, workspace_uid: str) -> None:
        window = self._windows.get(workspace_uid)
        runtime = self.controller.workspace_runtime(workspace_uid)
        if window is None or runtime is None:
            return

        context = runtime.context
        tick_available = False
        window.set_runtime_status(
            context.runtime_state,
            context.startup_phase,
        )
        window.set_execution_safety_hold(
            active=context.safety_hold_active,
            message=context.safety_hold_message,
            account_id=str(context.account_id or ""),
            symbol=context.symbol,
            signed_volume=context.safety_hold_signed_volume,
            evidence_status=str(context.safety_hold_evidence_status or ""),
            confirmation_required=context.safety_hold_confirmation_required,
        )
        if context.safety_hold_active:
            if workspace_uid not in self._external_hold_notified:
                self._external_hold_notified.add(workspace_uid)
                self._play_external_exposure_alert()
                self.external_exposure_resolution_requested.emit(
                    window.full_display_name or workspace_uid,
                    str(context.account_id or ""),
                    context.symbol,
                )
        else:
            self._external_hold_notified.discard(workspace_uid)
        window.set_runtime_snapshot(
            active_orders_count=context.active_orders_count,
            active_positions_count=context.positions_count,
            current_profit=context.current_profit,
            peak_profit=context.peak_profit,
        )
        if context.data_mode == WORKSPACE_DATA_MODE_REPLAY:
            initial_balance = context.replay_initial_balance
            realized_profit = context.daily_realized_pnl or 0.0
            balance = (
                initial_balance + realized_profit
                if initial_balance is not None
                else None
            )
            equity = context.risk_equity
            if equity is None:
                equity = balance
            window.set_replay_financial_snapshot(
                initial_balance=initial_balance,
                balance=balance,
                equity=equity,
            )
        window.set_owned_snapshot(runtime.owned_snapshot)
        window.set_signal_records(runtime.signal_records_for_ui())
        window.set_chart_snapshot(runtime.chart_snapshot())

        session = runtime.replay_session
        current_strategy_event = context.current_market_event
        current_execution_event = context.current_execution_event
        chart_execution_event = (
            current_execution_event
            if (
                session is not None
                and session.multi_resolution
                and current_execution_event is not None
                and (
                    current_strategy_event is None
                    or current_execution_event.timestamp
                    > current_strategy_event.timestamp
                )
            )
            else None
        )
        window.set_chart_execution_event(chart_execution_event)
        if (
            session is None
            and context.data_mode == WORKSPACE_DATA_MODE_BROKER
            and context.runtime_state
            in {WORKSPACE_STATE_STARTING, WORKSPACE_STATE_RUNNING}
        ):
            current_event = context.current_market_event
            time_text = "—"
            if current_event is not None:
                time_text = current_event.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
            spread_text = "—"
            if context.current_spread is not None:
                spread_text = f"{context.current_spread:.6f}"
            startup_phase_text = self._translated_code(
                context.startup_phase,
                WORKSPACE_STARTUP_PHASE_LABELS,
            )
            live_label = self._tr(
                "AlgorithmWorkspaceWindow.liveReadOnly",
                "Live Read-only",
            )
            if context.safety_hold_active:
                status_text = self._tr(
                    "AlgorithmWorkspaceWindow.safetyHoldExternalExposureStatus",
                    "SAFETY HOLD • {symbol} • new LGE execution is blocked • "
                    "Orders → Resolve reconciliation",
                ).format(symbol=context.symbol)
            else:
                status_text = (
                    f"{live_label} • {startup_phase_text} • "
                    f"{context.market_event_count} events • "
                    f"spread {spread_text} • {time_text}"
                )
            paused = False
            speed = int(runtime.replay_settings.get("speed", 1))
            active = False
        elif session is None:
            status_text = self._tr(
                "AlgorithmWorkspaceWindow.replayNotConnected",
                "Historical Replay is stopped.",
            )
            paused = False
            speed = int(runtime.replay_settings.get("speed", 1))
            active = False
        else:
            current_event = context.current_market_event
            execution_event = context.current_execution_event
            time_text = "—"
            if current_event is not None:
                time_text = current_event.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
            if (
                session.multi_resolution
                and execution_event is not None
                and (
                    current_event is None
                    or execution_event.timestamp > current_event.timestamp
                )
            ):
                tick_time = execution_event.timestamp.strftime("%H:%M:%S UTC")
                tick_label = self._tr(
                    "AlgorithmWorkspaceWindow.replayTickLabel",
                    "Tick",
                )
                time_text = (
                    f"{time_text} • {tick_label} {tick_time} "
                    f"• Bid {execution_event.bid:.5f} "
                    f"• Ask {execution_event.ask:.5f}"
                )
            spread_text = "—"
            if context.current_spread is not None:
                spread_text = f"{context.current_spread:.6f}"
            replay_state_text = self._translated_code(
                session.state,
                REPLAY_STATE_LABELS,
            )
            if session.completed:
                status_text = (
                    f"{replay_state_text} • "
                    f"{session.index}/{len(session.events)} • "
                    f"spread {spread_text} • {time_text}"
                )
            else:
                startup_phase_text = self._translated_code(
                    context.startup_phase,
                    WORKSPACE_STARTUP_PHASE_LABELS,
                )
                status_text = (
                    f"{replay_state_text} • {startup_phase_text} • "
                    f"{session.index}/{len(session.events)} • "
                    f"spread {spread_text} • {time_text}"
                )
            history_report = session.history_report
            if history_report is not None:
                quality_text = self._tr(
                    "AlgorithmWorkspaceWindow.historyQuality",
                    "skipped {filtered} • gaps {gaps} • quotes {quotes}",
                ).format(
                    filtered=history_report.filtered_rows,
                    gaps=history_report.gap_count,
                    quotes=history_report.derived_quotes,
                )
                status_text = f"{status_text} • {quality_text}"
            paused = session.state == REPLAY_STATE_PAUSED
            speed = session.speed
            active = (
                context.runtime_state
                in {WORKSPACE_STATE_STARTING, WORKSPACE_STATE_RUNNING}
                and not session.completed
            )
            tick_available = runtime.replay_tick_available
        window.set_replay_snapshot(
            status_text=status_text,
            paused=paused,
            speed=speed,
            active=active,
            tick_available=tick_available,
        )

        offset = self._runtime_log_offsets.get(workspace_uid, 0)
        entries = runtime.journal_from(offset)
        if entries:
            if offset == 0:
                window.clear_journal()
            window.append_journal_entries(entries)
            self._runtime_log_offsets[workspace_uid] = offset + len(entries)

    def _on_history_download_requested(self, workspace_uid: str) -> None:
        runtime = self.controller.workspace_runtime(workspace_uid)
        if runtime is not None and runtime.context.runtime_state in (
            ACTIVE_RUNTIME_STATES | {WORKSPACE_STATE_ERROR}
        ):
            QMessageBox.warning(
                self,
                "LGE",
                self._tr(
                    "AlgorithmWorkspaceArea.historyDownloadActive",
                    "Stop the WSP runtime before downloading history.",
                ),
            )
            return

        try:
            workspace = self.controller.load_workspace(workspace_uid)
            if workspace.broker == "CTRADER":

                def download(
                    start_utc,
                    end_utc,
                    progress_callback=None,
                    *,
                    uid=workspace_uid,
                ):
                    return self.controller.download_workspace_ctrader_history(
                        uid,
                        self._runtime_engine,
                        start_utc,
                        end_utc,
                        progress_callback=progress_callback,
                    )

            elif workspace.broker == "IB":

                def download(
                    start_utc,
                    end_utc,
                    progress_callback=None,
                    *,
                    uid=workspace_uid,
                ):
                    return self.controller.download_workspace_ib_history(
                        uid,
                        self._runtime_engine,
                        start_utc,
                        end_utc,
                        progress_callback=progress_callback,
                    )

            else:
                download = None

            dialog = AlgorithmWorkspaceHistoryDownloadDialog(
                workspace,
                self._lang_mgr,
                self,
                history_download=download,
            )
            dialog_result = dialog.exec()
            exported = dialog.downloaded_result
            if exported is None:
                return

            workspace = self.update_workspace_history_download_settings(
                workspace_uid,
                dialog.history_values(),
            )
            if (
                dialog_result != QDialog.DialogCode.Accepted
                or not dialog.use_for_replay_requested
            ):
                return

            existing = WorkspaceReplaySettings.from_workspace(workspace)
            replay_values = WorkspaceReplaySettings(
                source_type=WORKSPACE_REPLAY_SOURCE_CSV,
                file_path=str(exported.file_path),
                start_utc=exported.first_timestamp.isoformat(),
                end_utc=exported.last_timestamp.isoformat(),
                source_timezone="UTC",
                delimiter="AUTO",
                decimal_separator=".",
                spread=existing.spread,
                source_name=exported.source_name,
                source_timeframe=workspace.timeframe,
                speed=existing.speed,
            )
            self.update_workspace_replay_settings(
                workspace_uid,
                replay_values,
            )
        except (
            AlgorithmWorkspaceError,
            KeyError,
            ValueError,
            WorkspaceRuntimeError,
        ) as exc:
            QMessageBox.warning(self, "LGE", str(exc))

    def _on_replay_settings_requested(self, workspace_uid: str) -> None:
        runtime = self.controller.workspace_runtime(workspace_uid)
        if runtime is not None and runtime.context.runtime_state in (
            ACTIVE_RUNTIME_STATES | {WORKSPACE_STATE_ERROR}
        ):
            QMessageBox.warning(
                self,
                "LGE",
                self._tr(
                    "AlgorithmWorkspaceArea.replaySettingsActive",
                    "Stop the WSP runtime before changing Replay settings.",
                ),
            )
            return

        try:
            workspace = self.controller.load_workspace(workspace_uid)
            dialog = AlgorithmWorkspaceReplayDialog(
                workspace,
                self._lang_mgr,
                self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            self.update_workspace_replay_settings(
                workspace_uid,
                dialog.replay_values(),
            )
        except (
            AlgorithmWorkspaceError,
            KeyError,
            ValueError,
            WorkspaceRuntimeError,
        ) as exc:
            QMessageBox.warning(self, "LGE", str(exc))

    def _on_parameters_requested(self, workspace_uid: str) -> None:
        runtime = self.controller.workspace_runtime(workspace_uid)
        if runtime is not None and runtime.context.runtime_state in (
            ACTIVE_RUNTIME_STATES | {WORKSPACE_STATE_ERROR}
        ):
            QMessageBox.warning(
                self,
                "LGE",
                self._tr(
                    "AlgorithmWorkspaceArea.parametersActive",
                    "Stop the WSP runtime before changing algorithm " "parameters.",
                ),
            )
            return

        try:
            workspace = self.controller.load_workspace(workspace_uid)
            dialog = AlgorithmWorkspaceParametersDialog(
                workspace,
                self._lang_mgr,
                self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            self.update_workspace_parameters(
                workspace_uid,
                dialog.parameter_values(),
                schema_updates=dialog.schema_updates(),
                indicator_profile_bindings=(dialog.indicator_profile_bindings()),
            )
        except (
            AlgorithmWorkspaceError,
            KeyError,
            ValueError,
            WorkspaceRuntimeError,
        ) as exc:
            QMessageBox.warning(self, "LGE", str(exc))

    def _on_modes_changed(
        self,
        workspace_uid: str,
        data_mode: str,
        control_mode: str,
    ) -> None:
        try:
            workspace = self.controller.update_workspace_modes(
                workspace_uid,
                data_mode=data_mode,
                control_mode=control_mode,
            )
            self.controller.attach_workspace_runtime(workspace)
            self._runtime_log_offsets[workspace_uid] = 0
            self._sync_workspace_runtime(workspace_uid)
        except (
            AlgorithmWorkspaceError,
            KeyError,
            ValueError,
            WorkspaceRuntimeError,
        ) as exc:
            QMessageBox.warning(self, "LGE", str(exc))

    def _on_lock_toggled(self, locked: bool) -> None:
        self.controller.set_layout_locked(locked)
        self._refresh_lock_ui(locked)

    def _refresh_lock_ui(self, locked: bool) -> None:
        self.btn_new.setEnabled(not locked)
        self.btn_cascade.setEnabled(not locked)
        self.btn_tile.setEnabled(not locked)
        self.btn_lock.setIcon(QIcon(LOCK_CLOSE_ICON if locked else LOCK_OPEN_ICON))
        self.btn_lock.setToolTip(
            self._tr(
                "AlgorithmWorkspaceArea.tipLocked",
                "Locked. Click to allow workspace layout changes.",
            )
            if locked
            else self._tr(
                "AlgorithmWorkspaceArea.tipUnlocked",
                "Unlocked. Click to lock the workspace layout.",
            )
        )

        for workspace_uid, window in self._windows.items():
            window.set_layout_locked(locked)
            subwindow = self._subwindows.get(workspace_uid)
            if subwindow is not None:
                subwindow.set_layout_locked(locked)

    def _on_subwindow_activated(
        self,
        subwindow: QMdiSubWindow | None,
    ) -> None:
        workspace_uid = (
            subwindow.workspace_uid
            if isinstance(subwindow, AlgorithmMdiSubWindow)
            else None
        )
        self._refresh_active_workspace_indicators(workspace_uid)
        if self._restoring or self._closing_area:
            return
        self.controller.set_active_workspace(workspace_uid)

    def _refresh_active_workspace_indicators(
        self,
        active_workspace_uid: str | None,
    ) -> None:
        for workspace_uid, window in self._windows.items():
            window.set_active_workspace(workspace_uid == active_workspace_uid)

    def _can_close_workspace(self, workspace_uid: str) -> tuple[bool, str]:
        if self._closing_area:
            return True, ""
        if self.btn_lock.isChecked():
            return False, self._tr(
                "AlgorithmWorkspaceArea.closeBlockedLocked",
                "The WSP cannot be closed while the layout is locked.",
            )

        window = self._windows.get(workspace_uid)
        if window is None:
            return True, ""
        runtime = self.controller.workspace_runtime(workspace_uid)
        if runtime is None:
            return True, ""
        result = runtime.close_guard_result()
        blocker = result.primary_blocker
        if blocker is None:
            return True, ""
        return False, self._close_blocker_message(blocker)

    def _close_blocker_message(self, blocker: WorkspaceCloseBlocker) -> str:
        if blocker.code == WORKSPACE_CLOSE_BLOCK_RUNTIME_ACTIVE:
            return self._tr(
                "AlgorithmWorkspaceArea.closeBlockedRunning",
                "Stop the algorithm before closing the WSP.",
            )
        if blocker.code == WORKSPACE_CLOSE_BLOCK_ACTIVE_ORDERS:
            message = self._tr(
                "AlgorithmWorkspaceArea.closeBlockedOrders",
                "The WSP cannot be closed while it contains active orders: " "{count}.",
            )
            return message.format(count=blocker.details.get("count", 0))
        if blocker.code == WORKSPACE_CLOSE_BLOCK_OPEN_POSITIONS:
            message = self._tr(
                "AlgorithmWorkspaceArea.closeBlockedPositions",
                "The WSP cannot be closed while it contains open positions: "
                "{count}.",
            )
            return message.format(count=blocker.details.get("count", 0))
        if blocker.code == WORKSPACE_CLOSE_BLOCK_BROKER_OPERATION:
            return self._tr(
                "AlgorithmWorkspaceArea.closeBlockedBrokerOperation",
                "The WSP cannot be closed during a broker operation.",
            )
        if blocker.code in {
            WORKSPACE_CLOSE_BLOCK_MARKET_EVENT,
            WORKSPACE_CLOSE_BLOCK_REPLAY_STEP,
        }:
            return self._tr(
                "AlgorithmWorkspaceArea.closeBlockedEvent",
                "The WSP cannot be closed while a market event is processed.",
            )
        if blocker.code == WORKSPACE_CLOSE_BLOCK_PENDING_CLOSE:
            message = self._tr(
                "AlgorithmWorkspaceArea.closeBlockedPendingClose",
                "The WSP cannot be closed while a profit-protection CLOSE "
                "decision is pending: {count}.",
            )
            return message.format(count=blocker.details.get("count", 0))
        return blocker.reason

    def _on_close_blocked(self, _workspace_uid: str, reason: str) -> None:
        QMessageBox.warning(self, "LGE", reason)

    def _on_user_closed(self, workspace_uid: str) -> None:
        self._external_hold_notified.discard(workspace_uid)
        self._historical_summary_shown.discard(workspace_uid)
        if self._closing_area:
            return
        try:
            next_active_uid = self.controller.delete_workspace(workspace_uid)
        except (WorkspaceLayoutLockedError, WorkspaceRuntimeError) as exc:
            QMessageBox.warning(self, "LGE", str(exc))
            return

        self._pending_ui_state.discard(workspace_uid)
        self._runtime_log_offsets.pop(workspace_uid, None)
        self._windows.pop(workspace_uid, None)
        self._subwindows.pop(workspace_uid, None)
        self._update_empty_state()

        next_subwindow = self._subwindows.get(next_active_uid or "")
        if next_subwindow is not None:
            self.mdi.setActiveSubWindow(next_subwindow)
        elif not self._subwindows:
            self._refresh_active_workspace_indicators(None)
            self.controller.set_active_workspace(None)

    def _schedule_ui_state_save(self, workspace_uid: str) -> None:
        if self._restoring or self._closing_area:
            return
        if workspace_uid not in self._subwindows:
            return
        self._pending_ui_state.add(workspace_uid)
        self._save_ui_timer.start()

    def _schedule_all_ui_state_save(self) -> None:
        for workspace_uid in self._subwindows:
            self._pending_ui_state.add(workspace_uid)
        self._save_ui_timer.start()

    @staticmethod
    def _collect_ui_state(
        window: AlgorithmWorkspaceWindow,
        subwindow: AlgorithmMdiSubWindow,
    ) -> dict[str, Any]:
        geometry = subwindow.normal_workspace_geometry()

        if subwindow.isMinimized():
            window_state = "MINIMIZED"
        elif subwindow.is_workspace_maximized():
            window_state = "MAXIMIZED"
        else:
            window_state = "NORMAL"

        return {
            "geometry": {
                "x": geometry.x(),
                "y": geometry.y(),
                "width": geometry.width(),
                "height": geometry.height(),
            },
            "window_state": window_state,
            "active_panel": window.active_panel(),
        }

    @staticmethod
    def _requested_geometry(
        workspace: AlgorithmWorkspace,
        default_index: int,
    ) -> QRect:
        geometry_data = workspace.ui_state.get("geometry")
        if isinstance(geometry_data, dict):
            requested = QRect(
                int(geometry_data.get("x", 0)),
                int(geometry_data.get("y", 0)),
                int(geometry_data.get("width", 720)),
                int(geometry_data.get("height", 480)),
            )
        else:
            offset = 28 * (default_index % 8)
            requested = QRect(18 + offset, 18 + offset, 720, 480)
        return requested

    def _clamp_geometry(self, requested: QRect) -> QRect:
        viewport_size = self.mdi.viewport().size()
        available_width = max(1, viewport_size.width())
        available_height = max(1, viewport_size.height())

        minimum_width = min(500, available_width)
        minimum_height = min(450, available_height)
        width = min(max(requested.width(), minimum_width), available_width)
        height = min(max(requested.height(), minimum_height), available_height)
        x = min(max(requested.x(), 0), max(0, available_width - width))
        y = min(max(requested.y(), 0), max(0, available_height - height))
        return QRect(x, y, width, height)

    def _reclamp_all_windows(self, *, persist: bool) -> None:
        """Clamp restored WSP geometry to the final QMdiArea viewport."""
        if not self._subwindows or not self._restore_geometries:
            return

        was_restoring = self._restoring
        self._restoring = True
        try:
            for workspace_uid, subwindow in self._subwindows.items():
                requested = self._restore_geometries.get(workspace_uid)
                if requested is None:
                    requested = subwindow.geometry()

                window_state = self._restore_window_states.get(
                    workspace_uid,
                    "NORMAL",
                )
                subwindow.restore_workspace_normal()
                subwindow.apply_system_geometry(self._clamp_geometry(requested))
                if window_state == "MINIMIZED":
                    subwindow.showMinimized()
                elif window_state == "MAXIMIZED":
                    subwindow.show_workspace_maximized()

            active_subwindow = self._subwindows.get(
                self._restore_active_workspace_uid or ""
            )
            if active_subwindow is not None:
                self.mdi.setActiveSubWindow(active_subwindow)
        finally:
            self._restoring = was_restoring

        if persist:
            self._schedule_all_ui_state_save()

    def _finish_session_layout_restore(self) -> None:
        """Run the final post-show geometry pass and persist its result."""
        self._reclamp_all_windows(persist=True)
        self._restore_geometries.clear()
        self._restore_window_states.clear()
        self._restore_active_workspace_uid = None

    def _refresh_workspace_account_balance(self, workspace_uid: str) -> None:
        window = self._windows.get(workspace_uid)
        if window is None:
            return
        broker, account_id, data_mode = window.account_binding()
        if data_mode == WORKSPACE_DATA_MODE_REPLAY:
            runtime = self.controller.workspace_runtime(workspace_uid)
            initial_balance = None
            realized_profit = 0.0
            equity = None
            if runtime is not None:
                context = runtime.context
                initial_balance = context.replay_initial_balance
                realized_profit = context.daily_realized_pnl or 0.0
                equity = context.risk_equity
            balance = (
                initial_balance + realized_profit
                if initial_balance is not None
                else None
            )
            if equity is None:
                equity = balance
            window.set_replay_financial_snapshot(
                initial_balance=initial_balance,
                balance=balance,
                equity=equity,
            )
            return
        if data_mode != WORKSPACE_DATA_MODE_BROKER or not account_id:
            window.set_account_balance(None)
            return
        option = self._catalog.find_account(broker, account_id)
        if option is None:
            window.set_account_balance(None)
            return
        window.set_account_identity(
            option.display_name,
            option.account_mode,
            preserve_public_name=True,
        )
        window.set_account_balance(option.balance, option.currency)

    def _update_empty_state(self) -> None:
        target_page = self.ui.pageMdi if self._subwindows else self.ui.pageEmpty
        self.stack_workspace_state.setCurrentWidget(target_page)

    def _tr(self, key: str, fallback: str) -> str:
        if self._lang_mgr is None:
            return fallback

        return self._lang_mgr.tr(key, fallback)

    def _translated_code(
        self,
        value: str,
        labels: dict[str, tuple[str, str]],
    ) -> str:
        key, fallback = labels.get(value, ("", value))
        return self._tr(key, fallback) if key else fallback

    def _tile_workspaces_equal_grid(self) -> None:
        """Arrange visible WSP windows in a strict equal-sized grid.

        Unlike ``QMdiArea.tileSubWindows()``, geometry does not depend on
        title length or different child-window minimum size hints.
        """
        subwindows = [
            subwindow
            for subwindow in self.ui.mdiWorkspaces.subWindowList()
            if subwindow.isVisible()
        ]
        if not subwindows:
            return

        for subwindow in subwindows:
            subwindow.restore_workspace_normal()
            subwindow.set_workspace_tiled(True)

        mdi = self.ui.mdiWorkspaces
        horizontal_policy = mdi.horizontalScrollBarPolicy()
        vertical_policy = mdi.verticalScrollBarPolicy()
        mdi.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        mdi.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        viewport_rect = mdi.viewport().rect()
        workspace_count = len(subwindows)

        columns = math.ceil(math.sqrt(workspace_count))
        rows = math.ceil(workspace_count / columns)

        gap = 2
        available_height = viewport_rect.height() - gap * (rows - 1)
        cell_height = max(1, available_height // rows)

        for row in range(rows):
            first_index = row * columns
            last_index = first_index + columns
            row_windows = subwindows[first_index:last_index]
            if not row_windows:
                continue

            row_count = len(row_windows)
            available_width = viewport_rect.width() - gap * (row_count - 1)
            cell_width = max(1, available_width // row_count)

            y = row * (cell_height + gap)

            for column, subwindow in enumerate(row_windows):
                x = column * (cell_width + gap)

                width = cell_width
                if column == row_count - 1:
                    width = viewport_rect.width() - x

                height = cell_height
                if row == rows - 1:
                    height = viewport_rect.height() - y

                subwindow.setGeometry(
                    x,
                    y,
                    width,
                    height,
                )

        mdi.setHorizontalScrollBarPolicy(horizontal_policy)
        mdi.setVerticalScrollBarPolicy(vertical_policy)

    def _cascade_workspaces_in_viewport(self) -> None:
        """Зберегти Qt cascade offsets і вмістити normalized frames у viewport."""
        mdi = self.ui.mdiWorkspaces
        subwindows = [
            subwindow
            for subwindow in mdi.subWindowList()
            if subwindow.isVisible()
        ]
        if not subwindows:
            return

        horizontal_policy = mdi.horizontalScrollBarPolicy()
        vertical_policy = mdi.verticalScrollBarPolicy()
        mdi.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        mdi.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        try:
            mdi.cascadeSubWindows()
            viewport_rect = mdi.viewport().rect()
            max_x_offset = max(
                subwindow.geometry().x() - viewport_rect.x()
                for subwindow in subwindows
            )
            max_y_offset = max(
                subwindow.geometry().y() - viewport_rect.y()
                for subwindow in subwindows
            )
            maximum_width = max(1, viewport_rect.width() - max_x_offset)
            maximum_height = max(1, viewport_rect.height() - max_y_offset)
            minimum_width = max(subwindow.minimumWidth() for subwindow in subwindows)
            minimum_height = max(
                subwindow.minimumHeight() for subwindow in subwindows
            )
            workspace_count = len(subwindows)
            frame_width = self._cascade_preferred_extent(
                maximum_width,
                minimum_width,
                workspace_count,
            )
            frame_height = self._cascade_preferred_extent(
                maximum_height,
                minimum_height,
                workspace_count,
            )

            for subwindow in subwindows:
                geometry = subwindow.geometry()
                subwindow.setGeometry(
                    geometry.x(),
                    geometry.y(),
                    frame_width,
                    frame_height,
                )
        finally:
            mdi.setHorizontalScrollBarPolicy(horizontal_policy)
            mdi.setVerticalScrollBarPolicy(vertical_policy)

    @staticmethod
    def _cascade_preferred_extent(
        maximum_extent: int,
        minimum_extent: int,
        workspace_count: int,
    ) -> int:
        """Зарезервувати одну WSP-частку простору між minimum і max-fit."""
        if maximum_extent <= minimum_extent:
            return maximum_extent
        adjustable_extent = maximum_extent - minimum_extent
        reserve = math.ceil(adjustable_extent / max(1, workspace_count))
        return max(minimum_extent, maximum_extent - reserve)

    @staticmethod
    def _apply_subwindow_title(
        subwindow: QMdiSubWindow,
        display_name: str,
    ) -> None:
        """Apply a bounded title without a tooltip over the full WSP surface."""
        full_title = str(display_name or "").strip()

        visible_title = subwindow.fontMetrics().elidedText(
            full_title,
            Qt.TextElideMode.ElideRight,
            320,
        )

        subwindow.setWindowTitle(visible_title)
        subwindow.setToolTip("")
