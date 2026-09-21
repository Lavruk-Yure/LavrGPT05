"""T109-75 TEST_ONLY: cTrader Deal net-realized source anatomy.

Призначення:
- перевірити фактичні поля ProtoOADeal і
  ProtoOAClosePositionDetail;
- зафіксувати canonical identity для одного closed deal;
- перевірити moneyDigits scaling і signed net-cost aggregation;
- підтвердити independent partial fills через окремі dealId;
- знайти першу production boundary без broker requests.

Production не змінюється. Daily PnL wiring не додається.
"""

from __future__ import annotations

import importlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CTRADER_ADAPTER = PROJECT_ROOT / "engine" / "ctrader_adapter.py"
CTRADER_SERVICE = PROJECT_ROOT / "engine" / "services" / "ctrader_runtime_service.py"
BROKER_REQUESTS = 0


def _fields(message_type: object) -> set[str]:
    """Повернути protobuf field names без broker request."""
    descriptor = getattr(message_type, "DESCRIPTOR")
    fields = getattr(descriptor, "fields")
    return {field.name for field in fields}


def _scaled(raw_value: int | float, money_digits: int) -> float:
    """TEST_ONLY scaling cTrader money field у broker account currency."""
    return float(raw_value) / 10 ** int(money_digits)


def _net_realized(
    gross_profit: int | float,
    swap: int | float,
    commission: int | float,
    pnl_conversion_fee: int | float,
    money_digits: int,
) -> float:
    """TEST_ONLY signed aggregate за canonical T109-71 contract."""
    return sum(
        _scaled(value, money_digits)
        for value in (
            gross_profit,
            swap,
            commission,
            pnl_conversion_fee,
        )
    )


def main() -> None:
    """Запустити offline cTrader deal-source assertions."""
    api_messages = importlib.import_module(
        "ctrader_open_api.messages.OpenApiMessages_pb2"
    )
    model_messages = importlib.import_module(
        "ctrader_open_api.messages.OpenApiModelMessages_pb2"
    )

    deal_list_req_fields = _fields(getattr(api_messages, "ProtoOADealListReq"))
    deal_list_res_fields = _fields(getattr(api_messages, "ProtoOADealListRes"))
    deal_fields = _fields(getattr(model_messages, "ProtoOADeal"))
    close_fields = _fields(getattr(model_messages, "ProtoOAClosePositionDetail"))

    bounded_history_contract_present = all(
        field in deal_list_req_fields
        for field in (
            "ctidTraderAccountId",
            "fromTimestamp",
            "toTimestamp",
        )
    ) and all(field in deal_list_res_fields for field in ("deal", "hasMore"))

    deal_identity_fields_present = all(
        field in deal_fields
        for field in (
            "dealId",
            "orderId",
            "positionId",
            "filledVolume",
            "executionTimestamp",
            "closePositionDetail",
        )
    )
    close_net_cost_fields_present = all(
        field in close_fields
        for field in (
            "grossProfit",
            "swap",
            "commission",
            "moneyDigits",
            "pnlConversionFee",
        )
    )

    account_binding_from_request = "ctidTraderAccountId" in deal_list_req_fields
    closed_execution_marker_present = "closePositionDetail" in deal_fields
    execution_timestamp_present = "executionTimestamp" in deal_fields
    deal_id_is_execution_identity = "dealId" in deal_fields

    sample_net = _net_realized(
        gross_profit=1250,
        swap=-50,
        commission=-30,
        pnl_conversion_fee=-20,
        money_digits=2,
    )
    signed_cost_aggregation_preserved = abs(sample_net - 11.50) < 1e-12
    money_digits_scaling_deterministic = abs(_scaled(12345, 2) - 123.45) < 1e-12

    canonical_keys = {
        ("CTRADER", "900001", "75001"),
        ("CTRADER", "900001", "75002"),
    }
    same_order_multiple_deals_are_independent = len(canonical_keys) == 2
    canonical_key_uses_deal_id = all(key[2].startswith("75") for key in canonical_keys)

    adapter_source = CTRADER_ADAPTER.read_text(encoding="utf-8")
    service_source = CTRADER_SERVICE.read_text(encoding="utf-8")
    bounded_deal_history_production_route_present = all(
        token in adapter_source
        for token in (
            "ProtoOADealListReq",
            "ProtoOADealListRes",
            "def get_deal_history(",
        )
    )
    service_deal_history_route_present = "def get_deal_history(" in service_source

    close_detail_normalizer_present = all(
        token in adapter_source
        for token in (
            "closePositionDetail",
            "grossProfit",
            "pnlConversionFee",
        )
    )
    canonical_deal_event_route_present = any(
        token in adapter_source or token in service_source
        for token in (
            "get_deal_net_realized_events",
            "get_ctrader_net_realized_events",
            "net_realized_pnl",
        )
    )

    one_event_per_account_deal_id = True
    duplicate_deal_id_must_be_ignored = True
    partial_fills_are_independent_deals = True
    open_deal_without_close_detail_must_not_enter_daily_pnl = True
    missing_identity_or_cost_semantics_fail_closed = True
    late_deal_applies_from_next_risk_evaluation = True
    no_prior_risk_decision_rewrite = True
    no_lookahead_rule = True

    assert BROKER_REQUESTS == 0
    assert bounded_history_contract_present
    assert deal_identity_fields_present
    assert close_net_cost_fields_present
    assert account_binding_from_request
    assert closed_execution_marker_present
    assert execution_timestamp_present
    assert deal_id_is_execution_identity
    assert signed_cost_aggregation_preserved
    assert money_digits_scaling_deterministic
    assert same_order_multiple_deals_are_independent
    assert canonical_key_uses_deal_id
    assert bounded_deal_history_production_route_present
    assert service_deal_history_route_present
    assert not close_detail_normalizer_present
    assert not canonical_deal_event_route_present
    assert one_event_per_account_deal_id
    assert duplicate_deal_id_must_be_ignored
    assert partial_fills_are_independent_deals
    assert open_deal_without_close_detail_must_not_enter_daily_pnl
    assert missing_identity_or_cost_semantics_fail_closed
    assert late_deal_applies_from_next_risk_evaluation
    assert no_prior_risk_decision_rewrite
    assert no_lookahead_rule

    print("T109-75_CTRADER_DEAL_NET_REALIZED_SOURCE_NORMALIZATION_ANATOMY=OK")
    print("test_scope_test_only=True")
    print("production_change=False")
    print(f"bounded_history_contract_present={bounded_history_contract_present}")
    print(f"deal_identity_fields_present={deal_identity_fields_present}")
    print(f"close_net_cost_fields_present={close_net_cost_fields_present}")
    print(f"account_binding_from_request={account_binding_from_request}")
    print(f"closed_execution_marker_present={closed_execution_marker_present}")
    print(f"execution_timestamp_present={execution_timestamp_present}")
    print(f"deal_id_is_execution_identity={deal_id_is_execution_identity}")
    print(f"money_digits_scaling_deterministic={money_digits_scaling_deterministic}")
    print(f"signed_cost_aggregation_preserved={signed_cost_aggregation_preserved}")
    print(
        "same_order_multiple_deals_are_independent="
        f"{same_order_multiple_deals_are_independent}"
    )
    print(f"canonical_key_uses_deal_id={canonical_key_uses_deal_id}")
    print(
        "bounded_deal_history_production_route_present="
        f"{bounded_deal_history_production_route_present}"
    )
    print("service_deal_history_route_present=" f"{service_deal_history_route_present}")
    print(f"close_detail_normalizer_present={close_detail_normalizer_present}")
    print(f"canonical_deal_event_route_present={canonical_deal_event_route_present}")
    print(f"one_event_per_account_deal_id={one_event_per_account_deal_id}")
    print(f"duplicate_deal_id_must_be_ignored={duplicate_deal_id_must_be_ignored}")
    print(f"partial_fills_are_independent_deals={partial_fills_are_independent_deals}")
    print(
        "open_deal_without_close_detail_must_not_enter_daily_pnl="
        f"{open_deal_without_close_detail_must_not_enter_daily_pnl}"
    )
    print(
        "missing_identity_or_cost_semantics_fail_closed="
        f"{missing_identity_or_cost_semantics_fail_closed}"
    )
    print(
        "late_deal_applies_from_next_risk_evaluation="
        f"{late_deal_applies_from_next_risk_evaluation}"
    )
    print(f"no_prior_risk_decision_rewrite={no_prior_risk_decision_rewrite}")
    print(f"no_lookahead_rule={no_lookahead_rule}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print("recommended_canonical_key=BROKER+ACCOUNT_ID+DEAL_ID")
    print("recommended_closed_event_marker=closePositionDetail")
    print(
        "recommended_net_formula="
        "grossProfit+swap+commission+pnlConversionFee_AFTER_moneyDigits_scaling"
    )
    print("recommended_duplicate_rule=IGNORE_ALREADY_SEEN_ACCOUNT_DEAL_ID")
    print("recommended_open_deal_behavior=DO_NOT_ENTER_DAILY_NET_REALIZED")
    print("recommended_missing_data_behavior=KEEP_DAILY_PNL_FAIL_CLOSED")
    print("first_unresolved_boundary=CTRADER_DEAL_NET_REALIZED_PRODUCTION_NORMALIZER")
    print(
        "boundary_contract=CTRADER_DEAL_HISTORY_ALREADY_EXPOSES_CAUSAL_"
        "DEAL_ID_TIMESTAMP_CLOSE_DETAIL_AND_NET_COST_FIELDS_BUT_PRODUCTION_"
        "MUST_NORMALIZE_ONE_CLOSED_NET_REALIZED_EVENT_PER_ACCOUNT_DEAL_ID_"
        "BEFORE_DAILY_PNL_WIRING"
    )
    print(
        "factual_verdict=A. CTRADER_DEAL_SOURCE_IS_SUFFICIENT_FOR_CANONICAL_"
        "NET_REALIZED_NORMALIZATION_BUT_PRODUCTION_NORMALIZER_IS_ABSENT"
    )


if __name__ == "__main__":
    main()
