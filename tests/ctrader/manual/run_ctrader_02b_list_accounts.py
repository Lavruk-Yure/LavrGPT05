# run_ctrader_02b_list_accounts.py
"""
Manual test: cTrader Open API list accounts by access token.

Step 02b:
- connect
- application auth
- get account list by access token

Expected:
- CONNECTED
- APPLICATION AUTH OK
- ACCOUNT LIST RECEIVED
- DONE
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ctrader_open_api import Client, Protobuf, TcpProtocol
from ctrader_open_api.endpoints import EndPoints

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


def on_connected(client: Client, config: RuntimeConfig) -> None:
    logger.info("CONNECTED to %s:%s", HOST, PORT)
    send_app_auth(client, config)


def on_disconnected(_client: Client, reason) -> None:
    logger.info("DISCONNECTED: %s", reason)
    stop_reactor()


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
        logger.info("ACCOUNT LIST RECEIVED")

        accounts = list(getattr(payload, "ctidTraderAccount", []))
        if not accounts:
            logger.warning("Accounts list is empty.")
        else:
            for acc in accounts:
                logger.info(
                    "accountId=%s | traderLogin=%s | accountNumber=%s",
                    getattr(acc, "ctidTraderAccountId", None),
                    getattr(acc, "traderLogin", None),
                    getattr(acc, "accountNumber", None),
                )

        reactor_call_later(0, shutdown, client)
        return

    if message.payloadType == ProtoOAErrorRes().payloadType:
        logger.error(
            "API ERROR: %s | %s",
            payload.errorCode,
            payload.description,
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

    config = RuntimeConfig(
        client_id=client_id,
        client_secret=client_secret,
        access_token=access_token,
    )

    logger.info("cTrader Step 02b — LIST ACCOUNTS")
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
