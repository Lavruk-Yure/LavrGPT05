"""Deterministic cTrader Startup AutoConnect integration check."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class _StubCTraderAdapter:
    """Import-only cTrader adapter stub for this network-free check."""


class _StubHistoryResult:
    """Import-only cTrader history result stub for this network-free check."""


ctrader_adapter_stub = types.ModuleType("engine.ctrader_adapter")
ctrader_adapter_stub.HOST_DEMO = "demo.example.invalid"
ctrader_adapter_stub.HOST_LIVE = "live.example.invalid"
ctrader_adapter_stub.PORT = 5035
ctrader_adapter_stub.CTraderAdapter = _StubCTraderAdapter
sys.modules["engine.ctrader_adapter"] = ctrader_adapter_stub

ctrader_history_stub = types.ModuleType("engine.ctrader_history")
ctrader_history_stub.CTraderHistoryDownloadResult = _StubHistoryResult
sys.modules["engine.ctrader_history"] = ctrader_history_stub

from engine.runtime_engine import RuntimeEngine  # noqa: E402
from engine.runtime_events import RuntimeEventType  # noqa: E402
from engine.runtime_reconnect_task import RuntimeReconnectTask  # noqa: E402
from engine.services.ctrader_runtime_service import CTraderRuntimeService  # noqa: E402


class DummyAccount:
    """Minimum cTrader account snapshot required by the runtime service."""

    account_id = "CTRADER-DEMO"
    broker = "cTrader"
    currency = "USD"
    balance = 1000.0
    equity = 1000.0
    margin_used = 0.0
    margin_free = 1000.0

    def to_dict(self) -> dict:
        """Return a serializable account payload for the runtime event."""
        return {
            "account_id": self.account_id,
            "broker": self.broker,
            "currency": self.currency,
            "balance": self.balance,
            "equity": self.equity,
            "margin_used": self.margin_used,
            "margin_free": self.margin_free,
        }


class DummyAdapter:
    """Connected adapter returned by the deterministic reconnect."""

    @staticmethod
    def is_connected() -> bool:
        """Return connected state."""
        return True

    @staticmethod
    def is_session_alive() -> bool:
        """Return active-session state."""
        return True

    @staticmethod
    def get_account_info() -> DummyAccount:
        """Return the minimum account snapshot required by the service."""
        return DummyAccount()


class ControlledSessionManager:
    """Network-free SessionManager used to verify Startup AutoConnect."""

    def __init__(self, startup_ready: bool) -> None:
        self.startup_ready = bool(startup_ready)
        self.prepare_calls = 0
        self.connect_demo_calls = 0
        self.connect_live_calls = 0
        self.reconnect_calls = 0
        self.disconnect_calls = 0
        self.active_account_mode = ""
        self.active_adapter: DummyAdapter | None = None

    def prepare_startup_connection(self, account_mode: str) -> bool:
        """Preserve account mode without creating an adapter."""
        self.prepare_calls += 1
        self.active_account_mode = str(account_mode).strip().upper()
        return self.startup_ready

    def connect_demo(self) -> Any:
        """Record an unexpected direct Startup connect."""
        self.connect_demo_calls += 1
        return None

    def connect_live(self) -> Any:
        """Record an unexpected direct LIVE connect."""
        self.connect_live_calls += 1
        return None

    def reconnect(self) -> DummyAdapter:
        """Simulate the later canonical reconnect-watch recovery."""
        self.reconnect_calls += 1
        self.active_adapter = DummyAdapter()
        return self.active_adapter

    def disconnect(self) -> None:
        """Clear the deterministic active adapter."""
        self.disconnect_calls += 1
        self.active_adapter = None
        self.active_account_mode = ""

    def get_active_adapter(self) -> DummyAdapter | None:
        """Return the deterministic active adapter."""
        return self.active_adapter

    @staticmethod
    def get_forex_quote_snapshot(symbol_names: list[str]) -> dict:
        """Return an empty quote snapshot for protocol completeness."""
        return {
            "captured_utc": "",
            "complete": False,
            "quotes": {},
            "subscribed_symbols": list(symbol_names),
        }

    def get_historical_trendbars(
        self,
        symbol_name: str,
        timeframe: str,
        start_utc: Any,
        end_utc: Any,
    ) -> Any:
        """Historical data is not used by this regression check."""
        raise AssertionError(
            f"Unexpected history request: {symbol_name} {timeframe} "
            f"{start_utc} {end_utc}"
        )

    def modify_position_sl_tp(
        self,
        position_id: int | str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        """Position changes are not used by this regression check."""
        raise AssertionError(
            f"Unexpected modify request: {position_id} {stop_loss} {take_profit}"
        )


def _main_logic_startup_contract() -> tuple[bool, bool]:
    """Verify cTrader readiness ordering and unchanged IB startup flow."""
    source = (PROJECT_ROOT / "core" / "main_logic.py").read_text(encoding="utf-8")
    ctrader_start = source.index("    def _startup_connect_ctrader(")
    next_method = source.index(
        "    def _on_external_exposure_resolution_requested(",
        ctrader_start,
    )
    ctrader_source = source[ctrader_start:next_method]

    readiness_index = ctrader_source.index(
        "runtime_engine.prepare_ctrader_startup_connection("
    )
    connect_index = ctrader_source.index("runtime_engine.connect_ctrader_demo()")
    readiness_before_connect = readiness_index < connect_index
    timeout_starts_watch = all(
        token in ctrader_source
        for token in (
            "if not ready:",
            "runtime_engine.start_ctrader_reconnect_watch()",
            "return",
        )
    )

    ib_start = source.index("    def _startup_connect_ib(")
    ib_end = source.index(
        "    @staticmethod\n    def _startup_connect_ctrader(",
        ib_start,
    )
    ib_source = source[ib_start:ib_end]
    ib_startup_unchanged = "prepare_ctrader_startup_connection" not in ib_source

    return (
        readiness_before_connect and timeout_starts_watch,
        ib_startup_unchanged,
    )


def main() -> int:
    """Run Startup AutoConnect integration checks."""
    manager = ControlledSessionManager(startup_ready=False)
    service_manager: Any = manager
    service = CTraderRuntimeService(session_manager=service_manager)
    engine = RuntimeEngine(db_path=":memory:")
    engine.set_ctrader_runtime_service(service)

    ready = engine.prepare_ctrader_startup_connection(account_mode="DEMO")
    health_after_timeout = service.get_broker_health()
    timeout_state = health_after_timeout.state
    timeout_error = health_after_timeout.last_error

    engine.start_ctrader_reconnect_watch(interval_seconds=30.0)
    engine.start_ctrader_reconnect_watch(interval_seconds=30.0)
    reconnect_watch_events = [
        event
        for event in engine.events
        if event.event_type == RuntimeEventType.RECONNECT_STARTED
        and event.message == "cTrader reconnect watch started"
    ]

    reconnect_task = RuntimeReconnectTask(
        runtime_service=service,
        reconnect_cooldown_seconds=0.0,
    )
    reconnect_task.run_once()
    reconnect_task.run_once()

    final_health = service.get_broker_health()

    manual_manager = ControlledSessionManager(startup_ready=False)
    manual_service_manager: Any = manual_manager
    manual_service = CTraderRuntimeService(session_manager=manual_service_manager)
    manual_service.prepare_startup_connection(account_mode="DEMO")
    manual_service.disconnect()
    manual_task = RuntimeReconnectTask(
        runtime_service=manual_service,
        reconnect_cooldown_seconds=0.0,
    )
    manual_task.run_once()
    manual_health = manual_service.get_broker_health()

    startup_flow_ok, ib_startup_unchanged = _main_logic_startup_contract()

    checks = {
        "readiness_timeout_skips_candidate_connect": (
            not ready
            and manager.prepare_calls == 1
            and manager.connect_demo_calls == 0
            and manager.active_adapter is not None
        ),
        "timeout_enters_safe_disconnected": (
            timeout_state == "SAFE_DISCONNECTED"
            and timeout_error == "cTrader Startup Readiness timeout."
        ),
        "account_mode_preserved_for_reconnect": (manager.active_account_mode == "DEMO"),
        "single_reconnect_watch_registered": len(reconnect_watch_events) == 1,
        "canonical_reconnect_recovers_once": (
            manager.reconnect_calls == 1
            and final_health.is_connected()
            and reconnect_task.reconnect_attempts == 1
            and any(
                event.event_type == RuntimeEventType.RECONNECT_SUCCESS
                for event in service.get_runtime_events()
            )
        ),
        "manual_disconnect_blocks_auto_reconnect": (
            manual_manager.reconnect_calls == 0
            and manual_task.reconnect_attempts == 0
            and manual_health.manual_disconnect
        ),
        "startup_flow_checks_readiness_before_connect": startup_flow_ok,
        "ib_startup_path_unchanged": ib_startup_unchanged,
    }

    print("cTrader Startup AutoConnect result")
    for key, value in checks.items():
        print(f"  {key}={value}")

    engine.connection.close()

    ok = all(checks.values())
    print(f"CTRADER_STARTUP_AUTOCONNECT_CHECK={'OK' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
