"""T109-83 TEST_ONLY: IB daily PnL account-day recovery source anatomy."""

from __future__ import annotations

from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (_project_root() / relative_path).read_text(encoding="utf-8")


def main() -> None:
    ib_adapter = _read("engine/ib_adapter.py")
    ib_service = _read("engine/services/ib_runtime_service.py")

    req_executions_route_present = all(
        token in ib_adapter
        for token in (
            "ExecutionFilter()",
            "self._client.reqExecutions(",
            "def execDetails(",
            "def execDetailsEnd(",
        )
    )
    account_filter_present = "execution_filter.acctCode = account" in ib_adapter
    execution_identity_preserved = '"exec_id": str(' in ib_adapter
    commission_pairing_present = all(
        token in ib_adapter
        for token in (
            "def commissionAndFeesReport(",
            "pending_execution_by_exec_id",
            "pending_commission_by_exec_id",
            "_try_complete_execution_commission_pair",
        )
    )
    canonical_net_amount_present = (
        '"net_realized_pnl": float(realized_pnl)' in ib_adapter
    )
    service_normalized_route_present = (
        "def get_execution_commission_events(" in ib_service
    )

    day_filter_wired = any(
        token in ib_adapter
        for token in (
            "execution_filter.time =",
            "execution_filter.time=",
        )
    )
    dedicated_daily_recovery_route_present = any(
        token in ib_adapter or token in ib_service
        for token in (
            "recover_daily_realized",
            "get_daily_execution_commission_events(",
            "get_account_day_realized_events(",
            "get_daily_realized_pnl_events(",
        )
    )
    persistent_daily_event_store_present = any(
        token in ib_adapter or token in ib_service
        for token in (
            "persist_execution_commission_event",
            "daily_realized_event_repository",
            "daily_realized_events_db",
        )
    )

    # Authoritative IB API semantics used by this TEST_ONLY contract:
    # - reqExecutions returns executions available from the current TWS/account day.
    # - ExecutionFilter.time only narrows results to executions after a timestamp.
    # - Commission reports are delivered with requested execution evidence.
    broker_history_is_current_tws_day_limited = True
    execution_filter_time_is_lower_bound_only = True
    requested_executions_have_commission_evidence = True

    canonical_lge_day_is_utc = True
    tws_day_boundary_is_not_proven_equal_to_utc = True

    can_recover_pairs_from_available_ib_history = all(
        (
            req_executions_route_present,
            account_filter_present,
            execution_identity_preserved,
            commission_pairing_present,
            canonical_net_amount_present,
            requested_executions_have_commission_evidence,
        )
    )
    exec_details_end_alone_is_not_pairing_complete = commission_pairing_present
    source_complete_requires_all_exec_ids_paired = True

    req_executions_can_expand_before_tws_midnight = not (
        broker_history_is_current_tws_day_limited
        and execution_filter_time_is_lower_bound_only
    )
    utc_day_coverage_proven_from_req_executions_alone = not (
        canonical_lge_day_is_utc
        and tws_day_boundary_is_not_proven_equal_to_utc
        and not req_executions_can_expand_before_tws_midnight
    )

    restart_after_tws_midnight_can_lose_earlier_utc_events = (
        canonical_lge_day_is_utc
        and tws_day_boundary_is_not_proven_equal_to_utc
        and broker_history_is_current_tws_day_limited
    )
    durable_carryover_needed_for_utc_day_completeness = (
        restart_after_tws_midnight_can_lose_earlier_utc_events
    )
    production_can_prove_utc_day_complete_after_restart = all(
        (
            dedicated_daily_recovery_route_present,
            persistent_daily_event_store_present,
            utc_day_coverage_proven_from_req_executions_alone,
        )
    )

    missed_callback_recovery_within_available_history_is_feasible = (
        can_recover_pairs_from_available_ib_history
    )
    duplicate_recovery_safe_by_exec_id = (
        "completed_execution_commission_keys" in ib_adapter
        and 'key = ("IB", account_id, exec_id)' in ib_adapter
    )
    source_complete_true_allowed_for_ib_now = (
        production_can_prove_utc_day_complete_after_restart
    )

    assert req_executions_route_present
    assert account_filter_present
    assert execution_identity_preserved
    assert commission_pairing_present
    assert canonical_net_amount_present
    assert service_normalized_route_present
    assert not day_filter_wired
    assert not dedicated_daily_recovery_route_present
    assert not persistent_daily_event_store_present
    assert broker_history_is_current_tws_day_limited
    assert execution_filter_time_is_lower_bound_only
    assert requested_executions_have_commission_evidence
    assert canonical_lge_day_is_utc
    assert tws_day_boundary_is_not_proven_equal_to_utc
    assert can_recover_pairs_from_available_ib_history
    assert exec_details_end_alone_is_not_pairing_complete
    assert source_complete_requires_all_exec_ids_paired
    assert not req_executions_can_expand_before_tws_midnight
    assert not utc_day_coverage_proven_from_req_executions_alone
    assert restart_after_tws_midnight_can_lose_earlier_utc_events
    assert durable_carryover_needed_for_utc_day_completeness
    assert not production_can_prove_utc_day_complete_after_restart
    assert missed_callback_recovery_within_available_history_is_feasible
    assert duplicate_recovery_safe_by_exec_id
    assert not source_complete_true_allowed_for_ib_now

    print("T109-83_IB_DAILY_PNL_ACCOUNT_DAY_RECOVERY_SOURCE_ANATOMY=OK")
    print("test_scope_test_only=True")
    print("production_change=False")
    print(f"req_executions_route_present={req_executions_route_present}")
    print(f"account_filter_present={account_filter_present}")
    print(f"execution_identity_preserved={execution_identity_preserved}")
    print(f"commission_pairing_present={commission_pairing_present}")
    print(f"canonical_net_amount_present={canonical_net_amount_present}")
    print(
        "service_normalized_route_present="
        f"{service_normalized_route_present}"
    )
    print(f"day_filter_wired={day_filter_wired}")
    print(
        "dedicated_daily_recovery_route_present="
        f"{dedicated_daily_recovery_route_present}"
    )
    print(
        "persistent_daily_event_store_present="
        f"{persistent_daily_event_store_present}"
    )
    print(
        "broker_history_is_current_tws_day_limited="
        f"{broker_history_is_current_tws_day_limited}"
    )
    print(
        "execution_filter_time_is_lower_bound_only="
        f"{execution_filter_time_is_lower_bound_only}"
    )
    print(
        "requested_executions_have_commission_evidence="
        f"{requested_executions_have_commission_evidence}"
    )
    print(f"canonical_lge_day_is_utc={canonical_lge_day_is_utc}")
    print(
        "tws_day_boundary_is_not_proven_equal_to_utc="
        f"{tws_day_boundary_is_not_proven_equal_to_utc}"
    )
    print(
        "can_recover_pairs_from_available_ib_history="
        f"{can_recover_pairs_from_available_ib_history}"
    )
    print(
        "exec_details_end_alone_is_not_pairing_complete="
        f"{exec_details_end_alone_is_not_pairing_complete}"
    )
    print(
        "source_complete_requires_all_exec_ids_paired="
        f"{source_complete_requires_all_exec_ids_paired}"
    )
    print(
        "req_executions_can_expand_before_tws_midnight="
        f"{req_executions_can_expand_before_tws_midnight}"
    )
    print(
        "utc_day_coverage_proven_from_req_executions_alone="
        f"{utc_day_coverage_proven_from_req_executions_alone}"
    )
    print(
        "restart_after_tws_midnight_can_lose_earlier_utc_events="
        f"{restart_after_tws_midnight_can_lose_earlier_utc_events}"
    )
    print(
        "durable_carryover_needed_for_utc_day_completeness="
        f"{durable_carryover_needed_for_utc_day_completeness}"
    )
    print(
        "production_can_prove_utc_day_complete_after_restart="
        f"{production_can_prove_utc_day_complete_after_restart}"
    )
    print(
        "missed_callback_recovery_within_available_history_is_feasible="
        f"{missed_callback_recovery_within_available_history_is_feasible}"
    )
    print(
        "duplicate_recovery_safe_by_exec_id="
        f"{duplicate_recovery_safe_by_exec_id}"
    )
    print(
        "source_complete_true_allowed_for_ib_now="
        f"{source_complete_true_allowed_for_ib_now}"
    )
    print("broker_requests=0")
    print(
        "recommended_recovery_rule=REQEXECUTIONS_FOR_AVAILABLE_HISTORY_PLUS_"
        "WAIT_UNTIL_EVERY_RECOVERED_EXEC_ID_HAS_COMPLETE_COMMISSION_PAIR"
    )
    print(
        "recommended_utc_day_rule=DURABLE_CARRYOVER_REQUIRED_WHEN_BROKER_"
        "HISTORY_WINDOW_CANNOT_PROVE_FULL_UTC_DAY"
    )
    print(
        "recommended_incomplete_behavior="
        "KEEP_SOURCE_INCOMPLETE_AND_FAIL_CLOSED"
    )
    print("first_unresolved_boundary=IB_DAILY_PNL_DURABLE_UTC_DAY_CARRYOVER")
    print(
        "boundary_contract=IB_REQEXECUTIONS_CAN_REBUILD_EXECUTION_COMMISSION_"
        "PAIRS_WITHIN_THE_BROKER_AVAILABLE_CURRENT_DAY_WINDOW_BUT_THE_FILTER_"
        "CANNOT_EXPAND_HISTORY_BEFORE_TWS_MIDNIGHT_SO_A_CANONICAL_UTC_DAY_"
        "CANNOT_BE_PROVEN_COMPLETE_AFTER_ARBITRARY_RESTART_WITHOUT_DURABLE_"
        "CARRYOVER_OR_AN_EQUIVALENT_AUTHORITATIVE_HISTORY_SOURCE"
    )
    print(
        "factual_verdict=B. IB_REQEXECUTIONS_RECOVERY_IS_CAUSALLY_USABLE_"
        "WITHIN_AVAILABLE_HISTORY_BUT_CANNOT_UNIVERSALLY_PROVE_FULL_UTC_"
        "ACCOUNT_DAY_COMPLETENESS_AFTER_RESTART"
    )


if __name__ == "__main__":
    main()
