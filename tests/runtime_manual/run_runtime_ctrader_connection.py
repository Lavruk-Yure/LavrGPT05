# run_runtime_ctrader_connection.py
r"""
RoadMap67 diagnostic test:
RuntimeEngine -> BrokerInterface -> CTraderAdapter -> cTrader Open API.

ENV:
- CTRADER_CLIENT_ID
- CTRADER_CLIENT_SECRET
- CTRADER_ACCOUNT_ID

Tokens:
- tokens/tokens.json

Run:
    D:\LavrGPT\venv313\Scripts\python.exe ^
    D:\LavrGPT\LavrGPT05\tests\runtime_manual\run_runtime_ctrader_connection.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ctrader_adapter import CTraderAdapter  # noqa: E402
from engine.runtime_engine import RuntimeEngine  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    """
    Запустити runtime cTrader connection diagnostic.
    """

    engine = RuntimeEngine(db_path=str(PROJECT_ROOT / "data" / "demo.db"))
    engine.startup()
    engine.set_broker("CTRADER")

    try:
        adapter = CTraderAdapter.from_env(account_mode="DEMO", logger=logger)
        engine.set_broker_adapter(adapter)
        connected = engine.connect_broker()
    except RuntimeError as exc:
        logger.error("Runtime cTrader connection failed: %s", exc)
        engine.shutdown()
        return 1
    print(f"connected={connected}")
    print(f"broker_state={engine.context.broker_connection_state.value}")

    account_info = engine.get_broker_account_info()
    if account_info is not None:
        print(account_info.to_dict())

    engine.disconnect_broker()
    engine.shutdown()
    return 0 if connected else 1


if __name__ == "__main__":
    raise SystemExit(main())
