"""T109-70 TEST_ONLY: LGE account-day policy decision anatomy."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

TEST_ONLY = True
BROKER_REQUESTS = 0


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _utc_day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return start, start + timedelta(days=1)


def _in_utc_day(timestamp: datetime, start: datetime, end: datetime) -> bool:
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    normalized = timestamp.astimezone(UTC)
    return start <= normalized < end


def main() -> None:
    root = _project_root()
    ib_source = (root / "engine" / "ib_adapter.py").read_text(encoding="utf-8")
    ctrader_source = (root / "engine" / "ctrader_adapter.py").read_text(
        encoding="utf-8"
    )

    utc_policy_deterministic = True
    account_day_scope_explicit = True
    day = date(2026, 9, 18)
    start, end = _utc_day_bounds(day)

    boundary_start_included = _in_utc_day(start, start, end)
    boundary_end_excluded = not _in_utc_day(end, start, end)
    just_before_end_included = _in_utc_day(
        end - timedelta(microseconds=1),
        start,
        end,
    )

    ib_execution_time_available = all(
        token in ib_source
        for token in (
            "def execDetails(",
            '"time": str(getattr(execution, "time", "") or "")',
            "reqExecutions(",
        )
    )
    ib_account_pnl_candidate_present = "reqPnL(" in ib_source
    ib_position_pnl_present = "reqPnLSingle(" in ib_source
    ib_execution_realized_pnl_available = (
        '"realized_pnl"' in ib_source[ib_source.find("def execDetails(") :]  # noqa
        and "commissionReport" in ib_source
    )
    ib_commission_report_present = "def commissionReport(" in ib_source
    ib_net_realized_from_current_execution_route = (
        ib_execution_realized_pnl_available and ib_commission_report_present
    )

    ctrader_deal_history_present = all(
        token in ctrader_source
        for token in (
            "ProtoOADealListReq",
            "ProtoOADealListRes",
            "def get_deal_history(",
        )
    )
    ctrader_bounded_utc_window_present = all(
        token in ctrader_source
        for token in (
            "request.fromTimestamp = self._datetime_to_epoch_millis(start_utc)",
            "request.toTimestamp = self._datetime_to_epoch_millis(end_utc)",
            "def _datetime_to_epoch_millis(",
            "value.astimezone(UTC)",
        )
    )
    ctrader_close_detail_normalized = "closePositionDetail" in ctrader_source
    ctrader_commission_normalized = "commission" in ctrader_source.lower()
    ctrader_swap_normalized = "swap" in ctrader_source.lower()
    ctrader_net_realized_normalized = all(
        (
            ctrader_close_detail_normalized,
            ctrader_commission_normalized,
            ctrader_swap_normalized,
        )
    )

    current_runtime_can_apply_same_utc_window = (
        ib_execution_time_available
        and ctrader_deal_history_present
        and ctrader_bounded_utc_window_present
    )
    net_cost_semantics_complete_for_both = (
        ib_net_realized_from_current_execution_route and ctrader_net_realized_normalized
    )

    completed_event_only_rule = True
    no_lookahead_rule = True
    late_event_rule = "APPLY_ONLY_FROM_NEXT_RISK_EVALUATION_AFTER_OBSERVATION"
    current_decision_not_rewritten_by_late_event = True
    fail_closed_if_source_incomplete = True

    policy_day_boundary_resolved = all(
        (
            utc_policy_deterministic,
            account_day_scope_explicit,
            boundary_start_included,
            boundary_end_excluded,
            just_before_end_included,
        )
    )
    policy_fully_implementable_now = (
        policy_day_boundary_resolved
        and current_runtime_can_apply_same_utc_window
        and net_cost_semantics_complete_for_both
    )

    checks = {
        "test_scope_test_only": TEST_ONLY,
        "production_change": False,
        "utc_policy_deterministic": utc_policy_deterministic,
        "account_day_scope_explicit": account_day_scope_explicit,
        "utc_start_inclusive": boundary_start_included,
        "utc_end_exclusive": boundary_end_excluded,
        "utc_last_instant_included": just_before_end_included,
        "ib_execution_time_available": ib_execution_time_available,
        "ib_account_pnl_candidate_present": ib_account_pnl_candidate_present,
        "ib_position_pnl_present": ib_position_pnl_present,
        "ib_commission_report_present": ib_commission_report_present,
        "ib_net_realized_from_current_execution_route": (
            ib_net_realized_from_current_execution_route
        ),
        "ctrader_deal_history_present": ctrader_deal_history_present,
        "ctrader_bounded_utc_window_present": ctrader_bounded_utc_window_present,
        "ctrader_close_detail_normalized": ctrader_close_detail_normalized,
        "ctrader_commission_normalized": ctrader_commission_normalized,
        "ctrader_swap_normalized": ctrader_swap_normalized,
        "ctrader_net_realized_normalized": ctrader_net_realized_normalized,
        "same_utc_window_possible_for_both": current_runtime_can_apply_same_utc_window,
        "net_cost_semantics_complete_for_both": net_cost_semantics_complete_for_both,
        "completed_event_only_rule": completed_event_only_rule,
        "no_lookahead_rule": no_lookahead_rule,
        "late_event_does_not_rewrite_prior_decision": (
            current_decision_not_rewritten_by_late_event
        ),
        "fail_closed_if_source_incomplete": fail_closed_if_source_incomplete,
        "policy_day_boundary_resolved": policy_day_boundary_resolved,
        "policy_fully_implementable_now": policy_fully_implementable_now,
    }

    assert all(checks.values()) is False
    required_true = (
        "test_scope_test_only",
        "utc_policy_deterministic",
        "account_day_scope_explicit",
        "utc_start_inclusive",
        "utc_end_exclusive",
        "utc_last_instant_included",
        "ib_execution_time_available",
        "ib_position_pnl_present",
        "ctrader_deal_history_present",
        "ctrader_bounded_utc_window_present",
        "same_utc_window_possible_for_both",
        "completed_event_only_rule",
        "no_lookahead_rule",
        "late_event_does_not_rewrite_prior_decision",
        "fail_closed_if_source_incomplete",
        "policy_day_boundary_resolved",
    )
    for name in required_true:
        assert checks[name], name

    assert not ib_net_realized_from_current_execution_route
    assert not ctrader_net_realized_normalized
    assert not net_cost_semantics_complete_for_both
    assert not policy_fully_implementable_now

    print("T109-70_LGE_ACCOUNT_DAY_POLICY_DECISION_ANATOMY=OK")
    for name, value in checks.items():
        print(f"{name}={value}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(f"late_event_rule={late_event_rule}")
    print("recommended_account_day=UTC_HALF_OPEN_INTERVAL_[00:00_NEXT_00:00)")
    print("recommended_scope=BROKER_ACCOUNT")
    print(
        "recommended_realized_semantics="
        "CLOSED_EXECUTION_NET_OF_BROKER_REPORTED_COSTS"
    )
    print("production_wiring_allowed=False")
    print("recommended_behavior=KEEP_DAILY_PNL_FAIL_CLOSED")
    print("first_unresolved_boundary=DAILY_PNL_NET_REALIZED_DATA_CONTRACT")
    print(
        "boundary_contract=UTC_ACCOUNT_DAY_IS_DETERMINISTIC_BUT_PRODUCTION_MUST_"
        "FIRST_NORMALIZE_COMPLETE_NET_REALIZED_EXECUTION_AND_COST_DATA_FOR_BOTH_"
        "BROKERS_WITHOUT_REWRITING_PRIOR_RISK_DECISIONS_FROM_LATE_EVENTS"
    )
    print(
        "factual_verdict=B. UTC_ACCOUNT_DAY_POLICY_IS_DETERMINISTIC_BUT_"
        "NET_REALIZED_DATA_SEMANTICS_REMAIN_INCOMPLETE"
    )


if __name__ == "__main__":
    main()
