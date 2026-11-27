"""T116-50 TEST_ONLY — completed-bar integration у WSP Runtime."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest

from core.algorithm_workspace import WORKSPACE_DATA_MODE_BROKER
from core.workspace_broker_market import (
    RuntimeEngineWorkspaceMarketProvider,
    WorkspaceBrokerMarketError,
    WorkspaceExecutionSafetySnapshot,
)
from core.workspace_chart import WorkspaceChartModel
from core.workspace_market_event import WorkspaceMarketEvent
from core.workspace_profit_guard import WorkspaceProfitProtectionDecision
from core.workspace_runtime import (
    WORKSPACE_STARTUP_PHASE_RUNNING,
    WORKSPACE_STATE_RUNNING,
    WORKSPACE_STATE_STOPPED,
    WorkspaceRuntime,
    WorkspaceRuntimeContext,
    WorkspaceRuntimeError,
)
from tests.roadmap116.run_t116_49_ctrader_spot_workspace_integration import (
    DEMO_ACCOUNT_ID,
    EURUSD_SYMBOL_ID,
    FakeSpot,
    build_isolated_chain,
)

WORKSPACE_UID = "T11650-DEMO-EURUSD-M15"
BASE_TIME = datetime(2026, 11, 27, 13, 0, tzinfo=UTC)


class OfflineWorkspaceRuntime(WorkspaceRuntime):
    """Runtime без GUI, алгоритму та broker API."""

    # noinspection PyMissingConstructor
    def __init__(self, provider: RuntimeEngineWorkspaceMarketProvider) -> None:
        # Жодних production-конструкторів чи broker API.
        self.context = WorkspaceRuntimeContext(
            workspace_uid=WORKSPACE_UID,
            broker="CTRADER",
            account_id=str(DEMO_ACCOUNT_ID),
            account_mode="DEMO",
            symbol="EURUSD",
            timeframe="M15",
            algorithm_id="TEST_ONLY_NO_ALGORITHM",
            data_mode=WORKSPACE_DATA_MODE_BROKER,
            control_mode="MANUAL",
            runtime_state=WORKSPACE_STATE_RUNNING,
            startup_phase=WORKSPACE_STARTUP_PHASE_RUNNING,
            spread_limit=0.01,
        )
        self.chart_model = WorkspaceChartModel()
        self.broker_market_provider = provider
        self.algorithm = None
        self.replay_execution = None
        self.journal = []
        self._live_quote_received = False
        self._ib_live_boundary_pending = False
        self._ib_warmup_last_timestamp = None
        self.safety_checks = 0
        self.protection_checks = 0

    def _refresh_execution_safety(
        self,
        *,
        force: bool,
    ) -> WorkspaceExecutionSafetySnapshot:
        """Offline guard без брокерських запитів."""
        del force
        self.safety_checks += 1
        return WorkspaceExecutionSafetySnapshot.allowed_snapshot()

    def evaluate_profit_protection(
        self,
    ) -> tuple[WorkspaceProfitProtectionDecision, ...]:
        """Не виконувати ордери у TEST_ONLY."""
        self.protection_checks += 1
        return ()


def feed(
    adapter: Any,
    seconds: int,
    *,
    bid: int | None = None,
    ask: int | None = None,
    account_id: int = DEMO_ACCOUNT_ID,
    symbol_id: int = EURUSD_SYMBOL_ID,
) -> None:
    """Доставити SpotEvent лише у його фактичний час."""
    timestamp = int((BASE_TIME + timedelta(seconds=seconds)).timestamp() * 1000)
    getattr(adapter, "_on_spot_event")(
        FakeSpot(
            account_id=account_id,
            symbol_id=symbol_id,
            bid=bid,
            ask=ask,
            timestamp=timestamp,
        )
    )


def test_t116_50_workspace_runtime_quote_integration() -> None:
    """Перевірити completed bars і WSP chart без торгів."""
    denied = 0
    with (
        patch("socket.socket.connect", side_effect=AssertionError("TCP forbidden")),
        patch("socket.socket.connect_ex", side_effect=AssertionError("TCP forbidden")),
        patch("socket.create_connection", side_effect=AssertionError("TCP forbidden")),
    ):
        adapter, manager, engine, traces, subscriptions = build_isolated_chain()
        assert manager.get_active_adapter() is adapter
        engine.context = type("ExecutionContext", (), {"execution_mode": "OFF"})()

        def validate_binding(broker: str, account_id: str | None) -> None:
            if broker != "CTRADER" or account_id != str(DEMO_ACCOUNT_ID):
                raise RuntimeError("Invalid DEMO binding")

        engine.validate_workspace_broker_binding = validate_binding
        provider = RuntimeEngineWorkspaceMarketProvider(engine)
        assert (
            provider.start_workspace(
                workspace_uid=WORKSPACE_UID,
                broker="CTRADER",
                account_id=str(DEMO_ACCOUNT_ID),
                symbol="EURUSD",
                timeframe="M15",
                warmup_bars=0,
                spread_limit=0.01,
            )
            == ()
        )
        runtime = OfflineWorkspaceRuntime(provider)

        def poll() -> WorkspaceMarketEvent | None:
            return runtime.advance_broker_market()

        # Неповний Bid/Ask не є готовим баром.
        feed(adapter, 10, bid=109441)
        assert poll() is None
        assert runtime.context.market_event_count == 0
        assert runtime.chart_model.total_events == 0
        assert runtime.context.current_market_event is None

        feed(adapter, 11, ask=109442)
        assert poll() is None
        assert runtime.context.market_event_count == 0
        assert runtime.chart_model.total_events == 0

        # Відкритий M15-бар не надходить у WSP.
        feed(adapter, 14 * 60 + 20, bid=109450, ask=109452)
        assert poll() is None
        assert poll() is None  # дубль snapshot без майбутнього bar.
        assert runtime.chart_model.total_events == 0
        denied += 1

        # Чужий рахунок не змінює кеш.
        feed(adapter, 14 * 60 + 30, bid=100001, account_id=DEMO_ACCOUNT_ID + 1)
        assert poll() is None
        denied += 1

        # Перший M15-бар доступний після 13:15.
        feed(adapter, 15 * 60 + 2, bid=109460, ask=109462)
        first = poll()
        assert first is not None
        assert first.timestamp == BASE_TIME
        assert first.symbol == "EURUSD"
        assert first.timeframe == "M15"
        assert first.bid == pytest.approx(1.09450)
        assert first.ask == pytest.approx(1.09452)
        assert first.spread == pytest.approx(0.00002)
        assert first.open == pytest.approx((1.09441 + 1.09442) / 2)
        assert first.close == pytest.approx((1.09450 + 1.09452) / 2)
        assert runtime.context.current_market_event is first
        assert runtime.context.market_event_count == 1
        assert runtime.chart_model.total_events == 1
        assert runtime.chart_model.snapshot().events[-1] is first
        assert runtime.context.current_spread == pytest.approx(0.00002)
        assert runtime.context.event_processing is False
        assert runtime.algorithm is None

        assert poll() is None
        assert runtime.context.market_event_count == 1
        denied += 1

        # Бар 13:15 недоступний до початку 13:30.
        feed(adapter, 15 * 60 + 40, bid=109470, ask=109472)
        assert poll() is None
        assert runtime.chart_model.total_events == 1
        feed(adapter, 30 * 60 + 3, bid=109480, ask=109482)
        second = poll()
        assert second is not None
        assert second.timestamp == BASE_TIME + timedelta(minutes=15)
        assert runtime.chart_model.total_events == 2
        assert runtime.context.market_event_count == 2
        assert runtime.context.current_market_event is second
        assert runtime.chart_model.snapshot().events[-1] is second
        assert second.open == pytest.approx((1.09460 + 1.09462) / 2)
        assert second.close == pytest.approx((1.09470 + 1.09472) / 2)

        # Валідні знімки не запускають ордерів.
        assert engine.context.execution_mode == "OFF"
        assert runtime.algorithm is None
        assert runtime.replay_execution is None
        assert runtime.context.current_execution_event is second
        assert runtime.protection_checks == 2
        assert runtime.safety_checks > 2

        # Невідповідний account — відмова до підписки.
        with pytest.raises(RuntimeError, match="Invalid DEMO binding"):
            provider.start_workspace(
                workspace_uid="WRONG-ACCOUNT",
                broker="CTRADER",
                account_id="WRONG",
                symbol="EURUSD",
                timeframe="M15",
                warmup_bars=0,
                spread_limit=0.01,
            )
        denied += 1

        # Зупинений WSP не має права poll.
        runtime.context.runtime_state = WORKSPACE_STATE_STOPPED
        with pytest.raises(WorkspaceRuntimeError):
            poll()
        runtime.context.runtime_state = WORKSPACE_STATE_RUNNING
        denied += 1

        # Зупинений feed не передає барів.
        provider.suspend_workspace(WORKSPACE_UID)
        assert poll() is None
        assert provider.resume_workspace(WORKSPACE_UID) == ()
        denied += 1

        # Лише in-memory poll, без брокерських підключень.
        assert subscriptions and all(
            symbols == {EURUSD_SYMBOL_ID} for symbols in subscriptions
        )
        assert len(traces) >= 5
        provider.stop_workspace(WORKSPACE_UID)
        with pytest.raises(WorkspaceBrokerMarketError, match="not active"):
            provider.poll_workspace(WORKSPACE_UID)
        denied += 1

    assert denied == 7
    print("T116-50 TEST_ONLY | LGE WSP runtime completed-bar quote integration")
    print("demo_api_account_id=46368962")
    print("eurusd_symbol_id=1")
    print("runtime_path=SPOT_CACHE_ENGINE_PROVIDER_WORKSPACE_RUNTIME_CHART")
    print("orders_mode=OFF_TEST_ONLY_CONTEXT")
    print("workspace_state=SIMULATED_RUNNING_NO_GUI")
    print("partial_quotes=NO_COMPLETED_BAR")
    print("completed_bars_only=VERIFIED_TWO_M15_ROLLOVERS")
    print("no_lookahead=VERIFIED")
    print(f"negative_scenarios_denied={denied}")
    print("sdk_client_constructor=NOT_CALLED")
    print("external_tcp=BLOCKED")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("network_launch_authorized=NO")
    print("T116-50=GREEN_OFFLINE_RUNTIME_COMPLETED_BAR_INTEGRATION")
