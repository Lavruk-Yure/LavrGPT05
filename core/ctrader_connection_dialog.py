# ctrader_connection_dialog.py
"""
Діалог налаштування підключення до cTrader.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys

from PySide6.QtWidgets import QDialog, QMessageBox

from core.ctrader_oauth_flow import run_ctrader_oauth_flow
from core.lang_manager import LangManager
from core.ui_translator import UITranslator
from engine.runtime_engine import RuntimeEngine
from ui.ui_ctrader_connection_dialog import (
    Ui_CTraderConnectionDialog,
)

logger = logging.getLogger(__name__)


class CTraderConnectionDialog(QDialog):
    """
    Діалог налаштування cTrader Open API.
    """

    def __init__(
        self,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self.ui = Ui_CTraderConnectionDialog()
        self.ui.setupUi(self)

        self._lang_mgr = LangManager()
        self._translator = UITranslator(self._lang_mgr)
        self._runtime_engine = self._get_runtime_engine()

        self._register_i18n_keys()
        self._translator.apply(self)

        self._init_ui()
        self._load_from_conf()
        self._connect_signals()
        self._update_buttons_state()

    @staticmethod
    def _get_runtime_engine() -> RuntimeEngine:
        """
        Отримати shared RuntimeEngine, створений MainAppWindow.

        RoadMap78: діалог cTrader не створює RuntimeEngine самостійно.
        """
        from core import session_state

        runtime_engine = getattr(session_state, "CURRENT_RUNTIME_ENGINE", None)

        if runtime_engine is None:
            raise RuntimeError("CURRENT_RUNTIME_ENGINE is not initialized.")

        return runtime_engine

    def _register_i18n_keys(self) -> None:
        """
        Реєстрація ключів перекладу.
        """
        self._lang_mgr.tr(
            "CTraderConnectionDialog.title",
            "cTrader connection settings",
        )

        self._lang_mgr.tr(
            "CTraderConnectionDialog.lblHelp",
            (
                "To get client_id and client_secret: "
                "open openapi.ctrader.com → Applications → "
                "your app → Credentials. Trading account "
                "will be selected from the account list "
                "after connection."
            ),
        )

        self._lang_mgr.tr(
            "CTraderConnectionDialog.lblHost",
            "Host",
        )

        self._lang_mgr.tr(
            "CTraderConnectionDialog.lblPort",
            "Port",
        )

        self._lang_mgr.tr(
            "CTraderConnectionDialog.lblClientId",
            "Client ID",
        )

        self._lang_mgr.tr(
            "CTraderConnectionDialog.lblClientSecret",
            "Client Secret",
        )

        self._lang_mgr.tr(
            "CTraderConnectionDialog.lblAccountId",
            "Trading account",
        )

        self._lang_mgr.tr(
            "CTraderConnectionDialog.lblAccountMode",
            "Account mode",
        )

        self._lang_mgr.tr(
            "CTraderConnectionDialog.btnTestConnection",
            "Connect",
        )

        self._lang_mgr.tr(
            "CTraderConnectionDialog.btnDisconnect",
            "Disconnect",
        )

        self._lang_mgr.tr(
            "CTraderConnectionDialog.btnClose",
            "Close",
        )

        self._lang_mgr.tr(
            "CTraderConnectionDialog.msgTestStub",
            "Connection test is not implemented yet.",
        )

        self._lang_mgr.tr(
            "CTraderConnectionDialog.accountListConnectFirst",
            "Connect first to load accounts",
        )

        self._lang_mgr.tr(
            "CTraderConnectionDialog.msgClientIdRequired",
            "Client ID is required.",
        )

        self._lang_mgr.tr(
            "CTraderConnectionDialog.msgClientSecretRequired",
            "Client Secret is required.",
        )

        self._lang_mgr.tr(
            "CTraderConnectionDialog.msgTestReadyStub",
            "Connection parameters look valid. "
            "Real connection test is not implemented yet.",
        )

        self._lang_mgr.tr(
            "CTraderConnectionDialog.accountListEmpty",
            "No accounts found",
        )

        self._lang_mgr.tr(
            "CTraderConnectionDialog.msgAccountListLoaded",
            "Account list loaded successfully.",
        )

        self._lang_mgr.tr(
            "CTraderConnectionDialog.msgConnectionFailed",
            "Connection failed.",
        )

        self._lang_mgr.tr(
            "CTraderConnectionDialog.errAccessTokenInvalid",
            (
                "Access token is invalid for this cTrader application or expired. "
                "Run cTrader manual authorization again and update tokens.json."
            ),
        )

        self._lang_mgr.tr(
            "CTraderConnectionDialog.errConnectionTimeout",
            "Connection timeout. Check internet connection, " "host and port.",
        )

        self._lang_mgr.tr(
            "CTraderConnectionDialog.btnAuthorizeCtrader",
            "Authorize cTrader",
        )
        self._lang_mgr.tr(
            "CTraderConnectionDialog.accountSavedPlaceholder",
            "Saved account",
        )
        self._lang_mgr.tr(
            "CTraderOAuth.msgTitle",
            "cTrader OAuth",
        )

        self._lang_mgr.tr(
            "CTraderOAuth.msgSuccess",
            "OAuth authorization completed successfully.",
        )

        self._lang_mgr.tr(
            "CTraderOAuth.msgFailed",
            "OAuth authorization failed:",
        )

        self._lang_mgr.tr(
            "CTraderOAuth.msgTimeout",
            (
                "OAuth session expired.\n\n"
                "After restoring the Internet connection,\n"
                'click "Authorize with cTrader" again.'
            ),
        )

    def _init_ui(self) -> None:
        """
        Первинне налаштування UI.
        """
        self.ui.comboAccountMode.clear()

        self.ui.comboAccountMode.addItem(
            "Demo",
            "DEMO",
        )

        self.ui.comboAccountMode.addItem(
            "Live",
            "LIVE",
        )

        self.ui.comboAccountId.clear()

        self.ui.comboAccountId.addItem(
            self._lang_mgr.tr(
                "CTraderConnectionDialog.accountListConnectFirst",
                "Connect first to load accounts",
            ),
            "",
        )

        if not self._live_allowed():
            index = self.ui.comboAccountMode.findData("LIVE")
            if index >= 0:
                self.ui.comboAccountMode.removeItem(index)

        self.ui.comboAccountId.setEnabled(False)

        self.ui.comboAccountId.setMaxVisibleItems(12)

        self.ui.btnTestConnection.setText(
            self._lang_mgr.tr(
                "CTraderConnectionDialog.btnTestConnection",
                "Connect",
            )
        )
        self.ui.btnCancel.setText(
            self._lang_mgr.tr(
                "CTraderConnectionDialog.btnClose",
                "Close",
            )
        )

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

    def _load_from_conf(self) -> None:
        """
        Завантаження налаштувань із поточної конфігурації.
        """
        try:
            from core import session_state

            conf_obj = session_state.CURRENT_CONFIG
            if conf_obj is None:
                return

            self.ui.spinPort.setValue(int(conf_obj.get("ctrader", "port", 5035)))
            self.ui.editClientId.setText(conf_obj.get("ctrader", "client_id", ""))
            self.ui.editClientSecret.setText(
                conf_obj.get("ctrader", "client_secret", "")
            )

            account_mode = conf_obj.get("ctrader", "account_mode", "DEMO")
            index = self.ui.comboAccountMode.findData(account_mode)
            if index >= 0:
                self.ui.comboAccountMode.setCurrentIndex(index)

            self._update_host_by_account_mode()
            self._load_saved_account_placeholder()

        except Exception:  # noqa
            logger.exception("Не вдалося завантажити cTrader connection settings.")

    @staticmethod
    def _get_saved_account_id() -> str:
        """
        Повертає збережений cTrader account_id з LGE.conf.
        """
        try:
            from core import session_state

            conf_obj = session_state.CURRENT_CONFIG
            if conf_obj is None:
                return ""

            return str(conf_obj.get("ctrader", "account_id", "") or "").strip()

        except Exception:  # noqa
            logger.exception("Не вдалося прочитати збережений cTrader account_id.")
            return ""

    def _load_saved_account_placeholder(self) -> None:
        """
        Показує збережений account_id до реального завантаження account list.
        """
        account_id = self._get_saved_account_id()
        if not account_id:
            return

        self.ui.comboAccountId.clear()

        self.ui.comboAccountId.addItem(
            self._lang_mgr.tr(
                "CTraderConnectionDialog.accountSavedPlaceholder",
                "Saved account",
            )
            + f": {account_id}",
            account_id,
        )

        self.ui.comboAccountId.setEnabled(True)

    def _save_to_conf(self) -> None:
        """
        Збереження налаштувань у LGE.conf.
        """
        from core import session_state
        from core.app_paths import ROOT_CONF_PATH
        from core.config_manager import ConfigManager

        if (
            session_state.CURRENT_CONFIG is None
            or session_state.CURRENT_PASSWORD is None
        ):
            return

        conf_obj = session_state.CURRENT_CONFIG
        password = session_state.CURRENT_PASSWORD

        conf_obj.set("ctrader", "host", self.ui.editHost.text().strip())
        conf_obj.set("ctrader", "port", self.ui.spinPort.value())
        conf_obj.set("ctrader", "client_id", self.ui.editClientId.text().strip())
        conf_obj.set(
            "ctrader",
            "client_secret",
            self.ui.editClientSecret.text().strip(),
        )
        conf_obj.set(
            "ctrader",
            "account_mode",
            self.ui.comboAccountMode.currentData(),
        )

        account_data = self.ui.comboAccountId.currentData()

        if account_data:
            conf_obj.set("ctrader", "account_id", account_data)

        ConfigManager(ROOT_CONF_PATH).save(conf_obj.to_dict(), password)

    def _connect_signals(self) -> None:
        """
        Підключення сигналів UI.
        """
        self.ui.btnTestConnection.clicked.connect(self._on_test_connection)

        self.ui.btnDisconnect.clicked.connect(self._on_disconnect_clicked)

        self.ui.btnAuthorizeCtrader.clicked.connect(self._on_ctrader_oauth_clicked)

        self.ui.comboAccountMode.currentIndexChanged.connect(
            self._update_host_by_account_mode
        )

        self.ui.btnOK.clicked.connect(self._on_ok)

        self.ui.btnCancel.clicked.connect(self.reject)

    def _on_test_connection(self) -> None:
        """
        Тимчасова перевірка параметрів підключення.
        """
        client_id = self.ui.editClientId.text().strip()
        client_secret = self.ui.editClientSecret.text().strip()

        if not client_id:
            QMessageBox.warning(
                self,
                "cTrader",
                self._lang_mgr.tr(
                    "CTraderConnectionDialog.msgClientIdRequired",
                    "Client ID is required.",
                ),
            )
            self.ui.editClientId.setFocus()
            return

        if not client_secret:
            QMessageBox.warning(
                self,
                "cTrader",
                self._lang_mgr.tr(
                    "CTraderConnectionDialog.msgClientSecretRequired",
                    "Client Secret is required.",
                ),
            )
            self.ui.editClientSecret.setFocus()
            return

        try:
            account_mode = self.ui.comboAccountMode.currentData()

            if account_mode == "LIVE":
                connected = self._runtime_engine.connect_ctrader_live()
            else:
                connected = self._runtime_engine.connect_ctrader_demo()

            if not connected:
                raise RuntimeError("cTrader runtime connection failed.")

            self._set_ctrader_auto_connect(True)

            service = self._runtime_engine.ctrader_runtime_service

            if service is not None:
                accounts = service.get_account_list()
            else:
                accounts = []

            if accounts:
                accounts = self._enrich_accounts_with_snapshots(
                    accounts=accounts,
                    client_id=client_id,
                    client_secret=client_secret,
                )

            if accounts:
                self._load_accounts_to_combo(accounts)
            else:
                self._load_runtime_account_to_combo()

            parent = self.parent()

            if parent is not None:
                update_statusbar = getattr(parent, "_update_brokers_statusbar", None)

                if callable(update_statusbar):
                    update_statusbar()

            self._update_buttons_state()

            QMessageBox.information(
                self,
                "cTrader",
                self._lang_mgr.tr(
                    "CTraderConnectionDialog.msgAccountListLoaded",
                    "Account loaded successfully.",
                ),
            )

        except Exception as exc:
            QMessageBox.warning(
                self,
                "cTrader",
                (
                    self._lang_mgr.tr(
                        "CTraderConnectionDialog.msgConnectionFailed",
                        "Connection failed.",
                    )
                    + f"\n\n{self._format_probe_error(str(exc))}"
                ),
            )

    def _on_disconnect_clicked(self) -> None:
        """
        Відключити cTrader через RuntimeEngine.
        """
        self._runtime_engine.disconnect_ctrader()
        self._set_ctrader_auto_connect(False)
        self._update_buttons_state()

        parent = self.parent()

        if parent is not None:
            update_statusbar = getattr(parent, "_update_brokers_statusbar", None)

            if callable(update_statusbar):
                update_statusbar()

        QMessageBox.information(
            self,
            "cTrader",
            self._lang_mgr.tr(
                "CTraderConnectionDialog.msgDisconnected",
                "cTrader disconnected.",
            ),
        )

    def _on_ok(self) -> None:
        """
        Обробка кнопки OK.
        """
        self._save_to_conf()
        self.accept()

    def _on_ctrader_oauth_clicked(self) -> None:
        """
        Запускає browser OAuth flow для cTrader Open API.
        """
        title = self._lang_mgr.tr(
            "CTraderOAuth.msgTitle",
            "cTrader OAuth",
        )

        try:
            run_ctrader_oauth_flow(
                client_id=self.ui.editClientId.text().strip(),
                client_secret=self.ui.editClientSecret.text().strip(),
            )

            message = self._lang_mgr.tr(
                "CTraderOAuth.msgSuccess",
                (
                    "cTrader authorization completed successfully.\n\n"
                    "Tokens have been received.\n"
                    "The account list will be updated automatically."
                ),
            )

            QMessageBox.information(
                self,
                title,
                message,
            )

            self._on_test_connection()

        except Exception as exc:
            logger.exception("cTrader OAuth flow failed.")

            error_text = str(exc)

            if "authorization code not received" in error_text.lower():
                message = self._lang_mgr.tr(
                    "CTraderOAuth.msgTimeout",
                    (
                        "OAuth session expired.\n\n"
                        "After restoring the Internet connection,\n"
                        'click "Authorize with cTrader" again.'
                    ),
                )
            else:
                message = (
                    self._lang_mgr.tr(
                        "CTraderOAuth.msgFailed",
                        "OAuth authorization failed:",
                    )
                    + f"\n\n{error_text}"
                )

            QMessageBox.critical(
                self,
                title,
                message,
            )

    def _update_host_by_account_mode(self) -> None:
        """
        Оновлює host залежно від DEMO/LIVE.
        """
        account_mode = self.ui.comboAccountMode.currentData()

        if account_mode == "LIVE":
            self.ui.editHost.setText("live.ctraderapi.com")
        else:
            self.ui.editHost.setText("demo.ctraderapi.com")

    def _load_runtime_account_to_combo(self) -> None:
        """
        Завантажити активний runtime cTrader account у comboAccountId.
        """
        service = self._runtime_engine.ctrader_runtime_service

        if service is None:
            self.ui.comboAccountId.clear()
            self.ui.comboAccountId.addItem(
                self._lang_mgr.tr(
                    "CTraderConnectionDialog.accountListEmpty",
                    "No accounts found",
                ),
                "",
            )
            self.ui.comboAccountId.setEnabled(False)
            return

        account_state = service.get_account_state()

        if not account_state.is_loaded():
            self.ui.comboAccountId.clear()
            self.ui.comboAccountId.addItem(
                self._lang_mgr.tr(
                    "CTraderConnectionDialog.accountListEmpty",
                    "No accounts found",
                ),
                "",
            )
            self.ui.comboAccountId.setEnabled(False)
            return

        account_id = str(account_state.account_id or "").strip()
        currency = str(account_state.currency or "").strip()
        balance = account_state.balance
        raw_payload = getattr(account_state, "raw_payload", {}) or {}

        leverage = str(raw_payload.get("leverage", "")).strip()
        account_mode = self.ui.comboAccountMode.currentText().strip()

        parts = []

        if account_id:
            parts.append(account_id)

        if account_mode:
            parts.append(account_mode)

        if balance is not None:
            balance_text = str(balance)
            if currency:
                balance_text = f"{balance_text} {currency}"
            parts.append(balance_text)

        if leverage:
            parts.append(leverage)

        visible_text = " • ".join(parts)

        self.ui.comboAccountId.clear()
        self.ui.comboAccountId.addItem(
            visible_text,
            account_id,
        )
        self.ui.comboAccountId.setEnabled(True)

    def _load_accounts_to_combo(
        self,
        accounts: list[dict],
    ) -> None:
        """
        Завантажує отримані cTrader-рахунки у comboAccountId.

        Після reconnect список може прийти в іншому порядку. Тому вибір
        відновлюється за стабільним внутрішнім account_id, а не за індексом
        або видимим trader login.
        """
        current_account_id = str(
            self.ui.comboAccountId.currentData() or ""
        ).strip()
        preferred_account_id = (
            current_account_id or self._get_saved_account_id()
        )

        self.ui.comboAccountId.clear()

        if not accounts:
            self.ui.comboAccountId.addItem(
                self._lang_mgr.tr(
                    "CTraderConnectionDialog.accountListEmpty",
                    "No accounts found",
                ),
                "",
            )
            self.ui.comboAccountId.setEnabled(False)
            return

        for account in accounts:
            account_id = str(account.get("account_id", "")).strip()
            trader_login = str(account.get("trader_login", "")).strip()
            account_number = str(account.get("account_number", "")).strip()
            currency = str(account.get("currency", "")).strip()
            balance = account.get("balance", "")
            leverage = str(account.get("leverage", "")).strip()

            login_text = trader_login or account_number
            account_mode = self.ui.comboAccountMode.currentText().strip()

            parts = []

            if login_text:
                parts.append(login_text)

            if account_mode:
                parts.append(account_mode)

            if balance not in ("", None):
                balance_text = str(balance).strip()
                if currency:
                    balance_text = f"{balance_text} {currency}"
                parts.append(balance_text)

            if leverage:
                parts.append(leverage)

            visible_text = " • ".join(parts)

            self.ui.comboAccountId.addItem(
                visible_text,
                account_id,
            )

        preferred_index = self.ui.comboAccountId.findData(
            preferred_account_id
        )
        if preferred_index >= 0:
            self.ui.comboAccountId.setCurrentIndex(preferred_index)

        self.ui.comboAccountId.setEnabled(True)

    def _run_account_list_probe_subprocess(
        self,
        client_id: str,
        client_secret: str,
    ) -> list[dict]:
        """
        Запускає cTrader account-list probe в окремому Python-процесі.
        """
        payload = {
            "host": self.ui.editHost.text().strip(),
            "port": self.ui.spinPort.value(),
            "client_id": client_id,
            "client_secret": client_secret,
        }

        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "core.ctrader_account_list_probe_runner",
            ],
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )

        if not process.stdout.strip():
            raise RuntimeError(
                process.stderr.strip() or "cTrader probe returned empty response."
            )

        result = json.loads(process.stdout)

        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "cTrader probe failed.")

        accounts = result.get("accounts", [])

        if not isinstance(accounts, list):
            raise RuntimeError("cTrader probe returned invalid accounts list.")

        return self._enrich_accounts_with_snapshots(
            accounts=accounts,
            client_id=client_id,
            client_secret=client_secret,
        )

    def _run_account_snapshot_probe_subprocess(
        self,
        client_id: str,
        client_secret: str,
        account_id: str,
    ) -> dict:
        """
        Запускає cTrader account snapshot probe для одного рахунку.
        """
        payload = {
            "host": self.ui.editHost.text().strip(),
            "port": self.ui.spinPort.value(),
            "client_id": client_id,
            "client_secret": client_secret,
            "account_id": account_id,
        }

        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "core.ctrader_account_snapshot_probe_runner",
            ],
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )

        if not process.stdout.strip():
            raise RuntimeError(
                process.stderr.strip()
                or "cTrader snapshot probe returned empty response."
            )

        result = json.loads(process.stdout)

        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "cTrader snapshot probe failed.")

        snapshot = result.get("snapshot", {})

        if not isinstance(snapshot, dict):
            raise RuntimeError("cTrader snapshot probe returned invalid snapshot.")

        return snapshot

    def _enrich_accounts_with_snapshots(
        self,
        accounts: list[dict],
        client_id: str,
        client_secret: str,
    ) -> list[dict]:
        """
        Доповнює список рахунків runtime snapshot-даними.

        Balance/currency/leverage не зберігаються в LGE.conf.
        Це лише runtime/UI snapshot.
        """
        enriched_accounts = []

        for account in accounts:
            account_copy = dict(account)
            account_id = str(account_copy.get("account_id", "")).strip()

            if not account_id:
                enriched_accounts.append(account_copy)
                continue

            try:
                snapshot = self._run_account_snapshot_probe_subprocess(
                    client_id=client_id,
                    client_secret=client_secret,
                    account_id=account_id,
                )

                account_copy["balance"] = snapshot.get("balance", "")
                account_copy["currency"] = snapshot.get("currency", "")
                account_copy["leverage"] = snapshot.get("leverage", "")

            except Exception:  # noqa
                logger.exception(
                    "Не вдалося отримати snapshot для cTrader account_id=%s.",
                    account_id,
                )

            enriched_accounts.append(account_copy)

        return enriched_accounts

    def _format_probe_error(self, error_text: str) -> str:
        """
        Перетворює технічну помилку cTrader probe у зрозуміле UI-повідомлення.
        """
        if "CH_ACCESS_TOKEN_INVALID" in error_text:
            return self._lang_mgr.tr(
                "CTraderConnectionDialog.errAccessTokenInvalid",
                (
                    "Access token is invalid for this cTrader application or expired. "
                    "Run cTrader manual authorization again and update tokens.json."
                ),
            )

        if "Timeout" in error_text:
            return self._lang_mgr.tr(
                "CTraderConnectionDialog.errConnectionTimeout",
                "Connection timeout. Check internet connection, " "host and port.",
            )

        return error_text

    def _set_ctrader_auto_connect(  # noqa
        self,
        enabled: bool,
    ) -> None:
        """
        Зберегти намір автопідключення cTrader у LGE.conf.
        """
        from core import session_state
        from core.app_paths import ROOT_CONF_PATH
        from core.config_manager import ConfigManager

        conf_obj = session_state.CURRENT_CONFIG
        password = session_state.CURRENT_PASSWORD

        if conf_obj is None or password is None:
            logger.warning(
                "Cannot save cTrader auto_connect: config is unavailable.",
            )
            return

        conf = conf_obj.to_dict()
        engine = conf.setdefault("engine", {})
        auto_connect = engine.setdefault("auto_connect", {})

        auto_connect["ctrader"] = bool(enabled)

        ConfigManager(ROOT_CONF_PATH).save(conf, password)

    def _update_buttons_state(self) -> None:
        """
        Оновити доступність кнопок відповідно до broker health.
        """
        service = self._runtime_engine.ctrader_runtime_service

        if service is None:
            self.ui.btnTestConnection.setEnabled(True)
            self.ui.btnDisconnect.setEnabled(False)
            return

        health = service.get_broker_health()
        state = str(getattr(health, "state", "UNKNOWN"))

        if state == "CONNECTED":
            self.ui.btnTestConnection.setEnabled(False)
            self.ui.btnDisconnect.setEnabled(True)
            return

        if state in {"CONNECTING", "RECONNECTING"}:
            self.ui.btnTestConnection.setEnabled(False)
            self.ui.btnDisconnect.setEnabled(False)
            return

        self.ui.btnTestConnection.setEnabled(True)
        self.ui.btnDisconnect.setEnabled(False)
        self._refresh_buttons_visual_state()

    def _refresh_buttons_visual_state(self) -> None:
        """
        Примусово перемалювати кнопки після зміни enabled/disabled.
        """
        for button in (
            self.ui.btnAuthorizeCtrader,
            self.ui.btnTestConnection,
            self.ui.btnDisconnect,
            self.ui.btnOK,
            self.ui.btnCancel,
        ):
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()
