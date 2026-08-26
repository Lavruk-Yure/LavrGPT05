# run_ctrader_09_session_console.py
"""
RoadMap55 / Step 11:
session-based console for cTrader Open API.

База:
- working pattern зі Step 07
- amend SL/TP зі Step 08
- close position у тій самій сесії
- без нового core-модуля
- без GUI
- одна жива сесія
- кілька команд у межах одного connect/auth

Поточна версія меню:
1 — get positions
2 — amend SL/TP
3 — close position
0 — exit

ENV:
- CTRADER_CLIENT_ID
- CTRADER_CLIENT_SECRET
- CTRADER_ACCOUNT_ID

Токени:
- LavrGPT05/tokens/tokens.json
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from getpass import getpass
from pathlib import Path

import requests
from ctrader_open_api import Client, Protobuf, TcpProtocol
from ctrader_open_api.endpoints import EndPoints

# noinspection PyUnresolvedReferences
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAAccountAuthReq,
    ProtoOAAccountAuthRes,
    ProtoOAAmendPositionSLTPReq,
    ProtoOAApplicationAuthReq,
    ProtoOAApplicationAuthRes,
    ProtoOACancelOrderReq,
    ProtoOAClosePositionReq,
    ProtoOAErrorRes,
    ProtoOAExecutionEvent,
    ProtoOAGetAccountListByAccessTokenReq,
    ProtoOAGetAccountListByAccessTokenRes,
    ProtoOANewOrderReq,
    ProtoOAOrderErrorEvent,
    ProtoOAReconcileReq,
    ProtoOAReconcileRes,
)
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service
from selenium.webdriver.support import expected_conditions as EC  # noqa
from selenium.webdriver.support.ui import WebDriverWait
from twisted.internet import reactor  # noqa
from twisted.internet.error import ReactorNotRunning  # noqa

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault(
    "TOKENS_PATH",
    str(PROJECT_ROOT / "tokens" / "tokens.json"),
)

from core import ctrader_lot as ctr_lot  # noqa: E402
from core import ctrader_symbols as ctr_symbols  # noqa: E402
from core.token_manager import load_tokens, refresh_if_needed, save_tokens  # noqa: E402

INPUT_LOCK = threading.Lock()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

HOST = EndPoints.PROTOBUF_DEMO_HOST
PORT = EndPoints.PROTOBUF_PORT
WAIT_TIMEOUT_SECONDS = 20

ORDER_TYPE_MARKET = 1
ORDER_TYPE_LIMIT = 2
ORDER_TYPE_STOP = 3
ORDER_TYPE_STOP_LIMIT = 6
TIME_IN_FORCE_GOOD_TILL_CANCEL = 2

TRADE_SIDE_BUY = 1
TRADE_SIDE_SELL = 2

EXECUTION_TYPE_ORDER_ACCEPTED = 2
EXECUTION_TYPE_ORDER_FILLED = 3
EXECUTION_TYPE_ORDER_REPLACED = 4
EXECUTION_TYPE_ORDER_CANCELLED = 5
EXECUTION_TYPE_ORDER_REJECTED = 7
EXECUTION_TYPE_ORDER_CANCEL_REJECTED = 8

REDIRECT_URI = "http://localhost:8080/"
AUTH_SCOPE = "trading"
EDGE_DRIVER_PATH = r"C:\WebDriver\msedgedriver.exe"

reactor_stop = getattr(reactor, "stop")
reactor_run = getattr(reactor, "run")
reactor_call_from_thread = getattr(reactor, "callFromThread")


@dataclass
class RuntimeConfig:
    client_id: str
    client_secret: str
    access_token: str
    ctid_trader_account_id: int


@dataclass
class AmendRequest:
    position_id: int
    stop_loss: float
    take_profit: float


@dataclass
class PendingOrderRequest:
    symbol_name: str
    symbol_id: int
    lots: float
    api_volume: int
    trade_side: int
    order_type: int
    limit_price: float | None = None
    stop_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    slippage_in_points: int | None = None


@dataclass
class SessionState:
    session_ready: bool = False
    reactor_thread_started: bool = False
    shutdown_requested: bool = False

    session_ready_event: threading.Event = field(default_factory=threading.Event)
    reconcile_event: threading.Event = field(default_factory=threading.Event)
    amend_event: threading.Event = field(default_factory=threading.Event)
    order_event: threading.Event = field(default_factory=threading.Event)
    stop_event: threading.Event = field(default_factory=threading.Event)

    last_error_text: str = ""
    last_reconcile_payload = None
    last_amend_position = None
    last_execution_order = None
    last_execution_position = None
    pending_amend: AmendRequest | None = None
    pending_order_request: PendingOrderRequest | None = None
    pending_cancel_order_id: int | None = None


def read_input_line(prompt_text: str) -> str:
    """Безпечний input для роботи разом із reactor/logging."""
    with INPUT_LOCK:
        try:
            raw = input(prompt_text)
        except EOFError:
            return ""

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
    """Прочитати додатне int число."""
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


def read_optional_positive_float(prompt_text: str, field_name: str) -> float | None:
    """Прочитати optional додатне float число."""
    while True:
        raw = read_input_line(prompt_text).strip().replace(",", ".")

        if not raw:
            return None

        try:
            value = float(raw)
        except ValueError:
            logger.error("%s має бути числом або порожнім.", field_name)
            continue

        if value <= 0:
            logger.error("%s має бути > 0.", field_name)
            continue

        return value


def read_non_negative_int(prompt_text: str, field_name: str) -> int:
    """Прочитати int число >= 0."""
    while True:
        raw = read_input_line(prompt_text).strip()

        if not raw:
            logger.error("%s не може бути порожнім.", field_name)
            continue

        if not raw.isdigit():
            logger.error("%s має бути цілим числом.", field_name)
            continue

        value = int(raw)
        if value < 0:
            logger.error("%s має бути >= 0.", field_name)
            continue

        return value

    raise RuntimeError("Unreachable code in read_non_negative_int")


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
        return raw

    raise RuntimeError("Unreachable code in read_symbol_name")


def read_pending_order_type() -> int:
    """Прочитати тип pending order."""
    while True:
        raw = (
            read_input_line("Введіть ORDER_TYPE (LIMIT/STOP/STOP_LIMIT): ")
            .strip()
            .upper()
        )
        if raw == "LIMIT":
            return ORDER_TYPE_LIMIT
        if raw == "STOP":
            return ORDER_TYPE_STOP
        if raw in {"STOP_LIMIT", "STOP-LIMIT", "STOPLIMIT"}:
            return ORDER_TYPE_STOP_LIMIT
        logger.error("ORDER_TYPE має бути LIMIT, STOP або STOP_LIMIT.")


def get_env_required(name: str) -> str:
    """Прочитати обов'язкову змінну середовища."""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Не задано змінну середовища {name}")
    return value


def load_env_config() -> tuple[str, str, int]:
    """Завантажити cTrader credentials з env."""
    client_id = get_env_required("CTRADER_CLIENT_ID")
    client_secret = get_env_required("CTRADER_CLIENT_SECRET")
    account_id_text = get_env_required("CTRADER_ACCOUNT_ID")

    if not account_id_text.isdigit():
        raise RuntimeError("CTRADER_ACCOUNT_ID має бути цілим числом")

    return client_id, client_secret, int(account_id_text)


def exchange_auth_code_for_tokens(
    auth_code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> dict | None:
    """Обміняти authorization code на token set."""
    token_url = "https://openapi.ctrader.com/apps/token"
    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    response = requests.post(
        token_url,
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        timeout=30,
    )
    if response.status_code == 200:
        return response.json()

    logger.error(
        "Помилка при отриманні токену: HTTP %s | body=%s",
        response.status_code,
        response.text,
    )
    return None


def run_login_password_auth_flow(
    client_id: str,
    client_secret: str,
    login: str,
    password: str,
) -> dict:
    """Отримати нові токени через Selenium login/password flow."""
    redirect_uri_encoded = urllib.parse.quote(REDIRECT_URI, safe="")
    auth_url = (
        "https://id.ctrader.com/my/settings/openapi/grantingaccess/"
        f"?client_id={client_id}&redirect_uri={redirect_uri_encoded}"
        f"&scope={AUTH_SCOPE}&product=web"
    )

    logger.info("Starting Selenium auth flow...")
    logger.info("Auth URL prepared.")
    logger.info("Edge driver path: %s", EDGE_DRIVER_PATH)

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    service = Service(executable_path=EDGE_DRIVER_PATH)
    driver = webdriver.Edge(service=service, options=options)

    auth_code = None
    try:
        driver.get(auth_url)

        wait = WebDriverWait(driver, 20)
        wait.until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        email_input = wait.until(EC.visibility_of_element_located((By.NAME, "id")))
        email_input.clear()
        email_input.send_keys(login)

        password_input = wait.until(
            EC.visibility_of_element_located((By.NAME, "password"))
        )
        password_input.clear()
        password_input.send_keys(password)

        login_button = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, 'button.auth-form-btn[type="submit"]')
            )
        )
        login_button.click()
        logger.info("Log In clicked.")

        try:
            permission_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "auth-btn-allow"))
            )
            driver.execute_script(
                "arguments[0].scrollIntoView(true);",
                permission_button,
            )
            time.sleep(1)
            permission_button.click()
            logger.info("Access permission granted.")
        except Exception as exc:
            logger.info("Permission button not found or already granted: %s", exc)

        wait.until(EC.url_contains(REDIRECT_URI))
        current_url = driver.current_url
        logger.info("Redirect URL received.")

        parsed_url = urllib.parse.urlparse(current_url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        auth_code = query_params.get("code", [None])[0]

    finally:
        try:
            driver.quit()
        except Exception as exc:
            logger.warning("Не вдалося коректно закрити WebDriver: %s", exc)

    if not auth_code:
        raise RuntimeError("Authorization code не отримано.")

    token_data = exchange_auth_code_for_tokens(
        auth_code=auth_code,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=REDIRECT_URI,
    )
    if not token_data:
        raise RuntimeError("Не вдалося отримати token set по authorization code.")

    expires_in = int(token_data.get("expires_in", 0))
    token_data["expires_at"] = int(time.time()) + expires_in
    token_data["_comment"] = "Отримано через run_ctrader_09_session_console.py"
    return token_data


def ensure_access_token(
    client_id: str,
    client_secret: str,
) -> str:
    """Забезпечити валідний access token."""
    try:
        tokens = refresh_if_needed()
    except Exception as exc:
        logger.warning("refresh_if_needed() failed: %s", exc)
        tokens = None

    if tokens and tokens.get("access_token"):
        logger.info("Access token отримано через token_manager.")
        return str(tokens["access_token"])

    try:
        tokens = load_tokens()
    except Exception as exc:
        logger.warning("load_tokens() failed: %s", exc)
        tokens = None

    if tokens and tokens.get("access_token"):
        logger.info("Using existing access_token from tokens.json.")
        return str(tokens["access_token"])

    logger.info("Existing token unavailable. Login/password required.")
    login = read_non_empty("Введіть LOGIN (Email або cTrader ID): ")
    password = getpass("Введіть PASSWORD: ")

    new_tokens = run_login_password_auth_flow(
        client_id=client_id,
        client_secret=client_secret,
        login=login,
        password=password,
    )
    save_tokens(new_tokens)

    access_token = str(new_tokens.get("access_token", "")).strip()
    if not access_token:
        raise RuntimeError("Після авторизації access_token порожній.")

    logger.info("New access token obtained and saved.")
    return access_token


def trade_side_name(value: int | None) -> str:
    """Повернути текстове ім'я trade side."""
    if value == TRADE_SIDE_BUY:
        return "BUY"
    if value == TRADE_SIDE_SELL:
        return "SELL"
    return f"UNKNOWN({value})"


def order_type_name(value: int | None) -> str:
    """Повернути текстове ім'я order type."""
    if value == ORDER_TYPE_MARKET:
        return "MARKET"
    if value == ORDER_TYPE_LIMIT:
        return "LIMIT"
    if value == ORDER_TYPE_STOP:
        return "STOP"
    if value == ORDER_TYPE_STOP_LIMIT:
        return "STOP_LIMIT"
    return f"UNKNOWN({value})"


def order_status_name(value: int | None) -> str:
    """Повернути текстове ім'я order status."""
    if value == 1:
        return "ACCEPTED"
    if value == 2:
        return "FILLED"
    if value == 3:
        return "REJECTED"
    if value == 4:
        return "EXPIRED"
    if value == 5:
        return "CANCELLED"
    return f"UNKNOWN({value})"


def symbol_name_by_id(symbol_id: int | None) -> str:
    """Повернути symbol name по symbolId."""
    if symbol_id is None:
        return "UNKNOWN_SYMBOL_ID(None)"
    name = ctr_symbols.CTRADER_FOREX_NAME_BY_ID.get(symbol_id)
    if name:
        return name
    return f"UNKNOWN_SYMBOL_ID({symbol_id})"


def format_lots(api_volume: int) -> float:
    """Перевести api volume у FX lots для читабельного логу."""
    try:
        return ctr_lot.api_volume_to_lots(api_volume)
    except Exception:  # noqa
        return 0.0


def format_money(value) -> str:
    """Форматувати число для консолі."""
    if value is None:
        return ""
    try:
        return f"{float(value):.5f}"
    except Exception:  # noqa
        return str(value)


def execution_type_name(value: int | None) -> str:
    """Текстове ім'я execution type."""
    if value == EXECUTION_TYPE_ORDER_ACCEPTED:
        return "ORDER_ACCEPTED"
    if value == EXECUTION_TYPE_ORDER_FILLED:
        return "ORDER_FILLED"
    if value == EXECUTION_TYPE_ORDER_REPLACED:
        return "ORDER_REPLACED"
    if value == EXECUTION_TYPE_ORDER_CANCELLED:
        return "ORDER_CANCELLED"
    if value == EXECUTION_TYPE_ORDER_REJECTED:
        return "ORDER_REJECTED"
    if value == EXECUTION_TYPE_ORDER_CANCEL_REJECTED:
        return "ORDER_CANCEL_REJECTED"
    return f"UNKNOWN({value})"


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


def print_positions_from_reconcile(payload) -> None:
    """Розібрати й надрукувати позиції та pending orders з ProtoOAReconcileRes."""
    positions = list(getattr(payload, "position", []))
    orders = list(getattr(payload, "order", []))

    print()
    print("=== RECONCILE ===")
    print(f"positions_count={len(positions)} | orders_count={len(orders)}")
    print()

    print("=== POSITIONS ===")
    if not positions:
        print("OPEN POSITIONS: none")
        print()
    else:
        for pos in positions:
            position_id = getattr(pos, "positionId", None)
            trade_data = getattr(pos, "tradeData", None)

            symbol_id = getattr(trade_data, "symbolId", None) if trade_data else None
            api_volume = getattr(trade_data, "volume", 0) if trade_data else 0
            trade_side = getattr(trade_data, "tradeSide", None) if trade_data else None
            label = getattr(trade_data, "label", "") if trade_data else ""
            comment = getattr(trade_data, "comment", "") if trade_data else ""

            price = getattr(pos, "price", None)
            swap = getattr(pos, "swap", None)
            commission = getattr(pos, "commission", None)
            used_margin = getattr(pos, "usedMargin", None)
            position_status = getattr(pos, "positionStatus", None)
            utc_last_update = getattr(pos, "utcLastUpdateTimestamp", None)
            stop_loss = getattr(pos, "stopLoss", None)
            take_profit = getattr(pos, "takeProfit", None)

            print(
                "positionId=%s | symbol=%s | symbolId=%s | side=%s | "
                "api_volume=%s | lots=%.2f | price=%s | SL=%s | TP=%s | "
                "status=%s | commission=%s | swap=%s | used_margin=%s | "
                "label=%s | comment=%s | utc_last_update=%s"
                % (
                    position_id,
                    symbol_name_by_id(symbol_id),
                    symbol_id,
                    trade_side_name(trade_side),
                    api_volume,
                    format_lots(api_volume),
                    price,
                    stop_loss,
                    take_profit,
                    position_status,
                    commission,
                    swap,
                    used_margin,
                    label,
                    comment,
                    utc_last_update,
                )
            )
        print()

    print("=== PENDING ORDERS ===")
    if not orders:
        print("PENDING ORDERS: none")
        print()
        return

    for order in orders:
        trade_data = getattr(order, "tradeData", None)
        symbol_id = getattr(trade_data, "symbolId", None) if trade_data else None
        api_volume = getattr(trade_data, "volume", 0) if trade_data else 0
        trade_side = getattr(trade_data, "tradeSide", None) if trade_data else None
        label = getattr(trade_data, "label", "") if trade_data else ""
        comment = getattr(trade_data, "comment", "") if trade_data else ""

        print(
            "orderId=%s | symbol=%s | symbolId=%s | side=%s | type=%s | "
            "status=%s | api_volume=%s | lots=%.2f | limit=%s | stop=%s | "
            "SL=%s | TP=%s | slippage=%s | label=%s | comment=%s | utc_last_update=%s"
            % (
                getattr(order, "orderId", None),
                symbol_name_by_id(symbol_id),
                symbol_id,
                trade_side_name(trade_side),
                order_type_name(getattr(order, "orderType", None)),
                order_status_name(getattr(order, "orderStatus", None)),
                api_volume,
                format_lots(api_volume),
                format_money(getattr(order, "limitPrice", None)),
                format_money(getattr(order, "stopPrice", None)),
                format_money(getattr(order, "stopLoss", None)),
                format_money(getattr(order, "takeProfit", None)),
                getattr(order, "slippageInPoints", None),
                label,
                comment,
                getattr(order, "utcLastUpdateTimestamp", None),
            )
        )
    print()


def find_position_in_reconcile(payload, position_id: int):
    """Знайти позицію в ProtoOAReconcileRes по positionId."""
    positions = list(getattr(payload, "position", []))
    for pos in positions:
        if getattr(pos, "positionId", None) == position_id:
            return pos
    return None


def find_order_in_reconcile(payload, order_id: int):
    """Знайти pending order у ProtoOAReconcileRes по orderId."""
    orders = list(getattr(payload, "order", []))
    for order in orders:
        if getattr(order, "orderId", None) == order_id:
            return order
    return None


def wait_event(event: threading.Event, timeout: int, what: str) -> None:
    """Дочекатися threading event з таймаутом."""
    if event.wait(timeout):
        return
    raise TimeoutError(f"TIMEOUT: {what} not received within {timeout} seconds.")


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


def send_reconcile(client: Client, config: RuntimeConfig) -> None:
    """Запросити reconcile з позиціями/ордерними станами."""
    logger.info("Sending ProtoOAReconcileReq...")

    request = ProtoOAReconcileReq()
    request.ctidTraderAccountId = config.ctid_trader_account_id

    deferred = client.send(request)
    deferred.addErrback(on_deferred_error)


def send_amend_position_sltp(
    client: Client,
    config: RuntimeConfig,
    amend: AmendRequest,
) -> None:
    """Надіслати amend SL/TP для вже відкритої позиції."""
    logger.info(
        "Sending ProtoOAAmendPositionSLTPReq... positionId=%s | SL=%s | TP=%s",
        amend.position_id,
        amend.stop_loss,
        amend.take_profit,
    )

    request = ProtoOAAmendPositionSLTPReq()
    request.ctidTraderAccountId = config.ctid_trader_account_id
    request.positionId = amend.position_id
    request.stopLoss = amend.stop_loss
    request.takeProfit = amend.take_profit

    deferred = client.send(request)
    deferred.addErrback(on_deferred_error)


def send_close_position(
    client: Client,
    config: RuntimeConfig,
    position_id: int,
    volume: int,
) -> None:
    """Надіслати close position request."""
    logger.info(
        "Sending ProtoOAClosePositionReq... positionId=%s | volume=%s",
        position_id,
        volume,
    )

    request = ProtoOAClosePositionReq()
    request.ctidTraderAccountId = config.ctid_trader_account_id
    request.positionId = position_id
    request.volume = volume

    deferred = client.send(request)
    deferred.addErrback(on_deferred_error)


def send_new_pending_order(
    client: Client,
    config: RuntimeConfig,
    pending: PendingOrderRequest,
) -> None:
    """Надіслати pending order."""
    logger.info(
        "Sending ProtoOANewOrderReq... symbol=%s | symbolId=%s | side=%s | "
        "type=%s | lots=%s | api_volume=%s | limit=%s | stop=%s | "
        "SL=%s | TP=%s | slippage=%s",
        pending.symbol_name,
        pending.symbol_id,
        trade_side_name(pending.trade_side),
        order_type_name(pending.order_type),
        pending.lots,
        pending.api_volume,
        pending.limit_price,
        pending.stop_price,
        pending.stop_loss,
        pending.take_profit,
        pending.slippage_in_points,
    )

    request = ProtoOANewOrderReq()
    request.ctidTraderAccountId = config.ctid_trader_account_id
    request.symbolId = pending.symbol_id
    request.orderType = pending.order_type
    request.tradeSide = pending.trade_side
    request.volume = pending.api_volume
    request.timeInForce = TIME_IN_FORCE_GOOD_TILL_CANCEL
    request.comment = "LavrGPT05 RoadMap56 pending order"
    request.label = "RM56_PENDING"

    if pending.limit_price is not None:
        request.limitPrice = pending.limit_price
    if pending.stop_price is not None:
        request.stopPrice = pending.stop_price
    if pending.stop_loss is not None:
        request.stopLoss = pending.stop_loss
    if pending.take_profit is not None:
        request.takeProfit = pending.take_profit
    if pending.slippage_in_points is not None:
        request.slippageInPoints = pending.slippage_in_points

    deferred = client.send(request)
    deferred.addErrback(on_deferred_error)


def send_cancel_pending_order(
    client: Client,
    config: RuntimeConfig,
    order_id: int,
) -> None:
    """Надіслати cancel pending order request."""
    logger.info("Sending ProtoOACancelOrderReq... orderId=%s", order_id)

    request = ProtoOACancelOrderReq()
    request.ctidTraderAccountId = config.ctid_trader_account_id
    request.orderId = order_id

    deferred = client.send(request)
    deferred.addErrback(on_deferred_error)


def on_connected(client: Client, config: RuntimeConfig) -> None:
    """Callback після підключення."""
    logger.info("CONNECTED to %s:%s", HOST, PORT)
    send_app_auth(client, config)


def on_disconnected(_client: Client, reason) -> None:
    """Callback після відключення."""
    logger.info("DISCONNECTED: %s", reason)


def handle_execution_event(payload, state: SessionState) -> None:
    """Обробити execution event для amend/close/pending/cancel."""
    execution_type = getattr(payload, "executionType", None)
    position = getattr(payload, "position", None)
    order = getattr(payload, "order", None)

    position_id = getattr(position, "positionId", None) if position else None
    order_id = getattr(order, "orderId", None) if order else None

    logger.info(
        "EXECUTION EVENT RECEIVED | executionType=%s | orderId=%s | positionId=%s",
        execution_type_name(execution_type),
        order_id,
        position_id,
    )

    state.last_execution_order = order
    state.last_execution_position = position

    if state.pending_order_request is not None:
        if execution_type == EXECUTION_TYPE_ORDER_REJECTED:
            state.last_error_text = "PENDING ORDER REJECTED by execution event."
            state.order_event.set()
            return

        if execution_type == EXECUTION_TYPE_ORDER_ACCEPTED and order is not None:
            logger.info(
                "PENDING ORDER ACCEPTED | orderId=%s | type=%s",
                order_id,
                order_type_name(getattr(order, "orderType", None)),
            )
            state.order_event.set()
            return

    if state.pending_cancel_order_id is not None:
        if execution_type in (
            EXECUTION_TYPE_ORDER_REJECTED,
            EXECUTION_TYPE_ORDER_CANCEL_REJECTED,
        ):
            state.last_error_text = "CANCEL PENDING ORDER REJECTED by execution event."
            state.order_event.set()
            return

        if (
            execution_type == EXECUTION_TYPE_ORDER_CANCELLED
            and order_id == state.pending_cancel_order_id
        ):
            logger.info("PENDING ORDER CANCELLED | orderId=%s", order_id)
            state.order_event.set()
            return

    pending = state.pending_amend
    if pending is not None:
        if execution_type == EXECUTION_TYPE_ORDER_REJECTED:
            state.last_error_text = "ORDER REJECTED by execution event."
            state.amend_event.set()
            return

        if position is None:
            return

        if position_id != pending.position_id:
            return

        trade_data = getattr(position, "tradeData", None)
        pos_trade_side = getattr(trade_data, "tradeSide", None) if trade_data else None
        pos_volume = getattr(trade_data, "volume", None) if trade_data else None
        pos_label = getattr(trade_data, "label", "") if trade_data else ""
        pos_comment = getattr(trade_data, "comment", "") if trade_data else ""

        pos_price = getattr(position, "price", None)
        pos_sl = getattr(position, "stopLoss", None)
        pos_tp = getattr(position, "takeProfit", None)

        logger.info(
            "POSITION UPDATED | positionId=%s | side=%s | volume=%s | price=%s | "
            "SL=%s | TP=%s | label=%s | comment=%s",
            position_id,
            trade_side_name(pos_trade_side),
            pos_volume,
            pos_price,
            pos_sl,
            pos_tp,
            pos_label,
            pos_comment,
        )

        state.last_amend_position = position
        state.amend_event.set()
        return

    if execution_type == EXECUTION_TYPE_ORDER_REJECTED:
        state.last_error_text = "CLOSE POSITION REJECTED by execution event."
        state.amend_event.set()
        return

    if execution_type == EXECUTION_TYPE_ORDER_FILLED:
        state.amend_event.set()
        return


def handle_order_error_event(payload, state: SessionState) -> None:
    """Обробити order error event для amend/close/pending/cancel."""
    state.last_error_text = (
        "ORDER ERROR EVENT | errorCode=%s | description=%s | "
        "orderId=%s | positionId=%s"
        % (
            getattr(payload, "errorCode", None),
            getattr(payload, "description", None),
            getattr(payload, "orderId", None),
            getattr(payload, "positionId", None),
        )
    )
    logger.error(state.last_error_text)
    state.amend_event.set()
    state.order_event.set()


def on_message_received(
    client: Client,
    message,
    config: RuntimeConfig,
    state: SessionState,
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
        state.session_ready = True
        state.session_ready_event.set()
        return

    if message.payloadType == ProtoOAReconcileRes().payloadType:
        state.last_reconcile_payload = payload
        state.reconcile_event.set()
        return

    if message.payloadType == ProtoOAExecutionEvent().payloadType:
        handle_execution_event(payload, state)
        return

    if message.payloadType == ProtoOAOrderErrorEvent().payloadType:
        handle_order_error_event(payload, state)
        return

    if message.payloadType == ProtoOAErrorRes().payloadType:
        state.last_error_text = (
            f"API ERROR: {getattr(payload, 'errorCode', None)} | "
            f"{getattr(payload, 'description', None)}"
        )
        logger.error(state.last_error_text)
        state.session_ready_event.set()
        state.reconcile_event.set()
        state.amend_event.set()
        return


def on_deferred_error(failure) -> None:
    """Deferred errback."""
    logger.error("Deferred error: %s", failure)


def reactor_worker(client: Client) -> None:
    """Окремий потік Twisted reactor."""
    logger.info("Starting client service...")
    client.startService()

    logger.info("Running Twisted reactor...")
    reactor_run(installSignalHandlers=False)


def request_positions(
    client: Client,
    config: RuntimeConfig,
    state: SessionState,
) -> None:
    """Запросити positions у межах вже відкритої сесії."""
    state.last_reconcile_payload = None
    state.last_error_text = ""
    state.reconcile_event.clear()

    reactor_call_from_thread(send_reconcile, client, config)

    wait_event(
        state.reconcile_event,
        WAIT_TIMEOUT_SECONDS,
        "reconcile response",
    )

    if state.last_error_text:
        raise RuntimeError(state.last_error_text)

    if state.last_reconcile_payload is None:
        raise RuntimeError("Reconcile payload is empty.")

    print_positions_from_reconcile(state.last_reconcile_payload)


def request_amend_position_sltp(
    client: Client,
    config: RuntimeConfig,
    state: SessionState,
) -> None:
    """Запросити amend SL/TP у межах вже відкритої сесії."""
    print()
    print("Приклад:")
    print("positionId=604231236, SL=1.35000, TP=1.33309")
    print()

    position_id = read_positive_int(
        "Введіть POSITION_ID: ",
        "POSITION_ID",
    )
    stop_loss = read_positive_float(
        "Введіть STOP_LOSS: ",
        "STOP_LOSS",
    )
    take_profit = read_positive_float(
        "Введіть TAKE_PROFIT: ",
        "TAKE_PROFIT",
    )

    amend = AmendRequest(
        position_id=position_id,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )

    state.pending_amend = amend
    state.last_amend_position = None
    state.last_error_text = ""
    state.amend_event.clear()

    reactor_call_from_thread(send_amend_position_sltp, client, config, amend)

    wait_event(
        state.amend_event,
        WAIT_TIMEOUT_SECONDS,
        "amend position response/event",
    )

    if state.last_error_text:
        raise RuntimeError(state.last_error_text)

    if state.last_amend_position is None:
        raise RuntimeError("Amend event received but updated position is empty.")

    pos = state.last_amend_position
    trade_data = getattr(pos, "tradeData", None)

    print()
    print("=== POSITION UPDATED ===")
    print(f"positionId={getattr(pos, 'positionId', None)}")
    print(
        f"symbol={symbol_name_by_id(getattr(trade_data, 'symbolId', None)
                                    if trade_data else None)}"
    )
    print(
        f"side={trade_side_name(getattr(trade_data, 'tradeSide', None)
                                if trade_data else None)}"
    )
    print(f"volume={getattr(trade_data, 'volume', None) if trade_data else None}")
    print(f"price={format_money(getattr(pos, 'price', None))}")
    print(f"stopLoss={format_money(getattr(pos, 'stopLoss', None))}")
    print(f"takeProfit={format_money(getattr(pos, 'takeProfit', None))}")
    print()

    state.pending_amend = None


def request_close_position(
    client: Client,
    config: RuntimeConfig,
    state: SessionState,
) -> None:
    """Закрити позицію в межах поточної сесії."""
    print()
    print("Приклад:")
    print("positionId=604231236")
    print()

    position_id = read_positive_int(
        "Введіть POSITION_ID: ",
        "POSITION_ID",
    )

    if state.last_reconcile_payload is None:
        raise RuntimeError(
            "Немає актуального reconcile payload. Спочатку виконай 1 — get positions."
        )

    pos = find_position_in_reconcile(state.last_reconcile_payload, position_id)
    if pos is None:
        raise RuntimeError(
            f"Позицію positionId={position_id} не знайдено в останньому reconcile."
        )

    trade_data = getattr(pos, "tradeData", None)
    if trade_data is None:
        raise RuntimeError("У позиції відсутній tradeData.")

    volume = getattr(trade_data, "volume", 0)
    if not isinstance(volume, int) or volume <= 0:
        raise RuntimeError(f"Некоректний volume для positionId={position_id}: {volume}")

    state.pending_amend = None
    state.last_amend_position = None
    state.last_error_text = ""
    state.amend_event.clear()

    reactor_call_from_thread(
        send_close_position,
        client,
        config,
        position_id,
        volume,
    )

    wait_event(
        state.amend_event,
        WAIT_TIMEOUT_SECONDS,
        "close position response/event",
    )

    if state.last_error_text:
        raise RuntimeError(state.last_error_text)

    print()
    print("=== POSITION CLOSE REQUEST SENT ===")
    print(f"positionId={position_id}")
    print(f"volume={volume}")
    print()


def request_place_pending_order(
    client: Client,
    config: RuntimeConfig,
    state: SessionState,
) -> None:
    """Поставити pending order в межах поточної сесії."""
    print()
    print("Підтримуються: LIMIT, STOP, STOP_LIMIT")
    print("Для STOP_LIMIT slippageInPoints вводиться вручну.")
    print()

    symbol_name = read_symbol_name()
    symbol = ctr_symbols.CTRADER_FOREX_BY_NAME[symbol_name]
    symbol_id = symbol.symbol_id
    trade_side = read_trade_side()
    lots = read_positive_float("Введіть LOTS (наприклад 0.01): ", "LOTS")
    api_volume = ctr_lot.lots_to_api_volume(lots)
    order_type = read_pending_order_type()

    limit_price = None
    stop_price = None
    slippage_in_points = None

    if order_type == ORDER_TYPE_LIMIT:
        limit_price = read_positive_float("Введіть LIMIT_PRICE: ", "LIMIT_PRICE")
    elif order_type == ORDER_TYPE_STOP:
        stop_price = read_positive_float("Введіть STOP_PRICE: ", "STOP_PRICE")
    elif order_type == ORDER_TYPE_STOP_LIMIT:
        stop_price = read_positive_float("Введіть STOP_PRICE: ", "STOP_PRICE")
        slippage_in_points = read_non_negative_int(
            "Введіть SLIPPAGE_IN_POINTS: ",
            "SLIPPAGE_IN_POINTS",
        )

    stop_loss = read_optional_positive_float(
        "Введіть STOP_LOSS (Enter = без SL): ",
        "STOP_LOSS",
    )
    take_profit = read_optional_positive_float(
        "Введіть TAKE_PROFIT (Enter = без TP): ",
        "TAKE_PROFIT",
    )

    pending = PendingOrderRequest(
        symbol_name=symbol_name,
        symbol_id=symbol_id,
        lots=lots,
        api_volume=api_volume,
        trade_side=trade_side,
        order_type=order_type,
        limit_price=limit_price,
        stop_price=stop_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        slippage_in_points=slippage_in_points,
    )

    state.pending_amend = None
    state.pending_cancel_order_id = None
    state.pending_order_request = pending
    state.last_execution_order = None
    state.last_execution_position = None
    state.last_error_text = ""
    state.order_event.clear()

    reactor_call_from_thread(send_new_pending_order, client, config, pending)

    wait_event(
        state.order_event,
        WAIT_TIMEOUT_SECONDS,
        "place pending order response/event",
    )

    if state.last_error_text:
        raise RuntimeError(state.last_error_text)

    order = state.last_execution_order
    if order is None:
        raise RuntimeError("Pending order event received but order is empty.")

    trade_data = getattr(order, "tradeData", None)

    print()
    print("=== PENDING ORDER ACCEPTED ===")
    print(f"orderId={getattr(order, 'orderId', None)}")
    print(
        f"symbol={symbol_name_by_id(getattr(trade_data, 'symbolId', None)
                                    if trade_data else None)}"
    )
    print(
        f"side={trade_side_name(getattr(trade_data, 'tradeSide', None)
                                if trade_data else None)}"
    )
    print(f"type={order_type_name(getattr(order, 'orderType', None))}")
    print(f"volume={getattr(trade_data, 'volume', None) if trade_data else None}")
    print(f"limitPrice={format_money(getattr(order, 'limitPrice', None))}")
    print(f"stopPrice={format_money(getattr(order, 'stopPrice', None))}")
    print(f"stopLoss={format_money(getattr(order, 'stopLoss', None))}")
    print(f"takeProfit={format_money(getattr(order, 'takeProfit', None))}")
    print(f"slippageInPoints={getattr(order, 'slippageInPoints', None)}")
    print()

    state.pending_order_request = None


def request_cancel_pending_order(
    client: Client,
    config: RuntimeConfig,
    state: SessionState,
) -> None:
    """Скасувати pending order в межах поточної сесії."""
    print()
    print("Приклад:")
    print("orderId=123456789")
    print()

    order_id = read_positive_int("Введіть ORDER_ID: ", "ORDER_ID")

    if state.last_reconcile_payload is None:
        raise RuntimeError(
            "Немає актуального reconcile payload. "
            "Спочатку виконай 1 — get positions/orders."
        )

    order = find_order_in_reconcile(state.last_reconcile_payload, order_id)
    if order is None:
        raise RuntimeError(
            f"Pending order orderId={order_id} не знайдено в останньому reconcile."
        )

    state.pending_amend = None
    state.pending_order_request = None
    state.pending_cancel_order_id = order_id
    state.last_execution_order = None
    state.last_execution_position = None
    state.last_error_text = ""
    state.order_event.clear()

    reactor_call_from_thread(send_cancel_pending_order, client, config, order_id)

    wait_event(
        state.order_event,
        WAIT_TIMEOUT_SECONDS,
        "cancel pending order response/event",
    )

    if state.last_error_text:
        raise RuntimeError(state.last_error_text)

    print()
    print("=== PENDING ORDER CANCELLED ===")
    print(f"orderId={order_id}")
    print()

    state.pending_cancel_order_id = None


def stop_reactor_safe() -> None:
    """Безпечно зупинити reactor."""
    try:
        reactor_stop()
    except ReactorNotRunning:
        pass


def shutdown_session(
    client: Client,
    state: SessionState,
    reactor_thread: threading.Thread,
) -> None:
    """Коректно завершити сесію."""
    if state.shutdown_requested:
        return

    state.shutdown_requested = True
    state.stop_event.set()

    def _shutdown() -> None:
        logger.info("Stopping client service...")
        client.stopService()
        stop_reactor_safe()

    try:
        reactor_call_from_thread(_shutdown)
    except Exception as exc:
        logger.warning("reactor_call_from_thread shutdown failed: %s", exc)
        try:
            client.stopService()
        except Exception as exc2:
            logger.warning("client.stopService failed: %s", exc2)
        stop_reactor_safe()

    reactor_thread.join(timeout=5)
    logger.info("Session closed.")


def print_menu() -> None:
    """Надрукувати меню."""
    print()
    print("=== cTrader RM56 session ===")
    print("1 — get positions / pending orders")
    print("2 — amend SL/TP")
    print("3 — close position")
    print("4 — place pending order")
    print("5 — get pending orders (same reconcile)")
    print("6 — cancel pending order")
    print("0 — exit")
    print()


def main() -> None:
    """Запуск session-based console."""
    client_id, client_secret, ctid_trader_account_id = load_env_config()
    access_token = ensure_access_token(
        client_id=client_id,
        client_secret=client_secret,
    )

    config = RuntimeConfig(
        client_id=client_id,
        client_secret=client_secret,
        access_token=access_token,
        ctid_trader_account_id=ctid_trader_account_id,
    )
    state = SessionState()

    logger.info("cTrader RoadMap56 — SESSION CONSOLE")
    logger.info("Host: %s", HOST)
    logger.info("Port: %s", PORT)
    logger.info("Tokens path: %s", os.getenv("TOKENS_PATH"))
    logger.info("AccountId: %s", config.ctid_trader_account_id)

    client = Client(HOST, PORT, TcpProtocol)

    client.setConnectedCallback(lambda c: on_connected(c, config))
    client.setDisconnectedCallback(on_disconnected)
    client.setMessageReceivedCallback(
        lambda c, message: on_message_received(c, message, config, state)
    )

    reactor_thread = threading.Thread(
        target=reactor_worker,
        args=(client,),
        daemon=True,
        name="ctrader-reactor-thread",
    )
    reactor_thread.start()
    state.reactor_thread_started = True

    wait_event(
        state.session_ready_event,
        WAIT_TIMEOUT_SECONDS,
        "session ready",
    )

    if state.last_error_text:
        raise RuntimeError(state.last_error_text)

    if not state.session_ready:
        raise RuntimeError("Session did not become ready.")

    logger.info("SESSION READY")

    try:
        while True:
            print_menu()
            cmd = input("Select: ").strip()

            if cmd == "1":
                try:
                    request_positions(client, config, state)
                except Exception as exc:
                    logger.exception("Get positions failed")
                    print(f"Помилка get positions: {exc}")

            elif cmd == "2":
                try:
                    request_amend_position_sltp(client, config, state)
                except Exception as exc:
                    logger.exception("Amend SL/TP failed")
                    print(f"Помилка amend SL/TP: {exc}")

            elif cmd == "3":
                try:
                    request_close_position(client, config, state)
                except Exception as exc:
                    logger.exception("Close position failed")
                    print(f"Помилка close position: {exc}")

            elif cmd == "4":
                try:
                    request_place_pending_order(client, config, state)
                except Exception as exc:
                    logger.exception("Place pending order failed")
                    print(f"Помилка place pending order: {exc}")

            elif cmd == "5":
                try:
                    request_positions(client, config, state)
                except Exception as exc:
                    logger.exception("Get pending orders failed")
                    print(f"Помилка get pending orders: {exc}")

            elif cmd == "6":
                try:
                    request_cancel_pending_order(client, config, state)
                except Exception as exc:
                    logger.exception("Cancel pending order failed")
                    print(f"Помилка cancel pending order: {exc}")

            elif cmd == "0":
                break

            else:
                print("Невідома команда.")

    finally:
        shutdown_session(client, state, reactor_thread)
        logger.info("DONE")


if __name__ == "__main__":
    main()
