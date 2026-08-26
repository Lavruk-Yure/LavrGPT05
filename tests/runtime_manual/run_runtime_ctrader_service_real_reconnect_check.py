# run_runtime_ctrader_service_real_reconnect_check.py
"""
RoadMap74.3.2.

Real reconnect check через production service layer.

Сценарій:
1. CTraderRuntimeService.connect_demo()
2. CONNECTED
3. Примусовий adapter.disconnect()
4. refresh_broker_health() -> SAFE_DISCONNECTED
5. RuntimeReconnectTask.run_once()
6. service.reconnect()
7. CONNECTED
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.runtime_broker_health import (  # noqa: E402
    HEALTH_CONNECTED,
    HEALTH_SAFE_DISCONNECTED,
)
from engine.runtime_reconnect_task import RuntimeReconnectTask  # noqa: E402
from engine.services.ctrader_runtime_service import CTraderRuntimeService  # noqa: E402


def main() -> int:
    service = CTraderRuntimeService()

    print("\n=== STEP 1: INITIAL CONNECT ===")

    connect_result = service.connect_demo()
    health = service.get_broker_health()
    adapter_before = service.get_active_adapter()

    print(f"connect_result={connect_result}")
    print(f"health={health.state}")
    print(
        "adapter_before_alive="
        f"{adapter_before.is_session_alive() if adapter_before else None}"
    )

    check1 = (
        connect_result is not None
        and health.state == HEALTH_CONNECTED
        and adapter_before is not None
        and adapter_before.is_session_alive() is True
    )

    print("\n=== STEP 2: FORCE DISCONNECT ===")

    if adapter_before is not None:
        adapter_before.disconnect()

    health = service.refresh_broker_health()

    print(f"health={health.state}")
    print(f"error={health.last_error}")
    print(
        "adapter_before_alive_after_disconnect="
        f"{adapter_before.is_session_alive() if adapter_before else None}"
    )

    check2 = health.state == HEALTH_SAFE_DISCONNECTED

    print("\n=== STEP 3: RECONNECT TASK RUN_ONCE ===")

    task = RuntimeReconnectTask(
        runtime_service=service,
        reconnect_cooldown_seconds=0.0,
    )

    task.run_once()

    health_after = service.get_broker_health()
    adapter_after = service.get_active_adapter()

    print(f"reconnect_attempts={task.reconnect_attempts}")
    print(f"health_after={health_after.state}")
    print(f"error_after={health_after.last_error}")
    print(
        "adapter_after_alive="
        f"{adapter_after.is_session_alive() if adapter_after else None}"
    )
    print("adapter_replaced=" f"{adapter_after is not adapter_before}")

    check3 = (
        task.reconnect_attempts == 1
        and health_after.state == HEALTH_CONNECTED
        and adapter_after is not None
        and adapter_after.is_session_alive() is True
        and adapter_after is not adapter_before
    )

    if check1 and check2 and check3:
        print("\nRUNTIME_CTRADER_SERVICE_REAL_RECONNECT_CHECK=OK")
        return 0

    print("\nRUNTIME_CTRADER_SERVICE_REAL_RECONNECT_CHECK=FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
