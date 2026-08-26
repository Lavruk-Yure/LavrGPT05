# run_runtime_market_state_scheduler_check.py
"""
Runtime market-state scheduler integration diagnostic.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.runtime_market_state_task import (  # noqa: E402
    RuntimeMarketStateTask,
)
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

    task = RuntimeMarketStateTask(
        broker="CTRADER",
        symbol_name="EURUSD",
        logger_=logger,
    )

    scheduler = RuntimeScheduler(logger_=logger)

    scheduler.add_periodic_task(
        interval_seconds=1.0,
        task=task.refresh_market_state,
    )

    scheduler.start()

    time.sleep(3.5)

    scheduler.stop()

    print(f"market_checks_count={task.market_checks_count}")
    print(f"last_state={task.last_state}")
    print(f"last_check_utc={task.last_check_utc}")

    checks = [
        task.market_checks_count >= 3,
        task.last_state
        in {
            "MARKET_OPEN",
            "MARKET_CLOSED",
        },
        task.last_check_utc != "",
        scheduler.is_running is False,
    ]

    if all(checks):
        print("RUNTIME_MARKET_STATE_CHECK=OK")
        return 0

    print("RUNTIME_MARKET_STATE_CHECK=FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
