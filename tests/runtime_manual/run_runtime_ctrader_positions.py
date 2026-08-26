# run_runtime_ctrader_positions.py
"""
cTrader runtime positions diagnostic.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from pprint import pprint

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ctrader_adapter import CTraderAdapter  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)


def main() -> int:
    """
    Run diagnostic.
    """

    adapter = CTraderAdapter.from_env(
        account_mode="DEMO",
        logger=logger,
    )

    connected = adapter.connect()

    print(f"connected={connected}")
    print(f"broker_state={adapter.state.connection_state}")

    if not connected:
        return 1

    positions = adapter.get_positions()

    print(f"positions_count={len(positions)}")

    for position in positions:
        pprint(position.to_dict())

    adapter.disconnect()

    print("CTRADER_POSITIONS_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
