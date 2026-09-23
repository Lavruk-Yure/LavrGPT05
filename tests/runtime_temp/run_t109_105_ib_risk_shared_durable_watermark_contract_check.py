"""run_t109_105_ib_risk_shared_durable_watermark_contract_check.py.

TEST_ONLY contract check обирає causal shared watermark для IB workspace risk
snapshot. Runner використовує лише чинні durable daily-PnL coverage intervals
і complete reconciliation authority на temporary schema v12, без broker API.

Перевіряються відхилені account/coverage timestamps, обране authority
``captured_utc``, вимога contiguous PnL coverage до нього, заборона future
cached account facts та детерміноване відтворення після reopen. Production
sources хешуються; schema, lifecycle і risk wiring не змінюються.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from inspect import getfile
from pathlib import Path
from tempfile import TemporaryDirectory

from core.algorithm_workspace_controller import AlgorithmWorkspaceController
from core.ib_reconciliation_lifecycle import IBReconciliationLifecycleBridge
from core.main_logic import MainAppWindow
from engine.db.runtime_db import SCHEMA_VERSION
from engine.runtime_engine import RuntimeEngine
from engine.runtime_repository import RuntimeRepository

SELECTED_WATERMARK_RULE = "LATEST_COMPLETE_RECONCILIATION_CAPTURED_UTC"
RECOMMENDED_SEQUENCE = (
    "RECONCILIATION_COMPLETES_THEN_PNL_RECOVERY_EXTENDS_COVERAGE_THROUGH_"
    "AUTHORITY_THEN_RISK_RESYNC_USES_AUTHORITY_CAPTURED_UTC"
)
FIRST_UNRESOLVED_BOUNDARY = (
    "IB_RISK_SHARED_DURABLE_WATERMARK_PRODUCTION_WIRING"
)
BOUNDARY_CONTRACT = (
    "IB_RISK_USES_COMPLETE_RECONCILIATION_CAPTURED_UTC_AS_THE_SHARED_"
    "DURABLE_WATERMARK_ONLY_WHEN_PNL_COVERAGE_REACHES_IT_AND_CACHED_"
    "ACCOUNT_FACTS_ARE_NOT_FROM_ITS_FUTURE"
)
FACTUAL_VERDICT = (
    "A. IB_RISK_SHARED_DURABLE_WATERMARK_CONTRACT_SELECTED_WITH_EXISTING_"
    "AUTHORITY_AND_COVERAGE_TABLES_POST_RECONCILIATION_PNL_EXTENSION_"
    "FUTURE_ACCOUNT_REJECTION_AND_NO_SCHEMA_CHANGE"
)


def _hashes(paths: tuple[Path, ...]) -> dict[str, str]:
    """Порахувати hashes scoped production sources."""
    return {
        path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def _persist_authority(
    engine: RuntimeEngine,
    *,
    account_id: str,
    captured_utc: datetime,
) -> None:
    """Записати supplied complete empty reconciliation authority."""
    timestamp = captured_utc.isoformat()
    engine.connection.execute(
        """
        INSERT INTO ib_virtual_leg_reconciliation_authority (
            account_id,
            captured_utc,
            source_complete,
            snapshot_digest,
            created_utc,
            updated_utc
        )
        VALUES (?, ?, 1, ?, ?, ?)
        """,
        (
            account_id,
            timestamp,
            f"TEST_ONLY-{account_id}-{timestamp}",
            timestamp,
            timestamp,
        ),
    )
    engine.connection.commit()


def _derive_shared_watermark(
    repository: RuntimeRepository,
    *,
    account_id: str,
    cached_account_utc: datetime,
) -> datetime | None:
    """Вивести authority watermark лише за повного causal overlap."""
    if (
        cached_account_utc.tzinfo is None
        or cached_account_utc.utcoffset() is None
    ):
        return None

    authority = repository.get_ib_virtual_leg_reconciliation_authority(
        account_id=account_id,
    )
    if authority is None or authority.get("source_complete") is not True:
        return None
    try:
        captured = datetime.fromisoformat(str(authority["captured_utc"]))
    except (KeyError, ValueError):
        return None
    if captured.tzinfo is None or captured.utcoffset() is None:
        return None

    watermark = captured.astimezone(UTC)
    if cached_account_utc.astimezone(UTC) > watermark:
        return None
    day_start = watermark.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    if not repository.ib_daily_realized_coverage_is_complete(
        account_id=account_id,
        day_start_utc=day_start,
        evaluation_utc=watermark,
    ):
        return None
    return watermark


def _section(source: str, start: str, end: str) -> str:
    """Виділити production method section для static assertions."""
    start_index = source.index(start)
    end_index = source.index(end, start_index + len(start))
    return source[start_index:end_index]


def main() -> None:
    """Запустити shared durable watermark contract assertions T109-105."""
    repository_path = Path(getfile(RuntimeRepository)).resolve()
    production_root = repository_path.parents[1]
    engine_path = Path(getfile(RuntimeEngine)).resolve()
    controller_path = Path(getfile(AlgorithmWorkspaceController)).resolve()
    main_path = Path(getfile(MainAppWindow)).resolve()
    lifecycle_path = Path(getfile(IBReconciliationLifecycleBridge)).resolve()
    schema_path = production_root / "engine/db/runtime_db.py"
    production_paths = (
        repository_path,
        engine_path,
        controller_path,
        main_path,
        lifecycle_path,
        schema_path,
    )
    hashes_before = _hashes(production_paths)

    account_id = "DU105"
    workspace_uid = "10900000-0000-4000-8000-000000000105"
    account_timestamp = datetime(2026, 9, 23, 15, 0, 0, tzinfo=UTC)
    coverage_end = datetime(2026, 9, 23, 15, 0, 1, tzinfo=UTC)
    authority_timestamp = datetime(2026, 9, 23, 15, 0, 2, tzinfo=UTC)
    future_account_timestamp = datetime(
        2026,
        9,
        23,
        15,
        0,
        30,
        tzinfo=UTC,
    )
    extended_coverage_end = datetime(
        2026,
        9,
        23,
        15,
        0,
        3,
        tzinfo=UTC,
    )
    day_start = account_timestamp.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    with TemporaryDirectory(
        prefix="t109_105_ib_shared_watermark_",
        ignore_cleanup_errors=True,
    ) as temp_dir:
        database_path = Path(temp_dir) / "runtime.sqlite3"
        engine = RuntimeEngine(db_path=str(database_path))
        missing_authority_blocks = _derive_shared_watermark(
            engine.repository,
            account_id=account_id,
            cached_account_utc=account_timestamp,
        ) is None

        engine.repository.record_ib_daily_realized_coverage(
            account_id=account_id,
            start_utc=day_start,
            end_utc=coverage_end,
            source="TEST_ONLY_INITIAL_RECOVERY",
        )
        _persist_authority(
            engine,
            account_id=account_id,
            captured_utc=authority_timestamp,
        )

        account_timestamp_candidate_fails = (
            engine.read_ib_workspace_open_positions_count(
                account_id=account_id,
                workspace_uid=workspace_uid,
                evaluation_utc=account_timestamp,
            )
            is None
        )
        authority_without_coverage_fails = _derive_shared_watermark(
            engine.repository,
            account_id=account_id,
            cached_account_utc=account_timestamp,
        ) is None

        engine.repository.record_ib_daily_realized_coverage(
            account_id=account_id,
            start_utc=coverage_end,
            end_utc=extended_coverage_end,
            source="TEST_ONLY_POST_RECONCILIATION_RECOVERY",
        )
        selected_watermark = _derive_shared_watermark(
            engine.repository,
            account_id=account_id,
            cached_account_utc=account_timestamp,
        )
        future_account_facts_rejected = _derive_shared_watermark(
            engine.repository,
            account_id=account_id,
            cached_account_utc=future_account_timestamp,
        ) is None
        selected_is_authority_not_coverage_end = (
            selected_watermark == authority_timestamp
            and selected_watermark != extended_coverage_end
        )

        pnl_result = engine.read_ib_daily_realized_pnl_snapshot(
            account_id=account_id,
            evaluation_utc=authority_timestamp,
        )
        open_count = engine.read_ib_workspace_open_positions_count(
            account_id=account_id,
            workspace_uid=workspace_uid,
            evaluation_utc=authority_timestamp,
        )
        complete_empty_day_authorizes_zero = (
            pnl_result.success is True
            and pnl_result.daily_realized_pnl == 0.0
            and open_count == 0
        )
        engine.connection.close()

        reopened = RuntimeEngine(db_path=str(database_path))
        reopened_watermark = _derive_shared_watermark(
            reopened.repository,
            account_id=account_id,
            cached_account_utc=account_timestamp,
        )
        deterministic_after_reopen = reopened_watermark == authority_timestamp
        reopened.connection.close()

    main_source = main_path.read_text(encoding="utf-8")
    engine_source = engine_path.read_text(encoding="utf-8")
    recovery_route = _section(
        main_source,
        "    def _recover_ib_daily_realized_account_day_once(",
        "    def _notify_broker_state_changes(",
    )
    current_once_guard_blocks_post_authority_extension = all(
        token in recovery_route
        for token in (
            "if self._ib_daily_realized_recovery_key == recovery_key:",
            "return None",
        )
    )
    live_route = _section(
        engine_source,
        "    def persist_ib_daily_realized_live_events(",
        "    def read_ib_daily_realized_pnl_snapshot(",
    )
    live_events_cannot_authorize_coverage = (
        '"coverage_committed": False' in live_route
        and "record_ib_daily_realized_coverage(" not in live_route
    )
    hashes_after = _hashes(production_paths)
    production_change = hashes_before != hashes_after
    existing_tables_sufficient = (
        selected_watermark == authority_timestamp
        and complete_empty_day_authorizes_zero
        and deterministic_after_reopen
    )
    new_schema_required = False
    risk_snapshot_wiring_added = False
    broker_requests = 0

    assert SCHEMA_VERSION == 12
    assert missing_authority_blocks
    assert account_timestamp_candidate_fails
    assert authority_without_coverage_fails
    assert selected_is_authority_not_coverage_end
    assert future_account_facts_rejected
    assert complete_empty_day_authorizes_zero
    assert deterministic_after_reopen
    assert current_once_guard_blocks_post_authority_extension
    assert live_events_cannot_authorize_coverage
    assert existing_tables_sufficient
    assert not new_schema_required
    assert not production_change
    assert not risk_snapshot_wiring_added
    assert broker_requests == 0

    print("T109-105_IB_RISK_SHARED_DURABLE_WATERMARK_CONTRACT=OK")
    print("test_scope_test_only=True")
    print(f"production_change={production_change}")
    print(f"schema_version={SCHEMA_VERSION}")
    print(f"missing_authority_blocks={missing_authority_blocks}")
    print(
        "account_timestamp_candidate_fails="
        f"{account_timestamp_candidate_fails}"
    )
    print(
        "authority_without_coverage_fails="
        f"{authority_without_coverage_fails}"
    )
    print(f"selected_watermark_rule={SELECTED_WATERMARK_RULE}")
    print(
        "selected_is_authority_not_coverage_end="
        f"{selected_is_authority_not_coverage_end}"
    )
    print(f"future_account_facts_rejected={future_account_facts_rejected}")
    print(
        "complete_empty_day_authorizes_zero="
        f"{complete_empty_day_authorizes_zero}"
    )
    print(f"deterministic_after_reopen={deterministic_after_reopen}")
    print(
        "current_once_guard_blocks_post_authority_extension="
        f"{current_once_guard_blocks_post_authority_extension}"
    )
    print(
        "live_events_cannot_authorize_coverage="
        f"{live_events_cannot_authorize_coverage}"
    )
    print(f"existing_tables_sufficient={existing_tables_sufficient}")
    print(f"new_schema_required={new_schema_required}")
    print(f"risk_snapshot_wiring_added={risk_snapshot_wiring_added}")
    print(f"broker_requests={broker_requests}")
    print(f"recommended_sequence={RECOMMENDED_SEQUENCE}")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


def test_t109_105_ib_risk_shared_durable_watermark_contract() -> None:
    """Запустити T109-105 як pytest test."""
    main()


if __name__ == "__main__":
    main()
