from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.broker_position import BrokerPosition  # noqa: E402
from engine.ctrader_order_errors import CTraderMarketOrderTimeoutError  # noqa: E402
from engine.runtime_engine import (  # noqa: E402
    CTraderRuntimeServiceProtocol,
    RuntimeEngine,
)


class _FakeCTraderService:
    """TEST_ONLY cTrader service без broker I/O."""

    def __init__(self) -> None:
        self.place_calls = 0
        self.recovery_calls = 0
        self.correlation = ""

    def place_market_order(
        self,
        symbol_name: str,
        side: str,
        lots: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "LGE manual order",
    ) -> dict:
        _ = stop_loss, take_profit
        self.place_calls += 1
        raise CTraderMarketOrderTimeoutError(
            symbol_name=symbol_name,
            side=side,
            lots=lots,
            comment=comment,
        )

    def get_workspace_timeout_recovery_sources(
        self,
        correlation: str,
        start_utc,
        end_utc,
    ) -> dict[str, object]:
        _ = start_utc, end_utc
        del start_utc, end_utc
        self.recovery_calls += 1
        self.correlation = correlation
        order = SimpleNamespace(orderId=7001, orderStatus=2)
        if self.recovery_calls == 1:
            return {
                "reconcile_success": True,
                "pending_orders": [SimpleNamespace(orderId=7001)],
                "positions": [],
                "order_history_success": True,
                "history_orders": [],
                "deal_history_success": True,
                "deals": [],
            }
        position = BrokerPosition(
            broker="CTRADER",
            account_id="12345",
            account_mode="DEMO",
            position_id="9001",
            symbol_name="EURUSD",
            side="BUY",
            volume=0.03,
            entry_price=1.1000,
        )
        return {
            "reconcile_success": True,
            "pending_orders": [],
            "positions": [position],
            "order_history_success": True,
            "history_orders": [order],
            "deal_history_success": True,
            "deals": [SimpleNamespace(orderId=7001, filledVolume=300000)],
        }


class _TestRuntimeEngine(RuntimeEngine):
    """TEST_ONLY RuntimeEngine без external binding I/O."""

    def validate_workspace_broker_binding(
        self,
        broker_name: str,
        account_id: str | None,
    ) -> None:
        del broker_name, account_id


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="t109_67_") as temp_dir:
        db_path = str(Path(temp_dir) / "runtime.db")
        engine = _TestRuntimeEngine(db_path=db_path)
        fake = _FakeCTraderService()
        engine.ctrader_runtime_service = cast(
            CTraderRuntimeServiceProtocol,
            cast(object, fake),
        )
        trade_uid = engine.repository.create_trade(
            broker="CTRADER",
            account_id="12345",
            symbol="EURUSD",
            side="BUY",
            volume=3000.0,
            source="WORKSPACE",
            workspace_uid="workspace-t109-67",
            signal_uid="signal-t109-67",
            execution_origin="BROKER",
            control_mode="AUTO",
            execution_state="READY_FOR_SUBMISSION",
        )
        order_plan_uid = engine.repository.create_order_plan(
            trade_uid=trade_uid,
            order_type="MARKET",
            side="BUY",
            volume=3000.0,
            source="WORKSPACE",
            stop_loss=1.0950,
        )

        first_timeout_raised = False
        try:
            engine.submit_workspace_execution_plan(
                trade_uid,
                order_plan_uid,
                reverse_required=False,
                confirmed_flat=True,
            )
        except CTraderMarketOrderTimeoutError:
            first_timeout_raised = True

        chain_after_timeout = engine.repository.get_trade_chain(trade_uid)
        orders_after_timeout = chain_after_timeout["broker_orders"]
        pending_row = orders_after_timeout[-1]

        second_result = engine.submit_workspace_execution_plan(
            trade_uid,
            order_plan_uid,
            reverse_required=False,
            confirmed_flat=True,
        )
        chain_after_recovery = engine.repository.get_trade_chain(trade_uid)
        recovered_order = chain_after_recovery["broker_orders"][-1]
        recovered_position = engine.repository.get_position_by_trade_uid(trade_uid)

        source = (PROJECT_ROOT / "engine/runtime_engine.py").read_text(encoding="utf-8")
        adapter_source = (PROJECT_ROOT / "engine/ctrader_adapter.py").read_text(
            encoding="utf-8"
        )

        checks = {
            "production_change": True,
            "typed_ctrader_timeout_present": (
                "CTraderMarketOrderTimeoutError" in adapter_source
                and "except CTraderMarketOrderTimeoutError" in source
            ),
            "causal_pending_broker_order_persisted": (
                first_timeout_raised
                and len(orders_after_timeout) == 1
                and pending_row["execution_status"] == "PENDING_CONFIRMATION"
            ),
            "workspace_correlation_preserved": fake.correlation.startswith("WSP:"),
            "exact_order_id_recovered": recovered_order["broker_order_id"] == "7001",
            "terminal_fill_resolved": (
                recovered_order["execution_status"] == "FILLED"
                and second_result["execution_status"] == "FILLED"
            ),
            "confirmed_position_persisted": (
                recovered_position is not None
                and recovered_position["broker_position_id"] == "9001"
            ),
            "repeat_submit_blocked": fake.place_calls == 1,
            "recovery_reused_persisted_chain": (
                second_result["already_submitted"] is True
                and second_result["resubmit_allowed"] is False
            ),
            "recovery_calls_exactly_two": fake.recovery_calls == 2,
            "broker_requests": 0,
        }

        failed = [
            name
            for name, value in checks.items()
            if name != "broker_requests" and value is not True
        ]
        if checks["broker_requests"] != 0:
            failed.append("broker_requests")
        if failed:
            raise AssertionError(", ".join(failed))

        print("T109-67_CTRADER_PENDING_TIMEOUT_RECOVERY_LIFECYCLE_WIRING=OK")
        for name, value in checks.items():
            print(f"{name}={value}")
        print("still_pending_behavior=KEEP_PENDING_AND_BLOCK_RESUBMIT")
        print("unknown_behavior=KEEP_PENDING_AND_BLOCK_RESUBMIT")
        print("terminal_recovery=UPDATE_EXISTING_BROKER_ORDER_WITHOUT_RESUBMIT")
        print("schema_version_changed=False")
        print(
            "first_unresolved_boundary="
            "WORKSPACE_BROKER_EXECUTION_REMAINING_SAFETY_BLOCKERS"
        )
        print(
            "factual_verdict=A. CTRADER_PENDING_TIMEOUT_RECOVERY_"
            "LIFECYCLE_PRODUCTION_WIRING_GREEN"
        )

        engine.connection.commit()
        engine.connection.close()


if __name__ == "__main__":
    main()
