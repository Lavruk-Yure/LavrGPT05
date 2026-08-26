# run_ctrader_01_connect.py
"""
Manual test: cTrader Open API connection.

Step 01:
- establish raw connection to cTrader Open API
- no application auth
- no account auth
- verify transport-level connectivity
"""

from __future__ import annotations

import logging

from ctrader_open_api import Client, Protobuf, TcpProtocol
from ctrader_open_api.endpoints import EndPoints
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


def on_connected(client: Client) -> None:
    """Connected callback."""
    logger.info("CONNECTED to %s:%s", HOST, PORT)
    logger.info("Waiting %s seconds before disconnect...", WAIT_SECONDS)
    reactor_call_later(WAIT_SECONDS, shutdown, client)


def on_disconnected(_client: Client, reason) -> None:
    """Disconnected callback."""
    logger.info("DISCONNECTED: %s", reason)
    stop_reactor()


def on_message_received(_client: Client, message) -> None:
    """Message callback."""
    try:
        payload = Protobuf.extract(message)
        logger.debug("MESSAGE: %s", payload)
    except (TypeError, ValueError, AttributeError) as exc:
        logger.debug("MESSAGE extract skipped: %s", exc)


def main() -> None:
    """Run manual connect test."""
    logger.info("cTrader Step 01 — CONNECT")
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
