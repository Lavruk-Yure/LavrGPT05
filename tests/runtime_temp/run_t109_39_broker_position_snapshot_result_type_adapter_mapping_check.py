"""T109-39 — broker-neutral position snapshot DTO + adapter mapping check."""

from __future__ import annotations

import importlib
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

broker_position_module = importlib.import_module("engine.broker_position")
BrokerPosition = broker_position_module.BrokerPosition
BrokerPositionSnapshot = broker_position_module.BrokerPositionSnapshot

TEST_ID = "T109-39"
FACTUAL_VERDICT = "A. BROKER_POSITION_SNAPSHOT_RESULT_TYPE_ADAPTER_MAPPING_GREEN"
FIRST_UNRESOLVED_BOUNDARY = "RUNTIME_SERVICE_BROKER_POSITION_SNAPSHOT_ROUTING"
BOUNDARY_CONTRACT = (
    "RUNTIME_SERVICES_MUST_EXPOSE_BROKER_NEUTRAL_POSITION_SNAPSHOT_WITHOUT_"
    "COLLAPSING_FAILURE_TO_EMPTY_POSITIONS"
)


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def main() -> None:
    broker_position_source = _read("engine/broker_position.py")
    broker_interface_source = _read("engine/broker_interface.py")
    ib_source = _read("engine/ib_adapter.py")
    ctrader_source = _read("engine/ctrader_adapter.py")
    ib_service_source = _read("engine/services/ib_runtime_service.py")
    ctrader_service_source = _read("engine/services/ctrader_runtime_service.py")
    runtime_engine_source = _read("engine/runtime_engine.py")

    now_utc = datetime.now(UTC)
    position = BrokerPosition(
        broker="IB",
        account_id="DU123",
        account_mode="DEMO",
        position_id="IB:DU123:EURUSD",
        symbol_name="EURUSD",
        side="BUY",
        volume=3000.0,
    )
    success = BrokerPositionSnapshot(
        broker="IB",
        account_id="DU123",
        success=True,
        observed_at_utc=now_utc,
        positions=(position,),
    )
    empty_success = BrokerPositionSnapshot.success_result(
        broker="IB",
        account_id="DU123",
        positions=[],
    )
    failure = BrokerPositionSnapshot.failure_result(
        broker="IB",
        account_id="DU123",
        failure_reason="IB positions timeout.",
    )

    assert success.success is True
    assert success.positions == (position,)
    assert empty_success.success is True
    assert empty_success.positions == ()
    assert failure.success is False
    assert failure.positions == ()
    assert failure.failure_reason == "IB positions timeout."
    assert empty_success != failure

    for field_name in (
        "broker",
        "account_id",
        "success",
        "observed_at_utc",
        "positions",
        "failure_reason",
    ):
        assert field_name in BrokerPositionSnapshot.__dataclass_fields__

    assert "class BrokerPositionSnapshot" in broker_position_source
    assert "def get_positions_snapshot" in broker_interface_source
    assert "def get_positions_snapshot" in ib_source
    assert "BrokerPositionSnapshot.success_result" in ib_source
    assert "BrokerPositionSnapshot.failure_result" in ib_source
    assert "IB positions timeout." in ib_source
    assert "def get_positions_snapshot" in ctrader_source
    assert "CTRADER_POSITION_REQUEST_OUTCOME_SUCCESS" in ctrader_source
    assert "BrokerPositionSnapshot.success_result" in ctrader_source
    assert "BrokerPositionSnapshot.failure_result" in ctrader_source

    ib_service_snapshot_api = "def get_positions_snapshot" in ib_service_source
    ctrader_service_snapshot_api = (
        "def get_positions_snapshot" in ctrader_service_source
    )
    runtime_engine_snapshot_api = (
        "def get_broker_position_snapshot" in runtime_engine_source
    )

    assert not ib_service_snapshot_api
    assert not ctrader_service_snapshot_api
    assert not runtime_engine_snapshot_api

    print(f"{TEST_ID}_BROKER_POSITION_SNAPSHOT_RESULT_TYPE_ADAPTER_MAPPING=OK")
    print("production_change=True")
    print("broker_position_snapshot_type_present=True")
    print(
        "snapshot_fields="
        "broker,account_id,success,observed_at_utc,positions,failure_reason"
    )
    print("ib_adapter_snapshot_mapping_present=True")
    print("ctrader_adapter_snapshot_mapping_present=True")
    print("ib_empty_success_distinct_from_failure=True")
    print("ctrader_empty_success_distinct_from_failure=True")
    print(f"ib_runtime_service_snapshot_api_present={ib_service_snapshot_api}")
    print(
        "ctrader_runtime_service_snapshot_api_present="
        f"{ctrader_service_snapshot_api}"
    )
    print(f"runtime_engine_snapshot_api_present={runtime_engine_snapshot_api}")
    print("freshness_ttl_value_decided=False")
    print("workspace_controller_submission_wiring=False")
    print("broker_requests=0")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


if __name__ == "__main__":
    main()
