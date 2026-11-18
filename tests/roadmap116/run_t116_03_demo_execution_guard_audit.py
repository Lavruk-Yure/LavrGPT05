"""T116-03 · TEST_ONLY · offline аудит DEMO execution guards без broker API."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.broker_position import (  # noqa: E402
    BrokerPosition,
    BrokerPositionSnapshot,
    broker_position_snapshot_confirms_flat,
)
from engine.runtime_account_state import RuntimeAccountState  # noqa: E402
from engine.runtime_engine import RuntimeEngine  # noqa: E402
from engine.services.ctrader_runtime_service import (  # noqa: E402
    CTraderRuntimeService,
    CTraderSessionManagerProtocol,
)

ACCOUNT = "T116-FAKE-DEMO-ACCOUNT"
TRADE = "T116-TRADE"
PLAN = "T116-PLAN"


class FakeAdapter:
    def __init__(self, connected=True, alive=True, snapshot=None):
        self.connected = connected
        self.alive = alive
        self.snapshot = snapshot
        self.order_attempts = 0

    def is_connected(self):
        return self.connected

    def is_session_alive(self):
        return self.alive

    def get_positions_snapshot(self):
        assert self.snapshot is not None, "Unexpected position request"
        return self.snapshot

    def place_market_order(self, **_kwargs):
        self.order_attempts += 1
        raise AssertionError("TEST_ONLY: до відправлення ордера дійти не можна")


class FakeSession:
    def __init__(self, adapter):
        self.adapter = adapter

    def get_active_adapter(self):
        return self.adapter


class FakeRepo:
    def __init__(self, existing_status=None, execution_state="READY_FOR_SUBMISSION"):
        self.existing_status = existing_status
        self.execution_state = execution_state

    def get_trade_chain(self, uid):
        assert uid == TRADE
        orders = []
        if self.existing_status:
            orders.append(
                {
                    "order_plan_uid": PLAN,
                    "broker_order_uid": "T116-OLD-ORDER",
                    "broker_order_id": "T116-OLD-ID",
                    "execution_status": self.existing_status,
                }
            )
        return {
            "trade": {
                "source": "WORKSPACE",
                "broker": "CTRADER",
                "account_id": ACCOUNT,
                "control_mode": "AUTO",
                "execution_state": self.execution_state,
                "symbol": "EURUSD",
                "volume": 1000.0,
            },
            "order_plans": [
                {
                    "source": "WORKSPACE",
                    "order_plan_uid": PLAN,
                    "side": "BUY",
                    "volume": 1000.0,
                    "stop_loss": 1.08,
                }
            ],
            "broker_orders": orders,
        }


def make_engine(
    connected=True,
    alive=True,
    active_account=ACCOUNT,
    existing_status=None,
    execution_state="READY_FOR_SUBMISSION",
    snapshot=None,
):
    """Створити тільки підставні service/adapter та in-memory repository."""
    adapter = FakeAdapter(connected, alive, snapshot)
    session = Mock(spec=CTraderSessionManagerProtocol)
    session.get_active_adapter.return_value = adapter

    service = CTraderRuntimeService(session_manager=session)
    service.get_broker_health().set_connected()
    service._account_state = RuntimeAccountState(
        account_id=active_account, broker_name="CTRADER", currency="USD"
    )
    engine = RuntimeEngine.__new__(RuntimeEngine)
    engine.ctrader_runtime_service = service
    engine.ib_runtime_service = None
    engine.repository = FakeRepo(existing_status, execution_state)
    return engine, adapter, service


def blocked(call, message):
    try:
        call()
    except RuntimeError as caught_error:
        assert message.lower() in str(caught_error).lower(), str(caught_error)
    else:
        raise AssertionError(f"Expected block: {message}")


def test():
    adapters = []

    engine, adapter, _ = make_engine(connected=False)
    blocked(
        lambda: engine.submit_workspace_execution_plan(TRADE, PLAN), "not connected"
    )
    adapters.append(adapter)
    print("disconnected_blocks_submission=OK")

    engine, adapter, service = make_engine(alive=False)
    blocked(
        lambda: engine.submit_workspace_execution_plan(TRADE, PLAN), "not connected"
    )
    assert service.get_account_state().account_id is None
    adapters.append(adapter)
    print("dead_session_invalidates_health_and_account=OK")

    engine, adapter, _ = make_engine(active_account="OTHER-FAKE-ACCOUNT")
    blocked(
        lambda: engine.submit_workspace_execution_plan(TRADE, PLAN), "does not match"
    )
    adapters.append(adapter)
    print("exact_workspace_account_binding=OK")

    engine, adapter, _ = make_engine(execution_state="PENDING_CONFIRMATION")
    blocked(lambda: engine.submit_workspace_execution_plan(TRADE, PLAN), "not ready")
    adapters.append(adapter)
    print("unconfirmed_plan_blocks_submission=OK")

    engine, adapter, _ = make_engine()
    blocked(
        lambda: engine.submit_workspace_execution_plan(
            TRADE, PLAN, reverse_required=True, confirmed_flat=False
        ),
        "confirmed flat",
    )
    adapters.append(adapter)
    print("reverse_requires_confirmed_flat=OK")

    engine, adapter, _ = make_engine(existing_status="SUBMITTED")
    result = engine.submit_workspace_execution_plan(TRADE, PLAN)
    assert result["already_submitted"] is True
    assert result["broker_order_uid"] == "T116-OLD-ORDER"
    adapters.append(adapter)
    print("persisted_order_blocks_duplicate=OK")

    engine, adapter, _ = make_engine(existing_status="PENDING_CONFIRMATION")
    with patch.object(
        RuntimeEngine,
        "recover_ctrader_workspace_timeout",
        return_value={
            "execution_status": "STILL_PENDING",
            "broker_order_id": None,
            "position_uid": "",
        },
    ) as recovery:
        result = engine.submit_workspace_execution_plan(TRADE, PLAN)
        assert recovery.call_count == 1
        assert result["already_submitted"] is True
        assert result["resubmit_allowed"] is False
    adapters.append(adapter)
    print("pending_confirmation_no_resubmit=OK")

    now = datetime.now(UTC)
    failure = BrokerPositionSnapshot.failure_result("CTRADER", ACCOUNT, "TEST_ONLY")
    engine, adapter, _ = make_engine(snapshot=failure)
    snapshot = engine.get_workspace_broker_positions_snapshot("CTRADER", ACCOUNT)
    assert snapshot.success is False
    adapters.append(adapter)
    common = dict(
        broker="CTRADER",
        account_id=ACCOUNT,
        symbol="EURUSD",
        now_utc=now,
        max_age=timedelta(seconds=5),
    )
    assert not broker_position_snapshot_confirms_flat(snapshot, **common)
    print("failed_position_snapshot_not_flat=OK")

    stale = BrokerPositionSnapshot(
        "CTRADER", ACCOUNT, True, now - timedelta(minutes=1), ()
    )
    position = BrokerPosition(
        "CTRADER", ACCOUNT, "DEMO", "T116-POSITION", "EURUSD", volume=1000.0
    )
    occupied = BrokerPositionSnapshot("CTRADER", ACCOUNT, True, now, (position,))
    fresh_flat = BrokerPositionSnapshot("CTRADER", ACCOUNT, True, now, ())
    assert not broker_position_snapshot_confirms_flat(stale, **common)
    assert not broker_position_snapshot_confirms_flat(occupied, **common)
    assert broker_position_snapshot_confirms_flat(fresh_flat, **common)
    print("stale_or_occupied_snapshot_not_flat=OK")
    print("fresh_empty_snapshot_confirms_flat=OK")

    assert all(adapter.order_attempts == 0 for adapter in adapters)
    print("fake_order_attempts=0")
    print("broker_requests=0")
    print("database_writes=0")
    print("production_changes=0")
    print("active_lge_session=NOT_CHECKED")
    print("T116-03=GREEN_OFFLINE_GUARDS")


if __name__ == "__main__":
    print("T116-03 TEST_ONLY | cTrader DEMO offline guard audit")
    try:
        test()
    except Exception as exc:
        print(f"failure={type(exc).__name__}: {exc}")
        print("T116-03=RED")
        raise SystemExit(1)
