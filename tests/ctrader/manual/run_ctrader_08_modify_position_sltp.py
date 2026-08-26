# run_ctrader_08_modify_position_sltp.py
"""
Ручний тест: cTrader Open API modify position SL/TP
з авторизацією через env + tokens.json + login/password fallback.

RoadMap54 / Step 08:
1) беремо CLIENT_ID / CLIENT_SECRET / ACCOUNT_ID з env
2) пробуємо взяти access_token через token_manager
3) якщо токена нема або він невалідний — запускаємо login/password flow
4) connect
5) application auth
6) list accounts by access token
7) account auth
8) amend position SL/TP
9) чекаємо відповідь / execution event
10) done

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
import time
import urllib.parse
from dataclasses import dataclass
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
    ProtoOAErrorRes,
    ProtoOAExecutionEvent,
    ProtoOAGetAccountListByAccessTokenReq,
    ProtoOAGetAccountListByAccessTokenRes,
    ProtoOAOrderErrorEvent,
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

from core.token_manager import load_tokens, refresh_if_needed, save_tokens  # noqa: E402

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

HOST = EndPoints.PROTOBUF_DEMO_HOST
PORT = EndPoints.PROTOBUF_PORT
WAIT_TIMEOUT_SECONDS = 20

TRADE_SIDE_BUY = 1
TRADE_SIDE_SELL = 2

EXECUTION_TYPE_ORDER_ACCEPTED = 2
EXECUTION_TYPE_ORDER_FILLED = 3
EXECUTION_TYPE_ORDER_REJECTED = 7
EXECUTION_TYPE_ORDER_REPLACED = 5

REDIRECT_URI = "http://localhost:8080/"
AUTH_SCOPE = "trading"
EDGE_DRIVER_PATH = r"C:\WebDriver\msedgedriver.exe"

reactor_stop = getattr(reactor, "stop")
reactor_run = getattr(reactor, "run")
reactor_call_later = getattr(reactor, "callLater")


@dataclass
class RuntimeConfig:
    client_id: str
    client_secret: str
    access_token: str
    ctid_trader_account_id: int
    position_id: int
    stop_loss: float
    take_profit: float


@dataclass
class RuntimeState:
    amend_done: bool = False
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
    token_data["_comment"] = "Отримано через run_ctrader_08_modify_position_sltp.py"
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


def send_amend_position_sltp(client: Client, config: RuntimeConfig) -> None:
    logger.info(
        "Sending ProtoOAAmendPositionSLTPReq... positionId=%s | SL=%s | TP=%s",
        config.position_id,
        config.stop_loss,
        config.take_profit,
    )

    request = ProtoOAAmendPositionSLTPReq()
    request.ctidTraderAccountId = config.ctid_trader_account_id
    request.positionId = config.position_id
    request.stopLoss = config.stop_loss
    request.takeProfit = config.take_profit

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


def execution_type_name(value: int) -> str:
    if value == EXECUTION_TYPE_ORDER_ACCEPTED:
        return "ORDER_ACCEPTED"
    if value == EXECUTION_TYPE_ORDER_FILLED:
        return "ORDER_FILLED"
    if value == EXECUTION_TYPE_ORDER_REJECTED:
        return "ORDER_REJECTED"
    if value == EXECUTION_TYPE_ORDER_REPLACED:
        return "ORDER_REPLACED"
    return f"UNKNOWN({value})"


def trade_side_name(value: int | None) -> str:
    if value == TRADE_SIDE_BUY:
        return "BUY"
    if value == TRADE_SIDE_SELL:
        return "SELL"
    return f"UNKNOWN({value})"


def handle_execution_event(
    client: Client,
    payload,
    config: RuntimeConfig,
    state: RuntimeState,
) -> None:
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

    if position is not None and position_id == config.position_id:
        trade_data = getattr(position, "tradeData", None)

        pos_trade_side_raw = (
            getattr(trade_data, "tradeSide", None) if trade_data else None
        )
        pos_volume_raw = getattr(trade_data, "volume", None) if trade_data else None
        pos_price_raw = getattr(position, "price", None)
        pos_sl_raw = getattr(position, "stopLoss", None)
        pos_tp_raw = getattr(position, "takeProfit", None)
        pos_label = getattr(trade_data, "label", "") if trade_data else ""
        pos_comment = getattr(trade_data, "comment", "") if trade_data else ""

        pos_trade_side = (
            int(pos_trade_side_raw) if pos_trade_side_raw is not None else -1
        )
        pos_volume = int(pos_volume_raw) if pos_volume_raw is not None else 0
        pos_price = float(pos_price_raw) if pos_price_raw is not None else 0.0
        pos_sl = float(pos_sl_raw) if pos_sl_raw is not None else 0.0
        pos_tp = float(pos_tp_raw) if pos_tp_raw is not None else 0.0

        logger.info(
            "POSITION UPDATED | positionId=%s | side=%s | volume=%s | price=%s | "
            "SL=%s | TP=%s | label=%s | comment=%s",
            getattr(position, "positionId", None),
            trade_side_name(pos_trade_side),
            pos_volume,
            pos_price,
            pos_sl,
            pos_tp,
            pos_label,
            pos_comment,
        )
        state.amend_done = True
        schedule_shutdown(client, state, 0)
        return

    if execution_type == EXECUTION_TYPE_ORDER_REJECTED:
        logger.error("ORDER REJECTED by execution event.")
        schedule_shutdown(client, state, 0)


def handle_order_error_event(
    client: Client,
    payload,
    state: RuntimeState,
) -> None:
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
    if state.amend_done:
        return

    logger.error(
        "TIMEOUT: amend position response/event not received within %s seconds.",
        WAIT_TIMEOUT_SECONDS,
    )
    schedule_shutdown(client, state, 0)


def on_message_received(
    client: Client,
    message,
    config: RuntimeConfig,
    state: RuntimeState,
) -> None:
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
        reactor_call_later(1.0, send_amend_position_sltp, client, config)
        return

    if message.payloadType == ProtoOAExecutionEvent().payloadType:
        handle_execution_event(client, payload, config, state)
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
    logger.error("Deferred error: %s", failure)
    stop_reactor()


def main() -> None:
    client_id, client_secret, ctid_trader_account_id = load_env_config()
    access_token = ensure_access_token(
        client_id=client_id,
        client_secret=client_secret,
    )

    print()
    print("Поточний наш ордер із Step06a: positionId=604231236")
    print("Для нього можна ставити, наприклад, SL=1.35 і TP=1.334")
    print()

    position_id = read_positive_int(
        "Введіть POSITION_ID: ",
        "POSITION_ID",
    )
    stop_loss = read_positive_float(
        "Введіть STOP_LOSS (наприклад 1.35): ",
        "STOP_LOSS",
    )
    take_profit = read_positive_float(
        "Введіть TAKE_PROFIT (наприклад 1.334): ",
        "TAKE_PROFIT",
    )

    config = RuntimeConfig(
        client_id=client_id,
        client_secret=client_secret,
        access_token=access_token,
        ctid_trader_account_id=ctid_trader_account_id,
        position_id=position_id,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )
    state = RuntimeState()

    logger.info("cTrader Step 08 — MODIFY POSITION SL/TP")
    logger.info("Host: %s", HOST)
    logger.info("Port: %s", PORT)
    logger.info("Tokens path: %s", os.getenv("TOKENS_PATH"))
    logger.info(
        "Modify params | accountId=%s | positionId=%s | SL=%s | TP=%s",
        config.ctid_trader_account_id,
        config.position_id,
        config.stop_loss,
        config.take_profit,
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
