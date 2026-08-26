# run_ctrader_05_positions.py
"""
Manual test: cTrader Open API get positions.

Step 05:
- connect
- application auth
- list accounts by access token
- account auth
- request positions

Expected:
- CONNECTED
- APPLICATION AUTH OK
- ACCOUNT LIST RECEIVED
- ACCOUNT AUTH OK
- POSITIONS RECEIVED
- DONE
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ctrader_open_api import Client, Protobuf, TcpProtocol
from ctrader_open_api.endpoints import EndPoints

# noinspection PyUnresolvedReferences
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAAccountAuthReq,
    ProtoOAAccountAuthRes,
    ProtoOAApplicationAuthReq,
    ProtoOAApplicationAuthRes,
    ProtoOAErrorRes,
    ProtoOAGetAccountListByAccessTokenReq,
    ProtoOAGetAccountListByAccessTokenRes,
    ProtoOAReconcileReq,
    ProtoOAReconcileRes,
)
from twisted.internet import reactor  # noqa
from twisted.internet.error import ReactorNotRunning  # noqa

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

HOST = EndPoints.PROTOBUF_DEMO_HOST
PORT = EndPoints.PROTOBUF_PORT

reactor_stop = getattr(reactor, "stop")
reactor_run = getattr(reactor, "run")
reactor_call_later = getattr(reactor, "callLater")


@dataclass
class RuntimeConfig:
    client_id: str
    client_secret: str
    access_token: str
    ctid_trader_account_id: int


def stop_reactor() -> None:
    try:
        reactor_stop()
    except ReactorNotRunning:
        pass


def shutdown(client: Client) -> None:
    logger.info("Stopping client service...")
    client.stopService()


def read_non_empty(prompt_text: str) -> str:
    while True:
        value = input(prompt_text).strip()
        if value:
            return value
        logger.error("Порожнє значення не допускається.")


def read_account_id() -> int:  # noqa
    while True:
        raw = input("Введіть CTID_TRADER_ACCOUNT_ID (accountId): ").strip()
        if not raw:
            logger.error("CTID_TRADER_ACCOUNT_ID не може бути порожнім.")
            continue
        if not raw.isdigit():
            logger.error("CTID_TRADER_ACCOUNT_ID має бути цілим числом.")
            continue
        value = int(raw)
        return value


def send_app_auth(client: Client, config: RuntimeConfig) -> None:
    logger.info("Sending ProtoOAApplicationAuthReq...")

    request = ProtoOAApplicationAuthReq()
    request.clientId = config.client_id
    request.clientSecret = config.client_secret

    deferred = client.send(request)
    deferred.addErrback(on_deferred_error)


def send_get_account_list(client: Client, config: RuntimeConfig) -> None:
    logger.info("Sending ProtoOAGetAccountListByAccessTokenReq...")

    request = ProtoOAGetAccountListByAccessTokenReq()
    request.accessToken = config.access_token

    deferred = client.send(request)
    deferred.addErrback(on_deferred_error)


def send_account_auth(client: Client, config: RuntimeConfig) -> None:
    logger.info("Sending ProtoOAAccountAuthReq...")

    request = ProtoOAAccountAuthReq()
    request.ctidTraderAccountId = config.ctid_trader_account_id
    request.accessToken = config.access_token

    deferred = client.send(request)
    deferred.addErrback(on_deferred_error)


def send_reconcile(client: Client, config: RuntimeConfig) -> None:
    logger.info("Sending ProtoOAReconcileReq...")

    request = ProtoOAReconcileReq()
    request.ctidTraderAccountId = config.ctid_trader_account_id

    deferred = client.send(request)
    deferred.addErrback(on_deferred_error)


def on_connected(client: Client, config: RuntimeConfig) -> None:
    logger.info("CONNECTED to %s:%s", HOST, PORT)
    send_app_auth(client, config)


def on_disconnected(_client: Client, reason) -> None:
    logger.info("DISCONNECTED: %s", reason)
    stop_reactor()


def log_accounts(payload) -> None:
    accounts = list(getattr(payload, "ctidTraderAccount", []))
    if not accounts:
        logger.warning("Accounts list is empty.")
        return

    logger.info("ACCOUNT LIST RECEIVED")
    for acc in accounts:
        logger.info(
            "accountId=%s | traderLogin=%s | isLive=%s",
            getattr(acc, "ctidTraderAccountId", None),
            getattr(acc, "traderLogin", None),
            getattr(acc, "isLive", None),
        )


def log_positions(payload) -> None:
    positions = list(getattr(payload, "position", []))
    orders = list(getattr(payload, "order", []))

    logger.info(
        "RECONCILE RECEIVED | positions=%s | orders=%s",
        len(positions),
        len(orders),
    )

    if positions:
        for pos in positions:
            logger.info(
                "POSITION | positionId=%s | symbolId=%s | "
                "tradeSide=%s | volume=%s | price=%s",
                getattr(pos, "positionId", None),
                getattr(pos, "symbolId", None),
                getattr(pos, "tradeSide", None),
                getattr(pos, "volume", None),
                getattr(pos, "price", None),
            )
    else:
        logger.info("No open positions.")

    if orders:
        for order in orders:
            logger.info(
                "ORDER | orderId=%s | symbolId=%s | orderType=%s |"
                " tradeSide=%s | volume=%s",
                getattr(order, "orderId", None),
                getattr(order, "symbolId", None),
                getattr(order, "orderType", None),
                getattr(order, "tradeSide", None),
                getattr(order, "volume", None),
            )
    else:
        logger.info("No pending orders.")


def on_message_received(client: Client, message, config: RuntimeConfig) -> None:
    try:
        payload = Protobuf.extract(message)
    except Exception as exc:
        logger.debug("MESSAGE extract skipped: %s", exc)
        return

    logger.debug("MESSAGE: %s", payload)

    if message.payloadType == ProtoOAApplicationAuthRes().payloadType:
        logger.info("APPLICATION AUTH OK")
        send_get_account_list(client, config)
        return

    if message.payloadType == ProtoOAGetAccountListByAccessTokenRes().payloadType:
        log_accounts(payload)
        send_account_auth(client, config)
        return

    if message.payloadType == ProtoOAAccountAuthRes().payloadType:
        logger.info("ACCOUNT AUTH OK")
        send_reconcile(client, config)
        return

    if message.payloadType == ProtoOAReconcileRes().payloadType:
        log_positions(payload)
        reactor_call_later(0, shutdown, client)
        return

    if message.payloadType == ProtoOAErrorRes().payloadType:
        logger.error(
            "API ERROR: %s | %s",
            getattr(payload, "errorCode", None),
            getattr(payload, "description", None),
        )
        reactor_call_later(0, shutdown, client)
        return


def on_deferred_error(failure) -> None:
    logger.error("Deferred error: %s", failure)
    stop_reactor()


def main() -> None:
    client_id = read_non_empty("Введіть CLIENT_ID: ")
    client_secret = read_non_empty("Введіть CLIENT_SECRET: ")
    access_token = read_non_empty("Введіть ACCESS_TOKEN: ")
    ctid_trader_account_id = read_account_id()

    config = RuntimeConfig(
        client_id=client_id,
        client_secret=client_secret,
        access_token=access_token,
        ctid_trader_account_id=ctid_trader_account_id,
    )

    logger.info("cTrader Step 05 — POSITIONS")
    logger.info("Host: %s", HOST)
    logger.info("Port: %s", PORT)

    client = Client(HOST, PORT, TcpProtocol)

    client.setConnectedCallback(lambda c: on_connected(c, config))
    client.setDisconnectedCallback(on_disconnected)
    client.setMessageReceivedCallback(
        lambda c, message: on_message_received(c, message, config)
    )

    logger.info("Starting client service...")
    client.startService()

    logger.info("Running Twisted reactor...")
    reactor_run()

    logger.info("DONE")


if __name__ == "__main__":
    main()
