# run_runtime_engine_scheduler_check.py
"""
Діагностика інтеграції RuntimeScheduler у RuntimeEngine.

RoadMap73.4:
- RuntimeEngine створює RuntimeScheduler;
- startup() запускає scheduler;
- shutdown() зупиняє scheduler.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.runtime_engine import RuntimeEngine  # noqa: E402
from engine.runtime_state import RuntimeState  # noqa: E402


def main() -> int:
    """
    Запустити перевірку RuntimeEngine + RuntimeScheduler.
    """
    engine = RuntimeEngine()

    engine.startup()

    scheduler_running_after_startup = engine.is_scheduler_running()
    runtime_state_after_startup = engine.get_runtime_state()

    engine.shutdown()

    scheduler_running_after_shutdown = engine.is_scheduler_running()
    runtime_state_after_shutdown = engine.get_runtime_state()

    print(f"runtime_state_after_startup={runtime_state_after_startup}")
    print(f"scheduler_running_after_startup={scheduler_running_after_startup}")
    print(f"runtime_state_after_shutdown={runtime_state_after_shutdown}")
    print(f"scheduler_running_after_shutdown={scheduler_running_after_shutdown}")

    checks = [
        runtime_state_after_startup == RuntimeState.RUNNING,
        scheduler_running_after_startup is True,
        runtime_state_after_shutdown == RuntimeState.OFF,
        scheduler_running_after_shutdown is False,
    ]

    if all(checks):
        print("\nRUNTIME_ENGINE_SCHEDULER_CHECK=OK")
        return 0

    print("\nRUNTIME_ENGINE_SCHEDULER_CHECK=FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
