# -*- coding: utf-8 -*-
"""Qt-графік WSP з синхронними price/MACD panels та position overlay.

Модуль малює immutable market snapshot, Alligator/MACD series, crosshair і
навігаційні controls. RoadMap100 додає broker-neutral overlay активних
позицій з Entry/SL/TP без копіювання execution state у WorkspaceChartSnapshot.
Остання multi-resolution execution-подія передається окремим UI overlay: chart
показує актуальну Tick Bid/Ask-релевантну ціну, не домальовуючи M1 candles до
strategy M15 history. У Historical Replay захисні SL/TP можна перетягувати
лише коли Replay призупинений; локальний tooltip і cursor пояснюють drag, а
canvas лише формує UI-запит і ніколи не змінює position state самостійно.
Звичайний horizontal pan, zoom і read-only broker overlay мають залишатися
незалежними від цієї взаємодії. RoadMap101 дозволяє після переходу з
Signals/Positions зафіксувати crosshair на потрібному барі без ручного
позиціонування миші; велика canvas-підказка автоматично гасне через
10 секунд.
RoadMap103 розширює тимчасову ручну розмітку: явний стан інструмента,
RMB-побудову, ламану через LMB, кольори та hover-координати кінцевих точок.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import (
    QEvent,
    QLineF,
    QObject,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QCursor,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QShortcut,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollBar,
    QSizePolicy,
    QSplitter,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from core.workspace_chart import (
    WORKSPACE_CHART_ROLE_INDICATOR_HISTOGRAM,
    WORKSPACE_CHART_ROLE_INDICATOR_LINE,
    WORKSPACE_CHART_ROLE_PRICE_OVERLAY,
    WorkspaceChartSeries,
    WorkspaceChartSnapshot,
)
from core.workspace_market_event import WorkspaceMarketEvent
from core.workspace_ownership import WorkspaceOwnedSnapshot
from engine.runtime_constants import MIN_WORKSPACE_CHART_VISIBLE_EVENTS

_CHART_INFO_GUTTER_WIDTH = 100.0
_CHART_CONTROL_HEIGHT = 14
_CHART_CONTROL_WIDTH = 42
_CHART_CONTROL_FONT_POINT_SIZE = 8
_TOOLTIP_DISPLAY_MS = 10_000
_CHART_CONTROL_STYLE = (
    "QPushButton { min-height: 0px; max-height: 14px; " "padding: 0px 4px; }"
)
_POSITION_LINE_HIT_TOLERANCE = 6.0
_POSITION_LABEL_WIDTH = 188.0
_POSITION_LABEL_HEIGHT = 18.0
_EXECUTION_LABEL_WIDTH = 128.0


@dataclass(frozen=True, slots=True)
class _ProtectionLineHit:
    """Точний результат hit-test для однієї draggable SL/TP лінії."""

    position_id: str
    field_name: str
    price: float
    y: float


@dataclass(frozen=True, slots=True)
class _ManualDrawingAnchor:
    """Одна причинна координата ручної розмітки price chart."""

    event_index: int
    timestamp: datetime
    price: float


@dataclass(frozen=True, slots=True)
class _ManualDrawing:
    """Тимчасова ручна лінія лише для візуального аналізу WSP."""

    mode: str
    start: _ManualDrawingAnchor
    end: _ManualDrawingAnchor
    color_index: int


@dataclass(frozen=True, slots=True)
class _ManualDrawingHit:
    """Hit-test ручної лінії для hover-підсвічування й координат."""

    drawing_index: int
    part: str


_MANUAL_DRAWING_SEGMENT = "SEGMENT"
_MANUAL_DRAWING_HORIZONTAL = "HORIZONTAL"
_MANUAL_DRAWING_VERTICAL = "VERTICAL"
_MANUAL_DRAWING_MODES = {
    _MANUAL_DRAWING_SEGMENT,
    _MANUAL_DRAWING_HORIZONTAL,
    _MANUAL_DRAWING_VERTICAL,
}
_MANUAL_DRAWING_HIT_START = "START"
_MANUAL_DRAWING_HIT_END = "END"
_MANUAL_DRAWING_HIT_BODY = "BODY"
_MANUAL_DRAWING_ENDPOINT_RADIUS = 3.5
_MANUAL_DRAWING_ENDPOINT_HIT_TOLERANCE = 8.0
_MANUAL_DRAWING_BODY_HIT_TOLERANCE = 6.0
_MANUAL_DRAWING_COLOR_RGB = (
    (255, 193, 7),
    (0, 188, 212),
    (233, 30, 99),
    (139, 195, 74),
    (255, 112, 67),
    (171, 71, 188),
)


def _set_chart_control_font(button: QPushButton) -> None:
    font = button.font()
    font.setPointSize(_CHART_CONTROL_FONT_POINT_SIZE)
    button.setFont(font)
    button.setStyleSheet(_CHART_CONTROL_STYLE)
    button.setFixedHeight(_CHART_CONTROL_HEIGHT)


def _chart_info_rect(widget: QWidget, plot: QRectF) -> QRectF:
    left = plot.right() + 8.0
    return QRectF(
        left,
        2.0,
        max(10.0, widget.width() - left - 4.0),
        max(10.0, widget.height() - 6.0),
    )


class WorkspaceCandlestickCanvas(QWidget):
    """Малює OHLC snapshot та broker-neutral overlay активних позицій."""

    zoom_requested = Signal(int)
    pan_requested = Signal(int)
    hover_changed = Signal(int)
    hover_cleared = Signal()
    protection_change_requested = Signal(str, str, float)
    protection_hover_changed = Signal(str)
    protection_hover_cleared = Signal()
    manual_drawing_hover_changed = Signal(str)
    manual_drawing_hover_cleared = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._snapshot: WorkspaceChartSnapshot | None = None
        self._owned_snapshot = WorkspaceOwnedSnapshot(orders=(), positions=())
        self._execution_event: WorkspaceMarketEvent | None = None
        self._empty_text = "No market data."
        self._vertical_scale = 1.0
        self._vertical_pan_ratio = 0.0
        self._drag_start_x: float | None = None
        self._drag_start_visible_start: int | None = None
        self._last_pan_target: int | None = None
        self._hover_index: int | None = None
        self._hover_value: float | None = None
        self._show_time_label = False
        self._protection_drag_enabled = False
        self._protection_drag_hit: _ProtectionLineHit | None = None
        self._protection_preview_price: float | None = None
        self._protection_hover_field: str | None = None
        self._manual_drawing_mode: str | None = None
        self._manual_drawing_start: _ManualDrawingAnchor | None = None
        self._manual_drawing_preview: _ManualDrawingAnchor | None = None
        self._manual_drawings: list[_ManualDrawing] = []
        self._manual_drawing_active_color_index: int | None = None
        self._manual_drawing_next_color_index = 0
        self._manual_drawing_hover_hit: _ManualDrawingHit | None = None
        self._manual_drawing_start_label = "Start"
        self._manual_drawing_end_label = "End"
        self._manual_drawing_line_label = "Line"
        self._manual_drawing_time_label = "Time UTC"
        self._manual_drawing_value_label = "Value"
        self.setMinimumHeight(120)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    @property
    def vertical_scale(self) -> float:
        return self._vertical_scale

    @property
    def vertical_pan_ratio(self) -> float:
        return self._vertical_pan_ratio

    @property
    def hover_index(self) -> int | None:
        return self._hover_index

    @property
    def hover_value(self) -> float | None:
        return self._hover_value

    @property
    def time_label_visible(self) -> bool:
        return self._show_time_label

    @property
    def protection_drag_enabled(self) -> bool:
        return self._protection_drag_enabled

    @property
    def active_position_count(self) -> int:
        return len(self._owned_snapshot.active_positions)

    @property
    def protection_hover_field(self) -> str | None:
        return self._protection_hover_field

    @property
    def execution_event(self) -> WorkspaceMarketEvent | None:
        return self._execution_event

    @property
    def manual_drawing_mode(self) -> str | None:
        return self._manual_drawing_mode

    @property
    def manual_drawing_count(self) -> int:
        return len(self._manual_drawings)

    @property
    def manual_drawing_color_indexes(self) -> tuple[int, ...]:
        return tuple(drawing.color_index for drawing in self._manual_drawings)

    @property
    def manual_drawing_pending(self) -> bool:
        return self._manual_drawing_start is not None

    @property
    def manual_drawing_hover_part(self) -> str | None:
        hit = self._manual_drawing_hover_hit
        return None if hit is None else hit.part

    @property
    def manual_drawing_hover_text(self) -> str:
        hit = self._manual_drawing_hover_hit
        return "" if hit is None else self._manual_drawing_hover_text_for(hit)

    def set_manual_drawing_mode(self, mode: str | None) -> None:
        """Увімкнути тимчасовий інструмент розмітки без persistence."""
        normalized = None if mode is None else str(mode).strip().upper()
        if normalized is not None and normalized not in _MANUAL_DRAWING_MODES:
            raise ValueError(f"Unsupported manual drawing mode: {mode}")
        self._manual_drawing_mode = normalized
        self._manual_drawing_start = None
        self._manual_drawing_preview = None
        self._manual_drawing_active_color_index = None
        self._set_manual_drawing_hover_hit(None)
        self.update()

    def set_manual_drawing_hover_labels(
        self,
        *,
        start_label: str,
        end_label: str,
        line_label: str,
        time_label: str,
        value_label: str,
    ) -> None:
        """Оновити локалізовані підписи координат ручної розмітки."""
        self._manual_drawing_start_label = str(start_label)
        self._manual_drawing_end_label = str(end_label)
        self._manual_drawing_line_label = str(line_label)
        self._manual_drawing_time_label = str(time_label)
        self._manual_drawing_value_label = str(value_label)

    def clear_manual_drawings(self) -> None:
        """Очистити всю тимчасову розмітку поточної діаграми."""
        self._manual_drawings.clear()
        self._manual_drawing_start = None
        self._manual_drawing_preview = None
        self._manual_drawing_active_color_index = None
        self._manual_drawing_next_color_index = 0
        self._set_manual_drawing_hover_hit(None)
        self.update()

    def set_execution_event(self, event: WorkspaceMarketEvent | None) -> None:
        """Оновити останню Replay execution-подію окремо від M15 snapshot."""
        self._execution_event = event
        self.update()

    @property
    def hovered_event(self) -> WorkspaceMarketEvent | None:
        snapshot = self._snapshot
        hover_index = self._hover_index
        if snapshot is None or hover_index is None:
            return None
        if not snapshot.visible_start <= hover_index < snapshot.visible_end:
            return None
        return snapshot.visible_events[hover_index - snapshot.visible_start]

    def set_crosshair_index(
        self,
        index: int | None,
        *,
        show_time_label: bool = False,
    ) -> None:
        self._hover_index = index
        self._hover_value = None
        self._show_time_label = bool(show_time_label)
        self.update()

    def set_time_label_visible(self, visible: bool) -> None:
        self._show_time_label = bool(visible)
        self.update()

    def clear_crosshair(self) -> None:
        self._hover_index = None
        self._hover_value = None
        self._show_time_label = False
        self.update()

    def set_snapshot(self, snapshot: WorkspaceChartSnapshot) -> None:
        self._snapshot = snapshot
        self.update()

    def set_owned_snapshot(self, snapshot: WorkspaceOwnedSnapshot) -> None:
        """Оновити position overlay без зміни market/chart snapshot."""
        self._owned_snapshot = snapshot
        if self._protection_drag_hit is not None:
            position_ids = {
                position.position_id for position in snapshot.active_positions
            }
            if self._protection_drag_hit.position_id not in position_ids:
                self._cancel_protection_drag()
        self.update()

    def set_protection_drag_enabled(self, enabled: bool) -> None:
        """Дозволити SL/TP drag лише ззовні після Replay lifecycle check."""
        self._protection_drag_enabled = bool(enabled)
        if not self._protection_drag_enabled:
            self._cancel_protection_drag()
            self._set_protection_hover_field(None)
        self._refresh_cursor_for_position(self.mapFromGlobal(QCursor.pos()))

    def set_empty_text(self, text: str) -> None:
        self._empty_text = str(text)
        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:
        self.setFocus()
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        direction = -1 if delta > 0 else 1
        modifiers = event.modifiers()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            self.zoom_vertical(direction)
        else:
            self.zoom_requested.emit(direction)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        snapshot = self._snapshot
        if (
            event.button() == Qt.MouseButton.RightButton
            and self._manual_drawing_mode is not None
        ):
            anchor = self._manual_drawing_anchor_at(
                event.position().x(),
                event.position().y(),
            )
            if anchor is not None:
                if self._manual_drawing_start is None:
                    self._begin_manual_drawing(anchor)
                else:
                    self._append_manual_drawing(anchor)
                    self._manual_drawing_start = None
                    self._manual_drawing_preview = None
                    self._manual_drawing_active_color_index = None
                self._set_manual_drawing_hover_hit(None)
                self.update()
                event.accept()
                return
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._manual_drawing_mode == _MANUAL_DRAWING_SEGMENT
            and self._manual_drawing_start is not None
        ):
            anchor = self._manual_drawing_anchor_at(
                event.position().x(),
                event.position().y(),
            )
            if anchor is not None:
                self._append_manual_drawing(anchor)
                self._manual_drawing_start = anchor
                self._manual_drawing_preview = anchor
                self._set_manual_drawing_hover_hit(None)
                self.update()
                event.accept()
                return
        if event.button() == Qt.MouseButton.LeftButton:
            protection_hit = self._protection_hit_at(
                event.position().x(),
                event.position().y(),
            )
            if self._protection_drag_enabled and protection_hit is not None:
                self.setFocus()
                self._protection_drag_hit = protection_hit
                self._protection_preview_price = protection_hit.price
                self.setCursor(Qt.CursorShape.SizeVerCursor)
                event.accept()
                return
        if (
            event.button() == Qt.MouseButton.LeftButton
            and snapshot is not None
            and snapshot.visible_events
        ):
            self.setFocus()
            self._drag_start_x = event.position().x()
            self._drag_start_visible_start = snapshot.visible_start
            self._last_pan_target = snapshot.visible_start
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._manual_drawing_start is not None:
            preview = self._manual_drawing_anchor_at(
                event.position().x(),
                event.position().y(),
            )
            if preview is not None:
                self._manual_drawing_preview = preview
                self.update()
        if self._protection_drag_hit is not None:
            preview_price = self._price_from_y(event.position().y())
            if preview_price is not None:
                self._protection_preview_price = preview_price
                self.update()
            event.accept()
            return
        if self._drag_start_x is None or self._drag_start_visible_start is None:
            self._update_hover_from_position(
                event.position().x(),
                event.position().y(),
            )
            self._refresh_cursor_for_position(event.position())
            event.accept()
            return
        target = self._pan_target_for_x(event.position().x())
        if target is not None and target != self._last_pan_target:
            self._last_pan_target = target
            self.pan_requested.emit(target)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._protection_drag_hit is not None
        ):
            hit = self._protection_drag_hit
            requested_price = self._protection_preview_price
            self._cancel_protection_drag()
            self._refresh_cursor_for_position(event.position())
            if requested_price is not None and not math.isclose(
                requested_price,
                hit.price,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                self.protection_change_requested.emit(
                    hit.position_id,
                    hit.field_name,
                    requested_price,
                )
            event.accept()
            return
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._drag_start_x is not None
        ):
            self._drag_start_x = None
            self._drag_start_visible_start = None
            self._last_pan_target = None
            self._refresh_cursor_for_position(event.position())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        if self._drag_start_x is None and self._protection_drag_hit is None:
            self.clear_crosshair()
            self.hover_cleared.emit()
            self._set_protection_hover_field(None)
            self._set_manual_drawing_hover_hit(None)
        super().leaveEvent(event)

    def _update_hover_from_position(self, x: float, y: float) -> None:
        snapshot = self._snapshot
        if snapshot is None or not snapshot.visible_events:
            return
        plot = self._plot_rect()
        if not plot.contains(QPointF(x, y)):
            if self._hover_index is not None:
                self.clear_crosshair()
                self.hover_cleared.emit()
            return
        count = len(snapshot.visible_events)
        slot_width = plot.width() / max(1, count)
        local_index = int((x - plot.left()) / max(1.0, slot_width))
        local_index = min(count - 1, max(0, local_index))
        price_low, price_high = self._scaled_price_range(snapshot)
        ratio = (plot.bottom() - y) / max(1.0, plot.height())
        value = price_low + ratio * (price_high - price_low)
        self._hover_index = snapshot.visible_start + local_index
        self._hover_value = value
        self.update()
        self.hover_changed.emit(self._hover_index)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        if self._manual_drawing_mode is not None:
            event.accept()
            return
        super().contextMenuEvent(event)

    def _manual_drawing_anchor_at(
        self,
        x: float,
        y: float,
    ) -> _ManualDrawingAnchor | None:
        snapshot = self._snapshot
        if snapshot is None or not snapshot.visible_events:
            return None
        plot = self._plot_rect()
        point = QPointF(float(x), float(y))
        if not plot.contains(point):
            return None
        count = len(snapshot.visible_events)
        slot_width = plot.width() / max(1, count)
        local_index = int((float(x) - plot.left()) / max(1.0, slot_width))
        local_index = min(count - 1, max(0, local_index))
        price = self._price_from_y(float(y))
        if price is None:
            return None
        event = snapshot.visible_events[local_index]
        return _ManualDrawingAnchor(
            event_index=snapshot.visible_start + local_index,
            timestamp=event.timestamp,
            price=price,
        )

    def _begin_manual_drawing(self, start: _ManualDrawingAnchor) -> None:
        self._manual_drawing_start = start
        self._manual_drawing_preview = start
        self._manual_drawing_active_color_index = self._manual_drawing_next_color_index
        self._manual_drawing_next_color_index += 1

    def _append_manual_drawing(self, end: _ManualDrawingAnchor) -> None:
        start = self._manual_drawing_start
        mode = self._manual_drawing_mode
        if start is None or mode is None:
            return
        normalized_end = self._normalized_manual_drawing_end(mode, start, end)
        color_index = self._manual_drawing_active_color_index
        if color_index is None:
            color_index = self._manual_drawing_next_color_index
            self._manual_drawing_next_color_index += 1
        self._manual_drawings.append(
            _ManualDrawing(
                mode=mode,
                start=start,
                end=normalized_end,
                color_index=color_index,
            )
        )

    @staticmethod
    def _normalized_manual_drawing_end(
        mode: str,
        start: _ManualDrawingAnchor,
        end: _ManualDrawingAnchor,
    ) -> _ManualDrawingAnchor:
        if mode == _MANUAL_DRAWING_HORIZONTAL:
            return _ManualDrawingAnchor(
                event_index=end.event_index,
                timestamp=end.timestamp,
                price=start.price,
            )
        if mode == _MANUAL_DRAWING_VERTICAL:
            return _ManualDrawingAnchor(
                event_index=start.event_index,
                timestamp=start.timestamp,
                price=end.price,
            )
        return end

    @staticmethod
    def _manual_drawing_color(index: int) -> QColor:
        red, green, blue = _MANUAL_DRAWING_COLOR_RGB[
            int(index) % len(_MANUAL_DRAWING_COLOR_RGB)
        ]
        return QColor(red, green, blue)

    @staticmethod
    def _distance_to_segment(
        point: QPointF,
        start: QPointF,
        end: QPointF,
    ) -> float:
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length_squared = dx * dx + dy * dy
        if length_squared <= 1e-12:
            return math.hypot(point.x() - start.x(), point.y() - start.y())
        projection = (
            (point.x() - start.x()) * dx + (point.y() - start.y()) * dy
        ) / length_squared
        projection = min(1.0, max(0.0, projection))
        closest_x = start.x() + projection * dx
        closest_y = start.y() + projection * dy
        return math.hypot(point.x() - closest_x, point.y() - closest_y)

    @staticmethod
    def _manual_drawing_point_for(
        anchor: _ManualDrawingAnchor,
        *,
        plot: QRectF,
        snapshot: WorkspaceChartSnapshot,
        price_low: float,
        price_span: float,
    ) -> QPointF:
        slot_width = plot.width() / max(1, len(snapshot.visible_events))
        local_index = anchor.event_index - snapshot.visible_start
        x = plot.left() + slot_width * (local_index + 0.5)
        y = plot.bottom() - (anchor.price - price_low) / price_span * plot.height()
        return QPointF(x, y)

    def _manual_drawing_line_for(
        self,
        drawing: _ManualDrawing,
        *,
        plot: QRectF,
        snapshot: WorkspaceChartSnapshot,
        price_low: float,
        price_span: float,
    ) -> QLineF:
        return QLineF(
            self._manual_drawing_point_for(
                drawing.start,
                plot=plot,
                snapshot=snapshot,
                price_low=price_low,
                price_span=price_span,
            ),
            self._manual_drawing_point_for(
                drawing.end,
                plot=plot,
                snapshot=snapshot,
                price_low=price_low,
                price_span=price_span,
            ),
        )

    def _manual_drawing_hit_at(self, x: float, y: float) -> _ManualDrawingHit | None:
        snapshot = self._snapshot
        if snapshot is None or not snapshot.visible_events or not self._manual_drawings:
            return None
        plot = self._plot_rect()
        point = QPointF(float(x), float(y))
        if not plot.contains(point):
            return None
        price_low, price_high = self._scaled_price_range(snapshot)
        price_span = price_high - price_low
        if price_span <= 0.0:
            return None

        body_candidates: list[tuple[float, int]] = []
        for index, drawing in enumerate(self._manual_drawings):
            line = self._manual_drawing_line_for(
                drawing,
                plot=plot,
                snapshot=snapshot,
                price_low=price_low,
                price_span=price_span,
            )
            start_distance = math.hypot(
                point.x() - line.p1().x(),
                point.y() - line.p1().y(),
            )
            if start_distance <= _MANUAL_DRAWING_ENDPOINT_HIT_TOLERANCE:
                return _ManualDrawingHit(index, _MANUAL_DRAWING_HIT_START)
            end_distance = math.hypot(
                point.x() - line.p2().x(),
                point.y() - line.p2().y(),
            )
            if end_distance <= _MANUAL_DRAWING_ENDPOINT_HIT_TOLERANCE:
                return _ManualDrawingHit(index, _MANUAL_DRAWING_HIT_END)
            body_distance = self._distance_to_segment(point, line.p1(), line.p2())
            if body_distance <= _MANUAL_DRAWING_BODY_HIT_TOLERANCE:
                body_candidates.append((body_distance, index))
        if not body_candidates:
            return None
        body_candidates.sort(key=lambda item: item[0])
        return _ManualDrawingHit(body_candidates[0][1], _MANUAL_DRAWING_HIT_BODY)

    def _manual_drawing_hover_text_for(self, hit: _ManualDrawingHit) -> str:
        if not 0 <= hit.drawing_index < len(self._manual_drawings):
            return ""
        drawing = self._manual_drawings[hit.drawing_index]
        if hit.part == _MANUAL_DRAWING_HIT_START:
            return self._manual_drawing_anchor_hover_text(
                self._manual_drawing_start_label,
                drawing.start,
            )
        if hit.part == _MANUAL_DRAWING_HIT_END:
            return self._manual_drawing_anchor_hover_text(
                self._manual_drawing_end_label,
                drawing.end,
            )

        start = drawing.start
        end = drawing.end
        delta_seconds = (end.timestamp - start.timestamp).total_seconds()
        delta_minutes = int(round(delta_seconds / 60.0))
        delta_price = end.price - start.price
        return (
            f"{self._manual_drawing_line_label} {hit.drawing_index + 1}\n"
            f"{self._manual_drawing_start_label}: "
            f"{start.timestamp.strftime('%Y-%m-%d %H:%M UTC')} | {start.price:.5f}\n"
            f"{self._manual_drawing_end_label}: "
            f"{end.timestamp.strftime('%Y-%m-%d %H:%M UTC')} | {end.price:.5f}\n"
            f"Δt: {delta_minutes:+d} min\n"
            f"Δ: {delta_price:+.5f}"
        )

    def _manual_drawing_anchor_hover_text(
        self,
        title: str,
        anchor: _ManualDrawingAnchor,
    ) -> str:
        return (
            f"{title}\n"
            f"{self._manual_drawing_time_label}:\n"
            f"{anchor.timestamp.strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"{self._manual_drawing_value_label}:\n"
            f"{anchor.price:.5f}"
        )

    def _set_manual_drawing_hover_hit(self, hit: _ManualDrawingHit | None) -> None:
        if hit == self._manual_drawing_hover_hit:
            return
        self._manual_drawing_hover_hit = hit
        self.update()
        if hit is None:
            self.manual_drawing_hover_cleared.emit()
            return
        text = self._manual_drawing_hover_text_for(hit)
        if text:
            self.manual_drawing_hover_changed.emit(text)

    def _active_position_levels(self) -> tuple[float, ...]:
        values: list[float] = []
        for position in self._owned_snapshot.active_positions:
            for value in (
                position.entry_price,
                position.stop_loss,
                position.take_profit,
            ):
                if value is not None and math.isfinite(value):
                    values.append(float(value))
        return tuple(values)

    def _price_y(self, price: float) -> float | None:
        snapshot = self._snapshot
        if snapshot is None or not snapshot.visible_events:
            return None
        plot = self._plot_rect()
        price_low, price_high = self._scaled_price_range(snapshot)
        price_span = price_high - price_low
        if price_span <= 0.0:
            return None
        return plot.bottom() - (price - price_low) / price_span * plot.height()

    def _price_from_y(self, y: float) -> float | None:
        snapshot = self._snapshot
        if snapshot is None or not snapshot.visible_events:
            return None
        plot = self._plot_rect()
        clamped_y = min(plot.bottom(), max(plot.top(), float(y)))
        price_low, price_high = self._scaled_price_range(snapshot)
        ratio = (plot.bottom() - clamped_y) / max(1.0, plot.height())
        return price_low + ratio * (price_high - price_low)

    def _protection_hit_at(self, x: float, y: float) -> _ProtectionLineHit | None:
        if not self._protection_drag_enabled:
            return None
        plot = self._plot_rect()
        if x < plot.left() or x > plot.right():
            return None
        candidates: list[tuple[float, _ProtectionLineHit]] = []
        for position in self._owned_snapshot.active_positions:
            for field_name, price in (
                ("stop_loss", position.stop_loss),
                ("take_profit", position.take_profit),
            ):
                if price is None:
                    continue
                line_y = self._price_y(price)
                if line_y is None:
                    continue
                distance = abs(float(y) - line_y)
                if distance <= _POSITION_LINE_HIT_TOLERANCE:
                    candidates.append(
                        (
                            distance,
                            _ProtectionLineHit(
                                position_id=position.position_id,
                                field_name=field_name,
                                price=float(price),
                                y=line_y,
                            ),
                        )
                    )
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def _refresh_cursor_for_position(self, position: QPoint | QPointF) -> None:
        if self._protection_drag_hit is not None:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
            self._set_protection_hover_field(self._protection_drag_hit.field_name)
            self._set_manual_drawing_hover_hit(None)
            return
        drawing_hit = self._manual_drawing_hit_at(
            float(position.x()),
            float(position.y()),
        )
        if drawing_hit is not None and self._manual_drawing_start is None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self._set_protection_hover_field(None)
            self._set_manual_drawing_hover_hit(drawing_hit)
            return
        hit = self._protection_hit_at(float(position.x()), float(position.y()))
        if hit is not None:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
            self._set_protection_hover_field(hit.field_name)
            self._set_manual_drawing_hover_hit(None)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)
            self._set_protection_hover_field(None)
            self._set_manual_drawing_hover_hit(None)

    def _set_protection_hover_field(self, field_name: str | None) -> None:
        normalized = str(field_name or "").strip() or None
        if normalized == self._protection_hover_field:
            return
        self._protection_hover_field = normalized
        if normalized is None:
            self.protection_hover_cleared.emit()
        else:
            self.protection_hover_changed.emit(normalized)

    def _cancel_protection_drag(self) -> None:
        self._protection_drag_hit = None
        self._protection_preview_price = None
        self.update()

    def zoom_vertical(self, direction: int) -> None:
        factor = 0.8 if int(direction) < 0 else 1.25
        self._vertical_scale = min(8.0, max(0.25, self._vertical_scale * factor))
        self.update()

    def set_vertical_pan_ratio(self, ratio: float) -> None:
        self._vertical_pan_ratio = min(2.0, max(-2.0, float(ratio)))
        self.update()

    def _pan_target_for_x(self, current_x: float) -> int | None:
        snapshot = self._snapshot
        start_x = self._drag_start_x
        start_visible = self._drag_start_visible_start
        if snapshot is None or start_x is None or start_visible is None:
            return None
        count = max(1, len(snapshot.visible_events))
        slot_width = self._plot_width() / count
        pixel_delta = float(current_x) - start_x
        bar_delta = int(round(pixel_delta / max(1.0, slot_width)))
        return start_visible - bar_delta

    def _plot_rect(self) -> QRectF:
        left_margin = 68.0
        right_margin = _CHART_INFO_GUTTER_WIDTH + 12.0
        top_margin = 16.0
        bottom_margin = 34.0
        return QRectF(
            left_margin,
            top_margin,
            max(10.0, self.width() - left_margin - right_margin),
            max(10.0, self.height() - top_margin - bottom_margin),
        )

    def _plot_width(self) -> float:
        return self._plot_rect().width()

    def paintEvent(self, event: QPaintEvent) -> None:
        _ = event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.base())

        snapshot = self._snapshot
        if snapshot is None or not snapshot.visible_events:
            painter.setPen(palette.placeholderText().color())
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                self._empty_text,
            )
            return

        events = snapshot.visible_events
        plot = self._plot_rect()

        price_low, price_high = self._scaled_price_range(snapshot)
        price_span = price_high - price_low

        self._draw_grid(
            painter,
            plot,
            price_low,
            price_high,
        )
        self._draw_candles(
            painter,
            plot,
            events,
            price_low,
            price_span,
        )
        self._draw_price_overlays(
            painter,
            plot,
            snapshot,
            price_low,
            price_span,
        )
        self._draw_current_prices(
            painter,
            plot,
            snapshot,
            price_low,
            price_span,
        )
        self._draw_execution_price(
            painter,
            plot,
            price_low,
            price_span,
        )
        self._draw_position_overlays(
            painter,
            plot,
            price_low,
            price_span,
        )
        self._draw_manual_drawings(
            painter,
            plot,
            snapshot,
            price_low,
            price_span,
        )
        self._draw_time_axis(painter, plot, events)
        self._draw_cursor(painter, plot, snapshot)
        self._draw_hover_crosshair(
            painter,
            plot,
            snapshot,
            price_low,
            price_span,
        )

    def _draw_manual_drawings(
        self,
        painter: QPainter,
        plot: QRectF,
        snapshot: WorkspaceChartSnapshot,
        price_low: float,
        price_span: float,
    ) -> None:
        if not self._manual_drawings and self._manual_drawing_start is None:
            return

        painter.save()
        painter.setClipRect(plot)
        hover_hit = self._manual_drawing_hover_hit

        for index, stored_drawing in enumerate(self._manual_drawings):
            line = self._manual_drawing_line_for(
                stored_drawing,
                plot=plot,
                snapshot=snapshot,
                price_low=price_low,
                price_span=price_span,
            )
            base_color = self._manual_drawing_color(stored_drawing.color_index)
            highlighted = hover_hit is not None and hover_hit.drawing_index == index
            line_color = base_color.lighter(155) if highlighted else base_color
            painter.setPen(QPen(line_color, 3 if highlighted else 2))
            painter.drawLine(line)

            for part, point in (
                (_MANUAL_DRAWING_HIT_START, line.p1()),
                (_MANUAL_DRAWING_HIT_END, line.p2()),
            ):
                endpoint_hovered = (
                    hover_hit is not None
                    and hover_hit.drawing_index == index
                    and hover_hit.part == part
                )
                radius = (
                    _MANUAL_DRAWING_ENDPOINT_RADIUS + 1.5
                    if endpoint_hovered
                    else _MANUAL_DRAWING_ENDPOINT_RADIUS
                )
                painter.setPen(QPen(line_color, 2))
                endpoint_brush = (
                    line_color if endpoint_hovered else self.palette().base()
                )
                painter.setBrush(endpoint_brush)
                painter.drawEllipse(point, radius, radius)

        preview_start = self._manual_drawing_start
        preview = self._manual_drawing_preview
        mode = self._manual_drawing_mode
        if preview_start is not None and preview is not None and mode is not None:
            preview_end = self._normalized_manual_drawing_end(
                mode,
                preview_start,
                preview,
            )
            preview_drawing = _ManualDrawing(
                mode=mode,
                start=preview_start,
                end=preview_end,
                color_index=(
                    self._manual_drawing_active_color_index
                    if self._manual_drawing_active_color_index is not None
                    else self._manual_drawing_next_color_index
                ),
            )
            preview_color = self._manual_drawing_color(preview_drawing.color_index)
            preview_color.setAlpha(190)
            painter.setPen(QPen(preview_color, 2, Qt.PenStyle.DashLine))
            preview_line = self._manual_drawing_line_for(
                preview_drawing,
                plot=plot,
                snapshot=snapshot,
                price_low=price_low,
                price_span=price_span,
            )
            painter.drawLine(preview_line)
            painter.setBrush(self.palette().base())
            painter.drawEllipse(
                preview_line.p1(),
                _MANUAL_DRAWING_ENDPOINT_RADIUS,
                _MANUAL_DRAWING_ENDPOINT_RADIUS,
            )
        painter.restore()

    def _scaled_price_range(
        self,
        snapshot: WorkspaceChartSnapshot,
    ) -> tuple[float, float]:
        events = snapshot.visible_events
        price_low = min(event.low for event in events)
        price_high = max(event.high for event in events)
        if snapshot.current_bid is not None:
            price_low = min(price_low, snapshot.current_bid)
            price_high = max(price_high, snapshot.current_bid)
        if snapshot.current_ask is not None:
            price_low = min(price_low, snapshot.current_ask)
            price_high = max(price_high, snapshot.current_ask)
        overlay_values = tuple(
            value
            for series in snapshot.series
            if series.role == WORKSPACE_CHART_ROLE_PRICE_OVERLAY
            for value in (
                *(point.value for point in series.points),
                *(point.value for point in series.projection_points),
            )
        )
        if overlay_values:
            price_low = min(price_low, min(overlay_values))
            price_high = max(price_high, max(overlay_values))
        position_levels = self._active_position_levels()
        if position_levels:
            price_low = min(price_low, min(position_levels))
            price_high = max(price_high, max(position_levels))
        execution_price, _execution_label = self._execution_display_price()
        if execution_price is not None:
            price_low = min(price_low, execution_price)
            price_high = max(price_high, execution_price)
        base_span = max(1e-9, price_high - price_low)
        padded_span = base_span * 1.16
        center = (price_low + price_high) / 2.0
        scaled_span = max(1e-9, padded_span * self._vertical_scale)
        center += scaled_span * self._vertical_pan_ratio
        return center - scaled_span / 2.0, center + scaled_span / 2.0

    def _draw_grid(
        self,
        painter: QPainter,
        plot: QRectF,
        price_low: float,
        price_high: float,
    ) -> None:
        grid_color = self.palette().mid().color()
        grid_color.setAlpha(90)
        painter.setPen(QPen(grid_color, 1, Qt.PenStyle.DotLine))
        label_color = self.palette().text().color()
        font_metrics = painter.fontMetrics()

        rows = 5
        for row in range(rows + 1):
            ratio = row / rows
            y = plot.top() + plot.height() * ratio
            painter.drawLine(QLineF(plot.left(), y, plot.right(), y))
            price = price_high - (price_high - price_low) * ratio
            label = f"{price:.5f}"
            label_rect = QRectF(
                2.0,
                y - font_metrics.height() / 2,
                plot.left() - 8.0,
                font_metrics.height(),
            )
            painter.setPen(label_color)
            painter.drawText(
                label_rect,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                label,
            )
            painter.setPen(QPen(grid_color, 1, Qt.PenStyle.DotLine))

    @staticmethod
    def _draw_candles(
        painter: QPainter,
        plot: QRectF,
        events: tuple[WorkspaceMarketEvent, ...],
        price_low: float,
        price_span: float,
    ) -> None:
        count = len(events)
        slot_width = plot.width() / max(1, count)
        body_width = max(2.0, min(12.0, slot_width * 0.62))
        up_color = QColor(46, 125, 50)
        down_color = QColor(198, 40, 40)

        def price_y(price_value: float) -> float:
            return (
                plot.bottom() - (price_value - price_low) / price_span * plot.height()
            )

        for index, market_event in enumerate(events):
            x = plot.left() + slot_width * (index + 0.5)
            open_y = price_y(market_event.open)
            close_y = price_y(market_event.close)
            high_y = price_y(market_event.high)
            low_y = price_y(market_event.low)
            candle_color = (
                up_color if market_event.close >= market_event.open else down_color
            )
            painter.setPen(QPen(candle_color, 1))
            painter.drawLine(QLineF(x, high_y, x, low_y))

            body_top = min(open_y, close_y)
            body_height = max(1.0, abs(close_y - open_y))
            body = QRectF(
                x - body_width / 2,
                body_top,
                body_width,
                body_height,
            )
            painter.fillRect(body, candle_color)
            painter.drawRect(body)

    @staticmethod
    def _series_color(series: WorkspaceChartSeries) -> QColor:
        colors = {
            "ALLIGATOR_JAW": QColor(25, 118, 210),
            "ALLIGATOR_TEETH": QColor(216, 27, 96),
            "ALLIGATOR_LIPS": QColor(46, 125, 50),
        }
        return colors.get(series.series_code, QColor(255, 167, 38))

    def _draw_price_overlays(
        self,
        painter: QPainter,
        plot: QRectF,
        snapshot: WorkspaceChartSnapshot,
        price_low: float,
        price_span: float,
    ) -> None:
        overlays = tuple(
            series
            for series in snapshot.series
            if series.role == WORKSPACE_CHART_ROLE_PRICE_OVERLAY
        )
        if not overlays:
            return
        timestamp_indexes = {
            event.timestamp: index
            for index, event in enumerate(snapshot.visible_events)
        }
        count = max(1, len(snapshot.visible_events))
        slot_width = plot.width() / count

        def price_y(price_value: float) -> float:
            return (
                plot.bottom() - (price_value - price_low) / price_span * plot.height()
            )

        for series in overlays:
            color = self._series_color(series)
            painter.setPen(QPen(color, 2))
            previous: tuple[int, float, float] | None = None
            for point in series.points:
                local_index = timestamp_indexes.get(point.timestamp)
                if local_index is None:
                    previous = None
                    continue
                x = plot.left() + slot_width * (local_index + 0.5)
                y = price_y(point.value)
                if previous is not None and local_index == previous[0] + 1:
                    painter.drawLine(QLineF(previous[1], previous[2], x, y))
                previous = (local_index, x, y)

            if previous is None or not series.projection_points:
                continue
            factual_last_x = previous[1]
            projection_previous_x = factual_last_x
            projection_previous_y = previous[2]
            for point in series.projection_points:
                x = factual_last_x + slot_width * point.horizon_bars
                y = price_y(point.value)
                painter.drawLine(
                    QLineF(
                        projection_previous_x,
                        projection_previous_y,
                        x,
                        y,
                    )
                )
                projection_previous_x = x
                projection_previous_y = y
        self._draw_overlay_legend(painter, plot, overlays)

    def _draw_overlay_legend(
        self,
        painter: QPainter,
        plot: QRectF,
        overlays: tuple[WorkspaceChartSeries, ...],
    ) -> None:
        first = overlays[0]
        x = plot.left() + 8.0
        y = plot.top() + painter.fontMetrics().height()
        painter.setPen(self.palette().text().color())
        painter.drawText(
            QPointF(x, y),
            f"Alligator {first.timeframe} r{first.profile_revision}",
        )
        x += 128.0
        for series in overlays:
            color = self._series_color(series)
            painter.setPen(QPen(color, 2))
            painter.drawLine(QLineF(x, y - 4.0, x + 16.0, y - 4.0))
            painter.setPen(self.palette().text().color())
            painter.drawText(QPointF(x + 20.0, y), series.label)
            x += 62.0

    @staticmethod
    def _draw_current_prices(
        painter: QPainter,
        plot: QRectF,
        snapshot: WorkspaceChartSnapshot,
        price_low: float,
        price_span: float,
    ) -> None:
        def price_y(price_value: float) -> float:
            return (
                plot.bottom() - (price_value - price_low) / price_span * plot.height()
            )

        lines = (
            (snapshot.current_bid, QColor(25, 118, 210)),
            (snapshot.current_ask, QColor(123, 31, 162)),
        )
        for line_price, color in lines:
            if line_price is None:
                continue
            y = price_y(line_price)
            painter.setPen(QPen(color, 1, Qt.PenStyle.DashLine))
            painter.drawLine(QLineF(plot.left(), y, plot.right(), y))

    def _execution_display_price(self) -> tuple[float | None, str]:
        """Повернути execution-price, релевантну active position, і її label."""
        event = self._execution_event
        if event is None:
            return None, ""
        sides = {
            position.side
            for position in self._owned_snapshot.active_positions
            if position.side in {"BUY", "SELL"}
        }
        if sides == {"BUY"}:
            return float(event.bid), "Tick Bid"
        if sides == {"SELL"}:
            return float(event.ask), "Tick Ask"
        return float(event.close), "Tick"

    def _draw_execution_price(
        self,
        painter: QPainter,
        plot: QRectF,
        price_low: float,
        price_span: float,
    ) -> None:
        """Намалювати останню M1 execution-price поверх strategy M15 chart."""
        price, label_prefix = self._execution_display_price()
        if price is None or not label_prefix:
            return
        y = plot.bottom() - (price - price_low) / price_span * plot.height()
        if y < plot.top() - 1.0 or y > plot.bottom() + 1.0:
            return
        color = QColor(0, 172, 193)
        background = self.palette().window().color()
        background.setAlpha(225)
        self._draw_position_line(
            painter,
            plot,
            y,
            color,
            f"{label_prefix} {price:.5f}",
            Qt.PenStyle.DashDotLine,
            background,
            label_width=_EXECUTION_LABEL_WIDTH,
        )

    def _draw_position_overlays(
        self,
        painter: QPainter,
        plot: QRectF,
        price_low: float,
        price_span: float,
    ) -> None:
        """Намалювати Entry/SL/TP активних positions поверх price chart."""
        positions = self._owned_snapshot.active_positions
        if not positions:
            return

        def price_y(price_value: float) -> float:
            return (
                plot.bottom() - (price_value - price_low) / price_span * plot.height()
            )

        buy_color = QColor(46, 125, 50)
        sell_color = QColor(198, 40, 40)
        stop_color = QColor(211, 47, 47)
        take_color = QColor(0, 137, 123)
        label_background = self.palette().window().color()
        label_background.setAlpha(225)

        for position in positions:
            side_color = buy_color if position.side == "BUY" else sell_color
            if position.entry_price is not None:
                entry_label = (
                    f"{position.side} {position.volume:g}  "
                    f"{position.entry_price:.5f}  "
                    f"PnL {position.current_profit:+.2f}"
                )
                self._draw_position_line(
                    painter,
                    plot,
                    price_y(position.entry_price),
                    side_color,
                    entry_label,
                    Qt.PenStyle.SolidLine,
                    label_background,
                )

            for field_name, prefix, price, color in (
                ("stop_loss", "SL", position.stop_loss, stop_color),
                ("take_profit", "TP", position.take_profit, take_color),
            ):
                if price is None:
                    continue
                display_price = float(price)
                drag_hit = self._protection_drag_hit
                if (
                    drag_hit is not None
                    and drag_hit.position_id == position.position_id
                    and drag_hit.field_name == field_name
                    and self._protection_preview_price is not None
                ):
                    display_price = self._protection_preview_price
                self._draw_position_line(
                    painter,
                    plot,
                    price_y(display_price),
                    color,
                    f"{prefix} {display_price:.5f}",
                    Qt.PenStyle.DashLine,
                    label_background,
                )

    @staticmethod
    def _draw_position_line(
        painter: QPainter,
        plot: QRectF,
        y: float,
        color: QColor,
        label: str,
        style: Qt.PenStyle,
        label_background: QColor,
        *,
        label_width: float | None = None,
    ) -> None:
        if y < plot.top() - 1.0 or y > plot.bottom() + 1.0:
            return
        painter.setPen(QPen(color, 1, style))
        painter.drawLine(QLineF(plot.left(), y, plot.right(), y))

        resolved_label_width = (
            float(label_width)
            if label_width is not None
            else min(_POSITION_LABEL_WIDTH, max(84.0, plot.width() * 0.42))
        )
        resolved_label_width = min(resolved_label_width, plot.width())
        label_rect = QRectF(
            plot.right() - resolved_label_width,
            y - _POSITION_LABEL_HEIGHT / 2.0,
            resolved_label_width,
            _POSITION_LABEL_HEIGHT,
        )
        if label_rect.top() < plot.top():
            label_rect.moveTop(plot.top())
        if label_rect.bottom() > plot.bottom():
            label_rect.moveBottom(plot.bottom())
        painter.fillRect(label_rect, label_background)
        painter.setPen(color)
        painter.drawText(
            label_rect.adjusted(4.0, 0.0, -4.0, 0.0),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            label,
        )

    def _draw_time_axis(
        self,
        painter: QPainter,
        plot: QRectF,
        events: tuple[WorkspaceMarketEvent, ...],
    ) -> None:
        count = len(events)
        if count == 0:
            return
        label_color = self.palette().text().color()
        painter.setPen(label_color)
        label_indexes = sorted({0, count // 3, count * 2 // 3, count - 1})
        slot_width = plot.width() / max(1, count)
        for index in label_indexes:
            timestamp = events[index].timestamp.strftime("%m-%d %H:%M")
            x = plot.left() + slot_width * (index + 0.5)
            rect = QRectF(x - 52.0, plot.bottom() + 4.0, 104.0, 24.0)
            painter.drawText(
                rect,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                timestamp,
            )

    def _draw_cursor(
        self,
        painter: QPainter,
        plot: QRectF,
        snapshot: WorkspaceChartSnapshot,
    ) -> None:
        cursor_index = snapshot.cursor_index
        if cursor_index is None:
            return
        if not snapshot.visible_start <= cursor_index < snapshot.visible_end:
            return
        local_index = cursor_index - snapshot.visible_start
        count = max(1, len(snapshot.visible_events))
        slot_width = plot.width() / count
        x = plot.left() + slot_width * (local_index + 0.5)
        cursor_color = self.palette().highlight().color()
        painter.setPen(QPen(cursor_color, 1, Qt.PenStyle.DashDotLine))
        painter.drawLine(QLineF(x, plot.top(), x, plot.bottom()))

    def _draw_hover_crosshair(
        self,
        painter: QPainter,
        plot: QRectF,
        snapshot: WorkspaceChartSnapshot,
        price_low: float,
        price_span: float,
    ) -> None:
        hover_index = self._hover_index
        if hover_index is None:
            return
        if not snapshot.visible_start <= hover_index < snapshot.visible_end:
            return
        local_index = hover_index - snapshot.visible_start
        count = max(1, len(snapshot.visible_events))
        slot_width = plot.width() / count
        x = plot.left() + slot_width * (local_index + 0.5)
        color = self.palette().text().color()
        color.setAlpha(150)
        painter.setPen(QPen(color, 1, Qt.PenStyle.DashLine))
        painter.drawLine(QLineF(x, plot.top(), x, plot.bottom()))

        hover_value = self._hover_value
        if hover_value is not None:
            y = plot.bottom() - (hover_value - price_low) / price_span * plot.height()
            y = min(plot.bottom(), max(plot.top(), y))
            painter.drawLine(QLineF(plot.left(), y, plot.right(), y))
            self._draw_value_badge(painter, plot, y, hover_value)

        market_event = snapshot.visible_events[local_index]
        self._draw_hover_ohlc(painter, plot, market_event)
        if self._show_time_label:
            self._draw_time_badge(painter, plot, x, market_event.timestamp)

    def _draw_value_badge(
        self,
        painter: QPainter,
        plot: QRectF,
        y: float,
        value: float,
    ) -> None:
        width = 64.0
        height = 18.0
        rect = QRectF(
            plot.right() - width,
            y - height / 2.0,
            width,
            height,
        )
        painter.fillRect(rect, self.palette().window())
        painter.setPen(self.palette().text().color())
        painter.drawText(
            rect.adjusted(3.0, 0.0, -3.0, 0.0),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{value:.5f}",
        )

    def _draw_hover_ohlc(
        self,
        painter: QPainter,
        plot: QRectF,
        market_event: WorkspaceMarketEvent,
    ) -> None:
        info = _chart_info_rect(self, plot)
        metrics = painter.fontMetrics()
        line_height = metrics.height() + 2.0
        values = (
            ("O", market_event.open),
            ("H", market_event.high),
            ("L", market_event.low),
            ("C", market_event.close),
        )
        painter.setPen(self.palette().mid().color())
        painter.drawLine(
            QLineF(info.left() - 4.0, info.top(), info.left() - 4.0, info.bottom())
        )
        painter.setPen(self.palette().text().color())
        for index, (label, value) in enumerate(values):
            line = QRectF(
                info.left(),
                info.top() + index * line_height,
                info.width(),
                line_height,
            )
            painter.drawText(
                line.adjusted(1.0, 0.0, -2.0, 0.0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                label,
            )
            painter.drawText(
                line.adjusted(16.0, 0.0, -2.0, 0.0),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{value:.5f}",
            )

    def _draw_time_badge(
        self,
        painter: QPainter,
        plot: QRectF,
        x: float,
        timestamp,
    ) -> None:
        width = 126.0
        height = 18.0
        left = min(plot.right() - width, max(plot.left(), x - width / 2.0))
        rect = QRectF(left, plot.bottom() - height, width, height)
        painter.fillRect(rect, self.palette().window())
        painter.setPen(self.palette().text().color())
        painter.drawText(
            rect,
            Qt.AlignmentFlag.AlignCenter,
            timestamp.strftime("%Y-%m-%d %H:%M"),
        )


class WorkspaceMacdCanvas(QWidget):
    """Paint factual MACD lines and histogram for the shared chart viewport."""

    zoom_requested = Signal(int)
    pan_requested = Signal(int)
    hover_changed = Signal(int)
    hover_cleared = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._snapshot: WorkspaceChartSnapshot | None = None
        self._vertical_scale = 1.0
        self._vertical_pan_ratio = 0.0
        self._drag_start_x: float | None = None
        self._drag_start_visible_start: int | None = None
        self._last_pan_target: int | None = None
        self._hover_index: int | None = None
        self._hover_value: float | None = None
        self._show_time_label = False
        self.setMinimumHeight(56)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    @property
    def vertical_scale(self) -> float:
        return self._vertical_scale

    @property
    def vertical_pan_ratio(self) -> float:
        return self._vertical_pan_ratio

    @property
    def hover_index(self) -> int | None:
        return self._hover_index

    @property
    def hover_value(self) -> float | None:
        return self._hover_value

    @property
    def time_label_visible(self) -> bool:
        return self._show_time_label

    @property
    def hovered_values(self) -> tuple[tuple[str, float], ...]:
        snapshot = self._snapshot
        hover_index = self._hover_index
        if snapshot is None or hover_index is None:
            return ()
        if not snapshot.visible_start <= hover_index < snapshot.visible_end:
            return ()
        local_index = hover_index - snapshot.visible_start
        timestamp = snapshot.visible_events[local_index].timestamp
        values: list[tuple[str, float]] = []
        for series in self._macd_series(snapshot):
            point = next(
                (item for item in series.points if item.timestamp == timestamp),
                None,
            )
            if point is not None:
                values.append((series.label, point.value))
        return tuple(values)

    def set_crosshair_index(
        self,
        index: int | None,
        *,
        show_time_label: bool = False,
    ) -> None:
        self._hover_index = index
        self._hover_value = None
        self._show_time_label = bool(show_time_label)
        self.update()

    def set_time_label_visible(self, visible: bool) -> None:
        self._show_time_label = bool(visible)
        self.update()

    def clear_crosshair(self) -> None:
        self._hover_index = None
        self._hover_value = None
        self._show_time_label = False
        self.update()

    @staticmethod
    def has_macd_series(snapshot: WorkspaceChartSnapshot) -> bool:
        return any(
            series.role
            in {
                WORKSPACE_CHART_ROLE_INDICATOR_LINE,
                WORKSPACE_CHART_ROLE_INDICATOR_HISTOGRAM,
            }
            and series.series_code.startswith("MACD_")
            for series in snapshot.series
        )

    def set_snapshot(self, snapshot: WorkspaceChartSnapshot) -> None:
        self._snapshot = snapshot
        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:
        self.setFocus()
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        direction = -1 if delta > 0 else 1
        modifiers = event.modifiers()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            self.zoom_vertical(direction)
        else:
            self.zoom_requested.emit(direction)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        snapshot = self._snapshot
        if (
            event.button() == Qt.MouseButton.LeftButton
            and snapshot is not None
            and snapshot.visible_events
        ):
            self.setFocus()
            self._drag_start_x = event.position().x()
            self._drag_start_visible_start = snapshot.visible_start
            self._last_pan_target = snapshot.visible_start
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_start_x is None or self._drag_start_visible_start is None:
            self._update_hover_from_position(
                event.position().x(),
                event.position().y(),
            )
            event.accept()
            return
        target = self._pan_target_for_x(event.position().x())
        if target is not None and target != self._last_pan_target:
            self._last_pan_target = target
            self.pan_requested.emit(target)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._drag_start_x is not None
        ):
            self._drag_start_x = None
            self._drag_start_visible_start = None
            self._last_pan_target = None
            self.setCursor(Qt.CursorShape.CrossCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        if self._drag_start_x is None:
            self.clear_crosshair()
            self.hover_cleared.emit()
        super().leaveEvent(event)

    def _update_hover_from_position(self, x: float, y: float) -> None:
        snapshot = self._snapshot
        if snapshot is None or not snapshot.visible_events:
            return
        series = self._macd_series(snapshot)
        if not series:
            return
        plot = self._plot_rect()
        if not plot.contains(QPointF(x, y)):
            if self._hover_index is not None:
                self.clear_crosshair()
                self.hover_cleared.emit()
            return
        count = len(snapshot.visible_events)
        slot_width = plot.width() / max(1, count)
        local_index = int((x - plot.left()) / max(1.0, slot_width))
        local_index = min(count - 1, max(0, local_index))
        value_low, value_high = self._scaled_value_range(series)
        ratio = (plot.bottom() - y) / max(1.0, plot.height())
        value = value_low + ratio * (value_high - value_low)
        self._hover_index = snapshot.visible_start + local_index
        self._hover_value = value
        self.update()
        self.hover_changed.emit(self._hover_index)

    def zoom_vertical(self, direction: int) -> None:
        factor = 0.8 if int(direction) < 0 else 1.25
        self._vertical_scale = min(8.0, max(0.25, self._vertical_scale * factor))
        self.update()

    def set_vertical_pan_ratio(self, ratio: float) -> None:
        self._vertical_pan_ratio = min(2.0, max(-2.0, float(ratio)))
        self.update()

    def _pan_target_for_x(self, current_x: float) -> int | None:
        snapshot = self._snapshot
        start_x = self._drag_start_x
        start_visible = self._drag_start_visible_start
        if snapshot is None or start_x is None or start_visible is None:
            return None
        count = max(1, len(snapshot.visible_events))
        slot_width = self._plot_width() / count
        pixel_delta = float(current_x) - start_x
        bar_delta = int(round(pixel_delta / max(1.0, slot_width)))
        return start_visible - bar_delta

    def _plot_rect(self) -> QRectF:
        left_margin = 68.0
        right_margin = _CHART_INFO_GUTTER_WIDTH + 12.0
        top_margin = 22.0
        bottom_margin = 12.0
        return QRectF(
            left_margin,
            top_margin,
            max(10.0, self.width() - left_margin - right_margin),
            max(10.0, self.height() - top_margin - bottom_margin),
        )

    def _plot_width(self) -> float:
        return self._plot_rect().width()

    @staticmethod
    def _macd_series(
        snapshot: WorkspaceChartSnapshot,
    ) -> tuple[WorkspaceChartSeries, ...]:
        return tuple(
            item
            for item in snapshot.series
            if item.series_code.startswith("MACD_")
            and item.role
            in {
                WORKSPACE_CHART_ROLE_INDICATOR_LINE,
                WORKSPACE_CHART_ROLE_INDICATOR_HISTOGRAM,
            }
        )

    def paintEvent(self, event: QPaintEvent) -> None:
        _ = event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(self.rect(), self.palette().base())

        snapshot = self._snapshot
        if snapshot is None or not snapshot.visible_events:
            return
        series = self._macd_series(snapshot)
        if not series:
            return

        plot = self._plot_rect()
        value_low, value_high = self._scaled_value_range(series)
        value_span = value_high - value_low

        self._draw_grid(painter, plot, value_low, value_high)
        self._draw_histogram(
            painter,
            plot,
            snapshot,
            series,
            value_low,
            value_span,
        )
        self._draw_lines(
            painter,
            plot,
            snapshot,
            series,
            value_low,
            value_span,
        )
        self._draw_legend(painter, plot, series)
        self._draw_hover_crosshair(
            painter,
            plot,
            snapshot,
            value_low,
            value_span,
        )

    def _scaled_value_range(
        self,
        series: tuple[WorkspaceChartSeries, ...],
    ) -> tuple[float, float]:
        values = [point.value for item in series for point in item.points]
        max_abs = max((abs(value) for value in values), default=0.0)
        half_span = max(1e-9, max_abs * 1.15)
        scaled_span = max(2e-9, half_span * 2.0 * self._vertical_scale)
        center = scaled_span * self._vertical_pan_ratio
        return center - scaled_span / 2.0, center + scaled_span / 2.0

    def _draw_grid(
        self,
        painter: QPainter,
        plot: QRectF,
        value_low: float,
        value_high: float,
    ) -> None:
        grid_color = self.palette().mid().color()
        grid_color.setAlpha(80)
        label_color = self.palette().text().color()
        font_metrics = painter.fontMetrics()
        for row in range(5):
            ratio = row / 4.0
            y = plot.top() + plot.height() * ratio
            value = value_high - (value_high - value_low) * ratio
            pen_style = (
                Qt.PenStyle.DashLine if abs(value) < 1e-12 else Qt.PenStyle.DotLine
            )
            painter.setPen(QPen(grid_color, 1, pen_style))
            painter.drawLine(QLineF(plot.left(), y, plot.right(), y))
            painter.setPen(label_color)
            painter.drawText(
                QRectF(
                    2.0,
                    y - font_metrics.height() / 2,
                    plot.left() - 8.0,
                    font_metrics.height(),
                ),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{value:.5f}",
            )

    @staticmethod
    def _value_y(
        plot: QRectF,
        value: float,
        value_low: float,
        value_span: float,
    ) -> float:
        return plot.bottom() - (value - value_low) / value_span * plot.height()

    def _draw_histogram(
        self,
        painter: QPainter,
        plot: QRectF,
        snapshot: WorkspaceChartSnapshot,
        series: tuple[WorkspaceChartSeries, ...],
        value_low: float,
        value_span: float,
    ) -> None:
        histogram = next(
            (
                item
                for item in series
                if item.role == WORKSPACE_CHART_ROLE_INDICATOR_HISTOGRAM
            ),
            None,
        )
        if histogram is None:
            return
        indexes = {
            market_event.timestamp: index
            for index, market_event in enumerate(snapshot.visible_events)
        }
        count = max(1, len(snapshot.visible_events))
        slot_width = plot.width() / count
        bar_width = max(1.0, slot_width * 0.55)
        zero_y = self._value_y(plot, 0.0, value_low, value_span)
        positive_color = QColor(38, 166, 154)
        negative_color = QColor(239, 83, 80)
        for point in histogram.points:
            index = indexes.get(point.timestamp)
            if index is None:
                continue
            x = plot.left() + slot_width * (index + 0.5)
            value_y = self._value_y(plot, point.value, value_low, value_span)
            color = positive_color if point.value >= 0.0 else negative_color
            top = min(zero_y, value_y)
            height = max(1.0, abs(zero_y - value_y))
            painter.fillRect(
                QRectF(x - bar_width / 2.0, top, bar_width, height),
                color,
            )

    def _draw_lines(
        self,
        painter: QPainter,
        plot: QRectF,
        snapshot: WorkspaceChartSnapshot,
        series: tuple[WorkspaceChartSeries, ...],
        value_low: float,
        value_span: float,
    ) -> None:
        indexes = {
            market_event.timestamp: index
            for index, market_event in enumerate(snapshot.visible_events)
        }
        count = max(1, len(snapshot.visible_events))
        slot_width = plot.width() / count
        colors = {
            "MACD_VALUE": QColor(25, 118, 210),
            "MACD_SIGNAL": QColor(255, 152, 0),
        }
        for item in series:
            if item.role != WORKSPACE_CHART_ROLE_INDICATOR_LINE:
                continue
            painter.setPen(QPen(colors.get(item.series_code, QColor(96, 125, 139)), 2))
            previous: tuple[int, float, float] | None = None
            for point in item.points:
                index = indexes.get(point.timestamp)
                if index is None:
                    previous = None
                    continue
                x = plot.left() + slot_width * (index + 0.5)
                y = self._value_y(plot, point.value, value_low, value_span)
                if previous is not None and index == previous[0] + 1:
                    painter.drawLine(QLineF(previous[1], previous[2], x, y))
                previous = (index, x, y)

    def _draw_legend(
        self,
        painter: QPainter,
        plot: QRectF,
        series: tuple[WorkspaceChartSeries, ...],
    ) -> None:
        first = series[0]
        x = plot.left() + 8.0
        y = plot.top() - 6.0
        painter.setPen(self.palette().text().color())
        painter.drawText(
            QPointF(x, y),
            f"MACD {first.timeframe} r{first.profile_revision}",
        )
        x += 112.0
        labels = {item.series_code: item.label for item in series}
        histogram_label = labels.get("MACD_HISTOGRAM", "Histogram")
        legend_items = (
            (labels.get("MACD_VALUE", "MACD"), QColor(25, 118, 210)),
            (labels.get("MACD_SIGNAL", "Signal"), QColor(255, 152, 0)),
            (f"{histogram_label} +", QColor(38, 166, 154)),
            (f"{histogram_label} −", QColor(239, 83, 80)),
        )
        font_metrics = painter.fontMetrics()
        for label, color in legend_items:
            painter.setPen(QPen(color, 2))
            painter.drawLine(QLineF(x, y - 4.0, x + 14.0, y - 4.0))
            painter.setPen(self.palette().text().color())
            painter.drawText(QPointF(x + 18.0, y), label)
            x += 34.0 + font_metrics.horizontalAdvance(label)

    def _draw_hover_crosshair(
        self,
        painter: QPainter,
        plot: QRectF,
        snapshot: WorkspaceChartSnapshot,
        value_low: float,
        value_span: float,
    ) -> None:
        hover_index = self._hover_index
        if hover_index is None:
            return
        if not snapshot.visible_start <= hover_index < snapshot.visible_end:
            return
        local_index = hover_index - snapshot.visible_start
        count = max(1, len(snapshot.visible_events))
        slot_width = plot.width() / count
        x = plot.left() + slot_width * (local_index + 0.5)
        color = self.palette().text().color()
        color.setAlpha(150)
        painter.setPen(QPen(color, 1, Qt.PenStyle.DashLine))
        painter.drawLine(QLineF(x, plot.top(), x, plot.bottom()))

        hover_value = self._hover_value
        if hover_value is not None:
            y = self._value_y(plot, hover_value, value_low, value_span)
            y = min(plot.bottom(), max(plot.top(), y))
            painter.drawLine(QLineF(plot.left(), y, plot.right(), y))
            self._draw_value_badge(painter, plot, y, hover_value)

        self._draw_hover_values(painter, plot)
        if self._show_time_label:
            market_event = snapshot.visible_events[local_index]
            self._draw_time_badge(painter, plot, x, market_event.timestamp)

    def _draw_hover_values(
        self,
        painter: QPainter,
        plot: QRectF,
    ) -> None:
        values = self.hovered_values
        if not values:
            return
        info = _chart_info_rect(self, plot)
        metrics = painter.fontMetrics()
        line_height = metrics.height() + 2.0
        painter.setPen(self.palette().mid().color())
        painter.drawLine(
            QLineF(info.left() - 4.0, info.top(), info.left() - 4.0, info.bottom())
        )
        painter.setPen(self.palette().text().color())
        for index, (label, value) in enumerate(values):
            display_label = "Hist" if label == "Histogram" else label
            line = QRectF(
                info.left(),
                info.top() + index * line_height,
                info.width(),
                line_height,
            )
            painter.drawText(
                line.adjusted(1.0, 0.0, -2.0, 0.0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                display_label,
            )
            painter.drawText(
                line.adjusted(44.0, 0.0, -2.0, 0.0),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{value:+.5f}",
            )

    def _draw_value_badge(
        self,
        painter: QPainter,
        plot: QRectF,
        y: float,
        value: float,
    ) -> None:
        width = 68.0
        height = 18.0
        rect = QRectF(
            plot.right() - width,
            y - height / 2.0,
            width,
            height,
        )
        painter.fillRect(rect, self.palette().window())
        painter.setPen(self.palette().text().color())
        painter.drawText(
            rect.adjusted(3.0, 0.0, -3.0, 0.0),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{value:.5f}",
        )

    def _draw_time_badge(
        self,
        painter: QPainter,
        plot: QRectF,
        x: float,
        timestamp,
    ) -> None:
        width = 126.0
        height = 18.0
        left = min(plot.right() - width, max(plot.left(), x - width / 2.0))
        rect = QRectF(left, plot.bottom() - height, width, height)
        painter.fillRect(rect, self.palette().window())
        painter.setPen(self.palette().text().color())
        painter.drawText(
            rect,
            Qt.AlignmentFlag.AlignCenter,
            timestamp.strftime("%Y-%m-%d %H:%M"),
        )


class WorkspaceChartWidget(QWidget):
    """Shared price/MACD chart controls with synchronized time navigation."""

    visible_count_requested = Signal(int)
    visible_start_requested = Signal(int)
    latest_requested = Signal()
    protection_change_requested = Signal(str, str, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._snapshot: WorkspaceChartSnapshot | None = None
        self._macd_splitter_initialized = False
        self._canvas_hint_text = ""
        self._protection_stop_hint = ""
        self._protection_take_hint = ""
        self._canvas_hint_delay_ms = 1800
        self._canvas_hint_hide_delay_ms = 10000
        self._canvas_hint_timer = QTimer(self)
        self._canvas_hint_timer.setSingleShot(True)
        self._canvas_hint_timer.setInterval(self._canvas_hint_delay_ms)
        self._canvas_hint_timer.timeout.connect(self._show_delayed_canvas_hint)
        self._canvas_hint_hide_timer = QTimer(self)
        self._canvas_hint_hide_timer.setSingleShot(True)
        self._canvas_hint_hide_timer.setInterval(self._canvas_hint_hide_delay_ms)
        self._canvas_hint_hide_timer.timeout.connect(QToolTip.hideText)

        self.lbl_status = QLabel(self)
        self.lbl_status.setObjectName("lblChartStatus")
        self.lbl_status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.lbl_help = QLabel("?", self)
        self.lbl_help.setObjectName("lblChartHelp")
        self.lbl_help.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_help.setFixedSize(18, _CHART_CONTROL_HEIGHT)

        self.btn_zoom_out = QPushButton("X −", self)
        self.btn_zoom_out.setObjectName("btnChartZoomOut")
        self.btn_zoom_out.setFixedSize(_CHART_CONTROL_WIDTH, _CHART_CONTROL_HEIGHT)
        self.btn_zoom_in = QPushButton("X +", self)
        self.btn_zoom_in.setObjectName("btnChartZoomIn")
        self.btn_zoom_in.setFixedSize(_CHART_CONTROL_WIDTH, _CHART_CONTROL_HEIGHT)
        self.btn_vertical_zoom_out = QPushButton("Y −", self)
        self.btn_vertical_zoom_out.setObjectName("btnChartVerticalZoomOut")
        self.btn_vertical_zoom_out.setFixedSize(
            _CHART_CONTROL_WIDTH,
            _CHART_CONTROL_HEIGHT,
        )
        self.btn_vertical_zoom_in = QPushButton("Y +", self)
        self.btn_vertical_zoom_in.setObjectName("btnChartVerticalZoomIn")
        self.btn_vertical_zoom_in.setFixedSize(
            _CHART_CONTROL_WIDTH,
            _CHART_CONTROL_HEIGHT,
        )
        self.btn_latest = QPushButton("Current", self)
        self.btn_latest.setObjectName("btnChartLatest")
        self.btn_latest.setFixedHeight(_CHART_CONTROL_HEIGHT)
        self.btn_draw_segment = QPushButton("/", self)
        self.btn_draw_segment.setObjectName("btnChartDrawSegment")
        self.btn_draw_horizontal = QPushButton("—", self)
        self.btn_draw_horizontal.setObjectName("btnChartDrawHorizontal")
        self.btn_draw_vertical = QPushButton("|", self)
        self.btn_draw_vertical.setObjectName("btnChartDrawVertical")
        self.btn_draw_clear = QPushButton("×", self)
        self.btn_draw_clear.setObjectName("btnChartDrawClear")
        for button in (
            self.btn_draw_segment,
            self.btn_draw_horizontal,
            self.btn_draw_vertical,
        ):
            button.setCheckable(True)
        for button in (
            self.btn_draw_segment,
            self.btn_draw_horizontal,
            self.btn_draw_vertical,
            self.btn_draw_clear,
        ):
            button.setFixedSize(24, _CHART_CONTROL_HEIGHT)
        for button in (
            self.btn_zoom_out,
            self.btn_zoom_in,
            self.btn_vertical_zoom_out,
            self.btn_vertical_zoom_in,
            self.btn_latest,
            self.btn_draw_segment,
            self.btn_draw_horizontal,
            self.btn_draw_vertical,
            self.btn_draw_clear,
        ):
            _set_chart_control_font(button)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(2)
        header.addWidget(self.lbl_status, 1)
        header.addWidget(self.lbl_help)
        header.addWidget(self.btn_draw_segment)
        header.addWidget(self.btn_draw_horizontal)
        header.addWidget(self.btn_draw_vertical)
        header.addWidget(self.btn_draw_clear)
        header.addWidget(self.btn_zoom_out)
        header.addWidget(self.btn_zoom_in)
        header.addWidget(self.btn_vertical_zoom_out)
        header.addWidget(self.btn_vertical_zoom_in)
        header.addWidget(self.btn_latest)

        self.canvas = WorkspaceCandlestickCanvas(self)
        self.canvas.setObjectName("wspChartCanvas")
        self.vertical_scrollbar = QScrollBar(Qt.Orientation.Vertical, self)
        self.vertical_scrollbar.setObjectName("scrollChartVertical")
        self._configure_vertical_scrollbar(self.vertical_scrollbar)

        self.price_panel = QWidget(self)
        self.price_panel.setObjectName("wspPriceChartPanel")
        price_layout = QHBoxLayout(self.price_panel)
        price_layout.setContentsMargins(0, 0, 0, 0)
        price_layout.setSpacing(4)
        price_layout.addWidget(self.canvas, 1)
        price_layout.addWidget(self.vertical_scrollbar)

        self.macd_canvas = WorkspaceMacdCanvas(self)
        self.macd_canvas.setObjectName("wspMacdCanvas")
        self.macd_vertical_scrollbar = QScrollBar(
            Qt.Orientation.Vertical,
            self,
        )
        self.macd_vertical_scrollbar.setObjectName("scrollMacdVertical")
        self._configure_vertical_scrollbar(self.macd_vertical_scrollbar)
        self.btn_macd_vertical_zoom_out = QPushButton("Y −", self)
        self.btn_macd_vertical_zoom_out.setObjectName("btnMacdVerticalZoomOut")
        self.btn_macd_vertical_zoom_out.setFixedSize(
            _CHART_CONTROL_WIDTH,
            _CHART_CONTROL_HEIGHT,
        )
        _set_chart_control_font(self.btn_macd_vertical_zoom_out)
        self.btn_macd_vertical_zoom_out.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_macd_vertical_zoom_in = QPushButton("Y +", self)
        self.btn_macd_vertical_zoom_in.setObjectName("btnMacdVerticalZoomIn")
        self.btn_macd_vertical_zoom_in.setFixedSize(
            _CHART_CONTROL_WIDTH,
            _CHART_CONTROL_HEIGHT,
        )
        _set_chart_control_font(self.btn_macd_vertical_zoom_in)
        self.btn_macd_vertical_zoom_in.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        macd_controls = QHBoxLayout()
        macd_controls.setContentsMargins(0, 0, 0, 0)
        macd_controls.setSpacing(2)
        macd_controls.addStretch(1)
        macd_controls.addWidget(self.btn_macd_vertical_zoom_out)
        macd_controls.addWidget(self.btn_macd_vertical_zoom_in)

        macd_body = QHBoxLayout()
        macd_body.setContentsMargins(0, 0, 0, 0)
        macd_body.setSpacing(4)
        macd_body.addWidget(self.macd_canvas, 1)
        macd_body.addWidget(self.macd_vertical_scrollbar)

        self.macd_panel = QWidget(self)
        self.macd_panel.setObjectName("wspMacdPanel")
        macd_layout = QVBoxLayout(self.macd_panel)
        macd_layout.setContentsMargins(0, 0, 0, 0)
        macd_layout.setSpacing(1)
        macd_layout.addLayout(macd_controls)
        macd_layout.addLayout(macd_body, 1)
        self.macd_panel.setVisible(False)

        self.splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.splitter.setObjectName("splitChartMacd")
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(6)
        self.splitter.addWidget(self.price_panel)
        self.splitter.addWidget(self.macd_panel)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)

        self.scrollbar = QScrollBar(Qt.Orientation.Horizontal, self)
        self.scrollbar.setObjectName("scrollChart")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(header)
        layout.addWidget(self.splitter, 1)
        layout.addWidget(self.scrollbar)

        self.btn_draw_segment.clicked.connect(
            lambda checked: self._toggle_manual_drawing(
                _MANUAL_DRAWING_SEGMENT,
                checked,
                self.btn_draw_segment,
            )
        )
        self.btn_draw_horizontal.clicked.connect(
            lambda checked: self._toggle_manual_drawing(
                _MANUAL_DRAWING_HORIZONTAL,
                checked,
                self.btn_draw_horizontal,
            )
        )
        self.btn_draw_vertical.clicked.connect(
            lambda checked: self._toggle_manual_drawing(
                _MANUAL_DRAWING_VERTICAL,
                checked,
                self.btn_draw_vertical,
            )
        )
        self.btn_draw_clear.clicked.connect(self.canvas.clear_manual_drawings)
        self.btn_zoom_in.clicked.connect(lambda: self._request_zoom(0.8))
        self.btn_zoom_out.clicked.connect(lambda: self._request_zoom(1.25))
        self.btn_vertical_zoom_in.clicked.connect(lambda: self.canvas.zoom_vertical(-1))
        self.btn_vertical_zoom_out.clicked.connect(lambda: self.canvas.zoom_vertical(1))
        self.btn_macd_vertical_zoom_in.clicked.connect(
            lambda: self.macd_canvas.zoom_vertical(-1)
        )
        self.btn_macd_vertical_zoom_out.clicked.connect(
            lambda: self.macd_canvas.zoom_vertical(1)
        )
        self.btn_latest.clicked.connect(self.latest_requested.emit)
        self.canvas.zoom_requested.connect(self._on_wheel_zoom)
        self.canvas.pan_requested.connect(self.visible_start_requested.emit)
        self.macd_canvas.zoom_requested.connect(self._on_wheel_zoom)
        self.macd_canvas.pan_requested.connect(self.visible_start_requested.emit)
        self.canvas.hover_changed.connect(self._sync_price_hover)
        self.canvas.hover_cleared.connect(self._clear_crosshair)
        self.canvas.protection_change_requested.connect(
            self.protection_change_requested.emit
        )
        self.canvas.protection_hover_changed.connect(self._show_protection_hover_hint)
        self.canvas.protection_hover_cleared.connect(self._clear_protection_hover_hint)
        self.canvas.manual_drawing_hover_changed.connect(
            self._show_manual_drawing_hover_hint
        )
        self.canvas.manual_drawing_hover_cleared.connect(
            self._clear_manual_drawing_hover_hint
        )
        self.macd_canvas.hover_changed.connect(self._sync_macd_hover)
        self.macd_canvas.hover_cleared.connect(self._clear_crosshair)
        self.canvas.installEventFilter(self)
        self.macd_canvas.installEventFilter(self)
        self.scrollbar.valueChanged.connect(self._on_scrollbar_changed)
        self.vertical_scrollbar.valueChanged.connect(
            self._on_vertical_scrollbar_changed
        )
        self.macd_vertical_scrollbar.valueChanged.connect(
            self._on_macd_vertical_scrollbar_changed
        )

        self._shortcuts: list[QShortcut] = []
        self._install_keyboard_shortcuts()
        self._sync_manual_drawing_button_visuals()

    def _toggle_manual_drawing(
        self,
        mode: str,
        checked: bool,
        active_button: QPushButton,
    ) -> None:
        buttons = (
            self.btn_draw_segment,
            self.btn_draw_horizontal,
            self.btn_draw_vertical,
        )
        if checked:
            for button in buttons:
                if button is active_button:
                    continue
                button.blockSignals(True)
                try:
                    button.setChecked(False)
                finally:
                    button.blockSignals(False)
            self.canvas.set_manual_drawing_mode(mode)
            self._sync_manual_drawing_button_visuals()
            return
        self.canvas.set_manual_drawing_mode(None)
        self._sync_manual_drawing_button_visuals()

    def _sync_manual_drawing_button_visuals(self) -> None:
        """Зробити активний manual drawing tool помітним без окремої іконки."""
        self.btn_draw_segment.setText("╱" if self.btn_draw_segment.isChecked() else "/")
        self.btn_draw_horizontal.setText(
            "━" if self.btn_draw_horizontal.isChecked() else "—"
        )
        self.btn_draw_vertical.setText(
            "┃" if self.btn_draw_vertical.isChecked() else "|"
        )

    @staticmethod
    def _configure_vertical_scrollbar(scrollbar: QScrollBar) -> None:
        scrollbar.setRange(-200, 200)
        scrollbar.setSingleStep(5)
        scrollbar.setPageStep(20)
        scrollbar.setValue(0)

    @property
    def snapshot(self) -> WorkspaceChartSnapshot | None:
        return self._snapshot

    def set_snapshot(self, snapshot: WorkspaceChartSnapshot) -> None:
        self._snapshot = snapshot
        self.canvas.set_snapshot(snapshot)
        self.macd_canvas.set_snapshot(snapshot)
        macd_visible = self.macd_canvas.has_macd_series(snapshot)
        self.macd_panel.setVisible(macd_visible)
        if macd_visible and not self._macd_splitter_initialized:
            self.splitter.setSizes([300, 120])
            self._macd_splitter_initialized = True
        maximum_start = max(0, snapshot.total_events - snapshot.visible_count)
        self.scrollbar.blockSignals(True)
        try:
            self.scrollbar.setRange(0, maximum_start)
            self.scrollbar.setPageStep(max(1, snapshot.visible_count))
            self.scrollbar.setValue(snapshot.visible_start)
        finally:
            self.scrollbar.blockSignals(False)
        self.btn_latest.setEnabled(snapshot.total_events > 0 and not snapshot.at_latest)
        self._refresh_status()

    def set_owned_snapshot(self, snapshot: WorkspaceOwnedSnapshot) -> None:
        """Передати exact WSP-owned positions у price overlay."""
        self.canvas.set_owned_snapshot(snapshot)

    def focus_timestamp(
        self,
        timestamp: datetime,
        *,
        exact: bool = True,
    ) -> bool:
        """Зафіксувати crosshair на свічці без руху системної миші."""
        snapshot = self._snapshot
        if snapshot is None or not snapshot.visible_events:
            return False

        local_index: int | None = None
        if exact:
            for index, event in enumerate(snapshot.visible_events):
                if event.timestamp == timestamp:
                    local_index = index
                    break
        else:
            for index, event in enumerate(snapshot.visible_events):
                if event.timestamp > timestamp:
                    break
                local_index = index

        if local_index is None:
            return False

        target_index = snapshot.visible_start + local_index
        show_on_macd = self.macd_panel.isVisible()
        self.canvas.set_crosshair_index(
            target_index,
            show_time_label=not show_on_macd,
        )
        if show_on_macd:
            self.macd_canvas.set_crosshair_index(
                target_index,
                show_time_label=True,
            )
        else:
            self.macd_canvas.clear_crosshair()
        self._canvas_hint_timer.stop()
        self._canvas_hint_hide_timer.stop()
        QToolTip.hideText()
        return True

    def set_execution_event(self, event: WorkspaceMarketEvent | None) -> None:
        """Передати останній M1 execution event без зміни strategy snapshot."""
        self.canvas.set_execution_event(event)

    def set_protection_drag_enabled(self, enabled: bool) -> None:
        """Увімкнути drag SL/TP після зовнішньої Replay-state перевірки."""
        self.canvas.set_protection_drag_enabled(enabled)

    def set_texts(
        self,
        *,
        latest_text: str,
        empty_text: str,
    ) -> None:
        self.btn_latest.setText(latest_text)
        self.canvas.set_empty_text(empty_text)
        self._refresh_status()

    def set_control_hints(
        self,
        *,
        horizontal_zoom_out: str,
        horizontal_zoom_in: str,
        vertical_zoom_out: str,
        vertical_zoom_in: str,
        vertical_pan: str,
        latest: str,
        canvas: str,
        protection_stop: str,
        protection_take: str,
        draw_segment: str = "",
        draw_horizontal: str = "",
        draw_vertical: str = "",
        draw_clear: str = "",
        drawing_start_label: str = "Start",
        drawing_end_label: str = "End",
        drawing_line_label: str = "Line",
        drawing_time_label: str = "Time UTC",
        drawing_value_label: str = "Value",
    ) -> None:
        self.btn_zoom_out.setToolTip(horizontal_zoom_out)
        self.btn_zoom_in.setToolTip(horizontal_zoom_in)
        self.btn_vertical_zoom_out.setToolTip(vertical_zoom_out)
        self.btn_vertical_zoom_in.setToolTip(vertical_zoom_in)
        self.vertical_scrollbar.setToolTip(vertical_pan)
        self.btn_macd_vertical_zoom_out.setToolTip(vertical_zoom_out)
        self.btn_macd_vertical_zoom_in.setToolTip(vertical_zoom_in)
        self.macd_vertical_scrollbar.setToolTip(vertical_pan)
        self.btn_latest.setToolTip(latest)
        self.btn_draw_segment.setToolTip(draw_segment)
        self.btn_draw_horizontal.setToolTip(draw_horizontal)
        self.btn_draw_vertical.setToolTip(draw_vertical)
        self.btn_draw_clear.setToolTip(draw_clear)
        self.lbl_status.setToolTip(canvas)
        self.lbl_help.setToolTip(canvas)
        self._canvas_hint_text = str(canvas)
        self._protection_stop_hint = str(protection_stop)
        self._protection_take_hint = str(protection_take)
        self.canvas.set_manual_drawing_hover_labels(
            start_label=drawing_start_label,
            end_label=drawing_end_label,
            line_label=drawing_line_label,
            time_label=drawing_time_label,
            value_label=drawing_value_label,
        )
        self.canvas.setToolTip("")
        self.macd_canvas.setToolTip("")

    @property
    def canvas_hint_delay_ms(self) -> int:
        return self._canvas_hint_delay_ms

    @property
    def canvas_hint_text(self) -> str:
        return self._canvas_hint_text

    @property
    def canvas_hint_hide_delay_ms(self) -> int:
        return self._canvas_hint_hide_delay_ms

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched in (self.canvas, self.macd_canvas):
            event_type = event.type()
            if event_type in (QEvent.Type.Enter, QEvent.Type.MouseMove):
                if watched is self.canvas and self.canvas.protection_hover_field:
                    self._canvas_hint_timer.stop()
                else:
                    self._restart_canvas_hint_timer()
            elif event_type in (
                QEvent.Type.Leave,
                QEvent.Type.MouseButtonPress,
                QEvent.Type.Wheel,
            ):
                self._canvas_hint_timer.stop()
                self._canvas_hint_hide_timer.stop()
                QToolTip.hideText()
            elif event_type == QEvent.Type.ToolTip:
                return True
        return super().eventFilter(watched, event)

    def _restart_canvas_hint_timer(self) -> None:
        self._canvas_hint_timer.stop()
        self._canvas_hint_hide_timer.stop()
        QToolTip.hideText()
        if self._canvas_hint_text:
            self._canvas_hint_timer.start()

    def _show_delayed_canvas_hint(self) -> None:
        target: QWidget | None = None
        if self.canvas.underMouse():
            target = self.canvas
        elif self.macd_canvas.underMouse():
            target = self.macd_canvas
        if target is None or not self._canvas_hint_text:
            return
        position = QCursor.pos() + QPoint(16, 18)
        QToolTip.showText(
            position,
            self._canvas_hint_text,
            target,
            QRect(),
            _TOOLTIP_DISPLAY_MS,
        )
        self._canvas_hint_hide_timer.start()

    def _show_protection_hover_hint(self, field_name: str) -> None:
        """Показати коротку локальну підказку для draggable SL/TP."""
        self._canvas_hint_timer.stop()
        self._canvas_hint_hide_timer.stop()
        hint = (
            self._protection_stop_hint
            if field_name == "stop_loss"
            else self._protection_take_hint if field_name == "take_profit" else ""
        )
        if hint:
            QToolTip.showText(
                QCursor.pos() + QPoint(16, 18),
                hint,
                self.canvas,
                QRect(),
                _TOOLTIP_DISPLAY_MS,
            )
            self._canvas_hint_hide_timer.start()

    def _show_manual_drawing_hover_hint(self, text: str) -> None:
        """Показати координати точки або геометрію ручної лінії."""
        self._canvas_hint_timer.stop()
        self._canvas_hint_hide_timer.stop()
        if text:
            QToolTip.showText(
                QCursor.pos() + QPoint(16, 18),
                str(text),
                self.canvas,
                QRect(),
                _TOOLTIP_DISPLAY_MS,
            )
            self._canvas_hint_hide_timer.start()

    def _clear_manual_drawing_hover_hint(self) -> None:
        """Прибрати координатну підказку після виходу з manual line hit-zone."""
        self._canvas_hint_hide_timer.stop()
        QToolTip.hideText()

    def _clear_protection_hover_hint(self) -> None:
        """Прибрати локальну SL/TP підказку після виходу з hit-zone."""
        self._canvas_hint_hide_timer.stop()
        QToolTip.hideText()

    def _sync_price_hover(self, index: int) -> None:
        show_on_macd = self.macd_panel.isVisible()
        self.canvas.set_time_label_visible(not show_on_macd)
        self.macd_canvas.set_crosshair_index(
            int(index),
            show_time_label=show_on_macd,
        )

    def _sync_macd_hover(self, index: int) -> None:
        self.macd_canvas.set_time_label_visible(True)
        self.canvas.set_crosshair_index(int(index), show_time_label=False)

    def _clear_crosshair(self) -> None:
        self.canvas.clear_crosshair()
        self.macd_canvas.clear_crosshair()

    def _install_keyboard_shortcuts(self) -> None:
        self._add_shortcut("-", lambda: self._request_zoom(1.25))
        self._add_shortcut("+", lambda: self._request_zoom(0.8))
        self._add_shortcut("Ctrl+-", lambda: self._zoom_active_vertical(1))
        self._add_shortcut("Ctrl++", lambda: self._zoom_active_vertical(-1))
        self._add_shortcut("Left", lambda: self._request_pan_delta(-1))
        self._add_shortcut("Right", lambda: self._request_pan_delta(1))
        self._add_shortcut(
            "Up",
            lambda: self._request_active_vertical_pan_delta(-1),
        )
        self._add_shortcut(
            "Down",
            lambda: self._request_active_vertical_pan_delta(1),
        )
        self._add_shortcut("Home", self._request_first)
        self._add_shortcut("End", self.latest_requested.emit)

    def _add_shortcut(
        self,
        sequence: str,
        handler: Callable[[], object],
    ) -> None:
        shortcut = QShortcut(QKeySequence(sequence), self)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(handler)
        self._shortcuts.append(shortcut)

    def _active_vertical_canvas(
        self,
    ) -> WorkspaceCandlestickCanvas | WorkspaceMacdCanvas:
        focus = QApplication.focusWidget()
        if focus is not None and self.macd_panel.isAncestorOf(focus):
            return self.macd_canvas
        return self.canvas

    def _active_vertical_scrollbar(self) -> QScrollBar:
        focus = QApplication.focusWidget()
        if focus is not None and self.macd_panel.isAncestorOf(focus):
            return self.macd_vertical_scrollbar
        return self.vertical_scrollbar

    def _zoom_active_vertical(self, direction: int) -> None:
        self._active_vertical_canvas().zoom_vertical(direction)

    def _request_pan_delta(self, direction: int) -> None:
        snapshot = self._snapshot
        if snapshot is None:
            return
        maximum_start = max(0, snapshot.total_events - snapshot.visible_count)
        step = max(1, snapshot.visible_count // 10)
        target = snapshot.visible_start + int(direction) * step
        target = min(maximum_start, max(0, target))
        if target != snapshot.visible_start:
            self.visible_start_requested.emit(target)

    def _request_active_vertical_pan_delta(self, direction: int) -> None:
        scrollbar = self._active_vertical_scrollbar()
        step = scrollbar.singleStep()
        target = scrollbar.value() + int(direction) * step
        scrollbar.setValue(target)

    def _request_first(self) -> None:
        snapshot = self._snapshot
        if snapshot is not None and snapshot.visible_start != 0:
            self.visible_start_requested.emit(0)

    def _on_wheel_zoom(self, direction: int) -> None:
        self._request_zoom(0.8 if direction < 0 else 1.25)

    def _request_zoom(self, factor: float) -> None:
        snapshot = self._snapshot
        if snapshot is None:
            return
        visible_count = max(
            MIN_WORKSPACE_CHART_VISIBLE_EVENTS,
            int(round(snapshot.visible_count * factor)),
        )
        self.visible_count_requested.emit(visible_count)

    def _on_scrollbar_changed(self, value: int) -> None:
        self.visible_start_requested.emit(int(value))

    def _on_vertical_scrollbar_changed(self, value: int) -> None:
        self.canvas.set_vertical_pan_ratio(-float(value) / 100.0)

    def _on_macd_vertical_scrollbar_changed(self, value: int) -> None:
        self.macd_canvas.set_vertical_pan_ratio(-float(value) / 100.0)

    def _refresh_status(self) -> None:
        snapshot = self._snapshot
        if snapshot is None or snapshot.cursor_timestamp is None:
            self.lbl_status.setText("—")
            return
        timestamp = snapshot.cursor_timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
        close_text = self._format_price(snapshot.current_close)
        bid_text = self._format_price(snapshot.current_bid)
        ask_text = self._format_price(snapshot.current_ask)
        spread_text = self._format_price(snapshot.current_spread)
        self.lbl_status.setText(
            f"{timestamp} • close {close_text} • bid {bid_text} • "
            f"ask {ask_text} • spread {spread_text}"
        )

    @staticmethod
    def _format_price(value: float | None) -> str:
        if value is None:
            return "—"
        return f"{value:.6f}"
