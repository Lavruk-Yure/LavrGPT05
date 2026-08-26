"""Deterministic cTrader late-connect event wait regression check."""

from __future__ import annotations

import sys
import threading
import time
import types
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class _StubCTraderAdapter:
    """Import-only cTrader adapter stub."""


class _StubHistoryResult:
    """Import-only cTrader history result stub."""


ctrader_adapter_stub = types.ModuleType("engine.ctrader_adapter")
ctrader_adapter_stub.HOST_DEMO = "demo.example.invalid"
ctrader_adapter_stub.HOST_LIVE = "live.example.invalid"
ctrader_adapter_stub.PORT = 5035
ctrader_adapter_stub.CTraderAdapter = _StubCTraderAdapter
sys.modules["engine.ctrader_adapter"] = ctrader_adapter_stub

ctrader_history_stub = types.ModuleType("engine.ctrader_history")
ctrader_history_stub.CTraderHistoryDownloadResult = _StubHistoryResult
sys.modules["engine.ctrader_history"] = ctrader_history_stub

from engine.ctrader_session_manager import CTraderSessionManager  # noqa: E402


class ControlledAdapter:
    """Event-driven adapter double used by the late-connect check."""

    def __init__(
        self,
        *,
        connected: bool = False,
        alive: bool = True,
    ) -> None:
        self.connected = bool(connected)
        self.alive = bool(alive)
        self.connect_event = threading.Event()
        self.wait_calls = 0

    def is_session_alive(self) -> bool:
        """Return deterministic session-liveness state."""
        return self.alive

    def is_connected(self) -> bool:
        """Return deterministic connection state."""
        return self.connected

    def wait_for_connect_result(self, timeout_seconds: float) -> bool:
        """Wait for the deterministic connect-completion event."""
        self.wait_calls += 1
        self.connect_event.wait(timeout=max(0.0, float(timeout_seconds)))
        return self.connected

    def complete_connect(self) -> None:
        """Complete the deterministic late connection."""
        self.connected = True
        self.connect_event.set()


class TestableSessionManager(CTraderSessionManager):
    """Expose only the late-connect helper for this regression check."""

    def wait_for_late_connect(
        self,
        adapter: Any,
        *,
        session_generation: int,
        timeout_seconds: float,
    ) -> bool:
        """Call the production late-connect helper."""
        return self._wait_for_late_connect(
            adapter=adapter,
            session_generation=session_generation,
            timeout_seconds=timeout_seconds,
        )


def _source_contract() -> tuple[bool, bool]:
    """Verify production source uses event waiting instead of sleep polling."""
    manager_source = (
        PROJECT_ROOT / "engine" / "ctrader_session_manager.py"
    ).read_text(encoding="utf-8")
    wait_start = manager_source.index("    def _wait_for_late_connect(")
    wait_end = manager_source.index(
        "    @staticmethod\n    def _get_ctrader_host_port",
        wait_start,
    )
    wait_source = manager_source[wait_start:wait_end]

    adapter_source = (
        PROJECT_ROOT / "engine" / "ctrader_adapter.py"
    ).read_text(encoding="utf-8")
    adapter_wait_start = adapter_source.index("    def wait_for_connect_result(")
    adapter_wait_end = adapter_source.index(
        "    def is_connected(",
        adapter_wait_start,
    )
    adapter_wait_source = adapter_source[adapter_wait_start:adapter_wait_end]

    no_sleep_polling = (
        "time.sleep" not in wait_source
        and "wait_for_connect_result(" in wait_source
        and "while " not in wait_source
    )
    adapter_wait_contract = (
        "connected_event.wait(" in adapter_wait_source
        and "return self.is_connected()" in adapter_wait_source
    )
    return no_sleep_polling, adapter_wait_contract


def main() -> int:
    """Run deterministic late-connect event-wait checks."""
    manager = TestableSessionManager()

    late_adapter = ControlledAdapter()
    timer = threading.Timer(0.02, late_adapter.complete_connect)
    timer.start()
    late_success = manager.wait_for_late_connect(
        late_adapter,
        session_generation=7,
        timeout_seconds=0.25,
    )
    timer.join(timeout=0.5)

    immediate_adapter = ControlledAdapter(connected=True)
    immediate_success = manager.wait_for_late_connect(
        immediate_adapter,
        session_generation=8,
        timeout_seconds=0.25,
    )

    retired_adapter = ControlledAdapter(alive=False)
    retired_result = manager.wait_for_late_connect(
        retired_adapter,
        session_generation=9,
        timeout_seconds=0.25,
    )

    timeout_adapter = ControlledAdapter()
    timeout_started = time.monotonic()
    timeout_result = manager.wait_for_late_connect(
        timeout_adapter,
        session_generation=10,
        timeout_seconds=0.04,
    )
    timeout_elapsed = time.monotonic() - timeout_started

    no_sleep_polling, adapter_wait_contract = _source_contract()

    checks = {
        "late_success_event_driven": (
            late_success
            and late_adapter.connected
            and late_adapter.wait_calls == 1
        ),
        "immediate_connected_no_wait": (
            immediate_success and immediate_adapter.wait_calls == 0
        ),
        "retired_skips_wait": (
            not retired_result and retired_adapter.wait_calls == 0
        ),
        "timeout_bounded": (
            not timeout_result
            and timeout_adapter.wait_calls == 1
            and timeout_elapsed < 0.5
        ),
        "no_sleep_polling": no_sleep_polling,
        "adapter_wait_contract": adapter_wait_contract,
    }

    print("cTrader late-connect wait result")
    for name, value in checks.items():
        print(f"  {name}={value}")

    if not all(checks.values()):
        print("CTRADER_LATE_CONNECT_WAIT_CHECK=FAILED")
        return 1

    print("CTRADER_LATE_CONNECT_WAIT_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
