# run_ib_06_order_simulation.py
# -*- coding: utf-8 -*-
"""
RoadMap51: ручний тест order simulation з Interactive Brokers TWS API.

Що робить:
- підключається до TWS/Gateway
- чекає nextValidId
- виставляє BUY LMT ордер для GBP.USD
- чекає події openOrder / orderStatus
- тримає ордер короткий час, щоб його було видно в TWS
- скасовує ордер
- чекає статус скасування
- показує результат
- коректно відключається

Увага:
- тільки paper account
- ордер навмисно ставиться далеко від ринку, щоб не виконався
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.order import Order
from ibapi.order_cancel import OrderCancel
from ibapi.wrapper import EWrapper

DEBUG = False

HOST = "127.0.0.1"
PORT = 7497
CLIENT_ID = 6

CONNECT_WAIT_SECONDS = 10.0
ORDER_WAIT_SECONDS = 10.0
CANCEL_WAIT_SECONDS = 10.0
VISIBLE_IN_TWS_SECONDS = 30.0
DISCONNECT_WAIT_SECONDS = 0.5

ORDER_ACTION = "BUY"
ORDER_QUANTITY = 20000
ORDER_LIMIT_PRICE = 1.25000


LOG_LEVEL = logging.DEBUG if DEBUG else logging.INFO
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class OrderStatusRow:
    """Один callback orderStatus."""

    order_id: int
    status: str
    filled: float
    remaining: float
    avg_fill_price: float


@dataclass
class OpenOrderRow:
    """Один callback openOrder."""

    order_id: int
    symbol: str
    action: str
    order_type: str
    total_quantity: float
    lmt_price: float
    status: str


@dataclass
class OrderSimulationResult:
    """Результат ручного тесту order simulation."""

    connected_ok: bool = False
    next_valid_id: int | None = None
    managed_accounts: str = ""
    placed_order_id: int | None = None
    open_orders: list[OpenOrderRow] = field(default_factory=list)
    order_statuses: list[OrderStatusRow] = field(default_factory=list)
    cancel_requested: bool = False
    cancel_confirmed: bool = False
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
            f"PLACED_ORDER_ID: {self.placed_order_id}",
            f"CANCEL_REQUESTED: {'YES' if self.cancel_requested else 'NO'}",
            f"CANCEL_CONFIRMED: {'YES' if self.cancel_confirmed else 'NO'}",
            "",
            "OPEN_ORDERS:",
        ]

        if self.open_orders:
            for row in self.open_orders:
                lines.append(
                    f"  - orderId={row.order_id}, "
                    f"symbol={row.symbol}, "
                    f"action={row.action}, "
                    f"type={row.order_type}, "
                    f"qty={row.total_quantity}, "
                    f"lmtPrice={row.lmt_price}, "
                    f"status={row.status}"
                )
        else:
            lines.append("  (none)")

        lines.append("")
        lines.append("ORDER_STATUSES:")
        if self.order_statuses:
            for row in self.order_statuses:
                lines.append(
                    f"  - orderId={row.order_id}, "
                    f"status={row.status}, "
                    f"filled={row.filled}, "
                    f"remaining={row.remaining}, "
                    f"avgFillPrice={row.avg_fill_price}"
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


class IBOrderSimulationApp(EWrapper, EClient):
    """Мінімальний IB-клієнт для place/cancel order."""

    def __init__(self) -> None:
        EWrapper.__init__(self)
        EClient.__init__(self, self)

        self.connected_ok = False
        self.next_valid_id_value: int | None = None
        self.managed_accounts_value: str = ""
        self.error_messages: list[str] = []
        self.open_orders_rows: list[OpenOrderRow] = []
        self.order_status_rows: list[OrderStatusRow] = []

        self._next_valid_id_event = threading.Event()
        self._open_order_event = threading.Event()
        self._order_status_event = threading.Event()
        self._cancel_confirmed_event = threading.Event()

    def is_next_valid_id_received(self) -> bool:
        """Чи отримано nextValidId."""
        return self._next_valid_id_event.is_set()

    def is_open_order_received(self) -> bool:
        """Чи отримано хоч один openOrder."""
        return self._open_order_event.is_set()

    def is_order_status_received(self) -> bool:
        """Чи отримано хоч один orderStatus."""
        return self._order_status_event.is_set()

    def is_cancel_confirmed(self) -> bool:
        """Чи підтверджено скасування."""
        return self._cancel_confirmed_event.is_set()

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

    def openOrder(self, orderId, contract, order, orderState) -> None:  # noqa
        """Callback: openOrder."""
        row = OpenOrderRow(
            order_id=int(orderId),
            symbol=str(contract.symbol or ""),
            action=str(order.action or ""),
            order_type=str(order.orderType or ""),
            total_quantity=float(order.totalQuantity),
            lmt_price=float(getattr(order, "lmtPrice", 0.0) or 0.0),
            status=str(getattr(orderState, "status", "") or ""),
        )
        self.open_orders_rows.append(row)
        self._open_order_event.set()
        logger.info(
            "openOrder received: orderId=%s symbol=%s action=%s type=%s "
            "qty=%s lmtPrice=%s status=%s",
            row.order_id,
            row.symbol,
            row.action,
            row.order_type,
            row.total_quantity,
            row.lmt_price,
            row.status,
        )

    def orderStatus(
        self,
        orderId,  # noqa
        status,  # noqa
        filled,  # noqa
        remaining,  # noqa
        avgFillPrice,  # noqa
        permId,  # noqa
        parentId,  # noqa
        lastFillPrice,  # noqa
        clientId,  # noqa
        whyHeld,  # noqa
        mktCapPrice,  # noqa
    ) -> None:  # noqa
        """Callback: orderStatus."""
        row = OrderStatusRow(
            order_id=int(orderId),
            status=str(status),
            filled=float(filled),
            remaining=float(remaining),
            avg_fill_price=float(avgFillPrice),
        )
        self.order_status_rows.append(row)
        self._order_status_event.set()
        logger.info(
            "orderStatus received: orderId=%s status=%s filled=%s remaining=%s "
            "avgFillPrice=%s",
            row.order_id,
            row.status,
            row.filled,
            row.remaining,
            row.avg_fill_price,
        )

        status_upper = row.status.upper()
        if status_upper in {"CANCELLED", "API CANCELLED", "PENDINGCANCEL"}:
            self._cancel_confirmed_event.set()

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

        if errorCode in {202, 2104, 2106, 2158, 399}:
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


def build_limit_order(action: str, quantity: float, limit_price: float) -> Order:
    """Створити LMT ордер."""
    order = Order()

    order.action = action
    order.orderType = "LMT"
    order.totalQuantity = quantity
    order.lmtPrice = limit_price

    order.tif = "GTC"  # <<< ОБОВ'ЯЗКОВО
    order.transmit = True

    return order


def analyze_result(result: OrderSimulationResult) -> str:
    """Короткий висновок за результатами."""
    if not result.connected_ok or result.next_valid_id is None:
        return "FAIL: немає нормального handshake."

    if result.placed_order_id is None:
        return "FAIL: order не був виставлений."

    if not result.open_orders and not result.order_statuses:
        return "FAIL: немає callback по ордеру."

    if result.cancel_requested and result.cancel_confirmed:
        return "SUCCESS: order lifecycle completed."

    return "PARTIAL: order виставлено, але підтвердження скасування не спіймано."


def run_test() -> OrderSimulationResult:
    """Запустити ручний тест place/cancel order."""
    app = IBOrderSimulationApp()
    result = OrderSimulationResult()

    thread: threading.Thread | None = None

    try:
        logger.info(
            "Order simulation test started: host=%s port=%s clientId=%s",
            HOST,
            PORT,
            CLIENT_ID,
        )
        logger.info("Connecting to %s:%s ...", HOST, PORT)
        app.connect(HOST, PORT, CLIENT_ID)

        thread = threading.Thread(
            target=app.run,
            name="ibapi-order-simulation",
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

        result.placed_order_id = int(app.next_valid_id_value)

        contract = build_gbpusd_contract()
        order = build_limit_order(
            action=ORDER_ACTION,
            quantity=ORDER_QUANTITY,
            limit_price=ORDER_LIMIT_PRICE,
        )

        logger.info(
            "Placing order: orderId=%s %s %s GBP.USD LMT @ %s",
            result.placed_order_id,
            ORDER_ACTION,
            ORDER_QUANTITY,
            ORDER_LIMIT_PRICE,
        )
        app.placeOrder(result.placed_order_id, contract, order)

        started = time.time()
        while time.time() - started < ORDER_WAIT_SECONDS:
            if app.is_open_order_received() or app.is_order_status_received():
                break
            time.sleep(0.1)

        logger.info(
            "Order is left visible for %.1f seconds so it can be seen in TWS...",
            VISIBLE_IN_TWS_SECONDS,
        )
        time.sleep(VISIBLE_IN_TWS_SECONDS)

        logger.info("Cancelling orderId=%s ...", result.placed_order_id)
        result.cancel_requested = True

        order_cancel = OrderCancel()
        app.cancelOrder(result.placed_order_id, order_cancel)

        started = time.time()
        while time.time() - started < CANCEL_WAIT_SECONDS:
            if app.is_cancel_confirmed():
                result.cancel_confirmed = True
                break
            time.sleep(0.1)

        result.connected_ok = app.connected_ok
        result.next_valid_id = app.next_valid_id_value
        result.managed_accounts = app.managed_accounts_value
        result.open_orders.extend(app.open_orders_rows)
        result.order_statuses.extend(app.order_status_rows)
        result.errors.extend(app.error_messages)

    except Exception as exc:
        error_text = f"Python exception: {type(exc).__name__}: {exc}"
        logger.exception("Unhandled exception during order simulation test")
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
    print("IB ORDER SIMULATION TEST")
    print("=" * 70)
    print(f"HOST={HOST}")
    print(f"PORT={PORT}")
    print(f"CLIENT_ID={CLIENT_ID}")
    print(f"DEBUG={DEBUG}")
    print(f"ORDER_ACTION={ORDER_ACTION}")
    print(f"ORDER_QUANTITY={ORDER_QUANTITY}")
    print(f"ORDER_LIMIT_PRICE={ORDER_LIMIT_PRICE}")
    print(f"VISIBLE_IN_TWS_SECONDS={VISIBLE_IN_TWS_SECONDS}")
    print()

    result = run_test()

    print("-" * 70)
    print(result.summary_text())
    print("ANALYSIS:", analyze_result(result))
    print("-" * 70)

    if (
        result.connected_ok
        and result.next_valid_id is not None
        and result.placed_order_id is not None
        and (result.open_orders or result.order_statuses)
    ):
        print("RESULT: SUCCESS")
        return 0

    print("RESULT: FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
