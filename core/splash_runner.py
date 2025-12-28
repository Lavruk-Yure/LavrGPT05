# core/splash_runner.py
"""
SplashWindow — стартовий екран LGE05 (Patch 8.2 SR Edition).

Функції:
    • показує Splash;
    • застосовує переклад (UITranslator);
    • виконує послідовність кроків;
    • після завершення викликає callback.

Особливості Patch 8.2 SR:
    • чиста структура;
    • докстрінги у SR-формі;
    • контрольні точки check_point();
    • 100% сумісність із LangManager та LGE05.py.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMainWindow

from core.lang_manager import LANG
from core.ui_translator import UITranslator
from ui.ui_splash import Ui_MainWindow as UiSplash

# -------------------------------------------------------------
# Debug flags
# -------------------------------------------------------------
DEBUG_SPLASH = False


def check_point(name: str, **kw: Any) -> None:
    """
    Контрольна точка.
    Використовується для діагностики послідовності кроків Splash.
    """
    if not DEBUG_SPLASH:
        return

    parts = ", ".join(f"{k}={v}" for k, v in kw.items())
    print(f"[SPLASH_CP:{name}] {parts}")


# -------------------------------------------------------------
# SplashWindow
# -------------------------------------------------------------
class SplashWindow(QMainWindow):
    """
    Вікно Splash (заставка) із прогрес-баром.

    Виклик:
        splash = SplashWindow(lang_mgr)
        splash.start(on_done)

    Послідовність:
        1. apply translator
        2. setup steps
        3. запуск таймера
        4. виконання кроків
        5. виклик callback
    """

    def __init__(self) -> None:
        """
        Створення Splash-вікна.
        """
        super().__init__()

        self._lang_mgr = LANG
        self.ui = UiSplash()
        self.ui.setupUi(self)

        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)  # noqa

        self._translator = UITranslator(LANG)
        self._steps: list[tuple[str, Callable[[], None]]] = []
        self._progress_idx = 0
        self._timer = QTimer(self)
        self._on_done: Callable[[], None] | None = None

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------
    def start(self, on_done: Callable[[], None]) -> None:
        """
        Запускає переклад, кроки та таймер.

        :param on_done: callback після завершення.
        """
        check_point("start_begin")

        self._translator.apply(self)
        check_point("after_translator")

        self._setup_steps()
        check_point("steps_ready", count=len(self._steps))

        self._start_timer(on_done)

    # ---------------------------------------------------------
    # Steps setup
    # ---------------------------------------------------------
    def _setup_steps(self) -> None:
        """Створює послідовність кроків."""
        self._steps = [
            ("Splash.check_dirs", self._check_dirs),
            ("Splash.init_env", self._init_env),
            ("Splash.check_conf", self._check_conf),
            ("Splash.prep_ui", self._prep_ui),
        ]
        self._progress_idx = 0

    # ---------------------------------------------------------
    # Timer / Tick
    # ---------------------------------------------------------
    def _start_timer(self, on_done: Callable[[], None]) -> None:
        """
        Запускає таймер виконання кроків.

        :param on_done: callback після завершення.
        """
        self._on_done = on_done

        def tick() -> None:
            check_point("tick", idx=self._progress_idx)

            if self._progress_idx >= len(self._steps):
                done_text = self._lang_mgr.resolve("Splash.done") or "Done"
                self._set_progress(100, done_text)

                self._timer.stop()
                on_done()
                self.close()  # ← ОБОВ’ЯЗКОВО
                return

            key, fn = self._steps[self._progress_idx]
            text = self._lang_mgr.resolve(key) or key
            percent = int((self._progress_idx / len(self._steps)) * 100)

            self._set_progress(percent, text)

            try:
                fn()
            finally:
                self._progress_idx += 1

        self._timer.timeout.connect(tick)
        self._timer.start(350)

    # ---------------------------------------------------------
    # Step functions
    # ---------------------------------------------------------
    @staticmethod
    def _check_dirs() -> None:
        """Крок: перевірка каталогів."""
        check_point("step_dirs")

    @staticmethod
    def _init_env() -> None:
        """Крок: ініціалізація середовища."""
        check_point("step_init")

    @staticmethod
    def _check_conf() -> None:
        """Крок: перевірка конфігу."""
        check_point("step_conf")

    @staticmethod
    def _prep_ui() -> None:
        """Крок: підготовка інтерфейсу."""
        check_point("step_ui")

    # ---------------------------------------------------------
    # Progress update
    # ---------------------------------------------------------
    def _set_progress(self, value: int, text: str) -> None:
        """
        Оновлює прогрес-бар і статус.

        :param value: 0..100
        :param text: рядок статусу
        """
        try:
            self.ui.progressBar.setValue(value)
            self.ui.lblStatus.setText(text)
        except Exception:  # noqa
            pass


# -------------------------------------------------------------
# Public function for LGE05.py
# -------------------------------------------------------------
def run_splash(app, on_done: Callable[[], None]) -> None:
    """
    Запускає SplashWindow.

    Виклик із LGE05.py:
        run_splash(app, after_splash)
    """
    splash = SplashWindow()

    app.splash = splash  # для відлагодження
    splash.show()
    splash.start(on_done)
