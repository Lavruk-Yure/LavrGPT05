# ctrader_account_snapshot_probe.py
"""
Одноразове отримання runtime snapshot для одного cTrader-рахунку.

Призначення:
- отримати account runtime state для вибраного account_id;
- працювати без GUI;
- не писати в LGE.conf;
- не запускати RuntimeEngine;
- не запускати CTraderSessionManager;
- використовувати той самий canonical tokens/tokens.json;
- бути основою для майбутнього runtime account state service.

Поточний flow:
1. TCP connect.
2. Application auth.
3. Account auth.
4. Reconcile request.
5. Snapshot dict.
6. Disconnect.

Важливо:
- цей модуль має отримувати snapshot тільки для ОДНОГО вибраного account_id;
- не робити цикл по всіх рахунках;
- не зберігати balance/equity у config.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from ctrader_open_api import Client, Protobuf, TcpProtocol

# noinspection PyUnresolvedReferences
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAAccountAuthReq,
    ProtoOAAccountAuthRes,
    ProtoOAApplicationAuthReq,
    ProtoOAApplicationAuthRes,
    ProtoOAAssetListReq,
    ProtoOAAssetListRes,
    ProtoOAErrorRes,
    ProtoOAReconcileReq,
    ProtoOAReconcileRes,
    ProtoOATraderReq,
    ProtoOATraderRes,
)
from twisted.internet import reactor  # noqa
from twisted.internet.error import ReactorNotRunning  # noqa

from core.ctrader_account_list_probe import load_access_token

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 15

reactor_stop = getattr(reactor, "stop")
reactor_run = getattr(reactor, "run")
reactor_call_later = getattr(reactor, "callLater")


def stop_reactor() -> None:
    """
    Безпечно зупиняє Twisted reactor.
    """
    try:
        reactor_stop()
    except ReactorNotRunning:
        pass


class CTraderAccountSnapshotProbe:
    """
    Одноразовий probe для отримання snapshot вибраного cTrader-рахунку.
    """

    def __init__(
        self,
        host: str,
        port: int,
        client_id: str,
        client_secret: str,
        account_id: str,
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self.client_secret = client_secret
        self.account_id = self._normalize_account_id(account_id)
        self.access_token = load_access_token()

        self.client: Client | None = None
        self.snapshot: dict[str, Any] = {}
        self._trader_payload: object | None = None
        self.error_message = ""

    def run(self) -> dict[str, Any]:
        """
        Запускає probe і повертає canonical account snapshot.
        """
        logger.info("Starting cTrader account snapshot probe.")
        logger.info("Host: %s", self.host)
        logger.info("Port: %s", self.port)
        logger.info("Account ID: %s", self.account_id)

        self._validate_input()

        self.client = Client(self.host, self.port, TcpProtocol)

        self.client.setConnectedCallback(self._on_connected)
        self.client.setDisconnectedCallback(self._on_disconnected)
        self.client.setMessageReceivedCallback(self._on_message_received)

        reactor_call_later(DEFAULT_TIMEOUT_SECONDS, self._on_timeout)

        self.client.startService()

        try:
            reactor_run()
        except RuntimeError as exc:
            raise RuntimeError(
                "Twisted reactor не вдалося запустити для account snapshot probe."
            ) from exc

        if self.error_message:
            raise RuntimeError(self.error_message)

        if not self.snapshot:
            raise RuntimeError("cTrader account snapshot не отримано.")

        return self.snapshot

    def _validate_input(self) -> None:
        """
        Перевіряє обов'язкові параметри probe.
        """
        if not self.host.strip():
            raise ValueError("host is required.")

        if int(self.port) <= 0:
            raise ValueError("port must be positive.")

        if not self.client_id.strip():
            raise ValueError("client_id is required.")

        if not self.client_secret.strip():
            raise ValueError("client_secret is required.")

        if not self.account_id:
            raise ValueError("account_id is required.")

    @staticmethod
    def _normalize_account_id(account_id: str) -> str:
        """
        Нормалізує account_id до рядка.
        """
        return str(account_id or "").strip()

    def _on_connected(self, client: Client) -> None:
        """
        TCP-з'єднання встановлено.
        """
        logger.info("cTrader snapshot probe connected.")

        request = ProtoOAApplicationAuthReq()
        request.clientId = self.client_id
        request.clientSecret = self.client_secret

        deferred = client.send(request)
        deferred.addErrback(self._on_deferred_error)

    def _on_disconnected(self, _client: Client, reason: object) -> None:  # noqa
        """
        TCP-з'єднання розірвано.
        """
        logger.info("cTrader snapshot probe disconnected: %s", reason)

    def _on_message_received(self, client: Client, message: object) -> None:
        """
        Обробляє вхідне повідомлення cTrader Open API.
        """
        try:
            payload = Protobuf.extract(message)
        except Exception as exc:
            logger.debug("Message extract skipped: %s", exc)
            return

        payload_type = getattr(message, "payloadType", None)

        if payload_type == ProtoOAApplicationAuthRes().payloadType:
            logger.info("cTrader application auth OK.")
            self._send_account_auth(client)
            return

        if payload_type == ProtoOAAccountAuthRes().payloadType:
            logger.info("cTrader account auth OK.")
            self._send_trader_req(client)
            return

        if payload_type == ProtoOATraderRes().payloadType:
            logger.info("cTrader trader info received.")
            self._trader_payload = payload
            self._send_asset_list_req(client)
            return

        if payload_type == ProtoOAReconcileRes().payloadType:
            logger.info("cTrader reconcile received.")
            self._handle_reconcile(payload)
            self._finish(client)
            return

        if payload_type == ProtoOAErrorRes().payloadType:
            self._handle_error(payload, client)
            return

        if payload_type == ProtoOAAssetListRes().payloadType:
            logger.info("cTrader asset list received.")
            self._handle_trader(self._trader_payload, payload)
            self._finish(client)
            return

    def _send_asset_list_req(self, client: Client) -> None:
        """
        Надсилає ProtoOAAssetListReq для отримання валюти рахунку.
        """
        request = ProtoOAAssetListReq()
        request.ctidTraderAccountId = int(self.account_id)

        deferred = client.send(request)
        deferred.addErrback(self._on_deferred_error)

    def _handle_trader(
        self,
        payload: object | None,
        asset_payload: object | None = None,
    ) -> None:
        """
        Перетворює ProtoOATraderRes у canonical account snapshot.
        """
        now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        trader = getattr(payload, "trader", None)
        if trader is None:
            raise RuntimeError("ProtoOATraderRes не містить trader.")

        deposit_asset_id = getattr(trader, "depositAssetId", None)
        currency = self._get_currency_from_assets(asset_payload, deposit_asset_id)

        money_digits = int(getattr(trader, "moneyDigits", 2) or 2)
        raw_balance = getattr(trader, "balance", None)

        balance = None
        if raw_balance is not None:
            balance = float(raw_balance) / (10**money_digits)

        leverage_in_cents = getattr(trader, "leverageInCents", None)
        leverage = ""
        if leverage_in_cents not in ("", None):
            leverage = f"1:{int(leverage_in_cents) // 100}"

        self.snapshot = {
            "account_id": str(getattr(trader, "ctidTraderAccountId", self.account_id)),
            "trader_login": str(getattr(trader, "traderLogin", "") or ""),
            "account_number": str(getattr(trader, "traderLogin", "") or ""),
            "broker_name": str(getattr(trader, "brokerName", "") or ""),
            "account_type": str(getattr(trader, "accountType", "") or ""),
            "currency": currency,
            "balance": balance,
            "equity": None,
            "margin": None,
            "free_margin": None,
            "leverage": leverage,
            "money_digits": money_digits,
            "snapshot_utc": now_utc,
        }

    def _send_account_auth(self, client: Client) -> None:
        """
        Надсилає ProtoOAAccountAuthReq для вибраного account_id.
        """
        request = ProtoOAAccountAuthReq()
        request.ctidTraderAccountId = int(self.account_id)
        request.accessToken = self.access_token

        deferred = client.send(request)
        deferred.addErrback(self._on_deferred_error)

    def _send_trader_req(self, client: Client) -> None:
        """
        Надсилає ProtoOATraderReq для отримання balance/account info.
        """
        request = ProtoOATraderReq()
        request.ctidTraderAccountId = int(self.account_id)

        deferred = client.send(request)
        deferred.addErrback(self._on_deferred_error)

    def _send_reconcile(self, client: Client) -> None:
        """
        Надсилає ProtoOAReconcileReq для вибраного account_id.
        """
        request = ProtoOAReconcileReq()
        request.ctidTraderAccountId = int(self.account_id)

        deferred = client.send(request)
        deferred.addErrback(self._on_deferred_error)

    def _handle_reconcile(self, payload: object) -> None:
        """
        Перетворює ProtoOAReconcileRes у canonical snapshot dict.

        У різних версіях cTrader Open API частина account-полів може
        бути відсутня у ReconcileRes. Тому кожне поле читається обережно.
        """

        now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        account = self._find_account_object(payload)

        self.snapshot = {
            "account_id": self.account_id,
            "trader_login": self._get_first_attr(
                account,
                payload,
                names=("traderLogin", "login", "accountNumber"),
                default="",
            ),
            "account_number": self._get_first_attr(
                account,
                payload,
                names=("accountNumber", "traderLogin"),
                default="",
            ),
            "broker_name": self._get_first_attr(
                account,
                payload,
                names=("brokerName", "broker", "brokerTitle"),
                default="",
            ),
            "account_type": self._get_first_attr(
                account,
                payload,
                names=("accountType", "type"),
                default="",
            ),
            "currency": self._get_first_attr(
                account,
                payload,
                names=("depositCurrency", "currency", "moneyCurrency"),
                default="",
            ),
            "balance": self._get_money_value(
                account,
                payload,
                names=("balance",),
            ),
            "equity": self._get_money_value(
                account,
                payload,
                names=("equity",),
            ),
            "margin": self._get_money_value(
                account,
                payload,
                names=("margin", "usedMargin"),
            ),
            "free_margin": self._get_money_value(
                account,
                payload,
                names=("freeMargin", "free_margin"),
            ),
            "leverage": self._get_first_attr(
                account,
                payload,
                names=("leverage", "preciseLeverage"),
                default="",
            ),
            "snapshot_utc": now_utc,
        }

    @staticmethod
    def _find_account_object(payload: object) -> object | None:
        """
        Повертає account/trader object з reconcile payload, якщо він є.
        """
        for name in (
            "account",
            "trader",
            "traderAccount",
            "ctidTraderAccount",
        ):
            value = getattr(payload, name, None)
            if value is not None:
                return value

        return None

    @staticmethod
    def _get_first_attr(
        primary: object | None,
        secondary: object | None,
        names: tuple[str, ...],
        default: str,
    ) -> str:
        """
        Повертає перше непорожнє значення атрибута.
        """
        for source in (primary, secondary):
            if source is None:
                continue

            for name in names:
                value = getattr(source, name, None)
                if value not in ("", None):
                    return str(value).strip()

        return default

    @staticmethod
    def _get_money_value(
        primary: object | None,
        secondary: object | None,
        names: tuple[str, ...],
    ) -> float | None:
        """
        Повертає money value як float або None.

        Якщо API повертає integer у minor units, масштабування буде
        уточнено після першого реального payload dump.
        """
        raw_value = None

        for source in (primary, secondary):
            if source is None:
                continue

            for name in names:
                value = getattr(source, name, None)
                if value not in ("", None):
                    raw_value = value
                    break

            if raw_value is not None:
                break

        if raw_value in ("", None):
            return None

        try:
            return float(raw_value)
        except (TypeError, ValueError):
            logger.debug("Cannot convert money value to float: %s", raw_value)
            return None

    def _handle_error(self, payload: object, client: Client) -> None:
        """
        Обробляє помилку Open API.
        """
        error_code = str(getattr(payload, "errorCode", ""))
        description = str(getattr(payload, "description", ""))

        message = f"{error_code}: {description}".strip(": ")
        if not message:
            message = "Невідома помилка cTrader Open API."

        self.error_message = message
        logger.error("cTrader snapshot probe API error: %s", message)

        client.stopService()
        stop_reactor()

    def _on_deferred_error(self, failure: object) -> None:
        """
        Обробляє помилку Deferred.
        """
        self.error_message = str(failure)
        logger.error("cTrader snapshot probe deferred error: %s", failure)
        stop_reactor()

    def _on_timeout(self) -> None:
        """
        Обробляє timeout.
        """
        if self.snapshot or self.error_message:
            return

        self.error_message = "Timeout отримання cTrader account snapshot."
        logger.error(self.error_message)

        if self.client is not None:
            self._finish(self.client)
        else:
            stop_reactor()

    def _finish(self, client: Client) -> None:  # noqa
        """
        Завершує probe.
        """
        client.stopService()
        stop_reactor()

    @staticmethod
    def _get_currency_from_assets(
        asset_payload: object | None,
        deposit_asset_id: object | None,
    ) -> str:
        """
        Повертає валюту рахунку за depositAssetId.
        """
        if asset_payload is None or deposit_asset_id in ("", None):
            return ""

        assets = getattr(asset_payload, "asset", [])

        for asset in assets:
            asset_id = getattr(asset, "assetId", None)
            if str(asset_id) != str(deposit_asset_id):
                continue

            name = str(getattr(asset, "name", "") or "").strip()
            display_name = str(getattr(asset, "displayName", "") or "").strip()

            return name or display_name

        return ""
