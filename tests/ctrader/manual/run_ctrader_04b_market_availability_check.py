# run_ctrader_04b_market_availability_check.py
"""
Diagnostic: cTrader market availability check without placing orders.

RoadMap67:
- no input();
- no market order;
- reads ENV + tokens/tokens.json;
- connects to cTrader;
- verifies application/account auth;
- requests symbols list;
- finds configured symbol;
- reports MarketAvailabilityState.

Important:
This script does not prove broker schedule yet. It uses a safe weekend heuristic
for Forex and logs the symbol-list result. Broker error MARKET_CLOSED from order
execution remains only a fallback/confirmation, not the primary method.
"""

from __future__ import annotations

import logging
import os
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
    ProtoOAGetAccountListByAccessTokenReq,
    ProtoOAGetAccountListByAccessTokenRes,
    ProtoOASymbolsListReq,
    ProtoOASymbolsListRes,
)
from twisted.internet import reactor  # noqa
from twisted.internet.error import ReactorNotRunning  # noqa

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault(
    "TOKENS_PATH",
    str(PROJECT_ROOT / "tokens" / "tokens.json"),
)

from core import ctrader_symbols as ctr_symbols  # noqa: E402
from core.token_manager import refresh_if_needed  # noqa: E402
from engine.market_availability_state import (  # noqa: E402
    MarketAvailabilityState,
    detect_market_availability,
)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

HOST = EndPoints.PROTOBUF_DEMO_HOST
PORT = EndPoints.PROTOBUF_PORT
WAIT_TIMEOUT_SECONDS = 20

reactor_stop = getattr(reactor, "stop")
reactor_run = getattr(reactor, "run")
reactor_call_later = getattr(reactor, "callLater")


@dataclass(slots=True)
class RuntimeConfig:
    """Config для безпечного market availability diagnostic."""

    client_id: str
    client_secret: str
    access_token: str
    ctid_trader_account_id: int
    symbol_name: str
    symbol_id: int


@dataclass(slots=True)
class RuntimeState:
    """Mutable state diagnostic flow."""

    current_stage: str = "startup"
    completed: bool = False
    shutdown_scheduled: bool = False
    market_state: MarketAvailabilityState = MarketAvailabilityState.UNKNOWN
    market_state_source: str = "not_checked"


def stop_reactor() -> None:
    """Безпечно зупинити Twisted reactor."""
    try:
        reactor_stop()
    except ReactorNotRunning:
        pass


def shutdown(client: Client) -> None:
    """Коректно зупинити client service."""
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


def get_env_required(name: str) -> str:
    """Прочитати обов'язкову змінну середовища."""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Не задано змінну середовища {name}")
    return value


def load_runtime_config() -> RuntimeConfig:
    """Завантажити config без ручного вводу."""
    client_id = get_env_required("CTRADER_CLIENT_ID")
    client_secret = get_env_required("CTRADER_CLIENT_SECRET")
    account_id_text = get_env_required("CTRADER_ACCOUNT_ID")

    if not account_id_text.isdigit():
        raise RuntimeError("CTRADER_ACCOUNT_ID має бути цілим числом")

    symbol_name = os.getenv("CTRADER_SYMBOL_NAME", "EURUSD").strip().upper()
    if not symbol_name:
        symbol_name = "EURUSD"

    if symbol_name not in ctr_symbols.CTRADER_FOREX_BY_NAME:
        raise RuntimeError(f"Невідомий Forex symbol: {symbol_name}")

    symbol_id = ctr_symbols.get_enabled_symbol_id(symbol_name)

    tokens = refresh_if_needed()
    if not tokens:
        raise RuntimeError(
            "Немає чинного access_token. "
            "Спочатку онови tokens.json через run_ctrader_06a_place_order_login.py."
        )

    access_token = str(tokens.get("access_token", "")).strip()
    if not access_token:
        raise RuntimeError("tokens.json не містить access_token")

    return RuntimeConfig(
        client_id=client_id,
        client_secret=client_secret,
        access_token=access_token,
        ctid_trader_account_id=int(account_id_text),
        symbol_name=symbol_name,
        symbol_id=symbol_id,
    )


def detect_market_state_by_function(
    symbol_name: str,
) -> tuple[MarketAvailabilityState, str]:
    """Визначити market state через canonical engine function."""
    result = detect_market_availability(
        symbol_name,
        broker="CTRADER",
        asset_class="FOREX",
    )
    return result.state, result.source


def send_app_auth(
    client: Client,
    config: RuntimeConfig,
    state: RuntimeState,
) -> None:
    """Надіслати application auth."""
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
    """Запросити список account через access token."""
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
    """Надіслати account auth."""
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
    """Запросити список symbols без створення ордерів."""
    state.current_stage = "symbols_list"
    logger.info("Sending ProtoOASymbolsListReq...")

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
    """Callback після TCP connect."""
    logger.info("CONNECTED to %s:%s", HOST, PORT)
    send_app_auth(client, config, state)


def on_disconnected(_client: Client, reason) -> None:
    """Callback після disconnect."""
    logger.info("DISCONNECTED: %s", reason)
    stop_reactor()


def log_accounts(payload) -> None:
    """Залогувати accounts list."""
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


def find_symbol(payload, config: RuntimeConfig):
    """Знайти symbol у SymbolsListRes."""
    target = config.symbol_name.upper()
    for symbol in list(getattr(payload, "symbol", [])):
        if str(getattr(symbol, "symbolName", "")).upper() == target:
            return symbol
    return None


def handle_symbols_list(
    client: Client,
    payload,
    config: RuntimeConfig,
    state: RuntimeState,
) -> None:
    """Обробити SymbolsListRes і надрукувати market state."""
    symbol = find_symbol(payload, config)
    if symbol is None:
        logger.error("SYMBOL NOT FOUND: %s", config.symbol_name)
        state.market_state = MarketAvailabilityState.UNKNOWN
        state.market_state_source = "SYMBOL_NOT_FOUND"
    else:
        logger.info("SYMBOL FOUND")
        logger.info(
            "symbolId=%s | symbolName=%s | enabled=%s | scheduleId=%s",
            getattr(symbol, "symbolId", None),
            getattr(symbol, "symbolName", None),
            getattr(symbol, "enabled", None),
            getattr(symbol, "scheduleId", None),
        )
        state.market_state, state.market_state_source = detect_market_state_by_function(
            config.symbol_name
        )

    state.completed = True
    logger.info("MARKET_STATE=%s", state.market_state.value)
    logger.info("MARKET_STATE_SOURCE=%s", state.market_state_source)
    logger.info("IMPORTANT: no order was created by this diagnostic.")
    schedule_shutdown(client, state, 0)


def on_message_received(
    client: Client,
    message,
    config: RuntimeConfig,
    state: RuntimeState,
) -> None:
    """Головний callback для cTrader messages."""
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
        handle_symbols_list(client, payload, config, state)
        return

    if message.payloadType == ProtoOAErrorRes().payloadType:
        logger.error(
            "API ERROR at stage=%s: %s | %s",
            state.current_stage,
            getattr(payload, "errorCode", None),
            getattr(payload, "description", None),
        )
        state.market_state = MarketAvailabilityState.UNKNOWN
        state.market_state_source = "API_ERROR"
        state.completed = True
        schedule_shutdown(client, state, 0)
        return


def on_deferred_error(failure, state: RuntimeState) -> None:
    """Deferred errback logger."""
    logger.error("Deferred error at stage '%s': %s", state.current_stage, failure)


def on_timeout(
    client: Client,
    state: RuntimeState,
) -> None:
    """Загальний timeout diagnostic."""
    if state.completed:
        return

    logger.error(
        "TIMEOUT: market availability check not completed within %s seconds. "
        "Last stage: %s",
        WAIT_TIMEOUT_SECONDS,
        state.current_stage,
    )
    state.market_state = MarketAvailabilityState.UNKNOWN
    state.market_state_source = "TIMEOUT"
    schedule_shutdown(client, state, 0)


def main() -> int:
    """Запуск no-input market availability diagnostic."""
    config = load_runtime_config()
    state = RuntimeState()

    logger.info("cTrader Step 04b — MARKET AVAILABILITY CHECK")
    logger.info("Host: %s", HOST)
    logger.info("Port: %s", PORT)
    logger.info(
        "Params | accountId=%s | symbol=%s | symbolId=%s",
        config.ctid_trader_account_id,
        config.symbol_name,
        config.symbol_id,
    )

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

    if state.market_state == MarketAvailabilityState.UNKNOWN:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
