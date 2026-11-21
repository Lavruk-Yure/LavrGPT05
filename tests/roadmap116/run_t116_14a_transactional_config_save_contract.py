"""T116-14A · TEST_ONLY · транзакційне оновлення конфігурації в пам'яті.

Виконує production _save_to_conf через AST із підставним in-memory сховищем.
Не читає і не записує LGE.conf, БД та не використовує брокерський API.
"""

from __future__ import annotations

from copy import deepcopy
import sys
from pathlib import Path
from unittest.mock import patch

TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from run_t116_14_persistent_fail_closed_contract import (  # noqa: E402
    PersistenceHarness,
)


def check_transaction(
    name: str,
    *,
    initial: str,
    selected: str,
    fail_save: bool,
    mutate_stage: bool = False,
) -> bool:
    """Зіставити стан до і після збереження, включно з іншими полями."""
    harness = PersistenceHarness(initial)
    harness.config.data["other_section"] = {"untouched": [1, 2, 3]}
    harness.store.snapshot = deepcopy(harness.config.data)
    initial_data = deepcopy(harness.config.data)
    engine_reference = harness.config.data["engine"]

    if mutate_stage:
        original_save = harness.store.save

        def partial_save(staged_data: dict) -> None:
            """Імітувати зміну переданого словника перед відмовою запису."""
            staged_data["updated_at"] = "TEST_ONLY_STAGE_TIMESTAMP"
            staged_data["engine"]["unexpected"] = "TEST_ONLY_STAGE_FIELD"
            original_save(staged_data)

        harness.store.save = partial_save

    harness.start_or_reuse()
    outcome = harness.apply_mode(selected, fail_primary_save=fail_save)
    memory = harness.config.data
    disk = harness.store.snapshot
    runtime_mode = harness.engine.context.execution_mode
    expect_mode = initial if fail_save else selected

    matching = (
        outcome is not fail_save
        and memory == disk
        and memory["engine"]["execution_mode"] == expect_mode
        and runtime_mode == expect_mode
        and memory["other_section"] == initial_data["other_section"]
        and memory["engine"] is engine_reference
    )
    if fail_save:
        matching = matching and memory == initial_data

    print(
        f"case={name} save={'FAILED' if fail_save else 'OK'} "
        f"memory={memory['engine']['execution_mode']} "
        f"disk={disk['engine']['execution_mode']} runtime={runtime_mode} "
        f"result={'OK' if matching else 'DRIFT'}"
    )
    return matching


def test_t116_14a_transactional_config_save() -> None:
    """Помилка збереження не повинна змінювати конфіг у пам'яті."""
    print("T116-14A TEST_ONLY | transactional in-memory config save")
    with (
        patch("socket.socket.connect", side_effect=AssertionError("network forbidden")),
        patch("sqlite3.connect", side_effect=AssertionError("database forbidden")),
    ):
        checks = [
            check_transaction(
                "OFF_TO_AUTO_SUCCESS", initial="OFF",
                selected="AUTO", fail_save=False,
            ),
            check_transaction(
                "AUTO_TO_OFF_SUCCESS", initial="AUTO",
                selected="OFF", fail_save=False,
            ),
            check_transaction(
                "METADATA_COMMITTED_ON_SUCCESS", initial="OFF",
                selected="AUTO", fail_save=False, mutate_stage=True,
            ),
            check_transaction(
                "OFF_TO_AUTO_SAVE_FAILURE", initial="OFF",
                selected="AUTO", fail_save=True,
            ),
            check_transaction(
                "AUTO_TO_OFF_SAVE_FAILURE", initial="AUTO",
                selected="OFF", fail_save=True,
            ),
            check_transaction(
                "STAGED_DATA_MUTATED_THEN_FAILURE", initial="OFF",
                selected="AUTO", fail_save=True, mutate_stage=True,
            ),
        ]

    mismatches = sum(not result for result in checks)
    print(f"transaction_cases={len(checks)}")
    print(f"transaction_mismatches={mismatches}")
    print("broker_requests=0")
    print("database_writes=0")
    print("real_config_disk_writes=0")
    print("production_changes=0")
    if mismatches:
        print("T116-14A=RED_TRANSACTIONAL_MEMORY_SAVE")
        raise AssertionError(f"Збоїв збереження: {mismatches} із {len(checks)}")
    print("T116-14A=GREEN_TRANSACTIONAL_MEMORY_SAVE")


if __name__ == "__main__":
    test_t116_14a_transactional_config_save()
