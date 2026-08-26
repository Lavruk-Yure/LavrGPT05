# run_ib_04_market_data.py
# -*- coding: utf-8 -*-
"""
RoadMap51: ручний тест live market data з Interactive Brokers TWS API.

Що робить:
- підключається до TWS/Gateway
- чекає nextValidId
- запитує market data для GBP.USD
- збирає tickPrice / tickSize
- чекає кілька секунд
- скасовує market data
- показує результат
- коректно відключається

Без historical data.
Без ордерів.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.ticktype import TickTypeEnum
from ibapi.wrapper import EWrapper

DEBUG = False

HOST = "127.0.0.1"
PORT = 7497
CLIENT_ID = 4

CONNECT_WAIT_SECONDS = 10.0
MARKET_DATA_WAIT_SECONDS = 10.0
DISCONNECT_WAIT_SECONDS = 0.5

MARKET_DATA_REQ_ID = 2001


LOG_LEVEL = logging.DEBUG if DEBUG else logging.INFO
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class TickPriceRow:
    """Один tickPrice рядок."""

    req_id: int
    tick_type: int
    tick_name: str
    price: float


@dataclass
class TickSizeRow:
    """Один tickSize рядок."""

    req_id: int
    tick_type: int
    tick_name: str
    size: float


@dataclass
class MarketDataResult:
    """Результат ручного тесту market data."""

    connected_ok: bool = False
    next_valid_id: int | None = None
    managed_accounts: str = ""
    tick_price_rows: list[TickPriceRow] = field(default_factory=list)
    tick_size_rows: list[TickSizeRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary_text(self) -> str:
        """Повернути текстовий підсумок."""
        lines: list[str] = [
            f"HOST: {HOST}",
            f"PORT: {PORT}",
            f"CLIENT_ID: {CLIENT_ID}",
            f"CONNECTED: {'YES' if self.connected_ok else 'NO'}",
            f"NEXT_VALID_ID: {self.next_valid_id}",
            f"MANAGED_ACCOUNTS: {self.managed_accounts or '(empty)'}",
            "",
            "TICK_PRICE_ROWS:",
        ]

        if self.tick_price_rows:
            for row in self.tick_price_rows:
                lines.append(
                    f"  - reqId={row.req_id}, "
                    f"tickType={row.tick_type}, "
                    f"name={row.tick_name}, "
                    f"price={row.price}"
                )
        else:
            lines.append("  (none)")

        lines.append("")
        lines.append("TICK_SIZE_ROWS:")
        if self.tick_size_rows:
            for row in self.tick_size_rows:
                lines.append(
                    f"  - reqId={row.req_id}, "
                    f"tickType={row.tick_type}, "
                    f"name={row.tick_name}, "
                    f"size={row.size}"
                )
        else:
            lines.append("  (none)")

        lines.append("")
        if self.errors:
            lines.append("ERRORS:")
            for item in self.errors:
                lines.append(f"  - {item}")
        else:
            lines.append("ERRORS: none")

        return "\n".join(lines)


class IBMarketDataApp(EWrapper, EClient):
    """Мінімальний IB-клієнт для market data."""

    def __init__(self) -> None:
        EWrapper.__init__(self)
        EClient.__init__(self, self)

        self.connected_ok = False
        self.next_valid_id_value: int | None = None
        self.managed_accounts_value: str = ""
        self.error_messages: list[str] = []
        self.tick_price_rows: list[TickPriceRow] = []
        self.tick_size_rows: list[TickSizeRow] = []

        self._next_valid_id_event = threading.Event()
        self._first_tick_event = threading.Event()

    def is_next_valid_id_received(self) -> bool:
        """Чи отримано nextValidId."""
        return self._next_valid_id_event.is_set()

    def is_first_tick_received(self) -> bool:
        """Чи отримано хоч один tick."""
        return self._first_tick_event.is_set()

    def nextValidId(self, orderId: int) -> None:  # noqa
        """Callback: сервер видав next valid order id."""
        self.connected_ok = True
        self.next_valid_id_value = orderId
        logger.info("nextValidId received: %s", orderId)
        self._next_valid_id_event.set()

    def managedAccounts(self, accountsList: str) -> None:  # noqa
        """Callback: список рахунків."""
        self.managed_accounts_value = accountsList
        logger.info("managedAccounts received: %s", accountsList)

    def tickPrice(
        self,
        reqId: int,  # noqa
        tickType: int,  # noqa
        price: float,
        attrib,
    ) -> None:
        """Callback: ціна market data."""
        tick_name = TickTypeEnum.toStr(tickType)
        row = TickPriceRow(
            req_id=reqId,
            tick_type=tickType,
            tick_name=tick_name,
            price=price,
        )
        self.tick_price_rows.append(row)
        self._first_tick_event.set()
        logger.info(
            "tickPrice received: reqId=%s tickType=%s name=%s price=%s",
            reqId,
            tickType,
            tick_name,
            price,
        )

    def tickSize(
        self,
        reqId: int,  # noqa
        tickType: int,  # noqa
        size: float,
    ) -> None:
        """Callback: розмір market data."""
        tick_name = TickTypeEnum.toStr(tickType)
        row = TickSizeRow(
            req_id=reqId,
            tick_type=tickType,
            tick_name=tick_name,
            size=size,
        )
        self.tick_size_rows.append(row)
        self._first_tick_event.set()
        logger.info(
            "tickSize received: reqId=%s tickType=%s name=%s size=%s",
            reqId,
            tickType,
            tick_name,
            size,
        )

    def error(
        self,
        reqId,  # noqa
        errorTime,  # noqa
        errorCode,  # noqa
        errorString,  # noqa
        advancedOrderRejectJson="",  # noqa
    ) -> None:  # noqa
        """Callback: помилки та інформаційні повідомлення IB."""
        message = (
            f"reqId={reqId}, "
            f"time={errorTime}, "
            f"code={errorCode}, "
            f"message={errorString}"
        )
        if advancedOrderRejectJson:
            message += f", advanced={advancedOrderRejectJson}"

        if errorCode in {2104, 2106, 2158}:
            logger.info("IB info: %s", message)
        else:
            logger.warning("IB error: %s", message)
            self.error_messages.append(message)


def build_gbpusd_contract() -> Contract:
    """Створити Forex контракт GBP.USD."""
    contract = Contract()
    contract.symbol = "GBP"
    contract.secType = "CASH"
    contract.exchange = "IDEALPRO"
    contract.currency = "USD"
    return contract


def analyze_result(result: MarketDataResult) -> str:
    """Короткий висновок за результатами."""
    if not result.connected_ok or result.next_valid_id is None:
        return "FAIL: немає нормального handshake."

    if result.tick_price_rows or result.tick_size_rows:
        return "SUCCESS: market data received."

    return "FAIL: market data ticks не прийшли."


def run_test() -> MarketDataResult:
    """Запустити ручний тест market data."""
    app = IBMarketDataApp()
    result = MarketDataResult()

    thread: threading.Thread | None = None

    try:
        logger.info(
            "Market data test started: host=%s port=%s clientId=%s",
            HOST,
            PORT,
            CLIENT_ID,
        )
        logger.info("Connecting to %s:%s ...", HOST, PORT)
        app.connect(HOST, PORT, CLIENT_ID)

        thread = threading.Thread(
            target=app.run,
            name="ibapi-market-data",
            daemon=True,
        )
        thread.start()

        started = time.time()
        while time.time() - started < CONNECT_WAIT_SECONDS:
            if app.is_next_valid_id_received():
                break
            time.sleep(0.1)

        if not app.is_next_valid_id_received():
            result.connected_ok = app.connected_ok
            result.next_valid_id = app.next_valid_id_value
            result.managed_accounts = app.managed_accounts_value
            result.errors.extend(app.error_messages)
            return result

        contract = build_gbpusd_contract()
        logger.info("Requesting market data for GBP.USD ...")
        app.reqMktData(
            MARKET_DATA_REQ_ID,
            contract,
            "",
            False,
            False,
            [],
        )

        started = time.time()
        while time.time() - started < MARKET_DATA_WAIT_SECONDS:
            if app.is_first_tick_received():
                break
            time.sleep(0.1)

        try:
            app.cancelMktData(MARKET_DATA_REQ_ID)
        except Exception as exc:
            logger.warning("cancelMktData failed: %s", exc)

        result.connected_ok = app.connected_ok
        result.next_valid_id = app.next_valid_id_value
        result.managed_accounts = app.managed_accounts_value
        result.tick_price_rows.extend(app.tick_price_rows)
        result.tick_size_rows.extend(app.tick_size_rows)
        result.errors.extend(app.error_messages)

    except Exception as exc:
        error_text = f"Python exception: {type(exc).__name__}: {exc}"
        logger.exception("Unhandled exception during market data test")
        result.errors.append(error_text)

    finally:
        try:
            if app.isConnected():
                logger.info("Disconnecting from IB...")
                app.disconnect()
                time.sleep(DISCONNECT_WAIT_SECONDS)
        except Exception as exc:
            error_text = f"Disconnect exception: {type(exc).__name__}: {exc}"
            logger.exception("Error during disconnect")
            result.errors.append(error_text)

        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)

    return result


def main() -> int:
    """Точка входу."""
    print("=" * 70)
    print("IB MARKET DATA TEST")
    print("=" * 70)
    print(f"HOST={HOST}")
    print(f"PORT={PORT}")
    print(f"CLIENT_ID={CLIENT_ID}")
    print(f"DEBUG={DEBUG}")
    print()

    result = run_test()

    print("-" * 70)
    print(result.summary_text())
    print("ANALYSIS:", analyze_result(result))
    print("-" * 70)

    if (
        result.connected_ok
        and result.next_valid_id is not None
        and (result.tick_price_rows or result.tick_size_rows)
    ):
        print("RESULT: SUCCESS")
        return 0

    print("RESULT: FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
