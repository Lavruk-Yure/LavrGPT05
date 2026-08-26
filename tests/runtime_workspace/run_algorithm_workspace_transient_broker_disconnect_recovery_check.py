# -*- coding: utf-8 -*-
"""Regression check for a broker disconnect race during one WSP poll."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_DATA_MODE_BROKER,
    WORKSPACE_STATE_RUNNING,
    WORKSPACE_STATE_STARTING,
    AlgorithmWorkspace,
)
from core.workspace_broker_market import (  # noqa: E402
    RuntimeEngineWorkspaceMarketProvider,
)
from core.workspace_runtime import (  # noqa: E402
    WORKSPACE_STARTUP_PHASE_RUNNING,
    WORKSPACE_STARTUP_PHASE_WAIT_BROKER,
    WORKSPACE_STARTUP_PHASE_WAIT_SPREAD,
    WorkspaceRuntime,
)
from engine.ib_fx_external_exposure import (  # noqa: E402
    IB_FX_GUARD_ALLOWED,
    IBFxExternalExposureGuardDecision,
)
from engine.runtime_broker_health import RuntimeBrokerHealth  # noqa: E402
from engine.runtime_engine import (  # noqa: E402
    IBRuntimeServiceProtocol,
    RuntimeEngine,
)


@dataclass(slots=True)
class FakeIBAdapter:
    connected: bool = True

    def is_connected(self) -> bool:
        return self.connected


class FakeIBRuntimeService(IBRuntimeServiceProtocol):
    """Minimal service that disconnects after a current-health check."""

    def __init__(self) -> None:
        self.adapter = FakeIBAdapter()
        self.health = RuntimeBrokerHealth()
        self.health.set_connected()
        self.disconnect_on_next_quote = False
        self.quote_index = 0
        self.refresh_calls = 0
        self.execution_attempts = 0
        self._quotes = (
            ("2026-08-05T03:45:00Z", 1.34550, 1.34560),
            ("2026-08-05T04:00:00Z", 1.34560, 1.34570),
        )

    def get_broker_health(self) -> RuntimeBrokerHealth:
        return self.health

    def refresh_broker_health(self) -> RuntimeBrokerHealth:
        self.refresh_calls += 1
        if self.adapter.connected:
            self.health.set_connected()
        else:
            self.health.set_safe_disconnected(
                error="IB active adapter is not connected",
            )
        return self.health

    def get_managed_accounts(self) -> list[str]:
        if not self.adapter.connected:
            return []
        return ["DUM513747"]

    def get_forex_quote_snapshot(self, symbol_names: list[str]) -> dict:
        if not symbol_names:
            return {
                "captured_utc": "2026-08-05T03:45:10Z",
                "complete": True,
                "quotes": {},
                "subscribed_symbols": [],
            }
        if self.disconnect_on_next_quote:
            self.disconnect_on_next_quote = False
            self.adapter.connected = False
            self.quote_index = 0
            raise RuntimeError("IB adapter is not connected")

        index = min(self.quote_index, len(self._quotes) - 1)
        timestamp, bid, ask = self._quotes[index]
        self.quote_index += 1
        return {
            "captured_utc": timestamp,
            "complete": True,
            "quotes": {
                symbol: {
                    "symbol_name": symbol,
                    "timestamp": timestamp,
                    "bid": bid,
                    "ask": ask,
                    "volume": 0.0,
                }
                for symbol in symbol_names
            },
            "subscribed_symbols": list(symbol_names),
        }


class TestRuntimeEngine(RuntimeEngine):
    """Real RuntimeEngine connectivity logic with a deterministic guard."""

    def refresh_ib_fx_external_exposure_guard(
        self,
        *,
        account_id: str,
        symbol_name: str,
        runtime_mode: str,
    ) -> IBFxExternalExposureGuardDecision:
        del self, account_id, symbol_name, runtime_mode
        return IBFxExternalExposureGuardDecision(
            allowed=True,
            reason_code=IB_FX_GUARD_ALLOWED,
            reason_text="Synthetic current IB evidence is clear",
        )


def _workspace() -> AlgorithmWorkspace:
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode="PAPER",
        symbol="GBPUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_BROKER,
        parameters={
            "warmup_bars": 0,
            "spread_limit": 0.00020,
        },
    )


def main() -> int:
    engine = TestRuntimeEngine(":memory:")
    service = FakeIBRuntimeService()
    engine.ib_runtime_service = service
    provider = RuntimeEngineWorkspaceMarketProvider(engine)
    runtime = WorkspaceRuntime(
        _workspace(),
        broker_market_provider=provider,
    )

    try:
        runtime.begin_start()
        runtime.complete_start()
        first_event = runtime.advance_broker_market()
        if first_event is None:
            raise AssertionError("Initial live quote was not accepted")
        if runtime.context.runtime_state != WORKSPACE_STATE_RUNNING:
            raise AssertionError("WSP did not reach RUNNING")

        chart_before = runtime.chart_snapshot().events
        algorithm_before = runtime.algorithm
        accounting_before = provider.request_accounting_snapshot()

        service.disconnect_on_next_quote = True
        disconnected_event = runtime.advance_broker_market()
        if disconnected_event is not None:
            raise AssertionError("Disconnect poll unexpectedly produced an event")
        if runtime.context.runtime_state != WORKSPACE_STATE_STARTING:
            raise AssertionError("Transient disconnect did not enter STARTING")
        if runtime.context.startup_phase != WORKSPACE_STARTUP_PHASE_WAIT_BROKER:
            raise AssertionError("Transient disconnect did not enter WAIT_BROKER")
        if runtime.context.last_error is not None:
            raise AssertionError("Transient disconnect was retained as an error")
        if runtime.algorithm is not algorithm_before:
            raise AssertionError("Algorithm instance was replaced or stopped")
        if runtime.chart_snapshot().events != chart_before:
            raise AssertionError("Chart changed during broker disconnect")
        if runtime.can_form_signal():
            raise AssertionError("Signals remained enabled while broker was absent")

        journal_events = [entry.event for entry in runtime.journal]
        if "BROKER_DISCONNECTED" not in journal_events:
            raise AssertionError("Disconnect journal entry is missing")
        if "RUNTIME_ERROR" in journal_events:
            raise AssertionError("Transient disconnect entered RUNTIME_ERROR")
        if "STOPPED" in journal_events:
            raise AssertionError("Algorithm was stopped by transient disconnect")

        service.adapter.connected = True
        duplicate_after_reconnect = runtime.advance_broker_market()
        if duplicate_after_reconnect is not None:
            raise AssertionError("Duplicate reconnect quote was not ignored")
        if runtime.context.startup_phase != WORKSPACE_STARTUP_PHASE_WAIT_SPREAD:
            raise AssertionError("Reconnect did not require a fresh spread")
        if runtime.algorithm is not algorithm_before:
            raise AssertionError("Reconnect replaced the algorithm instance")
        if runtime.chart_snapshot().events != chart_before:
            raise AssertionError("Reconnect duplicate changed the chart")

        recovered_event = runtime.advance_broker_market()
        if recovered_event is None:
            raise AssertionError("Fresh reconnect quote was not accepted")
        if runtime.context.runtime_state != WORKSPACE_STATE_RUNNING:
            raise AssertionError("WSP did not recover to RUNNING")
        if runtime.context.startup_phase != WORKSPACE_STARTUP_PHASE_RUNNING:
            raise AssertionError("Recovered WSP phase is not RUNNING")
        if not runtime.can_form_signal():
            raise AssertionError("Signals did not recover after fresh spread")
        if runtime.algorithm is not algorithm_before:
            raise AssertionError("Recovered WSP replaced the algorithm")
        if runtime.chart_snapshot().events[:1] != chart_before[:1]:
            raise AssertionError("Historical chart prefix was not preserved")

        accounting_after = provider.request_accounting_snapshot()
        if accounting_before.subscription_requests != 1:
            raise AssertionError("Initial subscription request count is invalid")
        if accounting_after.subscription_requests != 1:
            raise AssertionError("Reconnect created a duplicate subscription")
        if accounting_after.active_subscriptions != 1:
            raise AssertionError("Reconnect lost the active subscription")
        if accounting_after.active_references != 1:
            raise AssertionError("Reconnect changed WSP ownership references")
        if accounting_after.retry_requests != 1:
            raise AssertionError("Reconnect retry was not counted once")
        if service.execution_attempts != 0:
            raise AssertionError("Broker execution was attempted")

        final_events = [entry.event for entry in runtime.journal]
        if "BROKER_RECONNECTED" not in final_events:
            raise AssertionError("Reconnect journal entry is missing")
        if "MARKET_DATA_RESUBSCRIBED" not in final_events:
            raise AssertionError("Resubscription journal entry is missing")
        if "RUNTIME_ERROR" in final_events:
            raise AssertionError("Recovered flow contains RUNTIME_ERROR")
        if "STOPPED" in final_events:
            raise AssertionError("Recovered flow stopped the algorithm")

        print("Algorithm Workspace transient broker disconnect result")
        print("  broker=IB")
        print("  disconnect_between_health_check_and_quote=True")
        print("  wait_broker_entered=True")
        print("  error_state_entered=False")
        print("  algorithm_stopped=False")
        print("  chart_preserved=True")
        print("  reconnect_revalidates_binding=True")
        print("  subscription_without_duplicates=True")
        print("  fresh_spread_required=True")
        print("  recovered_running=True")
        print("  broker_execution_attempted=False")
        print("ALGORITHM_WORKSPACE_TRANSIENT_BROKER_DISCONNECT_RECOVERY_CHECK=OK")
        return 0
    finally:
        if runtime.context.runtime_state in {
            WORKSPACE_STATE_STARTING,
            WORKSPACE_STATE_RUNNING,
        }:
            runtime.begin_stop()
            runtime.complete_stop()
        engine.connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
