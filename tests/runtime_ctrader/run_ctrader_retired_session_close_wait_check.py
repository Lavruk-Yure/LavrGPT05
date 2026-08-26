"""Deterministic cTrader retired-session close-evidence regression check."""

from __future__ import annotations

import sys
import threading
import time
import types
from pathlib import Path
from typing import Any
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


EVENTS: list[str] = []


class _StubCTraderAdapter:
    """Import-only adapter plus deterministic candidate factory."""

    next_candidate: Any = None

    @classmethod
    def from_env(cls, account_mode: str) -> Any:
        """Return the candidate installed by the current test scenario."""
        EVENTS.append(f"factory:{account_mode}")
        candidate = cls.next_candidate
        if candidate is None:
            raise AssertionError("Candidate adapter was not installed")
        cls.next_candidate = None
        return candidate


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

import engine.ctrader_session_manager as session_manager_module  # noqa: E402
from engine.ctrader_session_manager import CTraderSessionManager  # noqa: E402


class ControlledOldAdapter:
    """Old-session double exposing bounded close evidence."""

    def __init__(self) -> None:
        self.close_event = threading.Event()
        self.wait_calls = 0
        self.disconnect_calls = 0

    @staticmethod
    def retire_session() -> None:
        """Record old-session retirement."""
        EVENTS.append("old:retire")

    def wait_for_retired_disconnect(self, timeout_seconds: float) -> bool:
        """Wait for deterministic old-session close evidence."""
        self.wait_calls += 1
        EVENTS.append("old:wait_start")
        closed = self.close_event.wait(
            timeout=max(0.0, float(timeout_seconds)),
        )
        EVENTS.append("old:wait_end")
        return closed

    def disconnect(self) -> None:
        """Record final local cleanup after the bounded wait."""
        self.disconnect_calls += 1
        EVENTS.append("old:disconnect")

    def complete_close(self) -> None:
        """Publish deterministic broker/client close evidence."""
        EVENTS.append("old:close_evidence")
        self.close_event.set()


class ControlledCandidateAdapter:
    """Connected candidate created only after old-session close handling."""

    def __init__(self) -> None:
        self.session_generation = 0
        self.connect_calls = 0

    def set_session_generation(self, generation: int) -> None:
        """Record the promoted candidate generation."""
        self.session_generation = int(generation)
        EVENTS.append("candidate:generation")

    def connect(self) -> bool:
        """Return deterministic successful candidate connection."""
        self.connect_calls += 1
        EVENTS.append("candidate:connect")
        return True


class TestableSessionManager(CTraderSessionManager):
    """Expose controlled old-adapter installation for this check."""

    def install_active_adapter(self, adapter: Any) -> None:
        """Install the deterministic old adapter."""
        self._active_adapter = adapter

    def connect_demo_for_test(self) -> Any:
        """Run the production DEMO connect path."""
        return self._connect(account_mode="DEMO")


def _run_event_evidence_scenario() -> tuple[bool, bool, bool]:
    """Verify candidate creation waits for positive close evidence."""
    EVENTS.clear()
    manager = TestableSessionManager()
    old_adapter = ControlledOldAdapter()
    candidate = ControlledCandidateAdapter()
    manager.install_active_adapter(old_adapter)
    _StubCTraderAdapter.next_candidate = candidate

    timer = threading.Timer(0.02, old_adapter.complete_close)
    timer.start()
    with patch.object(
        CTraderSessionManager,
        "_is_ctrader_host_reachable",
        return_value=True,
    ), patch.object(
        session_manager_module,
        "CTRADER_OLD_SESSION_CLOSE_TIMEOUT_SECONDS",
        0.25,
    ):
        result = manager.connect_demo_for_test()
    timer.join(timeout=0.5)

    close_index = EVENTS.index("old:close_evidence")
    factory_index = EVENTS.index("factory:DEMO")
    wait_end_index = EVENTS.index("old:wait_end")
    disconnect_index = EVENTS.index("old:disconnect")

    return (
        result is candidate,
        close_index < wait_end_index < disconnect_index < factory_index,
        old_adapter.wait_calls == 1 and candidate.connect_calls == 1,
    )


def _run_timeout_scenario() -> tuple[bool, bool, bool]:
    """Verify missing close evidence falls back after a bounded timeout."""
    EVENTS.clear()
    manager = TestableSessionManager()
    old_adapter = ControlledOldAdapter()
    candidate = ControlledCandidateAdapter()
    manager.install_active_adapter(old_adapter)
    _StubCTraderAdapter.next_candidate = candidate

    started = time.monotonic()
    with patch.object(
        CTraderSessionManager,
        "_is_ctrader_host_reachable",
        return_value=True,
    ), patch.object(
        session_manager_module,
        "CTRADER_OLD_SESSION_CLOSE_TIMEOUT_SECONDS",
        0.03,
    ):
        result = manager.connect_demo_for_test()
    elapsed = time.monotonic() - started

    wait_end_index = EVENTS.index("old:wait_end")
    factory_index = EVENTS.index("factory:DEMO")

    return (
        result is candidate,
        0.02 <= elapsed < 0.5,
        wait_end_index < factory_index and old_adapter.wait_calls == 1,
    )


def _source_contract() -> tuple[bool, bool, bool]:
    """Verify production source uses bounded close evidence, not sleep."""
    manager_source = (PROJECT_ROOT / "engine" / "ctrader_session_manager.py").read_text(
        encoding="utf-8"
    )
    old_start = manager_source.index("        if old_adapter is not None:")
    old_end = manager_source.index(
        "        LOGGER.warning(\n"
        '            "Creating new cTrader candidate adapter.',
        old_start,
    )
    old_source = manager_source[old_start:old_end]

    adapter_source = (PROJECT_ROOT / "engine" / "ctrader_adapter.py").read_text(
        encoding="utf-8"
    )
    retire_start = adapter_source.index("    def retire_session(")
    retire_end = adapter_source.index("    def is_session_alive(", retire_start)
    retire_source = adapter_source[retire_start:retire_end]

    constants_source = (PROJECT_ROOT / "engine" / "runtime_constants.py").read_text(
        encoding="utf-8"
    )

    no_blind_close_sleep = (
        "time.sleep(" not in old_source and "wait_for_retired_disconnect(" in old_source
    )
    adapter_close_event_contract = all(
        token in retire_source
        for token in (
            "_retired_disconnect_event.clear()",
            "_retired_disconnect_event.set()",
            "def wait_for_retired_disconnect(",
            "_retired_disconnect_event.wait(",
        )
    )
    timeout_constant_semantics = (
        "CTRADER_OLD_SESSION_CLOSE_TIMEOUT_SECONDS = 2.0" in constants_source
        and "CTRADER_OLD_SESSION_CLOSE_DELAY_SECONDS" not in constants_source
    )
    return (
        no_blind_close_sleep,
        adapter_close_event_contract,
        timeout_constant_semantics,
    )


def main() -> int:
    """Run retired-session close-evidence lifecycle checks."""
    event_result, event_order, event_counts = _run_event_evidence_scenario()
    timeout_result, timeout_bounded, timeout_order = _run_timeout_scenario()
    (
        no_blind_close_sleep,
        adapter_close_event_contract,
        timeout_constant_semantics,
    ) = _source_contract()

    checks = {
        "close_evidence_precedes_candidate": (
            event_result and event_order and event_counts
        ),
        "missing_evidence_uses_bounded_timeout": (
            timeout_result and timeout_bounded and timeout_order
        ),
        "no_blind_old_session_sleep": no_blind_close_sleep,
        "adapter_close_event_contract": adapter_close_event_contract,
        "timeout_constant_semantics": timeout_constant_semantics,
    }

    print("cTrader retired-session close wait result")
    for name, value in checks.items():
        print(f"  {name}={value}")

    if not all(checks.values()):
        print("CTRADER_RETIRED_SESSION_CLOSE_WAIT_CHECK=FAILED")
        return 1

    print("CTRADER_RETIRED_SESSION_CLOSE_WAIT_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
