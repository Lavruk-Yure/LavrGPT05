"""Controlled RuntimeEngine shutdown and SQLite close regression."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.runtime_engine import RuntimeEngine  # noqa: E402
from engine.runtime_state import RuntimeState  # noqa: E402


class DisconnectProbeService:
    """Minimal service double recording controlled disconnect calls."""

    def __init__(self) -> None:
        self.disconnect_calls = 0

    def disconnect(self) -> None:
        self.disconnect_calls += 1


def main() -> int:
    with TemporaryDirectory(prefix="lge_controlled_shutdown_") as temp_dir:
        db_path = Path(temp_dir) / "runtime.db"
        engine = RuntimeEngine(db_path=str(db_path))
        ctrader_service = DisconnectProbeService()
        ib_service = DisconnectProbeService()
        ctrader_for_test: Any = ctrader_service
        ib_for_test: Any = ib_service
        engine.set_ctrader_runtime_service(ctrader_for_test)
        engine.set_ib_runtime_service(ib_for_test)
        engine.startup()

        engine.shutdown()
        engine.shutdown()

        database_closed = False
        try:
            engine.connection.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            database_closed = True

        shutdown_events = sum(
            1 for event in engine.events if event.event_type.value == "SHUTDOWN"
        )

        print("RuntimeEngine controlled shutdown result")
        print(f"  runtime_state={engine.get_runtime_state().value}")
        print(f"  scheduler_running={engine.is_scheduler_running()}")
        print(f"  ctrader_disconnect_calls={ctrader_service.disconnect_calls}")
        print(f"  ib_disconnect_calls={ib_service.disconnect_calls}")
        print(f"  shutdown_events={shutdown_events}")
        print(f"  database_closed={database_closed}")
        print("  duplicate_shutdown_safe=True")

        checks = [
            engine.get_runtime_state() == RuntimeState.OFF,
            not engine.is_scheduler_running(),
            ctrader_service.disconnect_calls == 1,
            ib_service.disconnect_calls == 1,
            shutdown_events == 1,
            database_closed,
        ]

        if all(checks):
            print("RUNTIME_ENGINE_CONTROLLED_SHUTDOWN_CHECK=OK")
            return 0

        print("RUNTIME_ENGINE_CONTROLLED_SHUTDOWN_CHECK=FAILED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
