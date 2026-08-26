# file_lock.py
# -*- coding: utf-8 -*-
"""
file_lock — перевірка, чи файл відкритий іншою програмою (Windows).

Patch 29.2 fix:
- msvcrt.locking НЕ ловить Notepad (advisory lock).
- Тому використовуємо WinAPI CreateFileW з dwShareMode=0
  і ловимо ERROR_SHARING_VIOLATION / ERROR_LOCK_VIOLATION.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_IS_WINDOWS = os.name == "nt"

if _IS_WINDOWS:
    import ctypes  # noqa: WPS433
    from ctypes import wintypes  # noqa: WPS433

    # WinAPI constants
    GENERIC_READ: int = 0x80000000
    FILE_SHARE_NONE: int = 0x00000000
    OPEN_EXISTING: int = 3
    FILE_ATTRIBUTE_NORMAL: int = 0x00000080
    INVALID_HANDLE_VALUE: int = wintypes.HANDLE(-1).value

    ERROR_SHARING_VIOLATION: int = 32
    ERROR_LOCK_VIOLATION: int = 33

    KERNEL32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    CreateFileW = KERNEL32.CreateFileW  # noqa
    CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    CreateFileW.restype = wintypes.HANDLE

    CloseHandle = KERNEL32.CloseHandle  # noqa
    CloseHandle.argtypes = [wintypes.HANDLE]
    CloseHandle.restype = wintypes.BOOL


def is_file_locked(path: Path) -> bool:
    """
    True, якщо файл відкритий/зайнятий іншою програмою (Windows).
    На інших ОС повертає False (не гарантуємо однакову семантику).
    """
    p = Path(path)

    if not p.exists() or not p.is_file():
        logger.warning("is_file_locked: file not found: %s", p)
        return False

    if not _IS_WINDOWS:
        return False

    return _is_file_locked_windows(p)


def _is_file_locked_windows(path: Path) -> bool:
    handle = CreateFileW(
        str(path),
        GENERIC_READ,
        FILE_SHARE_NONE,  # ключ: ексклюзивний доступ
        None,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        None,
    )

    if handle == INVALID_HANDLE_VALUE:
        err = ctypes.GetLastError()
        if err in (ERROR_SHARING_VIOLATION, ERROR_LOCK_VIOLATION):
            return True

        # інші помилки трактуємо як "зайнятий/недоступний"
        logger.warning("CreateFileW failed for %s, err=%s", path, err)
        return True

    CloseHandle(handle)
    return False
