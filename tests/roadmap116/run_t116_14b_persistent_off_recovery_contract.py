"""T116-14B · TEST_ONLY · стійкий OFF після помилки runtime-setter.

Виконує фактичні GUI-методи через AST і підставне in-memory сховище.
Перевіряє захисний запис OFF після успішного первинного збереження,
стан StatusBar / RuntimeEngine та повторну ініціалізацію.

Не відкриває LGE.conf, Qt, БД чи мережеве з'єднання.
Відмову запису захисного OFF перевірятимемо окремо у T116-14C.
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
) -> bool:
    """Звірити пам'ять, умовний диск, GUI, runtime і два види restart."""
    harness = PersistenceHarness(initial)
    harness.start_or_reuse()
    apply_ok = harness.apply_mode(selected, setter_failure=setter_failure)

    memory, disk, gui, runtime, boundary = harness.snapshot()
    reused_mode = harness.reuse_mode()
    cold_mode = harness.cold_restart_mode()

    expect_failure = setter_failure is not None
    expected_mode = "OFF" if expect_failure else selected
    expected_boundary = "INTERCEPTED" if expected_mode == "AUTO" else "BLOCKED"
    expected_writes = [selected, "OFF"] if expect_failure else [selected]
    expected_warnings = 1 if expect_failure else 0

    matching = (
        apply_ok is not expect_failure
        and memory == disk == gui == runtime == expected_mode
        and reused_mode == cold_mode == expected_mode
        and boundary == expected_boundary
        and harness.store.attempts == expected_writes
        and len(harness.warnings) == expected_warnings
        and not harness.store.injected_protective_failure
    )

    print(
        f"case={name} apply={'OK' if apply_ok else 'FAILED'} "
        f"memory={memory} disk={disk} gui={gui} runtime={runtime} "
        f"boundary={boundary} reuse={reused_mode} cold={cold_mode} "
        f"writes={','.join(harness.store.attempts)} "
        f"result={'OK' if matching else 'DRIFT'}"
    )
    return matching


def test_t116_14b_persistent_off_recovery() -> None:
    """Fail-first: помилка setter має залишати стійкий OFF на обох restart."""
    print("T116-14B TEST_ONLY | persistent OFF recovery after setter failure")

    with (
        patch("socket.socket.connect", side_effect=AssertionError("network forbidden")),
        patch("sqlite3.connect", side_effect=AssertionError("database forbidden")),
    ):
        checks = [
            check_case(
                "NORMAL_OFF_TO_AUTO", initial="OFF", selected="AUTO"
            ),
            check_case(
                "NORMAL_AUTO_TO_OFF", initial="AUTO", selected="OFF"
            ),
            check_case(
                "SETTER_BEFORE_OFF_TO_AUTO",
                initial="OFF", selected="AUTO", setter_failure="BEFORE_ASSIGN",
            ),
            check_case(
                "SETTER_AFTER_OFF_TO_AUTO",
                initial="OFF", selected="AUTO", setter_failure="AFTER_ASSIGN",
            ),
            check_case(
                "SETTER_BEFORE_AUTO_TO_MANUAL",
                initial="AUTO", selected="MANUAL", setter_failure="BEFORE_ASSIGN",
            ),
            check_case(
                "SETTER_AFTER_SEMI_TO_AUTO",
                initial="SEMI", selected="AUTO", setter_failure="AFTER_ASSIGN",
            ),
        ]

    mismatches = sum(not result for result in checks)
    print(f"recovery_cases={len(checks)}")
    print(f"recovery_mismatches={mismatches}")
    print("protective_off_write_failure=NOT_INJECTED_T116_14C")
    print("broker_requests=0")
    print("database_writes=0")
    print("real_config_disk_writes=0")
    print("production_changes=0")
    print("actual_qt_widgets=NOT_TESTED")
    print("active_lge_process=NOT_STARTED")

    if mismatches:
        print("T116-14B=RED_PERSISTENT_OFF_RECOVERY_CONTRACT")
        raise AssertionError(
            f"Persistent OFF Recovery порушено у {mismatches} "
            f"з {len(checks)} сценаріїв"
        )
    print("T116-14B=GREEN_PERSISTENT_OFF_RECOVERY_CONTRACT")


if __name__ == "__main__":
    test_t116_14b_persistent_off_recovery()
