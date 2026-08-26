# LGE.py
# runtime_broker_health.py
# -*- coding: utf-8 -*-
"""
LGE — точка входу (Patch 9.1 + QSS fix).

Важливе:
- На старті ще немає повного UI-стека,
  тому повідомлення про битий conf показуємо через common dialogs.
  беремо з ресурсу lang/strings_fallback.json
  (Qt resource: :/lang/strings_fallback.json).
- Мову беремо з lang/strings.json -> {"lang_active":{"code":"uk"}}
  Якщо файла нема / JSON битий — fallback 'en'.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from typing import Any, Dict

from PySide6.QtCore import QCoreApplication, QFile, QIODevice, QProcess
from PySide6.QtWidgets import QApplication

import resources_rc  # noqa: F401
from core.app_paths import BASE_DIR, ROOT_CONF_PATH, STRINGS_JSON, ensure_session_dir
from core.common_dialogs import CommonErrorDialog
from core.conf_guard import backup_bad_conf, check_conf_state
from core.lang_manager import LangManager
from core.login_logic import LoginWindow
from core.register_logic import RegisterWindow
from core.splash_runner import run_splash

DEBUG_LGE = False


def _apply_qss(app: QApplication) -> None:
    f = QFile(":/ui/common_dialogs.qss")
    if not f.open(QIODevice.OpenModeFlag.ReadOnly):
        return
    try:
        qba = f.readAll()  # QByteArray
        raw: bytes = qba.data()  # <- ключове: тип bytes
        qss = raw.decode("utf-8", errors="replace")
        if qss.strip():
            app.setStyleSheet(qss)
    finally:
        f.close()


def log_cp(name: str, **kw: Any) -> None:
    """Локальний debug-логер LGE."""
    if not DEBUG_LGE:
        return
    msg = f"[LGE:{name}] " + ", ".join(f"{k}={v!r}" for k, v in kw.items())
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

        try:
            qba = f.readAll()  # QByteArray
            raw: bytes = qba.data()  # bytes
            text = raw.decode("utf-8", errors="replace")
        finally:
            f.close()

        data = json.loads(text or "{}")
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
    """Return True if LGE.conf exists."""
    return ROOT_CONF_PATH.exists()


def shutdown_top_level_windows(app: QApplication) -> None:
    """Run controlled shutdown for active LGE top-level windows."""
    for widget in tuple(app.topLevelWidgets()):
        shutdown = getattr(widget, "shutdown_application", None)
        if callable(shutdown):
            shutdown()


def _msg_bad_conf_start(lang_code: str, bad_path: str) -> tuple[str, str]:
    title = fb("LGE.msg.bad_conf.title", lang_code)
    text = (
        f"{fb('LGE.msg.bad_conf.text_pre', lang_code)}\n\n"
        f"{fb('LGE.msg.bad_conf.text_moved', lang_code)}\n{bad_path}\n\n"
        f"{fb('LGE.msg.bad_conf.text_restart_finish', lang_code)}"
    )
    return title, text


def _msg_bad_conf_after_login(lang_code: str, moved_to: str) -> tuple[str, str]:
    title = fb("LGE.msg.bad_conf.title", lang_code)
    text = (
        f"{fb('LGE.msg.bad_conf.text_pre', lang_code)}\n\n"
        f"{fb('LGE.msg.bad_conf.text_moved', lang_code)}\n{moved_to}\n\n"
        f"{fb('LGE.msg.bad_conf.text_restart_reregister', lang_code)}"
    )
    return title, text


def _split_header_details(text: str) -> tuple[str, str]:
    """
    Розбиває багаторядковий текст на (header, details) для Common dialogs.

    Логіка:
    - header: перший абзац (до першого порожнього рядка)
    - details: решта, без зайвих пробілів/порожніх рядків на початку
    """
    raw = (text or "").strip()
    if not raw:
        return "", ""

    parts = re.split(r"\n\s*\n", raw, maxsplit=1)
    header = parts[0].strip()
    details = parts[1].strip() if len(parts) > 1 else ""
    return header, details


# ============================================================
# Main entry
# ============================================================


def main() -> None:
    """
    Головна функція:
        • створює QApplication,
        • підключає QSS для common dialogs,
        • створює Session + lang/strings.json (якщо треба),
        • перевіряє LGE.conf до Splash,
        • запускає Splash,
        • після Splash — Login або Register.
    """
    app = QApplication(sys.argv)
    _apply_qss(app)
    app.aboutToQuit.connect(lambda: shutdown_top_level_windows(app))

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
        header, details = _split_header_details(msg_text)
        CommonErrorDialog.show_dialog(
            None,
            LangManager(),
            title=title,
            header=header,
            details=details,
        )
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
            header2, details2 = _split_header_details(msg_text2)
            CommonErrorDialog.show_dialog(
                None,
                LangManager(),
                title=title2,
                header=header2,
                details=details2,
            )

        login_win.destroyed.connect(on_login_closed)

    # -------------------------------------------------------
    # Запуск Splash
    # -------------------------------------------------------
    run_splash(app, after_splash)
    exit_code = app.exec()
    if bool(app.property("lge_restart_requested")):
        QProcess.startDetached(
            sys.executable,
            [str(BASE_DIR / "LGE.py"), *sys.argv[1:]],
            str(BASE_DIR),
        )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
