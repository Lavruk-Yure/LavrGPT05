"""T109-87 TEST_ONLY: IB recovery completion authority contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (_project_root() / relative_path).read_text(encoding="utf-8")


@dataclass(slots=True)
class _RecoveryAuthority:
    req_id: int
    exec_details_end_seen: bool = False
    expected_exec_ids: set[str] = field(default_factory=set)
    completed_exec_ids: set[str] = field(default_factory=set)
    failed: bool = False
    coverage_committed: bool = False

    def on_execution(self, exec_id: str) -> None:
        if not self.failed and exec_id:
            self.expected_exec_ids.add(exec_id)

    def on_pair_complete(self, exec_id: str) -> None:
        if not self.failed and exec_id:
            self.completed_exec_ids.add(exec_id)
        self._try_commit()

    def on_exec_details_end(self) -> None:
        if self.failed:
            return
        self.exec_details_end_seen = True
        self._try_commit()

    def on_timeout(self) -> None:
        self.failed = True
        self.coverage_committed = False

    def _try_commit(self) -> None:
        if self.failed or not self.exec_details_end_seen:
            return
        if not self.expected_exec_ids.issubset(self.completed_exec_ids):
            return
        self.coverage_committed = True


def main() -> None:
    ib_adapter = _read("engine/ib_adapter.py")
    repository = _read("engine/runtime_repository.py")

    execution_callback_present = "def execDetails(" in ib_adapter
    commission_callback_present = "def commissionAndFeesReport(" in ib_adapter
    exec_end_callback_present = "def execDetailsEnd(" in ib_adapter
    pairing_present = "_try_complete_execution_commission_pair" in ib_adapter
    normalized_event_route_present = (
        "def get_execution_commission_events(" in ib_adapter
    )
    durable_event_store_present = (
        "def upsert_ib_daily_realized_event(" in repository
    )
    durable_coverage_store_present = (
        "def record_ib_daily_realized_coverage(" in repository
    )

    production_tracks_req_exec_ids = any(
        token in ib_adapter
        for token in (
            "recovery_exec_ids",
            "expected_recovery_exec_ids",
            "req_id_to_exec_ids",
        )
    )
    production_waits_all_pairs = any(
        token in ib_adapter
        for token in (
            "all_recovered_exec_ids_paired",
            "recovery_pairs_complete",
            "wait_for_execution_commission_pairs",
        )
    )

    empty = _RecoveryAuthority(req_id=1)
    empty.on_exec_details_end()
    empty_snapshot_can_complete = empty.coverage_committed

    execution_first = _RecoveryAuthority(req_id=2)
    execution_first.on_execution("E1")
    execution_first.on_exec_details_end()
    execution_first_waits_for_cost = not execution_first.coverage_committed
    execution_first.on_pair_complete("E1")
    execution_first_completes = execution_first.coverage_committed

    cost_first = _RecoveryAuthority(req_id=3)
    cost_first.on_pair_complete("E2")
    cost_first.on_execution("E2")
    cost_first.on_exec_details_end()
    cost_first_completes = cost_first.coverage_committed

    duplicate = _RecoveryAuthority(req_id=4)
    duplicate.on_execution("E3")
    duplicate.on_execution("E3")
    duplicate.on_pair_complete("E3")
    duplicate.on_pair_complete("E3")
    duplicate.on_exec_details_end()
    duplicate_exec_id_safe = (
        duplicate.coverage_committed
        and duplicate.expected_exec_ids == {"E3"}
        and duplicate.completed_exec_ids == {"E3"}
    )

    multi = _RecoveryAuthority(req_id=5)
    multi.on_execution("E4")
    multi.on_execution("E5")
    multi.on_pair_complete("E4")
    multi.on_exec_details_end()
    one_missing_pair_blocks_coverage = not multi.coverage_committed
    multi.on_pair_complete("E5")
    all_pairs_complete_commits_coverage = multi.coverage_committed

    late = _RecoveryAuthority(req_id=6)
    late.on_execution("E6")
    late.on_exec_details_end()
    late_commission_before_commit = not late.coverage_committed
    late.on_pair_complete("E6")
    late_commission_allows_commit = late.coverage_committed

    timeout = _RecoveryAuthority(req_id=7)
    timeout.on_execution("E7")
    timeout.on_exec_details_end()
    timeout.on_timeout()
    timeout.on_pair_complete("E7")
    timeout_fail_closed = not timeout.coverage_committed and timeout.failed

    authority_contract_complete = all(
        (
            empty_snapshot_can_complete,
            execution_first_waits_for_cost,
            execution_first_completes,
            cost_first_completes,
            duplicate_exec_id_safe,
            one_missing_pair_blocks_coverage,
            all_pairs_complete_commits_coverage,
            late_commission_before_commit,
            late_commission_allows_commit,
            timeout_fail_closed,
        )
    )

    assert execution_callback_present
    assert commission_callback_present
    assert exec_end_callback_present
    assert pairing_present
    assert normalized_event_route_present
    assert durable_event_store_present
    assert durable_coverage_store_present
    assert not production_tracks_req_exec_ids
    assert not production_waits_all_pairs
    assert authority_contract_complete

    print("T109-87_IB_RECOVERY_COMPLETION_AUTHORITY_CONTRACT=OK")
    print("test_scope_test_only=True")
    print("production_change=False")
    print(f"execution_callback_present={execution_callback_present}")
    print(f"commission_callback_present={commission_callback_present}")
    print(f"exec_end_callback_present={exec_end_callback_present}")
    print(f"pairing_present={pairing_present}")
    print(f"normalized_event_route_present={normalized_event_route_present}")
    print(f"durable_event_store_present={durable_event_store_present}")
    print(f"durable_coverage_store_present={durable_coverage_store_present}")
    print(f"production_tracks_req_exec_ids={production_tracks_req_exec_ids}")
    print(f"production_waits_all_pairs={production_waits_all_pairs}")
    print(f"empty_snapshot_can_complete={empty_snapshot_can_complete}")
    print(
        "execution_first_waits_for_cost="
        f"{execution_first_waits_for_cost}"
    )
    print(f"execution_first_completes={execution_first_completes}")
    print(f"cost_first_completes={cost_first_completes}")
    print(f"duplicate_exec_id_safe={duplicate_exec_id_safe}")
    print(
        "one_missing_pair_blocks_coverage="
        f"{one_missing_pair_blocks_coverage}"
    )
    print(
        "all_pairs_complete_commits_coverage="
        f"{all_pairs_complete_commits_coverage}"
    )
    print(
        "late_commission_before_commit="
        f"{late_commission_before_commit}"
    )
    print(
        "late_commission_allows_commit="
        f"{late_commission_allows_commit}"
    )
    print(f"timeout_fail_closed={timeout_fail_closed}")
    print(f"authority_contract_complete={authority_contract_complete}")
    print("broker_requests=0")
    print(
        "recommended_state_machine=REQ_STARTED>EXEC_IDS_DISCOVERED>"
        "EXEC_DETAILS_END>WAIT_MISSING_COMMISSION_PAIRS>"
        "ALL_PAIRS_COMPLETE>PERSIST_EVENTS>RECORD_COVERAGE>SOURCE_COMPLETE"
    )
    print(
        "recommended_empty_snapshot_rule=EXEC_DETAILS_END_WITH_ZERO_EXEC_IDS_"
        "MAY_COMMIT_COVERAGE"
    )
    print(
        "recommended_commit_rule=COMMIT_COVERAGE_ONLY_AFTER_EXEC_DETAILS_END_"
        "AND_EXPECTED_EXEC_IDS_SUBSET_OF_COMPLETED_PAIR_EXEC_IDS"
    )
    print(
        "recommended_timeout_rule=KEEP_SOURCE_INCOMPLETE_AND_DO_NOT_COMMIT_"
        "COVERAGE"
    )
    print(
        "first_unresolved_boundary="
        "IB_DAILY_PNL_RECOVERY_COMPLETION_AUTHORITY_PRODUCTION_WIRING"
    )
    print(
        "boundary_contract=ONE_REQEXECUTIONS_RECOVERY_REQUEST_MUST_TRACK_"
        "EVERY_DISCOVERED_EXEC_ID_AND_MAY_COMMIT_DURABLE_COVERAGE_ONLY_"
        "AFTER_EXECDETAILSEND_AND_AFTER_EVERY_DISCOVERED_EXEC_ID_HAS_A_"
        "COMPLETED_EXECUTION_COMMISSION_PAIR_WITH_TIMEOUT_OR_FAILURE_"
        "REMAINING_FAIL_CLOSED"
    )
    print(
        "factual_verdict=A. IB_RECOVERY_COMPLETION_AUTHORITY_CONTRACT_"
        "IDENTIFIED_WITH_EMPTY_SNAPSHOT_ORDER_INDEPENDENT_PAIRING_DUPLICATE_"
        "SAFETY_LATE_COMMISSION_AND_TIMEOUT_FAIL_CLOSED"
    )


if __name__ == "__main__":
    main()
