# run_runtime_ib_connection.py
"""IB runtime connection diagnostic."""

from __future__ import annotations

import logging
import os

from engine.ib_adapter import IBAdapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)


def main() -> int:
    """Run runtime IB connection diagnostic."""

    host = os.getenv("IB_HOST", "127.0.0.1")
    port = int(os.getenv("IB_PORT", "7497"))
    client_id = int(os.getenv("IB_CLIENT_ID", "1"))

    adapter = IBAdapter(
        host=host,
        port=port,
        client_id=client_id,
        logger=logger,
    )

    connected = adapter.connect()

    print(f"connected={connected}")
    print(f"broker_state={adapter.broker_state}")
    print(adapter.get_account_info())

    adapter.disconnect()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
