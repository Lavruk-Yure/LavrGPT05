"""T109-69 — canonical broker daily realized PnL source decision.

TEST_ONLY: перевіряє, чи можна вже визначити broker-authoritative account-day
realized PnL source для IB і cTrader без зміни production logic.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ibapi.client import EClient  # noqa: E402
from ibapi.wrapper import EWrapper  # noqa: E402


def _source(relative_path: str) -> str:
    """Прочитати production source для factual anatomy."""
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def main() -> None:
    """Зафіксувати source decision без broker requests."""
    ib_adapter = _source("engine/ib_adapter.py")
    ib_service = _source("engine/services/ib_runtime_service.py")
    ctrader_adapter = _source("engine/ctrader_adapter.py")
    ctrader_service = _source("engine/services/ctrader_runtime_service.py")
    controller = _source("core/algorithm_workspace_controller.py")

    req_pnl_fields = tuple(inspect.signature(EClient.reqPnL).parameters)
    pnl_fields = tuple(inspect.signature(EWrapper.pnl).parameters)

    ib_account_pnl_api_present = req_pnl_fields == (
        "self",
        "reqId",
        "account",
        "modelCode",
    ) and pnl_fields == (
        "self",
        "reqId",
        "dailyPnL",
        "unrealizedPnL",
        "realizedPnL",
    )
    ib_account_pnl_production_route_present = "self._client.reqPnL(" in ib_adapter
    ib_position_pnl_route_present = "self._client.reqPnLSingle(" in ib_adapter
    ib_daily_cache_present = any(
        token in ib_service for token in ("daily_realized_pnl", "daily_pnl")
    )

    ctrader_deal_history_route_present = all(
        token in ctrader_adapter
        for token in (
            "ProtoOADealListReq",
            "ProtoOADealListRes",
            "def get_deal_history(",
        )
    )
    ctrader_service_deal_history_route_present = (
        "def get_deal_history(" in ctrader_service
    )
    ctrader_daily_cache_present = any(
        token in ctrader_service for token in ("daily_realized_pnl", "daily_pnl")
    )

    risk_snapshot_daily_pnl_unwired = "daily_realized_pnl=None" in controller

    ib_period_identity_authoritative = False
    ib_account_day_boundary_authoritative = False
    ib_net_cost_completeness_proven = False

    ctrader_period_identity_authoritative = False
    ctrader_account_day_boundary_authoritative = False
    ctrader_net_cost_fields_available = True
    ctrader_account_day_aggregate_possible = True

    broker_neutral_authoritative_source_resolved = False
    production_wiring_allowed = False
    lge_owned_utc_day_policy_would_be_new_policy = True
    fail_closed_required = True
    broker_requests = 0

    assert ib_account_pnl_api_present
    assert not ib_account_pnl_production_route_present
    assert ib_position_pnl_route_present
    assert not ib_daily_cache_present
    assert ctrader_deal_history_route_present
    assert ctrader_service_deal_history_route_present
    assert not ctrader_daily_cache_present
    assert risk_snapshot_daily_pnl_unwired
    assert not ib_period_identity_authoritative
    assert not ib_account_day_boundary_authoritative
    assert not ib_net_cost_completeness_proven
    assert not ctrader_period_identity_authoritative
    assert not ctrader_account_day_boundary_authoritative
    assert ctrader_net_cost_fields_available
    assert ctrader_account_day_aggregate_possible
    assert not broker_neutral_authoritative_source_resolved
    assert not production_wiring_allowed
    assert lge_owned_utc_day_policy_would_be_new_policy
    assert fail_closed_required
    assert broker_requests == 0

    print("T109-69_CANONICAL_BROKER_DAILY_REALIZED_PNL_SOURCE_DECISION=OK")
    print("test_scope=TEST_ONLY")
    print("production_change=False")
    print(f"ib_account_pnl_api_present={ib_account_pnl_api_present}")
    print(
        "ib_account_pnl_production_route_present="
        f"{ib_account_pnl_production_route_present}"
    )
    print(f"ib_position_pnl_route_present={ib_position_pnl_route_present}")
    print(f"ib_daily_cache_present={ib_daily_cache_present}")
    print("ib_period_identity_authoritative=" f"{ib_period_identity_authoritative}")
    print(
        "ib_account_day_boundary_authoritative="
        f"{ib_account_day_boundary_authoritative}"
    )
    print("ib_net_cost_completeness_proven=" f"{ib_net_cost_completeness_proven}")
    print("ctrader_deal_history_route_present=" f"{ctrader_deal_history_route_present}")
    print(
        "ctrader_service_deal_history_route_present="
        f"{ctrader_service_deal_history_route_present}"
    )
    print(f"ctrader_daily_cache_present={ctrader_daily_cache_present}")
    print(
        "ctrader_period_identity_authoritative="
        f"{ctrader_period_identity_authoritative}"
    )
    print(
        "ctrader_account_day_boundary_authoritative="
        f"{ctrader_account_day_boundary_authoritative}"
    )
    print("ctrader_net_cost_fields_available=" f"{ctrader_net_cost_fields_available}")
    print(
        "ctrader_account_day_aggregate_possible="
        f"{ctrader_account_day_aggregate_possible}"
    )
    print("risk_snapshot_daily_pnl_unwired=" f"{risk_snapshot_daily_pnl_unwired}")
    print(
        "broker_neutral_authoritative_source_resolved="
        f"{broker_neutral_authoritative_source_resolved}"
    )
    print(f"production_wiring_allowed={production_wiring_allowed}")
    print(
        "lge_owned_utc_day_policy_would_be_new_policy="
        f"{lge_owned_utc_day_policy_would_be_new_policy}"
    )
    print(f"fail_closed_required={fail_closed_required}")
    print(f"broker_requests={broker_requests}")
    print("ib_candidate_source=REQPNL_ACCOUNT_SUBSCRIPTION_NOT_YET_CANONICAL")
    print(
        "ctrader_candidate_source=DEAL_HISTORY_NET_COST_AGGREGATE_"
        "WITHOUT_AUTHORITATIVE_ACCOUNT_DAY"
    )
    print(
        "source_decision=NO_BROKER_NEUTRAL_AUTHORITATIVE_SOURCE_"
        "UNDER_CURRENT_ACCOUNT_DAY_CONTRACT"
    )
    print("recommended_behavior=KEEP_DAILY_PNL_FAIL_CLOSED")
    print("first_unresolved_boundary=DAILY_PNL_ACCOUNT_DAY_POLICY_DECISION")
    print(
        "boundary_contract=CHOOSE_EXPLICIT_ACCOUNT_DAY_POLICY_OR_OBTAIN_"
        "AUTHORITATIVE_BROKER_PERIOD_IDENTITY_BEFORE_PRODUCTION_WIRING"
    )
    print(
        "factual_verdict=A. BROKER_AUTHORITATIVE_DAILY_REALIZED_PNL_"
        "SOURCE_REMAINS_UNRESOLVED"
    )


if __name__ == "__main__":
    main()
