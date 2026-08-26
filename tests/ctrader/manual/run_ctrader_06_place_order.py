# run_ctrader_06_place_order.py
"""
Ручний тест: cTrader Open API place market order.

RoadMap53 / Step 06:
1) connect
2) application auth
3) list accounts by access token
4) account auth
5) resolve symbol name -> symbolId
6) convert FX lots -> cTrader Open API volume
7) send market order
8) wait execution event

Очікування:
- CONNECTED
- APPLICATION AUTH OK
- ACCOUNT LIST RECEIVED
- ACCOUNT AUTH OK
- ORDER SENT
- EXECUTION EVENT RECEIVED або ORDER ERROR EVENT
- DONE
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from ctrader_open_api import Client, Protobuf, TcpProtocol
from ctrader_open_api.endpoints import EndPoints

# noinspection PyUnresolvedReferences
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAAccountAuthReq,
    ProtoOAAccountAuthRes,
    ProtoOAApplicationAuthReq,
    ProtoOAApplicationAuthRes,
    ProtoOAErrorRes,
    ProtoOAExecutionEvent,
    ProtoOAGetAccountListByAccessTokenReq,
    ProtoOAGetAccountListByAccessTokenRes,
    ProtoOANewOrderReq,
    ProtoOAOrderErrorEvent,
)
from twisted.internet import reactor  # noqa
from twisted.internet.error import ReactorNotRunning  # noqa

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import ctrader_lot as ctr_lot  # noqa: E402
from core import ctrader_symbols as ctr_symbols  # noqa: E402

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

HOST = EndPoints.PROTOBUF_DEMO_HOST
PORT = EndPoints.PROTOBUF_PORT
WAIT_TIMEOUT_SECONDS = 15

ORDER_TYPE_MARKET = 1
TRADE_SIDE_BUY = 1
TRADE_SIDE_SELL = 2

EXECUTION_TYPE_ORDER_ACCEPTED = 2
EXECUTION_TYPE_ORDER_FILLED = 3
EXECUTION_TYPE_ORDER_REJECTED = 7

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
    symbol_id: int
    lots: float
    api_volume: int
    trade_side: int


@dataclass
class RuntimeState:
    order_sent: bool = False
    execution_received: bool = False
    shutdown_scheduled: bool = False


def stop_reactor() -> None:
    """Безпечно зупинити Twisted reactor."""
    try:
        reactor_stop()
    except ReactorNotRunning:
        pass


def shutdown(client: Client) -> None:
    """Зупинити клієнтський сервіс."""
    logger.info("Stopping client service...")
    client.stopService()


def schedule_shutdown(
    client: Client,
    state: RuntimeState,
    delay_seconds: int = 0,
) -> None:
    """Запланувати коректне завершення лише один раз."""
    if state.shutdown_scheduled:
        return
    state.shutdown_scheduled = True
    reactor_call_later(delay_seconds, shutdown, client)


def read_input_line(prompt_text: str) -> str:
    """Прочитати рядок вводу гарантовано як str."""
    raw = input(prompt_text)
    if raw is None:
        return ""
    return str(raw)


def read_non_empty(prompt_text: str) -> str:
    """Прочитати непорожній рядок."""
    while True:
        value = read_input_line(prompt_text).strip()
        if value:
            return value
        logger.error("Порожнє значення не допускається.")


def read_positive_int(prompt_text: str, field_name: str) -> int:
    """Прочитати додатне ціле число."""
    while True:
        raw = read_input_line(prompt_text).strip()

        if not raw:
            logger.error("%s не може бути порожнім.", field_name)
            continue
        if not raw.isdigit():
            logger.error("%s має бути цілим числом.", field_name)
            continue

        value = int(raw)
        if value <= 0:
            logger.error("%s має бути > 0.", field_name)
            continue

        return value
    raise RuntimeError("Unreachable code in read_positive_int")


def read_positive_float(prompt_text: str, field_name: str) -> float:
    """Прочитати додатне float число."""
    while True:
        raw = read_input_line(prompt_text).strip().replace(",", ".")

        if not raw:
            logger.error("%s не може бути порожнім.", field_name)
            continue

        try:
            value = float(raw)
        except ValueError:
            logger.error("%s має бути числом.", field_name)
            continue

        if value <= 0:
            logger.error("%s має бути > 0.", field_name)
            continue

        return value
    raise RuntimeError("Unreachable code in read_positive_float")


def read_trade_side() -> int:
    """Прочитати сторону угоди BUY/SELL."""
    while True:
        raw = read_input_line("Введіть TRADE_SIDE (BUY/SELL): ").strip().upper()
        if raw == "BUY":
            return TRADE_SIDE_BUY
        if raw == "SELL":
            return TRADE_SIDE_SELL
        logger.error("TRADE_SIDE має бути BUY або SELL.")


def read_symbol_name() -> str:
    """Прочитати symbol name і перевірити його по таблиці."""
    while True:
        raw = (
            read_input_line("Введіть SYMBOL_NAME (наприклад EURUSD): ").strip().upper()
        )

        if not raw:
            logger.error("SYMBOL_NAME не може бути порожнім.")
            continue
        if raw not in ctr_symbols.CTRADER_FOREX_BY_NAME:
            logger.error("Невідомий Forex symbol: %s", raw)
            logger.info(
                "Приклади доступних symbols: %s",
                ", ".join(sorted(list(ctr_symbols.CTRADER_FOREX_BY_NAME.keys()))[:15]),
            )
            continue
        try:
            ctr_symbols.get_enabled_symbol_id(raw)
        except ValueError as exc:
            logger.error("%s", exc)
            continue

        return raw
    raise RuntimeError("Unreachable code in read_symbol_name")


def trade_side_name(value: int) -> str:
    """Повернути текстове ім'я trade side."""
    if value == TRADE_SIDE_BUY:
        return "BUY"
    if value == TRADE_SIDE_SELL:
        return "SELL"
    return f"UNKNOWN({value})"


def execution_type_name(value: int) -> str:
    """Повернути текстове ім'я execution type."""
    if value == EXECUTION_TYPE_ORDER_ACCEPTED:
        return "ORDER_ACCEPTED"
    if value == EXECUTION_TYPE_ORDER_FILLED:
        return "ORDER_FILLED"
    if value == EXECUTION_TYPE_ORDER_REJECTED:
        return "ORDER_REJECTED"
    return f"UNKNOWN({value})"


def send_app_auth(client: Client, config: RuntimeConfig) -> None:
    """Надіслати auth додатка."""
    logger.info("Sending ProtoOAApplicationAuthReq...")

    request = ProtoOAApplicationAuthReq()
    request.clientId = config.client_id
    request.clientSecret = config.client_secret

    deferred = client.send(request)
    deferred.addErrback(on_deferred_error)


def send_get_account_list(client: Client, config: RuntimeConfig) -> None:
    """Запросити список акаунтів по access token."""
    logger.info("Sending ProtoOAGetAccountListByAccessTokenReq...")

    request = ProtoOAGetAccountListByAccessTokenReq()
    request.accessToken = config.access_token

    deferred = client.send(request)
    deferred.addErrback(on_deferred_error)


def send_account_auth(client: Client, config: RuntimeConfig) -> None:
    """Надіслати auth торгового акаунта."""
    logger.info("Sending ProtoOAAccountAuthReq...")

    request = ProtoOAAccountAuthReq()
    request.ctidTraderAccountId = config.ctid_trader_account_id
    request.accessToken = config.access_token

    deferred = client.send(request)
    deferred.addErrback(on_deferred_error)


def send_new_market_order(
    client: Client,
    config: RuntimeConfig,
    state: RuntimeState,
) -> None:
    """Надіслати market order."""
    logger.info(
        "Sending ProtoOANewOrderReq... symbol=%s | symbolId=%s | side=%s | "
        "lots=%s | api_volume=%s",
        config.symbol_name,
        config.symbol_id,
        trade_side_name(config.trade_side),
        config.lots,
        config.api_volume,
    )

    request = ProtoOANewOrderReq()
    request.ctidTraderAccountId = config.ctid_trader_account_id
    request.symbolId = config.symbol_id
    request.orderType = ORDER_TYPE_MARKET
    request.tradeSide = config.trade_side
    request.volume = config.api_volume
    request.comment = "LavrGPT05 RoadMap53 Step06"
    request.label = "RM53_STEP06"

    deferred = client.send(request)
    deferred.addErrback(on_deferred_error)

    state.order_sent = True
    logger.info("ORDER SENT")


def on_connected(client: Client, config: RuntimeConfig) -> None:
    """Callback після підключення."""
    logger.info("CONNECTED to %s:%s", HOST, PORT)
    send_app_auth(client, config)


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


def log_execution_event(payload) -> tuple[int | None, int | None]:
    """Залогувати execution event."""
    execution_type = getattr(payload, "executionType", None)
    order = getattr(payload, "order", None)
    position = getattr(payload, "position", None)
    deal = getattr(payload, "deal", None)

    order_id = getattr(order, "orderId", None)
    position_id = getattr(position, "positionId", None)
    execution_price = getattr(order, "executionPrice", None)
    executed_volume = getattr(order, "executedVolume", None)
    deal_id = getattr(deal, "dealId", None)

    logger.info(
        "EXECUTION EVENT RECEIVED | executionType=%s | orderId=%s | "
        "positionId=%s | dealId=%s | executionPrice=%s | executedVolume=%s",
        execution_type_name(execution_type),
        order_id,
        position_id,
        deal_id,
        execution_price,
        executed_volume,
    )

    if order is not None:
        trade_data = getattr(order, "tradeData", None)
        logger.info(
            "ORDER DATA | symbolId=%s | tradeSide=%s | volume=%s | orderType=%s",
            getattr(trade_data, "symbolId", None),
            getattr(trade_data, "tradeSide", None),
            getattr(trade_data, "volume", None),
            getattr(order, "orderType", None),
        )

    if position is not None:
        trade_data = getattr(position, "tradeData", None)
        logger.info(
            "POSITION DATA | positionId=%s | symbolId=%s | tradeSide=%s | "
            "volume=%s | price=%s",
            getattr(position, "positionId", None),
            getattr(trade_data, "symbolId", None),
            getattr(trade_data, "tradeSide", None),
            getattr(trade_data, "volume", None),
            getattr(position, "price", None),
        )

    return order_id, position_id


def handle_execution_event(
    client: Client,
    payload,
    state: RuntimeState,
) -> None:
    """Обробити execution event."""
    state.execution_received = True

    order_id, position_id = log_execution_event(payload)
    execution_type = getattr(payload, "executionType", None)

    if execution_type == EXECUTION_TYPE_ORDER_ACCEPTED:
        logger.info("ORDER ACCEPTED | orderId=%s", order_id)
        return

    if execution_type == EXECUTION_TYPE_ORDER_FILLED:
        logger.info(
            "POSITION OPENED / ORDER FILLED | orderId=%s | positionId=%s",
            order_id,
            position_id,
        )
        schedule_shutdown(client, state, 0)
        return

    if execution_type == EXECUTION_TYPE_ORDER_REJECTED:
        logger.error("ORDER REJECTED by execution event.")
        schedule_shutdown(client, state, 0)
        return

    logger.warning("Unhandled executionType received, waiting for next event...")


def handle_order_error_event(
    client: Client,
    payload,
    state: RuntimeState,
) -> None:
    """Обробити окрему подію помилки ордера."""
    logger.error(
        "ORDER ERROR EVENT | errorCode=%s | description=%s | "
        "orderId=%s | positionId=%s",
        getattr(payload, "errorCode", None),
        getattr(payload, "description", None),
        getattr(payload, "orderId", None),
        getattr(payload, "positionId", None),
    )
    schedule_shutdown(client, state, 0)


def on_timeout(client: Client, state: RuntimeState) -> None:
    """Таймаут очікування execution event."""
    if state.execution_received:
        return

    logger.error(
        "TIMEOUT: execution event not received within %s seconds.",
        WAIT_TIMEOUT_SECONDS,
    )
    schedule_shutdown(client, state, 0)


def on_message_received(
    client: Client,
    message,
    config: RuntimeConfig,
    state: RuntimeState,
) -> None:
    """Головний message callback."""
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
        send_new_market_order(client, config, state)
        return

    if message.payloadType == ProtoOAExecutionEvent().payloadType:
        handle_execution_event(client, payload, state)
        return

    if message.payloadType == ProtoOAOrderErrorEvent().payloadType:
        handle_order_error_event(client, payload, state)
        return

    if message.payloadType == ProtoOAErrorRes().payloadType:
        logger.error(
            "API ERROR: %s | %s",
            getattr(payload, "errorCode", None),
            getattr(payload, "description", None),
        )
        schedule_shutdown(client, state, 0)
        return


def on_deferred_error(failure) -> None:
    """Deferred errback."""
    logger.error("Deferred error: %s", failure)
    stop_reactor()


def main() -> None:
    """Запуск ручного тесту place market order."""
    client_id = read_non_empty("Введіть CLIENT_ID: ")
    client_secret = read_non_empty("Введіть CLIENT_SECRET: ")
    access_token = read_non_empty("Введіть ACCESS_TOKEN: ")
    ctid_trader_account_id = read_positive_int(
        "Введіть CTID_TRADER_ACCOUNT_ID (accountId): ",
        "CTID_TRADER_ACCOUNT_ID",
    )
    symbol_name = read_symbol_name()
    symbol_id = ctr_symbols.get_enabled_symbol_id(symbol_name)
    lots = read_positive_float(
        "Введіть LOTS (наприклад 0.01): ",
        "LOTS",
    )
    lots = ctr_lot.normalize_fx_lots(lots)
    api_volume = ctr_lot.lots_to_api_volume(lots)
    api_volume = ctr_lot.normalize_fx_api_volume(api_volume)
    trade_side = read_trade_side()

    config = RuntimeConfig(
        client_id=client_id,
        client_secret=client_secret,
        access_token=access_token,
        ctid_trader_account_id=ctid_trader_account_id,
        symbol_name=symbol_name,
        symbol_id=symbol_id,
        lots=lots,
        api_volume=api_volume,
        trade_side=trade_side,
    )
    state = RuntimeState()

    logger.info("cTrader Step 06 — PLACE MARKET ORDER")
    logger.info("Host: %s", HOST)
    logger.info("Port: %s", PORT)
    logger.info(
        "Order params | accountId=%s | symbol=%s | symbolId=%s | side=%s | "
        "lots=%s | api_volume=%s",
        config.ctid_trader_account_id,
        config.symbol_name,
        config.symbol_id,
        trade_side_name(config.trade_side),
        config.lots,
        config.api_volume,
    )

    client = Client(HOST, PORT, TcpProtocol)

    client.setConnectedCallback(lambda c: on_connected(c, config))
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
