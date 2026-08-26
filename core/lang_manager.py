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
from collections.abc import Mapping
from typing import Any, Dict

from PySide6.QtCore import QFile, QIODevice
from PySide6.QtGui import QIcon

from core.app_paths import LANG_DIR, STRINGS_JSON
from core.translation_format import restore_format_placeholders
from core.translation_policy import (
    translation_context_for_key,
    translation_overrides_for_key,
)

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
STRINGS_PATH = STRINGS_JSON

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
    def resolve(self, key: str, fallback: str = "") -> str | None:
        """
        Повернути переклад ключа.

        Порядок:
          1) strings.json для поточної мови;
          2) strings_fallback.json для поточної мови;
          3) реєстрація fallback і автопереклад поточною мовою;
          4) англійське значення зі strings.json;
          5) англійське значення зі strings_fallback.json;
          6) fallback як звичайний рядок;
          7) порожній рядок.
        """
        lang = self.current_language
        explicit_fallback = fallback.strip() if isinstance(fallback, str) else ""

        entry = self._strings.get(key)
        fb = self._fallback.get(key)
        source_text = self._format_source_text(
            entry=entry,
            fallback_entry=fb,
            explicit_fallback=explicit_fallback,
        )

        if isinstance(entry, dict):
            value = entry.get(lang)
            if isinstance(value, str) and value.strip():
                return restore_format_placeholders(source_text, value)

        if isinstance(entry, str) and entry.strip():
            return restore_format_placeholders(source_text, entry)

        if isinstance(fb, dict):
            value = fb.get(lang)
            if isinstance(value, str) and value.strip():
                return restore_format_placeholders(source_text, value)

        if explicit_fallback:
            if not isinstance(entry, dict):
                entry = {}
                self._strings[key] = entry

            if not str(entry.get("en") or "").strip():
                self._store_in_strings(key, "en", explicit_fallback)

            if lang != "en":
                translated = self._auto_translate(
                    lang,
                    explicit_fallback,
                    key=key,
                )
                localized_text = (
                    translated
                    if isinstance(translated, str) and translated.strip()
                    else explicit_fallback
                )
                localized_text = restore_format_placeholders(
                    explicit_fallback,
                    localized_text,
                )
                self._store_in_strings(
                    key,
                    lang,
                    localized_text,
                )
                return localized_text

            return explicit_fallback

        if isinstance(entry, dict):
            value_en = entry.get("en")
            if isinstance(value_en, str) and value_en.strip():
                return restore_format_placeholders(
                    source_text,
                    value_en,
                )

        if isinstance(fb, dict):
            value_en = fb.get("en")
            if isinstance(value_en, str) and value_en.strip():
                return restore_format_placeholders(
                    source_text,
                    value_en,
                )

        if isinstance(fb, str) and fb.strip():
            return restore_format_placeholders(source_text, fb)

        return ""

    @staticmethod
    def _format_source_text(
        *,
        entry: Any,
        fallback_entry: Any,
        explicit_fallback: str,
    ) -> str:
        """Return the English source used to validate format placeholders."""
        if explicit_fallback:
            return explicit_fallback

        if isinstance(fallback_entry, dict):
            value = fallback_entry.get("en")
            if isinstance(value, str) and value.strip():
                return value

        if isinstance(entry, dict):
            value = entry.get("en")
            if isinstance(value, str) and value.strip():
                return value

        if isinstance(fallback_entry, str):
            return fallback_entry

        if isinstance(entry, str):
            return entry

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

    @staticmethod
    def _auto_translate(
        target_lang: str,
        text: str,
        *,
        key: str = "",
    ) -> str:  # noqa
        """
        Автопереклад з EN через AITranslator (DeepL/Libre/mock).
        Якщо переклад недоступний — повертає оригінальний текст.
        """
        target_lang = (target_lang or "").strip().lower()
        text = text or ""

        if not target_lang:
            return text

        try:
            
            from core import session_state
            from core.ai_translator import AITranslator

            conf_dict = {}
            if session_state.CURRENT_CONFIG is not None:
                conf_dict = session_state.CURRENT_CONFIG.to_dict()

            tr = AITranslator(conf_dict, lang_dir=LANG_DIR)

            context = translation_context_for_key(key, target_lang)
            out = tr.translate(
                text=text,
                target_lang=target_lang,
                source_lang="en",
                context=context,
            )
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

            translated = self._auto_translate(lang, en_text, key=key)
            localized_text = (
                translated
                if isinstance(translated, str) and translated.strip()
                else en_text
            )
            localized_text = restore_format_placeholders(
                en_text,
                localized_text,
            )

            # створюємо dict тільки коли реально є що записати
            if not isinstance(s_entry, dict):
                s_entry = {}
                strings[key] = s_entry

            s_entry[lang] = localized_text
            written += 1

        self._strings = strings
        self.save_strings_file()
        return written

    def t(self, key: str) -> str:
        """
        Legacy-сумісність для старого виклику lang.t(key).

        Новий canonical API — tr(key, fallback).
        Цей метод лишається для старих модулів, щоб вони не падали
        під час поступового переходу на tr(...).
        """

        legacy_fallbacks = {
            "tokens_saved": "Tokens saved: {path}",
        }
        fallback = legacy_fallbacks.get(key, key)
        return self.tr(key, fallback)

    def tr(
        self,
        key: str,
        fallback: str,
        localized_fallbacks: Mapping[str, str] | None = None,
    ) -> str:
        """
        Повертає переклад ключа.

        Якщо ключ відсутній:
        - записує fallback як базове EN-значення у strings.json;
        - для активної мови може створити автопереклад.

        Централізовані контексти, термінологія та точні overrides беруться з
        ``core.translation_policy``. ``localized_fallbacks`` лишається тільки
        як рідкісний локальний виняток для зворотної сумісності.

        Після rebuild_fallback.py ключ переходить у strings_fallback.json.
        """
        centralized_fallbacks = translation_overrides_for_key(key)
        combined_fallbacks = dict(centralized_fallbacks)
        if localized_fallbacks:
            combined_fallbacks.update(localized_fallbacks)

        self._register_localized_fallbacks(
            key=key,
            fallback=fallback,
            localized_fallbacks=combined_fallbacks or None,
        )
        text = self.resolve(key, fallback)

        if isinstance(text, str) and text.strip():
            return text

        return fallback

    def _register_localized_fallbacks(
        self,
        *,
        key: str,
        fallback: str,
        localized_fallbacks: Mapping[str, str] | None,
    ) -> None:
        """Register contextual translations only when stored values differ."""
        if not localized_fallbacks:
            return

        desired: dict[str, str] = {"en": str(fallback)}
        for language, text in localized_fallbacks.items():
            normalized_language = str(language or "").strip().lower()
            normalized_text = str(text or "").strip()
            if not normalized_language or not normalized_text:
                continue
            desired[normalized_language] = restore_format_placeholders(
                fallback,
                normalized_text,
            )

        strings_entry = self._strings.get(key)
        fallback_entry = self._fallback.get(key)
        pending: dict[str, str] = {}

        for language, text in desired.items():
            current_override = None
            if isinstance(strings_entry, dict):
                current_override = strings_entry.get(language)

            if isinstance(current_override, str) and current_override.strip():
                if current_override != text:
                    pending[language] = text
                continue

            current_fallback = None
            if isinstance(fallback_entry, dict):
                current_fallback = fallback_entry.get(language)
            if current_fallback != text:
                pending[language] = text

        if not pending:
            return

        if not isinstance(strings_entry, dict):
            strings_entry = {}
            self._strings[key] = strings_entry
        strings_entry.update(pending)
        self.save_strings_file()


def get_lang() -> LangManager:
    """Повертає глобальний менеджер мов."""
    return LANG


# ---------------------------------------------------------
# Глобальний екземпляр менеджера мов
# ---------------------------------------------------------
LANG = LangManager()
