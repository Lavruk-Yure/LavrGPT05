# main_logic.py
# -*- coding: utf-8 -*-
"""
core/main_logic.py — головне робоче вікно LGE.

Функції:
- ліва панель навігації (Моніторинг / Ордери / Налаштування / Про програму) +
    Вихід внизу
- центральна область зі сторінками (поки плейсхолдери)
- toolbar (ті самі дії)
- statusBar:
    - зліва: назва активної сторінки
    - справа: LGE vX.Y.Z | ліцензія | Full | Orders (кольори)
- UITranslator + глобальний LANG

Patch: statusbar segments + license summary (RoadMap20)
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QEvent, QRect, Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core import session_state
from core.about_dialog import AboutDialog
from core.algorithm_workspace_area import AlgorithmWorkspaceArea
from core.app_paths import ROOT_CONF_PATH
from core.config_manager import ConfigManager
from core.lang_manager import LANG
from core.license_manager import LicenseManager
from core.license_status import (
    LicenseStatus,
    get_trial_days,
    get_trial_days_left,
    should_show_trial_warning,
)
from core.orders_page import OrdersPage
from core.session_repository import SessionRepository, SessionRepositoryError
from core.settings_center import SettingsCenter
from core.ui_translator import UITranslator
from engine.market_availability_state import MARKET_CLOSED
from engine.runtime_constants import RUNTIME_ACCOUNT_REFRESH_INTERVAL_SECONDS
from engine.runtime_engine import RuntimeEngine
from engine.runtime_state import RuntimeState
from engine.services.ctrader_runtime_service import CTraderRuntimeService
from engine.services.ib_runtime_service import IBRuntimeService
from ui.ui_main_app import Ui_MainAppWindow

DEBUG_MAIN = False

BROKER_COL_WIDTH = 12
STATE_COL_WIDTH = 14
ACCOUNT_COL_WIDTH = 12
BALANCE_COL_WIDTH = 20

logger = logging.getLogger(__name__)


def log_cp(name: str, **kw: Any) -> None:
    """Локальний debug-логер модуля."""
    if not DEBUG_MAIN:
        return
    msg = f"[MAIN:{name}] " + ", ".join(f"{k}={v!r}" for k, v in kw.items())
    print(msg)


class MainAppWindow(QMainWindow):
    """Основне вікно LGE."""

    def __init__(self) -> None:
        super().__init__()

        # --- UI ---
        self.ui = Ui_MainAppWindow()
        self.ui.setupUi(self)

        self._session_repository = SessionRepository()
        self._restoring_main_window = True
        self._workspace_restore_scheduled = False
        self._saved_main_window_state = "NORMAL"
        self._workspace_restore_attempts = 0
        self._workspace_restore_stable_passes = 0
        self._workspace_restore_last_size: tuple[int, int] | None = None
        self._closing_main_window = False
        self._shutdown_in_progress = False
        self._shutdown_complete = False
        self._main_window_save_timer = QTimer(self)
        self._main_window_save_timer.setSingleShot(True)
        self._main_window_save_timer.setInterval(250)
        self._main_window_save_timer.timeout.connect(self._save_main_window_state)
        self._apply_saved_main_window_state()

        self.ui.lblMarketState.setVisible(False)

        self.conf_mgr = ConfigManager

        # --- Lang / Translator ---
        self._lang_mgr = LANG
        self._ui_translator = UITranslator(self._lang_mgr)

        # --- Layout ---
        main_layout = QHBoxLayout(self.ui.contentArea)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # =========================================================
        # Технічні прапорці
        # =========================================================
        self._trial_warning_last_key: str | None = None
        self._trial_expired_notified: bool = False
        self._trial_watch_timer: QTimer | None = None
        self._market_state_timer: QTimer | None = None
        self._last_account_refresh_monotonic = 0.0

        # =========================================================
        # LEFT PANEL
        # =========================================================
        self.left_panel = QFrame(self.ui.contentArea)
        self.left_panel.setFixedWidth(180)
        self.left_panel.setStyleSheet(
            "background-color: #2C7A8C; border-right: 1px solid #173A47;"
        )

        v_left = QVBoxLayout(self.left_panel)
        v_left.setContentsMargins(10, 10, 10, 10)
        v_left.setSpacing(10)

        # Title
        self.lbl_title_left = QLabel("[MainAppWindow.lblTitleLeft]")
        self.lbl_title_left.setObjectName("lblTitleLeft")
        self.lbl_title_left.setStyleSheet("color:white; font:bold 13pt 'Segoe UI';")
        v_left.addWidget(self.lbl_title_left)

        # Buttons
        self.btn_monitoring = QToolButton()
        self.btn_monitoring.setObjectName("btnMonitoring")
        self.btn_monitoring.setText("[MainAppWindow.btnMonitoring]")

        self.btn_orders = QToolButton()
        self.btn_orders.setObjectName("btnOrders")
        self.btn_orders.setText("[MainAppWindow.btnOrders]")

        self.btn_settings = QToolButton()
        self.btn_settings.setObjectName("btnSettings")
        self.btn_settings.setText("[MainAppWindow.btnSettings]")

        self.btn_about = QToolButton()
        self.btn_about.setObjectName("btnAbout")
        self.btn_about.setText("[MainAppWindow.btnAbout]")

        nav_style = (
            "QToolButton {background-color:#227685; color:white;"
            "border-radius:6px; padding:6px;} "
            "QToolButton:hover {background-color:#1E5FD0;}"
        )

        for b in (
            self.btn_monitoring,
            self.btn_orders,
            self.btn_settings,
            self.btn_about,
        ):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(nav_style)
            v_left.addWidget(b)

        v_left.addStretch()

        # Exit — внизу
        self.btn_exit = QToolButton()
        self.btn_exit.setObjectName("btnExit")
        self.btn_exit.setText("[MainAppWindow.btnExit]")
        self.btn_exit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_exit.setStyleSheet(
            "QToolButton {background-color:#2d3b42; color:white;"
            "border-radius:6px; padding:6px;} "
            "QToolButton:hover {background-color:#b00020;}"
        )
        v_left.addWidget(self.btn_exit)

        # =========================================================
        # CENTRAL STACK
        # =========================================================
        self.stacked = QStackedWidget(self.ui.contentArea)

        self.page_monitoring = AlgorithmWorkspaceArea(
            lang_mgr=self._lang_mgr,
        )
        self.page_monitoring.setObjectName("pageMonitoring")

        self.page_orders = OrdersPage(
            lang_mgr=self._lang_mgr,
        )
        self.page_orders.setObjectName("pageOrders")

        self.page_orders.close_requested.connect(
            lambda: self._switch_page(self.page_monitoring)
        )
        self.page_monitoring.external_exposure_resolution_requested.connect(
            self._on_external_exposure_resolution_requested
        )

        self.page_settings_placeholder = QLabel("[MainAppWindow.pageSettings]")
        self.page_settings_placeholder.setObjectName("pageSettings")
        self.page_settings_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.stacked.addWidget(self.page_monitoring)
        self.stacked.addWidget(self.page_orders)
        self.stacked.addWidget(self.page_settings_placeholder)

        main_layout.addWidget(self.left_panel)
        main_layout.addWidget(self.stacked)

        # =========================================================
        # TOOLBAR (QToolBar)
        # =========================================================
        tb = self.ui.toolBarMain
        tb.clear()

        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)

        tb.setStyleSheet(
            """
QToolBar {
    background-color: #173A47;
    border: none;
    spacing: 6px;
    padding: 4px;
}
QToolButton {
    background: transparent;
    color: white;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 6px 10px;
}
QToolButton:hover {
    background-color: #1E5FD0;
    border-color: #1E5FD0;
}
QToolButton:pressed {
    background-color: #164aa3;
}
QToolBar::separator {
    background-color: #0f2a34;
    width: 1px;
    margin: 2px 6px;
}
QToolButton#tbExit:hover {
    background-color: #b00020;
    border-color: #b00020;
}
QToolButton#tbExit:pressed {
    background-color: #7a0016;
}
"""
        )

        self.action_monitor = tb.addAction("[MainAppWindow.actionMonitoring]")
        self.action_monitor.setObjectName("actionMonitoring")

        self.action_orders = tb.addAction("[MainAppWindow.actionOrders]")
        self.action_orders.setObjectName("actionOrders")

        self.action_settings = tb.addAction("[MainAppWindow.actionSettings]")
        self.action_settings.setObjectName("actionSettings")

        self.action_about = tb.addAction("[MainAppWindow.actionAbout]")
        self.action_about.setObjectName("actionAbout")

        tb.addSeparator()

        self.action_exit = tb.addAction("[MainAppWindow.actionExit]")
        self.action_exit.setObjectName("actionExit")

        exit_btn = tb.widgetForAction(self.action_exit)
        if exit_btn is not None:
            exit_btn.setObjectName("tbExit")

        # =========================================================
        # Connections
        # =========================================================
        self.btn_monitoring.clicked.connect(
            lambda: self._switch_page(self.page_monitoring)
        )
        self.btn_orders.clicked.connect(lambda: self._switch_page(self.page_orders))
        self.btn_settings.clicked.connect(self._open_settings_dialog)
        self.btn_about.clicked.connect(self._open_about_dialog)
        self.btn_exit.clicked.connect(self.request_application_exit)

        self.action_monitor.triggered.connect(
            lambda: self._switch_page(self.page_monitoring)
        )
        self.action_orders.triggered.connect(
            lambda: self._switch_page(self.page_orders)
        )
        self.action_settings.triggered.connect(self._open_settings_dialog)
        self.action_about.triggered.connect(self._open_about_dialog)
        self.action_exit.triggered.connect(self.request_application_exit)
        self._last_broker_states: dict[str, str] = {}

        # =========================================================
        # APPLY TRANSLATION (початковий)
        # =========================================================
        self._ui_translator.apply(self)
        log_cp("init_done", lang=self._lang_mgr.current_language)

        try:
            conf = ConfigManager(ROOT_CONF_PATH).load(session_state.CURRENT_PASSWORD)
            if isinstance(conf, dict):
                LicenseManager.compute_and_update(
                    conf,
                    app_version=conf.get("version"),
                )
                ConfigManager(ROOT_CONF_PATH).save(
                    conf,
                    session_state.CURRENT_PASSWORD,
                )
        except Exception:  # noqa
            pass

        self._init_runtime_engine()

        self._startup_auto_connect()

        self._init_statusbar()
        self._update_statusbar()
        self._init_trial_watch_timer()
        self._init_broker_health_timer()
        self._init_market_state_timer()

        self._switch_page(self.page_monitoring)

    # ------------------------------------------------------------------
    def _init_runtime_engine(self) -> None:
        """
        Створити єдиний RuntimeEngine для GUI-сесії LGE.

        RoadMap78/RoadMap82:
        - MainAppWindow є власником RuntimeEngine;
        - діалоги IB/cTrader беруть готовий shared engine;
        - RuntimeEngine сам визначає canonical runtime DB path;
        - OrdersPage працює через цей самий RuntimeEngine.
        """
        runtime_engine = getattr(session_state, "CURRENT_RUNTIME_ENGINE", None)

        if runtime_engine is None:
            runtime_engine = RuntimeEngine()
            session_state.CURRENT_RUNTIME_ENGINE = runtime_engine
            logger.info("RuntimeEngine created for MainAppWindow.")

        self.runtime_engine = runtime_engine

        if hasattr(self, "page_orders"):
            self.page_orders.set_runtime_engine(runtime_engine)

        if hasattr(self, "page_monitoring"):
            self.page_monitoring.set_runtime_engine(runtime_engine)

        if runtime_engine.ib_runtime_service is None:
            runtime_engine.set_ib_runtime_service(IBRuntimeService())

        if runtime_engine.ctrader_runtime_service is None:
            runtime_engine.set_ctrader_runtime_service(CTraderRuntimeService())

        if runtime_engine.context.runtime_state == RuntimeState.OFF:
            runtime_engine.startup()

    # ------------------------------------------------------------------
    def _startup_auto_connect(self) -> None:
        """
        Startup AutoConnect за намірами з LGE.conf.

        Важливо:
        - auto_connect у conf є наміром користувача;
        - помилки підключення НЕ переписують conf;
        - підключення йде тільки через shared RuntimeEngine.
        """
        conf_obj = getattr(session_state, "CURRENT_CONFIG", None)
        runtime_engine = getattr(session_state, "CURRENT_RUNTIME_ENGINE", None)

        if conf_obj is None or runtime_engine is None:
            logger.warning("Startup AutoConnect skipped: config/runtime unavailable.")
            return

        conf = conf_obj.to_dict()
        engine_conf = conf.get("engine", {}) or {}
        auto_connect = engine_conf.get("auto_connect", {}) or {}

        auto_ib = bool(auto_connect.get("ib", False))
        auto_ctrader = bool(auto_connect.get("ctrader", False))

        logger.info(
            "Startup AutoConnect requested: ib=%s ctrader=%s",
            auto_ib,
            auto_ctrader,
        )

        if auto_ib:
            self._startup_connect_ib(runtime_engine)

        if auto_ctrader:
            self._startup_connect_ctrader(runtime_engine)

    # ------------------------------------------------------------------
    @staticmethod
    def _startup_connect_ib(
        runtime_engine: RuntimeEngine,
    ) -> None:
        """
        Startup AutoConnect для IB.

        Конфіг не переписуємо при помилках.
        """
        try:
            ok = runtime_engine.connect_ib_demo()

            if ok:
                logger.info("Startup AutoConnect IB: connected.")
            else:
                logger.warning("Startup AutoConnect IB: connection failed.")
                runtime_engine.start_ib_reconnect_watch()

        except Exception:  # noqa
            logger.warning("Startup AutoConnect IB: connection failed.")
            runtime_engine.start_ib_reconnect_watch()

    # ------------------------------------------------------------------
    @staticmethod
    def _startup_connect_ctrader(
        runtime_engine: RuntimeEngine,
    ) -> None:
        """
        Startup AutoConnect для cTrader.

        Конфіг не переписуємо при помилках.
        """
        try:
            ready = runtime_engine.prepare_ctrader_startup_connection(
                account_mode="DEMO",
            )
            if not ready:
                logger.warning("Startup AutoConnect cTrader: readiness timeout.")
                runtime_engine.start_ctrader_reconnect_watch()
                return

            ok = runtime_engine.connect_ctrader_demo()

            if ok:
                logger.info("Startup AutoConnect cTrader: connected.")
            else:
                logger.warning("Startup AutoConnect cTrader: connection failed.")
                runtime_engine.start_ctrader_reconnect_watch()

        except Exception:  # noqa
            logger.exception("Startup AutoConnect cTrader failed.")
            runtime_engine.start_ctrader_reconnect_watch()

    def _on_external_exposure_resolution_requested(
        self,
        workspace_display_name: str,
        account_id: str,
        symbol_name: str,
    ) -> None:
        """Route a WSP safety hold to the read-only Orders recovery view."""
        runtime_engine = self.runtime_engine
        if runtime_engine is not None:
            try:
                runtime_engine.unlock_active_broker()
                runtime_engine.set_active_broker("IB")
            except (RuntimeError, ValueError):
                logger.exception(
                    "Could not activate IB for external exposure recovery."
                )
        self._switch_page(self.page_orders)
        self.page_orders.prepare_external_exposure_resolution(
            account_id=account_id,
            symbol_name=symbol_name,
            refresh=False,
        )
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.warning(
            self,
            self._lang_mgr.tr(
                "AlgorithmWorkspaceArea.externalExposureDetectedTitle",
                "External IB FX exposure",
            ),
            self._lang_mgr.tr(
                "AlgorithmWorkspaceArea.externalExposureDetectedMessage",
                "LGE EXCLUSIVE placed workspace {workspace} on SAFETY HOLD "
                "for {symbol}. The Orders page was opened automatically. "
                "Select the external exposure row and click Resolve "
                "reconciliation to see the exact TWS order identifiers. "
                "After resolving the position or orphaned protection in TWS, "
                "press Refresh. Go to Monitoring to inspect the WSP and its "
                "journal.",
            ).format(
                workspace=workspace_display_name,
                symbol=symbol_name,
            ),
        )
        self.page_orders.prepare_external_exposure_resolution(
            account_id=account_id,
            symbol_name=symbol_name,
            refresh=True,
        )

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    def _switch_page(self, page_widget: QWidget) -> None:
        """Перемикає сторінку в центральному StackedWidget."""

        runtime_engine = self.runtime_engine

        if runtime_engine is not None:
            if page_widget is self.page_orders:
                runtime_engine.lock_active_broker()
            else:
                runtime_engine.unlock_active_broker()

        if hasattr(self, "_sb_brokers"):
            self._sb_brokers.setEnabled(page_widget is not self.page_orders)

        self.stacked.setCurrentWidget(page_widget)

        if page_widget is self.page_orders:
            self.page_orders.activate_page()

        title = ""
        if hasattr(page_widget, "text"):
            try:
                text = page_widget.text()
                title = text.replace("(TODO)", "").strip()
            except Exception:  # noqa
                title = ""

        self.ui.statusBarMain.showMessage(title or " ")
        self._update_statusbar()

        log_cp("switch", title=title)

    # ------------------------------------------------------------------
    def apply_translation(self) -> None:
        """Повторно застосувати переклад до цього вікна."""
        self._ui_translator.apply(self)
        self.page_monitoring.apply_translation()
        self.page_orders.apply_translation()
        self._update_statusbar()
        self._update_market_state_banner()

        cur = self.stacked.currentWidget()
        if cur is not None:
            self._switch_page(cur)

        log_cp("retranslated", lang=self._lang_mgr.current_language)

    # ------------------------------------------------------------------
    def _open_settings_dialog(self) -> None:
        """Відкрити діалог налаштувань."""
        dlg = SettingsCenter(self)
        dlg.exec()
        self._update_statusbar()

    def _open_about_dialog(self) -> None:
        """Відкрити діалог 'Про програму'."""
        dlg = AboutDialog(self)
        dlg.exec()

    # =========================================================
    # TRIAL WATCH TIMER
    # =========================================================
    def _init_trial_watch_timer(self) -> None:
        """Періодична перевірка trial при довгій роботі програми."""
        self._trial_watch_timer = QTimer(self)
        self._trial_watch_timer.setInterval(60_000)  # 1 хвилина
        self._trial_watch_timer.timeout.connect(self._on_trial_watch_timer)
        self._trial_watch_timer.start()

    def _on_trial_watch_timer(self) -> None:
        """
        Раз на хвилину:
        - перечитати conf з диска
        - перерахувати license status
        - зберегти назад
        - оновити session_state
        - оновити statusbar / warning
        """
        try:
            if not session_state.CURRENT_PASSWORD:
                return

            mgr = ConfigManager(ROOT_CONF_PATH)
            conf = mgr.load(session_state.CURRENT_PASSWORD)
            if not isinstance(conf, dict):
                return

            LicenseManager.compute_and_update(
                conf,
                app_version=conf.get("version"),
            )
            mgr.save(conf, session_state.CURRENT_PASSWORD)

            if session_state.CURRENT_CONFIG is not None:
                session_state.CURRENT_CONFIG.to_dict().clear()
                session_state.CURRENT_CONFIG.to_dict().update(conf)

            self._update_statusbar()

        except Exception:  # noqa
            pass

    def _init_market_state_timer(self) -> None:
        """
        Запустити періодичне оновлення global market state banner.
        """
        self._market_state_timer = QTimer(self)
        self._market_state_timer.setInterval(60_000)
        self._market_state_timer.timeout.connect(self._update_market_state_banner)
        self._market_state_timer.start()

        QTimer.singleShot(
            0,
            self._update_market_state_banner,
        )

    def _update_market_state_banner(self) -> None:
        """
        Показати або приховати глобальне повідомлення про стан Forex.
        """
        runtime_engine = getattr(
            session_state,
            "CURRENT_RUNTIME_ENGINE",
            None,
        )

        if runtime_engine is None:
            self.ui.lblMarketState.setVisible(False)
            return

        broker = runtime_engine.get_active_broker()

        if broker not in {"CTRADER", "IB"}:
            self.ui.lblMarketState.setVisible(False)
            return

        try:
            result = runtime_engine.get_active_market_availability(
                symbol_name="EURUSD",
            )
        except Exception:  # noqa
            logger.exception("Global market availability check failed.")
            self.ui.lblMarketState.setVisible(False)
            return

        if result.state != MARKET_CLOSED:
            self.ui.lblMarketState.setVisible(False)
            return

        self.ui.lblMarketState.setText(
            self._lang_mgr.tr(
                "MainAppWindow.statusForexMarketClosed",
                "Forex market is closed. " "Market orders are unavailable.",
            )
        )
        self.ui.lblMarketState.setVisible(True)

    # =========================================================
    # STATUSBAR (right side)
    # =========================================================

    def _init_statusbar(self) -> None:
        sb = self.ui.statusBarMain
        sb.clearMessage()

        self._sb_app = QLabel("")
        self._sb_lic = QLabel("")
        self._sb_full = QLabel("")
        self._sb_orders = QLabel("")
        self._sb_brokers = QComboBox()
        font = QFont()
        font.setFamilies(["Consolas", "Courier New"])
        font.setPointSize(9)

        self._sb_brokers.setFont(font)

        self._sb_sep1 = QLabel(" | ")
        self._sb_sep2 = QLabel(" | ")
        self._sb_sep3 = QLabel(" | ")
        self._sb_sep4 = QLabel(" | ")

        self._sb_brokers.setObjectName("sbBrokers")
        self._sb_brokers.setFixedWidth(260)
        self._sb_brokers.view().setMinimumWidth(540)
        self._sb_brokers.view().setMaximumWidth(540)
        self._sb_brokers.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._sb_brokers.setToolTip(
            self._lang_mgr.tr("StatusBar.brokerRuntimeStatus", "Broker runtime status")
        )

        grey = "lightgray"
        for w in (
            self._sb_app,
            self._sb_sep1,
            self._sb_lic,
            self._sb_sep2,
            self._sb_full,
            self._sb_sep3,
            self._sb_orders,
            self._sb_sep4,
        ):
            w.setStyleSheet(f"color: {grey};")

        sb.addPermanentWidget(self._sb_app)
        sb.addPermanentWidget(self._sb_sep1)
        sb.addPermanentWidget(self._sb_lic)
        sb.addPermanentWidget(self._sb_sep2)
        sb.addPermanentWidget(self._sb_full)
        sb.addPermanentWidget(self._sb_sep3)
        sb.addPermanentWidget(self._sb_orders)
        sb.addPermanentWidget(self._sb_sep4)
        sb.addPermanentWidget(self._sb_brokers)

        self.ui.statusBarMain.setStyleSheet("QStatusBar::item { border: none; }")

        self._sb_runtime_alert = QLabel("")
        self._sb_runtime_alert.setMinimumWidth(220)
        self._sb_runtime_alert.setStyleSheet("color: orange;")
        self.statusBar().addPermanentWidget(self._sb_runtime_alert)
        self._sb_brokers.showPopup = self._show_brokers_popup

        self._sb_brokers.activated.connect(self._on_brokers_combo_activated)

    def _update_statusbar(self) -> None:
        """Оновити праву частину status bar відповідно до стану ліцензії."""
        app_version = "-"
        status_raw = "NO_LICENSE"

        lic: dict[str, Any] = {}

        if session_state.CURRENT_CONFIG is not None:
            conf = session_state.CURRENT_CONFIG.to_dict()
            if isinstance(conf, dict):
                app_version = str(conf.get("version") or "-")
                lic_obj = conf.get("license", {})
                if isinstance(lic_obj, dict):
                    lic = dict(lic_obj)
                    status_raw = str(lic.get("status") or "NO_LICENSE")

        text_status, text_full, full_value = self._statusbar_license_segments(lic)
        orders_text, order_mode_key = self._statusbar_orders_text()

        self._sb_app.setText(f"LGE v{app_version}")
        self._sb_lic.setText(text_status)
        self._sb_full.setText(text_full)
        self._sb_orders.setText(orders_text)

        self._update_brokers_statusbar()

        days_left_num = get_trial_days_left(lic) if lic else None
        self._apply_statusbar_colors(
            status=status_raw,
            days_left_num=days_left_num,
            days_left_text=full_value,
            order_mode_key=order_mode_key,
        )

        self._handle_trial_warning_if_needed(lic)

    def _statusbar_license_segments(self, lic: dict[str, Any]) -> tuple[str, str, str]:
        """Повернути перекладені сегменти ліцензії для status bar."""
        status_raw = str(lic.get("status") or "NO_LICENSE")
        edition = str(lic.get("edition") or "free").strip().lower()

        try:
            status = LicenseStatus(status_raw)
        except Exception:  # noqa
            status = LicenseStatus.NO_LICENSE

        full_label = self._lang_mgr.tr("StatusBar.fullLabel", "Full")
        days_short = self._lang_mgr.tr("StatusBar.daysShort", "d")
        infinity = self._lang_mgr.tr("StatusBar.infinity", "∞")

        trial_days = get_trial_days(lic)
        days_left = get_trial_days_left(lic)

        if status is LicenseStatus.NO_LICENSE:
            full_value = f"{trial_days}{days_short}"
            return (
                self._lang_mgr.tr("StatusBar.noLicense", "No license"),
                f"{full_label}: {full_value}",
                full_value,
            )

        if status is LicenseStatus.TRIAL_OK:
            full_value = "?" if days_left is None else f"{days_left}{days_short}"
            return (
                self._lang_mgr.tr("StatusBar.trialActive", "TRIAL active"),
                f"{full_label}: {full_value}",
                full_value,
            )

        if status is LicenseStatus.TRIAL_EXPIRED:
            full_value = f"0{days_short}"
            return (
                self._lang_mgr.tr("StatusBar.trialExpired", "TRIAL expired"),
                f"{full_label}: {full_value}",
                full_value,
            )

        if status is LicenseStatus.PRO_OK:
            if edition == "pro_plus":
                status_text = self._lang_mgr.tr(
                    "StatusBar.proPlusActive", "PRO+ active"
                )
            else:
                status_text = self._lang_mgr.tr("StatusBar.proActive", "PRO active")

            return status_text, f"{full_label}: {infinity}", infinity

        status_texts = {
            LicenseStatus.OTHER_MACHINE: (
                "StatusBar.otherMachine",
                "Other machine",
            ),
            LicenseStatus.EXPIRED: (
                "StatusBar.licenseExpired",
                "License expired",
            ),
            LicenseStatus.UPDATE_REQUIRED: (
                "StatusBar.updateRequired",
                "Update required",
            ),
            LicenseStatus.TAMPERED: (
                "StatusBar.tampered",
                "License tampered",
            ),
            LicenseStatus.CLOCK_ROLLBACK: (
                "StatusBar.clockProblem",
                "Clock problem",
            ),
        }

        key, fallback = status_texts.get(
            status,
            ("StatusBar.unknownLicense", "Unknown license"),
        )

        full_value = "?"
        return (
            self._lang_mgr.tr(key, fallback),
            f"{full_label}: {full_value}",
            full_value,
        )

    def _handle_trial_warning_if_needed(self, lic: dict) -> None:
        """
        Показати warning про близьке завершення trial без дублювання і спаму.

        Правило:
        - warning показуємо лише для TRIAL_OK
        - не більше одного разу на поточну дату для одного days_left
        - після завершення trial окремо один раз показуємо повідомлення
        """
        if not isinstance(lic, dict):
            return

        now = datetime.now(UTC)
        status_raw = str(lic.get("status") or "NO_LICENSE")

        try:
            status = LicenseStatus(status_raw)
        except Exception:  # noqa
            status = LicenseStatus.NO_LICENSE

        if status is LicenseStatus.TRIAL_OK:
            self._trial_expired_notified = False

            if not should_show_trial_warning(lic, now):
                return

            days_left = get_trial_days_left(lic, now)
            if days_left is None or days_left <= 0:
                return

            today_key = f"{now.date().isoformat()}::{days_left}"
            if self._trial_warning_last_key == today_key:
                return

            self._trial_warning_last_key = today_key
            QTimer.singleShot(150, lambda: self._show_trial_warning_dialog(days_left))
            return

        if status is LicenseStatus.TRIAL_EXPIRED:
            if self._trial_expired_notified:
                return

            self._trial_expired_notified = True
            QTimer.singleShot(150, self._show_trial_expired_dialog)

    def _show_trial_expired_dialog(self) -> None:
        """Одноразове повідомлення про завершення trial."""
        from PySide6.QtWidgets import QMessageBox

        title = "Trial завершено"
        text = (
            "Пробний період завершився.\n\n"
            "Повний режим більше недоступний.\n"
            "Ордери переведено в ручний режим."
        )

        QMessageBox.warning(self, title, text)

    def _show_trial_warning_dialog(self, days_left: int) -> None:
        """Попередження про швидке завершення trial."""
        from PySide6.QtWidgets import QMessageBox

        title = "Попередження"

        if days_left == 1:
            text = "До кінця Trial залишилось 1 день!"
        else:
            text = f"До кінця Trial залишилось {days_left} днів!"

        QMessageBox.information(self, title, text)

    def update_statusbar(self) -> None:
        self._update_statusbar()

    def _statusbar_orders_text(self) -> tuple[str, str]:
        """
        Повертає текст режиму ордерів для status bar.

        Джерело істини:
        LGE.conf -> engine.execution_mode

        OFF    -> Orders: OFF
        MANUAL -> Orders: MANUAL
        SEMI   -> Orders: SEMI
        AUTO   -> Orders: AUTO
        """
        execution_mode = "OFF"

        if session_state.CURRENT_CONFIG is not None:
            conf = session_state.CURRENT_CONFIG.to_dict()
            if isinstance(conf, dict):
                engine = conf.get("engine", {})
                if isinstance(engine, dict):
                    execution_mode = (
                        str(engine.get("execution_mode") or "OFF").strip().upper()
                    )

        if execution_mode not in ("OFF", "MANUAL", "SEMI", "AUTO"):
            execution_mode = "OFF"

        orders_label = self._lang_mgr.tr("StatusBar.ordersLabel", "Orders")

        mode_map = {
            "OFF": ("StatusBar.orderModeOff", "OFF"),
            "MANUAL": ("StatusBar.orderModeManual", "MANUAL"),
            "SEMI": ("StatusBar.orderModeSemi", "SEMI"),
            "AUTO": ("StatusBar.orderModeAuto", "AUTO"),
        }

        mode_key, mode_fallback = mode_map[execution_mode]
        mode_text = self._lang_mgr.tr(mode_key, mode_fallback)

        return f"{orders_label}: {mode_text}", mode_key

    def _statusbar_license_text(self, status: str, edition: str) -> str:
        """Повернути короткий перекладений текст ліцензії для сумісності."""
        lic: dict[str, Any] = {}

        if session_state.CURRENT_CONFIG is not None:
            conf = session_state.CURRENT_CONFIG.to_dict()
            if isinstance(conf, dict):
                lic_obj = conf.get("license", {})
                if isinstance(lic_obj, dict):
                    lic = dict(lic_obj)

        lic["status"] = status
        lic["edition"] = edition

        text_status, text_full, _full_value = self._statusbar_license_segments(lic)
        return f"{text_status} | {text_full}"

    def _apply_statusbar_colors(
        self,
        *,
        status: str,
        days_left_num: int | None,
        days_left_text: str,
        order_mode_key: str,
    ) -> None:
        self._sb_app.setStyleSheet("color: lightgray;")
        self._sb_lic.setStyleSheet("color: lightgray;")
        self._sb_full.setStyleSheet("color: lightgray;")
        self._sb_orders.setStyleSheet("color: orange;")

        if status in ("UPDATE_REQUIRED", "OTHER_MACHINE", "TAMPERED", "EXPIRED"):
            self._sb_lic.setStyleSheet("color: salmon;")
        elif status in ("PRO_OK", "TRIAL_OK"):
            self._sb_lic.setStyleSheet("color: lightgreen;")

        inf = self._lang_mgr.tr("StatusBar.infinity", "∞")
        if days_left_text == inf:
            self._sb_full.setStyleSheet("color: lightgreen;")
        elif days_left_num is not None:
            self._sb_full.setStyleSheet(
                "color: lightgreen;" if days_left_num > 0 else "color: salmon;"
            )
        else:
            self._sb_full.setStyleSheet("color: lightgray;")

        if order_mode_key == "StatusBar.orderModeAuto":
            self._sb_orders.setStyleSheet("color: lightgreen;")
        elif order_mode_key == "StatusBar.orderModeSemi":
            self._sb_orders.setStyleSheet("color: khaki;")
        elif order_mode_key == "StatusBar.orderModeManual":
            self._sb_orders.setStyleSheet("color: orange;")
        else:
            self._sb_orders.setStyleSheet("color: lightgray;")

    def showEvent(self, event) -> None:
        """Finish Session restore only after the main Qt layout is ready."""
        super().showEvent(event)
        if self._workspace_restore_scheduled:
            return
        self._workspace_restore_scheduled = True
        QTimer.singleShot(0, self._prepare_workspace_restore_after_show)

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self._schedule_main_window_state_save()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._schedule_main_window_state_save()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._schedule_main_window_state_save()

    def _apply_saved_main_window_state(self) -> None:
        try:
            manifest = self._session_repository.load_manifest()
        except SessionRepositoryError:
            logger.exception("Cannot load main window Session state.")
            return

        state = manifest.get("main_window")
        if not isinstance(state, dict):
            return

        geometry = state.get("geometry")
        if isinstance(geometry, dict):
            requested = QRect(
                int(geometry.get("x", 0)),
                int(geometry.get("y", 0)),
                int(geometry.get("width", self.width())),
                int(geometry.get("height", self.height())),
            )
            self.setGeometry(self._clamp_main_window_geometry(requested))

        self._saved_main_window_state = str(
            state.get("window_state") or "NORMAL"
        ).upper()
        if self._saved_main_window_state == "MAXIMIZED":
            self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)

    def _clamp_main_window_geometry(self, requested: QRect) -> QRect:
        screen = QApplication.screenAt(requested.center())
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is None:
            return requested

        available = screen.availableGeometry()
        minimum_width = min(max(self.minimumWidth(), 640), available.width())
        minimum_height = min(max(self.minimumHeight(), 480), available.height())
        width = min(max(requested.width(), minimum_width), available.width())
        height = min(max(requested.height(), minimum_height), available.height())
        x = min(
            max(requested.x(), available.left()),
            available.right() - width + 1,
        )
        y = min(
            max(requested.y(), available.top()),
            available.bottom() - height + 1,
        )
        return QRect(x, y, width, height)

    def _prepare_workspace_restore_after_show(self) -> None:
        """Apply the saved main state before waiting for a stable MDI size."""
        if self._saved_main_window_state == "MAXIMIZED" and not self.isMaximized():
            self.showMaximized()
        QTimer.singleShot(50, self._wait_for_stable_workspace_layout)

    def _wait_for_stable_workspace_layout(self) -> None:
        """Wait until maximize/layout resize events stop changing the MDI."""
        self._workspace_restore_attempts += 1

        if (
            self._saved_main_window_state == "MAXIMIZED"
            and not self.isMaximized()
            and self._workspace_restore_attempts < 20
        ):
            self.showMaximized()
            QTimer.singleShot(50, self._wait_for_stable_workspace_layout)
            return

        if not hasattr(self, "page_monitoring"):
            QTimer.singleShot(50, self._wait_for_stable_workspace_layout)
            return

        viewport_size = self.page_monitoring.mdi.viewport().size()
        current_size = (viewport_size.width(), viewport_size.height())
        if current_size == self._workspace_restore_last_size:
            self._workspace_restore_stable_passes += 1
        else:
            self._workspace_restore_last_size = current_size
            self._workspace_restore_stable_passes = 0

        size_is_valid = current_size[0] > 0 and current_size[1] > 0
        layout_is_stable = self._workspace_restore_stable_passes >= 2
        attempts_exhausted = self._workspace_restore_attempts >= 20
        if size_is_valid and (layout_is_stable or attempts_exhausted):
            self._restore_workspaces_after_show()
            return

        QTimer.singleShot(50, self._wait_for_stable_workspace_layout)

    def _restore_workspaces_after_show(self) -> None:
        if hasattr(self, "page_monitoring"):
            self.page_monitoring.restore_from_session_after_layout()
        QTimer.singleShot(180, self._finish_main_window_restore)

    def _finish_main_window_restore(self) -> None:
        """Release normal persistence after the final WSP geometry pass."""
        self._restoring_main_window = False
        self._schedule_main_window_state_save()

    def _schedule_main_window_state_save(self) -> None:
        if self._restoring_main_window or self._closing_main_window:
            return
        self._main_window_save_timer.start()

    def _collect_main_window_state(self) -> dict[str, Any]:
        geometry = self.normalGeometry()
        if not geometry.isValid() or geometry.width() <= 0:
            geometry = self.geometry()
        return {
            "geometry": {
                "x": geometry.x(),
                "y": geometry.y(),
                "width": geometry.width(),
                "height": geometry.height(),
            },
            "window_state": "MAXIMIZED" if self.isMaximized() else "NORMAL",
        }

    def _save_main_window_state(self) -> None:
        try:
            self._session_repository.save_main_window_state(
                self._collect_main_window_state()
            )
        except SessionRepositoryError:
            logger.exception("Cannot save main window Session state.")

    def request_application_exit(self) -> None:
        """Route menu/button exit through the main-window close lifecycle."""
        self.close()

    def request_application_restart(self) -> None:
        """Restart LGE only after the shared controlled shutdown completes."""
        app = QApplication.instance()
        if not isinstance(app, QApplication):
            return
        app.setProperty("lge_restart_requested", True)
        self.close()
        app.quit()

    def shutdown_application(self) -> None:
        """Run one idempotent controlled shutdown for the whole LGE session."""
        if self._shutdown_complete or self._shutdown_in_progress:
            return

        self._shutdown_in_progress = True
        self._closing_main_window = True
        try:
            self._run_shutdown_step(
                "Main window timer shutdown failed.",
                self._stop_main_window_timers,
            )
            self._run_shutdown_step(
                "Secondary window shutdown failed.",
                self._close_secondary_windows,
            )

            if hasattr(self, "page_monitoring"):
                self._run_shutdown_step(
                    "Workspace shutdown failed.",
                    self.page_monitoring.shutdown_all_workspaces,
                )

            self._run_shutdown_step(
                "Main window state shutdown save failed.",
                self._save_main_window_state,
            )
            self._shutdown_runtime_engine()

            if hasattr(self, "page_orders"):
                self._run_shutdown_step(
                    "OrdersPage runtime detach failed.",
                    lambda: self.page_orders.set_runtime_engine(None),
                )

            self._shutdown_complete = True
        finally:
            self._shutdown_in_progress = False

    @staticmethod
    def _run_shutdown_step(
        failure_message: str,
        action: Callable[[], None],
    ) -> None:
        """Run one shutdown step without preventing later cleanup steps."""
        # Shutdown must continue even when an unexpected subsystem error occurs.
        # noinspection PyBroadException
        try:
            action()
        except Exception:
            logger.exception(failure_message)

    def _stop_main_window_timers(self) -> None:
        """Stop every periodic/deferred MainAppWindow timer."""
        for timer_name in (
            "_main_window_save_timer",
            "_trial_watch_timer",
            "_market_state_timer",
            "_broker_health_timer",
        ):
            timer = getattr(self, timer_name, None)
            if timer is not None:
                timer.stop()

    def _close_secondary_windows(self) -> None:
        """Close any dialog or auxiliary top-level window owned by LGE."""
        app = QApplication.instance()
        if not isinstance(app, QApplication):
            return

        for widget in tuple(app.topLevelWidgets()):
            if widget is self:
                continue
            widget.close()

    def shutdown_diagnostics(self) -> dict[str, bool]:
        """Return public shutdown state for diagnostics and regression tests."""
        timers = (
            self._main_window_save_timer,
            self._trial_watch_timer,
            self._market_state_timer,
            self._broker_health_timer,
        )
        return {
            "main_timers_stopped": all(not timer.isActive() for timer in timers),
            "shutdown_complete": self._shutdown_complete,
        }

    def closeEvent(self, event) -> None:
        """Close LGE through the shared controlled-shutdown path."""
        self.shutdown_application()
        super().closeEvent(event)

    @staticmethod
    def _shutdown_runtime_engine() -> None:
        """
        Коректно зупинити RuntimeEngine перед закриттям LGE.
        """
        runtime_engine = getattr(session_state, "CURRENT_RUNTIME_ENGINE", None)

        if runtime_engine is None:
            return

        try:
            runtime_engine.shutdown()
        except Exception:  # noqa
            logger.exception("RuntimeEngine shutdown failed.")
        finally:
            session_state.CURRENT_RUNTIME_ENGINE = None

    def _show_brokers_popup(self) -> None:
        """
        Оновити broker status combo перед відкриттям списку.
        """
        self._update_brokers_statusbar()
        QComboBox.showPopup(self._sb_brokers)

    def _on_brokers_combo_activated(self, index: int) -> None:
        """
        Вибрати активного broker зі StatusBar combo.

        Index 0 — summary row, не broker.
        """
        if index <= 0:
            return

        from core import session_state

        runtime_engine = getattr(session_state, "CURRENT_RUNTIME_ENGINE", None)

        if runtime_engine is None:
            return

        broker_name = self._sb_brokers.itemData(index)

        if not broker_name:
            return

        try:
            runtime_engine.set_active_broker(
                broker_name=str(broker_name),
                require_connected=True,
            )
        except Exception as exc:  # noqa
            self._sb_runtime_alert.setText(str(exc))
            self._update_brokers_statusbar()
            return

        self._sb_runtime_alert.setText("")
        self._update_brokers_statusbar()
        self._update_market_state_banner()

    def _update_brokers_statusbar(self) -> None:
        """
        Оновити combo стану runtime-брокерів у statusbar.
        """
        from core import session_state

        runtime_engine = getattr(session_state, "CURRENT_RUNTIME_ENGINE", None)

        broker_rows = []

        if runtime_engine is None:
            broker_rows.append(("IB", "OFF"))
            broker_rows.append(("cTrader", "OFF"))
        else:
            ib_state = self._runtime_broker_state(runtime_engine.ib_runtime_service)
            ctrader_state = self._runtime_broker_state(
                runtime_engine.ctrader_runtime_service
            )

            broker_rows.append(("IB", ib_state))
            broker_rows.append(("cTrader", ctrader_state))

        self._notify_broker_state_changes(broker_rows)

        connected_count = sum(1 for _, state in broker_rows if state == "CONNECTED")
        total_count = len(broker_rows)

        brokers_label = self._lang_mgr.tr("StatusBar.brokersLabel", "Brokers")
        active_label = self._lang_mgr.tr("StatusBar.activeBrokerLabel", "Active")

        active_broker = ""
        if runtime_engine is not None:
            active_broker = runtime_engine.get_active_broker()

        summary = f"{brokers_label}: {connected_count}/{total_count}"

        if active_broker and active_broker != "OFF":
            summary = f"{summary} | {active_label}: {active_broker}"

        self._sb_brokers.blockSignals(True)
        self._sb_brokers.clear()
        self._sb_brokers.addItem(summary)

        for broker_name, state in broker_rows:

            state_text = self._runtime_broker_state_text(state)

            account_id, balance_text = self._runtime_broker_balance_text(
                runtime_engine=runtime_engine,
                broker_name=broker_name,
                state=state,
            )

            if account_id or balance_text:

                broker_col = f"{broker_name:<{BROKER_COL_WIDTH}}"
                state_col = f"{state_text:<{STATE_COL_WIDTH}}"
                account_col = f"{account_id:<{ACCOUNT_COL_WIDTH}}"
                balance_col = f"{balance_text:>{BALANCE_COL_WIDTH}}"

                row_text = (
                    f"{broker_col} | "
                    f"{state_col} | "
                    f"{account_col} | "
                    f"{balance_col}"
                )

            else:

                row_text = f"{broker_name}: " f"{state_text}"

            broker_key = "CTRADER" if broker_name == "cTrader" else broker_name.upper()
            self._sb_brokers.addItem(row_text, broker_key)

        self._sb_brokers.setCurrentIndex(0)
        self._sb_brokers.blockSignals(False)
        self._apply_brokers_status_style(connected_count, total_count)

    @staticmethod
    def _runtime_broker_balance_text(
        runtime_engine,
        broker_name: str,
        state: str,
    ) -> tuple[str, str]:
        """
        Повернути account_id та balance для broker row у StatusBar.
        """
        if runtime_engine is None:
            return "", ""

        if state != "CONNECTED":
            return "", ""

        service = None

        if broker_name == "IB":
            service = getattr(runtime_engine, "ib_runtime_service", None)
        elif broker_name == "cTrader":
            service = getattr(runtime_engine, "ctrader_runtime_service", None)

        if service is None:
            return "", ""

        if not hasattr(service, "get_account_state"):
            return "", ""

        account_state = service.get_account_state()

        if account_state is None:
            return "", ""

        account_id = str(getattr(account_state, "account_id", "") or "").strip()

        balance = getattr(account_state, "balance", None)

        currency = str(getattr(account_state, "currency", "") or "").strip()

        balance_text = ""

        if balance not in ("", None):
            try:
                value = float(balance)

                balance_text = f"{value:,.2f}".replace(",", " ")

                if currency:
                    balance_text = f"{balance_text} {currency}"

            except (TypeError, ValueError):
                pass

        return account_id, balance_text

    @staticmethod
    def _runtime_balance_text(runtime_engine) -> str:
        """
        Повернути короткий текст balance для statusbar.
        """
        if runtime_engine is None:
            return ""

        parts = []

        for broker_name, service in (
            ("IB", getattr(runtime_engine, "ib_runtime_service", None)),
            ("cT", getattr(runtime_engine, "ctrader_runtime_service", None)),
        ):
            if service is None:
                continue
            if not hasattr(service, "get_account_state"):
                continue
            account_state = service.get_account_state()

            if not account_state.is_loaded():
                continue

            balance = account_state.balance
            currency = str(account_state.currency or "").strip()

            if balance in ("", None):
                continue

            balance_value = f"{float(balance):.2f}"

            if currency:
                parts.append(f"{broker_name}: {balance_value} {currency}")
            else:
                parts.append(f"{broker_name}: {balance_value}")

        return " | ".join(parts)

    @staticmethod
    def _runtime_broker_state(service) -> str:
        """
        Повернути короткий runtime state для broker service.
        """
        if service is None:
            return "OFF"

        try:
            health = service.get_broker_health()
        except Exception:  # noqa
            return "ERROR"

        if health is None:
            return "UNKNOWN"

        return str(health.state or "UNKNOWN")

    def _runtime_broker_state_text(self, state: str) -> str:
        """
        Повернути перекладений текст runtime-стану broker для StatusBar.
        """
        state_key_map = {
            "OFF": ("StatusBar.brokerStateOff", "OFF"),
            "UNKNOWN": ("StatusBar.brokerStateUnknown", "UNKNOWN"),
            "CONNECTED": ("StatusBar.brokerStateConnected", "CONNECTED"),
            "DISCONNECTED": ("StatusBar.brokerStateDisconnected", "DISCONNECTED"),
            "SAFE_DISCONNECTED": (
                "StatusBar.brokerStateSafeDisconnected",
                "SAFE DISCONNECTED",
            ),
            "RECONNECTING": ("StatusBar.brokerStateReconnecting", "RECONNECTING"),
            "ERROR": ("StatusBar.brokerStateError", "ERROR"),
        }

        key, fallback = state_key_map.get(
            state,
            ("StatusBar.brokerStateUnknown", "UNKNOWN"),
        )

        return self._lang_mgr.tr(key, fallback)

    def _apply_brokers_status_style(
        self,
        connected_count: int,
        total_count: int,
    ) -> None:
        """
        Застосувати простий колір для broker combo.
        """
        if total_count <= 0:
            self._sb_brokers.setStyleSheet("")
            return

        if connected_count == total_count:
            self._sb_brokers.setStyleSheet("QComboBox#sbBrokers { color: lightgreen; }")
            return

        if connected_count == 0:
            self._sb_brokers.setStyleSheet("QComboBox#sbBrokers { color: #ff7070; }")
            return

        self._sb_brokers.setStyleSheet("QComboBox#sbBrokers { color: yellow; }")

    def _init_broker_health_timer(self) -> None:
        """
        Періодично оновлювати broker health/statusbar.

        RoadMap78:
        потрібен для фіксації втрати інтернету під час роботи.
        """
        self._broker_health_timer = QTimer(self)
        self._broker_health_timer.timeout.connect(self._refresh_broker_health_status)
        self._broker_health_timer.start(5000)

    def _refresh_broker_health_status(self) -> None:
        """
        Оновити broker health, періодично перечитати account state
        і перемалювати StatusBar.
        """
        runtime_engine = getattr(session_state, "CURRENT_RUNTIME_ENGINE", None)

        if runtime_engine is None:
            return

        now_monotonic = time.monotonic()
        should_refresh_account = (
            now_monotonic - self._last_account_refresh_monotonic
            >= RUNTIME_ACCOUNT_REFRESH_INTERVAL_SECONDS
        )

        ib_service = runtime_engine.ib_runtime_service
        if ib_service is not None:
            try:
                ib_service.refresh_broker_health()

                if should_refresh_account:
                    ib_service.refresh_account_state()
            except Exception:  # noqa
                logger.exception("IB broker health/account refresh failed.")

        ctrader_service = runtime_engine.ctrader_runtime_service
        if ctrader_service is not None:
            try:
                ctrader_service.refresh_broker_health()

                if should_refresh_account:
                    ctrader_service.refresh_account_state()
            except Exception:  # noqa
                logger.exception("cTrader broker health/account refresh failed.")

        if should_refresh_account:
            self._last_account_refresh_monotonic = now_monotonic

        self._update_brokers_statusbar()

    def _notify_broker_state_changes(
        self,
        broker_rows: list[tuple[str, str]],
    ) -> None:
        """
        Повідомити користувача про зміну стану брокерів.
        """
        from core import session_state

        runtime_engine = getattr(session_state, "CURRENT_RUNTIME_ENGINE", None)

        for broker_name, state in broker_rows:
            previous_state = self._last_broker_states.get(broker_name)

            if previous_state == state:
                continue

            self._last_broker_states[broker_name] = state

            if previous_state is None:
                continue

            if state == "CONNECTED":
                message_text = self._lang_mgr.tr(
                    "RuntimeAlert.brokerConnectionRestored",
                    "Connection restored.",
                )
                message = f"{broker_name}: {message_text}"

                QApplication.beep()

                if hasattr(self, "_sb_runtime_alert"):
                    self._sb_runtime_alert.setText(message)
                    self._sb_runtime_alert.setStyleSheet("color: lightgreen;")

                logger.warning("%s connection restored.", broker_name)
                continue

            if state in {"DISCONNECTED", "SAFE_DISCONNECTED"}:
                if broker_name == "IB":
                    message_text = self._lang_mgr.tr(
                        "RuntimeAlert.ibConnectionLost",
                        "TWS is reconnecting to IBKR servers.",
                    )
                else:
                    message_text = self._lang_mgr.tr(
                        "RuntimeAlert.brokerConnectionLost",
                        "Connection to broker lost.",
                    )

                message = f"{broker_name}: {message_text}"

                QApplication.beep()

                if hasattr(self, "_sb_runtime_alert"):
                    self._sb_runtime_alert.setText(message)
                    self._sb_runtime_alert.setStyleSheet("color: orange;")

                logger.warning(
                    "%s connection lost. state=%s",
                    broker_name,
                    state,
                )

                if runtime_engine is not None:
                    if broker_name == "IB":
                        # runtime_engine.start_ib_reconnect_watch()
                        conf_obj = getattr(session_state, "CURRENT_CONFIG", None)
                        auto_ib = False

                        if conf_obj is not None:
                            conf = conf_obj.to_dict()
                            auto_ib = bool(
                                conf.get("engine", {})
                                .get("auto_connect", {})
                                .get("ib", False)
                            )
                        if (
                            runtime_engine is not None
                            and broker_name == "IB"
                            and auto_ib
                        ):
                            runtime_engine.start_ib_reconnect_watch()

                    elif broker_name == "cTrader":
                        runtime_engine.start_ctrader_reconnect_watch()
