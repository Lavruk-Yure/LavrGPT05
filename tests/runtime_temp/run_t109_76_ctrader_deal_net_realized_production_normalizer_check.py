"""T109-76 production cTrader Deal net-realized normalizer check.

Перевіряє offline:
- closed deal -> один canonical net-realized event;
- moneyDigits scaling і signed cost aggregation;
- dedup за account + dealId;
- partial fills одного order лишаються окремими deals;
- open deal не входить у daily realized;
- incomplete closed deal fail-closed;
- hasMore fail-closed;
- runtime service route;
- daily PnL wiring ще не додається;
- broker_requests=0.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from engine.ctrader_adapter import CTraderAdapter, CTraderRuntimeConfig
from engine.services.ctrader_runtime_service import (
    CTraderRuntimeService,
    CTraderSessionManagerProtocol,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BROKER_REQUESTS = 0


class _Proto:
    """Мінімальний protobuf-like payload з підтримкою HasField."""

    def __init__(self, *, present: set[str], **values: object) -> None:
        self._present = set(present)
        for name, value in values.items():
            setattr(self, name, value)

    def HasField(self, field_name: str) -> bool:  # noqa
        """Повернути explicit field presence для TEST_ONLY payload."""
        return field_name in self._present


class _OfflineAdapter(CTraderAdapter):
    """cTrader adapter без broker I/O з підставленим deal history."""

    def __init__(self, history: dict[str, object]) -> None:
        super().__init__(
            CTraderRuntimeConfig(
                client_id="TEST_ONLY",
                client_secret="TEST_ONLY",
                access_token="TEST_ONLY",
                ctid_trader_account_id=900001,
                account_mode="DEMO",
            )
        )
        self.history = history

    def get_deal_history(
        self,
        start_utc: datetime,
        end_utc: datetime,
    ) -> dict[str, object]:
        """Повернути TEST_ONLY history без broker request."""
        _ = start_utc, end_utc
        return dict(self.history)


class _SessionManager:
    """Мінімальний TEST_ONLY session manager для runtime service route."""

    def __init__(self, adapter: CTraderAdapter) -> None:
        self.adapter = adapter

    def get_active_adapter(self) -> CTraderAdapter:
        """Повернути offline adapter."""
        return self.adapter


def _close_detail(
    *,
    gross_profit: int = 1250,
    swap: int = -50,
    commission: int = -30,
    money_digits: int = 2,
    pnl_conversion_fee: int = -20,
    missing: str = "",
) -> _Proto:
    """Побудувати TEST_ONLY closePositionDetail."""
    values = {
        "grossProfit": gross_profit,
        "swap": swap,
        "commission": commission,
        "moneyDigits": money_digits,
        "pnlConversionFee": pnl_conversion_fee,
    }
    present = set(values)
    if missing:
        present.discard(missing)
    return _Proto(present=present, **values)


def _deal(
    deal_id: int,
    *,
    order_id: int = 7001,
    position_id: int = 8001,
    timestamp: int = 1_789_945_200_000,
    close_detail: _Proto | None = None,
    closed: bool = True,
) -> _Proto:
    """Побудувати TEST_ONLY ProtoOADeal-like payload."""
    values: dict[str, object] = {
        "dealId": deal_id,
        "orderId": order_id,
        "positionId": position_id,
        "filledVolume": 3_000_000,
        "executionTimestamp": timestamp,
    }
    present = set(values)
    if closed:
        values["closePositionDetail"] = close_detail or _close_detail()
        present.add("closePositionDetail")
    return _Proto(present=present, **values)


def main() -> None:
    """Запустити offline production normalizer assertions."""
    start_utc = datetime(2026, 9, 21, tzinfo=UTC)
    end_utc = start_utc + timedelta(days=1)

    deal_a = _deal(75001)
    deal_a_duplicate = _deal(75001)
    deal_b = _deal(75002, order_id=7001, position_id=8001)
    open_deal = _deal(75003, closed=False)

    adapter = _OfflineAdapter(
        {
            "success": True,
            "deals": [deal_a, deal_a_duplicate, deal_b, open_deal],
            "has_more": False,
            "failure_reason": "",
        }
    )
    result = adapter.get_deal_net_realized_events(start_utc, end_utc)
    events = cast(list[dict[str, object]], result["events"])

    normalization_success = bool(result["success"])
    duplicate_deal_id_emits_once = len(events) == 2
    event_ids = {str(item["deal_id"]) for item in events}
    same_order_partial_deals_independent = event_ids == {"75001", "75002"}
    open_deal_ignored = "75003" not in event_ids

    first = events[0]
    canonical_key_preserved = (
        first["broker"] == "CTRADER"
        and first["account_id"] == "900001"
        and first["deal_id"] == "75001"
    )
    identity_preserved = (
        first["order_id"] == "7001"
        and first["position_id"] == "8001"
        and first["execution_timestamp"] == 1_789_945_200_000
    )
    raw_volume_preserved = first["filled_volume_raw"] == 3_000_000
    money_digits_preserved = first["money_digits"] == 2

    gross_realized_pnl = float(cast(float, first["gross_realized_pnl"]))
    swap_pnl_effect = float(cast(float, first["swap_pnl_effect"]))
    commission_pnl_effect = float(cast(float, first["commission_pnl_effect"]))
    pnl_conversion_fee_pnl_effect = float(
        cast(float, first["pnl_conversion_fee_pnl_effect"])
    )
    net_realized_pnl = float(cast(float, first["net_realized_pnl"]))

    signed_components_preserved = (
        abs(gross_realized_pnl - 12.50) < 1e-12
        and abs(swap_pnl_effect + 0.50) < 1e-12
        and abs(commission_pnl_effect + 0.30) < 1e-12
        and abs(pnl_conversion_fee_pnl_effect + 0.20) < 1e-12
    )

    net_realized_correct = abs(net_realized_pnl - 11.50) < 1e-12

    incomplete_adapter = _OfflineAdapter(
        {
            "success": True,
            "deals": [
                _deal(
                    76001,
                    close_detail=_close_detail(missing="commission"),
                )
            ],
            "has_more": False,
            "failure_reason": "",
        }
    )
    incomplete_result = incomplete_adapter.get_deal_net_realized_events(
        start_utc,
        end_utc,
    )
    incomplete_closed_deal_fail_closed = (
        not bool(incomplete_result["success"]) and incomplete_result["events"] == []
    )

    paginated_adapter = _OfflineAdapter(
        {
            "success": True,
            "deals": [deal_a],
            "has_more": True,
            "failure_reason": "",
        }
    )
    paginated_result = paginated_adapter.get_deal_net_realized_events(
        start_utc,
        end_utc,
    )
    incomplete_pagination_fail_closed = (
        not bool(paginated_result["success"])
        and paginated_result["events"] == []
        and bool(paginated_result["has_more"])
    )

    manager = cast(
        CTraderSessionManagerProtocol,
        cast(object, _SessionManager(adapter)),
    )
    service = CTraderRuntimeService(manager)
    service_result = service.get_deal_net_realized_events(start_utc, end_utc)
    service_route_present = service_result == result

    engine_source = (PROJECT_ROOT / "engine" / "runtime_engine.py").read_text(
        encoding="utf-8"
    )
    controller_source = (
        PROJECT_ROOT / "core" / "algorithm_workspace_controller.py"
    ).read_text(encoding="utf-8")
    daily_pnl_wiring_added = "get_deal_net_realized_events(" in (
        engine_source + controller_source
    )

    checks = {
        "production_change": True,
        "normalization_success": normalization_success,
        "canonical_key_preserved": canonical_key_preserved,
        "identity_preserved": identity_preserved,
        "raw_volume_preserved": raw_volume_preserved,
        "money_digits_preserved": money_digits_preserved,
        "signed_components_preserved": signed_components_preserved,
        "net_realized_correct": net_realized_correct,
        "duplicate_deal_id_emits_once": duplicate_deal_id_emits_once,
        "same_order_partial_deals_independent": same_order_partial_deals_independent,
        "open_deal_ignored": open_deal_ignored,
        "incomplete_closed_deal_fail_closed": incomplete_closed_deal_fail_closed,
        "incomplete_pagination_fail_closed": incomplete_pagination_fail_closed,
        "service_route_present": service_route_present,
        "daily_pnl_wiring_added": daily_pnl_wiring_added,
        "broker_requests": BROKER_REQUESTS,
    }

    assert all(
        value is True
        for name, value in checks.items()
        if name
        not in {
            "daily_pnl_wiring_added",
            "broker_requests",
        }
    )
    assert not daily_pnl_wiring_added
    assert BROKER_REQUESTS == 0

    print("T109-76_CTRADER_DEAL_NET_REALIZED_PRODUCTION_NORMALIZER=OK")
    for name, value in checks.items():
        print(f"{name}={value}")
    print("canonical_key=BROKER+ACCOUNT_ID+DEAL_ID")
    print(
        "net_formula=grossProfit+swap+commission+pnlConversionFee_"
        "AFTER_moneyDigits_scaling"
    )
    print("open_deal_behavior=DO_NOT_ENTER_DAILY_NET_REALIZED")
    print("incomplete_source_behavior=FAIL_CLOSED")
    print("first_unresolved_boundary=BROKER_DAILY_PNL_EVENT_AGGREGATION_CONTRACT")
    print(
        "boundary_contract=IB_AND_CTRADER_NOW_EXPOSE_NORMALIZED_CAUSAL_"
        "REALIZED_EXECUTION_COST_EVIDENCE_BUT_BROKER_NEUTRAL_ACCOUNT_DAY_"
        "AGGREGATION_AND_RISK_SNAPSHOT_WIRING_REMAIN_UNIMPLEMENTED"
    )
    print(
        "factual_verdict=A. CTRADER_DEAL_NET_REALIZED_PRODUCTION_"
        "NORMALIZER_GREEN_WITH_ACCOUNT_DEAL_ID_DEDUP_AND_FAIL_CLOSED_"
        "INCOMPLETE_SOURCES"
    )


if __name__ == "__main__":
    main()
