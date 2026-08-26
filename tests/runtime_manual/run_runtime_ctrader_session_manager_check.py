# run_runtime_ctrader_session_manager_check.py
"""
RoadMap69:
Перевірка SessionManager reconnect.
"""

from __future__ import annotations

import logging
import time

from engine.ctrader_session_manager import (
    CTraderSessionManager,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


def main() -> None:
    """
    Main test.
    """

    manager = CTraderSessionManager()

    print()
    print("=== CONNECT #1 ===")
    print()

    adapter1 = manager.connect_demo()

    time.sleep(10)

    print()
    print("=== PAUSE BEFORE RECONNECT TEST ===")
    print("Now you can disable internet. Waiting 30 seconds...")
    print()

    time.sleep(30)

    adapter2 = None

    for attempt in range(1, 11):
        print()
        print(f"=== RECONNECT ATTEMPT {attempt}/10 ===")
        print()

        adapter2 = manager.reconnect()

        time.sleep(20)

        if adapter2 is not None and adapter2.is_connected():
            print()
            print("CONNECTED AFTER RECONNECT")
            print()
            break
    else:
        print()
        print("NOT CONNECTED AFTER 10 ATTEMPTS")
        print()

    print()
    print("=== CHECK ===")
    print()

    print(
        "adapter1 alive:",
        adapter1.is_session_alive(),
    )

    if adapter2 is not None:
        print(
            "adapter2 alive:",
            adapter2.is_session_alive(),
        )

    print()

    print("=== DISCONNECT ===")
    print()

    manager.disconnect()

    time.sleep(3)

    print()
    print("DONE")
    print()


if __name__ == "__main__":
    main()
