# run_ctrader_02_auth_app.py
"""
Manual test: cTrader Open API application authorization.

Step 02:
- connect to cTrader Open API
- send ProtoOAApplicationAuthReq
- verify application-level authorization

Expected:
- CONNECTED
- application auth response received
- clean disconnect
"""

from __future__ import annotations

import logging

from ctrader_open_api import Client, Protobuf, TcpProtocol
from ctrader_open_api.endpoints import EndPoints

# noinspection PyUnresolvedReferences
from ctrader_open_api.messages.OpenApiMessages_pb2 import (  # noqa
    ProtoOAApplicationAuthReq,
    ProtoOAApplicationAuthRes,
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

# TODO: встав свої реальні значення
CLIENT_ID = "17468_5BxqdWm2OvAsdJsBStSefqAvnKvv4Tg45Ht0enwQOU2j8LjMwk"
CLIENT_SECRET = "lhKRifMYWFhwX0loCJShQP7RymF01yRSTHqe3t33HcAUlhvV9O"

reactor_stop = getattr(reactor, "stop")
reactor_run = getattr(reactor, "run")
reactor_call_later = getattr(reactor, "callLater")


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


def send_app_auth(client: Client) -> None:
    """Send application auth request."""
    if not CLIENT_ID.strip():
        logger.error("CLIENT_ID is empty")
        shutdown(client)
        return

    if not CLIENT_SECRET.strip():
        logger.error("CLIENT_SECRET is empty")
        shutdown(client)
        return

    request = ProtoOAApplicationAuthReq()
    request.clientId = CLIENT_ID
    request.clientSecret = CLIENT_SECRET

    logger.info("Sending ProtoOAApplicationAuthReq...")
    deferred = client.send(request)
    deferred.addErrback(on_deferred_error)


def on_connected(client: Client) -> None:
    """Connected callback."""
    logger.info("CONNECTED to %s:%s", HOST, PORT)
    send_app_auth(client)


def on_disconnected(_client: Client, reason) -> None:
    """Disconnected callback."""
    logger.info("DISCONNECTED: %s", reason)
    stop_reactor()


def on_message_received(client: Client, message) -> None:
    """Message callback."""
    try:
        payload = Protobuf.extract(message)
    except (TypeError, ValueError, AttributeError) as exc:
        logger.debug("MESSAGE extract skipped: %s", exc)
        return

    logger.debug("MESSAGE: %s", payload)

    if isinstance(payload, ProtoOAApplicationAuthRes):
        logger.info("APPLICATION AUTH OK")
        reactor_call_later(WAIT_SECONDS, shutdown, client)


def on_deferred_error(failure) -> None:
    """Deferred error callback."""
    logger.error("Deferred error: %s", failure)
    stop_reactor()


def main() -> None:
    """Run manual application auth test."""
    logger.info("cTrader Step 02 — AUTH APP")
    logger.info("Host: %s", HOST)
    logger.info("Port: %s", PORT)

    client = Client(HOST, PORT, TcpProtocol)
    client.setConnectedCallback(on_connected)
    client.setDisconnectedCallback(on_disconnected)
    client.setMessageReceivedCallback(on_message_received)

    logger.info("Starting client service...")
    client.startService()

    logger.info("Running Twisted reactor...")
    reactor_run()

    logger.info("DONE")


if __name__ == "__main__":
    main()
