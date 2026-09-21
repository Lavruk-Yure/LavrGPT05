"""T109-82 TEST_ONLY: broker daily PnL source completeness anatomy."""

from __future__ import annotations

from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (_project_root() / relative_path).read_text(encoding="utf-8")


def main() -> None:
    ib_adapter = _read("engine/ib_adapter.py")
    ib_service = _read("engine/services/ib_runtime_service.py")
    ctrader_adapter = _read("engine/ctrader_adapter.py")
    ctrader_service = _read("engine/services/ctrader_runtime_service.py")
    aggregator = _read("engine/daily_realized_pnl.py")

    aggregator_requires_source_complete = all(
        token in aggregator
        for token in (
            "source_complete: bool",
            "if not source_complete:",
            "Canonical realized-event source is incomplete.",
        )
    )
    aggregator_uses_utc_account_day = all(
        token in aggregator
        for token in (
            "day_start = evaluation.replace(hour=0",
            "day_end = day_start + timedelta(days=1)",
            "day_start <= timestamp < day_end",
        )
    )
    aggregator_excludes_future_events = "if timestamp >= evaluation:" in aggregator
    aggregator_dedups_identity = all(
        token in aggregator
        for token in (
            "seen: set[tuple[str, str, str]]",
            "if key in seen:",
            "seen.add(key)",
        )
    )

    ib_normalized_events_are_in_memory = all(
        token in ib_adapter
        for token in (
            "self.execution_commission_events",
            "def get_execution_commission_events(",
            "return self._wrapper.get_execution_commission_events()",
        )
    )
    ib_pairing_is_callback_driven = all(
        token in ib_adapter
        for token in (
            "def execDetails(",
            "def commissionAndFeesReport(",
            "self._try_complete_execution_commission_pair(exec_id)",
        )
    )
    ib_req_executions_route_exists = all(
        token in ib_adapter
        for token in (
            "ExecutionFilter()",
            "self._client.reqExecutions(",
            "execution_filter.acctCode = account",
        )
    )
    ib_req_executions_day_filter_present = any(
        token in ib_adapter
        for token in (
            "execution_filter.time =",
            "execution_filter.time=",
        )
    )
    ib_daily_recovery_route_present = any(
        token in ib_adapter or token in ib_service
        for token in (
            "get_daily_realized_pnl_events(",
            "get_account_day_realized_events(",
            "recover_daily_realized",
            "get_daily_execution_commission_events(",
        )
    )
    ib_persistent_daily_cache_present = any(
        token in ib_adapter or token in ib_service
        for token in (
            "daily_realized_event_repository",
            "daily_realized_events_db",
            "persist_execution_commission_event",
        )
    )
    ib_can_prove_account_day_complete_after_restart = (
        ib_daily_recovery_route_present
        and ib_req_executions_day_filter_present
        and ib_persistent_daily_cache_present
    )
    ib_missed_callback_recovery_proven = ib_daily_recovery_route_present

    ctrader_bounded_deal_history_route_present = all(
        token in ctrader_adapter
        for token in (
            "def get_deal_history(",
            "request.fromTimestamp =",
            "request.toTimestamp =",
            "ProtoOADealListReq()",
        )
    )
    ctrader_normalized_day_route_present = all(
        token in ctrader_adapter
        for token in (
            "def get_deal_net_realized_events(",
            "history = self.get_deal_history(start_utc, end_utc)",
        )
    )
    ctrader_pagination_fail_closed = all(
        token in ctrader_adapter
        for token in (
            'if bool(history.get("has_more")):',
            '"cTrader deal history pagination incomplete."',
        )
    )
    ctrader_service_route_present = (
        "def get_deal_net_realized_events(" in ctrader_service
    )
    ctrader_restart_recovery_possible = (
        ctrader_bounded_deal_history_route_present
        and ctrader_normalized_day_route_present
        and ctrader_pagination_fail_closed
        and ctrader_service_route_present
    )
    ctrader_source_complete_rule_defined = ctrader_restart_recovery_possible

    duplicate_or_replayed_event_safe_after_complete_source = aggregator_dedups_identity
    late_event_applies_from_next_evaluation = aggregator_excludes_future_events
    no_lookahead_rule = (
        aggregator_excludes_future_events and aggregator_uses_utc_account_day
    )

    source_complete_true_allowed_for_ib_now = (
        ib_can_prove_account_day_complete_after_restart
    )
    source_complete_true_allowed_for_ctrader_now = ctrader_source_complete_rule_defined

    assert aggregator_requires_source_complete
    assert aggregator_uses_utc_account_day
    assert aggregator_excludes_future_events
    assert aggregator_dedups_identity
    assert ib_normalized_events_are_in_memory
    assert ib_pairing_is_callback_driven
    assert ib_req_executions_route_exists
    assert not ib_req_executions_day_filter_present
    assert not ib_daily_recovery_route_present
    assert not ib_persistent_daily_cache_present
    assert not ib_can_prove_account_day_complete_after_restart
    assert not ib_missed_callback_recovery_proven
    assert ctrader_bounded_deal_history_route_present
    assert ctrader_normalized_day_route_present
    assert ctrader_pagination_fail_closed
    assert ctrader_service_route_present
    assert ctrader_restart_recovery_possible
    assert ctrader_source_complete_rule_defined
    assert duplicate_or_replayed_event_safe_after_complete_source
    assert late_event_applies_from_next_evaluation
    assert no_lookahead_rule
    assert not source_complete_true_allowed_for_ib_now
    assert source_complete_true_allowed_for_ctrader_now

    print("T109-82_BROKER_DAILY_PNL_SOURCE_COMPLETENESS_ANATOMY=OK")
    print("test_scope_test_only=True")
    print("production_change=False")
    print(f"aggregator_requires_source_complete={aggregator_requires_source_complete}")
    print(f"aggregator_uses_utc_account_day={aggregator_uses_utc_account_day}")
    print(f"aggregator_excludes_future_events={aggregator_excludes_future_events}")
    print(f"aggregator_dedups_identity={aggregator_dedups_identity}")
    print(f"ib_normalized_events_are_in_memory={ib_normalized_events_are_in_memory}")
    print(f"ib_pairing_is_callback_driven={ib_pairing_is_callback_driven}")
    print(f"ib_req_executions_route_exists={ib_req_executions_route_exists}")
    print(
        "ib_req_executions_day_filter_present="
        f"{ib_req_executions_day_filter_present}"
    )
    print(f"ib_daily_recovery_route_present={ib_daily_recovery_route_present}")
    print(f"ib_persistent_daily_cache_present={ib_persistent_daily_cache_present}")
    print(
        "ib_can_prove_account_day_complete_after_restart="
        f"{ib_can_prove_account_day_complete_after_restart}"
    )
    print(f"ib_missed_callback_recovery_proven={ib_missed_callback_recovery_proven}")
    print(
        "ctrader_bounded_deal_history_route_present="
        f"{ctrader_bounded_deal_history_route_present}"
    )
    print(
        "ctrader_normalized_day_route_present="
        f"{ctrader_normalized_day_route_present}"
    )
    print(f"ctrader_pagination_fail_closed={ctrader_pagination_fail_closed}")
    print(f"ctrader_service_route_present={ctrader_service_route_present}")
    print(f"ctrader_restart_recovery_possible={ctrader_restart_recovery_possible}")
    print(
        "ctrader_source_complete_rule_defined="
        f"{ctrader_source_complete_rule_defined}"
    )
    print(
        "duplicate_or_replayed_event_safe_after_complete_source="
        f"{duplicate_or_replayed_event_safe_after_complete_source}"
    )
    print(
        "late_event_applies_from_next_evaluation="
        f"{late_event_applies_from_next_evaluation}"
    )
    print(f"no_lookahead_rule={no_lookahead_rule}")
    print(
        "source_complete_true_allowed_for_ib_now="
        f"{source_complete_true_allowed_for_ib_now}"
    )
    print(
        "source_complete_true_allowed_for_ctrader_now="
        f"{source_complete_true_allowed_for_ctrader_now}"
    )
    print("broker_requests=0")
    print("recommended_ib_behavior=KEEP_SOURCE_INCOMPLETE_UNTIL_DAY_RECOVERY_EXISTS")
    print("recommended_ctrader_behavior=COMPLETE_ONLY_AFTER_SUCCESS_AND_HAS_MORE_FALSE")
    print("recommended_restart_rule=REBUILD_CURRENT_UTC_DAY_BEFORE_RISK_ALLOW")
    print("recommended_missed_callback_rule=RECOVER_FROM_BROKER_HISTORY_OR_FAIL_CLOSED")
    print("first_unresolved_boundary=IB_DAILY_PNL_ACCOUNT_DAY_RECOVERY_SOURCE")
    print(
        "boundary_contract=CTRADER_CAN_REBUILD_A_BOUNDED_UTC_DAY_FROM_DEAL_HISTORY_"
        "WITH_PAGINATION_FAIL_CLOSED_BUT_IB_CURRENT_CANONICAL_EVENTS_ARE_SESSION_"
        "MEMORY_ONLY_AND_EXISTING_REQEXECUTIONS_ROUTES_DO_NOT_PROVE_A_COMPLETE_"
        "CURRENT_DAY_EXECUTION_COMMISSION_SOURCE_AFTER_RESTART_OR_MISSED_CALLBACKS"
    )
    print(
        "factual_verdict=B. CTRADER_DAY_SOURCE_CAN_BE_PROVEN_COMPLETE_FROM_BOUNDED_"
        "BROKER_HISTORY_BUT_IB_CURRENT_NORMALIZED_SOURCE_CANNOT_PROVE_ACCOUNT_DAY_"
        "COMPLETENESS_AFTER_RESTART"
    )


if __name__ == "__main__":
    main()
