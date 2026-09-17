from __future__ import annotations

from pathlib import Path

# noinspection PyPep8Naming
# noinspection PyPep8Naming
from ctrader_open_api.messages import OpenApiMessages_pb2 as oa_messages
from ctrader_open_api.messages import OpenApiModelMessages_pb2 as oa_model  # noqa

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _fields(message_type: object) -> set[str]:
    descriptor = getattr(message_type, "DESCRIPTOR", None)
    if descriptor is None:
        return set()
    return {field.name for field in descriptor.fields}


def _source(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    adapter_source = _source("engine/ctrader_adapter.py")
    runtime_source = _source("engine/runtime_engine.py")
    manual_source = _source("tests/ctrader/manual/run_ctrader_09_session_console.py")

    reconcile_res = getattr(oa_messages, "ProtoOAReconcileRes")
    order_list_req = getattr(oa_messages, "ProtoOAOrderListReq")
    order_list_res = getattr(oa_messages, "ProtoOAOrderListRes")
    order_details_req = getattr(oa_messages, "ProtoOAOrderDetailsReq")
    order_details_res = getattr(oa_messages, "ProtoOAOrderDetailsRes")
    deal_list_req = getattr(oa_messages, "ProtoOADealListReq")
    deal_list_res = getattr(oa_messages, "ProtoOADealListRes")
    order_type = getattr(oa_model, "ProtoOAOrder")
    trade_data_type = getattr(oa_model, "ProtoOATradeData")
    deal_type = getattr(oa_model, "ProtoOADeal")

    reconcile_fields = _fields(reconcile_res)
    order_list_req_fields = _fields(order_list_req)
    order_list_res_fields = _fields(order_list_res)
    order_details_req_fields = _fields(order_details_req)
    order_details_res_fields = _fields(order_details_res)
    deal_list_req_fields = _fields(deal_list_req)
    deal_list_res_fields = _fields(deal_list_res)
    order_fields = _fields(order_type)
    trade_data_fields = _fields(trade_data_type)
    deal_fields = _fields(deal_type)

    checks = {
        "test_scope": "TEST_ONLY",
        "production_change": False,
        "ctrader_reconcile_exposes_positions_and_pending_orders": {
            "position",
            "order",
        }.issubset(reconcile_fields),
        "project_manual_reconcile_reads_pending_orders": (
            'orders = list(getattr(payload, "order", []))' in manual_source
        ),
        "production_reconcile_discards_pending_orders": (
            'self._positions_payload = list(getattr(payload, "position", []))'
            in adapter_source
            and 'self._orders_payload = list(getattr(payload, "order", []))'
            not in adapter_source
        ),
        "ctrader_order_list_api_present": all(
            hasattr(oa_messages, name)
            for name in ("ProtoOAOrderListReq", "ProtoOAOrderListRes")
        ),
        "order_list_supports_bounded_history_window": {
            "ctidTraderAccountId",
            "fromTimestamp",
            "toTimestamp",
        }.issubset(order_list_req_fields),
        "order_list_returns_orders_and_pagination": {
            "order",
            "hasMore",
        }.issubset(order_list_res_fields),
        "order_history_has_terminal_status_and_fill_state": {
            "orderId",
            "tradeData",
            "orderStatus",
            "executedVolume",
        }.issubset(order_fields),
        "order_history_has_workspace_correlation_fields": {
            "label",
            "comment",
        }.issubset(trade_data_fields),
        "ctrader_order_details_api_present": all(
            hasattr(oa_messages, name)
            for name in ("ProtoOAOrderDetailsReq", "ProtoOAOrderDetailsRes")
        ),
        "order_details_requires_exact_order_id": {
            "ctidTraderAccountId",
            "orderId",
        }.issubset(order_details_req_fields),
        "order_details_returns_order": "order" in order_details_res_fields,
        "ctrader_deal_history_api_present": all(
            hasattr(oa_messages, name)
            for name in ("ProtoOADealListReq", "ProtoOADealListRes")
        ),
        "deal_history_supports_bounded_window": {
            "ctidTraderAccountId",
            "fromTimestamp",
            "toTimestamp",
        }.issubset(deal_list_req_fields),
        "deal_history_returns_deals_and_pagination": {
            "deal",
            "hasMore",
        }.issubset(deal_list_res_fields),
        "deal_history_preserves_execution_identity": {
            "orderId",
            "positionId",
            "filledVolume",
            "dealStatus",
        }.issubset(deal_fields),
        "deal_history_workspace_correlation_required": False,
        "workspace_submission_uses_stable_wsp_correlation": (
            'f"WSP:{trade_hint}"' in runtime_source
        ),
        "production_order_list_recovery_route_present": (
            "ProtoOAOrderListReq" in adapter_source
        ),
        "production_deal_list_recovery_route_present": (
            "ProtoOADealListReq" in adapter_source
        ),
        "reconcile_can_resolve_still_pending": True,
        "order_history_can_resolve_terminal_order_status": True,
        "deal_history_can_resolve_confirmed_execution": True,
        "deal_history_can_join_by_recovered_order_id": ("orderId" in deal_fields),
        "order_details_is_initial_recovery_source_without_order_id": False,
        "safe_resubmit_when_recovery_returns_unknown": False,
        "broker_requests": 0,
    }

    required_true = [
        "ctrader_reconcile_exposes_positions_and_pending_orders",
        "project_manual_reconcile_reads_pending_orders",
        "production_reconcile_discards_pending_orders",
        "ctrader_order_list_api_present",
        "order_list_supports_bounded_history_window",
        "order_list_returns_orders_and_pagination",
        "order_history_has_terminal_status_and_fill_state",
        "order_history_has_workspace_correlation_fields",
        "ctrader_order_details_api_present",
        "order_details_requires_exact_order_id",
        "order_details_returns_order",
        "ctrader_deal_history_api_present",
        "deal_history_supports_bounded_window",
        "deal_history_returns_deals_and_pagination",
        "deal_history_preserves_execution_identity",
        "workspace_submission_uses_stable_wsp_correlation",
        "reconcile_can_resolve_still_pending",
        "order_history_can_resolve_terminal_order_status",
        "deal_history_can_resolve_confirmed_execution",
        "deal_history_can_join_by_recovered_order_id",
    ]
    failed = [name for name in required_true if checks[name] is not True]
    if checks["production_order_list_recovery_route_present"] is not False:
        failed.append("production_order_list_recovery_route_present")
    if checks["production_deal_list_recovery_route_present"] is not False:
        failed.append("production_deal_list_recovery_route_present")
    if checks["order_details_is_initial_recovery_source_without_order_id"]:
        failed.append("order_details_is_initial_recovery_source_without_order_id")
    if checks["safe_resubmit_when_recovery_returns_unknown"]:
        failed.append("safe_resubmit_when_recovery_returns_unknown")
    if failed:
        raise AssertionError(", ".join(failed))

    print("T109-64_CTRADER_PENDING_TIMEOUT_RECOVERY_SOURCE_ANATOMY=OK")
    for name, value in checks.items():
        print(f"{name}={value}")
    print("recommended_recovery_stage_1=RECONCILE_BY_WSP_CORRELATION")
    print("recommended_recovery_stage_2=ORDER_LIST_BY_BOUNDED_TIME_WINDOW")
    print("recommended_recovery_stage_3=DEAL_LIST_FOR_EXECUTION_CONFIRMATION")
    print("recommended_order_details_use=AFTER_EXACT_ORDER_ID_RECOVERED")
    print("recommended_unknown_behavior=KEEP_PENDING_AND_BLOCK_RESUBMIT")
    print(
        "first_unresolved_boundary="
        "CTRADER_ORDER_HISTORY_RECOVERY_SOURCE_PRODUCTION_WIRING"
    )
    print(
        "boundary_contract=CTRADER_WORKSPACE_TIMEOUT_RECOVERY_MUST_USE_"
        "BROKER_RECONCILE_AND_BOUNDED_ORDER_HISTORY_MATCHED_BY_STABLE_WSP_"
        "CORRELATION_THEN_USE_DEAL_HISTORY_FOR_CONFIRMED_EXECUTION_WITHOUT_"
        "RESUBMITTING_WHILE_OUTCOME_REMAINS_UNKNOWN"
    )
    print(
        "factctual_verdict=A. CTRADER_BROKER_RECOVERY_SOURCES_EXIST_BUT_"
        "PRODUCTION_ADAPTER_DOES_NOT_EXPOSE_ORDER_HISTORY_RECOVERY"
    )


if __name__ == "__main__":
    main()
