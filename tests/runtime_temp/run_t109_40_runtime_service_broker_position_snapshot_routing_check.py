"""T109-40 — RuntimeService -> RuntimeEngine position snapshot routing check."""

from __future__ import annotations

import importlib
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

broker_position_module = importlib.import_module("engine.broker_position")
runtime_engine_module = importlib.import_module("engine.runtime_engine")

BrokerPositionSnapshot = broker_position_module.BrokerPositionSnapshot
RuntimeEngine = runtime_engine_module.RuntimeEngine

TEST_ID = "T109-40"
FACTUAL_VERDICT = "A. RUNTIME_SERVICE_BROKER_POSITION_SNAPSHOT_ROUTING_GREEN"
FIRST_UNRESOLVED_BOUNDARY = "WORKSPACE_CONFIRMED_FLAT_FRESHNESS_EVALUATION"
BOUNDARY_CONTRACT = (
    "RUNTIME_ENGINE_MUST_EXPOSE_EXACT_BROKER_ACCOUNT_SNAPSHOT_METADATA_BEFORE_"
    "CONTROLLER_CAN_EVALUATE_CONFIRMED_FLAT"
)


class _SnapshotService:
    """TEST_ONLY RuntimeService surface без broker I/O."""

    def __init__(self, snapshot: Any) -> None:
        self.snapshot = snapshot
        self.snapshot_calls = 0

    def get_positions_snapshot(self) -> Any:
        self.snapshot_calls += 1
        return self.snapshot


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def _snapshot(
    *,
    broker: str,
    account_id: str,
    success: bool,
    failure_reason: str = "",
) -> Any:
    return BrokerPositionSnapshot(
        broker=broker,
        account_id=account_id,
        success=success,
        observed_at_utc=datetime(2026, 9, 13, 12, 0, tzinfo=UTC),
        positions=(),
        failure_reason=failure_reason,
    )


def main() -> None:
    broker_requests = 0

    ib_service_source = _read("engine/services/ib_runtime_service.py")
    ctrader_service_source = _read("engine/services/ctrader_runtime_service.py")
    runtime_engine_source = _read("engine/runtime_engine.py")

    assert "def get_positions_snapshot" in ib_service_source
    assert "return adapter.get_positions_snapshot()" in ib_service_source
    assert "BrokerPositionSnapshot.failure_result" in ib_service_source
    assert "def get_positions_snapshot" in ctrader_service_source
    assert "return adapter.get_positions_snapshot()" in ctrader_service_source
    assert "BrokerPositionSnapshot.failure_result" in ctrader_service_source
    assert "def get_active_broker_positions_snapshot" in runtime_engine_source
    assert "return service.get_positions_snapshot()" in runtime_engine_source

    ib_snapshot = _snapshot(
        broker="IB",
        account_id="DU123",
        success=True,
    )
    ctrader_snapshot = _snapshot(
        broker="CTRADER",
        account_id="456",
        success=False,
        failure_reason="TEST_ONLY_TIMEOUT",
    )
    ib_service = _SnapshotService(ib_snapshot)
    ctrader_service = _SnapshotService(ctrader_snapshot)

    with tempfile.TemporaryDirectory(prefix="t109_40_") as tmp_dir:
        engine = RuntimeEngine(
            db_path=str(Path(tmp_dir) / "runtime.sqlite3"),
        )
        setattr(engine, "ib_runtime_service", ib_service)
        setattr(engine, "ctrader_runtime_service", ctrader_service)

        engine.set_active_broker("IB", require_connected=False)
        ib_engine_snapshot = engine.get_active_broker_positions_snapshot()

        engine.set_active_broker("CTRADER", require_connected=False)
        ctrader_engine_snapshot = engine.get_active_broker_positions_snapshot()

        engine.connection.close()

    assert ib_engine_snapshot is ib_snapshot
    assert ib_engine_snapshot.success is True
    assert ib_engine_snapshot.account_id == "DU123"
    assert ctrader_engine_snapshot is ctrader_snapshot
    assert ctrader_engine_snapshot.success is False
    assert ctrader_engine_snapshot.positions == ()
    assert ctrader_engine_snapshot.failure_reason == "TEST_ONLY_TIMEOUT"
    assert ib_service.snapshot_calls == 1
    assert ctrader_service.snapshot_calls == 1

    print(f"{TEST_ID}_RUNTIME_SERVICE_BROKER_POSITION_SNAPSHOT_ROUTING=OK")
    print("production_change=True")
    print("ib_runtime_service_snapshot_api_present=True")
    print("ctrader_runtime_service_snapshot_api_present=True")
    print("runtime_engine_snapshot_api_present=True")
    print("ib_success_metadata_preserved=True")
    print("ctrader_failure_metadata_preserved=True")
    print("failure_not_collapsed_to_empty_positions=True")
    print("observed_at_utc_preserved=True")
    print("exact_broker_account_scope_preserved=True")
    print("freshness_ttl_value_decided=False")
    print("workspace_controller_submission_wiring=False")
    print(f"broker_requests={broker_requests}")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


if __name__ == "__main__":
    main()
