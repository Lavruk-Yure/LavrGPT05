# run_runtime_heartbeat_scheduler_check.py
"""
Runtime heartbeat + scheduler integration diagnostic.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.runtime_heartbeat import RuntimeHeartbeat  # noqa: E402
from engine.runtime_scheduler import RuntimeScheduler  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)


def main() -> int:
    """
    Run diagnostic.
    """

    heartbeat = RuntimeHeartbeat(logger_=logger)

    scheduler = RuntimeScheduler(logger_=logger)

    scheduler.add_periodic_task(
        interval_seconds=1.0,
        task=heartbeat.heartbeat,
    )

    scheduler.start()

    time.sleep(3.5)

    scheduler.stop()

    print(f"heartbeat_counter={heartbeat.heartbeat_counter}")
    print(f"last_heartbeat_utc={heartbeat.last_heartbeat_utc}")

    checks = [
        heartbeat.heartbeat_counter >= 3,
        heartbeat.last_heartbeat_utc != "",
        scheduler.is_running is False,
    ]

    if all(checks):
        print("RUNTIME_HEARTBEAT_CHECK=OK")
        return 0

    print("RUNTIME_HEARTBEAT_CHECK=FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
