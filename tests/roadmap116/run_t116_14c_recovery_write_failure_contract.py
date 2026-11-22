"""T116-14C · TEST_ONLY · відмова запису захисного OFF.

Контракт для фактичних GUI/runtime методів, виконаних через AST
із підставним сховищем. Не відкриває LGE.conf, не записує на диск,
не запускає LGE/Qt/RuntimeEngine та не звертається до брокерів.

Fail-first RED означає: після помилки запису OFF наступний запуск
може повторно активувати режим, який не вдалося застосувати.
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


def check_case(
    name: str,
    *,
    initial: str,
    selected: str,
    setter_failure: str | None = None,
    fail_protective_off: bool = False,
    fail_primary_save: bool = False,
) -> bool:
    """Перевірити узгодженість до і після двох типів перезапуску."""
    harness = PersistenceHarness(initial)
    harness.start_or_reuse()
    result = harness.apply_mode(
        selected,
        setter_failure=setter_failure,
        fail_primary_save=fail_primary_save,
        fail_protective_off=fail_protective_off,
    )
    memory, persisted, gui, runtime, boundary = harness.snapshot()
    reused = harness.reuse_mode()
    cold = harness.cold_restart_mode()

    failure_expected = setter_failure is not None or fail_primary_save
    expected_mode = (
        "OFF" if setter_failure is not None
        else initial if fail_primary_save
        else selected
    )
    expected_persisted = selected if fail_protective_off else (
        initial if fail_primary_save else expected_mode
    )
    expected_runtime = (
        "OFF" if fail_primary_save and initial == "AUTO" else expected_mode
    )
    expected_cold = (
        "OFF" if expected_persisted == "AUTO" else expected_persisted
    )
    expected_boundary = (
        "INTERCEPTED" if expected_runtime == "AUTO" else "BLOCKED"
    )
    expected_writes = (
        [selected, "OFF"] if setter_failure is not None
        else [selected]
    )
    injection_ok = (
        harness.store.injected_protective_failure == fail_protective_off
    )
    consistent = (
        result is not failure_expected
        and memory == persisted == expected_persisted
        and gui == runtime == expected_runtime
        and reused == expected_runtime
        and cold == expected_cold
        and boundary == expected_boundary
        and harness.store.attempts == expected_writes
        and injection_ok
    )

    injection_text = (
        "YES" if harness.store.injected_protective_failure else "NO"
    )
    print(
        f"case={name} apply={'OK' if result else 'FAILED'} "
        f"memory={memory} persisted={persisted} gui={gui} "
        f"runtime={runtime} boundary={boundary} "
        f"reuse={reused} cold={cold} "
        f"off_write_failure_injected={injection_text} "
        f"writes={','.join(harness.store.attempts)} "
        f"result={'OK' if consistent else 'DRIFT'}"
    )
    return consistent


def test_t116_14c_recovery_write_failure() -> None:
    """Fail-first: відмова захисного запису не повинна відновити AUTO."""
    print("T116-14C TEST_ONLY | protective OFF persistence write failure")
    with (
        patch("socket.socket.connect", side_effect=AssertionError("network forbidden")),
        patch("sqlite3.connect", side_effect=AssertionError("database forbidden")),
    ):
        checks = [
            check_case(
                "NORMAL_OFF_TO_AUTO",
                initial="OFF", selected="AUTO",
            ),
            check_case(
                "SETTER_FAIL_OFF_SAVED",
                initial="OFF", selected="AUTO",
                setter_failure="AFTER_ASSIGN",
            ),
            check_case(
                "PROTECTIVE_WRITE_FAIL_BEFORE_ASSIGN",
                initial="OFF", selected="AUTO",
                setter_failure="BEFORE_ASSIGN", fail_protective_off=True,
            ),
            check_case(
                "PROTECTIVE_WRITE_FAIL_AFTER_ASSIGN",
                initial="OFF", selected="AUTO",
                setter_failure="AFTER_ASSIGN", fail_protective_off=True,
            ),
            check_case(
                "PROTECTIVE_WRITE_FAIL_SEMI_TO_AUTO",
                initial="SEMI", selected="AUTO",
                setter_failure="AFTER_ASSIGN", fail_protective_off=True,
            ),
            check_case(
                "PRIMARY_WRITE_FAILURE",
                initial="OFF", selected="AUTO", fail_primary_save=True,
            ),
        ]

    mismatches = sum(not passed for passed in checks)
    print(f"recovery_cases={len(checks)}")
    print(f"recovery_mismatches={mismatches}")
    print("real_broker_requests=0")
    print("real_database_writes=0")
    print("real_config_disk_writes=0")
    print("production_changes=0")
    print("actual_qt_widgets=NOT_TESTED")
    print("active_lge_process=NOT_STARTED")

    if mismatches:
        print("T116-14C=RED_PROTECTIVE_OFF_WRITE_FAILURE")
        raise AssertionError(
            f"Відмова захисного запису: порушення в {mismatches} "
            f"із {len(checks)} сценаріїв"
        )
    print("T116-14C=GREEN_PROTECTIVE_OFF_WRITE_FAILURE")


if __name__ == "__main__":
    test_t116_14c_recovery_write_failure()
