"""Compact cTrader Startup/Reconnect regression check for RoadMap97."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class _StubHistoryResult:
    """Import-only cTrader history result for this network-free check."""


class FakeAccount:
    """Minimal account snapshot required by CTraderRuntimeService."""

    account_id = "CTRADER-DEMO"
    broker = "cTrader"
    currency = "USD"
    balance = 1000.0
    equity = 1000.0
    margin_used = 0.0
    margin_free = 1000.0

    def to_dict(self) -> dict:
        """Return the serializable runtime account payload."""
        return {
            "account_id": self.account_id,
            "broker": self.broker,
            "currency": self.currency,
            "balance": self.balance,
            "equity": self.equity,
            "margin_used": self.margin_used,
            "margin_free": self.margin_free,
        }


class FakeAdapter:
    """Deterministic adapter exposing only the lifecycle contract under test."""

    created: list[FakeAdapter] = []

    def __init__(self, account_mode: str) -> None:
        self.account_mode = str(account_mode).strip().upper()
        self.session_generation = 0
        self.connected = False
        self.retire_calls = 0
        self.close_wait_calls = 0
        self.disconnect_calls = 0
        type(self).created.append(self)

    @classmethod
    def from_env(cls, account_mode: str = "DEMO") -> FakeAdapter:
        """Create exactly one deterministic candidate adapter."""
        return cls(account_mode=account_mode)

    def set_session_generation(self, session_generation: int) -> None:
        """Record the generation assigned by SessionManager."""
        self.session_generation = int(session_generation)

    def connect(self) -> bool:
        """Complete the deterministic connection immediately."""
        self.connected = True
        return True

    def is_connected(self) -> bool:
        """Return deterministic connection state."""
        return self.connected

    def is_session_alive(self) -> bool:
        """Return whether this fake session has not been retired."""
        return self.retire_calls == 0

    def wait_for_connect_result(self, timeout_seconds: float) -> bool:
        """Return the already-known deterministic connection result."""
        if timeout_seconds < 0.0:
            raise AssertionError("timeout_seconds must be non-negative")
        return self.connected

    def retire_session(self) -> None:
        """Record retirement of an old or manually disconnected session."""
        self.retire_calls += 1

    def wait_for_retired_disconnect(self, timeout_seconds: float) -> bool:
        """Return immediate close evidence for a retired fake session."""
        if timeout_seconds < 0.0:
            raise AssertionError("timeout_seconds must be non-negative")
        self.close_wait_calls += 1
        return True

    def disconnect(self) -> None:
        """Record final local cleanup."""
        self.disconnect_calls += 1
        self.connected = False

    @staticmethod
    def get_account_info() -> FakeAccount:
        """Return the minimum runtime account snapshot."""
        return FakeAccount()


ctrader_adapter_stub = types.ModuleType("engine.ctrader_adapter")
ctrader_adapter_stub.HOST_DEMO = "demo.example.invalid"
ctrader_adapter_stub.HOST_LIVE = "live.example.invalid"
ctrader_adapter_stub.PORT = 5035
ctrader_adapter_stub.CTraderAdapter = FakeAdapter
sys.modules["engine.ctrader_adapter"] = ctrader_adapter_stub

ctrader_history_stub = types.ModuleType("engine.ctrader_history")
ctrader_history_stub.CTraderHistoryDownloadResult = _StubHistoryResult
sys.modules["engine.ctrader_history"] = ctrader_history_stub

from engine.ctrader_session_manager import CTraderSessionManager  # noqa: E402
from engine.runtime_engine import RuntimeEngine  # noqa: E402
from engine.runtime_events import RuntimeEventType  # noqa: E402
from engine.runtime_reconnect_task import RuntimeReconnectTask  # noqa: E402
from engine.services.ctrader_runtime_service import CTraderRuntimeService  # noqa: E402


def _ib_startup_path_unchanged() -> bool:
    """Verify that the cTrader readiness work did not enter IB startup."""
    source = (PROJECT_ROOT / "core" / "main_logic.py").read_text(
        encoding="utf-8"
    )
    ib_start = source.index("    def _startup_connect_ib(")
    ib_end = source.index(
        "    @staticmethod\n    def _startup_connect_ctrader(",
        ib_start,
    )
    ib_source = source[ib_start:ib_end]
    return all(
        token in ib_source
        for token in (
            "runtime_engine.connect_ib_demo()",
            "runtime_engine.start_ib_reconnect_watch()",
        )
    ) and "prepare_ctrader_startup_connection" not in ib_source


def main() -> int:
    """Run the compact Startup/Reconnect regression."""
    FakeAdapter.created.clear()
    manager = CTraderSessionManager()

    with mock.patch.object(
        CTraderSessionManager,
        "_wait_for_ctrader_host_ready",
        return_value=False,
    ):
        startup_ready = manager.prepare_startup_connection(account_mode="DEMO")

    readiness_candidate_count = len(FakeAdapter.created)

    with mock.patch.object(
        CTraderSessionManager,
        "_is_ctrader_host_reachable",
        return_value=True,
    ):
        first_adapter = manager.connect_demo()
        second_adapter = manager.reconnect()

    lifecycle_adapters = list(FakeAdapter.created)
    lifecycle_generations = [
        adapter.session_generation for adapter in lifecycle_adapters
    ]

    watch_manager = CTraderSessionManager()
    watch_manager_any: Any = watch_manager
    watch_service = CTraderRuntimeService(session_manager=watch_manager_any)
    engine = RuntimeEngine(db_path=":memory:")
    engine.set_ctrader_runtime_service(watch_service)

    with mock.patch.object(
        engine,
        "attach_reconnect_task",
        wraps=engine.attach_reconnect_task,
    ) as attach_mock:
        engine.start_ctrader_reconnect_watch(interval_seconds=30.0)
        engine.start_ctrader_reconnect_watch(interval_seconds=30.0)

    reconnect_watch_events = [
        event
        for event in engine.events
        if event.event_type == RuntimeEventType.RECONNECT_STARTED
        and event.message == "cTrader reconnect watch started"
    ]

    FakeAdapter.created.clear()
    manual_manager = CTraderSessionManager()
    manual_manager_any: Any = manual_manager
    manual_service = CTraderRuntimeService(session_manager=manual_manager_any)

    with mock.patch.object(
        CTraderSessionManager,
        "_is_ctrader_host_reachable",
        return_value=True,
    ):
        manual_adapter = manual_service.connect_demo()

    manual_service.disconnect()
    created_before_manual_task = len(FakeAdapter.created)
    manual_task = RuntimeReconnectTask(
        runtime_service=manual_service,
        reconnect_cooldown_seconds=0.0,
    )
    manual_task.run_once()
    manual_health = manual_service.get_broker_health()

    checks = {
        "readiness_does_not_create_candidate": (
            not startup_ready and readiness_candidate_count == 0
        ),
        "one_candidate_per_connect_generation": (
            first_adapter is lifecycle_adapters[0]
            and second_adapter is lifecycle_adapters[1]
            and len(lifecycle_adapters) == 2
        ),
        "session_generation_monotonic": lifecycle_generations == [1, 2],
        "old_adapter_retired_once_before_reconnect": (
            lifecycle_adapters[0].retire_calls == 1
            and lifecycle_adapters[0].close_wait_calls == 1
            and lifecycle_adapters[0].disconnect_calls == 1
            and manager.get_active_adapter() is lifecycle_adapters[1]
        ),
        "single_reconnect_watch_task": (
            attach_mock.call_count == 1 and len(reconnect_watch_events) == 1
        ),
        "manual_disconnect_blocks_auto_reconnect": (
            manual_adapter is not None
            and manual_task.reconnect_attempts == 0
            and len(FakeAdapter.created) == created_before_manual_task
            and manual_health.manual_disconnect
        ),
        "ib_startup_path_unchanged": _ib_startup_path_unchanged(),
    }

    print("cTrader Startup/Reconnect regression result")
    for key, value in checks.items():
        print(f"  {key}={value}")

    engine.connection.close()

    ok = all(checks.values())
    print(f"CTRADER_STARTUP_RECONNECT_REGRESSION_CHECK={'OK' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
