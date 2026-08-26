# run_runtime_engine_lifecycle.py
"""
Ручний тест lifecycle runtime engine ATS.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pprint import pprint

from engine.db.runtime_db import get_runtime_database_path
from engine.runtime_engine import RuntimeEngine
from engine.services.ctrader_runtime_service import CTraderRuntimeService


def main() -> None:
    """
    Точка входу manual runtime lifecycle test.
    """

    engine = RuntimeEngine(db_path=str(get_runtime_database_path("DEMO")))

    print("\n=== INITIAL CONTEXT ===")
    pprint(engine.context.to_dict())

    print("\n=== STARTUP ===")
    engine.startup()

    service = CTraderRuntimeService()
    engine.set_ctrader_runtime_service(service)

    pprint(engine.context.to_dict())

    print("\n=== EVENTS AFTER STARTUP ===")

    for event in engine.events:
        pprint(event.to_dict())

    print("\n=== SHUTDOWN ===")
    engine.shutdown()

    pprint(engine.context.to_dict())

    print("\n=== EVENTS AFTER SHUTDOWN ===")

    for event in engine.events:
        pprint(event.to_dict())

    print("\n=== TEST FINISHED ===")


if __name__ == "__main__":
    main()
