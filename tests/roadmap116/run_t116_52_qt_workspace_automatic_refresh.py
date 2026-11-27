"""T116-52 TEST_ONLY — автоматичний Qt refresh завершених M15-барів.

Жодного брокерського з'єднання, торгового алгоритму або зміни Session.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.workspace_ownership import WorkspaceOwnedSnapshot
from tests.roadmap116.run_t116_49_ctrader_spot_workspace_integration import (
    DEMO_ACCOUNT_ID,
    build_isolated_chain,
)
from tests.roadmap116.run_t116_50_workspace_runtime_quote_integration import (
    OfflineWorkspaceRuntime,
    feed,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AREA_PATH = PROJECT_ROOT / "core" / "algorithm_workspace_area.py"


def _method(class_name: str, method_name: str) -> ast.FunctionDef:
    """Взяти незмінений метод GUI з поточного production-файлу."""
    tree = ast.parse(AREA_PATH.read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for method in node.body:
                if isinstance(method, ast.FunctionDef) and method.name == method_name:
                    return method
    raise AssertionError(f"Missing GUI method: {class_name}.{method_name}")


def _call(method: ast.FunctionDef, name: str) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == name
        for node in ast.walk(method)
    )


def test_t116_52_qt_timer_source_contract() -> None:
    """Контракт штатного QTimer → broker poll → GUI sync."""
    constructor = _method("AlgorithmWorkspaceArea", "__init__")
    dispatch = _method("AlgorithmWorkspaceArea", "advance_replay_runtimes")
    sync = _method("AlgorithmWorkspaceArea", "_sync_workspace_runtime")

    source = ast.unparse(constructor)
    assert "QTimer(self)" in source
    assert "self._replay_timer.setInterval(250)" in source
    assert "self._replay_timer.timeout.connect(self.advance_replay_runtimes)" in source
    assert "self._replay_timer.start()" in source
    assert _call(dispatch, "advance_workspace_broker_market")
    assert _call(dispatch, "_sync_workspace_runtime")
    assert "event is not None" in ast.unparse(dispatch)
    assert "WORKSPACE_STATE_RUNNING" in ast.unparse(dispatch)
    assert _call(sync, "chart_snapshot")
    assert _call(sync, "set_chart_snapshot")

    print("T116-52 TEST_ONLY | automatic Qt timer STATIC contract")
    print("timer=QT_250MS_ADVANCE_BROKER_MARKET_SYNC_GUI")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("T116-52=GREEN_STATIC_AUTOMATIC_GUI_REFRESH")


def test_t116_52_real_qt_automatic_chart_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Справжній Qt-таймер доставляє тільки завершені бари без ручного render."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6.QtWidgets", reason="LAVRUK PySide6 required")
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    from core.algorithm_workspace import AlgorithmWorkspace, WORKSPACE_DATA_MODE_BROKER
    from core.algorithm_workspace_area import (
        AlgorithmWorkspaceArea,
        AlgorithmWorkspaceWindow,
    )
    from core import algorithm_workspace_area as workspace_area
    from core.workspace_broker_market import RuntimeEngineWorkspaceMarketProvider
    from core.workspace_runtime import WORKSPACE_STATE_STOPPED
    from core.algorithm_workspace_controller import AlgorithmWorkspaceController

    class NoSessionTableWidths:
        """Захист від зчитування і запису UI Session у тесті."""

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    assert isinstance(app, QApplication)

    workspace = AlgorithmWorkspace(
        workspace_uid="11652000-0000-4000-8000-000000000001",
        display_name="T116-52 EURUSD GUI TEST_ONLY",
        broker="CTRADER",
        account_id=str(DEMO_ACCOUNT_ID),
        account_mode="DEMO",
        symbol="EURUSD",
        timeframe="M15",
        algorithm="TEST_ONLY_NO_ALGORITHM",
        data_mode=WORKSPACE_DATA_MODE_BROKER,
        control_mode="MANUAL",
    )

    workspace_uid = workspace.workspace_uid

    with (
        patch("socket.socket.connect", side_effect=AssertionError("TCP blocked")),
        patch("socket.socket.connect_ex", side_effect=AssertionError("TCP blocked")),
        patch("socket.create_connection", side_effect=AssertionError("TCP blocked")),
        patch.object(
            workspace_area, "TableColumnWidthPersistence", NoSessionTableWidths,
        ),
    ):
        adapter, _manager, engine, _traces, subscriptions = build_isolated_chain()
        engine.context = type("ExecutionContext", (), {"execution_mode": "OFF"})()

        def check_binding(broker: str, account_id: str | None) -> None:
            if broker != "CTRADER" or account_id != str(DEMO_ACCOUNT_ID):
                raise AssertionError("Invalid DEMO binding")

        engine.validate_workspace_broker_binding = check_binding
        provider = RuntimeEngineWorkspaceMarketProvider(engine)
        assert provider.start_workspace(
            workspace_uid=workspace_uid,
            broker="CTRADER",
            account_id=str(DEMO_ACCOUNT_ID),
            symbol="EURUSD",
            timeframe="M15",
            warmup_bars=0,
            spread_limit=0.01,
        ) == ()
        runtime = OfflineWorkspaceRuntime(provider)
        runtime.context.workspace_uid = workspace_uid
        setattr(runtime, "_chart_algorithm", None)
        runtime.owned_snapshot = WorkspaceOwnedSnapshot(orders=(), positions=())
        runtime.signals = []
        runtime.replay_session = None
        runtime.replay_settings = {"speed": 1}

        controller = AlgorithmWorkspaceController(repository=MagicMock())
        getattr(controller, "_runtimes")[workspace_uid] = runtime
        area = AlgorithmWorkspaceArea(controller=controller)
        window = AlgorithmWorkspaceWindow(workspace)
        getattr(area, "_windows")[workspace_uid] = window
        timer = getattr(area, "_replay_timer")
        assert timer.isActive()
        assert timer.interval() == 250
        # Під час підготовки UI callbacks ще не мають права виконувати poll.
        timer.stop()

        polls: list[str] = []

        def advance_broker_market(requested_uid: str) -> object:
            assert requested_uid == workspace_uid
            polls.append(requested_uid)
            return runtime.advance_broker_market()

        def qt_cycles() -> None:
            """Обробити справжні timeout Qt, не викликаючи refresh вручну."""
            loop = QEventLoop()
            QTimer.singleShot(360, loop.quit)
            loop.exec()
            app.processEvents()

        try:
            window.resize(1000, 660)
            window.show()
            app.processEvents()
            with (
                patch.object(
                    controller,
                    "advance_workspace_broker_market",
                    side_effect=advance_broker_market,
                ),
                patch.object(
                    window,
                    "set_chart_snapshot",
                    wraps=window.set_chart_snapshot,
                ) as chart_spy,
            ):
                timer.start()
                qt_cycles()
                assert polls, "QTimer did not poll broker workspace"
                baseline_renders = chart_spy.call_count

                def assert_chart(total: int, renders: int) -> None:
                    qt_cycles()
                    assert chart_spy.call_count == baseline_renders + renders
                    snapshot = window.chart_widget.snapshot
                    if total == 0:
                        assert snapshot is None or snapshot.total_events == 0
                    else:
                        assert snapshot is not None
                        assert snapshot.total_events == total
                        assert len(snapshot.visible_events) == total
                    assert runtime.chart_model.total_events == total

                assert_chart(0, 0)
                feed(adapter, 10, bid=109441)
                assert_chart(0, 0)
                feed(adapter, 11, ask=109442)
                assert_chart(0, 0)
                feed(adapter, 14 * 60 + 20, bid=109450, ask=109452)
                assert_chart(0, 0)

                feed(adapter, 15 * 60 + 2, bid=109460, ask=109462)
                assert_chart(1, 1)
                first_snapshot = window.chart_widget.snapshot
                assert first_snapshot is not None
                first = first_snapshot.visible_events[-1]
                current_event = runtime.context.current_market_event
                assert current_event is not None
                assert first.timestamp == current_event.timestamp
                assert_chart(1, 1)  # дубль polling не дублює GUI.

                feed(adapter, 15 * 60 + 40, bid=109470, ask=109472)
                assert_chart(1, 1)
                feed(adapter, 30 * 60 + 3, bid=109480, ask=109482)
                assert_chart(2, 2)
                second_snapshot = window.chart_widget.snapshot
                assert second_snapshot is not None
                assert second_snapshot.visible_events[0].timestamp == first.timestamp
                assert runtime.context.market_event_count == 2

                # STOPPED WSP не опитує брокер і не оновлює chart.
                runtime.context.runtime_state = WORKSPACE_STATE_STOPPED
                baseline_polls = len(polls)
                qt_cycles()
                assert len(polls) == baseline_polls
                assert chart_spy.call_count == baseline_renders + 2

                assert runtime.algorithm is None
                assert runtime.replay_execution is None
                assert engine.context.execution_mode == "OFF"
                assert subscriptions and all(ids == {1} for ids in subscriptions)
                assert not window.chart_widget.canvas.grab().isNull()
        finally:
            timer.stop()
            getattr(area, "_windows").clear()
            getattr(controller, "_runtimes").clear()
            setattr(area, "_shutdown_complete", True)
            window.close()
            area.close()
            provider.stop_workspace(workspace_uid)
            app.processEvents()

    print("T116-52 TEST_ONLY | REAL QT automatic WSP refresh OFFLINE")
    print("qt_timer=EVENT_LOOP_ACTUAL_TIMEOUT_CALLBACKS")
    print("automatic_chart_set_snapshot=VERIFIED_NO_MANUAL_CALL")
    print("completed_bars_only=VERIFIED_TWO_M15_ROLLOVERS")
    print("uncompleted_bar_visible=NO")
    print("stopped_runtime_poll=BLOCKED")
    print("orders_mode=OFF_TEST_ONLY_CONTEXT")
    print("algorithm=NOT_STARTED")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("T116-52=GREEN_QT_AUTOMATIC_COMPLETED_BAR_REFRESH")
