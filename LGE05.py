# LGE05.py
# -*- coding: utf-8 -*-
"""
LGE05 — точка входу (Patch 9.1).

Важливе:
- На старті ще немає LANG-менеджера, тому системні QMessageBox (про битий conf)
  беремо з ресурсу lang/strings_fallback.json
  (Qt resource: :/lang/strings_fallback.json).
- Мову для цих QMessageBox беремо з lang/strings.json -> {"lang_active":{"code":"uk"}}
  Якщо файла нема / JSON битий — fallback 'en'.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from typing import Any, Dict, cast

from PySide6.QtCore import QCoreApplication, QFile, QIODevice
from PySide6.QtWidgets import QApplication, QMessageBox

import resources_rc  # noqa: F401
from core.app_paths import ROOT_CONF_PATH, STRINGS_JSON, ensure_session_dir
from core.conf_guard import backup_bad_conf, check_conf_state
from core.login_logic import LoginWindow
from core.register_logic import RegisterWindow
from core.splash_runner import run_splash

DEBUG_LGE05 = False


def log_cp(name: str, **kw: Any) -> None:
    """Локальний debug-логер LGE05."""
    if not DEBUG_LGE05:
        return
    msg = f"[LGE05:{name}] " + ", ".join(f"{k}={v!r}" for k, v in kw.items())
    print(msg)


# ============================================================
# Minimal language (pre-LANG) + fallback strings
# ============================================================


def _read_lang_active_default_en() -> str:
    """
    Беремо мову з lang/strings.json:
      {"lang_active":{"code":"uk"}}
    Якщо нема/битий — 'en'.
    """
    try:
        if not STRINGS_JSON.exists():
            return "en"
        data = json.loads(STRINGS_JSON.read_text(encoding="utf-8") or "{}")
        lang_active = data.get("lang_active")
        if isinstance(lang_active, dict):
            code = lang_active.get("code")
            if isinstance(code, str) and code.strip():
                return code.strip().lower()
    except Exception:  # noqa
        return "en"
    return "en"


def _load_fallback_strings() -> Dict[str, Any]:
    """
    Читає resource :/lang/strings_fallback.json.
    Повертає dict або {}.
    """
    try:
        f = QFile(":/lang/strings_fallback.json")
        if not f.open(QIODevice.OpenModeFlag.ReadOnly):
            return {}

        qba = f.readAll()  # QByteArray
        f.close()

        # PyCharm: QByteArray.data() не типізований як bytes, тому cast.
        raw_bytes = cast(bytes, qba.data())
        raw = raw_bytes.decode("utf-8", errors="replace")

        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa
        return {}


_FALLBACK: Dict[str, Any] = _load_fallback_strings()


def fb(key: str, lang_code: str) -> str:
    """
    Fallback-рядок:
      1) key[lang_code]
      2) key['en']
      3) key (останній варіант)
    """
    node = _FALLBACK.get(key)
    if isinstance(node, dict):
        v = node.get(lang_code)
        if isinstance(v, str) and v:
            return v
        v = node.get("en")
        if isinstance(v, str) and v:
            return v
    return key


# ============================================================
# Safe translate patch (Qt → sanitised)
# ============================================================

_original_translate = QCoreApplication.translate


def _sanitize_text(text: str) -> str:
    """Normalize text, remove surrogate pairs, enforce UTF-8 safe."""
    s = unicodedata.normalize("NFC", text)
    s = re.sub(r"[\ud800-\udfff]", "", s)
    return s.encode("utf-8", "replace").decode("utf-8", "replace")


def safe_translate(context: str, text: str, disambiguation=None):
    """Wrapper to prevent crashes on broken Unicode."""
    try:
        clean = _sanitize_text(text)
        return _original_translate(context, clean, disambiguation)
    except Exception:  # noqa
        return text or ""


QCoreApplication.translate = safe_translate


# ============================================================
# Tiny helpers
# ============================================================


def config_exists() -> bool:
    """Return True if LGE05.conf exists."""
    return ROOT_CONF_PATH.exists()


def _msg_bad_conf_start(lang_code: str, bad_path: str) -> tuple[str, str]:
    title = fb("LGE05.msg.bad_conf.title", lang_code)
    text = (
        f"{fb('LGE05.msg.bad_conf.text_pre', lang_code)}\n\n"
        f"{fb('LGE05.msg.bad_conf.text_moved', lang_code)}\n{bad_path}\n\n"
        f"{fb('LGE05.msg.bad_conf.text_restart_finish', lang_code)}"
    )
    return title, text


def _msg_bad_conf_after_login(lang_code: str, moved_to: str) -> tuple[str, str]:
    title = fb("LGE05.msg.bad_conf.title", lang_code)
    text = (
        f"{fb('LGE05.msg.bad_conf.text_pre', lang_code)}\n\n"
        f"{fb('LGE05.msg.bad_conf.text_moved', lang_code)}\n{moved_to}\n\n"
        f"{fb('LGE05.msg.bad_conf.text_restart_reregister', lang_code)}"
    )
    return title, text


# ============================================================
# Main entry
# ============================================================


def main() -> None:
    """
    Головна функція:
        • створює QApplication,
        • створює Session + lang/strings.json (якщо треба),
        • перевіряє LGE05.conf до Splash,
        • запускає Splash,
        • після Splash — Login або Register.
    """
    app = QApplication(sys.argv)

    # Створюємо Session + порожній lang/strings.json (якщо нема)
    ensure_session_dir()

    # -------------------------------------------------------
    # Конфіг до Splash. Не можна запускати UI, якщо він битий.
    # -------------------------------------------------------
    state = check_conf_state(ROOT_CONF_PATH)
    log_cp("conf.state", state=state)

    if state in ("corrupted", "json_error", "unknown_error"):
        bad_path_obj = backup_bad_conf(ROOT_CONF_PATH)
        lang_code = _read_lang_active_default_en()

        title, msg_text = _msg_bad_conf_start(lang_code, str(bad_path_obj))
        QMessageBox.warning(None, title, msg_text)
        return

    # -------------------------------------------------------
    # Callback після Splash
    # -------------------------------------------------------
    def after_splash() -> None:
        """Викликається після завершення Splash."""
        # Немає конфігу → реєстрація
        if not config_exists():
            win = RegisterWindow()
            app.win = win  # type: ignore[attr-defined]
            win.show()
            return

        # Є конфіг → вхід
        login_win = LoginWindow()
        app.login = login_win  # type: ignore[attr-defined]
        login_win.show()

        # Обробка виключно після закриття login
        def on_login_closed() -> None:
            result = getattr(login_win, "result", None)
            log_cp("login.closed", result=result)

            if result != "bad_conf":
                return

            if ROOT_CONF_PATH.exists():
                moved_to_obj = backup_bad_conf(ROOT_CONF_PATH)
            else:
                moved_to_obj = ROOT_CONF_PATH.with_suffix(".conf.bad")

            lang_code2 = _read_lang_active_default_en()
            title2, msg_text2 = _msg_bad_conf_after_login(lang_code2, str(moved_to_obj))
            QMessageBox.warning(None, title2, msg_text2)

        login_win.destroyed.connect(on_login_closed)

    # -------------------------------------------------------
    # Запуск Splash
    # -------------------------------------------------------
    run_splash(app, after_splash)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
