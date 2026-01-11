# settings_center.py
"""
SettingsCenter — центр налаштувань LGE05 (меню-стиль).

Patch 1:
- Новий каркас: treeNav + stackPages.
- Навігація зліва (items тільки кодом):
    0) Language
    1) IB Trader (stub)
    2) cTrader (stub)
    3) Exit (action)
- Без глобальних OK/Apply/Cancel (кнопки будуть локально на сторінках).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QTreeWidgetItem, QVBoxLayout, QWidget

from core.lang_manager import LANG
from core.settings_page_language import SettingsPageLanguage
from core.settings_page_license import SettingsPageLicense
from core.settings_page_translator import SettingsPageTranslator
from core.ui_translator import UITranslator
from ui.ui_settings_center import Ui_SettingsCenter

DEBUG_SETTINGS_CENTER = False


def log_cp(name: str, **kw: Any) -> None:
    """Локальний debug-логер SettingsCenter."""
    if not DEBUG_SETTINGS_CENTER:
        return
    msg = f"[SET_CENTER:{name}] " + ", ".join(f"{k}={v!r}" for k, v in kw.items())
    print(msg)


@dataclass(frozen=True)
class NavEntry:
    key: str
    page_index: Optional[int] = None
    action: Optional[str] = None


class SettingsCenter(QDialog):
    ROLE_PAGE = int(Qt.ItemDataRole.UserRole) + 10
    ROLE_ACTION = int(Qt.ItemDataRole.UserRole) + 11

    def __init__(self, main_window: QWidget):
        super().__init__(main_window)

        self._main_window = main_window
        self._lang_mgr = LANG
        self._translator = UITranslator(self._lang_mgr)

        self.ui = Ui_SettingsCenter()
        self.ui.setupUi(self)
        self.ui.treeNav.itemActivated.connect(self._on_nav_activated)
        self.ui.treeNav.setStyleSheet(
            """
        QTreeWidget {
            background: rgba(255,255,255,18);
            color: #EDEDED;
            border: 1px solid rgba(255,255,255,25);
            outline: 0;
        }
        QTreeWidget::item {
            padding: 6px 10px;
        }
        QTreeWidget::item:selected {
            background: rgba(255,255,255,55);
            color: #FFFFFF;
        }
        QTreeWidget::item:hover {
            background: rgba(255,255,255,35);
        }
        """
        )
        self.ui.treeNav.setAllColumnsShowFocus(True)
        self.ui.treeNav.setSelectionBehavior(
            self.ui.treeNav.SelectionBehavior.SelectRows
        )

        self._init_pages()
        self._init_tree_items()

        self._page_language.reload_combo()
        self._page_language.snapshot()

        ui_lang = self._page_language.ui
        ui_lang.btnApply.clicked.connect(self._lang_apply)
        ui_lang.btnOK.clicked.connect(self._lang_ok)
        ui_lang.btnCancel.clicked.connect(self._lang_cancel)

        self.ui.treeNav.currentItemChanged.connect(self._on_nav_changed)

        self.ui.treeNav.itemClicked.connect(self._on_nav_clicked)

        self._load_translator_from_conf()
        self._bind_translator_buttons()

        # переклад одразу (поки ключі можуть бути “сирі”, але це нормально)
        self._translator.apply(self)
        log_cp("init.done")

    # ---------------------------------------------------------
    def _init_pages(self) -> None:
        """Створює сторінки-пустишки для stackPages."""
        stack = self.ui.stackPages

        # QStackedWidget не має clear() — чистимо вручну
        while stack.count() > 0:
            w = stack.widget(0)
            stack.removeWidget(w)
            w.deleteLater()

        self._page_language = SettingsPageLanguage(stack, self._lang_mgr)
        stack.addWidget(self._page_language)  # index = 0

        self._page_translator = SettingsPageTranslator(stack)
        stack.addWidget(self._page_translator)
        # index = 1 (якщо перед IB)

        self._page_license = SettingsPageLicense(stack, self._lang_mgr)
        stack.addWidget(self._page_license)  # index = 2

        stack.addWidget(self._make_stub_page("[SettingsPageIB.header]"))

        stack.addWidget(self._make_stub_page("[SettingsPageCTrader.header]"))

        stack.setCurrentIndex(0)
        log_cp("pages.inited", count=stack.count())

    @staticmethod
    def _make_stub_page(header_key: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        lbl = QLabel(header_key)
        lbl.setObjectName("lblHeader")
        layout.addWidget(lbl)
        layout.addStretch(1)
        return page

    # ---------------------------------------------------------
    def _init_tree_items(self) -> None:
        """Створює навігацію (items тільки кодом)."""
        tree = self.ui.treeNav
        tree.clear()
        tree.setColumnCount(1)
        tree.setHeaderHidden(True)

        entries = [
            NavEntry("[SettingsCenter.tree.language]", page_index=0),
            NavEntry("[SettingsCenter.tree.translator]", page_index=1),
            NavEntry("[SettingsCenter.tree.license]", page_index=2),
            NavEntry("[SettingsCenter.tree.ib]", page_index=3),
            NavEntry("[SettingsCenter.tree.ctrader]", page_index=4),
            NavEntry("[SettingsCenter.tree.exit]", action="exit"),
        ]

        for e in entries:
            item = QTreeWidgetItem(tree)
            item.setText(0, e.key)
            if e.page_index is not None:
                item.setData(0, self.ROLE_PAGE, int(e.page_index))

            if e.action:
                item.setData(0, self.ROLE_ACTION, e.action)

        tree.setCurrentItem(tree.topLevelItem(0))
        log_cp("tree.inited", count=tree.topLevelItemCount())

    # ---------------------------------------------------------
    def _on_nav_changed(self, current: QTreeWidgetItem, _prev: QTreeWidgetItem) -> None:
        if current is None:
            return

        action = current.data(0, self.ROLE_ACTION)
        page = current.data(0, self.ROLE_PAGE)

        log_cp(
            "nav.changed",
            text=current.text(0),
            action=action,
            page=page,
            page_type=type(page).__name__,
            stack_count=self.ui.stackPages.count(),
        )

        log_cp("roles", ROLE_PAGE=self.ROLE_PAGE, ROLE_ACTION=self.ROLE_ACTION)

        # QTreeWidget інколи повертає не pure-int; підстрахуємось
        try:
            page_i = int(page)
        except Exception:  # noqa
            log_cp("nav.page.invalid", reason="cannot int(page)", page=page)
            return
        # --- спеціальні дії (без сторінок) ---
        if action == "exit":
            log_cp("nav.action", action="exit")
            self.reject()  # або self.close()
            return

        if 0 <= page_i < self.ui.stackPages.count():
            self.ui.stackPages.setCurrentIndex(page_i)

            log_cp(
                "nav.page",
                page=page_i,
                page_count=self.ui.stackPages.count(),
                text=current.text(0),
            )

            # License page: refresh on enter
            if page_i == 2 and hasattr(self, "_page_license"):
                try:
                    log_cp("license.refresh.enter")
                    self._page_license.refresh()
                except Exception as e:  # noqa
                    log_cp("license.refresh.error", err=str(e))

    def _reload_languages_combo(self) -> None:
        self._page_language.reload_combo()

    def _lang_apply(self) -> None:
        ui = self._page_language.ui
        code = ui.comboLanguage.currentData()
        if not isinstance(code, str) or not code:
            return

        self._apply_language(code)
        self._lang_saved = code

    def _lang_ok(self) -> None:
        self._lang_apply()
        self.close()

    def _lang_cancel(self) -> None:
        ui = self._page_language.ui
        saved = getattr(self, "_lang_saved", self._lang_mgr.current_language)
        idx = ui.comboLanguage.findData(saved)
        if idx >= 0:
            ui.comboLanguage.setCurrentIndex(idx)
        self._page_language.restore_snapshot()
        self.close()

    def _apply_language(self, code: str) -> None:
        # 0) автозаповнення тільки тут (Apply/OK), не на старті та не на логіні
        try:
            if code != "en" and self._lang_mgr.is_language_new(code):
                self._lang_mgr.initialize_language(
                    code
                )  # всередині save_strings_file()
        except Exception:  # noqa
            pass

        # 1) strings.json (тільки lang_active)
        try:
            if code != "en" and self._lang_mgr.is_language_new(code):
                self._lang_mgr.initialize_language(code)
        except Exception:  # noqa
            pass

        self._lang_mgr.set_current_language(code)

        # 2) LGE05.conf (якщо є сесія)
        try:
            from core import session_state
            from core.app_paths import ROOT_CONF_PATH
            from core.config_manager import ConfigManager

            if (
                session_state.CURRENT_CONFIG is not None
                and session_state.CURRENT_PASSWORD is not None
            ):
                password: str = session_state.CURRENT_PASSWORD
                session_state.CURRENT_CONFIG.set("", "language", code)
                ConfigManager(ROOT_CONF_PATH).save(
                    session_state.CURRENT_CONFIG.to_dict(), password
                )
        except Exception:  # noqa
            pass

        self._page_language.snapshot()

        # 3) оновити MainApp
        if hasattr(self._main_window, "apply_translation"):
            self._main_window.apply_translation()

        # 4) оновити сам SettingsCenter
        self._translator.apply(self)
        self._reload_languages_combo()

    def _load_translator_from_conf(self) -> None:
        try:
            from core import session_state

            if session_state.CURRENT_CONFIG is None:
                return
            conf = session_state.CURRENT_CONFIG.to_dict()
            self._page_translator.load_from_config(conf)
        except Exception:  # noqa
            return

    def _bind_translator_buttons(self) -> None:
        ui = self._page_translator.ui
        ui.btnApply.clicked.connect(self._translator_apply)
        ui.btnOK.clicked.connect(self._translator_ok)
        ui.btnCancel.clicked.connect(self._translator_cancel)

    def _translator_apply(self) -> None:
        self._apply_translator_settings(close_after=False)

    def _translator_ok(self) -> None:
        self._apply_translator_settings(close_after=True)

    def _translator_cancel(self) -> None:
        self._page_translator.restore_snapshot()
        self.close()

    def _apply_translator_settings(self, close_after: bool) -> None:
        try:
            from core import session_state
            from core.app_paths import ROOT_CONF_PATH
            from core.config_manager import ConfigManager

            if (
                session_state.CURRENT_CONFIG is None
                or session_state.CURRENT_PASSWORD is None
            ):
                return

            password: str = session_state.CURRENT_PASSWORD

            conf = session_state.CURRENT_CONFIG.to_dict()
            conf = self._page_translator.write_to_config(conf)

            # запис назад в CURRENT_CONFIG (щоб стан був консистентний)
            session_state.CURRENT_CONFIG = session_state.CURRENT_CONFIG.__class__(conf)

            ConfigManager(ROOT_CONF_PATH).save(conf, password)

            # переклад UI не чіпаємо: це не мова, це лише конфіг перекладача
            if close_after:
                self.close()

        except Exception:  # noqa
            return

    def _on_nav_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        # У деяких стилях/налаштуваннях UI клік не робить item поточним.
        # Тому примусово:
        self.ui.treeNav.setCurrentItem(item)

    def _on_nav_activated(self, item: QTreeWidgetItem, _col: int) -> None:
        action = item.data(0, self.ROLE_ACTION)
        if action == "exit":
            self.close()
