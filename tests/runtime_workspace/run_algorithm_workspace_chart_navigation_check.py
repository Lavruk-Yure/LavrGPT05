# -*- coding: utf-8 -*-
"""Runtime check for WSP chart horizontal pan and X/Y zoom controls."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core.workspace_chart import WorkspaceChartModel  # noqa: E402
from core.workspace_chart_widget import WorkspaceChartWidget  # noqa: E402
from core.workspace_replay import WorkspaceReplayService  # noqa: E402


def main() -> None:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])

    service = WorkspaceReplayService()
    session = service.create_synthetic_session(
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        replay_settings={
            "start_utc": "2026-07-01T08:00:00Z",
            "event_count": 40,
            "base_price": 1.14500,
            "spread": 0.00014,
            "speed": 1,
            "source": "SYNTHETIC_CHART_NAVIGATION_TEST",
        },
    )
    model = WorkspaceChartModel(max_events=40, visible_count=20)
    model.extend(tuple(session.events))
    model.scroll_to(10)
    snapshot = model.snapshot()

    widget = WorkspaceChartWidget()
    widget.resize(1000, 500)
    widget.set_snapshot(snapshot)
    widget.set_control_hints(
        horizontal_zoom_out="X out: - / mouse wheel down",
        horizontal_zoom_in="X in: + / mouse wheel up",
        vertical_zoom_out="Y out: Ctrl+- / Ctrl+mouse wheel down",
        vertical_zoom_in="Y in: Ctrl++ / Ctrl+mouse wheel up",
        vertical_pan="Vertical pan: Up/Down",
        latest="Latest: End",
        canvas=(
            "Drag / arrows / mouse wheel / Ctrl+mouse wheel / +/- / "
            "Ctrl++ / Home / End"
        ),
    )
    widget.show()
    widget.activateWindow()
    widget.canvas.setFocus()
    app.processEvents()

    horizontal_requests: list[int] = []
    pan_requests: list[int] = []
    widget.visible_count_requested.connect(horizontal_requests.append)
    widget.visible_start_requested.connect(pan_requests.append)

    widget.btn_zoom_in.click()
    horizontal_zoom = horizontal_requests == [16]

    original_vertical_scale = widget.canvas.vertical_scale
    widget.btn_vertical_zoom_in.click()
    vertical_zoom = (
        widget.canvas.vertical_scale < original_vertical_scale
        and widget.canvas.vertical_scale == 0.8
    )

    canvas = widget.canvas
    center_y = max(1, canvas.height() // 2)
    start = QPoint(max(100, canvas.width() // 2), center_y)
    finish = QPoint(min(canvas.width() - 10, start.x() + 150), center_y)
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas, finish, delay=1)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=finish)
    horizontal_drag_pan = bool(pan_requests) and pan_requests[-1] < 10

    x_controls = (
        widget.btn_zoom_out.text() == "X −" and widget.btn_zoom_in.text() == "X +"
    )
    y_controls = (
        widget.btn_vertical_zoom_out.text() == "Y −"
        and widget.btn_vertical_zoom_in.text() == "Y +"
    )
    control_hints = (
        "mouse wheel down" in widget.btn_zoom_out.toolTip()
        and "mouse wheel up" in widget.btn_zoom_in.toolTip()
        and "Ctrl+mouse wheel" in widget.btn_vertical_zoom_out.toolTip()
        and "Ctrl+mouse wheel" in widget.btn_vertical_zoom_in.toolTip()
        and "Up/Down" in widget.vertical_scrollbar.toolTip()
        and "End" in widget.btn_latest.toolTip()
        and "Home" in widget.canvas_hint_text
        and "End" in widget.canvas_hint_text
        and widget.canvas_hint_delay_ms >= 1500
        and not widget.canvas.toolTip()
    )

    horizontal_requests.clear()
    QTest.keyClick(widget.canvas, Qt.Key.Key_Plus)
    app.processEvents()
    keyboard_horizontal_zoom = horizontal_requests == [16]

    vertical_before_keyboard = widget.canvas.vertical_scale
    QTest.keyClick(
        widget.canvas,
        Qt.Key.Key_Plus,
        Qt.KeyboardModifier.ControlModifier,
    )
    app.processEvents()
    keyboard_vertical_zoom = widget.canvas.vertical_scale < vertical_before_keyboard

    pan_requests.clear()
    QTest.keyClick(widget.canvas, Qt.Key.Key_Right)
    app.processEvents()
    keyboard_horizontal_pan = pan_requests == [12]

    vertical_before_pan = widget.canvas.vertical_pan_ratio
    QTest.keyClick(widget.canvas, Qt.Key.Key_Down)
    app.processEvents()
    keyboard_vertical_pan = widget.canvas.vertical_pan_ratio < vertical_before_pan

    pan_requests.clear()
    QTest.keyClick(widget.canvas, Qt.Key.Key_Home)
    app.processEvents()
    keyboard_first = pan_requests == [0]

    latest_requests: list[bool] = []
    widget.latest_requested.connect(lambda: latest_requests.append(True))
    QTest.keyClick(widget.canvas, Qt.Key.Key_End)
    app.processEvents()
    keyboard_latest = latest_requests == [True]

    scrollbar_preserved = widget.scrollbar.maximum() == 20
    vertical_scrollbar = (
        widget.vertical_scrollbar.minimum() == -200
        and widget.vertical_scrollbar.maximum() == 200
    )
    latest_preserved = widget.btn_latest.objectName() == "btnChartLatest"

    assert horizontal_zoom
    assert vertical_zoom
    assert horizontal_drag_pan
    assert x_controls
    assert y_controls
    assert control_hints
    assert keyboard_horizontal_zoom
    assert keyboard_vertical_zoom
    assert keyboard_horizontal_pan
    assert keyboard_vertical_pan
    assert keyboard_first
    assert keyboard_latest
    assert scrollbar_preserved
    assert vertical_scrollbar
    assert latest_preserved

    print("Algorithm Workspace Chart Navigation result")
    print(f"  horizontal_zoom={horizontal_zoom}")
    print(f"  vertical_zoom={vertical_zoom}")
    print(f"  horizontal_drag_pan={horizontal_drag_pan}")
    print(f"  x_controls={x_controls}")
    print(f"  y_controls={y_controls}")
    print(f"  control_hints={control_hints}")
    print(f"  keyboard_horizontal_zoom={keyboard_horizontal_zoom}")
    print(f"  keyboard_vertical_zoom={keyboard_vertical_zoom}")
    print(f"  keyboard_horizontal_pan={keyboard_horizontal_pan}")
    print(f"  keyboard_vertical_pan={keyboard_vertical_pan}")
    print(f"  keyboard_first={keyboard_first}")
    print(f"  keyboard_latest={keyboard_latest}")
    print(f"  scrollbar_preserved={scrollbar_preserved}")
    print(f"  vertical_scrollbar={vertical_scrollbar}")
    print(f"  latest_control_preserved={latest_preserved}")
    print("ALGORITHM_WORKSPACE_CHART_NAVIGATION_CHECK=OK")

    widget.close()
    widget.deleteLater()
    app.processEvents()


if __name__ == "__main__":
    main()
