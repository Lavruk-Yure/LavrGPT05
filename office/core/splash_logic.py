# splash_logic.py
# -*- coding: utf-8 -*-
"""
splash_logic — логіка Splash для LGEOffice.

Потік:
Splash -> перевірка ініціалізації -> Init або Login.
"""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog

from office.core.init_state import check_initialized
from office.core.office_paths import get_config_path

logger = logging.getLogger(__name__)


class SplashLogic:
    def __init__(
        self,
        splash: QDialog,
        open_init_cb,
        open_login_cb,
        min_show_seconds: int = 5,  # <-- ТУТ
    ) -> None:
        self._splash = splash
        self._open_init_cb = open_init_cb
        self._open_login_cb = open_login_cb
        self._min_show_ms = min_show_seconds * 1000
        self._start_ts: float | None = None

    def start(self) -> None:
        logger.debug("Splash: show()")
        self._start_ts = time.monotonic()
        self._splash.show()

        # Перевірку робимо одразу
        QTimer.singleShot(0, self._route)

    def _route(self) -> None:
        cfg = get_config_path()
        state = check_initialized(cfg)
        logger.debug("Splash: init_state=%s (%s)", state.initialized, state.reason)

        # рахуємо, скільки ще тримати splash
        elapsed_ms = int((time.monotonic() - self._start_ts) * 1000)
        delay_ms = max(0, self._min_show_ms - elapsed_ms)

        QTimer.singleShot(delay_ms, lambda: self._finish(state.initialized))

    def _finish(self, initialized: bool) -> None:
        logger.debug("Splash: close()")
        self._splash.close()

        if initialized:
            self._open_login_cb()
        else:
            self._open_init_cb()
