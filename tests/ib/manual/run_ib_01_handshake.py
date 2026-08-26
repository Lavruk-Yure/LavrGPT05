# run_ib_01_handshake.py
# -*- coding: utf-8 -*-
"""
RoadMap51: ручний тест Handshake для Interactive Brokers TWS API.

Що робить:
- підключається до TWS/Gateway
- робить до 5 спроб
- чекає nextValidId / managedAccounts
- збирає та показує помилки
- коректно відключається

Без ордерів.
Без market data.
Без historical data.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

from ibapi.client import EClient
from ibapi.wrapper import EWrapper

# Налаштування запуску
HOST = "127.0.0.1"
PORT = 7497
CLIENT_ID_BASE = 1

MAX_ATTEMPTS = 1
CONNECT_WAIT_SECONDS = 5.0
SLEEP_BETWEEN_ATTEMPTS_SECONDS = 2.0
DISCONNECT_WAIT_SECONDS = 0.5

DEBUG = False
LOG_LEVEL = logging.DEBUG if DEBUG else logging.INFO


logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class HandshakeResult:
    """Результат однієї спроби handshake."""

    attempt_no: int
    host: str
    port: int
    client_id: int
    connected_ok: bool = False
    next_valid_id: int | None = None
    managed_accounts: str = ""
    errors: list[str] = field(default_factory=list)

    def summary_text(self) -> str:
        """Повернути короткий текстовий підсумок."""
        lines: list[str] = [
            f"ATTEMPT: {self.attempt_no}",
            f"HOST: {self.host}",
            f"PORT: {self.port}",
            f"CLIENT_ID: {self.client_id}",
            f"CONNECTED: {'YES' if self.connected_ok else 'NO'}",
            f"NEXT_VALID_ID: {self.next_valid_id}",
            f"MANAGED_ACCOUNTS: {self.managed_accounts or '(empty)'}",
        ]
        if self.errors:
            lines.append("ERRORS:")
            for item in self.errors:
                lines.append(f"  - {item}")
        else:
            lines.append("ERRORS: none")
        return "\n".join(lines)


class IBHandshakeApp(EWrapper, EClient):
    """Мінімальний IB-клієнт для тесту connect/disconnect."""

    def __init__(self) -> None:
        EWrapper.__init__(self)
        EClient.__init__(self, self)

        self.connected_ok = False
        self.next_valid_id_value: int | None = None
        self.managed_accounts_value: str = ""
        self.error_messages: list[str] = []

        self._next_valid_id_event = threading.Event()
        self._managed_accounts_event = threading.Event()

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
        self._managed_accounts_event.set()

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

    def is_next_valid_id_received(self) -> bool:
        """Чи отримано nextValidId."""
        return self._next_valid_id_event.is_set()


def run_single_handshake_attempt(
    attempt_no: int,
    host: str,
    port: int,
    client_id: int,
    wait_seconds: float,
) -> HandshakeResult:
    """Виконати одну спробу handshake."""
    logger.info(
        "Handshake attempt %s started: host=%s port=%s clientId=%s",
        attempt_no,
        host,
        port,
        client_id,
    )

    app = IBHandshakeApp()
    result = HandshakeResult(
        attempt_no=attempt_no,
        host=host,
        port=port,
        client_id=client_id,
    )

    thread: threading.Thread | None = None

    try:
        logger.info("Connecting to %s:%s ...", host, port)
        app.connect(host, port, client_id)

        # Окремий потік потрібен для app.run(), бо цей цикл блокує виконання.
        thread = threading.Thread(
            target=app.run,
            name=f"ibapi-handshake-{attempt_no}",
            daemon=True,
        )
        thread.start()

        started = time.time()
        while time.time() - started < wait_seconds:
            if app.is_next_valid_id_received():
                break
            time.sleep(0.1)

        result.connected_ok = app.connected_ok
        result.next_valid_id = app.next_valid_id_value
        result.managed_accounts = app.managed_accounts_value
        result.errors.extend(app.error_messages)

        logger.info(
            "Handshake attempt %s finished, connected_ok=%s",
            attempt_no,
            result.connected_ok,
        )

    except Exception as exc:
        error_text = f"Python exception: {type(exc).__name__}: {exc}"
        logger.exception("Unhandled exception during handshake")
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


def analyze_result(result: HandshakeResult) -> str:
    """Повернути короткий людський висновок по спробі."""
    if result.connected_ok and result.next_valid_id is not None:
        return "SUCCESS: handshake completed."

    joined_errors = "\n".join(result.errors)

    if "code=502" in joined_errors:
        return (
            "FAIL: TWS/Gateway недоступний. "
            "Перевірити, чи запущений TWS, чи правильний host/port."
        )

    if "code=504" in joined_errors:
        return (
            "FAIL: not connected. Зазвичай або TWS не прийняв з'єднання, "
            "або клієнт відвалився відразу."
        )

    if "code=326" in joined_errors:
        return (
            "FAIL: clientId already in use. "
            "Закрити інший клієнт або змінити clientId."
        )

    if "code=1300" in joined_errors:
        return (
            "FAIL: socket port changed on TWS side. " "Перевірити API settings у TWS."
        )

    if "code=2104" in joined_errors or "code=2106" in joined_errors:
        return (
            "PARTIAL: є серверні info-повідомлення, але handshake не завершився. "
            "Дивись, чи прийшов nextValidId."
        )

    if not result.errors:
        return (
            "FAIL: помилок нема, але nextValidId не прийшов. "
            "Можливо, замалий timeout або TWS завис."
        )

    return "FAIL: handshake not completed. Дивись список помилок."


def main() -> int:
    """Точка входу."""
    print("=" * 70)
    print("IB HANDSHAKE TEST")
    print("=" * 70)
    print(f"HOST={HOST}")
    print(f"PORT={PORT}")
    print(f"MAX_ATTEMPTS={MAX_ATTEMPTS}")
    print()

    final_success = False

    for attempt_no in range(1, MAX_ATTEMPTS + 1):
        client_id = CLIENT_ID_BASE + attempt_no - 1

        result = run_single_handshake_attempt(
            attempt_no=attempt_no,
            host=HOST,
            port=PORT,
            client_id=client_id,
            wait_seconds=CONNECT_WAIT_SECONDS,
        )

        print("-" * 70)
        print(result.summary_text())
        print("ANALYSIS:", analyze_result(result))
        print("-" * 70)

        if result.connected_ok and result.next_valid_id is not None:
            final_success = True
            print("RESULT: SUCCESS")
            break

        if attempt_no < MAX_ATTEMPTS:
            print(
                f"Waiting {SLEEP_BETWEEN_ATTEMPTS_SECONDS:.1f}s before next attempt..."
            )
            time.sleep(SLEEP_BETWEEN_ATTEMPTS_SECONDS)

    if not final_success:
        print("RESULT: FAILED AFTER ALL ATTEMPTS")
        return 1

    print("RESULT: DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
