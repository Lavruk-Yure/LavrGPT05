# ib_connection_dialog.py
"""
Діалог підключення Interactive Brokers через RuntimeEngine.

RoadMap76:
- перший GUI -> RuntimeEngine міст для IB;
- без прямого доступу UI до IBAdapter;
- UI працює тільки через RuntimeEngine + IBRuntimeService.
"""

from __future__ import annotations

import logging
from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox

from core.app_paths import ROOT_CONF_PATH
from core.config_manager import ConfigManager
from core.lang_manager import LangManager
from engine.runtime_engine import RuntimeEngine
from engine.services.ib_runtime_service import IBRuntimeService
from ui.ui_ib_connection_dialog import Ui_IBConnectionDialog

logger = logging.getLogger(__name__)


class IBConnectionDialog(QDialog):
    """
    Діалог підключення IB через RuntimeEngine.
    """

    def __init__(
        self,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self._lang_mgr = LangManager()
        self._runtime_engine = self._get_runtime_engine()

        self.ui = Ui_IBConnectionDialog()
        self.ui.setupUi(self)

        self._retranslate_ui()

        self._init_values()
        self._connect_signals()
        self._refresh_status()
        self._update_buttons_state()

    def _init_values(self) -> None:
        """
        Заповнити перші runtime-значення IB.

        RoadMap76:
        поки DEMO/PAPER через TWS 127.0.0.1:7497.
        """
        self.ui.editHost.setText("127.0.0.1")
        self.ui.editHost.setReadOnly(True)

        self.ui.spinPort.setValue(7497)
        self.ui.spinPort.setReadOnly(True)

        self.ui.spinClientId.setValue(1)
        self.ui.spinClientId.setReadOnly(True)

        for button in (
            self.ui.btnRefresh,
            self.ui.btnConnect,
            self.ui.btnDisconnect,
            self.ui.btnOk,
            self.ui.btnCancel,
        ):
            button.setDefault(False)
            button.setAutoDefault(False)

        self.ui.btnConnect.setDefault(True)
        self.ui.btnConnect.setAutoDefault(True)
        self.ui.btnConnect.setFocus()

        self.ui.lblHealthValue.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.ui.lblAccountValue.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

    def _connect_signals(self) -> None:
        """
        Підключити кнопки.
        """
        self.ui.btnConnect.clicked.connect(self._on_connect)
        self.ui.btnDisconnect.clicked.connect(self._on_disconnect)
        self.ui.btnRefresh.clicked.connect(self._on_refresh_clicked)
        self.ui.btnOk.clicked.connect(self.accept)
        self.ui.btnCancel.clicked.connect(self.reject)
        self.ui.comboAccounts.currentIndexChanged.connect(self._on_account_changed)

    @staticmethod
    def _get_runtime_engine() -> RuntimeEngine:
        """
        Отримати shared RuntimeEngine, створений MainAppWindow.

        RoadMap78: діалог IB не створює RuntimeEngine самостійно.
        """
        from core import session_state

        runtime_engine = getattr(session_state, "CURRENT_RUNTIME_ENGINE", None)

        if runtime_engine is None:
            raise RuntimeError("CURRENT_RUNTIME_ENGINE is not initialized.")

        return runtime_engine

    def _on_connect(self) -> None:
        """
        Підключити IB DEMO/PAPER через RuntimeEngine.
        """
        self.ui.btnConnect.setEnabled(False)
        self.ui.btnRefresh.setEnabled(False)

        try:
            ok = self._runtime_engine.connect_ib_demo()
            self._refresh_status()
            self._update_buttons_state()
            self._refresh_accounts_combo()

            if ok:
                selected_account_id = self.ui.comboAccounts.currentData()
                self._save_ib_runtime_config(
                    account_id=str(selected_account_id) if selected_account_id else None
                )

                self._set_ib_auto_connect(True)

                QMessageBox.information(
                    self,
                    self._lang_mgr.tr("IBConnectionDialog.title", "IB"),
                    self._lang_mgr.tr(
                        "IBConnectionDialog.msgConnected",
                        "IB connected successfully.",
                    ),
                )
                return

            QMessageBox.warning(
                self,
                self._lang_mgr.tr("IBConnectionDialog.title", "IB"),
                self._lang_mgr.tr(
                    "IBConnectionDialog.msgConnectionFailed",
                    (
                        "IB connection failed. Check that TWS / IB Gateway "
                        "is running, API socket clients are enabled, "
                        "and the port is 7497 for Paper or 7496 for Live."
                    ),
                ),
            )

        except Exception as exc:  # noqa: BLE001
            logger.exception("IB RuntimeEngine connect failed.")
            QMessageBox.warning(
                self,
                self._lang_mgr.tr("IBConnectionDialog.title", "IB"),
                str(exc),
            )
        finally:
            self.ui.btnRefresh.setEnabled(True)
            self._refresh_status()

            self._update_buttons_state()

    def _on_disconnect(self) -> None:
        """
        Відключити IB runtime service.
        """
        service = self._runtime_engine.ib_runtime_service

        if service is not None:
            service.disconnect()

        self._set_ib_auto_connect(False)

        self._refresh_status()

        self._update_buttons_state()

        QMessageBox.information(
            self,
            self._lang_mgr.tr("IBConnectionDialog.title", "IB"),
            self._lang_mgr.tr(
                "IBConnectionDialog.msgDisconnected",
                "IB disconnected.",
            ),
        )

    def _on_refresh_clicked(self) -> None:
        """
        Оновити IB статус з видимою реакцією для користувача.
        """
        self._refresh_status()
        self._update_buttons_state()

        QMessageBox.information(
            self,
            self._lang_mgr.tr("IBConnectionDialog.title", "IB"),
            self._lang_mgr.tr(
                "IBConnectionDialog.msgStatusRefreshed",
                "IB status refreshed.",
            ),
        )

    def _refresh_status(self) -> None:
        """
        Оновити BrokerHealth та RuntimeAccountState.
        """
        service = self._runtime_engine.ib_runtime_service

        if service is None:
            self.ui.lblHealthValue.setText("IBRuntimeService: NONE")
            self.ui.lblAccountValue.setText("-")
            self._update_buttons_state()
            return

        ib_service = cast(IBRuntimeService, service)

        health = ib_service.refresh_broker_health()
        account = ib_service.get_account_state()

        self.ui.lblHealthValue.setText(
            self._health_text(health.state, health.last_error)
        )

        if not account.is_loaded():
            self.ui.lblAccountValue.setText("-")
            self._update_buttons_state()
            self._refresh_accounts_combo()
            return

        self.ui.lblAccountValue.setText(
            (
                f"{account.account_id} | "
                f"{account.currency} | "
                f"{self._lang_mgr.tr('RuntimeAccount.balance', 'Balance')}: "
                f"{account.balance} | "
                f"{self._lang_mgr.tr('RuntimeAccount.equity', 'Equity')}: "
                f"{account.equity} | "
                f"{self._lang_mgr.tr('RuntimeAccount.freeMargin', 'Free margin')}: "
                f"{account.free_margin}"
            )
        )

        self._update_buttons_state()

        self._refresh_accounts_combo()

    def _update_buttons_state(self) -> None:
        """
        Оновити доступність кнопок відповідно до broker health.
        """
        service = self._runtime_engine.ib_runtime_service

        if service is None:
            self.ui.btnConnect.setEnabled(True)
            self.ui.btnDisconnect.setEnabled(False)
            return

        health = service.get_broker_health()
        state = str(getattr(health, "state", "UNKNOWN"))

        if state == "CONNECTED":
            self.ui.btnConnect.setEnabled(False)
            self.ui.btnDisconnect.setEnabled(True)
            return

        if state in {"CONNECTING", "RECONNECTING"}:
            self.ui.btnConnect.setEnabled(False)
            self.ui.btnDisconnect.setEnabled(False)
            return

        self.ui.btnConnect.setEnabled(True)
        self.ui.btnDisconnect.setEnabled(False)
        self._refresh_buttons_visual_state()

    def _refresh_buttons_visual_state(self) -> None:
        """
        Примусово перемалювати кнопки після зміни enabled/disabled.
        """
        for button in (
            self.ui.btnRefresh,
            self.ui.btnConnect,
            self.ui.btnDisconnect,
            self.ui.btnOk,
            self.ui.btnCancel,
        ):
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def _save_ib_runtime_config(
        self,
        account_id: str | None = None,
    ) -> None:
        """
        Зберегти IB runtime connection settings у LGE.conf.

        УВАГА:
        це не runtime health. Це тільки остання відома конфігурація,
        щоб LGE знав, до якого broker/account підключатися.
        """
        from core import session_state

        conf_obj = session_state.CURRENT_CONFIG
        password = session_state.CURRENT_PASSWORD

        if conf_obj is None or password is None:
            logger.warning("Cannot save IB runtime config: config is unavailable.")
            return

        account = None
        service = self._runtime_engine.ib_runtime_service
        if service is not None:
            ib_service = cast(IBRuntimeService, service)
            account = ib_service.get_account_state()

        if account_id is None:
            account_id = None

            if account is not None and account.is_loaded():
                account_id = str(account.account_id)

        conf_obj.set("engine", "broker", "IB")
        conf_obj.set("engine", "account_mode", "DEMO")
        conf_obj.set(
            "engine",
            "ib",
            {
                "host": self.ui.editHost.text().strip(),
                "port": int(self.ui.spinPort.value()),
                "client_id": int(self.ui.spinClientId.value()),
                "account_id": account_id,
            },
        )

        ConfigManager(ROOT_CONF_PATH).save(conf_obj.to_dict(), password)
        logger.info("IB runtime config saved.")

    def _set_ib_auto_connect(  # noqa
        self,
        enabled: bool,
    ) -> None:
        """
        Зберегти намір автопідключення IB у LGE.conf.
        """
        from core import session_state

        conf_obj = session_state.CURRENT_CONFIG
        password = session_state.CURRENT_PASSWORD

        if conf_obj is None or password is None:
            logger.warning(
                "Cannot save IB auto_connect: config is unavailable.",
            )
            return

        conf = conf_obj.to_dict()
        engine = conf.setdefault("engine", {})
        auto_connect = engine.setdefault("auto_connect", {})

        auto_connect["ib"] = bool(enabled)

        ConfigManager(ROOT_CONF_PATH).save(conf, password)
        logger.info("IB auto_connect saved: %s", enabled)

    def _health_text(self, state: str, last_error: str = "") -> str:
        """
        Повернути користувацький текст broker health.
        """
        labels = {
            "CONNECTED": self._lang_mgr.tr(
                "BrokerHealth.CONNECTED",
                "Connected",
            ),
            "DISCONNECTED": self._lang_mgr.tr(
                "BrokerHealth.DISCONNECTED",
                "Disconnected",
            ),
            "SAFE_DISCONNECTED": self._lang_mgr.tr(
                "BrokerHealth.SAFE_DISCONNECTED",
                "Safe disconnected",
            ),
            "RECONNECTING": self._lang_mgr.tr(
                "BrokerHealth.RECONNECTING",
                "Reconnecting",
            ),
            "ERROR": self._lang_mgr.tr(
                "BrokerHealth.ERROR",
                "Error",
            ),
            "UNKNOWN": self._lang_mgr.tr(
                "BrokerHealth.UNKNOWN",
                "Unknown",
            ),
        }

        text = labels.get(state, state)

        if last_error and state not in {"DISCONNECTED"}:
            text = f"{text} | {last_error}"

        return text

    def _retranslate_ui(self) -> None:
        """
        Перекласти тексти IBConnectionDialog після setupUi().
        """
        self.setWindowTitle(
            self._lang_mgr.tr(
                "IBConnectionDialog.title",
                "Interactive Brokers connection",
            )
        )
        self.ui.lblHelp.setText(
            self._lang_mgr.tr(
                "IBConnectionDialog.lblHelp",
                (
                    "Start TWS or IB Gateway first. "
                    "For Paper/DEMO TWS use port 7497. "
                    "For LIVE TWS use port 7496."
                ),
            )
        )
        self.ui.lblHost.setText(self._lang_mgr.tr("IBConnectionDialog.lblHost", "Host"))
        self.ui.lblPort.setText(self._lang_mgr.tr("IBConnectionDialog.lblPort", "Port"))
        self.ui.lblClientId.setText(
            self._lang_mgr.tr("IBConnectionDialog.lblClientId", "Client ID")
        )
        self.ui.lblSelectedAccount.setText(
            self._lang_mgr.tr(
                "IBConnectionDialog.lblSelectedAccount",
                "Selected account",
            )
        )
        self.ui.lblHealth.setText(
            self._lang_mgr.tr("IBConnectionDialog.lblHealth", "Broker health")
        )
        self.ui.lblAccount.setText(
            self._lang_mgr.tr("IBConnectionDialog.lblAccount", "Account")
        )
        self.ui.btnConnect.setText(
            self._lang_mgr.tr("IBConnectionDialog.btnConnect", "Connect")
        )
        self.ui.btnDisconnect.setText(
            self._lang_mgr.tr("IBConnectionDialog.btnDisconnect", "Disconnect")
        )
        self.ui.btnRefresh.setText(
            self._lang_mgr.tr("IBConnectionDialog.btnRefresh", "Refresh status")
        )
        self.ui.btnOk.setText(self._lang_mgr.tr("Common.btnOK", "OK"))
        self.ui.btnCancel.setText(
            self._lang_mgr.tr(
                "IBConnectionDialog.btnClose",
                "Close",
            )
        )

    def _refresh_accounts_combo(self) -> None:
        """
        Оновити список IB accounts у comboAccounts.
        """
        service = self._runtime_engine.ib_runtime_service

        if service is None:
            self.ui.comboAccounts.clear()
            return

        ib_service = cast(IBRuntimeService, service)

        accounts = ib_service.get_managed_accounts()
        account_state = ib_service.get_account_state()

        if account_state.is_loaded():
            current_account_id = str(account_state.account_id)

            if current_account_id not in accounts:
                accounts.append(current_account_id)

        saved_account_id = self._load_saved_account_id()

        self.ui.comboAccounts.blockSignals(True)
        self.ui.comboAccounts.clear()

        for account_id in accounts:
            self.ui.comboAccounts.addItem(
                self._account_combo_label(account_id, account_state),
                account_id,
            )

        index_to_select = -1

        if saved_account_id:
            index_to_select = self.ui.comboAccounts.findData(saved_account_id)

        if index_to_select < 0 and account_state.is_loaded():
            index_to_select = self.ui.comboAccounts.findData(
                str(account_state.account_id)
            )

        if index_to_select >= 0:
            self.ui.comboAccounts.setCurrentIndex(index_to_select)

        self.ui.comboAccounts.blockSignals(False)

    def _account_combo_label(
        self,
        account_id: str,
        account_state,
    ) -> str:
        """
        Побудувати label для IB account combo.
        """
        if account_state.is_loaded() and str(account_state.account_id) == account_id:
            return (
                f"{account_id} | "
                f"{account_state.currency} | "
                f"{self._lang_mgr.tr('RuntimeAccount.balance', 'Balance')}: "
                f"{account_state.balance} | "
                f"{self._lang_mgr.tr('RuntimeAccount.equity', 'Equity')}: "
                f"{account_state.equity}"
            )

        return account_id

    @staticmethod
    def _load_saved_account_id() -> str:
        """
        Прочитати збережений IB account_id з LGE.conf.
        """
        from core import session_state

        conf_obj = session_state.CURRENT_CONFIG

        if conf_obj is None:
            return ""

        engine_ib = conf_obj.get("engine", "ib", {}) or {}

        if not isinstance(engine_ib, dict):
            return ""

        return str(engine_ib.get("account_id") or "")

    def _on_account_changed(self) -> None:
        """
        Зберегти вибраний IB account_id.
        """
        account_id = self.ui.comboAccounts.currentData()

        if not account_id:
            return

        self._save_ib_runtime_config(account_id=str(account_id))
