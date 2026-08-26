# run_ib_03_positions.py
# -*- coding: utf-8 -*-
"""
RoadMap51: ручний тест читання positions з Interactive Brokers TWS API.

Що робить:
- підключається до TWS/Gateway
- чекає nextValidId
- запитує positions
- збирає всі position(...)
- чекає positionEnd()
- показує результат
- коректно відключається

Без market data.
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
from ibapi.wrapper import EWrapper

DEBUG = False

HOST = "127.0.0.1"
PORT = 7497
CLIENT_ID = 3

CONNECT_WAIT_SECONDS = 5.0
POSITIONS_WAIT_SECONDS = 10.0
DISCONNECT_WAIT_SECONDS = 0.5


LOG_LEVEL = logging.DEBUG if DEBUG else logging.INFO
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class PositionRow:
    """Один рядок position."""

    account: str
    symbol: str
    sec_type: str
    exchange: str
    currency: str
    position: float
    avg_cost: float


@dataclass
class PositionsResult:
    """Результат ручного тесту positions."""

    connected_ok: bool = False
    next_valid_id: int | None = None
    managed_accounts: str = ""
    positions_completed: bool = False
    positions_rows: list[PositionRow] = field(default_factory=list)
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
            f"POSITIONS_COMPLETED: {'YES' if self.positions_completed else 'NO'}",
            "",
            "POSITIONS_ROWS:",
        ]

        if self.positions_rows:
            for row in self.positions_rows:
                lines.append(
                    "  - "
                    f"account={row.account}, "
                    f"symbol={row.symbol}, "
                    f"secType={row.sec_type}, "
                    f"exchange={row.exchange}, "
                    f"currency={row.currency}, "
                    f"position={row.position}, "
                    f"avgCost={row.avg_cost}"
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


class IBPositionsApp(EWrapper, EClient):
    """Мінімальний IB-клієнт для positions."""

    def __init__(self) -> None:
        EWrapper.__init__(self)
        EClient.__init__(self, self)

        self.connected_ok = False
        self.next_valid_id_value: int | None = None
        self.managed_accounts_value: str = ""
        self.error_messages: list[str] = []
        self.positions_rows: list[PositionRow] = []
        self.positions_completed = False

        self._next_valid_id_event = threading.Event()
        self._positions_end_event = threading.Event()

    def is_next_valid_id_received(self) -> bool:
        """Чи отримано nextValidId."""
        return self._next_valid_id_event.is_set()

    def is_positions_completed(self) -> bool:
        """Чи завершено positions."""
        return self._positions_end_event.is_set()

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

    def position(
        self,
        account: str,
        contract: Contract,
        position: float,
        avgCost: float,  # noqa
    ) -> None:
        """Callback: один рядок position."""
        row = PositionRow(
            account=account,
            symbol=contract.symbol or "",
            sec_type=contract.secType or "",
            exchange=contract.exchange or "",
            currency=contract.currency or "",
            position=position,
            avg_cost=avgCost,
        )
        self.positions_rows.append(row)
        logger.info(
            "position received: account=%s symbol=%s secType=%s exchange=%s "
            "currency=%s position=%s avgCost=%s",
            row.account,
            row.symbol,
            row.sec_type,
            row.exchange,
            row.currency,
            row.position,
            row.avg_cost,
        )

    def positionEnd(self) -> None:  # noqa
        """Callback: завершення positions."""
        self.positions_completed = True
        logger.info("positionEnd received")
        self._positions_end_event.set()

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


def analyze_result(result: PositionsResult) -> str:
    """Короткий висновок за результатами."""
    if not result.connected_ok or result.next_valid_id is None:
        return "FAIL: немає нормального handshake."

    if not result.positions_completed:
        return "FAIL: positions не завершився по timeout."

    return "SUCCESS: positions received."


def run_test() -> PositionsResult:
    """Запустити ручний тест positions."""
    app = IBPositionsApp()
    result = PositionsResult()

    thread: threading.Thread | None = None

    try:
        logger.info(
            "Positions test started: host=%s port=%s clientId=%s",
            HOST,
            PORT,
            CLIENT_ID,
        )
        logger.info("Connecting to %s:%s ...", HOST, PORT)
        app.connect(HOST, PORT, CLIENT_ID)

        thread = threading.Thread(
            target=app.run,
            name="ibapi-positions",
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

        logger.info("Requesting positions ...")
        app.reqPositions()

        started = time.time()
        while time.time() - started < POSITIONS_WAIT_SECONDS:
            if app.is_positions_completed():
                break
            time.sleep(0.1)

        try:
            app.cancelPositions()
        except Exception as exc:
            logger.warning("cancelPositions failed: %s", exc)

        result.connected_ok = app.connected_ok
        result.next_valid_id = app.next_valid_id_value
        result.managed_accounts = app.managed_accounts_value
        result.positions_completed = app.positions_completed
        result.positions_rows.extend(app.positions_rows)
        result.errors.extend(app.error_messages)

    except Exception as exc:
        error_text = f"Python exception: {type(exc).__name__}: {exc}"
        logger.exception("Unhandled exception during positions test")
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
    print("IB POSITIONS TEST")
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
        and result.positions_completed
    ):
        print("RESULT: SUCCESS")
        return 0

    print("RESULT: FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
