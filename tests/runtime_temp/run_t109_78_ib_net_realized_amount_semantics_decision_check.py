"""T109-78 TEST_ONLY: IB net realized amount semantics decision."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IB_ADAPTER = PROJECT_ROOT / "engine" / "ib_adapter.py"
IB_SERVICE = PROJECT_ROOT / "engine" / "services" / "ib_runtime_service.py"
BROKER_REQUESTS = 0

# Reviewed against the current IBKR TWS API reference for
# CommissionAndFeesReport. The reference defines RealizedPNL and
# CommissionAndFees as separate fields, but does not state whether
# RealizedPNL is already net of CommissionAndFees.
OFFICIAL_REFERENCE_FIELDS_SEPARATE = True
OFFICIAL_REFERENCE_NET_RELATION_EXPLICIT = False


def main() -> None:
    """Перевірити, чи можна безпечно визначити IB canonical net amount."""
    ib_adapter = IB_ADAPTER.read_text(encoding="utf-8")
    ib_service = IB_SERVICE.read_text(encoding="utf-8")

    production_pair_route_present = (
        all(
            token in ib_adapter
            for token in (
                "def commissionAndFeesReport(",
                '"commission_and_fees": float(commission_value)',
                '"broker_reported_realized_pnl": float(realized_pnl)',
                "def get_execution_commission_events(",
            )
        )
        and "def get_execution_commission_events(" in ib_service
    )

    production_values_remain_separate = all(
        token in ib_adapter
        for token in (
            '"commission_and_fees": float(commission_value)',
            '"broker_reported_realized_pnl": float(realized_pnl)',
        )
    )
    production_canonical_net_amount_present = (
        '"net_realized_pnl"'
        in ib_adapter[
            ib_adapter.find(
                "def _try_complete_execution_commission_pair("
            ) : ib_adapter.find(  # noqa
                "def execDetailsEnd("
            )
        ]
    )

    sample_realized_pnl = 10.0
    sample_commission_and_fees = 2.0
    candidate_already_net = sample_realized_pnl
    candidate_gross_minus_cost = sample_realized_pnl - sample_commission_and_fees
    candidate_formulas_diverge = candidate_already_net != candidate_gross_minus_cost

    installed_api_exposes_both_values = production_values_remain_separate
    authoritative_net_semantics_resolved = OFFICIAL_REFERENCE_NET_RELATION_EXPLICIT
    safe_to_derive_net_by_subtracting_commission = False
    safe_to_treat_realized_pnl_as_already_net = False
    production_net_normalizer_allowed = all(
        (
            production_pair_route_present,
            installed_api_exposes_both_values,
            authoritative_net_semantics_resolved,
        )
    )

    fail_closed_required = not production_net_normalizer_allowed
    no_lookahead_rule = True
    prior_risk_decision_rewrite = False

    assert BROKER_REQUESTS == 0
    assert production_pair_route_present
    assert production_values_remain_separate
    assert not production_canonical_net_amount_present
    assert OFFICIAL_REFERENCE_FIELDS_SEPARATE
    assert not OFFICIAL_REFERENCE_NET_RELATION_EXPLICIT
    assert candidate_formulas_diverge
    assert installed_api_exposes_both_values
    assert not authoritative_net_semantics_resolved
    assert not safe_to_derive_net_by_subtracting_commission
    assert not safe_to_treat_realized_pnl_as_already_net
    assert not production_net_normalizer_allowed
    assert fail_closed_required
    assert no_lookahead_rule
    assert not prior_risk_decision_rewrite

    print("T109-78_IB_NET_REALIZED_AMOUNT_SEMANTICS_DECISION=OK")
    print("test_scope_test_only=True")
    print("production_change=False")
    print(f"production_pair_route_present={production_pair_route_present}")
    print("production_values_remain_separate=" f"{production_values_remain_separate}")
    print(
        "production_canonical_net_amount_present="
        f"{production_canonical_net_amount_present}"
    )
    print("official_reference_fields_separate=" f"{OFFICIAL_REFERENCE_FIELDS_SEPARATE}")
    print(
        "official_reference_net_relation_explicit="
        f"{OFFICIAL_REFERENCE_NET_RELATION_EXPLICIT}"
    )
    print(f"candidate_formulas_diverge={candidate_formulas_diverge}")
    print("installed_api_exposes_both_values=" f"{installed_api_exposes_both_values}")
    print(
        "authoritative_net_semantics_resolved="
        f"{authoritative_net_semantics_resolved}"
    )
    print(
        "safe_to_derive_net_by_subtracting_commission="
        f"{safe_to_derive_net_by_subtracting_commission}"
    )
    print(
        "safe_to_treat_realized_pnl_as_already_net="
        f"{safe_to_treat_realized_pnl_as_already_net}"
    )
    print("production_net_normalizer_allowed=" f"{production_net_normalizer_allowed}")
    print(f"fail_closed_required={fail_closed_required}")
    print("no_lookahead_rule=True")
    print("prior_risk_decision_rewrite=False")
    print(f"broker_requests={BROKER_REQUESTS}")
    print("recommended_behavior=KEEP_IB_NET_REALIZED_FAIL_CLOSED")
    print("recommended_next_step=OBTAIN_AUTHORITATIVE_IB_NET_PNL_SEMANTICS")
    print("first_unresolved_boundary=IB_NET_REALIZED_AUTHORITATIVE_SEMANTICS")
    print(
        "boundary_contract=IB_COMMISSION_AND_FEES_REPORT_EXPOSES_REALIZED_PNL_"
        "AND_COMMISSION_AND_FEES_SEPARATELY_BUT_CURRENT_AUTHORITATIVE_REFERENCE_"
        "DOES_NOT_STATE_THEIR_NET_RELATION_SO_PRODUCTION_MUST_NOT_DOUBLE_COUNT_"
        "OR_SUBTRACT_COST_WITHOUT_EXPLICIT_SEMANTICS"
    )
    print(
        "factual_verdict=B. IB_NET_REALIZED_AMOUNT_SEMANTICS_REMAIN_"
        "AUTHORITATIVELY_UNRESOLVED_AND_PRODUCTION_MUST_STAY_FAIL_CLOSED"
    )


if __name__ == "__main__":
    main()
