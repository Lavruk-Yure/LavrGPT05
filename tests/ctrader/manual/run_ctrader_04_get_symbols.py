# run_ctrader_04_get_symbols.py
"""
Manual test: cTrader Open API get symbol by name.

Step 04:
- connect
- application auth
- list accounts by access token
- account auth
- request symbol details by symbol name

Expected:
- CONNECTED
- APPLICATION AUTH OK
- ACCOUNT LIST RECEIVED
- ACCOUNT AUTH OK
- SYMBOL FOUND
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
    ProtoOASymbolsListReq,
    ProtoOASymbolsListRes,
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
WAIT_TIMEOUT_SECONDS = 20

reactor_stop = getattr(reactor, "stop")
reactor_run = getattr(reactor, "run")
reactor_call_later = getattr(reactor, "callLater")


@dataclass
class RuntimeConfig:
    client_id: str
    client_secret: str
    access_token: str
    ctid_trader_account_id: int
    symbol_name: str


@dataclass
class RuntimeState:
    current_stage: str = "startup"
    symbol_response_received: bool = False
    shutdown_scheduled: bool = False


def stop_reactor() -> None:
    """Безпечно зупинити Twisted reactor."""
    try:
        reactor_stop()
    except ReactorNotRunning:
        pass


def shutdown(client: Client) -> None:
    """Коректно зупинити клієнт."""
    logger.info("Stopping client service...")
    client.stopService()


def schedule_shutdown(
    client: Client,
    state: RuntimeState,
    delay_seconds: int = 0,
) -> None:
    """Запланувати shutdown лише один раз."""
    if state.shutdown_scheduled:
        return
    state.shutdown_scheduled = True
    reactor_call_later(delay_seconds, shutdown, client)


def read_non_empty(prompt_text: str) -> str:
    """Прочитати непорожній рядок."""
    while True:
        value = input(prompt_text).strip()
        if value:
            return value
        logger.error("Порожнє значення не допускається.")


def read_account_id() -> int:  # noqa
    """Прочитати accountId."""
    while True:
        raw = input("Введіть CTID_TRADER_ACCOUNT_ID (accountId): ").strip()
        if not raw:
            logger.error("CTID_TRADER_ACCOUNT_ID не може бути порожнім.")
            continue
        if not raw.isdigit():
            logger.error("CTID_TRADER_ACCOUNT_ID має бути цілим числом.")
            continue
        value = int(raw)
        if value <= 0:
            logger.error("CTID_TRADER_ACCOUNT_ID має бути > 0.")
            continue
        return value


def send_app_auth(
    client: Client,
    config: RuntimeConfig,
    state: RuntimeState,
) -> None:
    """Надіслати auth додатка."""
    state.current_stage = "application_auth"
    logger.info("Sending ProtoOAApplicationAuthReq...")

    request = ProtoOAApplicationAuthReq()
    request.clientId = config.client_id
    request.clientSecret = config.client_secret

    deferred = client.send(request)
    deferred.addErrback(on_deferred_error, state)


def send_get_account_list(
    client: Client,
    config: RuntimeConfig,
    state: RuntimeState,
) -> None:
    """Запросити список акаунтів."""
    state.current_stage = "get_account_list"
    logger.info("Sending ProtoOAGetAccountListByAccessTokenReq...")

    request = ProtoOAGetAccountListByAccessTokenReq()
    request.accessToken = config.access_token

    deferred = client.send(request)
    deferred.addErrback(on_deferred_error, state)


def send_account_auth(
    client: Client,
    config: RuntimeConfig,
    state: RuntimeState,
) -> None:
    """Надіслати auth торгового акаунта."""
    state.current_stage = "account_auth"
    logger.info("Sending ProtoOAAccountAuthReq...")

    request = ProtoOAAccountAuthReq()
    request.ctidTraderAccountId = config.ctid_trader_account_id
    request.accessToken = config.access_token

    deferred = client.send(request)
    deferred.addErrback(on_deferred_error, state)


def send_symbols_list(
    client: Client,
    config: RuntimeConfig,
    state: RuntimeState,
) -> None:
    """Запросити список символів."""
    state.current_stage = "symbols_list"
    logger.info(
        "Sending ProtoOASymbolsListReq for symbol '%s'...",
        config.symbol_name,
    )

    request = ProtoOASymbolsListReq()
    request.ctidTraderAccountId = config.ctid_trader_account_id
    request.includeArchivedSymbols = False

    deferred = client.send(request)
    deferred.addErrback(on_deferred_error, state)


def on_connected(
    client: Client,
    config: RuntimeConfig,
    state: RuntimeState,
) -> None:
    """Callback після підключення."""
    logger.info("CONNECTED to %s:%s", HOST, PORT)
    send_app_auth(client, config, state)


def on_disconnected(_client: Client, reason) -> None:
    """Callback після відключення."""
    logger.info("DISCONNECTED: %s", reason)
    stop_reactor()


def log_accounts(payload) -> None:
    """Залогувати список акаунтів."""
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


def log_symbol_match(payload, config: RuntimeConfig) -> None:
    """Знайти й залогувати symbol по symbolName."""
    symbols = list(getattr(payload, "symbol", []))
    if not symbols:
        logger.warning("Symbols list is empty.")
        return

    target = config.symbol_name.strip().upper()
    found = None

    for sym in symbols:
        name = str(getattr(sym, "symbolName", "")).upper()
        if name == target:
            found = sym
            break

    if found is None:
        logger.warning("SYMBOL NOT FOUND: %s", config.symbol_name)
        logger.info("Received symbols count: %s", len(symbols))

        preview = []
        for sym in symbols[:20]:
            preview.append(str(getattr(sym, "symbolName", "")))

        if preview:
            logger.info("First symbols preview: %s", ", ".join(preview))
        return

    logger.info("SYMBOL FOUND")
    logger.info(
        "symbolId=%s | symbolName=%s | digits=%s | pipPosition=%s | scheduleId=%s",
        getattr(found, "symbolId", None),
        getattr(found, "symbolName", None),
        getattr(found, "digits", None),
        getattr(found, "pipPosition", None),
        getattr(found, "scheduleId", None),
    )


def on_message_received(
    client: Client,
    message,
    config: RuntimeConfig,
    state: RuntimeState,
) -> None:
    """Головний callback для всіх повідомлень."""
    try:
        payload = Protobuf.extract(message)
    except Exception as exc:
        logger.debug("MESSAGE extract skipped: %s", exc)
        return

    logger.debug("MESSAGE: %s", payload)

    if message.payloadType == ProtoOAApplicationAuthRes().payloadType:
        logger.info("APPLICATION AUTH OK")
        send_get_account_list(client, config, state)
        return

    if message.payloadType == ProtoOAGetAccountListByAccessTokenRes().payloadType:
        log_accounts(payload)
        send_account_auth(client, config, state)
        return

    if message.payloadType == ProtoOAAccountAuthRes().payloadType:
        logger.info("ACCOUNT AUTH OK")
        send_symbols_list(client, config, state)
        return

    if message.payloadType == ProtoOASymbolsListRes().payloadType:
        state.symbol_response_received = True
        log_symbol_match(payload, config)
        schedule_shutdown(client, state, 0)
        return

    if message.payloadType == ProtoOAErrorRes().payloadType:
        logger.error(
            "API ERROR: %s | %s",
            getattr(payload, "errorCode", None),
            getattr(payload, "description", None),
        )
        schedule_shutdown(client, state, 0)
        return


def on_deferred_error(failure, state: RuntimeState) -> None:
    """
    Deferred errback.

    Не валимо reactor миттєво.
    Лише логуємо, на якому етапі збій.
    """
    logger.error(
        "Deferred error at stage '%s': %s",
        state.current_stage,
        failure,
    )


def on_timeout(
    client: Client,
    state: RuntimeState,
) -> None:
    """Загальний timeout на весь сценарій."""
    if state.symbol_response_received:
        return

    logger.error(
        "TIMEOUT: symbols flow not completed within %s seconds. Last stage: %s",
        WAIT_TIMEOUT_SECONDS,
        state.current_stage,
    )
    schedule_shutdown(client, state, 0)


def main() -> None:
    """Запуск ручного тесту отримання symbol by name."""
    client_id = read_non_empty("Введіть CLIENT_ID: ")
    client_secret = read_non_empty("Введіть CLIENT_SECRET: ")
    access_token = read_non_empty("Введіть ACCESS_TOKEN: ")
    ctid_trader_account_id = read_account_id()
    symbol_name = read_non_empty("Введіть SYMBOL_NAME (наприклад EURUSD): ")

    config = RuntimeConfig(
        client_id=client_id,
        client_secret=client_secret,
        access_token=access_token,
        ctid_trader_account_id=ctid_trader_account_id,
        symbol_name=symbol_name,
    )
    state = RuntimeState()

    logger.info("cTrader Step 04 — GET SYMBOLS")
    logger.info("Host: %s", HOST)
    logger.info("Port: %s", PORT)

    client = Client(HOST, PORT, TcpProtocol)

    client.setConnectedCallback(lambda c: on_connected(c, config, state))
    client.setDisconnectedCallback(on_disconnected)
    client.setMessageReceivedCallback(
        lambda c, message: on_message_received(c, message, config, state)
    )

    logger.info("Starting client service...")
    client.startService()

    reactor_call_later(WAIT_TIMEOUT_SECONDS, on_timeout, client, state)

    logger.info("Running Twisted reactor...")
    reactor_run()

    logger.info("DONE")


if __name__ == "__main__":
    main()
