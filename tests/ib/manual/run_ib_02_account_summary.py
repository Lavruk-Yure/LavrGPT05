# run_ib_02_account_summary.py
# -*- coding: utf-8 -*-
"""
RoadMap51: ручний тест читання account summary з Interactive Brokers TWS API.

Що робить:
- підключається до TWS/Gateway
- чекає nextValidId
- запитує account summary
- збирає NetLiquidation / TotalCashValue / Currency
- показує результат
- коректно відключається

Без positions.
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
from ibapi.wrapper import EWrapper

DEBUG = False

HOST = "127.0.0.1"
PORT = 7497
CLIENT_ID = 2

CONNECT_WAIT_SECONDS = 5.0
SUMMARY_WAIT_SECONDS = 10.0
DISCONNECT_WAIT_SECONDS = 0.5

SUMMARY_REQ_ID = 1001
SUMMARY_GROUP = "All"
SUMMARY_TAGS = "NetLiquidation,TotalCashValue,Currency"


LOG_LEVEL = logging.DEBUG if DEBUG else logging.INFO
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class SummaryRow:
    """Один рядок account summary."""

    req_id: int
    account: str
    tag: str
    value: str
    currency: str


@dataclass
class AccountSummaryResult:
    """Результат ручного тесту account summary."""

    connected_ok: bool = False
    next_valid_id: int | None = None
    managed_accounts: str = ""
    summary_completed: bool = False
    summary_rows: list[SummaryRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def find_tag_values(self, tag_name: str) -> list[SummaryRow]:
        """Повернути всі рядки з потрібним tag."""
        return [row for row in self.summary_rows if row.tag == tag_name]

    def summary_text(self) -> str:
        """Повернути текстовий підсумок."""
        lines: list[str] = [
            f"HOST: {HOST}",
            f"PORT: {PORT}",
            f"CLIENT_ID: {CLIENT_ID}",
            f"CONNECTED: {'YES' if self.connected_ok else 'NO'}",
            f"NEXT_VALID_ID: {self.next_valid_id}",
            f"MANAGED_ACCOUNTS: {self.managed_accounts or '(empty)'}",
            f"SUMMARY_COMPLETED: {'YES' if self.summary_completed else 'NO'}",
            "",
            "SUMMARY_ROWS:",
        ]

        if self.summary_rows:
            for row in self.summary_rows:
                lines.append(
                    f"  - account={row.account}, "
                    f"tag={row.tag}, value={row.value}, currency={row.currency}"
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


class IBAccountSummaryApp(EWrapper, EClient):
    """Мінімальний IB-клієнт для account summary."""

    def __init__(self) -> None:
        EWrapper.__init__(self)
        EClient.__init__(self, self)

        self.connected_ok = False
        self.next_valid_id_value: int | None = None
        self.managed_accounts_value: str = ""
        self.error_messages: list[str] = []
        self.summary_rows: list[SummaryRow] = []
        self.summary_completed = False

        self._next_valid_id_event = threading.Event()
        self._summary_end_event = threading.Event()

    def is_next_valid_id_received(self) -> bool:
        """Чи отримано nextValidId."""
        return self._next_valid_id_event.is_set()

    def is_summary_completed(self) -> bool:
        """Чи завершено account summary."""
        return self._summary_end_event.is_set()

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

    def accountSummary(
        self,
        reqId: int,  # noqa
        account: str,
        tag: str,
        value: str,
        currency: str,
    ) -> None:
        """Callback: один рядок account summary."""
        row = SummaryRow(
            req_id=reqId,
            account=account,
            tag=tag,
            value=value,
            currency=currency,
        )
        self.summary_rows.append(row)
        logger.info(
            "accountSummary received: reqId=%s account=%s tag=%s value=%s "
            "currency=%s",
            reqId,
            account,
            tag,
            value,
            currency,
        )

    def accountSummaryEnd(self, reqId: int) -> None:  # noqa
        """Callback: завершення account summary."""
        self.summary_completed = True
        logger.info("accountSummaryEnd received: reqId=%s", reqId)
        self._summary_end_event.set()

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


def analyze_result(result: AccountSummaryResult) -> str:
    """Короткий висновок за результатами."""
    if not result.connected_ok or result.next_valid_id is None:
        return "FAIL: немає нормального handshake."

    if not result.summary_completed:
        return "FAIL: account summary не завершився по timeout."

    if not result.summary_rows:
        return "FAIL: account summary завершився, але рядки не прийшли."

    has_net_liq = any(row.tag == "NetLiquidation" for row in result.summary_rows)
    has_cash = any(row.tag == "TotalCashValue" for row in result.summary_rows)
    has_any_currency = any((row.currency or "").strip() for row in result.summary_rows)

    if has_net_liq and has_cash and has_any_currency:
        return "SUCCESS: account summary received."

    return "PARTIAL: account summary завершився, але прийшли не всі очікувані дані."


def run_test() -> AccountSummaryResult:
    """Запустити ручний тест account summary."""
    app = IBAccountSummaryApp()
    result = AccountSummaryResult()

    thread: threading.Thread | None = None

    try:
        logger.info(
            "Account summary test started: host=%s port=%s clientId=%s",
            HOST,
            PORT,
            CLIENT_ID,
        )
        logger.info("Connecting to %s:%s ...", HOST, PORT)
        app.connect(HOST, PORT, CLIENT_ID)

        thread = threading.Thread(
            target=app.run,
            name="ibapi-account-summary",
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

        logger.info(
            "Requesting account summary: reqId=%s group=%s tags=%s",
            SUMMARY_REQ_ID,
            SUMMARY_GROUP,
            SUMMARY_TAGS,
        )
        app.reqAccountSummary(SUMMARY_REQ_ID, SUMMARY_GROUP, SUMMARY_TAGS)

        started = time.time()
        while time.time() - started < SUMMARY_WAIT_SECONDS:
            if app.is_summary_completed():
                break
            time.sleep(0.1)

        try:
            app.cancelAccountSummary(SUMMARY_REQ_ID)
        except Exception as exc:
            logger.warning("cancelAccountSummary failed: %s", exc)

        result.connected_ok = app.connected_ok
        result.next_valid_id = app.next_valid_id_value
        result.managed_accounts = app.managed_accounts_value
        result.summary_completed = app.summary_completed
        result.summary_rows.extend(app.summary_rows)
        result.errors.extend(app.error_messages)

    except Exception as exc:
        error_text = f"Python exception: {type(exc).__name__}: {exc}"
        logger.exception("Unhandled exception during account summary test")
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
    print("IB ACCOUNT SUMMARY TEST")
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
        and result.summary_completed
        and result.summary_rows
    ):
        print("RESULT: SUCCESS")
        return 0

    print("RESULT: FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
