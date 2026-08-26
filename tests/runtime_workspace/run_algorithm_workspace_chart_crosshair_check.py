# -*- coding: utf-8 -*-
"""Qt check for synchronized chart crosshair and factual OHLC hover data."""

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

from PySide6.QtCore import QEvent, QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from core.workspace_chart import (  # noqa: E402
    WORKSPACE_CHART_ROLE_INDICATOR_HISTOGRAM,
    WORKSPACE_CHART_ROLE_INDICATOR_LINE,
    WorkspaceChartModel,
    WorkspaceChartSeries,
    WorkspaceChartSeriesPoint,
    WorkspaceChartSnapshot,
)
from core.workspace_chart_widget import WorkspaceChartWidget  # noqa: E402
from core.workspace_replay import WorkspaceReplayService  # noqa: E402


def _macd_series(
    snapshot: WorkspaceChartSnapshot,
) -> tuple[WorkspaceChartSeries, ...]:
    value_points: list[WorkspaceChartSeriesPoint] = []
    signal_points: list[WorkspaceChartSeriesPoint] = []
    histogram_points: list[WorkspaceChartSeriesPoint] = []
    for index, market_event in enumerate(snapshot.visible_events):
        value = math.sin(index / 3.0) * 0.0008
        signal = math.sin((index - 1) / 3.0) * 0.0006
        value_points.append(
            WorkspaceChartSeriesPoint(
                timestamp=market_event.timestamp,
                value=value,
                source_timestamp=market_event.timestamp,
                available_at=market_event.timestamp,
            )
        )
        signal_points.append(
            WorkspaceChartSeriesPoint(
                timestamp=market_event.timestamp,
                value=signal,
                source_timestamp=market_event.timestamp,
                available_at=market_event.timestamp,
            )
        )
        histogram_points.append(
            WorkspaceChartSeriesPoint(
                timestamp=market_event.timestamp,
                value=value - signal,
                source_timestamp=market_event.timestamp,
                available_at=market_event.timestamp,
            )
        )
    profile_uid = "00000000-0000-5000-8000-000000000001"
    return (
        WorkspaceChartSeries(
            series_code="MACD_VALUE",
            role=WORKSPACE_CHART_ROLE_INDICATOR_LINE,
            label="MACD",
            timeframe="M15",
            profile_uid=profile_uid,
            profile_revision=1,
            points=tuple(value_points),
        ),
        WorkspaceChartSeries(
            series_code="MACD_SIGNAL",
            role=WORKSPACE_CHART_ROLE_INDICATOR_LINE,
            label="Signal",
            timeframe="M15",
            profile_uid=profile_uid,
            profile_revision=1,
            points=tuple(signal_points),
        ),
        WorkspaceChartSeries(
            series_code="MACD_HISTOGRAM",
            role=WORKSPACE_CHART_ROLE_INDICATOR_HISTOGRAM,
            label="Histogram",
            timeframe="M15",
            profile_uid=profile_uid,
            profile_revision=1,
            points=tuple(histogram_points),
        ),
    )


def _point_in_plot(
    widget: QWidget,
    x_ratio: float,
    y_ratio: float,
) -> QPoint:
    x = widget.width() * float(x_ratio)
    y = widget.height() * float(y_ratio)
    return QPoint(int(round(x)), int(round(y)))


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
            "source": "SYNTHETIC_CHART_CROSSHAIR_TEST",
        },
    )
    model = WorkspaceChartModel(max_events=40, visible_count=20)
    model.extend(tuple(session.events))
    model.scroll_to(10)
    base_snapshot = model.snapshot()
    snapshot = replace(base_snapshot, series=_macd_series(base_snapshot))

    chart = WorkspaceChartWidget()
    chart.resize(1000, 620)
    chart.set_snapshot(snapshot)
    chart.set_control_hints(
        horizontal_zoom_out="X out",
        horizontal_zoom_in="X in",
        vertical_zoom_out="Y out",
        vertical_zoom_in="Y in",
        vertical_pan="Vertical pan",
        latest="Latest",
        canvas="Drag / +/- / Ctrl+mouse wheel / Home / End",
    )
    chart.show()
    chart.activateWindow()
    app.processEvents()

    cross_cursor = (
        chart.canvas.cursor().shape() == Qt.CursorShape.CrossCursor
        and chart.macd_canvas.cursor().shape() == Qt.CursorShape.CrossCursor
    )

    price_point = _point_in_plot(chart.canvas, 0.42, 0.48)
    QTest.mouseMove(chart.canvas, price_point)
    app.processEvents()
    price_index = chart.canvas.hover_index
    price_event = chart.canvas.hovered_event
    price_crosshair_sync = (
        price_index is not None
        and chart.macd_canvas.hover_index == price_index
        and chart.canvas.hover_value is not None
        and chart.macd_canvas.hover_value is None
    )
    time_label_routes_bottom = (
        not chart.canvas.time_label_visible
        and chart.macd_canvas.time_label_visible
    )
    candle_ohlc_available = (
        price_event is not None
        and price_event.high >= max(price_event.open, price_event.close)
        and price_event.low <= min(price_event.open, price_event.close)
    )
    right_price_value_available = chart.canvas.hover_value is not None

    gutter_point = _point_in_plot(chart.canvas, 0.94, 0.48)
    QTest.mouseMove(chart.canvas, gutter_point)
    app.processEvents()
    right_info_gutter_reserved = chart.canvas.hover_index is None

    macd_point = _point_in_plot(chart.macd_canvas, 0.67, 0.35)
    QTest.mouseMove(chart.macd_canvas, macd_point)
    app.processEvents()
    macd_index = chart.macd_canvas.hover_index
    macd_crosshair_sync = (
        macd_index is not None
        and chart.canvas.hover_index == macd_index
        and chart.macd_canvas.hover_value is not None
        and chart.canvas.hover_value is None
        and chart.macd_canvas.time_label_visible
    )
    right_macd_value_available = chart.macd_canvas.hover_value is not None
    macd_values = chart.macd_canvas.hovered_values
    factual_macd_values_available = (
        len(macd_values) == 3
        and {label for label, _value in macd_values}
        == {"MACD", "Signal", "Histogram"}
    )
    canvas_hint_not_obscuring_data = (
        not chart.canvas.toolTip()
        and not chart.macd_canvas.toolTip()
        and chart.lbl_help.text() == "?"
        and "Home" in chart.lbl_help.toolTip()
        and "End" in chart.lbl_help.toolTip()
        and chart.lbl_help.toolTip() == chart.lbl_status.toolTip()
        and chart.canvas_hint_text == chart.lbl_help.toolTip()
        and chart.canvas_hint_delay_ms >= 1500
    )

    leave_event = QEvent(QEvent.Type.Leave)
    QApplication.sendEvent(chart.macd_canvas, leave_event)
    app.processEvents()
    hover_clear = (
        chart.canvas.hover_index is None
        and chart.macd_canvas.hover_index is None
        and chart.canvas.hover_value is None
        and chart.macd_canvas.hover_value is None
    )

    assert cross_cursor
    assert price_crosshair_sync
    assert time_label_routes_bottom
    assert candle_ohlc_available
    assert right_price_value_available
    assert right_info_gutter_reserved
    assert macd_crosshair_sync
    assert right_macd_value_available
    assert factual_macd_values_available
    assert canvas_hint_not_obscuring_data
    assert hover_clear

    print("Algorithm Workspace Chart Crosshair result")
    print(f"  cross_cursor={cross_cursor}")
    print(f"  price_crosshair_sync={price_crosshair_sync}")
    print(f"  time_label_routes_bottom={time_label_routes_bottom}")
    print(f"  candle_ohlc_available={candle_ohlc_available}")
    print(f"  right_price_value_available={right_price_value_available}")
    print(f"  right_info_gutter_reserved={right_info_gutter_reserved}")
    print(f"  macd_crosshair_sync={macd_crosshair_sync}")
    print(f"  right_macd_value_available={right_macd_value_available}")
    print(f"  factual_macd_values_available={factual_macd_values_available}")
    print(f"  canvas_hint_not_obscuring_data={canvas_hint_not_obscuring_data}")
    print(f"  hover_clear={hover_clear}")
    print("ALGORITHM_WORKSPACE_CHART_CROSSHAIR_CHECK=OK")

    chart.close()
    chart.deleteLater()
    app.processEvents()


if __name__ == "__main__":
    main()
