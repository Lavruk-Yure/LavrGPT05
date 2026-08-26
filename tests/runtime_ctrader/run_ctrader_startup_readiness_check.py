# run_ctrader_startup_readiness_check.py
"""Deterministic check for bounded cTrader Startup Readiness."""

from __future__ import annotations

import sys
import time
import types
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class _StubCTraderAdapter:
    """Import-only cTrader adapter stub for this network-free check."""


class _StubHistoryResult:
    """Import-only history result stub for this network-free check."""


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
from engine.runtime_constants import (  # noqa: E402
    CTRADER_STARTUP_READINESS_GRACE_SECONDS,
    CTRADER_STARTUP_READINESS_POLL_INTERVAL_SECONDS,
    CTRADER_STARTUP_READINESS_PROBE_TIMEOUT_SECONDS,
)


class ProbeControlledSessionManager(CTraderSessionManager):
    """Session manager exposing generation for this deterministic check."""

    @property
    def session_generation_snapshot(self) -> int:
        """Expose generation only for this deterministic runtime check."""
        return self._session_generation


def _run_readiness_with_probe(
    probe_results: list[bool],
    *,
    account_mode: str,
    grace_seconds: float,
    poll_interval_seconds: float,
) -> tuple[ProbeControlledSessionManager, bool, int]:
    """Run readiness with deterministic reachability results."""
    manager = ProbeControlledSessionManager()

    with patch.object(
        CTraderSessionManager,
        "_is_ctrader_host_reachable",
        side_effect=list(probe_results),
    ) as probe_mock:
        ready = manager.prepare_startup_connection(
            account_mode=account_mode,
            timeout_seconds=grace_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        probe_calls = probe_mock.call_count

    return manager, ready, probe_calls


def main() -> int:
    """Run Startup Readiness regression checks."""
    immediate, immediate_ready, immediate_probe_calls = _run_readiness_with_probe(
        [True],
        account_mode="DEMO",
        grace_seconds=0.0,
        poll_interval_seconds=0.01,
    )

    _delayed, delayed_ready, delayed_probe_calls = _run_readiness_with_probe(
        [False, False, True],
        account_mode="LIVE",
        grace_seconds=0.20,
        poll_interval_seconds=0.01,
    )

    started = time.monotonic()
    unavailable, unavailable_ready, unavailable_probe_calls = _run_readiness_with_probe(
        [False] * 32,
        account_mode="DEMO",
        grace_seconds=0.03,
        poll_interval_seconds=0.005,
    )
    unavailable_elapsed = time.monotonic() - started

    invalid_mode_blocked = False
    try:
        immediate.prepare_startup_connection(
            account_mode="INVALID",
            timeout_seconds=0.0,
        )
    except ValueError:
        invalid_mode_blocked = True

    checks = {
        "immediate_host_connects_without_wait": (
            immediate_ready and immediate_probe_calls == 1
        ),
        "bounded_grace_recovers_transient_unavailability": (
            delayed_ready and delayed_probe_calls == 3
        ),
        "timeout_returns_unavailable": (
            not unavailable_ready and unavailable_probe_calls >= 1
        ),
        "timeout_is_bounded": unavailable_elapsed < 0.20,
        "account_mode_preserved_for_reconnect": (
            unavailable.get_active_account_mode() == "DEMO"
        ),
        "readiness_does_not_create_adapter": (unavailable.get_active_adapter() is None),
        "readiness_does_not_advance_generation": (
            unavailable.session_generation_snapshot == 0
        ),
        "invalid_account_mode_blocked": invalid_mode_blocked,
        "canonical_defaults": (
            CTRADER_STARTUP_READINESS_GRACE_SECONDS == 5.0
            and CTRADER_STARTUP_READINESS_PROBE_TIMEOUT_SECONDS == 0.5
            and CTRADER_STARTUP_READINESS_POLL_INTERVAL_SECONDS == 0.25
        ),
    }

    print("cTrader Startup Readiness result")
    for key, value in checks.items():
        print(f"  {key}={value}")

    ok = all(checks.values())
    print(f"CTRADER_STARTUP_READINESS_CHECK={'OK' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
