# LGEOffice.py
# -*- coding: utf-8 -*-
"""
LGEOffice — головний запуск (office/ самодостатній проєкт).

Потік:
Splash -> (не ініт) Init -> Login -> Main
Splash -> (ініт) Login -> Main
"""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QFile, QIODevice
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog

import office.resources_rc  # noqa: F401 <-- ОБОВ'ЯЗКОВО, якщо файл тут
from office.core.init_window_logic import InitWindow
from office.core.login_window_logic import LoginWindow
from office.core.main_window_logic import MainWindow
from office.core.splash_logic import SplashLogic
from office.ui.ui_splash_office import Ui_SplashOfficeWindow

DEBUG = False  # <-- ТУТ керуєш логами (True / False)

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.DEBUG if DEBUG else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def _apply_qss(app: QApplication) -> None:
    qss = QFile(":/office/ui/office.qss")
    if not qss.open(QIODevice.OpenModeFlag.ReadOnly):
        return

    data = qss.readAll()  # QByteArray
    app.setStyleSheet(data.data().decode("utf-8"))
    qss.close()


def main() -> int:
    setup_logging()
    logger.debug("LGEOffice start")

    app = QApplication(sys.argv)
    app.setApplicationName("LGE Office")
    app.setOrganizationName("LGE")

    app.setWindowIcon(QIcon(":/icons/LGEOffice.ico"))

    _apply_qss(app)

    splash = QDialog()
    ui = Ui_SplashOfficeWindow()
    ui.setupUi(splash)
    ui.lblStatus.setText("Перевірка ініціалізації...")

    main_holder: dict[str, object] = {}

    def open_login_real() -> None:
        w = LoginWindow()
        if w.exec() != QDialog.DialogCode.Accepted:
            return
        mw = MainWindow()
        mw.show()
        main_holder["main"] = mw

    def open_init_real() -> None:
        """
        InitWindow:
        - Accepted => Продовжити => йдемо в Login
        - Rejected => Вихід => нічого не робимо (користувач закрив)
        """
        w = InitWindow()
        if w.exec() == QDialog.DialogCode.Accepted:
            open_login_real()

    logic = SplashLogic(
        splash=splash,
        open_init_cb=open_init_real,
        open_login_cb=open_login_real,
        min_show_seconds=5,
    )
    logic.start()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
