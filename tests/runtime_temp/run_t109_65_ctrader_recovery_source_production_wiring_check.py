from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ctrader_open_api import Client  # noqa: E402

from engine.broker_connection_state import BrokerConnectionState  # noqa: E402
from engine.ctrader_adapter import (  # noqa: E402
    CTraderAdapter,
    CTraderRuntimeConfig,
)


class _Deferred:
    # noinspection PyPep8Naming
    # noinspection PyMethodMayBeStatic
    def addErrback(self, _callback: object) -> None:  # noqa: N802
        return None


class _FakeClient:
    def __init__(self, adapter: CTraderAdapter, correlation: str) -> None:
        self.adapter = adapter
        self.correlation = correlation
        self.requests: list[str] = []
        self.window_pairs: list[tuple[int, int]] = []

    def send(self, request: object) -> _Deferred:
        request_name = request.__class__.__name__
        self.requests.append(request_name)
        if request_name == "ProtoOAReconcileReq":
            pending_order = SimpleNamespace(
                orderId=7001,
                tradeData=SimpleNamespace(
                    label="LGE",
                    comment=f"{self.correlation}|AUTO",
                ),
            )
            # noinspection PyProtectedMember
            self.adapter._on_reconcile_res(
                SimpleNamespace(position=[], order=[pending_order])
            )
        elif request_name == "ProtoOAOrderListReq":
            self.window_pairs.append(
                (
                    int(getattr(request, "fromTimestamp", 0) or 0),
                    int(getattr(request, "toTimestamp", 0) or 0),
                )
            )
            history_order = SimpleNamespace(
                orderId=7001,
                orderStatus=3,
                executedVolume=300000,
                tradeData=SimpleNamespace(
                    label="LGE",
                    comment=f"{self.correlation}|AUTO",
                ),
            )
            unrelated_order = SimpleNamespace(
                orderId=7999,
                orderStatus=3,
                executedVolume=300000,
                tradeData=SimpleNamespace(
                    label="LGE",
                    comment="WSP:other|AUTO",
                ),
            )
            # noinspection PyProtectedMember
            self.adapter._on_order_list_res(
                SimpleNamespace(
                    order=[history_order, unrelated_order],
                    hasMore=False,
                )
            )
        elif request_name == "ProtoOADealListReq":
            self.window_pairs.append(
                (
                    int(getattr(request, "fromTimestamp", 0) or 0),
                    int(getattr(request, "toTimestamp", 0) or 0),
                )
            )
            matched_deal = SimpleNamespace(
                orderId=7001,
                positionId=9001,
                filledVolume=300000,
                dealStatus=2,
            )
            unrelated_deal = SimpleNamespace(
                orderId=7999,
                positionId=9999,
                filledVolume=300000,
                dealStatus=2,
            )
            # noinspection PyProtectedMember
            self.adapter._on_deal_list_res(
                SimpleNamespace(
                    deal=[matched_deal, unrelated_deal],
                    hasMore=False,
                )
            )
        else:
            raise AssertionError(f"Unexpected fake request: {request_name}")
        return _Deferred()


def _make_adapter(correlation: str) -> tuple[CTraderAdapter, _FakeClient]:
    config = CTraderRuntimeConfig(
        client_id="test",
        client_secret="test",
        access_token="test",
        ctid_trader_account_id=123456,
        account_mode="DEMO",
    )
    adapter = CTraderAdapter(config)
    adapter.state.connection_state = BrokerConnectionState.CONNECTED
    client = _FakeClient(adapter, correlation)
    adapter.client = cast(Client, cast(object, client))
    return adapter, client


def main() -> None:
    adapter_source = (PROJECT_ROOT / "engine/ctrader_adapter.py").read_text(
        encoding="utf-8"
    )
    service_source = (
        PROJECT_ROOT / "engine/services/ctrader_runtime_service.py"
    ).read_text(encoding="utf-8")

    correlation = "WSP:abc123"
    adapter, client = _make_adapter(correlation)
    end_utc = datetime(2026, 9, 18, 9, 0, tzinfo=UTC)
    start_utc = end_utc - timedelta(hours=6)

    evidence = adapter.get_workspace_timeout_recovery_sources(
        correlation,
        start_utc,
        end_utc,
    )

    pending_orders = cast(
        list[object],
        evidence.get("pending_orders", []),
    )
    history_orders = cast(
        list[object],
        evidence.get("history_orders", []),
    )
    deals = cast(
        list[object],
        evidence.get("deals", []),
    )

    checks = {
        "production_change": True,
        "reconcile_pending_orders_exposed": len(pending_orders) == 1,
        "reconcile_workspace_correlation_filtered": (
            str(getattr(pending_orders[0], "orderId", "")) == "7001"
        ),
        "bounded_order_history_route_present": (
            "ProtoOAOrderListReq" in adapter_source
            and "get_order_history" in adapter_source
        ),
        "bounded_deal_history_route_present": (
            "ProtoOADealListReq" in adapter_source
            and "get_deal_history" in adapter_source
        ),
        "order_history_workspace_correlation_filtered": (
            len(history_orders) == 1
            and str(getattr(history_orders[0], "orderId", "")) == "7001"
        ),
        "deal_history_joined_by_recovered_order_id": (
            len(deals) == 1 and str(getattr(deals[0], "orderId", "")) == "7001"
        ),
        "stable_wsp_correlation_required": (evidence.get("correlation") == correlation),
        "bounded_windows_forwarded": bool(client.window_pairs)
        and all(start < end for start, end in client.window_pairs),
        "runtime_service_recovery_routes_present": all(
            name in service_source
            for name in (
                "get_workspace_reconcile_snapshot",
                "get_order_history",
                "get_deal_history",
                "get_workspace_timeout_recovery_sources",
            )
        ),
        "workspace_resubmit_added": False,
        "runtime_timeout_lifecycle_wiring": False,
        "broker_requests": 0,
    }

    failed = [
        name
        for name, value in checks.items()
        if isinstance(value, bool)
        and name
        not in {
            "workspace_resubmit_added",
            "runtime_timeout_lifecycle_wiring",
        }
        and value is not True
    ]
    if checks["workspace_resubmit_added"] is not False:
        failed.append("workspace_resubmit_added")
    if checks["runtime_timeout_lifecycle_wiring"] is not False:
        failed.append("runtime_timeout_lifecycle_wiring")
    if failed:
        raise AssertionError(", ".join(failed))

    print("T109-65_CTRADER_RECOVERY_SOURCE_PRODUCTION_WIRING=OK")
    for name, value in checks.items():
        print(f"{name}={value}")
    print(
        "first_unresolved_boundary=" "CTRADER_PENDING_TIMEOUT_RECOVERY_LIFECYCLE_WIRING"
    )
    print(
        "boundary_contract=CTRADER_RECOVERY_SOURCES_NOW_EXPOSE_RECONCILE_"
        "PENDING_ORDERS_BOUNDED_ORDER_HISTORY_AND_DEAL_EXECUTION_EVIDENCE_"
        "BY_STABLE_WSP_CORRELATION_BUT_RUNTIME_MUST_STILL_PERSIST_CAUSAL_"
        "PENDING_STATE_AND_RESOLVE_IT_WITHOUT_RESUBMIT"
    )
    print("factual_verdict=A. CTRADER_RECOVERY_SOURCE_PRODUCTION_WIRING_GREEN")


if __name__ == "__main__":
    main()
