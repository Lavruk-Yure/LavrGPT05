# -*- coding: utf-8 -*-
"""Qt check for splitter and independent MACD pane navigation controls."""

from __future__ import annotations

import math
import os
import sys
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core.workspace_chart import (  # noqa: E402
    WORKSPACE_CHART_ROLE_INDICATOR_HISTOGRAM,
    WORKSPACE_CHART_ROLE_INDICATOR_LINE,
    WorkspaceChartModel,
    WorkspaceChartSeries,
    WorkspaceChartSeriesPoint,
)
from core.workspace_chart_widget import WorkspaceChartWidget  # noqa: E402
from core.workspace_replay import WorkspaceReplayService  # noqa: E402


def _macd_series(snapshot) -> tuple[WorkspaceChartSeries, ...]:
    points_value: list[WorkspaceChartSeriesPoint] = []
    points_signal: list[WorkspaceChartSeriesPoint] = []
    points_histogram: list[WorkspaceChartSeriesPoint] = []
    for index, market_event in enumerate(snapshot.visible_events):
        value = math.sin(index / 3.0) * 0.0008
        signal = math.sin((index - 1) / 3.0) * 0.0006
        points_value.append(
            WorkspaceChartSeriesPoint(
                timestamp=market_event.timestamp,
                value=value,
                source_timestamp=market_event.timestamp,
                available_at=market_event.timestamp,
            )
        )
        points_signal.append(
            WorkspaceChartSeriesPoint(
                timestamp=market_event.timestamp,
                value=signal,
                source_timestamp=market_event.timestamp,
                available_at=market_event.timestamp,
            )
        )
        points_histogram.append(
            WorkspaceChartSeriesPoint(
                timestamp=market_event.timestamp,
                value=value - signal,
                source_timestamp=market_event.timestamp,
                available_at=market_event.timestamp,
            )
        )
    return (
        WorkspaceChartSeries(
            series_code="MACD_VALUE",
            role=WORKSPACE_CHART_ROLE_INDICATOR_LINE,
            label="MACD",
            timeframe="M15",
            profile_uid="00000000-0000-5000-8000-000000000001",
            profile_revision=1,
            points=tuple(points_value),
        ),
        WorkspaceChartSeries(
            series_code="MACD_SIGNAL",
            role=WORKSPACE_CHART_ROLE_INDICATOR_LINE,
            label="Signal",
            timeframe="M15",
            profile_uid="00000000-0000-5000-8000-000000000001",
            profile_revision=1,
            points=tuple(points_signal),
        ),
        WorkspaceChartSeries(
            series_code="MACD_HISTOGRAM",
            role=WORKSPACE_CHART_ROLE_INDICATOR_HISTOGRAM,
            label="Histogram",
            timeframe="M15",
            profile_uid="00000000-0000-5000-8000-000000000001",
            profile_revision=1,
            points=tuple(points_histogram),
        ),
    )


def main() -> None:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    global_qss = (PROJECT_ROOT / "ui" / "common_dialogs.qss").read_text(
        encoding="utf-8"
    )
    app.setStyleSheet(global_qss)

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
            "source": "SYNTHETIC_MACD_NAVIGATION_TEST",
        },
    )
    model = WorkspaceChartModel(max_events=40, visible_count=20)
    model.extend(tuple(session.events))
    model.scroll_to(10)
    base_snapshot = model.snapshot()
    snapshot = replace(base_snapshot, series=_macd_series(base_snapshot))

    widget = WorkspaceChartWidget()
    widget.resize(1000, 620)
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
    widget.macd_canvas.setFocus()
    app.processEvents()

    splitter_present = (
        widget.splitter.count() == 2
        and widget.splitter.orientation() == Qt.Orientation.Vertical
        and widget.macd_panel.isVisible()
    )
    initial_sizes = widget.splitter.sizes()
    widget.splitter.setSizes([240, 260])
    app.processEvents()
    adjusted_sizes = widget.splitter.sizes()
    splitter_resizable = (
        len(initial_sizes) == 2
        and len(adjusted_sizes) == 2
        and adjusted_sizes != initial_sizes
        and adjusted_sizes[0] > 0
        and adjusted_sizes[1] > 0
    )

    widget.splitter.setSizes([250, 250])
    app.processEvents()
    half_sizes = widget.splitter.sizes()
    half_total = sum(half_sizes)
    splitter_half_range = (
        len(half_sizes) == 2
        and half_total > 0
        and abs(half_sizes[0] - half_sizes[1]) <= 40
    )

    widget.splitter.setSizes([380, 80])
    app.processEvents()
    compact_sizes = widget.splitter.sizes()
    compact_total = sum(compact_sizes)
    splitter_compact_macd = (
        len(compact_sizes) == 2
        and compact_total > 0
        and compact_sizes[1] < half_sizes[1]
        and compact_sizes[1] <= max(120, compact_total // 4)
        and widget.macd_canvas.minimumHeight() == 56
        and widget.canvas.minimumHeight() == 120
    )
    control_heights = (
        widget.btn_zoom_out.height(),
        widget.btn_zoom_in.height(),
        widget.btn_vertical_zoom_out.height(),
        widget.btn_vertical_zoom_in.height(),
        widget.btn_macd_vertical_zoom_out.height(),
        widget.btn_macd_vertical_zoom_in.height(),
        widget.btn_latest.height(),
    )
    compact_control_rows = (
        min(control_heights) >= 13
        and max(control_heights) <= 14
        and max(control_heights) - min(control_heights) <= 1
    )
    chart_controls = (
        widget.btn_zoom_out,
        widget.btn_zoom_in,
        widget.btn_vertical_zoom_out,
        widget.btn_vertical_zoom_in,
        widget.btn_macd_vertical_zoom_out,
        widget.btn_macd_vertical_zoom_in,
        widget.btn_latest,
    )
    global_button_qss_overridden = all(
        "min-height: 0px" in button.styleSheet()
        and "padding: 0px 4px" in button.styleSheet()
        for button in chart_controls
    )

    horizontal_requests: list[int] = []
    pan_requests: list[int] = []
    widget.visible_count_requested.connect(horizontal_requests.append)
    widget.visible_start_requested.connect(pan_requests.append)

    QTest.keyClick(widget.macd_canvas, Qt.Key.Key_Plus)
    app.processEvents()
    macd_keyboard_horizontal_zoom = horizontal_requests == [16]

    macd_scale_before = widget.macd_canvas.vertical_scale
    price_scale_before = widget.canvas.vertical_scale
    QTest.keyClick(
        widget.macd_canvas,
        Qt.Key.Key_Plus,
        Qt.KeyboardModifier.ControlModifier,
    )
    app.processEvents()
    macd_keyboard_vertical_zoom = (
        widget.macd_canvas.vertical_scale < macd_scale_before
        and widget.canvas.vertical_scale == price_scale_before
    )

    macd_pan_before = widget.macd_canvas.vertical_pan_ratio
    price_pan_before = widget.canvas.vertical_pan_ratio
    QTest.keyClick(widget.macd_canvas, Qt.Key.Key_Down)
    app.processEvents()
    macd_keyboard_vertical_pan = (
        widget.macd_canvas.vertical_pan_ratio < macd_pan_before
        and widget.canvas.vertical_pan_ratio == price_pan_before
    )

    macd_button_scale = widget.macd_canvas.vertical_scale
    widget.btn_macd_vertical_zoom_in.click()
    app.processEvents()
    macd_y_controls = (
        widget.btn_macd_vertical_zoom_out.text() == "Y −"
        and widget.btn_macd_vertical_zoom_in.text() == "Y +"
        and widget.macd_canvas.vertical_scale < macd_button_scale
    )

    widget.macd_vertical_scrollbar.setValue(35)
    app.processEvents()
    macd_vertical_scrollbar = (
        widget.macd_vertical_scrollbar.minimum() == -200
        and widget.macd_vertical_scrollbar.maximum() == 200
        and widget.macd_canvas.vertical_pan_ratio == -0.35
    )

    pan_requests.clear()
    canvas = widget.macd_canvas
    center_y = max(1, canvas.height() // 2)
    start = QPoint(max(100, canvas.width() // 2), center_y)
    finish = QPoint(min(canvas.width() - 10, start.x() + 150), center_y)
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas, finish, delay=1)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=finish)
    app.processEvents()
    macd_drag_shared_pan = bool(pan_requests) and pan_requests[-1] < 10

    widget.canvas.setFocus()
    price_scale_before = widget.canvas.vertical_scale
    macd_scale_before = widget.macd_canvas.vertical_scale
    QTest.keyClick(
        widget.canvas,
        Qt.Key.Key_Plus,
        Qt.KeyboardModifier.ControlModifier,
    )
    app.processEvents()
    focus_routes_vertical_control = (
        widget.canvas.vertical_scale < price_scale_before
        and widget.macd_canvas.vertical_scale == macd_scale_before
    )

    control_hints = (
        "Ctrl+mouse wheel" in widget.btn_macd_vertical_zoom_out.toolTip()
        and "Ctrl+mouse wheel" in widget.btn_macd_vertical_zoom_in.toolTip()
        and "Up/Down" in widget.macd_vertical_scrollbar.toolTip()
        and "Home" in widget.lbl_help.toolTip()
        and "End" in widget.lbl_help.toolTip()
        and widget.lbl_help.toolTip() == widget.lbl_status.toolTip()
        and widget.canvas_hint_text == widget.lbl_help.toolTip()
        and widget.canvas_hint_delay_ms >= 1500
        and not widget.canvas.toolTip()
        and not widget.macd_canvas.toolTip()
    )
    shared_horizontal_scrollbar = widget.scrollbar.maximum() == 20

    assert splitter_present
    assert splitter_resizable
    assert splitter_half_range
    assert splitter_compact_macd
    assert compact_control_rows, f"control_heights={control_heights}"
    assert global_button_qss_overridden
    assert macd_keyboard_horizontal_zoom
    assert macd_keyboard_vertical_zoom
    assert macd_keyboard_vertical_pan
    assert macd_y_controls
    assert macd_vertical_scrollbar
    assert macd_drag_shared_pan
    assert focus_routes_vertical_control
    assert control_hints
    assert shared_horizontal_scrollbar

    print("Algorithm Workspace Chart MACD Navigation result")
    print(f"  splitter_present={splitter_present}")
    print(f"  splitter_resizable={splitter_resizable}")
    print(f"  splitter_half_range={splitter_half_range}")
    print(f"  splitter_compact_macd={splitter_compact_macd}")
    print(f"  compact_control_rows={compact_control_rows}")
    print(f"  control_heights={control_heights}")
    print(f"  global_button_qss_overridden={global_button_qss_overridden}")
    print(f"  macd_keyboard_horizontal_zoom={macd_keyboard_horizontal_zoom}")
    print(f"  macd_keyboard_vertical_zoom={macd_keyboard_vertical_zoom}")
    print(f"  macd_keyboard_vertical_pan={macd_keyboard_vertical_pan}")
    print(f"  macd_y_controls={macd_y_controls}")
    print(f"  macd_vertical_scrollbar={macd_vertical_scrollbar}")
    print(f"  macd_drag_shared_pan={macd_drag_shared_pan}")
    print(f"  focus_routes_vertical_control={focus_routes_vertical_control}")
    print(f"  control_hints={control_hints}")
    print(f"  shared_horizontal_scrollbar={shared_horizontal_scrollbar}")
    print("ALGORITHM_WORKSPACE_CHART_MACD_NAVIGATION_CHECK=OK")

    widget.close()
    widget.deleteLater()
    app.setStyleSheet("")
    app.processEvents()


if __name__ == "__main__":
    main()
