# tests/runtime_manual/run_runtime_ctrader_manual_buy_close_check.py
"""
Manual cTrader BUY/CLOSE check для RoadMap81.

УВАГА:
- відкриває реальну DEMO позицію;
- після цього одразу пробує її закрити;
- використовувати тільки на cTrader DEMO.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from pprint import pprint

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.broker_position import BrokerPosition  # noqa: E402
from engine.ctrader_session_manager import CTraderSessionManager  # noqa: E402


def _configure_logging() -> None:
    """
    Налаштувати logging для ручного runtime test.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def _print_positions(
    title: str,
    positions: list[BrokerPosition],
) -> None:
    """
    Надрукувати positions snapshot.
    """
    print(f"\n=== {title} ===")
    print(f"positions_count={len(positions)}")

    for position in positions:
        pprint(position.to_dict())


def _find_new_position(
    before: list[BrokerPosition],
    after: list[BrokerPosition],
) -> BrokerPosition | None:
    """
    Знайти position, яка з'явилася після order.
    """
    before_ids = {str(position.position_id) for position in before}

    for position in after:
        if str(position.position_id) not in before_ids:
            return position

    return None


def main() -> int:
    """
    Запустити ручний BUY/CLOSE сценарій cTrader DEMO.
    """
    _configure_logging()

    session_manager = CTraderSessionManager()

    adapter = session_manager.connect_demo()

    if adapter is None:
        print("CTRADER_MANUAL_BUY_CLOSE_CHECK=CONNECT_FAILED")
        return 1

    try:
        before_positions = adapter.get_positions()
        _print_positions("POSITIONS BEFORE BUY", before_positions)

        print("\n=== SEND BUY MARKET EURUSD 0.01 ===")
        result = adapter.place_market_buy(
            symbol_name="EURUSD",
            lots=0.01,
            comment="LGE RoadMap81 manual BUY test",
        )
        print("BUY_RESULT:")
        pprint(result)

        time.sleep(2.0)

        after_buy_positions = adapter.get_positions()
        _print_positions("POSITIONS AFTER BUY", after_buy_positions)

        new_position = _find_new_position(
            before=before_positions,
            after=after_buy_positions,
        )

        if new_position is None:
            print("CTRADER_MANUAL_BUY_CLOSE_CHECK=NO_NEW_POSITION")
            return 1

        print("\n=== CLOSE NEW POSITION ===")
        print(f"position_id={new_position.position_id}")

        close_result = adapter.close_position(
            position_id=new_position.position_id,
        )
        print("CLOSE_RESULT:")
        pprint(close_result)

        time.sleep(2.0)

        after_close_positions = adapter.get_positions()
        _print_positions("POSITIONS AFTER CLOSE", after_close_positions)

        remaining_ids = {
            str(position.position_id) for position in after_close_positions
        }

        if str(new_position.position_id) in remaining_ids:
            print("CTRADER_MANUAL_BUY_CLOSE_CHECK=CLOSE_FAILED")
            return 1

        print("CTRADER_MANUAL_BUY_CLOSE_CHECK=OK")
        return 0

    finally:
        session_manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
