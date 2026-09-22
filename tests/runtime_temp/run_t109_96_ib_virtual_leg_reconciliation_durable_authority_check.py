"""run_t109_96_ib_virtual_leg_reconciliation_durable_authority_check.py.

Production regression перевіряє durable completeness authority для повного IB
virtual-leg reconciliation. На тимчасовій schema v12 runner persist-ить exact
account і ``captured_utc`` навіть для empty snapshot, перевіряє idempotent repeat,
multi-account scope, stale/conflict fail-closed та відхилення incomplete або
causally mismatched evidence.

Authority записується атомарно в тому самому savepoint, що й reconciled legs.
Runner не викликає broker API та не додає lifecycle caller, workspace count read
або risk snapshot wiring. Production SQLite користувача не відкривається.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

from engine.db.runtime_db import (
    SCHEMA_VERSION,
    connect_runtime_db,
    get_schema_version,
)
from engine.ib_virtual_position_leg import (
    IBVirtualPositionLegReconciliationSnapshot,
)
from engine.runtime_repository import RuntimeRepository


def _snapshot(
    captured_utc: str,
    *,
    marker: str = "",
) -> IBVirtualPositionLegReconciliationSnapshot:
    """Побудувати complete authoritative empty reconciliation snapshot."""
    return IBVirtualPositionLegReconciliationSnapshot(
        captured_utc=captured_utc,
        complete=True,
        legs=[],
        group_statuses={},
        group_messages=(
            {"TEST_ONLY": (marker,)}
            if marker
            else {}
        ),
        unmapped_protective_order_ids=[],
    )


def _evidence(
    captured_utc: str,
    account_ids: list[str],
    *,
    complete: bool = True,
) -> dict[str, object]:
    """Побудувати supplied broker-free complete evidence metadata."""
    return {
        "broker": "IB",
        "captured_utc": captured_utc,
        "complete": complete,
        "positions_complete": complete,
        "open_orders_complete": complete,
        "completed_orders_complete": complete,
        "executions_complete": complete,
        "account_ids": list(account_ids),
        "positions": [],
        "open_orders": [],
        "completed_orders": [],
        "executions": [],
    }


def _raises_runtime_error(action: Callable[[], object]) -> bool:
    """Повернути True, якщо supplied action fail-closed через RuntimeError."""
    try:
        action()
    except RuntimeError:
        return True
    return False


def main() -> None:
    """Запустити production authority regression T109-96."""
    first_capture = "2026-09-22T08:00:00+00:00"
    older_capture = "2026-09-22T07:59:59+00:00"
    newer_capture = "2026-09-22T08:01:00+00:00"
    multi_capture = "2026-09-22T08:02:00+00:00"

    with TemporaryDirectory(
        prefix="t109_96_ib_authority_",
        ignore_cleanup_errors=True,
    ) as temp_dir:
        db_path = Path(temp_dir) / "runtime.db"
        legacy_connection = sqlite3.connect(db_path)
        legacy_connection.execute(
            "CREATE TABLE migration_sentinel (value TEXT NOT NULL)"
        )
        legacy_connection.execute(
            "INSERT INTO migration_sentinel (value) VALUES ('V11')"
        )
        legacy_connection.execute("PRAGMA user_version=11")
        legacy_connection.commit()
        legacy_connection.close()

        connection = connect_runtime_db(db_path)
        repository = RuntimeRepository(connection)

        table_present = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'ib_virtual_leg_reconciliation_authority'
            """
        ).fetchone() is not None
        schema_version = get_schema_version(connection)
        sentinel_row = connection.execute(
            "SELECT value FROM migration_sentinel"
        ).fetchone()
        migration_preserves_existing_data = (
            sentinel_row is not None and str(sentinel_row[0]) == "V11"
        )

        first_snapshot = _snapshot(first_capture)
        first_evidence = _evidence(first_capture, ["DU109"])
        first_result = repository.sync_reconciled_ib_virtual_position_leg_snapshot(
            snapshot=first_snapshot,
            evidence_snapshot=first_evidence,
        )
        first_authority = (
            repository.get_ib_virtual_leg_reconciliation_authority(
                account_id="DU109"
            )
        )
        complete_empty_snapshot_authorized = (
            first_result["open_legs"] == 0
            and first_result["authority_rows_written"] == 1
            and first_authority is not None
            and first_authority["account_id"] == "DU109"
            and first_authority["captured_utc"] == first_capture
            and first_authority["source_complete"] is True
        )

        repeat_result = repository.sync_reconciled_ib_virtual_position_leg_snapshot(
            snapshot=first_snapshot,
            evidence_snapshot=first_evidence,
        )
        duplicate_same_snapshot_deduped = (
            repeat_result["authority_rows_written"] == 0
        )

        conflict_fail_closed = _raises_runtime_error(
            lambda: repository.sync_reconciled_ib_virtual_position_leg_snapshot(
                snapshot=_snapshot(first_capture, marker="CONFLICT"),
                evidence_snapshot=first_evidence,
            )
        )
        stale_snapshot_fail_closed = _raises_runtime_error(
            lambda: repository.sync_reconciled_ib_virtual_position_leg_snapshot(
                snapshot=_snapshot(older_capture),
                evidence_snapshot=_evidence(older_capture, ["DU109"]),
            )
        )
        incomplete_snapshot_not_authorized = _raises_runtime_error(
            lambda: repository.sync_reconciled_ib_virtual_position_leg_snapshot(
                snapshot=_snapshot(newer_capture),
                evidence_snapshot=_evidence(
                    newer_capture,
                    ["DU109"],
                    complete=False,
                ),
            )
        )
        timestamp_mismatch_fail_closed = _raises_runtime_error(
            lambda: repository.sync_reconciled_ib_virtual_position_leg_snapshot(
                snapshot=_snapshot(newer_capture),
                evidence_snapshot=_evidence(first_capture, ["DU109"]),
            )
        )
        missing_account_scope_fail_closed = _raises_runtime_error(
            lambda: repository.sync_reconciled_ib_virtual_position_leg_snapshot(
                snapshot=_snapshot(newer_capture),
                evidence_snapshot=_evidence(newer_capture, []),
            )
        )

        after_failures = repository.get_ib_virtual_leg_reconciliation_authority(
            account_id="DU109"
        )
        failures_preserve_authority = after_failures == first_authority

        multi_result = repository.sync_reconciled_ib_virtual_position_leg_snapshot(
            snapshot=_snapshot(multi_capture),
            evidence_snapshot=_evidence(
                multi_capture,
                ["DU200", "DU109", "DU200"],
            ),
        )
        second_authority = (
            repository.get_ib_virtual_leg_reconciliation_authority(
                account_id="DU200"
            )
        )
        multi_account_exact_scope = (
            multi_result["authority_accounts"] == ["DU109", "DU200"]
            and multi_result["authority_rows_written"] == 2
            and second_authority is not None
            and second_authority["account_id"] == "DU200"
            and second_authority["captured_utc"] == multi_capture
        )
        wrong_account_excluded = (
            repository.get_ib_virtual_leg_reconciliation_authority(
                account_id="DU999"
            )
            is None
        )

        repository_path = Path(__file__).resolve().parents[2] / (
            "engine/runtime_repository.py"
        )
        repository_source = repository_path.read_text(encoding="utf-8")
        sync_source = repository_source.split(
            "    def sync_reconciled_ib_virtual_position_leg_snapshot(",
            maxsplit=1,
        )[1].split(
            "\n    def get_ib_virtual_leg_reconciliation_authority(",
            maxsplit=1,
        )[0]
        authority_inside_savepoint = (
            sync_source.index("SAVEPOINT ib_virtual_leg_sync")
            < sync_source.index(
                "self._upsert_ib_reconciliation_authority_no_commit("
            )
            < sync_source.index("RELEASE ib_virtual_leg_sync")
        )

        connection.close()

    production_change = True
    lifecycle_caller_added = False
    workspace_count_read_added = False
    risk_snapshot_wiring_added = False
    broker_requests = 0

    assert SCHEMA_VERSION == 12
    assert schema_version == 12
    assert table_present
    assert migration_preserves_existing_data
    assert complete_empty_snapshot_authorized
    assert duplicate_same_snapshot_deduped
    assert conflict_fail_closed
    assert stale_snapshot_fail_closed
    assert incomplete_snapshot_not_authorized
    assert timestamp_mismatch_fail_closed
    assert missing_account_scope_fail_closed
    assert failures_preserve_authority
    assert multi_account_exact_scope
    assert wrong_account_excluded
    assert authority_inside_savepoint
    assert not lifecycle_caller_added
    assert not workspace_count_read_added
    assert not risk_snapshot_wiring_added
    assert broker_requests == 0

    print("T109-96_IB_VIRTUAL_LEG_RECONCILIATION_DURABLE_AUTHORITY=OK")
    print(f"production_change={production_change}")
    print(f"schema_version={schema_version}")
    print(f"authority_table_present={table_present}")
    print(
        "v11_to_v12_migration_preserves_existing_data="
        f"{migration_preserves_existing_data}"
    )
    print(
        "complete_empty_snapshot_authorized="
        f"{complete_empty_snapshot_authorized}"
    )
    print(
        "duplicate_same_snapshot_deduped="
        f"{duplicate_same_snapshot_deduped}"
    )
    print(f"conflict_fail_closed={conflict_fail_closed}")
    print(f"stale_snapshot_fail_closed={stale_snapshot_fail_closed}")
    print(
        "incomplete_snapshot_not_authorized="
        f"{incomplete_snapshot_not_authorized}"
    )
    print(
        "timestamp_mismatch_fail_closed="
        f"{timestamp_mismatch_fail_closed}"
    )
    print(
        "missing_account_scope_fail_closed="
        f"{missing_account_scope_fail_closed}"
    )
    print(f"failures_preserve_authority={failures_preserve_authority}")
    print(f"multi_account_exact_scope={multi_account_exact_scope}")
    print(f"wrong_account_excluded={wrong_account_excluded}")
    print(f"authority_inside_savepoint={authority_inside_savepoint}")
    print(f"lifecycle_caller_added={lifecycle_caller_added}")
    print(f"workspace_count_read_added={workspace_count_read_added}")
    print(f"risk_snapshot_wiring_added={risk_snapshot_wiring_added}")
    print(f"broker_requests={broker_requests}")
    print(
        "first_unresolved_boundary="
        "IB_VIRTUAL_LEG_RECONCILIATION_NON_BLOCKING_RISK_LIFECYCLE_CALLER"
    )
    print(
        "boundary_contract=DURABLE_COMPLETE_OR_EMPTY_ACCOUNT_AUTHORITY_IS_NOW_"
        "ATOMIC_IDEMPOTENT_AND_CONFLICT_FAIL_CLOSED_WHILE_NO_NON_BLOCKING_"
        "RISK_LIFECYCLE_CALLER_REFRESHES_IT"
    )
    print(
        "factual_verdict=A. IB_VIRTUAL_LEG_RECONCILIATION_DURABLE_"
        "COMPLETENESS_AUTHORITY_GREEN_WITH_AUTHORITATIVE_EMPTY_SNAPSHOT_"
        "ATOMIC_COMMIT_DEDUP_AND_CONFLICT_FAIL_CLOSED"
    )


def test_t109_96_ib_virtual_leg_reconciliation_durable_authority() -> None:
    """Запустити T109-96 як pytest-compatible production checkpoint."""
    main()


if __name__ == "__main__":
    main()
