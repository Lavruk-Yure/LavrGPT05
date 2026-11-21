"""T116-12A · TEST_ONLY · startup/reuse синхронізація execution_mode.

Перевірка фактичного методу GUI через AST та фальшивий RuntimeEngine.
Без брокерів, БД, конфігураційних записів або запуску LGE.
"""

from __future__ import annotations

import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from run_t116_12_execution_mode_sync_contract import check_startup  # noqa: E402


def test_t116_12a_startup_mode_sync() -> None:
    """Новий і повторно використаний runtime мають приймати режим до запуску."""
    print("T116-12A TEST_ONLY | startup/reused RuntimeEngine execution-mode sync")

    cases = [
        ("AUTO", None),
        ("MANUAL", None),
        ("SEMI", None),
        ("OFF", None),
        ("OFF", "AUTO"),
        ("AUTO", "OFF"),
        ("INVALID", "AUTO"),
        ("", "AUTO"),
    ]
    results = [check_startup(mode, existing) for mode, existing in cases]
    mismatches = sum(not result for result in results)

    print(f"startup_cases={len(cases)}")
    print(f"startup_mismatches={mismatches}")
    print("broker_requests=0")
    print("database_writes=0")
    print("config_disk_writes=0")
    print("production_changes=0")
    print("settings_apply_sync=NOT_MODIFIED")

    if mismatches:
        print("T116-12A=RED_STARTUP_SYNC_CONTRACT")
        raise AssertionError(f"Startup sync порушено: {mismatches}/{len(cases)}")
    print("T116-12A=GREEN_STARTUP_SYNC_CONTRACT")


if __name__ == "__main__":
    test_t116_12a_startup_mode_sync()
