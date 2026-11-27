"""T116-51 TEST_ONLY — реальне Qt-вікно WSP, лише завершені M15-бари.

Жодних broker connect, алгоритмів або запису production Session.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

import pytest

from core.workspace_broker_market import RuntimeEngineWorkspaceMarketProvider
from tests.roadmap116.run_t116_49_ctrader_spot_workspace_integration import (
    DEMO_ACCOUNT_ID,
    build_isolated_chain,
)
from tests.roadmap116.run_t116_50_workspace_runtime_quote_integration import (
    BASE_TIME,
    WORKSPACE_UID,
    OfflineWorkspaceRuntime,
    feed,
)

CORE_DIR = Path(__file__).resolve().parents[2] / "core"


def _class_method(path: Path, class_name: str, method_name: str) -> ast.FunctionDef:
    """Взяти саме production-метод з актуального робочого дерева."""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for method in node.body:
                if isinstance(method, ast.FunctionDef) and method.name == method_name:
                    return method
    raise AssertionError(f"Missing production method: {class_name}.{method_name}")


def _call_count(method: ast.FunctionDef, method_name: str) -> int:
    return sum(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == method_name
        for node in ast.walk(method)
    )


def test_t116_51_gui_wiring_source_contract() -> None:
    """Fail-closed, якщо зміниться фактичний шлях Runtime → GUI."""
    area = CORE_DIR / "algorithm_workspace_area.py"
    chart = CORE_DIR / "workspace_chart_widget.py"

    sync = _class_method(area, "AlgorithmWorkspaceArea", "_sync_workspace_runtime")
    window = _class_method(area, "AlgorithmWorkspaceWindow", "set_chart_snapshot")
    widget = _class_method(chart, "WorkspaceChartWidget", "set_snapshot")

    assert _call_count(sync, "chart_snapshot") == 1
    assert _call_count(sync, "set_chart_snapshot") == 1
    assert _call_count(window, "set_snapshot") == 1
    assert _call_count(widget, "set_snapshot") == 2
    assert _call_count(widget, "_refresh_status") == 1
    print("T116-51 TEST_ONLY | GUI route STATIC source contract")
    print("gui_route=RUNTIME_CHART_SNAPSHOT_WINDOW_WIDGET_CANVAS")
    print("production_changes=0")
    print("real_broker_requests=0")
    print("T116-51=GREEN_STATIC_GUI_WIRING")


def test_t116_51_real_qt_workspace_completed_bars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Створити справжній Qt WSP (не LGE.exe), показати лише completed bars."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6.QtWidgets", reason="LAVRUK PySide6 required")
    from PySide6.QtWidgets import QApplication

    from core import algorithm_workspace_area as workspace_area
    from core.algorithm_workspace import WORKSPACE_DATA_MODE_BROKER, AlgorithmWorkspace
    from core.algorithm_workspace_area import AlgorithmWorkspaceWindow
    from core.workspace_chart_widget import WorkspaceChartWidget

    # У GUI конструкторі є persistence таблиць — відключити читання/запис Session.
    class NoSessionTableWidths:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    assert isinstance(app, QApplication)

    workspace = AlgorithmWorkspace(
        workspace_uid="11651000-0000-4000-8000-000000000001",
        display_name="T116-51 EURUSD GUI TEST_ONLY",
        broker="CTRADER",
        account_id=str(DEMO_ACCOUNT_ID),
        account_mode="DEMO",
        symbol="EURUSD",
        timeframe="M15",
        algorithm="TEST_ONLY_NO_ALGORITHM",
        data_mode=WORKSPACE_DATA_MODE_BROKER,
        control_mode="MANUAL",
    )

    with (
        patch("socket.socket.connect", side_effect=AssertionError("TCP blocked")),
        patch("socket.socket.connect_ex", side_effect=AssertionError("TCP blocked")),
        patch("socket.create_connection", side_effect=AssertionError("TCP blocked")),
        patch.object(
            workspace_area,
            "TableColumnWidthPersistence",
            NoSessionTableWidths,
        ),
    ):
        adapter, manager, engine, _traces, subscriptions = build_isolated_chain()
        assert manager.get_active_adapter() is adapter
        engine.context = type("ExecutionContext", (), {"execution_mode": "OFF"})()

        def check_binding(broker: str, account_id: str | None) -> None:
            if broker != "CTRADER" or account_id != str(DEMO_ACCOUNT_ID):
                raise AssertionError("Unexpected WSP account binding")

        engine.validate_workspace_broker_binding = check_binding
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
        # Тестовий конструктор T116-50 не ініціалізує стан chart-only.
        setattr(runtime, "_chart_algorithm", None)
        window = AlgorithmWorkspaceWindow(workspace)
        try:
            window.resize(1000, 660)
            window.show()
            app.processEvents()
            assert isinstance(window.chart_widget, WorkspaceChartWidget)
            assert window.chart_widget.objectName() == "workspaceChart"
            assert window.tabs_workspace.currentWidget() is window.ui.tabChart
            assert window.account_binding() == (
                "CTRADER",
                str(DEMO_ACCOUNT_ID),
                WORKSPACE_DATA_MODE_BROKER,
            )

            def render_snapshot(expected_count: int) -> None:
                snapshot = runtime.chart_snapshot()
                assert snapshot.total_events == expected_count
                window.set_chart_snapshot(snapshot)
                app.processEvents()
                assert window.chart_widget.snapshot is snapshot
                assert window.chart_widget.snapshot.total_events == expected_count
                assert window.chart_widget.canvas.isVisible()
                assert window.chart_widget.scrollbar.value() == snapshot.visible_start
                if expected_count:
                    assert snapshot.visible_events[-1].timestamp < BASE_TIME.replace(
                        hour=14,
                    )

            # Незавершена свічка не потрапляє у справжній Qt chart.
            render_snapshot(0)
            feed(adapter, 10, bid=109441)
            assert runtime.advance_broker_market() is None
            render_snapshot(0)
            feed(adapter, 11, ask=109442)
            assert runtime.advance_broker_market() is None
            render_snapshot(0)
            feed(adapter, 14 * 60 + 20, bid=109450, ask=109452)
            assert runtime.advance_broker_market() is None
            render_snapshot(0)

            # Один completed bar при rollover 13:15.
            feed(adapter, 15 * 60 + 2, bid=109460, ask=109462)
            first = runtime.advance_broker_market()
            assert first is not None and first.timestamp == BASE_TIME
            render_snapshot(1)
            assert window.chart_widget.snapshot is not None
            assert window.chart_widget.snapshot.visible_events == (first,)

            # Поточний бар не повинен з'явитися на графіку до 13:30.
            feed(adapter, 15 * 60 + 40, bid=109470, ask=109472)
            assert runtime.advance_broker_market() is None
            render_snapshot(1)
            feed(adapter, 30 * 60 + 3, bid=109480, ask=109482)
            second = runtime.advance_broker_market()
            assert second is not None
            render_snapshot(2)
            assert window.chart_widget.snapshot is not None
            assert window.chart_widget.snapshot.visible_events == (first, second)
            assert not window.chart_widget.canvas.grab().isNull()
            assert runtime.algorithm is None
            assert runtime.replay_execution is None
            assert engine.context.execution_mode == "OFF"
            assert runtime.context.market_event_count == 2
            assert subscriptions and all(ids == {1} for ids in subscriptions)
        finally:
            window.close()
            provider.stop_workspace(WORKSPACE_UID)
            app.processEvents()

    print("T116-51 TEST_ONLY | actual Qt WSP window chart OFFLINE")
    print("ui_component=AlgorithmWorkspaceWindow_WorkspaceChartWidget")
    print("completed_bars_only=VERIFIED_TWO_M15_ROLLOVERS")
    print("uncompleted_bar_visible=NO")
    print("orders_mode=OFF_TEST_ONLY_CONTEXT")
    print("algorithm=NOT_STARTED")
    print("session_persistence=DISABLED")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("T116-51=GREEN_QT_WORKSPACE_COMPLETED_BAR_GUI")
