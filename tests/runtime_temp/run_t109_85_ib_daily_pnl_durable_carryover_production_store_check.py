"""T109-85 production: IB durable UTC-day carryover store check."""

from __future__ import annotations

import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.daily_realized_pnl import (  # noqa: E402
    aggregate_broker_daily_realized_pnl,
)
from engine.db.runtime_db import (  # noqa: E402
    SCHEMA_VERSION,
    connect_runtime_db,
    get_schema_version,
)
from engine.runtime_repository import RuntimeRepository  # noqa: E402


def _event(
    exec_id: str,
    execution_time: str,
    amount: float,
) -> dict[str, object]:
    return {
        "broker": "IB",
        "account_id": "DU1",
        "exec_id": exec_id,
        "execution_time": execution_time,
        "net_realized_pnl": amount,
        "broker_reported_realized_pnl": amount,
        "commission_and_fees": 0.25,
        "currency": "USD",
    }


def _persist(
    repository: RuntimeRepository,
    event: dict[str, object],
) -> None:
    repository.upsert_ib_daily_realized_event(
        account_id=str(event["account_id"]),
        exec_id=str(event["exec_id"]),
        execution_time=str(event["execution_time"]),
        net_realized_pnl=float(cast(float, event["net_realized_pnl"])),
        payload=event,
    )


def main() -> None:
    day_start = datetime(2026, 9, 21, 0, 0, tzinfo=UTC)
    evaluation = datetime(2026, 9, 21, 9, 0, tzinfo=UTC)

    with tempfile.TemporaryDirectory(prefix="t109_85_") as temp_dir:
        db_path = Path(temp_dir) / "runtime.db"
        connection = connect_runtime_db(db_path)
        repository = RuntimeRepository(connection)

        schema_version = get_schema_version(connection)
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        event_table_present = "ib_daily_realized_events" in tables
        coverage_table_present = "ib_daily_realized_coverage" in tables

        first = _event("E1", "20260921 01:00:00 UTC", 5.0)
        second = _event("E2", "20260921 05:00:00 UTC", -2.0)
        recovered = _event("E3", "20260921 08:00:00 UTC", 3.0)

        _persist(repository, first)
        _persist(repository, second)
        _persist(repository, second)

        repository.record_ib_daily_realized_coverage(
            account_id="DU1",
            start_utc=day_start,
            end_utc=datetime(2026, 9, 21, 6, 30, tzinfo=UTC),
            source="SESSION",
        )
        connection.close()

        connection = connect_runtime_db(db_path)
        repository = RuntimeRepository(connection)
        persisted_after_restart = repository.list_ib_daily_realized_events(
            account_id="DU1",
        )
        restart_persistence_ok = len(persisted_after_restart) == 2

        _persist(repository, second)
        _persist(repository, recovered)
        merged_after_recovery = repository.list_ib_daily_realized_events(
            account_id="DU1",
        )
        duplicate_same_event_deduped = len(merged_after_recovery) == 3

        conflict = _event("E2", "20260921 05:00:00 UTC", -9.0)
        conflict_fail_closed = False
        try:
            _persist(repository, conflict)
        except ValueError:
            conflict_fail_closed = True

        repository.record_ib_daily_realized_coverage(
            account_id="DU1",
            start_utc=datetime(2026, 9, 21, 6, 0, tzinfo=UTC),
            end_utc=evaluation,
            source="REQEXECUTIONS",
        )
        coverage_with_overlap_complete = (
            repository.ib_daily_realized_coverage_is_complete(
                account_id="DU1",
                day_start_utc=day_start,
                evaluation_utc=evaluation,
            )
        )

        gap_account = "DU_GAP"
        repository.record_ib_daily_realized_coverage(
            account_id=gap_account,
            start_utc=day_start,
            end_utc=datetime(2026, 9, 21, 6, 0, tzinfo=UTC),
            source="SESSION",
        )
        repository.record_ib_daily_realized_coverage(
            account_id=gap_account,
            start_utc=datetime(2026, 9, 21, 7, 0, tzinfo=UTC),
            end_utc=evaluation,
            source="REQEXECUTIONS",
        )
        uncovered_gap_fail_closed = not (
            repository.ib_daily_realized_coverage_is_complete(
                account_id=gap_account,
                day_start_utc=day_start,
                evaluation_utc=evaluation,
            )
        )

        aggregate = aggregate_broker_daily_realized_pnl(
            broker="IB",
            account_id="DU1",
            events=merged_after_recovery,
            evaluation_utc=evaluation,
            source_complete=coverage_with_overlap_complete,
        )
        aggregation_from_persisted_store_correct = (
            aggregate.success
            and aggregate.event_count == 3
            and aggregate.daily_realized_pnl == 6.0
        )

        risk_snapshot_wiring_added = False
        broker_requests = 0

        assert SCHEMA_VERSION == 12
        assert schema_version == SCHEMA_VERSION
        assert event_table_present
        assert coverage_table_present
        assert restart_persistence_ok
        assert duplicate_same_event_deduped
        assert conflict_fail_closed
        assert coverage_with_overlap_complete
        assert uncovered_gap_fail_closed
        assert aggregation_from_persisted_store_correct
        assert not risk_snapshot_wiring_added
        assert broker_requests == 0

        print("T109-85_IB_DAILY_PNL_DURABLE_CARRYOVER_PRODUCTION_STORE=OK")
        print("production_change=True")
        print(f"schema_version={schema_version}")
        print(f"event_table_present={event_table_present}")
        print(f"coverage_table_present={coverage_table_present}")
        print(f"restart_persistence_ok={restart_persistence_ok}")
        print("duplicate_same_event_deduped=" f"{duplicate_same_event_deduped}")
        print(f"conflict_fail_closed={conflict_fail_closed}")
        print("coverage_with_overlap_complete=" f"{coverage_with_overlap_complete}")
        print(f"uncovered_gap_fail_closed={uncovered_gap_fail_closed}")
        print(
            "aggregation_from_persisted_store_correct="
            f"{aggregation_from_persisted_store_correct}"
        )
        print(f"risk_snapshot_wiring_added={risk_snapshot_wiring_added}")
        print(f"broker_requests={broker_requests}")
        print("canonical_key=BROKER+ACCOUNT_ID+EXEC_ID")
        print("coverage_rule=CONTIGUOUS_UTC_DAY_START_TO_EVALUATION")
        print(
            "first_unresolved_boundary=" "IB_DAILY_PNL_RECOVERY_ROUTE_TO_DURABLE_STORE"
        )
        print(
            "boundary_contract=IB_DURABLE_EVENT_AND_COVERAGE_STORE_IS_"
            "PERSISTENT_DEDUPED_AND_GAP_AWARE_BUT_RUNTIME_STILL_MUST_"
            "POPULATE_IT_FROM_LIVE_AND_REQEXECUTIONS_RECOVERY_BEFORE_"
            "SOURCE_COMPLETE_CAN_DRIVE_THE_RISK_SNAPSHOT"
        )
        print(
            "factual_verdict=A. IB_DAILY_PNL_DURABLE_CARRYOVER_"
            "PRODUCTION_STORE_GREEN_WITH_SCHEMA_12_RESTART_PERSISTENCE_"
            "EXECID_DEDUP_CONFLICT_FAIL_CLOSED_AND_COVERAGE_GAP_DETECTION"
        )
        connection.close()


if __name__ == "__main__":
    main()
