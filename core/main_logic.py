# main_logic.py
"""
core/main_logic.py — головне робоче вікно LGE05.

Функції:
- ліва панель навігації (Моніторинг / Ордери / Налаштування / Про програму) +
    Вихід внизу
- центральна область зі сторінками (поки плейсхолдери)
- toolbar (ті самі дії)
- statusBar (показує назву активної сторінки)
- UITranslator + глобальний LANG

Patch: toolbar hover + правильний порядок меню
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.about_dialog import AboutDialog
from core.lang_manager import LANG
from core.settings_center import SettingsCenter
from core.ui_translator import UITranslator
from ui.ui_main_app import Ui_MainAppWindow

DEBUG_MAIN = False


def log_cp(name: str, **kw: Any) -> None:
    """Локальний debug-логер модуля."""
    if not DEBUG_MAIN:
        return
    msg = f"[MAIN:{name}] " + ", ".join(f"{k}={v!r}" for k, v in kw.items())
    print(msg)


class MainAppWindow(QMainWindow):
    """Основне вікно LGE05."""

    def __init__(self) -> None:
        super().__init__()

        # --- UI ---
        self.ui = Ui_MainAppWindow()
        self.ui.setupUi(self)

        # --- Lang / Translator ---
        self._lang_mgr = LANG
        self._ui_translator = UITranslator(self._lang_mgr)

        # --- Layout ---
        main_layout = QHBoxLayout(self.ui.centralArea)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # =========================================================
        # LEFT PANEL
        # =========================================================
        self.left_panel = QFrame(self.ui.centralArea)
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
        self.stacked = QStackedWidget(self.ui.centralArea)

        self.page_monitoring = QLabel("[MainAppWindow.pageMonitoring]")
        self.page_monitoring.setObjectName("pageMonitoring")
        self.page_monitoring.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.page_orders = QLabel("[MainAppWindow.pageOrders]")
        self.page_orders.setObjectName("pageOrders")
        self.page_orders.setAlignment(Qt.AlignmentFlag.AlignCenter)

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

        # Текстові кнопки
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)

        # Весь hover робимо стилем тулбара (а не findChildren)
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

/* Exit — червоний hover (кнопці дамо objectName tbExit) */
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

        # Позначаємо кнопку Exit в toolbar, щоб працював QToolButton#tbExit
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
        self.btn_exit.clicked.connect(self.close)

        self.action_monitor.triggered.connect(
            lambda: self._switch_page(self.page_monitoring)
        )
        self.action_orders.triggered.connect(
            lambda: self._switch_page(self.page_orders)
        )
        self.action_settings.triggered.connect(self._open_settings_dialog)
        self.action_about.triggered.connect(self._open_about_dialog)
        self.action_exit.triggered.connect(self.close)

        # =========================================================
        # APPLY TRANSLATION (початковий)
        # =========================================================
        self._ui_translator.apply(self)
        log_cp("init_done", lang=self._lang_mgr.current_language)

        # Стартова сторінка
        self._switch_page(self.page_monitoring)

    # ------------------------------------------------------------------
    def _switch_page(self, page_widget: QWidget) -> None:
        """Перемикає сторінку в центральному StackedWidget."""
        self.stacked.setCurrentWidget(page_widget)

        title = ""
        if hasattr(page_widget, "text"):
            try:
                text = page_widget.text()
                title = text.replace("(TODO)", "").strip()
            except Exception:  # noqa
                title = ""

        self.ui.statusBarMain.showMessage(title or " ")
        log_cp("switch", title=title)

    # ------------------------------------------------------------------
    def apply_translation(self) -> None:
        """Повторно застосувати переклад до цього вікна."""
        self._ui_translator.apply(self)
        log_cp("retranslated", lang=self._lang_mgr.current_language)

    # ------------------------------------------------------------------
    def _open_settings_dialog(self) -> None:
        """Відкрити діалог налаштувань."""
        dlg = SettingsCenter(self)
        dlg.exec()

    def _open_about_dialog(self) -> None:
        """Відкрити діалог 'Про програму'."""
        dlg = AboutDialog(self)
        dlg.exec()
