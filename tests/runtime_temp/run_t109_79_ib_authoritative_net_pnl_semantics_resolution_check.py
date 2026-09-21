"""T109-79 TEST_ONLY: IB authoritative net-PnL semantics resolution."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
IB_ADAPTER = PROJECT_ROOT / "engine" / "ib_adapter.py"
IB_SERVICE = PROJECT_ROOT / "engine" / "services" / "ib_runtime_service.py"
BROKER_REQUESTS = 0

# Official IBKR documentation reviewed for this semantic decision:
# 1) Account Value Keys: RealizedPnL is the difference between entry and exit
#    execution costs, and the documented formula includes commissions on both
#    opening and closing executions.
# 2) TWS Statements notes / Reporting Guide: FIFO realized P&L includes or nets
#    commissions into cost basis and sales proceeds.
# 3) CommissionAndFeesReport: realizedPNL is the execution's realized P&L while
#    commissionAndFees is exposed separately for the same execId.
OFFICIAL_REALIZED_PNL_INCLUDES_COMMISSIONS = True
COMMISSION_REPORT_REALIZED_PNL_IS_REALIZED_PNL = True
COMMISSION_AND_FEES_IS_SEPARATE_AUDIT_FIELD = True


def main() -> None:
    """Зафіксувати безпечну IB net-realized semantics для наступного wiring."""
    ib_adapter = IB_ADAPTER.read_text(encoding="utf-8")
    ib_service = IB_SERVICE.read_text(encoding="utf-8")

    production_pair_route_present = all(
        token in ib_adapter
        for token in (
            "def commissionAndFeesReport(",
            '"commission_and_fees": float(commission_value)',
            '"broker_reported_realized_pnl": float(realized_pnl)',
            "def get_execution_commission_events(",
        )
    ) and "def get_execution_commission_events(" in ib_service

    production_values_preserved_separately = all(
        token in ib_adapter
        for token in (
            '"commission_and_fees": float(commission_value)',
            '"broker_reported_realized_pnl": float(realized_pnl)',
        )
    )

    pair_start = ib_adapter.find("def _try_complete_execution_commission_pair(")
    pair_end = ib_adapter.find("def execDetailsEnd(")
    pair_source = ib_adapter[pair_start:pair_end]
    production_canonical_net_amount_present = '"net_realized_pnl"' in pair_source

    authoritative_net_semantics_resolved = all(
        (
            OFFICIAL_REALIZED_PNL_INCLUDES_COMMISSIONS,
            COMMISSION_REPORT_REALIZED_PNL_IS_REALIZED_PNL,
            COMMISSION_AND_FEES_IS_SEPARATE_AUDIT_FIELD,
        )
    )

    sample_broker_reported_realized_pnl = 10.0
    sample_commission_and_fees = 2.0
    canonical_net_realized_pnl = sample_broker_reported_realized_pnl
    incorrect_double_subtracted_value = (
        sample_broker_reported_realized_pnl - sample_commission_and_fees
    )
    double_subtraction_changes_broker_realized = (
        canonical_net_realized_pnl != incorrect_double_subtracted_value
    )

    safe_to_use_broker_reported_realized_as_net = authoritative_net_semantics_resolved
    safe_to_subtract_commission_again = False
    commission_kept_for_audit_only = True
    production_net_normalizer_allowed = all(
        (
            production_pair_route_present,
            production_values_preserved_separately,
            authoritative_net_semantics_resolved,
            safe_to_use_broker_reported_realized_as_net,
            commission_kept_for_audit_only,
        )
    )

    prior_risk_decision_rewrite = False
    no_lookahead_rule = True

    assert BROKER_REQUESTS == 0
    assert production_pair_route_present
    assert production_values_preserved_separately
    assert not production_canonical_net_amount_present
    assert OFFICIAL_REALIZED_PNL_INCLUDES_COMMISSIONS
    assert COMMISSION_REPORT_REALIZED_PNL_IS_REALIZED_PNL
    assert COMMISSION_AND_FEES_IS_SEPARATE_AUDIT_FIELD
    assert authoritative_net_semantics_resolved
    assert double_subtraction_changes_broker_realized
    assert safe_to_use_broker_reported_realized_as_net
    assert not safe_to_subtract_commission_again
    assert commission_kept_for_audit_only
    assert production_net_normalizer_allowed
    assert no_lookahead_rule
    assert not prior_risk_decision_rewrite

    print("T109-79_IB_AUTHORITATIVE_NET_PNL_SEMANTICS_RESOLUTION=OK")
    print("test_scope_test_only=True")
    print("production_change=False")
    print(f"production_pair_route_present={production_pair_route_present}")
    print(
        "production_values_preserved_separately="
        f"{production_values_preserved_separately}"
    )
    print(
        "production_canonical_net_amount_present="
        f"{production_canonical_net_amount_present}"
    )
    print(
        "official_realized_pnl_includes_commissions="
        f"{OFFICIAL_REALIZED_PNL_INCLUDES_COMMISSIONS}"
    )
    print(
        "commission_report_realized_pnl_is_realized_pnl="
        f"{COMMISSION_REPORT_REALIZED_PNL_IS_REALIZED_PNL}"
    )
    print(
        "commission_and_fees_is_separate_audit_field="
        f"{COMMISSION_AND_FEES_IS_SEPARATE_AUDIT_FIELD}"
    )
    print(
        "authoritative_net_semantics_resolved="
        f"{authoritative_net_semantics_resolved}"
    )
    print(
        "double_subtraction_changes_broker_realized="
        f"{double_subtraction_changes_broker_realized}"
    )
    print(
        "safe_to_use_broker_reported_realized_as_net="
        f"{safe_to_use_broker_reported_realized_as_net}"
    )
    print(
        "safe_to_subtract_commission_again="
        f"{safe_to_subtract_commission_again}"
    )
    print(f"commission_kept_for_audit_only={commission_kept_for_audit_only}")
    print(
        "production_net_normalizer_allowed="
        f"{production_net_normalizer_allowed}"
    )
    print("no_lookahead_rule=True")
    print("prior_risk_decision_rewrite=False")
    print(f"broker_requests={BROKER_REQUESTS}")
    print("recommended_ib_net_realized_source=BROKER_REPORTED_REALIZED_PNL")
    print("recommended_commission_behavior=AUDIT_ONLY_DO_NOT_SUBTRACT_AGAIN")
    print("first_unresolved_boundary=IB_NET_REALIZED_PRODUCTION_NORMALIZER")
    print(
        "boundary_contract=OFFICIAL_IBKR_REALIZED_PNL_SEMANTICS_INCLUDE_"
        "COMMISSIONS_IN_EXECUTION_COSTS_SO_COMMISSION_AND_FEES_REPORT_"
        "REALIZED_PNL_CAN_BE_THE_CANONICAL_IB_NET_REALIZED_AMOUNT_WHILE_"
        "COMMISSION_AND_FEES_REMAINS_A_SEPARATE_AUDIT_FIELD_AND_MUST_NOT_"
        "BE_SUBTRACTED_AGAIN"
    )
    print(
        "factual_verdict=A. IB_AUTHORITATIVE_NET_REALIZED_SEMANTICS_RESOLVED_"
        "USE_BROKER_REPORTED_REALIZED_PNL_WITHOUT_DOUBLE_SUBTRACTING_COSTS"
    )


if __name__ == "__main__":
    main()
