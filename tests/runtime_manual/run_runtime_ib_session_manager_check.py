# run_runtime_ib_session_manager_check.py
"""
Тест IBSessionManager.

RoadMap75:
1. Створення manager.
2. Connect DEMO без TWS.
3. Перевірка стану.
4. Disconnect.
"""

from __future__ import annotations

from pprint import pprint

from engine.ib_session_manager import IBSessionManager


def main() -> None:
    print()
    print("=== CREATE SESSION MANAGER ===")

    manager = IBSessionManager()

    print("manager created")
    print()

    print("=== CONNECT DEMO ===")

    adapter = manager.connect_demo()

    print()
    print("=== ADAPTER ===")

    pprint(
        {
            "adapter_exists": adapter is not None,
            "account_mode": manager.get_active_account_mode(),
            "connected": adapter.is_connected(),
        }
    )

    print()
    print("=== DISCONNECT ===")

    manager.disconnect()

    print("disconnect finished")

    print()
    print("=== DONE ===")


if __name__ == "__main__":
    main()
