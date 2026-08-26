# run_broker_position_check.py
"""
Diagnostic: перевірка canonical BrokerPosition model.

RoadMap68:
- без broker API;
- без Qt;
- без SQLite;
- швидкий smoke-test для unified positions foundation.
"""

from __future__ import annotations

import sys
from pathlib import Path
from pprint import pprint

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.broker_position import (  # noqa: E402
    POSITION_SIDE_BUY,
    POSITION_SIDE_SELL,
    POSITION_SIDE_UNKNOWN,
    BrokerPosition,
    normalize_position_side,
)


def main() -> int:
    """
    Запустити diagnostic.
    """

    position = BrokerPosition(
        broker="IB",
        account_id="DU123456",
        account_mode="DEMO",
        position_id="IB:DU123456:EURUSD",
        symbol_name="EURUSD",
        side=POSITION_SIDE_BUY,
        volume=10000.0,
        entry_price=1.085,
        current_price=1.087,
        stop_loss=1.08,
        take_profit=1.095,
        unrealized_pnl=20.0,
        currency="USD",
        opened_utc="",
        raw_payload={"source": "diagnostic"},
    )

    pprint(position.to_dict())

    checks = [
        position.to_dict()["broker"] == "IB",
        position.to_dict()["symbol_name"] == "EURUSD",
        normalize_position_side("BUY") == POSITION_SIDE_BUY,
        normalize_position_side("LONG") == POSITION_SIDE_BUY,
        normalize_position_side("1") == POSITION_SIDE_BUY,
        normalize_position_side("SELL") == POSITION_SIDE_SELL,
        normalize_position_side("SHORT") == POSITION_SIDE_SELL,
        normalize_position_side("2") == POSITION_SIDE_SELL,
        normalize_position_side("bad") == POSITION_SIDE_UNKNOWN,
        normalize_position_side(None) == POSITION_SIDE_UNKNOWN,
    ]

    if all(checks):
        print("BROKER_POSITION_CHECK=OK")
        return 0

    print("BROKER_POSITION_CHECK=FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
