# run_ib_05_historical_data.py
# -*- coding: utf-8 -*-
"""
RoadMap51: ручний тест historical data з Interactive Brokers TWS API.

Що робить:
- підключається до TWS/Gateway
- чекає nextValidId
- запитує historical data для GBP.USD
- збирає bars
- чекає historicalDataEnd
- показує результат
- коректно відключається

Без ордерів.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.wrapper import EWrapper

DEBUG = False

HOST = "127.0.0.1"
PORT = 7497
CLIENT_ID = 5

CONNECT_WAIT_SECONDS = 10.0
HISTORICAL_WAIT_SECONDS = 15.0
DISCONNECT_WAIT_SECONDS = 0.5

HIST_REQ_ID = 3001
END_DATETIME = ""
DURATION_STR = "1 D"
BAR_SIZE_SETTING = "1 hour"
WHAT_TO_SHOW = "MIDPOINT"
USE_RTH = 0
FORMAT_DATE = 1
KEEP_UP_TO_DATE = False
CHART_OPTIONS: list = []


LOG_LEVEL = logging.DEBUG if DEBUG else logging.INFO
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class HistoricalBarRow:
    """Один historical bar."""

    date_text: str
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: str
    bar_count: int
    wap: str


@dataclass
class HistoricalResult:
    """Результат ручного тесту historical data."""

    connected_ok: bool = False
    next_valid_id: int | None = None
    managed_accounts: str = ""
    historical_completed: bool = False
    bars: list[HistoricalBarRow] = field(default_factory=list)
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
            f"HISTORICAL_COMPLETED: {'YES' if self.historical_completed else 'NO'}",
            "",
            "BARS:",
        ]

        if self.bars:
            for row in self.bars:
                lines.append(
                    f"  - date={row.date_text}, "
                    f"open={row.open_price}, "
                    f"high={row.high_price}, "
                    f"low={row.low_price}, "
                    f"close={row.close_price}, "
                    f"volume={row.volume}, "
                    f"barCount={row.bar_count}, "
                    f"wap={row.wap}"
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


class IBHistoricalDataApp(EWrapper, EClient):
    """Мінімальний IB-клієнт для historical data."""

    def __init__(self) -> None:
        EWrapper.__init__(self)
        EClient.__init__(self, self)

        self.connected_ok = False
        self.next_valid_id_value: int | None = None
        self.managed_accounts_value: str = ""
        self.error_messages: list[str] = []
        self.bars: list[HistoricalBarRow] = []
        self.historical_completed = False

        self._next_valid_id_event = threading.Event()
        self._historical_end_event = threading.Event()

    def is_next_valid_id_received(self) -> bool:
        """Чи отримано nextValidId."""
        return self._next_valid_id_event.is_set()

    def is_historical_completed(self) -> bool:
        """Чи завершено historical data."""
        return self._historical_end_event.is_set()

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

    def historicalData(self, reqId, bar) -> None:  # noqa
        """Callback: один historical bar."""
        row = HistoricalBarRow(
            date_text=str(bar.date),
            open_price=float(bar.open),
            high_price=float(bar.high),
            low_price=float(bar.low),
            close_price=float(bar.close),
            volume=str(bar.volume),
            bar_count=int(bar.barCount),
            wap=str(getattr(bar, "average", "")),
        )
        self.bars.append(row)
        logger.info(
            "historicalData received: reqId=%s date=%s open=%s high=%s low=%s "
            "close=%s volume=%s barCount=%s wap=%s",
            reqId,
            row.date_text,
            row.open_price,
            row.high_price,
            row.low_price,
            row.close_price,
            row.volume,
            row.bar_count,
            row.wap,
        )

    def historicalDataEnd(self, reqId, start, end) -> None:  # noqa
        """Callback: завершення historical data."""
        self.historical_completed = True
        logger.info(
            "historicalDataEnd received: reqId=%s start=%s end=%s",
            reqId,
            start,
            end,
        )
        self._historical_end_event.set()

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


def analyze_result(result: HistoricalResult) -> str:
    """Короткий висновок за результатами."""
    if not result.connected_ok or result.next_valid_id is None:
        return "FAIL: немає нормального handshake."

    if not result.historical_completed:
        return "FAIL: historical data не завершився по timeout."

    if not result.bars:
        return "FAIL: historical data завершився, але bars не прийшли."

    return "SUCCESS: historical data received."


def run_test() -> HistoricalResult:
    """Запустити ручний тест historical data."""
    app = IBHistoricalDataApp()
    result = HistoricalResult()

    thread: threading.Thread | None = None

    try:
        logger.info(
            "Historical data test started: host=%s port=%s clientId=%s",
            HOST,
            PORT,
            CLIENT_ID,
        )
        logger.info("Connecting to %s:%s ...", HOST, PORT)
        app.connect(HOST, PORT, CLIENT_ID)

        thread = threading.Thread(
            target=app.run,
            name="ibapi-historical-data",
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
        logger.info(
            "Requesting historical data for GBP.USD: duration=%s barSize=%s "
            "whatToShow=%s",
            DURATION_STR,
            BAR_SIZE_SETTING,
            WHAT_TO_SHOW,
        )
        app.reqHistoricalData(
            HIST_REQ_ID,
            contract,
            END_DATETIME,
            DURATION_STR,
            BAR_SIZE_SETTING,
            WHAT_TO_SHOW,
            USE_RTH,
            FORMAT_DATE,
            KEEP_UP_TO_DATE,
            CHART_OPTIONS,
        )

        started = time.time()
        while time.time() - started < HISTORICAL_WAIT_SECONDS:
            if app.is_historical_completed():
                break
            time.sleep(0.1)

        try:
            app.cancelHistoricalData(HIST_REQ_ID)
        except Exception as exc:
            logger.warning("cancelHistoricalData failed: %s", exc)

        result.connected_ok = app.connected_ok
        result.next_valid_id = app.next_valid_id_value
        result.managed_accounts = app.managed_accounts_value
        result.historical_completed = app.historical_completed
        result.bars.extend(app.bars)
        result.errors.extend(app.error_messages)

    except Exception as exc:
        error_text = f"Python exception: {type(exc).__name__}: {exc}"
        logger.exception("Unhandled exception during historical data test")
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
    print("IB HISTORICAL DATA TEST")
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
        and result.historical_completed
        and result.bars
    ):
        print("RESULT: SUCCESS")
        return 0

    print("RESULT: FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
