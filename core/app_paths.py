# app_paths.py
"""
core/app_paths.py — шляхи застосунку.

Правило:
- У dev-режимі (з сорсів): база = корінь проєкту (поруч із папками core/, ui/, lang/…)
- У PyInstaller (onefile/onedir): база = папка, де лежить LGE.exe
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def get_base_dir() -> Path:
    """Повертає базову директорію, де мають лежати conf/session/lang."""
    if getattr(sys, "frozen", False):
        # PyInstaller: база = директорія EXE, а не _MEI...
        return Path(sys.executable).resolve().parent
    # Dev: core/app_paths.py -> core -> ROOT
    return Path(__file__).resolve().parent.parent


def get_program_data_dir() -> Path:
    """
    Повертає системну директорію ProgramData.

    На Windows:
    - зазвичай це C:\\ProgramData

    Fallback для dev/нестандартного середовища:
    - BASE_DIR / "ProgramData"
    """
    pd = os.environ.get("ProgramData", "").strip()
    if pd:
        return Path(pd).resolve()
    return (get_base_dir() / "ProgramData").resolve()


BASE_DIR = get_base_dir()
PROGRAM_DATA_DIR = get_program_data_dir()

ROOT_CONF_PATH = BASE_DIR / "LGE.conf"
SESSION_DIR = BASE_DIR / "Session"
LANG_DIR = BASE_DIR / "lang"
STRINGS_JSON = LANG_DIR / "strings.json"
ROOT_INIT_PATH = BASE_DIR / "__init__.py"


def ensure_session_dir() -> None:
    """Створює Session/ та lang/, і створює strings.json, якщо його немає."""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    LANG_DIR.mkdir(parents=True, exist_ok=True)

    if not STRINGS_JSON.exists():
        # Мінімальний коректний формат, щоб код не падав
        STRINGS_JSON.write_text(
            '{\n  "lang_active": {\n    "code": "uk"\n  }\n}\n',
            encoding="utf-8",
        )
