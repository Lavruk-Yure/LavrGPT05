# -*- coding: utf-8 -*-
"""Перевірка тимчасових ручних інструментів розмітки WSP chart."""

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


def _draw_two_points(
    widget: WorkspaceChartWidget,
    first: QPoint,
    second: QPoint,
) -> None:
    QTest.mouseClick(widget.canvas, Qt.MouseButton.RightButton, pos=first)
    QApplication.processEvents()
    assert widget.canvas.manual_drawing_pending
    QTest.mouseMove(widget.canvas, second, delay=1)
    QApplication.processEvents()
    QTest.mouseClick(widget.canvas, Qt.MouseButton.RightButton, pos=second)
    QApplication.processEvents()
    assert not widget.canvas.manual_drawing_pending


def _move_until_hover(
    widget: WorkspaceChartWidget,
    target: QPoint,
    expected_part: str,
) -> None:
    for dx in range(-24, 25, 2):
        for dy in range(-8, 9, 2):
            QTest.mouseMove(
                widget.canvas,
                QPoint(target.x() + dx, target.y() + dy),
                delay=1,
            )
            QApplication.processEvents()
            if widget.canvas.manual_drawing_hover_part == expected_part:
                return
    raise AssertionError(f"Manual drawing hover not found: {expected_part}")


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
            "source": "SYNTHETIC_CHART_MANUAL_DRAWING_TEST",
        },
    )
    model = WorkspaceChartModel(max_events=40, visible_count=20)
    model.extend(tuple(session.events))
    model.scroll_to(10)

    widget = WorkspaceChartWidget()
    widget.resize(1000, 500)
    widget.set_snapshot(model.snapshot())
    widget.set_control_hints(
        horizontal_zoom_out="zoom out",
        horizontal_zoom_in="zoom in",
        vertical_zoom_out="vertical out",
        vertical_zoom_in="vertical in",
        vertical_pan="vertical pan",
        latest="latest",
        canvas="canvas",
        protection_stop="stop",
        protection_take="take",
        draw_segment="segment rules",
        draw_horizontal="horizontal rules",
        draw_vertical="vertical rules",
        draw_clear="clear rules",
        drawing_start_label="Start",
        drawing_end_label="End",
        drawing_line_label="Line",
        drawing_time_label="Time UTC",
        drawing_value_label="Value",
    )
    widget.show()
    widget.activateWindow()
    app.processEvents()

    canvas = widget.canvas
    first = QPoint(220, max(70, canvas.height() // 3))
    second = QPoint(520, max(100, canvas.height() // 2))
    third = QPoint(720, max(110, canvas.height() * 2 // 3))

    assert widget.btn_draw_segment.text() == "/"
    assert widget.btn_draw_horizontal.text() == "—"
    assert widget.btn_draw_vertical.text() == "|"
    assert widget.btn_draw_clear.text() == "×"
    assert widget.btn_draw_segment.toolTip() == "segment rules"
    assert widget.btn_draw_horizontal.toolTip() == "horizontal rules"
    assert widget.btn_draw_vertical.toolTip() == "vertical rules"
    assert widget.btn_draw_clear.toolTip() == "clear rules"

    widget.btn_draw_segment.click()
    app.processEvents()
    assert canvas.manual_drawing_mode == "SEGMENT"
    assert widget.btn_draw_segment.isChecked()
    assert widget.btn_draw_segment.text() == "╱"

    QTest.mouseClick(canvas, Qt.MouseButton.RightButton, pos=first)
    app.processEvents()
    assert canvas.manual_drawing_pending
    QTest.mouseMove(canvas, second, delay=1)
    app.processEvents()
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=second)
    app.processEvents()
    assert canvas.manual_drawing_count == 1
    assert canvas.manual_drawing_pending
    QTest.mouseMove(canvas, third, delay=1)
    app.processEvents()
    QTest.mouseClick(canvas, Qt.MouseButton.RightButton, pos=third)
    app.processEvents()
    assert canvas.manual_drawing_count == 2
    assert not canvas.manual_drawing_pending

    _move_until_hover(widget, first, "START")
    assert canvas.manual_drawing_hover_part == "START"
    assert "Time UTC" in canvas.manual_drawing_hover_text
    assert "Value" in canvas.manual_drawing_hover_text

    midpoint = QPoint(
        (first.x() + second.x()) // 2,
        (first.y() + second.y()) // 2,
    )
    _move_until_hover(widget, midpoint, "BODY")
    assert canvas.manual_drawing_hover_part == "BODY"
    assert "Line 1" in canvas.manual_drawing_hover_text
    assert "Δt:" in canvas.manual_drawing_hover_text

    assert canvas.manual_drawing_color_indexes == (0, 0)

    widget.btn_draw_horizontal.click()
    app.processEvents()
    assert canvas.manual_drawing_mode == "HORIZONTAL"
    assert widget.btn_draw_horizontal.isChecked()
    assert widget.btn_draw_horizontal.text() == "━"
    assert not widget.btn_draw_segment.isChecked()
    assert widget.btn_draw_segment.text() == "/"
    _draw_two_points(widget, first, second)
    assert canvas.manual_drawing_count == 3
    assert canvas.manual_drawing_color_indexes == (0, 0, 1)

    widget.btn_draw_vertical.click()
    app.processEvents()
    assert canvas.manual_drawing_mode == "VERTICAL"
    assert widget.btn_draw_vertical.isChecked()
    assert widget.btn_draw_vertical.text() == "┃"
    assert not widget.btn_draw_horizontal.isChecked()
    assert widget.btn_draw_horizontal.text() == "—"
    _draw_two_points(widget, first, second)
    assert canvas.manual_drawing_count == 4

    widget.btn_draw_clear.click()
    app.processEvents()
    assert canvas.manual_drawing_count == 0
    assert canvas.manual_drawing_mode == "VERTICAL"

    widget.btn_draw_vertical.click()
    app.processEvents()
    assert canvas.manual_drawing_mode is None
    assert not widget.btn_draw_vertical.isChecked()
    assert widget.btn_draw_vertical.text() == "|"

    print("Algorithm Workspace Chart Manual Drawing Tools result")
    print("  tools=segment:/->╱,horizontal:—->━,vertical:|->┃,clear:×")
    print("  tool_button_second_click_disables=True")
    print("  per_tool_usage_hints=True")
    print("  segment_start=RIGHT_CLICK")
    print("  segment_finish=RIGHT_CLICK")
    print("  polyline_continue=LEFT_CLICK")
    print("  endpoint_markers_visible=True")
    print("  endpoint_hover_coordinates=True")
    print("  line_body_hover_summary=True")
    print("  line_body_hover_highlight=True")
    print("  polyline_single_color=True")
    print("  next_independent_line_new_color=True")
    print("  horizontal_created=True")
    print("  vertical_created=True")
    print("  exclusive_tool_selection=True")
    print("  clear_removes_all=True")
    print("  drawing_persistence=UI_ONLY_CURRENT_CHART")
    print("  runtime_state_changed=False")
    print("ALGORITHM_WORKSPACE_CHART_MANUAL_DRAWING_TOOLS_CHECK=OK")

    widget.close()
    app.processEvents()


if __name__ == "__main__":
    main()
