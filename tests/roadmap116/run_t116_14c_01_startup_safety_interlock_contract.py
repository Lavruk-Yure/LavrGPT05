"""T116-14C-01 · TEST_ONLY · fail-first контракт безпечного запуску.

Виконує справжні тіла GUI/RuntimeEngine-методів, ізольовані через AST.
Лише фіктивні конфігурація, RuntimeEngine, репозиторій і брокер.
Жодних реальних мережевих, файлових чи DB-запитів.

Контракт: збережене AUTO не є новим дозволом на AUTO після restart.
Свідоме застосування AUTO у поточній сесії залишається допустимим.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from run_t116_14_persistent_fail_closed_contract import (  # noqa: E402
    PersistenceHarness,
)


def verify(
    case: str,
    harness: PersistenceHarness,
    expected_mode: str,
    expected_boundary: str,
) -> bool:
    """Зіставити фактичний режим, StatusBar і допуск до fake adapter."""
    memory, persisted, gui, runtime, boundary = harness.snapshot()
    matching = (
        runtime == expected_mode
        and gui == expected_mode
        and boundary == expected_boundary
    )
    print(
        f"case={case} memory={memory} persisted={persisted} "
        f"gui={gui} runtime={runtime} boundary={boundary} "
        f"expected={expected_mode}/{expected_boundary} "
        f"result={'OK' if matching else 'DRIFT'}"
    )
    return matching


def check_cases() -> list[bool]:
    """Не плутати активне свідоме ввімкнення AUTO з холодним запуском."""
    checks: list[bool] = []

    for mode, expected in (
        ("OFF", "OFF"),
        ("MANUAL", "MANUAL"),
        ("SEMI", "SEMI"),
        ("INVALID", "OFF"),
        ("AUTO", "OFF"),
    ):
        harness = PersistenceHarness(mode)
        harness.start_or_reuse()
        checks.append(
            verify(f"COLD_CONFIG_{mode}", harness, expected, "BLOCKED")
        )

    authorized = PersistenceHarness("OFF")
    authorized.start_or_reuse()
    assert authorized.apply_mode("AUTO") is True
    checks.append(
        verify("EXPLICIT_AUTO_SAME_SESSION", authorized, "AUTO", "INTERCEPTED")
    )
    authorized.start_or_reuse()
    checks.append(
        verify("REUSE_ALREADY_AUTHORIZED_AUTO", authorized, "AUTO", "INTERCEPTED")
    )

    cold_after_authorization = PersistenceHarness(authorized.store.mode)
    cold_after_authorization.start_or_reuse()
    checks.append(
        verify("COLD_AFTER_PREVIOUS_AUTO", cold_after_authorization, "OFF", "BLOCKED")
    )

    failed = PersistenceHarness("OFF")
    failed.start_or_reuse()
    assert failed.apply_mode(
        "AUTO", setter_failure="AFTER_ASSIGN", fail_protective_off=True
    ) is False
    assert failed.store.injected_protective_failure
    failed.start_or_reuse()
    checks.append(
        verify("REUSE_AFTER_OFF_WRITE_FAILURE", failed, "OFF", "BLOCKED")
    )

    cold_after_failure = PersistenceHarness(failed.store.mode)
    cold_after_failure.start_or_reuse()
    checks.append(
        verify("COLD_AFTER_OFF_WRITE_FAILURE", cold_after_failure, "OFF", "BLOCKED")
    )
    return checks


def test_t116_14c_01_startup_safety_interlock() -> None:
    """Fail-first: до production-правки збережене AUTO активується знову."""
    print("T116-14C-01 TEST_ONLY | startup AUTO requires fresh session consent")
    with (
        patch("socket.socket.connect", side_effect=AssertionError("network forbidden")),
        patch("sqlite3.connect", side_effect=AssertionError("database forbidden")),
    ):
        checks = check_cases()

    mismatches = sum(not passed for passed in checks)
    print(f"startup_cases={len(checks)}")
    print(f"startup_mismatches={mismatches}")
    print("explicit_session_auto=TESTED")
    print("persistent_auto_requires_rearm=YES_CONTRACT")
    print("real_broker_requests=0")
    print("real_database_writes=0")
    print("real_config_disk_writes=0")
    print("production_changes=0")
    print("actual_qt_widgets=NOT_TESTED")
    print("active_lge_process=NOT_STARTED")

    if mismatches:
        print("T116-14C-01=RED_STARTUP_INTERLOCK_ABSENT")
        raise AssertionError(
            f"Startup Safety Interlock порушено в {mismatches} "
            f"із {len(checks)} сценаріїв"
        )
    print("T116-14C-01=GREEN_STARTUP_INTERLOCK_CONTRACT")


if __name__ == "__main__":
    test_t116_14c_01_startup_safety_interlock()
