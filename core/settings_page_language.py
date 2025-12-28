# settings_page_language.py
# -*- coding: utf-8 -*-
"""
SettingsPageLanguage — сторінка налаштувань мови (QWidget + UI).
Тримає тільки UI + допоміжні методи (reload, snapshot/restore).
Логіку застосування (запис strings/conf + apply_translation) лишаємо в SettingsCenter.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QWidget

from core.lang_manager import LangManager
from ui.ui_settings_page_language import Ui_pageLanguage


class SettingsPageLanguage(QWidget):
    def __init__(self, parent: QWidget, lang_mgr: LangManager) -> None:
        super().__init__(parent)

        self._lang_mgr = lang_mgr
        self.ui = Ui_pageLanguage()
        self.ui.setupUi(self)

        ui = self.ui
        ui.comboLanguage.setStyleSheet(
            """
            QComboBox QAbstractItemView::item:selected {
                background: rgba(255,255,255,80);
                color: #FFFFFF;
            }
            QComboBox QAbstractItemView::item:hover {
                background: rgba(255,255,255,50);
            }
            """
        )

        self._saved_code: str = self._lang_mgr.current_language

    def snapshot(self) -> None:
        self._saved_code = self._lang_mgr.current_language

    def restore_snapshot(self) -> None:
        self.set_current_code(self._saved_code)

    def reload_combo(self) -> None:
        combo = self.ui.comboLanguage
        combo.blockSignals(True)
        combo.clear()

        current = self._lang_mgr.current_language
        for code in self._lang_mgr.language_codes():
            name = self._lang_mgr.language_name(code)
            icon = self._lang_mgr.get_flag_icon(code)
            combo.addItem(icon, name, code)

        self.set_current_code(current)
        combo.blockSignals(False)

    def current_code(self) -> Optional[str]:
        code = self.ui.comboLanguage.currentData()
        return code if isinstance(code, str) and code else None

    def set_current_code(self, code: str) -> None:
        combo = self.ui.comboLanguage
        idx = combo.findData(code)
        if idx >= 0:
            combo.setCurrentIndex(idx)
