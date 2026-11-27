"""T116-54 TEST_ONLY — перевірка можливості окремого Market Data Only.

Запускає фактичні методи WorkspaceRuntime через ізольований AST-клас.
Production, GUI, SDK і брокерські з'єднання не створює.
"""

from __future__ import annotations

import ast
import copy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "core" / "workspace_runtime.py"
METHOD_NAMES = (
    "_complete_broker_start",
    "advance_broker_market",
    "_accept_market_event",
    "_dispatch_market_event_to_algorithm",
)
PHASE_WAIT_SPREAD = "WAIT_SPREAD"
PHASE_RUNNING = "RUNNING"
STARTING = "STARTING"
RUNNING = "RUNNING"
STOPPED = "STOPPED"
BASE_TIME = datetime(2026, 11, 27, 13, 0, tzinfo=UTC)


class FakeBrokerMarketError(RuntimeError):
    """Помилка синтетичного джерела ринкових даних."""


class FakeChart:
    """Накопичує лише фактично передані завершені бари."""

    def __init__(self) -> None:
        self.events: list[SimpleNamespace] = []

    def append(self, event: SimpleNamespace) -> None:
        self.events.append(event)


class FakeReadOnlyProvider:
    """Синтетичне джерело без сокетів і ордерів."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.events: list[SimpleNamespace | None] = []
        self.connected = True

    def start_workspace(self, **kwargs: object) -> tuple[()]:
        assert kwargs["broker"] == "CTRADER"
        assert kwargs["account_id"] == "46368962"
        assert kwargs["symbol"] == "EURUSD"
        assert kwargs["timeframe"] == "M15"
        assert kwargs["warmup_bars"] == 0
        self.calls.append("provider.start_workspace")
        return ()

    def is_workspace_broker_connected(self, workspace_uid: str) -> bool:
        assert workspace_uid == "T11654-DEMO-EURUSD-M15"
        return self.connected

    def poll_workspace(self, workspace_uid: str) -> SimpleNamespace | None:
        assert workspace_uid == "T11654-DEMO-EURUSD-M15"
        self.calls.append("provider.poll_workspace")
        return self.events.pop(0) if self.events else None


def load_production_methods() -> tuple[dict[str, Any], ast.ClassDef]:
    """Взяти без змін лише перевірювані методи із поточного дерева."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    runtime_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "WorkspaceRuntime"
    )
    methods = {
        node.name: node
        for node in runtime_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert all(name in methods for name in METHOD_NAMES)

    # Поточний production стартує алгоритм перед підключенням feed.
    start_method = methods["_complete_broker_start"]
    calls = [
        ast.unparse(node.func)
        for node in ast.walk(start_method)
        if isinstance(node, ast.Call)
    ]
    assert "self._start_algorithm" in calls
    assert "provider.start_workspace" in calls
    assert calls.index("self._start_algorithm") < calls.index(
        "provider.start_workspace"
    )

    # У production signal gate допускає True, отже окремий режим потрібен.
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

    # Поточний dispatch уже має безпечний вихід за algorithm=None.
    dispatch = methods["_dispatch_market_event_to_algorithm"]
    assert any(
        isinstance(node, ast.If)
        and ast.unparse(node.test) == "algorithm is None"
        and any(isinstance(stmt, ast.Return) for stmt in node.body)
        for node in ast.walk(dispatch)
    )

    module = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__", names=[ast.alias(name="annotations")], level=0
            ),
            *(copy.deepcopy(methods[name]) for name in METHOD_NAMES),
        ],
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    constants = {
        "WORKSPACE_DATA_MODE_BROKER": "BROKER",
        "WORKSPACE_STATE_STARTING": STARTING,
        "WORKSPACE_STATE_RUNNING": RUNNING,
        "WORKSPACE_STARTUP_PHASE_WAIT_BROKER": "WAIT_BROKER",
        "WORKSPACE_STARTUP_PHASE_SAFETY_HOLD_EXTERNAL_EXPOSURE": (
            "SAFETY_HOLD_EXTERNAL_EXPOSURE"
        ),
        "WORKSPACE_STARTUP_PHASE_WAIT_SPREAD": PHASE_WAIT_SPREAD,
        "WORKSPACE_STARTUP_PHASE_READY": "READY",
        "WORKSPACE_STARTUP_PHASE_RUNNING": PHASE_RUNNING,
        "WorkspaceBrokerMarketError": FakeBrokerMarketError,
        "WorkspaceRuntimeError": RuntimeError,
        "broker_live_trace": SimpleNamespace(
            record_runtime_state=lambda **kwargs: None
        ),
    }
    exec(compile(module, str(SOURCE), "exec"), constants)
    return {name: constants[name] for name in METHOD_NAMES}, runtime_class


def make_runtime(methods: dict[str, Any], provider: FakeReadOnlyProvider) -> Any:
    """Синтетичний WSP: штатні методи, але без алгоритму й мережі."""

    class Probe:
        _complete_broker_start = methods["_complete_broker_start"]
        advance_broker_market = methods["advance_broker_market"]
        _accept_market_event = methods["_accept_market_event"]
        _dispatch_market_event_to_algorithm = methods[
            "_dispatch_market_event_to_algorithm"
        ]

        def __init__(self) -> None:
            self.context = SimpleNamespace(
                workspace_uid="T11654-DEMO-EURUSD-M15",
                broker="CTRADER",
                account_id="46368962",
                symbol="EURUSD",
                timeframe="M15",
                data_mode="BROKER",
                runtime_state=STARTING,
                startup_phase="LOAD_DATA",
                warmup_complete=True,
                warmup_bars_required=0,
                warmup_bars_processed=0,
                spread_limit=0.01,
                spread_ok=False,
                current_spread=None,
                signal_allowed=False,
                signal_block_reason="market data only",
                safety_hold_active=False,
                current_market_event=None,
                market_event_count=0,
                event_processing=False,
            )
            self.broker_market_provider = provider
            self.chart_model = FakeChart()
            self.algorithm = None
            self._chart_algorithm = None
            self.replay_session = None
            self.replay_execution = None
            self._live_quote_received = False
            self._ib_live_boundary_pending = False
            self._ib_warmup_last_timestamp = None
            self.journal: list[tuple[str, str, str, dict[str, object]]] = []
            self.phase_messages: list[str] = []
            self.replay_events: list[SimpleNamespace] = []
            self.fact_order: list[str] = []
            self.profit_evaluations = 0

        def _start_algorithm(self) -> None:
            # У production це реальний конструктор RailAlgorithm.
            self.fact_order.append("algorithm.start")
            raise AssertionError("Production START requires RailAlgorithm")

        def _transition_startup_phase(self, phase: str, message: str) -> None:
            self.phase_messages.append(message)
            self.context.startup_phase = phase

        def _append_journal(
            self, category: str, event: str, message: str, **details: object
        ) -> None:
            self.journal.append((category, event, message, dict(details)))

        def _refresh_execution_safety(self, *, force: bool) -> None:
            assert isinstance(force, bool)
            # Безпека ордерів незалежна від наявності ринкових даних.
            self.context.signal_allowed = False

        def _require_state(self, allowed: set[str], operation: str) -> None:
            assert self.context.runtime_state in allowed, operation

        def _update_market_guards(
            self, event: SimpleNamespace, *, warmup_only: bool = False
        ) -> None:
            assert isinstance(warmup_only, bool)
            self.context.current_spread = event.spread
            self.context.spread_ok = event.spread <= self.context.spread_limit
            self.context.signal_allowed = False
            self.context.signal_block_reason = "TEST_ONLY_MARKET_DATA_ONLY"

        def _advance_replay_execution(self, event: SimpleNamespace) -> None:
            self.replay_events.append(event)

        def evaluate_profit_protection(self) -> None:
            self.profit_evaluations += 1

    return Probe()


def completed_bar(minute: int) -> SimpleNamespace:
    """Підготувати тільки завершений M15-бар на його каузальній межі."""
    return SimpleNamespace(
        timestamp=BASE_TIME + timedelta(minutes=minute),
        broker="CTRADER",
        symbol="EURUSD",
        timeframe="M15",
        open=1.09440,
        high=1.09460,
        low=1.09435,
        close=1.09450,
        bid=1.09449,
        ask=1.09451,
        spread=0.00002,
        volume=0.0,
        source_mode="BROKER",
    )


def test_t116_54_market_data_only_feasibility() -> None:
    """Встановити можливість data-only та відсутність production-вмикання."""
    denied = 0
    with (
        patch("socket.socket.connect", side_effect=AssertionError("TCP blocked")),
        patch("socket.socket.connect_ex", side_effect=AssertionError("TCP blocked")),
        patch("socket.create_connection", side_effect=AssertionError("TCP blocked")),
    ):
        methods, runtime_ast = load_production_methods()
        provider = FakeReadOnlyProvider()
        runtime = make_runtime(methods, provider)

        # Без обходу реальний START зупиняється на запуску RailAlgorithm.
        with pytest.raises(AssertionError, match="requires RailAlgorithm"):
            runtime._complete_broker_start()
        assert provider.calls == []
        assert runtime.fact_order == ["algorithm.start"]
        denied += 1

        # Лише TEST_ONLY ізольоване вимкнення запуску алгоритму.
        runtime._start_algorithm = lambda: None
        runtime._complete_broker_start()
        assert provider.calls == ["provider.start_workspace"]
        assert runtime.algorithm is None
        assert runtime._chart_algorithm is None
        assert runtime.context.signal_allowed is False

        # Стан RUNNING — тільки synthetic harness, не production функція.
        runtime.context.runtime_state = RUNNING
        runtime.context.startup_phase = PHASE_RUNNING
        provider.events = [None, completed_bar(0), None, completed_bar(15)]
        assert runtime.advance_broker_market() is None
        assert runtime.chart_model.events == []
        first = runtime.advance_broker_market()
        assert first is not None and first.timestamp == BASE_TIME
        assert runtime.advance_broker_market() is None
        assert len(runtime.chart_model.events) == 1
        second = runtime.advance_broker_market()
        assert second is not None
        assert second.timestamp == BASE_TIME + timedelta(minutes=15)
        assert len(runtime.chart_model.events) == 2
        assert runtime.context.market_event_count == 2
        assert runtime.algorithm is None
        assert runtime.context.signal_allowed is False
        assert runtime.profit_evaluations == 2
        assert [event.timestamp for event in runtime.replay_events] == [
            BASE_TIME,
            BASE_TIME + timedelta(minutes=15),
        ]
        denied += 1

        runtime.context.runtime_state = STOPPED
        with pytest.raises(AssertionError, match="poll broker market"):
            runtime.advance_broker_market()
        denied += 1

        with pytest.raises(AssertionError):
            provider.start_workspace(
                broker="CTRADER",
                account_id="WRONG",
                symbol="EURUSD",
                timeframe="M15",
                warmup_bars=0,
            )
        assert runtime.algorithm is None
        assert provider.calls.count("provider.start_workspace") == 1
        denied += 1

        # Зіставлення з початковим production-алгоритмом — без змін коду.
        runtime_method_names = {
            node.name for node in runtime_ast.body if isinstance(node, ast.FunctionDef)
        }
        assert {"_start_algorithm", "_complete_broker_start", "begin_start"} <= (
            runtime_method_names
        )

    assert denied == 4
    print("T116-54 TEST_ONLY | Market Data Only feasibility OFFLINE")
    print("production_broker_start=ALGORITHM_FIRST_CONFIRMED")
    print("production_signal_gate=EXPLICIT_BLOCK_REQUIRED")
    print("test_only_algorithm_bypass=VERIFIED_NOT_PRODUCTION_WIRED")
    print("market_feed=READONLY_SYNTHETIC_COMPLETED_BARS")
    print("synthetic_completed_bar_delivery=2")
    print("algorithm_constructed=NO_TEST_ONLY")
    print("signals_allowed=NO_TEST_ONLY")
    print("negative_scenarios_denied=4")
    print("external_tcp=BLOCKED")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("network_launch_authorized=NO")
    print("T116-54=GREEN_OFFLINE_MARKET_DATA_ONLY_FEASIBILITY")
