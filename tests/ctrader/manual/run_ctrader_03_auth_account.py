# run_ctrader_03_auth_account.py
"""
Manual test: cTrader Open API account authorization.

Step 03:
- connect
- application auth
- account auth

Expected:
- CONNECTED
- APPLICATION AUTH OK
- ACCOUNT AUTH OK
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
WAIT_SECONDS = 5

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
    """Safely stop Twisted reactor."""
    try:
        reactor_stop()
    except ReactorNotRunning:
        pass


def shutdown(client: Client) -> None:
    """Stop client service."""
    logger.info("Stopping client service...")
    client.stopService()


def read_non_empty(prompt_text: str) -> str:
    """Read non-empty text from console."""
    while True:
        value = input(prompt_text).strip()
        if value:
            return value
        logger.error("Порожнє значення не допускається.")


def read_account_id() -> int:  # noqa
    """Read and validate CTID trader account id."""
    while True:
        raw = input("Введіть CTID_TRADER_ACCOUNT_ID (accountId): ").strip()
        if not raw:
            logger.error("CTID_TRADER_ACCOUNT_ID не може бути порожнім.")
            continue
        if not raw.isdigit():
            logger.error("CTID_TRADER_ACCOUNT_ID має бути цілим числом.")
            continue
        value: int = int(raw)
        return value


def send_app_auth(client: Client, config: RuntimeConfig) -> None:
    """Send application auth request."""
    logger.info("Sending ProtoOAApplicationAuthReq...")

    request = ProtoOAApplicationAuthReq()
    request.clientId = config.client_id
    request.clientSecret = config.client_secret

    deferred = client.send(request)
    deferred.addErrback(on_deferred_error)


def send_account_auth(client: Client, config: RuntimeConfig) -> None:
    """Send account auth request."""
    logger.info("Sending ProtoOAAccountAuthReq...")

    request = ProtoOAAccountAuthReq()
    request.ctidTraderAccountId = config.ctid_trader_account_id
    request.accessToken = config.access_token

    deferred = client.send(request)
    deferred.addErrback(on_deferred_error)


def on_connected(client: Client, config: RuntimeConfig) -> None:
    """Connected callback."""
    logger.info("CONNECTED to %s:%s", HOST, PORT)
    send_app_auth(client, config)


def on_disconnected(_client: Client, reason) -> None:
    """Disconnected callback."""
    logger.info("DISCONNECTED: %s", reason)
    stop_reactor()


def on_message_received(client: Client, message, config: RuntimeConfig) -> None:
    """Message callback."""
    try:
        payload = Protobuf.extract(message)
    except (TypeError, ValueError, AttributeError) as exc:
        logger.debug("MESSAGE extract skipped: %s", exc)
        return

    logger.debug("MESSAGE: %s", payload)

    if message.payloadType == ProtoOAApplicationAuthRes().payloadType:
        logger.info("APPLICATION AUTH OK")
        send_account_auth(client, config)
        return

    if message.payloadType == ProtoOAErrorRes().payloadType:
        logger.error("API ERROR: %s | %s", payload.errorCode, payload.description)
        reactor_call_later(0, shutdown, client)
        return

    if message.payloadType == ProtoOAAccountAuthRes().payloadType:
        logger.info("ACCOUNT AUTH OK")
        reactor_call_later(WAIT_SECONDS, shutdown, client)
        return


def on_deferred_error(failure) -> None:
    """Deferred error callback."""
    logger.error("Deferred error: %s", failure)
    stop_reactor()


def main() -> None:
    """Run manual account auth test."""
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

    logger.info("cTrader Step 03 — AUTH ACCOUNT")
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
