"""T109-71 TEST_ONLY: Daily PnL net-realized data contract anatomy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


TEST_ONLY = True
BROKER_REQUESTS = 0


@dataclass(frozen=True, slots=True)
class CanonicalRealizedEvent:
    """TEST_ONLY canonical closed-execution realized event."""

    broker: str
    account_id: str
    execution_id: str
    gross_realized_pnl: float
    commission_pnl_effect: float
    swap_pnl_effect: float
    other_fee_pnl_effect: float

    @property
    def net_realized_pnl(self) -> float:
        return (
            self.gross_realized_pnl
            + self.commission_pnl_effect
            + self.swap_pnl_effect
            + self.other_fee_pnl_effect
        )


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _deduplicate_events(
    events: list[CanonicalRealizedEvent],
) -> list[CanonicalRealizedEvent]:
    result: list[CanonicalRealizedEvent] = []
    seen: set[tuple[str, str, str]] = set()
    for event in events:
        key = event.broker, event.account_id, event.execution_id
        if key in seen:
            continue
        seen.add(key)
        result.append(event)
    return result


def main() -> None:
    root = _project_root()
    ib_source = (root / "engine" / "ib_adapter.py").read_text(encoding="utf-8")
    ctrader_source = (root / "engine" / "ctrader_adapter.py").read_text(
        encoding="utf-8"
    )

    ib_execution_snapshot_route_present = all(
        token in ib_source
        for token in (
            "ExecutionFilter",
            "reqExecutions(",
            "def execDetails(",
            "def execDetailsEnd(",
        )
    )
    ib_execution_account_present = (
        '"account": str(getattr(execution, "acctNumber", "") or "")'
        in ib_source
    )
    ib_execution_timestamp_present = (
        '"time": str(getattr(execution, "time", "") or "")' in ib_source
    )
    ib_execution_order_identity_present = all(
        token in ib_source
        for token in (
            '"order_id": int(getattr(execution, "orderId", 0) or 0)',
            '"perm_id": int(getattr(execution, "permId", 0) or 0)',
        )
    )
    ib_execution_id_preserved = (
        'getattr(execution, "execId"' in ib_source
        or 'getattr(execution, "execID"' in ib_source
    )
    ib_commission_report_callback_present = "def commissionReport(" in ib_source
    ib_commission_pairing_by_execution_id_possible = (
        ib_execution_id_preserved and ib_commission_report_callback_present
    )
    ib_current_route_can_build_complete_net_realized = (
        ib_execution_snapshot_route_present
        and ib_execution_account_present
        and ib_execution_timestamp_present
        and ib_commission_pairing_by_execution_id_possible
    )

    ctrader_deal_history_route_present = all(
        token in ctrader_source
        for token in (
            "ProtoOADealListReq",
            "ProtoOADealListRes",
            "def get_deal_history(",
        )
    )
    ctrader_deal_history_is_bounded = all(
        token in ctrader_source
        for token in (
            "request.fromTimestamp = self._datetime_to_epoch_millis(start_utc)",
            "request.toTimestamp = self._datetime_to_epoch_millis(end_utc)",
        )
    )
    ctrader_deal_payload_normalizer_present = (
        "def _build_realized" in ctrader_source
        or "def _normalize_deal" in ctrader_source
        or "net_realized_pnl" in ctrader_source
    )
    ctrader_close_detail_normalized = "closePositionDetail" in ctrader_source
    ctrader_commission_normalized = "commission_pnl_effect" in ctrader_source
    ctrader_swap_normalized = "swap_pnl_effect" in ctrader_source
    ctrader_current_route_can_build_complete_net_realized = all(
        (
            ctrader_deal_history_route_present,
            ctrader_deal_history_is_bounded,
            ctrader_deal_payload_normalizer_present,
            ctrader_close_detail_normalized,
            ctrader_commission_normalized,
            ctrader_swap_normalized,
        )
    )

    canonical_execution_identity_required = True
    account_scope_required = True
    closed_execution_only = True
    partial_fills_are_independent_execution_events = True
    multiple_deals_per_order_allowed = True
    broker_costs_normalized_as_signed_pnl_effects = True
    fail_closed_on_missing_identity_or_cost_semantics = True
    late_events_apply_from_next_risk_evaluation = True
    no_lookahead_rule = True

    first_fill = CanonicalRealizedEvent(
        broker="TEST",
        account_id="A1",
        execution_id="E1",
        gross_realized_pnl=10.0,
        commission_pnl_effect=-1.0,
        swap_pnl_effect=-0.5,
        other_fee_pnl_effect=0.0,
    )
    second_fill = CanonicalRealizedEvent(
        broker="TEST",
        account_id="A1",
        execution_id="E2",
        gross_realized_pnl=5.0,
        commission_pnl_effect=-0.5,
        swap_pnl_effect=0.0,
        other_fee_pnl_effect=0.0,
    )
    duplicate_first_fill = first_fill
    unique_events = _deduplicate_events(
        [first_fill, second_fill, duplicate_first_fill]
    )
    dedup_prevents_double_count = len(unique_events) == 2
    partial_fill_net_sum_is_additive = abs(
        sum(event.net_realized_pnl for event in unique_events) - 13.0
    ) < 1e-12

    canonical_contract_complete = all(
        (
            canonical_execution_identity_required,
            account_scope_required,
            closed_execution_only,
            partial_fills_are_independent_execution_events,
            multiple_deals_per_order_allowed,
            broker_costs_normalized_as_signed_pnl_effects,
            fail_closed_on_missing_identity_or_cost_semantics,
            late_events_apply_from_next_risk_evaluation,
            no_lookahead_rule,
            dedup_prevents_double_count,
            partial_fill_net_sum_is_additive,
        )
    )
    production_sources_complete_for_both = (
        ib_current_route_can_build_complete_net_realized
        and ctrader_current_route_can_build_complete_net_realized
    )
    production_wiring_allowed = (
        canonical_contract_complete and production_sources_complete_for_both
    )

    checks = {
        "test_scope_test_only": TEST_ONLY,
        "production_change": False,
        "ib_execution_snapshot_route_present": ib_execution_snapshot_route_present,
        "ib_execution_account_present": ib_execution_account_present,
        "ib_execution_timestamp_present": ib_execution_timestamp_present,
        "ib_execution_order_identity_present": ib_execution_order_identity_present,
        "ib_execution_id_preserved": ib_execution_id_preserved,
        "ib_commission_report_callback_present": (
            ib_commission_report_callback_present
        ),
        "ib_commission_pairing_by_execution_id_possible": (
            ib_commission_pairing_by_execution_id_possible
        ),
        "ib_current_route_can_build_complete_net_realized": (
            ib_current_route_can_build_complete_net_realized
        ),
        "ctrader_deal_history_route_present": ctrader_deal_history_route_present,
        "ctrader_deal_history_is_bounded": ctrader_deal_history_is_bounded,
        "ctrader_deal_payload_normalizer_present": (
            ctrader_deal_payload_normalizer_present
        ),
        "ctrader_close_detail_normalized": ctrader_close_detail_normalized,
        "ctrader_commission_normalized": ctrader_commission_normalized,
        "ctrader_swap_normalized": ctrader_swap_normalized,
        "ctrader_current_route_can_build_complete_net_realized": (
            ctrader_current_route_can_build_complete_net_realized
        ),
        "canonical_execution_identity_required": canonical_execution_identity_required,
        "account_scope_required": account_scope_required,
        "closed_execution_only": closed_execution_only,
        "partial_fills_are_independent_execution_events": (
            partial_fills_are_independent_execution_events
        ),
        "multiple_deals_per_order_allowed": multiple_deals_per_order_allowed,
        "broker_costs_normalized_as_signed_pnl_effects": (
            broker_costs_normalized_as_signed_pnl_effects
        ),
        "dedup_prevents_double_count": dedup_prevents_double_count,
        "partial_fill_net_sum_is_additive": partial_fill_net_sum_is_additive,
        "fail_closed_on_missing_identity_or_cost_semantics": (
            fail_closed_on_missing_identity_or_cost_semantics
        ),
        "late_events_apply_from_next_risk_evaluation": (
            late_events_apply_from_next_risk_evaluation
        ),
        "no_lookahead_rule": no_lookahead_rule,
        "canonical_contract_complete": canonical_contract_complete,
        "production_sources_complete_for_both": production_sources_complete_for_both,
        "production_wiring_allowed": production_wiring_allowed,
    }

    required_true = (
        "test_scope_test_only",
        "ib_execution_snapshot_route_present",
        "ib_execution_account_present",
        "ib_execution_timestamp_present",
        "ib_execution_order_identity_present",
        "ctrader_deal_history_route_present",
        "ctrader_deal_history_is_bounded",
        "canonical_execution_identity_required",
        "account_scope_required",
        "closed_execution_only",
        "partial_fills_are_independent_execution_events",
        "multiple_deals_per_order_allowed",
        "broker_costs_normalized_as_signed_pnl_effects",
        "dedup_prevents_double_count",
        "partial_fill_net_sum_is_additive",
        "fail_closed_on_missing_identity_or_cost_semantics",
        "late_events_apply_from_next_risk_evaluation",
        "no_lookahead_rule",
        "canonical_contract_complete",
    )
    for name in required_true:
        assert checks[name], name

    assert not ib_execution_id_preserved
    assert not ib_commission_report_callback_present
    assert not ib_current_route_can_build_complete_net_realized
    assert not ctrader_deal_payload_normalizer_present
    assert not ctrader_current_route_can_build_complete_net_realized
    assert not production_sources_complete_for_both
    assert not production_wiring_allowed

    print("T109-71_DAILY_PNL_NET_REALIZED_DATA_CONTRACT_ANATOMY=OK")
    for name, value in checks.items():
        print(f"{name}={value}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print("canonical_dedup_key=BROKER+ACCOUNT_ID+EXECUTION_ID")
    print(
        "canonical_net_realized_formula=GROSS_REALIZED_PNL+COMMISSION_PNL_EFFECT+"
        "SWAP_PNL_EFFECT+OTHER_FEE_PNL_EFFECT"
    )
    print("recommended_partial_fill_rule=ONE_CANONICAL_EVENT_PER_EXECUTION_OR_DEAL")
    print("recommended_duplicate_rule=IGNORE_ALREADY_SEEN_EXECUTION_ID")
    print("recommended_missing_data_behavior=KEEP_DAILY_PNL_FAIL_CLOSED")
    print("first_unresolved_boundary=IB_EXECUTION_COST_IDENTITY_NORMALIZATION")
    print(
        "boundary_contract=CANONICAL_NET_REALIZED_EVENT_CONTRACT_IS_DEFINED_BUT_"
        "IB_MUST_PRESERVE_EXECUTION_ID_AND_COMMISSION_PAIRING_AND_CTRADER_MUST_"
        "NORMALIZE_DEAL_CLOSE_RESULT_AND_COST_FIELDS_BEFORE_DAILY_PNL_WIRING"
    )
    print(
        "factual_verdict=A. CANONICAL_NET_REALIZED_EVENT_CONTRACT_IDENTIFIED_BUT_"
        "BROKER_SOURCE_NORMALIZATION_REMAINS_INCOMPLETE"
    )


if __name__ == "__main__":
    main()
