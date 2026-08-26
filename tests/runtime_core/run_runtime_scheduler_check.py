# run_runtime_scheduler_check.py
"""
RuntimeScheduler diagnostic.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.runtime_scheduler import RuntimeScheduler  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)


startup_counter = 0
periodic_counter = 0


def startup_task() -> None:
    """
    Startup task.
    """

    global startup_counter

    startup_counter += 1

    print(f"startup_task executed: {startup_counter}")


def periodic_task() -> None:
    """
    Periodic task.
    """

    global periodic_counter

    periodic_counter += 1

    print(f"periodic_task executed: {periodic_counter}")


def main() -> int:
    """
    Run diagnostic.
    """

    scheduler = RuntimeScheduler(logger_=logger)

    scheduler.add_startup_task(startup_task)

    scheduler.add_periodic_task(
        interval_seconds=1.0,
        task=periodic_task,
    )

    scheduler.start()

    time.sleep(3.5)

    scheduler.stop()

    checks = [
        startup_counter == 1,
        periodic_counter >= 3,
        scheduler.is_running is False,
    ]

    print(f"startup_counter={startup_counter}")
    print(f"periodic_counter={periodic_counter}")

    if all(checks):
        print("RUNTIME_SCHEDULER_CHECK=OK")
        return 0

    print("RUNTIME_SCHEDULER_CHECK=FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
