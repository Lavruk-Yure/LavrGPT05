# settings_page_language.py
# -*- coding: utf-8 -*-
"""
SettingsPageLanguage — сторінка налаштувань мови.

Завдання:
- ComboBox показує: [прапор] [код] [назва]
- Те саме у випадаючому списку.
- Дані itemData = code (чистий код, без тексту).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QComboBox, QWidget

from core.lang_manager import LangManager
from ui.ui_settings_page_language import Ui_pageLanguage

logger = logging.getLogger(__name__)

DEBUG_SETTINGS_PAGE_LANGUAGE = False


def log_cp(name: str, **kw: object) -> None:
    """Локальний debug-логер SettingsPageLanguage."""
    if not DEBUG_SETTINGS_PAGE_LANGUAGE:
        return
    logger.debug(
        "SettingsPageLanguage: %s | %s",
        name,
        ", ".join(f"{k}={v!r}" for k, v in kw.items()),
    )


@dataclass
class LanguageSnapshot:
    code: str = "en"


class SettingsPageLanguage(QWidget):
    """UI-сторінка вибору мови (без логіки збереження)."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        lang_mgr: Optional[LangManager] = None,
    ) -> None:
        """
        Сумісність з існуючим викликом у SettingsCenter:
            SettingsPageLanguage(stack, self._lang_mgr)

        Тобто:
            parent = stack (QWidget)
            lang_mgr = LangManager
        """
        # Якщо хтось випадково передав LangManager першим аргументом
        if isinstance(parent, LangManager) and lang_mgr is None:
            lang_mgr = parent
            parent = None

        super().__init__(parent)

        if lang_mgr is None:
            raise TypeError("SettingsPageLanguage: lang_mgr is required")

        self.ui = Ui_pageLanguage()
        self.ui.setupUi(self)

        self._lang_mgr = lang_mgr
        self._snapshot = LanguageSnapshot(code=self._lang_mgr.current_language)

        self._setup_combo_view()
        self.reload_combo()
        self.snapshot()

    # ---------------------------------------------------------
    def _setup_combo_view(self) -> None:
        """Налаштування ComboBox: fixed-font для вирівнювання коду/назви."""
        combo: QComboBox = self.ui.comboLanguage

        # Вирівнювання робимо моноширинним системним шрифтом.
        # Так ljust() реально працює і виглядає як “колонки”.
        fixed_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        combo.setFont(fixed_font)

        view = combo.view()
        if view is not None:
            view.setFont(fixed_font)

        # Щоб не “стрибала” ширина при різних мовах
        combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        combo.setMinimumContentsLength(18)

        # Не обов’язково, але корисно
        combo.setMaxVisibleItems(25)

        log_cp("combo.setup_done")

    # ---------------------------------------------------------
    @staticmethod
    def _display_text(code: str, native_name: str) -> str:
        """
        Формат: "uk   Українська"
        (код вирівнюємо до 5 символів — нормально для en/de/uk/pt-br тощо)
        """
        code_clean = (code or "").strip()
        name_clean = (native_name or "").strip()
        return f"{code_clean.ljust(5)} {name_clean}"

    # ---------------------------------------------------------

    def reload_combo(self) -> None:
        """Перезавантажує список мов у ComboBox."""
        combo: QComboBox = self.ui.comboLanguage
        current = self.current_code() or self._lang_mgr.current_language

        combo.blockSignals(True)
        combo.clear()

        # Сортуємо по коду — як ти любиш (класично і передбачувано)
        codes = sorted(self._lang_mgr.language_codes())

        for code in codes:
            name = self._lang_mgr.language_name(code)
            icon = self._lang_mgr.get_flag_icon(code)

            combo.addItem(icon, self._display_text(code, name), code)

        self.set_current_code(current)
        combo.blockSignals(False)

        log_cp("combo.reload_done", count=combo.count(), current=current)

    # ---------------------------------------------------------
    def current_code(self) -> Optional[str]:
        code = self.ui.comboLanguage.currentData()
        return code if isinstance(code, str) and code.strip() else None

    def set_current_code(self, code: str) -> None:
        code = (code or "").strip().lower()
        combo: QComboBox = self.ui.comboLanguage
        idx = combo.findData(code)
        if idx >= 0:
            combo.setCurrentIndex(idx)
            log_cp("combo.set_current", code=code, idx=idx)
        else:
            log_cp("combo.set_current_fail", code=code)

    # ---------------------------------------------------------
    def snapshot(self) -> None:
        self._snapshot = LanguageSnapshot(code=self.current_code() or "en")
        log_cp("snapshot", code=self._snapshot.code)

    def restore_snapshot(self) -> None:
        self.set_current_code(self._snapshot.code)
        log_cp("restore", code=self._snapshot.code)
