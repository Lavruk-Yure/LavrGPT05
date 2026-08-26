# run_market_availability_state_check.py
"""
Перевірка canonical market availability layer без broker API.

RoadMap87:
- перевіряє точні межі Forex weekend heuristic;
- перевіряє cTrader та IB;
- не підключається до broker;
- не створює ордерів;
- не залежить від поточного дня і часу.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.market_availability_state import (  # noqa: E402
    CTRADER_FOREX_WEEKDAY_HEURISTIC,
    CTRADER_FOREX_WEEKEND_HEURISTIC,
    IB_FOREX_WEEKDAY_HEURISTIC,
    IB_FOREX_WEEKEND_HEURISTIC,
    MARKET_CLOSED,
    MARKET_OPEN,
    MARKET_UNKNOWN,
    UNKNOWN,
    detect_market_state,
)


def _print_result(
    title: str,
    result,
) -> None:
    """
    Надрукувати canonical market availability result.
    """
    print(title)
    print(f"  state={result.state}")
    print(f"  source={result.source}")
    print(f"  symbol_name={result.symbol_name}")
    print(f"  broker={result.broker}")
    print(f"  checked_utc={result.checked_utc.isoformat()}")
    print(f"  reason={result.reason}")
    print("  can_place_market_order=" f"{result.can_place_market_order}")
    print("  can_place_pending_order=" f"{result.can_place_pending_order}")


def _require(
    condition: bool,
    message: str,
) -> None:
    """
    Перервати diagnostic зі зрозумілою причиною.
    """
    if not condition:
        raise AssertionError(message)


def _check_forex_case(
    *,
    title: str,
    broker: str,
    checked_utc: datetime,
    expected_state: str,
    expected_source: str,
) -> None:
    """
    Перевірити один Forex market availability case.
    """
    result = detect_market_state(
        broker=broker,
        symbol_name="EURUSD",
        checked_utc=checked_utc,
    )

    _print_result(title, result)

    _require(
        result.state == expected_state,
        f"{title}: expected state={expected_state}, " f"actual={result.state}",
    )
    _require(
        result.source == expected_source,
        f"{title}: expected source={expected_source}, " f"actual={result.source}",
    )
    _require(
        result.broker == broker,
        f"{title}: expected broker={broker}, " f"actual={result.broker}",
    )
    _require(
        result.symbol_name == "EURUSD",
        f"{title}: expected symbol=EURUSD, " f"actual={result.symbol_name}",
    )

    expected_market_order = expected_state == MARKET_OPEN

    _require(
        result.can_place_market_order is expected_market_order,
        (
            f"{title}: incorrect can_place_market_order="
            f"{result.can_place_market_order}"
        ),
    )
    _require(
        result.can_place_pending_order is True,
        (
            f"{title}: incorrect can_place_pending_order="
            f"{result.can_place_pending_order}"
        ),
    )

    print("  result=OK")
    print()


def _check_non_forex_symbol(
    broker: str,
) -> None:
    """
    Перевірити MARKET_UNKNOWN для non-Forex symbol.
    """
    title = f"{broker} non-Forex symbol"

    result = detect_market_state(
        broker=broker,
        symbol_name="AAPL",
        checked_utc=datetime(
            2026,
            7,
            11,
            12,
            0,
            tzinfo=UTC,
        ),
    )

    _print_result(title, result)

    _require(
        result.state == MARKET_UNKNOWN,
        f"{title}: expected state={MARKET_UNKNOWN}, " f"actual={result.state}",
    )
    _require(
        result.source == UNKNOWN,
        f"{title}: expected source={UNKNOWN}, " f"actual={result.source}",
    )
    _require(
        result.can_place_market_order is False,
        f"{title}: market order must be unavailable",
    )
    _require(
        result.can_place_pending_order is False,
        f"{title}: pending order must be unavailable",
    )

    print("  result=OK")
    print()


def main() -> int:
    """
    Запустити boundary diagnostic для cTrader та IB.
    """
    friday_before_close = datetime(
        2026,
        7,
        10,
        21,
        59,
        tzinfo=UTC,
    )
    friday_at_close = datetime(
        2026,
        7,
        10,
        22,
        0,
        tzinfo=UTC,
    )
    saturday = datetime(
        2026,
        7,
        11,
        12,
        0,
        tzinfo=UTC,
    )
    sunday_before_open = datetime(
        2026,
        7,
        12,
        21,
        59,
        tzinfo=UTC,
    )
    sunday_at_open = datetime(
        2026,
        7,
        12,
        22,
        0,
        tzinfo=UTC,
    )

    broker_sources = {
        "CTRADER": {
            MARKET_OPEN: CTRADER_FOREX_WEEKDAY_HEURISTIC,
            MARKET_CLOSED: CTRADER_FOREX_WEEKEND_HEURISTIC,
        },
        "IB": {
            MARKET_OPEN: IB_FOREX_WEEKDAY_HEURISTIC,
            MARKET_CLOSED: IB_FOREX_WEEKEND_HEURISTIC,
        },
    }

    time_cases = [
        (
            "Friday 21:59 UTC",
            friday_before_close,
            MARKET_OPEN,
        ),
        (
            "Friday 22:00 UTC",
            friday_at_close,
            MARKET_CLOSED,
        ),
        (
            "Saturday 12:00 UTC",
            saturday,
            MARKET_CLOSED,
        ),
        (
            "Sunday 21:59 UTC",
            sunday_before_open,
            MARKET_CLOSED,
        ),
        (
            "Sunday 22:00 UTC",
            sunday_at_open,
            MARKET_OPEN,
        ),
    ]

    try:
        for broker, sources in broker_sources.items():
            for case_name, checked_utc, expected_state in time_cases:
                _check_forex_case(
                    title=f"{broker} — {case_name}",
                    broker=broker,
                    checked_utc=checked_utc,
                    expected_state=expected_state,
                    expected_source=sources[expected_state],
                )

            _check_non_forex_symbol(broker)

    except AssertionError as exc:
        print("MARKET_AVAILABILITY_BOUNDARY_CHECK=FAILED")
        print(f"reason={exc}")
        return 1

    print("MARKET_AVAILABILITY_BOUNDARY_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
