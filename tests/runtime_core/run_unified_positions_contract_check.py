# run_unified_positions_contract_check.py
"""
Unified broker positions contract diagnostic.

RoadMap68:
- перевіряє canonical get_positions() contract;
- перевіряє unified BrokerPosition model;
- IB + cTrader через один interface.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.broker_position import BrokerPosition  # noqa: E402
from engine.ctrader_adapter import CTraderAdapter  # noqa: E402
from engine.ib_adapter import IBAdapter  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)


def _validate_positions(
    broker_name: str,
    positions: list[BrokerPosition],
) -> bool:
    """
    Перевірити canonical BrokerPosition list.
    """

    print(f"{broker_name}: positions_count={len(positions)}")

    for idx, position in enumerate(positions, start=1):
        data = position.to_dict()

        print(
            f"{broker_name} POSITION {idx}: "
            f"{data['symbol_name']} | "
            f"{data['side']} | "
            f"{data['volume']}"
        )

        checks = [
            isinstance(position, BrokerPosition),
            isinstance(data["position_id"], str),
            isinstance(data["symbol_name"], str),
            isinstance(data["side"], str),
            isinstance(data["volume"], float),
        ]

        if not all(checks):
            return False

    return True


def main() -> int:
    """
    Run unified positions diagnostic.
    """

    ib_ok = False
    ctrader_ok = False

    # -----------------------------------------------------------------
    # IB
    # -----------------------------------------------------------------

    ib_adapter = IBAdapter(
        host=os.getenv("IB_HOST", "127.0.0.1"),
        port=int(os.getenv("IB_PORT", "7497")),
        client_id=int(os.getenv("IB_CLIENT_ID", "2")),
        logger=logger,
    )

    if ib_adapter.connect():
        try:
            ib_positions = ib_adapter.get_positions()
            ib_ok = _validate_positions("IB", ib_positions)
        finally:
            ib_adapter.disconnect()
    else:
        print("IB connect failed.")

    # -----------------------------------------------------------------
    # cTrader
    # -----------------------------------------------------------------

    ctrader_adapter = CTraderAdapter.from_env(
        account_mode="DEMO",
        logger=logger,
    )

    if ctrader_adapter.connect():
        try:
            ctrader_positions = ctrader_adapter.get_positions()
            ctrader_ok = _validate_positions(
                "CTRADER",
                ctrader_positions,
            )
        finally:
            ctrader_adapter.disconnect()
    else:
        print("cTrader connect failed.")

    if ib_ok and ctrader_ok:
        print("UNIFIED_POSITIONS_CONTRACT_CHECK=OK")
        return 0

    print("UNIFIED_POSITIONS_CONTRACT_CHECK=FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
