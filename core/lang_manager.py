# core\lang_manager.py
"""
LangManager — керує перекладом інтерфейсу (Patch 11.0)

Функції:
    • завантаження strings.json (override)
    • завантаження strings_fallback.json (ресурс)
    • робота з lang_active.code
    • забезпечення fallback-механізму
    • повернення QIcon для прапорів мов
    • DEBUG-контрольні точки
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from PySide6.QtCore import QFile, QIODevice
from PySide6.QtGui import QIcon

# ---------------------------------------------------------
# Debug
# ---------------------------------------------------------
DEBUG_LANG = False  # поки налагоджуємо — залишимо True


def log_cp(name: str, **kw: Any) -> None:
    """
    Лог контрольної точки .
    Приклад:
        log_cp("init_done", lang=self._lang_mgr.current_language)
    """
    if not DEBUG_LANG:
        return
    msg = f"[LANG_CP:{name}] " + ", ".join(f"{k}={v!r}" for k, v in kw.items())
    print(msg)


# ---------------------------------------------------------
# Шляхи
# ---------------------------------------------------------
FALLBACK_PATH = ":/lang/strings_fallback.json"
STRINGS_PATH = Path("lang/strings.json")

# каталог(и) з прапорами у ресурсах
FLAG_DIRS = [
    ":/lang/flags",  # lang/flags/en_24.png тощо
    #    ":/icons/flags",  # резервний варіант, якщо знадобиться
]


# ---------------------------------------------------------
# Клас LangManager
# ---------------------------------------------------------
class LangManager:
    """
    Менеджер перекладу.

    Працює з двома джерелами:
        • strings.json      (користувацькі заміни)
        • strings_fallback  (ресурс)

    Також зберігає активну мову у:
        "lang_active": {"code": "<xx>"}
    """

    def __init__(self) -> None:
        """Ініціалізація менеджера мов."""
        self._strings: Dict[str, Any] = {}
        self._fallback: Dict[str, Any] = {}

        # ------------------------------
        # 1. Load strings.json (override)
        # ------------------------------
        self.load_strings()

        # ------------------------------
        # 2. Load fallback (resource)
        # ------------------------------
        self._fallback = self._load_json(FALLBACK_PATH)
        log_cp("init_fallback_loaded", path=FALLBACK_PATH, keys=len(self._fallback))

        # Карта доступних мов
        self._languages: Dict[str, str] = self._fallback.get("languages", {})
        log_cp("init_languages_map", languages=self._languages)

        # ------------------------------
        # 3. Load active language
        # ------------------------------
        default_lang = "en"

        active = self._strings.get("lang_active", {})
        code = active.get("code")

        if code in self._languages:
            self._current_lang = code
        else:
            self._current_lang = default_lang

        log_cp("init_current_lang", current_lang=self._current_lang)

    # ---------------------------------------------------------
    # 16.2 — допоміжні методи для сторінки Settings
    # ---------------------------------------------------------

    def list_languages(self) -> list[str]:
        return list(self._languages.keys())

    @property
    def current(self) -> str:
        """Поточний код мови (alias до current_language)."""
        return self._current_lang

    def get_native_name(self, code: str) -> str:
        """Назва мови для відображення в ComboBox."""
        return self.language_name(code)

    def set_language(self, code: str) -> None:
        """Встановити мову (alias до set_current_language)."""
        self.set_current_language(code)

    # ---------------------------------------------------------
    # JSON loader (resource)
    # ---------------------------------------------------------
    @staticmethod
    def _load_json(path: str) -> Dict[str, Any]:
        """Завантаження JSON із Qt-ресурсу."""
        f = QFile(path)
        if not f.open(QIODevice.OpenModeFlag.ReadOnly):
            log_cp("fallback_open_fail", path=path)
            return {}

        raw = bytes(f.readAll().data())
        f.close()

        try:
            data = json.loads(raw.decode("utf-8"))
            log_cp("load_resource_ok", path=path, keys=len(data))
            return data
        except Exception as exc:  # noqa: BLE001
            log_cp("load_resource_error", path=path, err=str(exc))
            return {}

    # ---------------------------------------------------------
    # Load strings.json (override)
    # ---------------------------------------------------------
    def load_strings(self) -> None:
        """
        Завантажує strings.json.

        Гарантії:
        • якщо файл відсутній -> створюється {"lang_active": {"code": "en"}}
        • якщо файл порожній -> створюється мінімальний словник
        • якщо JSON пошкоджений -> файл перезаписується мінімальним словником
        """
        log_cp("load_strings_start")

        base_data = {"lang_active": {"code": "en"}}

        # 1. Файл не існує
        if not STRINGS_PATH.exists():
            log_cp("strings_missing", created=base_data)
            self._strings = base_data
            self.save_strings_file()
            return

        # 2. Пробуємо прочитати
        try:
            raw = STRINGS_PATH.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception as exc:
            log_cp("strings_corrupted", err=str(exc))
            self._strings = base_data
            self.save_strings_file()
            return

        # 3. Порожній або не dict
        if not isinstance(data, dict) or not data:
            log_cp("strings_empty", created=base_data)
            self._strings = base_data
            self.save_strings_file()
            return

        # 4. Все ок
        self._strings = data
        log_cp("strings_loaded", lang_active=self._strings.get("lang_active"))

    def save_strings_file(self) -> None:
        """Записує self._strings у strings.json."""
        try:
            STRINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            STRINGS_PATH.write_text(
                json.dumps(self._strings, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            log_cp("strings_saved_ok")
        except Exception as exc:
            log_cp("strings_save_error", err=str(exc))

    # ---------------------------------------------------------
    # Public API — мови
    # ---------------------------------------------------------
    @property
    def languages(self) -> Dict[str, str]:
        """Список доступних мов (код → назва)."""
        return self._languages

    @property
    def current_language(self) -> str:
        """Повертає активну мову (код)."""
        return self._current_lang

    # ---------------------------------------------------------
    # Language setter
    # ---------------------------------------------------------
    def set_current_language(self, code: str) -> None:
        """Встановлює мову та зберігає у strings.json (ТІЛЬКИ lang_active)."""
        if code not in self._languages:
            log_cp("set_lang_fail", code=code)
            return

        self._current_lang = code
        log_cp("set_lang_ok", code=code)
        self._save_active_lang()

    # ---------------------------------------------------------
    # Save active language to strings.json
    # ---------------------------------------------------------
    def _save_active_lang(self) -> None:
        """Зберігає {"lang_active": {"code": ...}} у strings.json."""
        try:
            self._strings["lang_active"] = {"code": self._current_lang}

            STRINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            STRINGS_PATH.write_text(
                json.dumps(self._strings, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            log_cp("active_lang_saved", code=self._current_lang)
        except Exception as exc:  # noqa: BLE001
            log_cp("active_lang_save_error", err=str(exc))

    # ---------------------------------------------------------
    # Resolve translation key
    # ---------------------------------------------------------
    def resolve(self, key: str) -> str | None:
        """
        Read-only resolve (без автоперекладу і без записів у strings.json):
          1) strings.json[lang]
          2) fallback[lang]
          3) fallback["en"]
          4) fallback як str
          5) "" (нічого не створюємо)
        """
        lang = self.current_language

        entry = self._strings.get(key)
        if isinstance(entry, dict):
            val = entry.get(lang)
            if isinstance(val, str) and val.strip():
                return val
        if isinstance(entry, str) and entry.strip():
            return entry

        fb = self._fallback.get(key)

        if isinstance(fb, dict):
            val = fb.get(lang)
            if isinstance(val, str) and val.strip():
                return val

            val_en = fb.get("en")
            if isinstance(val_en, str) and val_en.strip():
                return val_en

        if isinstance(fb, str) and fb.strip():
            return fb

        return ""

    # ---------------------------------------------------------
    # Flag icons
    # ---------------------------------------------------------

    @staticmethod
    def get_flag_icon(code: str) -> QIcon:
        path = f":/lang/flags/{code}_24.png"
        fallback = ":/lang/flags/no_flag_24.png"

        if QFile.exists(path):
            return QIcon(path)
        if QFile.exists(fallback):
            return QIcon(fallback)
        return QIcon()

    def language_codes(self) -> list[str]:
        """Список мов, визначених у fallback.json."""
        return list(self._languages.keys())

    def language_name(self, code: str) -> str:
        """Людське ім’я мови: English, Українська, Deutsch..."""
        return self._languages.get(code, code)

    def _store_in_strings(self, key: str, lang: str, value: str) -> None:
        """Записує ключ у self._strings і одразу зберігає strings.json."""
        entry = self._strings.get(key)

        if not isinstance(entry, dict):
            entry = {}
            self._strings[key] = entry

        entry[lang] = value

        # використовуємо існуючий метод
        self.save_strings_file()

    def _auto_translate(self, target_lang: str, text: str) -> str:  # noqa
        """
        Автопереклад з EN через AITranslator (DeepL/Libre/mock).
        Якщо переклад недоступний — повертає оригінальний текст.
        """
        target_lang = (target_lang or "").strip().lower()
        text = text or ""

        if not target_lang:
            return text

        try:
            from pathlib import Path

            from core import session_state
            from core.ai_translator import AITranslator

            conf_dict = {}
            if session_state.CURRENT_CONFIG is not None:
                conf_dict = session_state.CURRENT_CONFIG.to_dict()

            tr = AITranslator(conf_dict, lang_dir=Path("lang"))

            out = tr.translate(text=text, target_lang=target_lang, source_lang="en")
            return out if isinstance(out, str) and out.strip() else text

        except Exception:  # noqa
            return text

    def is_language_new(self, lang: str) -> bool:
        lang = (lang or "").strip().lower()
        if not lang or lang == "en":
            return False

        strings = self._strings if isinstance(self._strings, dict) else {}
        fallback = self._fallback if isinstance(self._fallback, dict) else {}

        for key, fb_entry in fallback.items():
            if key == "languages":
                continue
            if not isinstance(fb_entry, dict):
                continue

            en_text = fb_entry.get("en")
            if not isinstance(en_text, str) or not en_text.strip():
                continue

            # якщо у fallback вже є lang — це не “нова/порожня” для цього ключа
            if isinstance(fb_entry.get(lang), str) and fb_entry.get(lang, "").strip():
                continue

            s_entry = strings.get(key)
            if not isinstance(s_entry, dict):
                return True
            if (
                not isinstance(s_entry.get(lang), str)
                or not s_entry.get(lang, "").strip()
            ):
                return True

        return False

    def initialize_language(self, lang: str) -> int:
        """
        Одноразово заповнює strings перекладами для нової мови:
        - джерело: fallback["en"]
        - переклад: AITranslator (deepl/libre/mock)
        Повертає кількість записаних ключів.
        """
        lang = (lang or "").strip().lower()
        if not lang or lang == "en":
            return 0

        strings = self._strings if isinstance(self._strings, dict) else {}
        fallback = self._fallback if isinstance(self._fallback, dict) else {}

        written = 0

        for key, fb_entry in fallback.items():
            if key == "languages":
                continue
            if not isinstance(fb_entry, dict):
                continue

            en_text = fb_entry.get("en")
            if not isinstance(en_text, str) or not en_text.strip():
                continue

            # якщо у fallback вже є lang — пропускаємо (ручний переклад)
            if isinstance(fb_entry.get(lang), str) and fb_entry.get(lang, "").strip():
                continue

            s_entry = strings.get(key)
            if isinstance(s_entry, dict):
                # якщо у strings вже є lang — пропускаємо
                if isinstance(s_entry.get(lang), str) and s_entry.get(lang, "").strip():
                    continue
            else:
                s_entry = None  # не створюємо {} завчасно

            translated = self._auto_translate(lang, en_text)

            # не пишемо сміття: пусто або те саме, що EN
            if not isinstance(translated, str) or not translated.strip():
                continue
            if translated.strip() == en_text.strip():
                continue

            # створюємо dict тільки коли реально є що записати
            if not isinstance(s_entry, dict):
                s_entry = {}
                strings[key] = s_entry

            s_entry[lang] = translated
            written += 1

            # якщо у strings вже є lang — пропускаємо
            if isinstance(s_entry.get(lang), str) and s_entry.get(lang, "").strip():
                continue

            translated = self._auto_translate(lang, en_text)

            # не пишемо сміття: пусто або те саме, що EN
            if not isinstance(translated, str) or not translated.strip():
                continue
            if translated.strip() == en_text.strip():
                continue

            s_entry[lang] = translated
            written += 1

        self._strings = strings
        self.save_strings_file()
        return written


def get_lang() -> LangManager:
    """Повертає глобальний менеджер мов."""
    return LANG


# ---------------------------------------------------------
# Глобальний екземпляр менеджера мов
# ---------------------------------------------------------
LANG = LangManager()
