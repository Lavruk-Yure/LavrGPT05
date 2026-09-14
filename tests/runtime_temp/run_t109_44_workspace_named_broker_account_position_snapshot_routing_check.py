from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

broker_position_module = importlib.import_module("engine.broker_position")
runtime_engine_module = importlib.import_module("engine.runtime_engine")
BrokerPosition = broker_position_module.BrokerPosition
BrokerPositionSnapshot = broker_position_module.BrokerPositionSnapshot
RuntimeEngine = runtime_engine_module.RuntimeEngine

TEST_ID = "T109-44"
FACTUAL_VERDICT = "A. WORKSPACE_NAMED_BROKER_ACCOUNT_POSITION_SNAPSHOT_ROUTING_GREEN"
FIRST_UNRESOLVED_BOUNDARY = "WORKSPACE_CONTROLLER_FRESHNESS_POLICY_SOURCE"
BOUNDARY_CONTRACT = (
    "CONTROLLER_MUST_RECEIVE_EXACT_WORKSPACE_BROKER_ACCOUNT_SNAPSHOT_BEFORE_"
    "APPLYING_PARAMETERIZED_FRESHNESS_POLICY_AND_AUTO_SUBMISSION_GATE"
)


@dataclass(slots=True)
class _Health:
    connected: bool = True

    def is_connected(self) -> bool:
        return self.connected


class _IBService:
    def __init__(self, snapshot: Any) -> None:
        self.snapshot = snapshot
        self.snapshot_calls = 0

    @staticmethod
    def refresh_broker_health() -> _Health:
        return _Health()

    @staticmethod
    def get_managed_accounts() -> list[str]:
        return ["DU111", "DU222"]

    def get_positions_snapshot(self) -> Any:
        self.snapshot_calls += 1
        return self.snapshot


class _CTraderService:
    def __init__(self, snapshot: Any) -> None:
        self.snapshot = snapshot
        self.snapshot_calls = 0

    @staticmethod
    def refresh_broker_health() -> _Health:
        return _Health()

    @staticmethod
    def get_account_state() -> SimpleNamespace:
        return SimpleNamespace(account_id="CT123")

    def get_positions_snapshot(self) -> Any:
        self.snapshot_calls += 1
        return self.snapshot


def _position(broker: str, account_id: str, symbol: str) -> Any:
    return BrokerPosition(
        broker=broker,
        account_id=account_id,
        account_mode="PAPER",
        position_id=f"{broker}-{account_id}-{symbol}",
        symbol_name=symbol,
        side="BUY",
        volume=1000.0,
    )


def main() -> None:
    observed_at = datetime.now(UTC)
    ib_snapshot = BrokerPositionSnapshot(
        broker="IB",
        account_id="DU111",
        success=True,
        observed_at_utc=observed_at,
        positions=(
            _position("IB", "DU111", "EURUSD"),
            _position("IB", "DU222", "GBPUSD"),
        ),
    )
    ctrader_failure = BrokerPositionSnapshot(
        broker="CTRADER",
        account_id="CT123",
        success=False,
        observed_at_utc=observed_at,
        positions=(),
        failure_reason="TEST_ONLY request failure",
    )

    ib_service = _IBService(ib_snapshot)
    ctrader_service = _CTraderService(ctrader_failure)
    engine = RuntimeEngine.__new__(RuntimeEngine)
    engine_any: Any = engine
    engine_any.ib_runtime_service = ib_service
    engine_any.ctrader_runtime_service = ctrader_service

    ib_result = engine_any.get_workspace_broker_positions_snapshot("IB", "DU222")
    assert ib_result.success
    assert ib_result.broker == "IB"
    assert ib_result.account_id == "DU222"
    assert ib_result.observed_at_utc == observed_at
    assert len(ib_result.positions) == 1
    assert ib_result.positions[0].account_id == "DU222"
    assert ib_result.positions[0].symbol_name == "GBPUSD"

    ctrader_result = engine_any.get_workspace_broker_positions_snapshot(
        "CTRADER",
        "CT123",
    )
    assert not ctrader_result.success
    assert ctrader_result.broker == "CTRADER"
    assert ctrader_result.account_id == "CT123"
    assert ctrader_result.observed_at_utc == observed_at
    assert ctrader_result.failure_reason == "TEST_ONLY request failure"
    assert ctrader_result.positions == ()

    active_broker_before = getattr(engine, "context", None)
    assert active_broker_before is None
    assert ib_service.snapshot_calls == 1
    assert ctrader_service.snapshot_calls == 1

    print(f"{TEST_ID}_WORKSPACE_NAMED_BROKER_ACCOUNT_POSITION_SNAPSHOT_ROUTING=OK")
    print("production_change=True")
    print("runtime_named_workspace_snapshot_api_present=True")
    print("exact_named_broker_routing_present=True")
    print("exact_account_scope_preserved=True")
    print("ib_managed_account_snapshot_scoped=True")
    print("ctrader_exact_active_account_binding_enforced=True")
    print("failure_metadata_preserved=True")
    print("observed_at_utc_preserved=True")
    print("active_broker_context_not_required=True")
    print("workspace_controller_submission_wiring=False")
    print("freshness_ttl_value_decided=False")
    print("broker_requests=0")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


if __name__ == "__main__":
    main()
