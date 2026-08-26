# run_ib_market_availability_check.py
"""
IB market availability runtime check.

RoadMap67:
- function-level IB market availability check;
- no UI dependency;
- no order execution;
- no TWS order placement.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.market_availability_state import (
    IB_FOREX_WEEKDAY_HEURISTIC,
    IB_FOREX_WEEKEND_HEURISTIC,
    MARKET_CLOSED,
    MARKET_OPEN,
    detect_ib_market_state,
    detect_market_state,
)


def print_result(title: str, result) -> None:
    """
    Print canonical market availability result.
    """
    print(title)
    print(f"  state={result.state}")
    print(f"  source={result.source}")
    print(f"  symbol_name={result.symbol_name}")
    print(f"  broker={result.broker}")
    print(f"  checked_utc={result.checked_utc.isoformat()}")
    print(f"  reason={result.reason}")
    print(f"  can_place_market_order={result.can_place_market_order}")
    print(f"  can_place_pending_order={result.can_place_pending_order}")


def main() -> int:
    """
    Run IB market availability function check.
    """
    weekend_dt = datetime(2026, 5, 16, 9, 0, tzinfo=UTC)
    weekday_dt = datetime(2026, 5, 18, 9, 0, tzinfo=UTC)

    weekend_result = detect_ib_market_state(
        symbol_name="EURUSD",
        checked_utc=weekend_dt,
    )
    print_result("IB weekend heuristic:", weekend_result)

    assert weekend_result.state == MARKET_CLOSED
    assert weekend_result.source == IB_FOREX_WEEKEND_HEURISTIC
    assert weekend_result.can_place_market_order is False
    assert weekend_result.can_place_pending_order is True

    weekday_result = detect_ib_market_state(
        symbol_name="EURUSD",
        checked_utc=weekday_dt,
    )
    print_result("IB weekday heuristic:", weekday_result)

    assert weekday_result.state == MARKET_OPEN
    assert weekday_result.source == IB_FOREX_WEEKDAY_HEURISTIC
    assert weekday_result.can_place_market_order is True
    assert weekday_result.can_place_pending_order is True

    generic_ib_result = detect_market_state(
        broker="IB",
        symbol_name="EURUSD",
        checked_utc=weekend_dt,
    )
    print_result("Generic broker-independent IB check:", generic_ib_result)

    assert generic_ib_result.state == MARKET_CLOSED
    assert generic_ib_result.broker == "IB"

    print("IB_MARKET_AVAILABILITY_CHECK=OK")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
