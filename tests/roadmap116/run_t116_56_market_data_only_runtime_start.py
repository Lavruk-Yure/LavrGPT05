"""T116-56 TEST_ONLY — перший production-шлях Market Data Only, без GUI/SDK.

Виконує дійсні методи WorkspaceRuntime через AST; TCP заборонено.
Режим не підключений до кнопки «СТАРТ» і не запускає мережу.
"""

from __future__ import annotations

import ast
import copy
from datetime import timedelta
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any, Callable
from unittest.mock import patch

import pytest

from tests.roadmap116.run_t116_54_market_data_only_feasibility import (
    BASE_TIME,
    FakeReadOnlyProvider,
    completed_bar,
)

SOURCE = Path(__file__).resolve().parents[2] / "core" / "workspace_runtime.py"
ROOT = SOURCE.parents[1]
WORKSPACE_ID = "T11654-DEMO-EURUSD-M15"
BROKER = "CTRADER"
ACCOUNT_ID = "46368962"
STOPPED = "STOPPED"
STARTING = "STARTING"
RUNNING = "RUNNING"

METHODS = (
    "begin_market_data_only_start",
    "begin_start",
    "complete_start",
    "_complete_market_data_only_start",
    "advance_broker_market",
    "_advance_market_data_only",
    "_accept_market_event",
    "_accept_market_data_only_event",
    "begin_stop",
    "complete_stop",
    "fail",
    "evaluate_profit_protection",
)


class MarketDataProvider(FakeReadOnlyProvider):
    """Детермінована read-only заглушка без мережевих конструкторів."""

    def __init__(self) -> None:
        super().__init__()
        self.started = False
        self.unsubscribed = 0
        self.raise_on_start = False
        self.raise_on_poll = False
        self.warmup_events: tuple[SimpleNamespace, ...] = (
            completed_bar(0),
            completed_bar(15),
        )

    def start_workspace(self, **kwargs: object) -> tuple[SimpleNamespace, ...]:
        assert kwargs == {
            "workspace_uid": WORKSPACE_ID,
            "broker": BROKER,
            "account_id": ACCOUNT_ID,
            "symbol": "EURUSD",
            "timeframe": "M15",
            "warmup_bars": 2,
            "spread_limit": 0.01,
        }
        if self.raise_on_start:
            raise RuntimeError("synthetic start failure")
        super().start_workspace(**{**kwargs, "warmup_bars": 0})
        self.started = True
        return self.warmup_events

    def poll_workspace(self, workspace_uid: str) -> SimpleNamespace | None:
        if self.raise_on_poll:
            raise RuntimeError("synthetic poll failure")
        assert self.started
        return super().poll_workspace(workspace_uid)

    def stop_workspace(self, workspace_uid: str) -> None:
        assert workspace_uid == WORKSPACE_ID
        self.unsubscribed += 1
        self.started = False


class FakeChart:
    def __init__(self) -> None:
        self.events: list[SimpleNamespace] = []

    def clear(self) -> None:
        self.events.clear()

    def append(self, event: SimpleNamespace) -> None:
        self.events.append(event)


def production_methods() -> dict[str, Callable[..., Any]]:
    """Взяти справжні production-методи без імпорту повного LGE."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    runtime_class = next(
        item
        for item in tree.body
        if isinstance(item, ast.ClassDef) and item.name == "WorkspaceRuntime"
    )
    methods = {
        node.name: node
        for node in runtime_class.body
        if isinstance(node, ast.FunctionDef)
    }
    assert set(METHODS) <= methods.keys()
    # Нова production-гілка не може бути викликана звичайним GUI START.
    gui_source = (ROOT / "core" / "algorithm_workspace_area.py").read_text(
        encoding="utf-8"
    )
    assert "begin_market_data_only_start" not in gui_source
    assert "begin_workspace_runtime_start" in gui_source

    module = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__",
                names=[ast.alias(name="annotations")],
                level=0,
            ),
            *(copy.deepcopy(methods[name]) for name in METHODS),
        ],
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    scope: dict[str, Any] = {
        "WORKSPACE_DATA_MODE_BROKER": BROKER,
        "WORKSPACE_DATA_MODE_REPLAY": "REPLAY",
        "WORKSPACE_STATE_STOPPED": STOPPED,
        "WORKSPACE_STATE_RESTORED": "RESTORED",
        "WORKSPACE_STATE_STARTING": STARTING,
        "WORKSPACE_STATE_RUNNING": RUNNING,
        "WORKSPACE_STATE_STOPPING": "STOPPING",
        "WORKSPACE_STATE_ERROR": "ERROR",
        "WORKSPACE_STARTUP_PHASE_IDLE": "IDLE",
        "WORKSPACE_STARTUP_PHASE_LOAD_DATA": "LOAD_DATA",
        "WORKSPACE_STARTUP_PHASE_RUNNING": "RUNNING",
        "WorkspaceRuntimeError": RuntimeError,
        "WorkspaceAlgorithmError": type("WorkspaceAlgorithmError", (RuntimeError,), {}),
        "WorkspaceBrokerMarketError": type(
            "WorkspaceBrokerMarketError", (RuntimeError,), {}
        ),
        "WorkspaceReplayError": type("WorkspaceReplayError", (RuntimeError,), {}),
        "WORKSPACE_STARTUP_PHASE_WAIT_BROKER": "WAIT_BROKER",
        "WORKSPACE_STARTUP_PHASE_SAFETY_HOLD_EXTERNAL_EXPOSURE": "SAFETY_HOLD",
        "WORKSPACE_STARTUP_PHASE_WAIT_SPREAD": "WAIT_SPREAD",
        "WORKSPACE_STARTUP_PHASE_READY": "READY",
        "broker_live_trace": SimpleNamespace(
            record_runtime_state=lambda **_kwargs: None
        ),
    }
    exec(compile(module, str(SOURCE), "exec"), scope)
    return {name: scope[name] for name in METHODS}


def make_runtime(
    methods: dict[str, Callable[..., Any]],
    provider: MarketDataProvider | None = None,
) -> tuple[Any, MarketDataProvider]:
    """Зібрати тільки volatile контекст для виконання production-методів."""
    feed = provider if provider is not None else MarketDataProvider()

    class Probe:
        def __init__(self) -> None:
            self.journal: list[tuple[str, str]] = []
            self.side_effects: list[str] = []

    for name, method in methods.items():
        setattr(Probe, name, method)
    runtime = Probe()
    runtime.context = SimpleNamespace(
        workspace_uid=WORKSPACE_ID,
        broker=BROKER,
        account_id=ACCOUNT_ID,
        account_mode="DEMO",
        symbol="EURUSD",
        timeframe="M15",
        data_mode=BROKER,
        runtime_state=STOPPED,
        startup_phase="IDLE",
        warmup_bars_required=2,
        warmup_bars_processed=0,
        warmup_complete=False,
        warmup_required_by_timeframe={},
        warmup_components_by_timeframe={},
        spread_limit=0.01,
        current_spread=None,
        spread_ok=False,
        signal_allowed=False,
        signal_block_reason="runtime is stopped",
        last_error=None,
        current_market_event=None,
        current_execution_event=None,
        market_event_count=0,
        event_processing=False,
        signals_count=0,
        accepted_signals_count=0,
        rejected_signals_count=0,
        risk_equity=None,
        daily_realized_pnl=None,
        profit_decisions_count=0,
        pending_close_decisions_count=0,
    )
    runtime._market_data_only = False
    runtime.algorithm = None
    runtime._chart_algorithm = None
    runtime.replay_execution = None
    runtime.replay_session = None
    runtime.risk_account_snapshot = None
    runtime.historical_summary = None
    runtime._historical_signal_records = []
    runtime._historical_csv_selection_elapsed_seconds = None
    runtime._historical_replay_started_monotonic = None
    runtime._historical_replay_elapsed_seconds = None
    runtime._ib_warmup_last_timestamp = None
    runtime._ib_live_boundary_pending = False
    runtime._live_quote_received = False
    runtime._replay_completion_logged = False
    runtime.profit_decisions = []
    runtime.signals = []
    runtime.chart_model = FakeChart()
    runtime.broker_market_provider = feed

    def require_state(self: Any, states: set[str], operation: str) -> None:
        if self.context.runtime_state not in states:
            raise RuntimeError(f"state denied: {operation}")

    def transition(self: Any, state: str, _reason: str) -> None:
        self.context.runtime_state = state

    def phase(self: Any, state: str, _reason: str) -> None:
        self.context.startup_phase = state

    def append_journal(
        self: Any, category: str, event: str, _message: str, **_details: object
    ) -> None:
        self.journal.append((category, event))

    def forbid_effect(self: Any, *args: object, **kwargs: object) -> None:
        self.side_effects.append(f"FORBIDDEN:args={len(args)}:kwargs={len(kwargs)}")
        raise AssertionError("unexpected algorithm, risk or replay side effect")

    def stop_algorithm(self: Any, *, suppress_errors: bool = False) -> None:
        assert isinstance(suppress_errors, bool)
        assert self.algorithm is None

    def clear_risk(self: Any, _reason: str) -> None:
        assert self.risk_account_snapshot is None

    runtime._require_state = MethodType(require_state, runtime)
    runtime._transition = MethodType(transition, runtime)
    runtime._transition_startup_phase = MethodType(phase, runtime)
    runtime._append_journal = MethodType(append_journal, runtime)
    runtime._clear_pending_replay_execution = lambda: None
    runtime._clear_execution_safety_hold = lambda **_kwargs: None
    runtime._start_algorithm = MethodType(forbid_effect, runtime)
    runtime._dispatch_market_event_to_algorithm = MethodType(forbid_effect, runtime)
    runtime._update_market_guards = MethodType(forbid_effect, runtime)
    runtime._refresh_execution_safety = MethodType(forbid_effect, runtime)
    runtime._advance_replay_execution = MethodType(forbid_effect, runtime)
    runtime._apply_replay_profit_protection = MethodType(forbid_effect, runtime)
    runtime._evaluate_profit_protection_at = MethodType(forbid_effect, runtime)
    runtime._stop_algorithm = MethodType(stop_algorithm, runtime)
    runtime.clear_risk_account_snapshot = MethodType(clear_risk, runtime)
    # Звичайний старт залишаємо окремо: перевіряємо маршрутизацію, а не алгоритм.
    runtime._complete_broker_start = lambda: runtime.side_effects.append(
        "NORMAL_ALGORITHM_FIRST"
    )
    return runtime, feed


def test_t116_56_market_data_only_runtime_start() -> None:
    """Один крок: явний runtime opt-in; звичайний START без змін."""
    methods = production_methods()
    denied = 0
    with (
        patch("socket.socket.connect", side_effect=PermissionError("TCP blocked")),
        patch("socket.socket.connect_ex", side_effect=PermissionError("TCP blocked")),
        patch("socket.create_connection", side_effect=PermissionError("TCP blocked")),
    ):
        normal, normal_provider = make_runtime(methods)
        normal.begin_start()
        normal.complete_start()
        assert normal.side_effects == ["NORMAL_ALGORITHM_FIRST"]
        assert normal._market_data_only is False
        assert normal_provider.calls == []

        # Відмови до запуску provider й до зміни стану.
        for changed in (
            {"data_mode": "REPLAY"},
            {"broker": "IB"},
            {"account_mode": "LIVE"},
            {"account_mode": None},
            {"account_id": ""},
            {"runtime_state": RUNNING},
            {"algorithm": object()},
            {"replay_execution": object()},
            {"broker_market_provider": None},
        ):
            runtime, feed = make_runtime(methods)
            for key, value in changed.items():
                if hasattr(runtime.context, key):
                    setattr(runtime.context, key, value)
                else:
                    setattr(runtime, key, value)
            with pytest.raises(RuntimeError):
                runtime.begin_market_data_only_start()
            assert not feed.started and not feed.calls
            denied += 1

        runtime, feed = make_runtime(methods)
        runtime.begin_market_data_only_start()
        assert runtime.context.runtime_state == STARTING
        assert runtime._market_data_only is True
        with pytest.raises(RuntimeError):
            runtime.begin_market_data_only_start()
        denied += 1
        runtime.complete_start()
        assert runtime.context.runtime_state == RUNNING
        assert runtime.context.startup_phase == RUNNING
        assert runtime.algorithm is None and runtime._chart_algorithm is None
        assert len(runtime.chart_model.events) == 2
        assert runtime.context.market_event_count == 2
        assert runtime.context.warmup_bars_processed == 2
        assert runtime.context.warmup_complete is True
        assert runtime.context.signal_allowed is False
        assert not runtime.side_effects
        assert feed.started and len(feed.calls) == 1

        feed.events = [None, completed_bar(30)]
        assert runtime.advance_broker_market() is None
        third = runtime.advance_broker_market()
        assert third is not None
        assert third.timestamp == BASE_TIME + timedelta(minutes=30)
        assert len(runtime.chart_model.events) == 3
        assert runtime.context.signal_allowed is False
        assert runtime.context.current_execution_event is None
        assert runtime.evaluate_profit_protection() == ()
        assert runtime.profit_decisions == [] and runtime.signals == []
        assert not runtime.side_effects

        # Відхилення чужого символу не створює нового бара, зупиняє feed.
        wrong, bad_feed = make_runtime(methods)
        wrong.begin_market_data_only_start()
        wrong.complete_start()
        bad_feed.events = [
            SimpleNamespace(**{**vars(completed_bar(30)), "symbol": "GBPUSD"})
        ]
        with pytest.raises(RuntimeError, match="polling failed"):
            wrong.advance_broker_market()
        assert wrong.context.runtime_state == "ERROR"
        assert bad_feed.unsubscribed == 1
        assert len(wrong.chart_model.events) == 2
        denied += 1

        # Помилки start та poll завершуються fail-closed без повторів.
        bad, bad_feed = make_runtime(methods)
        bad_feed.raise_on_start = True
        bad.begin_market_data_only_start()
        with pytest.raises(RuntimeError, match="startup failed"):
            bad.complete_start()
        assert bad.context.runtime_state == "ERROR"
        assert bad_feed.unsubscribed == 1
        denied += 1

        other, other_feed = make_runtime(methods)
        other.begin_market_data_only_start()
        other.complete_start()
        other_feed.connected = False
        with pytest.raises(RuntimeError, match="polling failed"):
            other.advance_broker_market()
        assert other.context.runtime_state == "ERROR"
        assert other_feed.unsubscribed == 1
        denied += 1

        # Штатний Stop звільняє feed; profit/signal не виконуються.
        runtime.begin_stop("T116-56 stop")
        runtime.complete_stop()
        assert runtime.context.runtime_state == STOPPED
        assert runtime._market_data_only is False
        assert feed.unsubscribed == 1 and not feed.started
        assert not runtime.side_effects
        with pytest.raises(RuntimeError):
            runtime.advance_broker_market()
        denied += 1

    assert denied == 14
    print("T116-56 TEST_ONLY | initial production Market Data Only runtime path")
    print("normal_start=UNCHANGED_ALGORITHM_FIRST")
    print("data_only=EXPLICIT_OPT_IN_NO_GUI_WIRING")
    print("account_mode=CTRADER_DEMO_ONLY")
    print("synthetic_completed_bars=3")
    print("rail_algorithm=NOT_CREATED")
    print("signals_replay_profit_execution=NOT_CALLED")
    print("stop_unsubscribe=EXACTLY_ONCE")
    print(f"negative_scenarios_denied={denied}")
    print("external_tcp=BLOCKED")
    print("real_broker_requests=0")
    print("network_launch_authorized=NO")
    print("T116-56=GREEN_OFFLINE_PRODUCTION_RUNTIME_ENTRY")
