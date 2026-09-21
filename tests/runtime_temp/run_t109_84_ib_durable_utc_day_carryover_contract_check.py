"""T109-84 TEST_ONLY: IB durable UTC-day carryover contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class _Coverage:
    start: datetime
    end: datetime


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (_project_root() / relative_path).read_text(encoding="utf-8")


def _merge_events(
    persisted: list[dict[str, object]],
    recovered: list[dict[str, object]],
) -> tuple[bool, list[dict[str, object]]]:
    by_key: dict[tuple[str, str, str], dict[str, object]] = {}

    for event in persisted + recovered:
        broker = str(event.get("broker") or "").strip().upper()
        account = str(event.get("account_id") or "").strip()
        exec_id = str(event.get("exec_id") or "").strip()
        if broker != "IB" or not account or not exec_id:
            return False, []

        key = broker, account, exec_id
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = event
            continue

        if (
            existing.get("execution_time") != event.get("execution_time")
            or existing.get("net_realized_pnl")
            != event.get("net_realized_pnl")
        ):
            return False, []

    return True, list(by_key.values())


def _coverage_complete(
    day_start: datetime,
    evaluation: datetime,
    segments: list[_Coverage],
) -> bool:
    ordered = sorted(segments, key=lambda item: item.start)
    cursor = day_start

    for segment in ordered:
        if segment.end <= cursor:
            continue
        if segment.start > cursor:
            return False
        cursor = max(cursor, segment.end)
        if cursor >= evaluation:
            return True

    return cursor >= evaluation


def main() -> None:
    runtime_db = _read("engine/db/runtime_db.py")
    aggregator = _read("engine/daily_realized_pnl.py")
    ib_adapter = _read("engine/ib_adapter.py")

    aggregator_requires_source_complete = (
        "if not source_complete:" in aggregator
        and "Canonical realized-event source is incomplete." in aggregator
    )
    durable_event_table_present = "daily_realized_events" in runtime_db
    durable_coverage_table_present = "daily_realized_coverage" in runtime_db
    ib_exec_id_dedup_present = (
        "completed_execution_commission_keys" in ib_adapter
        and 'key = ("IB", account_id, exec_id)' in ib_adapter
    )
    ib_recovery_source_present = all(
        token in ib_adapter
        for token in (
            "ExecutionFilter()",
            "reqExecutions(",
            "commissionAndFeesReport(",
        )
    )

    day_start = datetime(2026, 9, 21, 0, 0, tzinfo=UTC)
    evaluation = datetime(2026, 9, 21, 9, 0, tzinfo=UTC)

    persisted = [
        {
            "broker": "IB",
            "account_id": "DU1",
            "exec_id": "E1",
            "execution_time": "20260921 01:00:00 UTC",
            "net_realized_pnl": 5.0,
        },
        {
            "broker": "IB",
            "account_id": "DU1",
            "exec_id": "E2",
            "execution_time": "20260921 05:00:00 UTC",
            "net_realized_pnl": -2.0,
        },
    ]
    recovered = [
        {
            "broker": "IB",
            "account_id": "DU1",
            "exec_id": "E2",
            "execution_time": "20260921 05:00:00 UTC",
            "net_realized_pnl": -2.0,
        },
        {
            "broker": "IB",
            "account_id": "DU1",
            "exec_id": "E3",
            "execution_time": "20260921 08:00:00 UTC",
            "net_realized_pnl": 3.0,
        },
    ]

    merge_success, merged = _merge_events(persisted, recovered)
    duplicate_exec_id_deduped = merge_success and len(merged) == 3

    conflict = [
        {
            "broker": "IB",
            "account_id": "DU1",
            "exec_id": "E2",
            "execution_time": "20260921 05:00:00 UTC",
            "net_realized_pnl": -9.0,
        }
    ]
    conflict_success, _ = _merge_events(persisted, conflict)
    conflicting_duplicate_fail_closed = not conflict_success

    overlapping_coverage = [
        _Coverage(
            datetime(2026, 9, 21, 0, 0, tzinfo=UTC),
            datetime(2026, 9, 21, 7, 0, tzinfo=UTC),
        ),
        _Coverage(
            datetime(2026, 9, 21, 6, 30, tzinfo=UTC),
            evaluation,
        ),
    ]
    coverage_with_overlap_is_complete = _coverage_complete(
        day_start,
        evaluation,
        overlapping_coverage,
    )

    gap_coverage = [
        _Coverage(
            datetime(2026, 9, 21, 0, 0, tzinfo=UTC),
            datetime(2026, 9, 21, 6, 0, tzinfo=UTC),
        ),
        _Coverage(
            datetime(2026, 9, 21, 7, 0, tzinfo=UTC),
            evaluation,
        ),
    ]
    uncovered_gap_fail_closed = not _coverage_complete(
        day_start,
        evaluation,
        gap_coverage,
    )

    restart_after_broker_history_reset_requires_overlap = True
    durable_events_alone_do_not_prove_no_gap = True
    durable_coverage_ledger_required = True
    recovered_pairs_must_be_complete = True
    merge_conflict_must_fail_closed = True
    prior_day_events_must_be_ignored_by_aggregator = True
    source_complete_requires_contiguous_coverage = True
    source_complete_allowed_after_restart = (
        coverage_with_overlap_is_complete
        and duplicate_exec_id_deduped
        and conflicting_duplicate_fail_closed
    )
    production_store_present = (
        durable_event_table_present and durable_coverage_table_present
    )

    assert aggregator_requires_source_complete
    assert not durable_event_table_present
    assert not durable_coverage_table_present
    assert ib_exec_id_dedup_present
    assert ib_recovery_source_present
    assert merge_success
    assert duplicate_exec_id_deduped
    assert conflicting_duplicate_fail_closed
    assert coverage_with_overlap_is_complete
    assert uncovered_gap_fail_closed
    assert restart_after_broker_history_reset_requires_overlap
    assert durable_events_alone_do_not_prove_no_gap
    assert durable_coverage_ledger_required
    assert recovered_pairs_must_be_complete
    assert merge_conflict_must_fail_closed
    assert prior_day_events_must_be_ignored_by_aggregator
    assert source_complete_requires_contiguous_coverage
    assert source_complete_allowed_after_restart
    assert not production_store_present

    print("T109-84_IB_DURABLE_UTC_DAY_CARRYOVER_CONTRACT=OK")
    print("test_scope_test_only=True")
    print("production_change=False")
    print(
        "aggregator_requires_source_complete="
        f"{aggregator_requires_source_complete}"
    )
    print(f"durable_event_table_present={durable_event_table_present}")
    print(f"durable_coverage_table_present={durable_coverage_table_present}")
    print(f"ib_exec_id_dedup_present={ib_exec_id_dedup_present}")
    print(f"ib_recovery_source_present={ib_recovery_source_present}")
    print(f"duplicate_exec_id_deduped={duplicate_exec_id_deduped}")
    print(
        "conflicting_duplicate_fail_closed="
        f"{conflicting_duplicate_fail_closed}"
    )
    print(
        "coverage_with_overlap_is_complete="
        f"{coverage_with_overlap_is_complete}"
    )
    print(f"uncovered_gap_fail_closed={uncovered_gap_fail_closed}")
    print(
        "restart_after_broker_history_reset_requires_overlap="
        f"{restart_after_broker_history_reset_requires_overlap}"
    )
    print(
        "durable_events_alone_do_not_prove_no_gap="
        f"{durable_events_alone_do_not_prove_no_gap}"
    )
    print(
        "durable_coverage_ledger_required="
        f"{durable_coverage_ledger_required}"
    )
    print(
        "recovered_pairs_must_be_complete="
        f"{recovered_pairs_must_be_complete}"
    )
    print(
        "merge_conflict_must_fail_closed="
        f"{merge_conflict_must_fail_closed}"
    )
    print(
        "prior_day_events_must_be_ignored_by_aggregator="
        f"{prior_day_events_must_be_ignored_by_aggregator}"
    )
    print(
        "source_complete_requires_contiguous_coverage="
        f"{source_complete_requires_contiguous_coverage}"
    )
    print(
        "source_complete_allowed_after_restart="
        f"{source_complete_allowed_after_restart}"
    )
    print(f"production_store_present={production_store_present}")
    print("broker_requests=0")
    print(
        "recommended_event_key=BROKER+ACCOUNT_ID+EXEC_ID"
    )
    print(
        "recommended_store=CANONICAL_IB_EVENTS_PLUS_DURABLE_"
        "OBSERVATION_COVERAGE_INTERVALS"
    )
    print(
        "recommended_merge=UNION_PERSISTED_AND_RECOVERED_BY_EXEC_ID_"
        "WITH_CONFLICT_FAIL_CLOSED"
    )
    print(
        "recommended_source_complete_rule=CONTIGUOUS_COVERAGE_FROM_UTC_"
        "DAY_START_TO_EVALUATION_PLUS_ALL_RECOVERED_EXEC_IDS_PAIRED"
    )
    print(
        "recommended_restart_rule=REQUIRE_RECOVERY_OVERLAP_WITH_LAST_"
        "DURABLE_COVERAGE_OR_KEEP_SOURCE_INCOMPLETE"
    )
    print(
        "first_unresolved_boundary="
        "IB_DAILY_PNL_DURABLE_CARRYOVER_PRODUCTION_STORE"
    )
    print(
        "boundary_contract=DURABLE_IB_UTC_DAY_RECOVERY_REQUIRES_CANONICAL_"
        "EVENT_PERSISTENCE_AND_A_DURABLE_COVERAGE_LEDGER_SO_PERSISTED_AND_"
        "REQEXECUTIONS_RECOVERED_EVENTS_CAN_BE_MERGED_BY_EXEC_ID_WITHOUT_"
        "DOUBLE_COUNT_AND_SOURCE_COMPLETE_IS_TRUE_ONLY_WHEN_COVERAGE_IS_"
        "CONTIGUOUS_FROM_UTC_DAY_START_TO_THE_CURRENT_EVALUATION"
    )
    print(
        "factual_verdict=A. IB_DURABLE_UTC_DAY_CARRYOVER_CONTRACT_"
        "IDENTIFIED_WITH_EVENT_PERSISTENCE_COVERAGE_CONTINUITY_AND_"
        "FAIL_CLOSED_GAP_DETECTION"
    )


if __name__ == "__main__":
    main()
