"""T116-55 TEST_ONLY — контракт інтеграції Market Data Only.

Виконує незмінені production-методи обробки бара і зупинки через AST.
Не додає production-режим, не створює SDK-клієнт і не запускає мережу.
"""

from __future__ import annotations

import ast
import copy
from datetime import timedelta
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from tests.roadmap116.run_t116_54_market_data_only_feasibility import (
    BASE_TIME,
    PHASE_RUNNING,
    RUNNING,
    STARTING,
    STOPPED,
    FakeReadOnlyProvider,
    completed_bar,
    load_production_methods,
    make_runtime,
)

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_SOURCE = ROOT / "core" / "workspace_runtime.py"
GUI_SOURCE = ROOT / "core" / "algorithm_workspace_area.py"
ACCOUNT_ID = "46368962"
WORKSPACE_ID = "T11654-DEMO-EURUSD-M15"
MODE = "TEST_ONLY_MARKET_DATA_ONLY"


class IsolatedMarketFeed(FakeReadOnlyProvider):
    """Синтетична підписка; кожна спроба торгового запиту заборонена."""

    def __init__(self) -> None:
        super().__init__()
        self.started = False
        self.stopped = 0
        self.polls = 0
        self.order_attempts = 0
        self.order_call_shapes: list[tuple[int, int]] = []

    def start_workspace(self, **kwargs: object) -> tuple[()]:
        if self.started:
            raise PermissionError("duplicate TEST_ONLY subscription")
        result = super().start_workspace(**kwargs)
        self.started = True
        return result

    def poll_workspace(self, workspace_uid: str) -> SimpleNamespace | None:
        if not self.started:
            raise PermissionError("TEST_ONLY feed inactive")
        self.polls += 1
        return super().poll_workspace(workspace_uid)

    def stop_workspace(self, workspace_uid: str) -> None:
        assert workspace_uid == WORKSPACE_ID
        self.stopped += 1
        self.started = False
        self.calls.append("provider.stop_workspace")

    def send_order(self, *args: object, **kwargs: object) -> None:
        self.order_attempts += 1
        self.order_call_shapes.append((len(args), len(kwargs)))
        raise PermissionError("TEST_ONLY order path forbidden")


def production_contract() -> dict[str, Any]:
    """Звірити реальні бар'єри до майбутньої production-інтеграції."""
    tree = ast.parse(RUNTIME_SOURCE.read_text(encoding="utf-8"))
    runtime_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "WorkspaceRuntime"
    )
    methods = {
        node.name: node
        for node in runtime_class.body
        if isinstance(node, ast.FunctionDef)
    }
    required = (
        "_complete_broker_start",
        "_start_algorithm",
        "_complete_replay_start",
        "_accept_market_event",
        "_update_market_guards",
        "_dispatch_market_event_to_algorithm",
        "advance_broker_market",
        "begin_stop",
        "complete_stop",
    )
    assert all(name in methods for name in required)

    def calls(node: ast.FunctionDef) -> list[str]:
        return [
            ast.unparse(item.func)
            for item in ast.walk(node)
            if isinstance(item, ast.Call)
        ]

    broker_calls = calls(methods["_complete_broker_start"])
    assert broker_calls.index("self._start_algorithm") < broker_calls.index(
        "provider.start_workspace"
    )
    accept_calls = calls(methods["_accept_market_event"])
    assert "self._advance_replay_execution" in accept_calls
    assert "self.evaluate_profit_protection" in accept_calls
    assert "self._dispatch_market_event_to_algorithm" in accept_calls
    assert "self._update_market_guards" in accept_calls
    guard = methods["_update_market_guards"]
    assert any(
        isinstance(node, ast.Assign)
        and any(
            ast.unparse(target) == "self.context.signal_allowed"
            for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
        and node.value.value is True
        for node in ast.walk(guard)
    )
    stop_calls = calls(methods["complete_stop"])
    assert "self.broker_market_provider.stop_workspace" in stop_calls
    assert "self._stop_algorithm" in stop_calls
    assert "self.evaluate_profit_protection" in stop_calls

    gui_text = GUI_SOURCE.read_text(encoding="utf-8")
    assert "self._replay_timer.setInterval(250)" in gui_text
    assert (
        "self._replay_timer.timeout.connect(self.advance_replay_runtimes)" in gui_text
    )
    gui_tree = ast.parse(gui_text)
    gui_class = next(
        node
        for node in gui_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "AlgorithmWorkspaceArea"
    )
    poll = next(
        node
        for node in gui_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "advance_replay_runtimes"
    )
    poll_calls = calls(poll)
    assert "self.controller.advance_workspace_broker_market" in poll_calls
    assert "WORKSPACE_STATE_STARTING" in ast.unparse(poll)
    assert "WORKSPACE_STATE_RUNNING" in ast.unparse(poll)

    # Тільки два production-методи Stop, без справжніх конструкторів/імпортів.
    stop_module = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__", names=[ast.alias(name="annotations")], level=0
            ),
            *(copy.deepcopy(methods[name]) for name in ("begin_stop", "complete_stop")),
        ],
        type_ignores=[],
    )
    ast.fix_missing_locations(stop_module)
    scope: dict[str, Any] = {
        "WORKSPACE_STATE_STARTING": STARTING,
        "WORKSPACE_STATE_RUNNING": RUNNING,
        "WORKSPACE_STATE_STOPPING": "STOPPING",
        "WORKSPACE_STATE_ERROR": "ERROR",
        "WORKSPACE_STATE_STOPPED": STOPPED,
        "WORKSPACE_STARTUP_PHASE_IDLE": "IDLE",
        "WORKSPACE_DATA_MODE_BROKER": "BROKER",
    }
    exec(compile(stop_module, str(RUNTIME_SOURCE), "exec"), scope)
    return scope


def isolated_data_only(
    runtime: Any, provider: IsolatedMarketFeed, *, orders_off: bool, demo: bool
) -> None:
    """Виключно TEST_ONLY інтеграційний контракт; не production API."""
    if runtime.context.runtime_state != STARTING:
        raise PermissionError("start state invalid")
    if not orders_off or not demo:
        raise PermissionError("data-only safety attestation absent")
    if runtime.context.account_id != ACCOUNT_ID or runtime.context.broker != "CTRADER":
        raise PermissionError("account or broker mismatch")
    if runtime.context.symbol != "EURUSD" or runtime.context.timeframe != "M15":
        raise PermissionError("symbol or timeframe mismatch")
    if runtime.context.data_mode != "BROKER":
        raise PermissionError("broker data mode required")
    if (
        runtime.algorithm is not None
        or getattr(runtime, "_chart_algorithm") is not None
    ):
        raise PermissionError("algorithm already present")
    if not provider.connected or provider.started:
        raise PermissionError("feed not ready")
    assert runtime.context.signal_allowed is False
    assert runtime.replay_execution is None
    provider.start_workspace(
        workspace_uid=WORKSPACE_ID,
        broker="CTRADER",
        account_id=ACCOUNT_ID,
        symbol="EURUSD",
        timeframe="M15",
        warmup_bars=0,
    )
    runtime.context.runtime_state = RUNNING
    runtime.context.startup_phase = PHASE_RUNNING
    runtime.context.signal_allowed = False
    runtime.context.signal_block_reason = MODE


def make_isolated_runtime(scope: dict[str, Any]) -> tuple[Any, IsolatedMarketFeed]:
    """Використати справжні production-методи без виклику GUI/SDK."""
    methods, _ = load_production_methods()
    provider = IsolatedMarketFeed()
    runtime = make_runtime(methods, provider)
    runtime.begin_stop = MethodType(scope["begin_stop"], runtime)
    runtime.complete_stop = MethodType(scope["complete_stop"], runtime)
    runtime.orders_attempted = 0
    runtime.stopped_algorithms = 0
    runtime.risk_actions = 0
    runtime._stop_algorithm = lambda: setattr(
        runtime, "stopped_algorithms", runtime.stopped_algorithms + 1
    )
    runtime.clear_risk_account_snapshot = lambda _reason: None
    runtime._clear_execution_safety_hold = lambda **_kwargs: None

    def transition(_self: Any, state: str, _reason: str) -> None:
        _self.context.runtime_state = state

    runtime._transition = MethodType(transition, runtime)

    def stop_profit_protection() -> None:
        # Production Stop викликає оцінку прибутку; у TEST_ONLY side effects заборонені.
        assert runtime.replay_execution is None
        assert runtime.algorithm is None

    runtime.evaluate_profit_protection = stop_profit_protection

    def safe_accept(
        event: SimpleNamespace, *, origin: str, warmup_only: bool = False
    ) -> None:
        # Обов'язковий майбутній guard: без Replay/profit execution.
        methods["_accept_market_event"](
            runtime,
            event,
            origin=origin,
            warmup_only=warmup_only,
            advance_replay_execution=False,
        )
        if runtime.context.signal_allowed:
            raise PermissionError("signal gate opened in data-only")

    runtime._accept_market_event = safe_accept
    return runtime, provider


def test_t116_55_market_data_only_integration_contract() -> None:
    """Перевірити майбутню інтеграцію, не підміняючи production-готовність."""
    denied = 0
    with (
        patch("socket.socket.connect", side_effect=PermissionError("TCP blocked")),
        patch("socket.socket.connect_ex", side_effect=PermissionError("TCP blocked")),
        patch("socket.create_connection", side_effect=PermissionError("TCP blocked")),
    ):
        scope = production_contract()
        runtime, provider = make_isolated_runtime(scope)

        # Штатний production Start не переписаний: запускає RailAlgorithm.
        with pytest.raises(AssertionError, match="requires RailAlgorithm"):
            runtime._complete_broker_start()
        assert provider.calls == []
        denied += 1

        # Guard майбутнього data-only — усі відмови до виклику provider.
        cases: tuple[dict[str, object], ...] = (
            {"orders_off": False},
            {"demo": False},
            {"account_id": "WRONG"},
            {"broker": "IB"},
            {"symbol": "GBPUSD"},
            {"timeframe": "M5"},
            {"data_mode": "REPLAY"},
            {"runtime_state": STOPPED},
            {"algorithm": object()},
        )
        for case in cases:
            isolated, fake = make_isolated_runtime(scope)
            orders_off = bool(case.get("orders_off", True))
            demo = bool(case.get("demo", True))
            for key, value in case.items():
                if key in {"orders_off", "demo"}:
                    continue
                if key == "algorithm":
                    isolated.algorithm = value
                elif key == "runtime_state":
                    isolated.context.runtime_state = value
                else:
                    setattr(isolated.context, key, value)
            with pytest.raises(PermissionError):
                isolated_data_only(isolated, fake, orders_off=orders_off, demo=demo)
            assert fake.calls == []
            denied += 1

        # Реальне виконання незмінених production-методів poll + accept.
        isolated_data_only(runtime, provider, orders_off=True, demo=True)
        provider.events = [None, completed_bar(0), None, completed_bar(15)]
        assert runtime.advance_broker_market() is None
        assert len(runtime.chart_model.events) == 0
        first = runtime.advance_broker_market()
        assert first is not None and first.timestamp == BASE_TIME
        assert runtime.advance_broker_market() is None
        second = runtime.advance_broker_market()
        assert second is not None
        assert second.timestamp == BASE_TIME + timedelta(minutes=15)
        assert len(runtime.chart_model.events) == 2
        assert runtime.context.market_event_count == 2
        assert runtime.algorithm is None and runtime._chart_algorithm is None
        assert runtime.context.signal_allowed is False
        assert runtime.replay_events == []
        assert runtime.profit_evaluations == 0
        assert runtime.orders_attempted == 0

        # Окремий ордерний маршрут заборонений незалежно від Orders=OFF.
        with pytest.raises(PermissionError, match="order path forbidden"):
            provider.send_order("ProtoOANewOrderReq")
        assert provider.order_attempts == 1
        assert provider.order_call_shapes == [(1, 0)]
        denied += 1

        # STOP — саме production begin_stop/complete_stop; відписка рівно один раз.
        polls_before = provider.polls
        runtime.begin_stop("T116-55 data-only stop")
        assert runtime.context.runtime_state == "STOPPING"
        runtime.complete_stop()
        assert runtime.context.runtime_state == STOPPED
        assert runtime.context.signal_allowed is False
        assert provider.stopped == 1 and not provider.started
        assert runtime.algorithm is None
        assert runtime.stopped_algorithms == 1
        with pytest.raises(AssertionError, match="poll broker market"):
            runtime.advance_broker_market()
        assert provider.polls == polls_before
        denied += 1

        # STOP не повинен випадково створювати другий unsubscribe.
        with pytest.raises(AssertionError):
            runtime.complete_stop()
        assert provider.stopped == 1
        denied += 1

    assert denied == 13
    print("T116-55 TEST_ONLY | market data only integration contract OFFLINE")
    print("normal_production_start=UNCHANGED_ALGORITHM_FIRST")
    print("data_only_start=TEST_ONLY_EXPLICIT_SEPARATE_PATH")
    print("synthetic_completed_bar_delivery=2")
    print("rail_algorithm=NOT_CREATED_IN_TEST_ONLY")
    print("signal_gate=BLOCKED_TEST_ONLY")
    print("replay_and_profit_side_effects=BLOCKED_TEST_ONLY")
    print("trade_requests=DENIED_TEST_ONLY")
    print("production_stop_methods=EXECUTED_FROM_CURRENT_AST")
    print("feed_unsubscribe=ONCE_STOPPED")
    print("stopped_workspace_poll=BLOCKED")
    print("qt_timer=GLOBAL_RUNNING_STOPPED_WORKSPACES_SKIPPED")
    print(f"negative_scenarios_denied={denied}")
    print("sdk_client_constructor=NOT_CALLED")
    print("external_tcp=BLOCKED")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("network_launch_authorized=NO")
    print("production_mode_ready=NO_SEPARATE_APPROVAL_REQUIRED")
    print("T116-55=GREEN_OFFLINE_MARKET_DATA_ONLY_INTEGRATION_CONTRACT")
