# run_runtime_ib_positions.py
"""
IB runtime positions diagnostic.

RoadMap68:
- перевіряє реальний IBAdapter.get_positions();
- потребує запущений TWS/IB Gateway;
- не створює ордерів;
- тільки читає відкриті positions.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from pprint import pprint

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_adapter import IBAdapter  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)


def main() -> int:
    """
    Run IB positions diagnostic.
    """

    host = os.getenv("IB_HOST", "127.0.0.1")
    port = int(os.getenv("IB_PORT", "7497"))
    client_id = int(os.getenv("IB_CLIENT_ID", "2"))

    adapter = IBAdapter(
        host=host,
        port=port,
        client_id=client_id,
        logger=logger,
    )

    connected = adapter.connect()
    print(f"connected={connected}")
    print(f"broker_state={adapter.broker_state}")

    if not connected:
        return 1

    positions = adapter.get_positions()

    print(f"positions_count={len(positions)}")
    for position in positions:
        pprint(position.to_dict())

    adapter.disconnect()

    print("IB_POSITIONS_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
