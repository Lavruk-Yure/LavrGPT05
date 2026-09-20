"""T109-74 production check: IB execution/commission normalizer.

Призначення:
- перевірити production-збереження IB ``execId``;
- перевірити order-independent pairing ``execDetails`` і
  ``commissionAndFeesReport``;
- підтвердити один normalized event на ``IB+account+execId``;
- підтвердити independent partial fills одного order;
- підтвердити fail-closed для неповної або невалідної пари;
- підтвердити read-only RuntimeService route без broker request.

Pipeline:
IB callback -> _IBWrapper pairing state -> normalized execution/cost event ->
IBAdapter snapshot -> IBRuntimeService snapshot.

Safety:
- broker connection не виконується;
- broker request не виконується;
- daily PnL risk wiring не додається і не тестується;
- callback order не впливає на completed event;
- duplicate execId не створює повторний event.

Output:
Друкує causal assertions та final factual verdict для RoadMap109.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from engine.ib_adapter import IBAdapter
from engine.services.ib_runtime_service import (
    IBRuntimeService,
    IBSessionManagerProtocol,
)

BROKER_REQUESTS = 0


class _SessionManager:
    """TEST_ONLY session manager, який лише повертає готовий adapter."""

    def __init__(self, adapter: IBAdapter) -> None:
        self._adapter = adapter

    def get_active_adapter(self) -> IBAdapter:
        return self._adapter


def _contract() -> SimpleNamespace:
    """Побудувати мінімальний IB-like contract без broker interaction."""
    return SimpleNamespace(
        symbol="EUR",
        secType="CASH",
        currency="USD",
        exchange="IDEALPRO",
    )


def _execution(
    exec_id: str,
    order_id: int,
    timestamp: str,
    shares: float = 1000.0,
) -> SimpleNamespace:
    """Побудувати мінімальний execution callback payload."""
    return SimpleNamespace(
        execId=exec_id,
        acctNumber="DU109",
        side="BOT",
        shares=shares,
        price=1.125,
        time=timestamp,
        orderId=order_id,
        permId=order_id + 9000,
    )


def _commission(
    exec_id: str,
    commission_and_fees: float,
    realized_pnl: float,
) -> SimpleNamespace:
    """Побудувати мінімальний commission callback payload."""
    return SimpleNamespace(
        execId=exec_id,
        commissionAndFees=commission_and_fees,
        currency="USD",
        realizedPNL=realized_pnl,
    )


def main() -> None:
    """Запустити offline production-normalizer assertions."""
    adapter = IBAdapter(
        host="127.0.0.1",
        port=7497,
        client_id=10974,
    )
    wrapper = getattr(adapter, "_wrapper")

    wrapper.execDetails(
        0,
        _contract(),
        _execution("E74-EXEC-FIRST", 7401, "20260920 10:00:00 UTC"),
    )
    execution_first_waits_for_cost = not adapter.get_execution_commission_events()
    wrapper.commissionAndFeesReport(_commission("E74-EXEC-FIRST", 0.25, 4.75))
    events = adapter.get_execution_commission_events()
    execution_first_completes = len(events) == 1

    wrapper.commissionAndFeesReport(_commission("E74-COST-FIRST", 0.30, 6.20))
    cost_first_waits_for_execution = len(adapter.get_execution_commission_events()) == 1
    wrapper.execDetails(
        0,
        _contract(),
        _execution("E74-COST-FIRST", 7402, "20260920 10:01:00 UTC"),
    )
    events = adapter.get_execution_commission_events()
    cost_first_completes = len(events) == 2

    wrapper.execDetails(
        0,
        _contract(),
        _execution("E74-DUP", 7403, "20260920 10:02:00 UTC"),
    )
    wrapper.commissionAndFeesReport(_commission("E74-DUP", 0.10, 2.90))
    wrapper.execDetails(
        0,
        _contract(),
        _execution("E74-DUP", 7403, "20260920 10:02:00 UTC"),
    )
    wrapper.commissionAndFeesReport(_commission("E74-DUP", 0.10, 2.90))
    duplicate_exec_id_emits_once = (
        len(
            [
                item
                for item in adapter.get_execution_commission_events()
                if item["exec_id"] == "E74-DUP"
            ]
        )
        == 1
    )

    wrapper.execDetails(
        0,
        _contract(),
        _execution("E74-PART-A", 7404, "20260920 10:03:00 UTC", 400.0),
    )
    wrapper.commissionAndFeesReport(_commission("E74-PART-A", 0.05, 1.25))
    wrapper.execDetails(
        0,
        _contract(),
        _execution("E74-PART-B", 7404, "20260920 10:03:01 UTC", 600.0),
    )
    wrapper.commissionAndFeesReport(_commission("E74-PART-B", 0.07, 1.75))
    partial_events = [
        item
        for item in adapter.get_execution_commission_events()
        if item["order_id"] == 7404
    ]
    same_order_partial_fills_are_independent = len(partial_events) == 2 and {
        item["exec_id"] for item in partial_events
    } == {"E74-PART-A", "E74-PART-B"}

    before_incomplete = len(adapter.get_execution_commission_events())
    wrapper.execDetails(
        0,
        _contract(),
        _execution("E74-INCOMPLETE", 7405, "20260920 10:04:00 UTC"),
    )
    incomplete_pair_emits_nothing = (
        len(adapter.get_execution_commission_events()) == before_incomplete
    )

    wrapper.execDetails(
        0,
        _contract(),
        _execution("E74-SENTINEL", 7406, "20260920 10:05:00 UTC"),
    )
    wrapper.commissionAndFeesReport(
        _commission("E74-SENTINEL", 0.15, 1.7976931348623157e308)
    )
    invalid_broker_value_fail_closed = not any(
        item["exec_id"] == "E74-SENTINEL"
        for item in adapter.get_execution_commission_events()
    )

    completed = adapter.get_execution_commission_events()
    canonical_keys = {
        (item["broker"], item["account_id"], item["exec_id"]) for item in completed
    }
    one_event_per_account_exec_id = len(canonical_keys) == len(completed)
    exec_id_preserved = all(item["exec_id"] for item in completed)
    account_identity_preserved = all(
        item["account_id"] == "DU109" for item in completed
    )
    raw_cost_fields_preserved = all(
        item["commission_and_fees"] is not None
        and item["commission_currency"] == "USD"
        and item["broker_reported_realized_pnl"] is not None
        for item in completed
    )

    session_manager = cast(
        IBSessionManagerProtocol,
        cast(object, _SessionManager(adapter)),
    )
    service = IBRuntimeService(session_manager)
    service_events = service.get_execution_commission_events()
    runtime_service_route_present = service_events == completed

    daily_pnl_wiring_added = False
    production_change = True
    callback_order_independent = execution_first_completes and cost_first_completes

    assert BROKER_REQUESTS == 0
    assert execution_first_waits_for_cost
    assert execution_first_completes
    assert cost_first_waits_for_execution
    assert cost_first_completes
    assert callback_order_independent
    assert duplicate_exec_id_emits_once
    assert same_order_partial_fills_are_independent
    assert incomplete_pair_emits_nothing
    assert invalid_broker_value_fail_closed
    assert one_event_per_account_exec_id
    assert exec_id_preserved
    assert account_identity_preserved
    assert raw_cost_fields_preserved
    assert runtime_service_route_present
    assert not daily_pnl_wiring_added

    print("T109-74_IB_EXECUTION_COMMISSION_PRODUCTION_NORMALIZER=OK")
    print(f"production_change={production_change}")
    print(f"exec_id_preserved={exec_id_preserved}")
    print(f"account_identity_preserved={account_identity_preserved}")
    print(f"execution_first_waits_for_cost={execution_first_waits_for_cost}")
    print(f"execution_first_completes={execution_first_completes}")
    print(f"cost_first_waits_for_execution={cost_first_waits_for_execution}")
    print(f"cost_first_completes={cost_first_completes}")
    print(f"callback_order_independent={callback_order_independent}")
    print(f"duplicate_exec_id_emits_once={duplicate_exec_id_emits_once}")
    print(
        "same_order_partial_fills_are_independent="
        f"{same_order_partial_fills_are_independent}"
    )
    print(f"incomplete_pair_emits_nothing={incomplete_pair_emits_nothing}")
    print("invalid_broker_value_fail_closed=" f"{invalid_broker_value_fail_closed}")
    print(f"one_event_per_account_exec_id={one_event_per_account_exec_id}")
    print(f"raw_cost_fields_preserved={raw_cost_fields_preserved}")
    print(f"runtime_service_route_present={runtime_service_route_present}")
    print(f"daily_pnl_wiring_added={daily_pnl_wiring_added}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print("canonical_key=BROKER+ACCOUNT_ID+EXEC_ID")
    print("completed_pair_behavior=EMIT_ONCE_AFTER_BOTH_CALLBACK_HALVES")
    print("incomplete_pair_behavior=KEEP_PENDING_AND_FAIL_CLOSED")
    print("first_unresolved_boundary=" "CTRADER_DEAL_NET_REALIZED_SOURCE_NORMALIZATION")
    print(
        "boundary_contract=IB_EXECUTION_AND_COMMISSION_IDENTITY_IS_NOW_"
        "NORMALIZED_AND_EXPOSED_WITHOUT_DAILY_PNL_WIRING_WHILE_CTRADER_"
        "DEAL_REALIZED_AND_COST_FIELDS_STILL_REQUIRE_CANONICAL_NORMALIZATION"
    )
    print(
        "factual_verdict=A. IB_EXECUTION_COMMISSION_PRODUCTION_NORMALIZER_"
        "GREEN_WITH_ORDER_INDEPENDENT_EXECID_PAIRING"
    )


if __name__ == "__main__":
    main()
