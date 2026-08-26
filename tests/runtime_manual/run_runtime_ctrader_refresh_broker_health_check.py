# run_runtime_ctrader_refresh_broker_health_check.py

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
from engine.services.ctrader_runtime_service import (  # noqa: E402
    CTraderRuntimeService,
)


def main() -> int:
    service = CTraderRuntimeService()

    print("\n=== CASE 1: NO ADAPTER ===")

    health = service.refresh_broker_health()

    print(f"state={health.state}")
    print(f"error={health.last_error}")

    check1 = not health.is_connected()

    print("\n=== CASE 2: CONNECTED ADAPTER ===")

    service.connect_demo()

    health = service.refresh_broker_health()

    print(f"state={health.state}")
    print(f"error={health.last_error}")

    check2 = health.state == HEALTH_CONNECTED

    adapter = service.get_active_adapter()

    print("\n=== CASE 3: FORCED SAFE_DISCONNECTED ===")

    adapter.disconnect()

    health = service.refresh_broker_health()

    print(f"state={health.state}")
    print(f"error={health.last_error}")

    check3 = health.state == HEALTH_SAFE_DISCONNECTED

    if check1 and check2 and check3:
        print("\nRUNTIME_CTRADER_REFRESH_BROKER_HEALTH_CHECK=OK")
        return 0

    print("\nRUNTIME_CTRADER_REFRESH_BROKER_HEALTH_CHECK=FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
