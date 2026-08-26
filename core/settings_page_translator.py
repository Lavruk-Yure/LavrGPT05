# settings_page_translator.py
# -*- coding: utf-8 -*-
"""
SettingsPageTranslator — сторінка налаштувань перекладача (DeepL / Off).

Схема конфігу (canonical):
translator: {
  "provider": "deepl" | "off",
  "deepl_key_1": "...",
  "deepl_key_2": "..."
}

Важливе:
- LibreTranslate та mock видалені (і з UI, і з конфіга).
- Якщо в conf залишився старий provider ("libretranslate"/"mock") — показуємо "off".
- При збереженні конфіга видаляємо "libretranslate_url", якщо він є в старому conf.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from PySide6.QtWidgets import QWidget

from ui.ui_settings_page_translator import Ui_pageTranslator

logger = logging.getLogger(__name__)

DEBUG_SETTINGS_PAGE_TRANSLATOR = False


def log_cp(name: str, **kw: Any) -> None:
    """Локальний debug-логер SettingsPageTranslator."""
    if not DEBUG_SETTINGS_PAGE_TRANSLATOR:
        return
    logger.debug(
        "SettingsPageTranslator: %s | %s",
        name,
        ", ".join(f"{k}={v!r}" for k, v in kw.items()),
    )


@dataclass
class TranslatorSnapshot:
    provider: str = "off"
    deepl_key_1: str = ""
    deepl_key_2: str = ""


class SettingsPageTranslator(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.ui = Ui_pageTranslator()
        self.ui.setupUi(self)

        self._snapshot = TranslatorSnapshot()

        self._init_provider_combo()
        self.snapshot()

    # ---------------------------------------------------------
    def _init_provider_combo(self) -> None:
        combo = self.ui.comboProvider
        combo.clear()

        # 2 значення за ТЗ:
        combo.addItem("DeepL", "deepl")
        combo.addItem("Вимкнено", "off")

        # дефолт: off (безпечніше, ніж мовчки лізти в API)
        combo.setCurrentIndex(combo.findData("off"))
        log_cp("combo.inited", items=combo.count())

    def get_provider(self) -> str:
        combo = self.ui.comboProvider
        data = combo.currentData()
        if isinstance(data, str) and data:
            return data
        return "off"

    def set_provider(self, provider: str) -> None:
        provider = (provider or "off").strip().lower()
        if provider not in ("deepl", "off"):
            provider = "off"

        combo = self.ui.comboProvider
        idx = combo.findData(provider)
        if idx < 0:
            idx = combo.findData("off")
        if idx >= 0:
            combo.setCurrentIndex(idx)

    # ---------------------------------------------------------
    def snapshot(self) -> None:
        self._snapshot = TranslatorSnapshot(
            provider=self.get_provider(),
            deepl_key_1=self.ui.editDeeplKey1.text().strip(),
            deepl_key_2=self.ui.editDeeplKey2.text().strip(),
        )
        log_cp("snapshot", provider=self._snapshot.provider)

    def restore_snapshot(self) -> None:
        s = self._snapshot
        self.set_provider(s.provider)
        self.ui.editDeeplKey1.setText(s.deepl_key_1)
        self.ui.editDeeplKey2.setText(s.deepl_key_2)
        log_cp("restore", provider=s.provider)

    # ---------------------------------------------------------
    def load_from_config(self, conf: Dict[str, Any]) -> None:
        """
        Заповнює UI з conf (SettingsCenter очікує саме цю назву).
        """
        tr = conf.get("translator")
        if not isinstance(tr, dict):
            tr = {}

        provider = str(tr.get("provider") or "off").strip().lower()
        # міграція зі старих значень:
        if provider not in ("deepl", "off"):
            provider = "off"

        key1 = str(tr.get("deepl_key_1") or "").strip()
        key2 = str(tr.get("deepl_key_2") or "").strip()

        self.set_provider(provider)
        self.ui.editDeeplKey1.setText(key1)
        self.ui.editDeeplKey2.setText(key2)

        self.snapshot()
        log_cp("load", provider=provider, has_key1=bool(key1), has_key2=bool(key2))

    def write_to_config(self, conf: Dict[str, Any]) -> Dict[str, Any]:
        """
        Записує UI -> conf і повертає conf (SettingsCenter очікує саме цю назву).
        Також чистить legacy поля LibreTranslate.
        """
        provider = self.get_provider()
        key1 = self.ui.editDeeplKey1.text().strip()
        key2 = self.ui.editDeeplKey2.text().strip()

        tr = conf.get("translator")
        if not isinstance(tr, dict):
            tr = {}
            conf["translator"] = tr

        tr["provider"] = provider
        tr["deepl_key_1"] = key1
        tr["deepl_key_2"] = key2

        # legacy cleanup
        tr.pop("libretranslate_url", None)

        self.snapshot()
        log_cp("write", provider=provider, has_key1=bool(key1), has_key2=bool(key2))
        return conf
