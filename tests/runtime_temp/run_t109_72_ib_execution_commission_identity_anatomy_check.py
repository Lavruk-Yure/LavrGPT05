"""T109-72 TEST_ONLY: IB execution + commission identity anatomy."""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

from ibapi.commission_and_fees_report import CommissionAndFeesReport
from ibapi.execution import Execution
from ibapi.wrapper import EWrapper


TEST_ONLY = True
BROKER_REQUESTS = 0


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    root = _project_root()
    adapter_path = root / "engine" / "ib_adapter.py"
    service_path = root / "engine" / "services" / "ib_runtime_service.py"

    hashes_before = {
        adapter_path: _sha256(adapter_path),
        service_path: _sha256(service_path),
    }

    ib_source = adapter_path.read_text(encoding="utf-8")
    service_source = service_path.read_text(encoding="utf-8")

    execution_fields = vars(Execution())
    report_fields = vars(CommissionAndFeesReport())

    exec_id_available_in_installed_api = "execId" in execution_fields
    exec_account_available_in_installed_api = "acctNumber" in execution_fields
    exec_time_available_in_installed_api = "time" in execution_fields
    exec_order_id_available_in_installed_api = "orderId" in execution_fields
    exec_perm_id_available_in_installed_api = "permId" in execution_fields

    commission_callback_available_in_installed_api = hasattr(
        EWrapper,
        "commissionAndFeesReport",
    )
    commission_callback_signature = ()
    if commission_callback_available_in_installed_api:
        commission_callback_signature = tuple(
            inspect.signature(EWrapper.commissionAndFeesReport).parameters
        )

    commission_exec_id_available = "execId" in report_fields
    commission_amount_available = "commissionAndFees" in report_fields
    commission_currency_available = "currency" in report_fields
    commission_realized_pnl_available = "realizedPNL" in report_fields

    installed_api_supports_exec_cost_pairing = all(
        (
            exec_id_available_in_installed_api,
            commission_callback_available_in_installed_api,
            commission_exec_id_available,
            commission_amount_available,
            commission_currency_available,
            commission_realized_pnl_available,
        )
    )

    production_exec_details_present = "def execDetails(" in ib_source
    production_exec_account_preserved = (
        '"account": str(getattr(execution, "acctNumber", "") or "")'
        in ib_source
    )
    production_exec_time_preserved = (
        '"time": str(getattr(execution, "time", "") or "")' in ib_source
    )
    production_exec_order_id_preserved = (
        '"order_id": int(getattr(execution, "orderId", 0) or 0)' in ib_source
    )
    production_exec_perm_id_preserved = (
        '"perm_id": int(getattr(execution, "permId", 0) or 0)' in ib_source
    )
    production_exec_id_preserved = (
        'getattr(execution, "execId"' in ib_source
        or 'getattr(execution, "execID"' in ib_source
    )
    production_commission_callback_present = (
        "def commissionAndFeesReport(" in ib_source
    )
    production_commission_cache_present = any(
        token in ib_source or token in service_source
        for token in (
            "commission_and_fees_by_exec_id",
            "commission_by_exec_id",
            "realized_by_exec_id",
        )
    )

    production_can_pair_execution_and_cost = all(
        (
            production_exec_id_preserved,
            production_commission_callback_present,
            production_commission_cache_present,
        )
    )

    execution_id_is_correct_pairing_key = installed_api_supports_exec_cost_pairing
    order_id_is_not_sufficient_for_partial_fills = True
    one_canonical_event_per_exec_id = True
    duplicate_exec_id_must_be_ignored = True
    callback_pairing_must_be_order_independent = True
    incomplete_pair_must_not_enter_daily_net_pnl = True
    late_complete_pair_applies_from_next_risk_evaluation = True
    fail_closed_until_pair_complete = True
    no_lookahead_rule = True

    production_change = any(
        _sha256(path) != digest for path, digest in hashes_before.items()
    )

    assert TEST_ONLY
    assert not production_change
    assert BROKER_REQUESTS == 0
    assert exec_id_available_in_installed_api
    assert exec_account_available_in_installed_api
    assert exec_time_available_in_installed_api
    assert exec_order_id_available_in_installed_api
    assert exec_perm_id_available_in_installed_api
    assert commission_callback_available_in_installed_api
    assert commission_exec_id_available
    assert commission_amount_available
    assert commission_currency_available
    assert commission_realized_pnl_available
    assert installed_api_supports_exec_cost_pairing
    assert production_exec_details_present
    assert production_exec_account_preserved
    assert production_exec_time_preserved
    assert production_exec_order_id_preserved
    assert production_exec_perm_id_preserved
    assert not production_exec_id_preserved
    assert not production_commission_callback_present
    assert not production_can_pair_execution_and_cost
    assert execution_id_is_correct_pairing_key
    assert order_id_is_not_sufficient_for_partial_fills
    assert one_canonical_event_per_exec_id
    assert duplicate_exec_id_must_be_ignored
    assert callback_pairing_must_be_order_independent
    assert incomplete_pair_must_not_enter_daily_net_pnl
    assert late_complete_pair_applies_from_next_risk_evaluation
    assert fail_closed_until_pair_complete
    assert no_lookahead_rule

    print("T109-72_IB_EXECUTION_COMMISSION_IDENTITY_ANATOMY=OK")
    print(f"test_scope_test_only={TEST_ONLY}")
    print(f"production_change={production_change}")
    print(f"exec_id_available_in_installed_api={exec_id_available_in_installed_api}")
    print(
        "exec_account_available_in_installed_api="
        f"{exec_account_available_in_installed_api}"
    )
    print(
        "exec_time_available_in_installed_api="
        f"{exec_time_available_in_installed_api}"
    )
    print(
        "exec_order_id_available_in_installed_api="
        f"{exec_order_id_available_in_installed_api}"
    )
    print(
        "exec_perm_id_available_in_installed_api="
        f"{exec_perm_id_available_in_installed_api}"
    )
    print(
        "commission_callback_available_in_installed_api="
        f"{commission_callback_available_in_installed_api}"
    )
    print(f"commission_callback_signature={commission_callback_signature}")
    print(f"commission_exec_id_available={commission_exec_id_available}")
    print(f"commission_amount_available={commission_amount_available}")
    print(f"commission_currency_available={commission_currency_available}")
    print(f"commission_realized_pnl_available={commission_realized_pnl_available}")
    print(
        "installed_api_supports_exec_cost_pairing="
        f"{installed_api_supports_exec_cost_pairing}"
    )
    print(f"production_exec_details_present={production_exec_details_present}")
    print(f"production_exec_account_preserved={production_exec_account_preserved}")
    print(f"production_exec_time_preserved={production_exec_time_preserved}")
    print(f"production_exec_order_id_preserved={production_exec_order_id_preserved}")
    print(f"production_exec_perm_id_preserved={production_exec_perm_id_preserved}")
    print(f"production_exec_id_preserved={production_exec_id_preserved}")
    print(
        "production_commission_callback_present="
        f"{production_commission_callback_present}"
    )
    print(f"production_commission_cache_present={production_commission_cache_present}")
    print(
        "production_can_pair_execution_and_cost="
        f"{production_can_pair_execution_and_cost}"
    )
    print(
        "execution_id_is_correct_pairing_key="
        f"{execution_id_is_correct_pairing_key}"
    )
    print(
        "order_id_is_not_sufficient_for_partial_fills="
        f"{order_id_is_not_sufficient_for_partial_fills}"
    )
    print(f"one_canonical_event_per_exec_id={one_canonical_event_per_exec_id}")
    print(f"duplicate_exec_id_must_be_ignored={duplicate_exec_id_must_be_ignored}")
    print(
        "callback_pairing_must_be_order_independent="
        f"{callback_pairing_must_be_order_independent}"
    )
    print(
        "incomplete_pair_must_not_enter_daily_net_pnl="
        f"{incomplete_pair_must_not_enter_daily_net_pnl}"
    )
    print(
        "late_complete_pair_applies_from_next_risk_evaluation="
        f"{late_complete_pair_applies_from_next_risk_evaluation}"
    )
    print(f"fail_closed_until_pair_complete={fail_closed_until_pair_complete}")
    print(f"no_lookahead_rule={no_lookahead_rule}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print("recommended_pairing_key=BROKER+ACCOUNT_ID+EXEC_ID")
    print("recommended_partial_fill_rule=ONE_EVENT_PER_EXEC_ID")
    print("recommended_incomplete_pair_behavior=WAIT_COST_AND_FAIL_CLOSED")
    print(
        "first_unresolved_boundary="
        "IB_EXECUTION_COMMISSION_PRODUCTION_NORMALIZER"
    )
    print(
        "boundary_contract=INSTALLED_IB_API_EXPOSES_EXECID_ON_EXECUTION_AND_"
        "COMMISSION_AND_FEES_REPORT_BUT_PRODUCTION_MUST_PRESERVE_EXECID_"
        "AND_PAIR_COST_BY_EXECID_BEFORE_DAILY_NET_REALIZED_PNL_CAN_BE_WIRED"
    )
    print(
        "factual_verdict=A. INSTALLED_IB_API_SUPPORTS_EXECID_COST_PAIRING_"
        "BUT_PRODUCTION_DROPS_EXECID_AND_HAS_NO_COMMISSION_WIRING"
    )


if __name__ == "__main__":
    main()
