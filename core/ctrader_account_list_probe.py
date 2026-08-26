# ctrader_account_list_probe.py
"""
Одноразове отримання списку cTrader-рахунків через Open API.

Використовується тільки для кнопки "Перевірити з'єднання"
у діалозі налаштування cTrader.

Не запускає RuntimeEngine.
Не запускає CTraderSessionManager.
Не виконує account auth.
Не виставляє ордери.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ctrader_open_api import Client, Protobuf, TcpProtocol

# noinspection PyUnresolvedReferences
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAApplicationAuthReq,
    ProtoOAApplicationAuthRes,
    ProtoOAErrorRes,
    ProtoOAGetAccountListByAccessTokenReq,
    ProtoOAGetAccountListByAccessTokenRes,
)
from twisted.internet import reactor  # noqa
from twisted.internet.error import ReactorNotRunning  # noqa

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 15

reactor_stop = getattr(reactor, "stop")
reactor_run = getattr(reactor, "run")
reactor_call_later = getattr(reactor, "callLater")
reactor_running = getattr(reactor, "running", False)


def stop_reactor() -> None:
    """
    Безпечно зупиняє Twisted reactor.
    """
    try:
        reactor_stop()
    except ReactorNotRunning:
        pass


def shutdown(client: Client) -> None:
    """
    Зупиняє cTrader client service.
    """
    logger.debug("Stopping cTrader probe client service.")
    client.stopService()


def load_access_token() -> str:
    """
    Завантажує access_token з tokens.json.
    """
    root_dir = Path(__file__).resolve().parent.parent

    candidates = [
        root_dir / "tokens" / "tokens.json",
    ]

    for tokens_path in candidates:
        if not tokens_path.exists():
            continue

        with tokens_path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        access_token = str(data.get("access_token", "")).strip()

        if access_token:
            return access_token

    raise RuntimeError("access_token не знайдено у tokens.json.")


class CTraderAccountListProbe:
    """
    Одноразовий probe для отримання списку cTrader-рахунків.
    """

    def __init__(
        self,
        host: str,
        port: int,
        client_id: str,
        client_secret: str,
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = load_access_token()

        self.client: Client | None = None
        self.accounts: list[dict[str, Any]] = []
        self.error_message = ""

    def run(self) -> list[dict[str, Any]]:
        """
        Запускає probe і повертає список рахунків.
        """
        logger.info("Starting cTrader account list probe.")
        logger.info("Host: %s", self.host)
        logger.info("Port: %s", self.port)

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
                "Twisted reactor не вдалося запустити для probe."
            ) from exc

        if self.error_message:
            raise RuntimeError(self.error_message)

        return self.accounts

    def _on_connected(self, client: Client) -> None:
        """
        TCP-з'єднання встановлено.
        """
        logger.info("cTrader probe connected.")

        request = ProtoOAApplicationAuthReq()
        request.clientId = self.client_id
        request.clientSecret = self.client_secret

        deferred = client.send(request)
        deferred.addErrback(self._on_deferred_error)

    def _on_disconnected(self, _client: Client, reason: object) -> None:  # noqa
        """
        TCP-з'єднання розірвано.
        """
        logger.info("cTrader probe disconnected: %s", reason)

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
            self._send_get_account_list(client)
            return

        if payload_type == ProtoOAGetAccountListByAccessTokenRes().payloadType:
            logger.info("cTrader account list received.")
            self._handle_account_list(payload)
            self._finish(client)
            return

        if payload_type == ProtoOAErrorRes().payloadType:
            self._handle_error(payload, client)
            return

    def _send_get_account_list(self, client: Client) -> None:
        """
        Надсилає запит списку рахунків за access_token.
        """
        request = ProtoOAGetAccountListByAccessTokenReq()
        request.accessToken = self.access_token

        deferred = client.send(request)
        deferred.addErrback(self._on_deferred_error)

    def _handle_account_list(self, payload: object) -> None:
        """
        Перетворює відповідь API у список словників.
        """
        accounts = []

        for account in getattr(payload, "ctidTraderAccount", []):
            account_id = str(getattr(account, "ctidTraderAccountId", ""))
            trader_login = str(getattr(account, "traderLogin", ""))
            account_number = str(getattr(account, "accountNumber", ""))
            currency = str(getattr(account, "depositCurrency", ""))

            balance = getattr(account, "balance", None)

            accounts.append(
                {
                    "account_id": account_id,
                    "trader_login": trader_login,
                    "account_number": account_number,
                    "currency": currency,
                    "balance": balance,
                }
            )

        self.accounts = accounts

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
        logger.error("cTrader probe API error: %s", message)

        client.stopService()
        stop_reactor()

    def _on_deferred_error(self, failure: object) -> None:
        """
        Обробляє помилку Deferred.
        """
        self.error_message = str(failure)
        logger.error("cTrader probe deferred error: %s", failure)
        stop_reactor()

    def _on_timeout(self) -> None:
        """
        Обробляє timeout.
        """
        if self.accounts or self.error_message:
            return

        self.error_message = "Timeout підключення до cTrader Open API."
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
