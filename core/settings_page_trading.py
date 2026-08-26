# settings_page_trading.py
# -*- coding: utf-8 -*-
"""
SettingsPageTrading — сторінка налаштувань торгового режиму.

Призначення:
- читати поточні engine-налаштування з LGE.conf;
- показувати broker/account_mode/execution_mode;
- записувати дозволені зміни в LGE.conf;
- не підключатися до broker API;
- не створювати runtime/session logic.

Canonical engine config:

"engine": {
  "broker": "CTRADER",
  "account_mode": "DEMO",
  "execution_mode": "MANUAL"
}

LIVE дозволяється тільки для PRO/PRO+.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtWidgets import QMessageBox, QWidget

from core.ctrader_connection_dialog import (
    CTraderConnectionDialog,
)
from core.ib_connection_dialog import IBConnectionDialog
from core.lang_manager import LangManager
from core.ui_translator import UITranslator
from ui.ui_settings_page_trading import Ui_SettingsPageTrading

logger = logging.getLogger(__name__)

DEFAULT_ENGINE = {
    "broker": "OFF",
    "account_mode": "OFF",
    "execution_mode": "OFF",
}


class SettingsPageTrading(QWidget):
    """
    Сторінка торгового режиму.
    """

    def __init__(
        self,
        lang_mgr: LangManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._lang_mgr = lang_mgr
        self._snapshot: dict[str, str] = DEFAULT_ENGINE.copy()

        self.ui = Ui_SettingsPageTrading()
        self.ui.setupUi(self)

        self._translator = UITranslator(self._lang_mgr)

        self._register_i18n_keys()
        self._translator.apply(self)

        self._init_ui()
        self._load_from_conf()

        # self._update_broker_connection_status()

        self._connect_signals()

        self._set_apply_enabled(False)

    # ---------------------------------------------------------
    # Init
    # ---------------------------------------------------------
    def _init_ui(self) -> None:
        """
        Ініціалізує combobox-и торгового режиму.
        """

        # ---------------------------------------------------------
        # Broker
        # ---------------------------------------------------------
        self.ui.comboBroker.clear()

        self.ui.comboBroker.addItem(
            self._lang_mgr.tr("Common.off", "Off"),
            "OFF",
        )

        self.ui.comboBroker.addItem(
            "cTrader",
            "CTRADER",
        )

        self.ui.comboBroker.addItem(
            "Interactive Brokers",
            "IB",
        )

        # ---------------------------------------------------------
        # Account mode
        # ---------------------------------------------------------
        self.ui.comboAccountMode.clear()

        self.ui.comboAccountMode.addItem(
            self._lang_mgr.tr("Common.off", "Off"),
            "OFF",
        )

        self.ui.comboAccountMode.addItem(
            self._lang_mgr.tr("Engine.account.demo", "DEMO"),
            "DEMO",
        )

        self.ui.comboAccountMode.addItem(
            self._lang_mgr.tr("Engine.account.live", "LIVE"),
            "LIVE",
        )

        # ---------------------------------------------------------
        # Execution mode
        # ---------------------------------------------------------
        self.ui.comboExecutionMode.clear()

        self.ui.comboExecutionMode.addItem(
            self._lang_mgr.tr("Common.off", "Off"),
            "OFF",
        )

        self.ui.comboExecutionMode.addItem(
            self._lang_mgr.tr("Engine.execution.manual", "MANUAL"),
            "MANUAL",
        )

        self.ui.comboExecutionMode.addItem(
            self._lang_mgr.tr("Engine.execution.semi", "SEMI"),
            "SEMI",
        )

        self.ui.comboExecutionMode.addItem(
            self._lang_mgr.tr("Engine.execution.auto", "AUTO"),
            "AUTO",
        )

    def _connect_signals(self) -> None:
        """
        Підключає кнопки та зміни combobox.
        """
        self.ui.btnOK.clicked.connect(self._on_ok)
        self.ui.btnApply.clicked.connect(self._on_apply)
        self.ui.btnCancel.clicked.connect(self._on_cancel)

        self.ui.btnCtraderConnection.clicked.connect(self._on_ctrader_connection)
        self.ui.btnIbConnection.clicked.connect(self._on_ib_connection)

        self.ui.comboBroker.currentIndexChanged.connect(self._on_value_changed)
        self.ui.comboAccountMode.currentIndexChanged.connect(self._on_value_changed)
        self.ui.comboExecutionMode.currentIndexChanged.connect(self._on_value_changed)

    def _register_i18n_keys(self) -> None:
        """
        Реєструє LANG-ключі сторінки через canonical API.

        ВАЖЛИВО:
        fallback завжди англійський.
        """
        self._lang_mgr.tr("SettingsPageTrading.header", "Trading mode")
        self._lang_mgr.tr("SettingsPageTrading.grpBroker", "Broker")
        self._lang_mgr.tr("SettingsPageTrading.grpAccount", "Account")
        self._lang_mgr.tr("SettingsPageTrading.grpExecution", "Execution mode")

        self._lang_mgr.tr("Common.btnOK", "OK")
        self._lang_mgr.tr("Common.btnApply", "Apply")
        self._lang_mgr.tr("SettingsPageTrading.btnClose", "Close")

        self._lang_mgr.tr(
            "SettingsPageTrading.msgLiveNeedsLicense",
            "LIVE mode requires PRO or PRO+ license.",
        )
        self._lang_mgr.tr(
            "SettingsPageTrading.msgConfigUnavailable",
            "Configuration is not available.",
        )

        self._lang_mgr.tr(
            "SettingsPageTrading.grpConnection",
            "Broker connection",
        )
        self._lang_mgr.tr(
            "SettingsPageTrading.lblCtraderConnectionStatus",
            "cTrader connection",
        )
        self._lang_mgr.tr(
            "SettingsPageTrading.lblIBConnectionStatus",
            "IB connection",
        )

        self._lang_mgr.tr(
            "SettingsPageTrading.btnCtraderConnection",
            "cTrader connection settings",
        )
        self._lang_mgr.tr(
            "SettingsPageTrading.btnIbConnection",
            "IB connection settings",
        )
        self._lang_mgr.tr(
            "SettingsPageTrading.msgCtraderConnectionStub",
            "cTrader connection dialog is not implemented yet.",
        )
        self._lang_mgr.tr(
            "SettingsPageTrading.msgIbConnectionStub",
            "IB connection dialog is not implemented yet.",
        )

    # ---------------------------------------------------------
    # Config load/save
    # ---------------------------------------------------------
    def _load_from_conf(self) -> None:
        """
        Читає engine-налаштування з LGE.conf.

        Якщо engine ще немає — показує дефолтні значення,
        але фізично conf тут не записує.
        """
        values = self._read_engine_values()

        self._set_combo_by_data(self.ui.comboBroker, values["broker"])
        self._set_combo_by_data(
            self.ui.comboAccountMode,
            values["account_mode"],
        )
        self._set_combo_by_data(
            self.ui.comboExecutionMode,
            values["execution_mode"],
        )

        self._snapshot = self.current_values()
        logger.debug("Trading settings loaded: %s", self._snapshot)

    def _read_engine_values(self) -> dict[str, str]:
        """
        Повертає engine-значення з CURRENT_CONFIG або дефолт.
        """
        try:
            from core import session_state

            conf_obj = session_state.CURRENT_CONFIG
            if conf_obj is None:
                return DEFAULT_ENGINE.copy()

            broker = self._normalize_broker(
                conf_obj.get("engine", "broker", DEFAULT_ENGINE["broker"])
            )
            account_mode = self._normalize_account_mode(
                conf_obj.get(
                    "engine",
                    "account_mode",
                    DEFAULT_ENGINE["account_mode"],
                )
            )
            execution_mode = self._normalize_execution_mode(
                conf_obj.get(
                    "engine",
                    "execution_mode",
                    DEFAULT_ENGINE["execution_mode"],
                )
            )

            return {
                "broker": broker,
                "account_mode": account_mode,
                "execution_mode": execution_mode,
            }
        except Exception:  # noqa
            logger.exception("Failed to read engine config")
            return DEFAULT_ENGINE.copy()

    def _save_to_conf(self, values: dict[str, str]) -> bool:
        """
        Записує engine-налаштування в LGE.conf.
        """
        try:
            from core import session_state
            from core.app_paths import ROOT_CONF_PATH
            from core.config_manager import ConfigManager

            if (
                session_state.CURRENT_CONFIG is None
                or session_state.CURRENT_PASSWORD is None
            ):
                self._show_warning(
                    self._lang_mgr.tr(
                        "SettingsPageTrading.msgConfigUnavailable",
                        "Configuration is not available.",
                    )
                )
                return False

            conf_obj = session_state.CURRENT_CONFIG
            password = session_state.CURRENT_PASSWORD

            conf_obj.set("engine", "broker", values["broker"])
            conf_obj.set("engine", "account_mode", values["account_mode"])
            conf_obj.set("engine", "execution_mode", values["execution_mode"])

            ConfigManager(ROOT_CONF_PATH).save(conf_obj.to_dict(), password)

            logger.info("Trading settings saved: %s", values)
            return True

        except Exception:  # noqa
            logger.exception("Failed to save trading settings")
            self._show_warning(
                self._lang_mgr.tr(
                    "SettingsPageTrading.msgConfigUnavailable",
                    "Configuration is not available.",
                )
            )
            return False

    # ---------------------------------------------------------
    # Values
    # ---------------------------------------------------------
    def current_values(self) -> dict[str, str]:
        """
        Повертає поточні значення сторінки.
        """
        return {
            "broker": self._normalize_broker(self.ui.comboBroker.currentData()),
            "account_mode": self._normalize_account_mode(
                self.ui.comboAccountMode.currentData()
            ),
            "execution_mode": self._normalize_execution_mode(
                self.ui.comboExecutionMode.currentData()
            ),
        }

    def restore_snapshot(self) -> None:
        """
        Повертає значення UI до останнього збереженого стану.
        """
        self._block_combo_signals(True)
        try:
            self._set_combo_by_data(
                self.ui.comboBroker,
                self._snapshot.get("broker", DEFAULT_ENGINE["broker"]),
            )
            self._set_combo_by_data(
                self.ui.comboAccountMode,
                self._snapshot.get(
                    "account_mode",
                    DEFAULT_ENGINE["account_mode"],
                ),
            )
            self._set_combo_by_data(
                self.ui.comboExecutionMode,
                self._snapshot.get(
                    "execution_mode",
                    DEFAULT_ENGINE["execution_mode"],
                ),
            )
        finally:
            self._block_combo_signals(False)

        self._set_apply_enabled(False)

    # ---------------------------------------------------------
    # Button handlers
    # ---------------------------------------------------------
    def _on_apply(self) -> None:
        """
        Apply:
        - перевіряє дозвіл;
        - записує зміни в LGE.conf;
        - лишає вікно відкритим.
        """
        if self._apply_changes():
            self._set_apply_enabled(False)

    def _on_ok(self) -> None:
        """
        OK:
        - те саме що Apply;
        - після успішного запису закриває Settings.
        """
        if self._apply_changes():
            self._close_settings_window()

    def _on_cancel(self) -> None:
        """
        Close:
        - нічого не записує;
        - відновлює snapshot;
        - закриває Settings.
        """
        self.restore_snapshot()
        self._close_settings_window()

    def _apply_changes(self) -> bool:
        """
        Центральна логіка застосування змін.
        """
        values = self.current_values()

        if values["account_mode"] == "LIVE" and not self._live_allowed():
            self._show_warning(
                self._lang_mgr.tr(
                    "SettingsPageTrading.msgLiveNeedsLicense",
                    "LIVE mode requires PRO or PRO+ license.",
                )
            )

            self._set_combo_by_data(self.ui.comboAccountMode, "DEMO")

            return False

        if not self._save_to_conf(values):
            return False

        self._snapshot = values.copy()
        self._notify_main_window()
        return True

    def _on_value_changed(self, *_args: Any) -> None:
        """
        Вмикає Apply, якщо поточні значення відрізняються від snapshot.
        """
        changed = self.current_values() != self._snapshot
        self._set_apply_enabled(changed)

    def _update_broker_connection_status(self) -> None:
        """
        Оновлює статус broker-з'єднання на сторінці.
        """
        self.ui.lblBrokerConnectionStatus.setText(
            self._lang_mgr.tr(
                "SettingsPageTrading.statusSafeDisconnected",
                "SAFE_DISCONNECTED",
            )
        )

    def _on_ctrader_connection(self) -> None:
        """
        Відкрити діалог налаштування cTrader.
        """
        dialog = CTraderConnectionDialog(self)
        dialog.exec()

    def _on_ib_connection(self) -> None:
        """
        Відкрити діалог налаштування IB через RuntimeEngine.
        """
        dialog = IBConnectionDialog(self)
        dialog.exec()

    # ---------------------------------------------------------
    # License rules
    # ---------------------------------------------------------
    def _live_allowed(self) -> bool:  # noqa
        """
        LIVE дозволений тільки для PRO/PRO+.
        """
        try:
            from core import session_state

            conf_obj = session_state.CURRENT_CONFIG
            if conf_obj is None:
                return False

            conf = conf_obj.to_dict()
            lic = conf.get("license")
            if not isinstance(lic, dict):
                return False

            edition = str(lic.get("edition") or "").strip().lower()
            status = str(lic.get("status") or "").strip().upper()

            if edition in ("pro", "pro_plus"):
                return True

            return status == "PRO_OK"

        except Exception:  # noqa
            logger.exception("Failed to check LIVE permission")
            return False

    def snapshot(self) -> None:
        """
        Заглушка для сумісності з SettingsCenter при зміні мови.
        """
        return

    # ---------------------------------------------------------
    # UI helpers
    # ---------------------------------------------------------
    def _set_apply_enabled(self, value: bool) -> None:
        """
        Керує тільки Apply.

        Close завжди активний, бо це вихід без змін.
        OK завжди активний, бо може застосувати поточний стан.
        """
        self.ui.btnApply.setEnabled(value)
        self.ui.btnCancel.setEnabled(True)
        self.ui.btnOK.setEnabled(True)

    def _show_warning(self, message: str) -> None:
        """
        Показує попередження.
        """
        QMessageBox.warning(
            self,
            self._lang_mgr.tr("SettingsPageTrading.warningTitle", "Warning"),
            message,
        )

    def _close_settings_window(self) -> None:
        """
        Закриває Settings dialog.
        """
        window = self.window()
        if window is not None and window is not self:
            window.close()

    def _notify_main_window(self) -> None:
        """
        Повідомляє головне вікно, якщо воно підтримує оновлення статусу.
        """
        window = self.window()
        parent = window.parent() if window is not None else None

        if parent is not None and hasattr(parent, "update_statusbar"):
            try:
                parent.update_statusbar()
            except Exception:  # noqa
                logger.exception("Failed to update main window statusbar")

    def _block_combo_signals(self, value: bool) -> None:
        """
        Блокує сигнали combobox під час програмного відновлення.
        """
        self.ui.comboBroker.blockSignals(value)
        self.ui.comboAccountMode.blockSignals(value)
        self.ui.comboExecutionMode.blockSignals(value)

    @staticmethod
    def _set_combo_by_data(combo, value: str) -> None:
        """
        Встановлює combobox за userData.
        """
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    @staticmethod
    def _normalize_broker(value: Any) -> str:
        """
        Нормалізує broker.
        """
        text = str(value or "").strip().upper()
        if text in ("IB", "CTRADER"):
            return text
        return DEFAULT_ENGINE["broker"]

    @staticmethod
    def _normalize_account_mode(value: Any) -> str:
        """
        Нормалізує account_mode.
        """
        text = str(value or "").strip().upper()
        if text in ("DEMO", "LIVE"):
            return text
        return DEFAULT_ENGINE["account_mode"]

    @staticmethod
    def _normalize_execution_mode(value: Any) -> str:
        """
        Нормалізує execution_mode.
        """
        text = str(value or "").strip().upper()
        if text in ("MANUAL", "SEMI", "AUTO"):
            return text
        return DEFAULT_ENGINE["execution_mode"]
