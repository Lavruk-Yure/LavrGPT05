"""T109-86 TEST_ONLY: IB daily PnL recovery route to durable store anatomy."""

from __future__ import annotations

from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (_project_root() / relative_path).read_text(encoding="utf-8")


def main() -> None:
    adapter = _read("engine/ib_adapter.py")
    service = _read("engine/services/ib_runtime_service.py")
    repository = _read("engine/runtime_repository.py")
    engine = _read("engine/runtime_engine.py")

    canonical_live_source_present = all(
        token in adapter
        for token in (
            "def commissionAndFeesReport(",
            "def _try_complete_execution_commission_pair(",
            '"net_realized_pnl": float(realized_pnl)',
            "def get_execution_commission_events(",
        )
    )
    service_live_source_route_present = (
        "def get_execution_commission_events(" in service
    )
    req_executions_recovery_source_present = all(
        token in adapter
        for token in (
            "ExecutionFilter()",
            "execution_filter.acctCode = account",
            "self._client.reqExecutions(",
            "def execDetailsEnd(",
        )
    )
    durable_event_store_api_present = all(
        token in repository
        for token in (
            "def upsert_ib_daily_realized_event(",
            "def list_ib_daily_realized_events(",
        )
    )
    durable_coverage_store_api_present = all(
        token in repository
        for token in (
            "def record_ib_daily_realized_coverage(",
            "def list_ib_daily_realized_coverage(",
            "def ib_daily_realized_coverage_is_complete(",
        )
    )

    production_sources = "\n".join((adapter, service, engine))
    live_event_store_wiring_present = (
        "upsert_ib_daily_realized_event(" in production_sources
    )
    recovery_coverage_store_wiring_present = (
        "record_ib_daily_realized_coverage(" in production_sources
    )
    recovery_store_read_wiring_present = (
        "list_ib_daily_realized_events(" in production_sources
    )

    exec_details_end_only_sets_execution_event = all(
        token in adapter
        for token in (
            "def execDetailsEnd(",
            "self.execution_event.set()",
        )
    )
    commission_pairing_is_independent_callback = all(
        token in adapter
        for token in (
            "def commissionAndFeesReport(",
            "pending_commission_by_exec_id",
            "_try_complete_execution_commission_pair(exec_id)",
        )
    )
    recovery_tracks_snapshot_exec_ids = any(
        token in adapter
        for token in (
            "recovery_exec_ids",
            "expected_recovery_exec_ids",
            "execution_request_exec_ids",
            "req_id_to_exec_ids",
        )
    )
    recovery_waits_for_all_commission_pairs = any(
        token in adapter or token in service
        for token in (
            "wait_for_execution_commission_pairs",
            "all_recovered_exec_ids_paired",
            "recovery_pairs_complete",
        )
    )
    dedicated_daily_recovery_route_present = any(
        token in adapter or token in service or token in engine
        for token in (
            "recover_ib_daily_realized",
            "recover_daily_execution_commission_events",
            "get_ib_daily_realized_recovery",
            "rebuild_ib_daily_realized",
        )
    )

    live_completed_pair_can_be_persisted_causally = (
        canonical_live_source_present and durable_event_store_api_present
    )
    req_executions_can_recover_execution_halves = (
        req_executions_recovery_source_present
    )
    exec_details_end_is_not_enough_for_source_complete = (
        exec_details_end_only_sets_execution_event
        and commission_pairing_is_independent_callback
    )
    recovery_completion_authority_present = (
        recovery_tracks_snapshot_exec_ids
        and recovery_waits_for_all_commission_pairs
    )

    production_route_complete = all(
        (
            live_event_store_wiring_present,
            recovery_coverage_store_wiring_present,
            recovery_store_read_wiring_present,
            dedicated_daily_recovery_route_present,
            recovery_completion_authority_present,
        )
    )
    source_complete_true_allowed_now = production_route_complete

    assert canonical_live_source_present
    assert service_live_source_route_present
    assert req_executions_recovery_source_present
    assert durable_event_store_api_present
    assert durable_coverage_store_api_present
    assert not live_event_store_wiring_present
    assert not recovery_coverage_store_wiring_present
    assert not recovery_store_read_wiring_present
    assert exec_details_end_only_sets_execution_event
    assert commission_pairing_is_independent_callback
    assert not recovery_tracks_snapshot_exec_ids
    assert not recovery_waits_for_all_commission_pairs
    assert not dedicated_daily_recovery_route_present
    assert live_completed_pair_can_be_persisted_causally
    assert req_executions_can_recover_execution_halves
    assert exec_details_end_is_not_enough_for_source_complete
    assert not recovery_completion_authority_present
    assert not production_route_complete
    assert not source_complete_true_allowed_now

    print("T109-86_IB_DAILY_PNL_RECOVERY_ROUTE_TO_DURABLE_STORE_ANATOMY=OK")
    print("test_scope_test_only=True")
    print("production_change=False")
    print(f"canonical_live_source_present={canonical_live_source_present}")
    print(
        "service_live_source_route_present="
        f"{service_live_source_route_present}"
    )
    print(
        "req_executions_recovery_source_present="
        f"{req_executions_recovery_source_present}"
    )
    print(
        "durable_event_store_api_present="
        f"{durable_event_store_api_present}"
    )
    print(
        "durable_coverage_store_api_present="
        f"{durable_coverage_store_api_present}"
    )
    print(
        "live_event_store_wiring_present="
        f"{live_event_store_wiring_present}"
    )
    print(
        "recovery_coverage_store_wiring_present="
        f"{recovery_coverage_store_wiring_present}"
    )
    print(
        "recovery_store_read_wiring_present="
        f"{recovery_store_read_wiring_present}"
    )
    print(
        "exec_details_end_only_sets_execution_event="
        f"{exec_details_end_only_sets_execution_event}"
    )
    print(
        "commission_pairing_is_independent_callback="
        f"{commission_pairing_is_independent_callback}"
    )
    print(
        "recovery_tracks_snapshot_exec_ids="
        f"{recovery_tracks_snapshot_exec_ids}"
    )
    print(
        "recovery_waits_for_all_commission_pairs="
        f"{recovery_waits_for_all_commission_pairs}"
    )
    print(
        "dedicated_daily_recovery_route_present="
        f"{dedicated_daily_recovery_route_present}"
    )
    print(
        "live_completed_pair_can_be_persisted_causally="
        f"{live_completed_pair_can_be_persisted_causally}"
    )
    print(
        "req_executions_can_recover_execution_halves="
        f"{req_executions_can_recover_execution_halves}"
    )
    print(
        "exec_details_end_is_not_enough_for_source_complete="
        f"{exec_details_end_is_not_enough_for_source_complete}"
    )
    print(
        "recovery_completion_authority_present="
        f"{recovery_completion_authority_present}"
    )
    print(f"production_route_complete={production_route_complete}")
    print(
        "source_complete_true_allowed_now="
        f"{source_complete_true_allowed_now}"
    )
    print("broker_requests=0")
    print(
        "recommended_live_rule=PERSIST_ONLY_COMPLETED_EXECUTION_COMMISSION_"
        "PAIRS_BY_ACCOUNT_EXEC_ID"
    )
    print(
        "recommended_recovery_rule=TRACK_EVERY_REQEXECUTIONS_EXEC_ID_AND_"
        "WAIT_UNTIL_EACH_HAS_A_COMPLETE_COMMISSION_PAIR_BEFORE_RECORDING_"
        "RECOVERY_COVERAGE"
    )
    print(
        "recommended_coverage_rule=NEVER_MARK_COVERAGE_AT_EXECDETAILSEND_"
        "ALONE"
    )
    print(
        "first_unresolved_boundary="
        "IB_DAILY_PNL_RECOVERY_COMPLETION_AUTHORITY"
    )
    print(
        "boundary_contract=THE_DURABLE_EVENT_AND_COVERAGE_STORE_EXISTS_AND_"
        "IB_CAN_EMIT_CANONICAL_COMPLETED_PAIRS_BUT_PRODUCTION_HAS_NO_ROUTE_"
        "THAT_PERSISTS_LIVE_PAIRS_OR_TRACKS_REQEXECUTIONS_EXEC_IDS_UNTIL_"
        "ALL_COMMISSION_PAIRS_COMPLETE_BEFORE_RECORDING_RECOVERY_COVERAGE"
    )
    print(
        "factual_verdict=B. IB_DURABLE_STORE_AND_CANONICAL_EVENT_SOURCES_"
        "EXIST_BUT_RECOVERY_COMPLETION_AUTHORITY_AND_STORE_WIRING_ARE_"
        "NOT_IMPLEMENTED"
    )


if __name__ == "__main__":
    main()
