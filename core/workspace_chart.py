# core/workspace_chart.py — історія та viewport одного WSP
# -*- coding: utf-8 -*-
"""Broker-neutral модель історії та viewport діаграми WSP.

Модель зберігає bounded tail для runtime, а у Replay може мати окремо
прикріплену immutable історію без відкриття майбутніх барів.
RoadMap99_04C додає перехід до вже обробленого timestamp, щоб Positions
міг показати signal bar або entry bar. Перехід змінює лише viewport;
market data, algorithm state і trading logic не змінюються.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.workspace_market_event import WorkspaceMarketEvent
from engine.runtime_constants import (
    DEFAULT_WORKSPACE_CHART_MAX_EVENTS,
    DEFAULT_WORKSPACE_CHART_VISIBLE_EVENTS,
    MAX_WORKSPACE_CHART_VISIBLE_EVENTS,
    MIN_WORKSPACE_CHART_VISIBLE_EVENTS,
)


WORKSPACE_CHART_ROLE_PRICE_OVERLAY = "PRICE_OVERLAY"
WORKSPACE_CHART_ROLE_INDICATOR_LINE = "INDICATOR_LINE"
WORKSPACE_CHART_ROLE_INDICATOR_HISTOGRAM = "INDICATOR_HISTOGRAM"


@dataclass(frozen=True, slots=True)
class WorkspaceChartSeriesPoint:
    """One bounded chart-series point aligned to a visible market bar."""

    timestamp: datetime
    value: float
    source_timestamp: datetime | None = None
    available_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceChartSeries:
    """One read-only chart series produced by the active algorithm."""

    series_code: str
    role: str
    label: str
    timeframe: str
    profile_uid: str
    profile_revision: int
    points: tuple[WorkspaceChartSeriesPoint, ...]


class WorkspaceChartError(RuntimeError):
    """Raised when a chart viewport request is invalid."""


@dataclass(frozen=True, slots=True)
class WorkspaceChartSnapshot:
    """Immutable chart state with bounded retained events and viewport."""

    events: tuple[WorkspaceMarketEvent, ...]
    visible_events: tuple[WorkspaceMarketEvent, ...]
    total_events: int
    visible_start: int
    visible_end: int
    visible_count: int
    cursor_index: int | None
    cursor_timestamp: datetime | None
    current_close: float | None
    current_bid: float | None
    current_ask: float | None
    current_spread: float | None
    at_latest: bool
    series: tuple[WorkspaceChartSeries, ...] = ()


class WorkspaceChartModel:
    """Bounded OHLC tail with optional full Replay viewport history."""

    def __init__(
        self,
        *,
        max_events: int = DEFAULT_WORKSPACE_CHART_MAX_EVENTS,
        visible_count: int = DEFAULT_WORKSPACE_CHART_VISIBLE_EVENTS,
    ) -> None:
        normalized_max = int(max_events)
        if normalized_max < MIN_WORKSPACE_CHART_VISIBLE_EVENTS:
            raise WorkspaceChartError(
                "max_events must be at least "
                f"{MIN_WORKSPACE_CHART_VISIBLE_EVENTS}"
            )
        self.max_events = normalized_max
        self._events: list[WorkspaceMarketEvent] = []
        self._full_history: tuple[WorkspaceMarketEvent, ...] | None = None
        self._processed_history_count = 0
        self._visible_count = self._normalize_visible_count(visible_count)
        self._visible_start = 0
        self._follow_latest = True
        self._cursor_index: int | None = None

    @property
    def total_events(self) -> int:
        if self._full_history is not None:
            return self._processed_history_count
        return len(self._events)

    @property
    def visible_count(self) -> int:
        return self._visible_count

    @property
    def visible_start(self) -> int:
        return self._visible_start

    @property
    def at_latest(self) -> bool:
        return self._follow_latest

    def clear(self) -> None:
        """Clear volatile chart history before a new WSP runtime start."""
        self._events.clear()
        self._full_history = None
        self._processed_history_count = 0
        self._visible_start = 0
        self._follow_latest = True
        self._cursor_index = None

    def attach_full_history(
        self,
        events: tuple[WorkspaceMarketEvent, ...],
    ) -> None:
        """Attach immutable Replay history without exposing future bars."""
        if self._events or self._cursor_index is not None:
            raise WorkspaceChartError(
                "Full chart history must be attached before market events"
            )
        for index in range(1, len(events)):
            if events[index].timestamp <= events[index - 1].timestamp:
                raise WorkspaceChartError(
                    "Full chart history must be strictly chronological"
                )
        self._full_history = events
        self._processed_history_count = 0
        self._visible_start = 0
        self._follow_latest = True

    def append(self, event: WorkspaceMarketEvent) -> None:
        """Append or replace one chronological canonical market event."""
        if self._events:
            last_event = self._events[-1]
            if event.timestamp < last_event.timestamp:
                raise WorkspaceChartError(
                    "Chart market events must be chronological"
                )
            if event.timestamp == last_event.timestamp:
                self._validate_full_history_replacement(event)
                self._events[-1] = event
                self._cursor_index = self.total_events - 1
                self._align_viewport_after_event()
                return

        self._validate_full_history_append(event)
        self._events.append(event)
        if self._full_history is not None:
            self._processed_history_count += 1
        overflow = len(self._events) - self.max_events
        if overflow > 0:
            del self._events[:overflow]
            if self._full_history is None:
                self._visible_start = max(0, self._visible_start - overflow)

        self._cursor_index = self.total_events - 1
        self._align_viewport_after_event()

    def extend(self, events: tuple[WorkspaceMarketEvent, ...]) -> None:
        """Append multiple events through the same chronology rules."""
        for event in events:
            self.append(event)

    def set_visible_count(self, visible_count: int) -> None:
        """Set zoom level while keeping the current right edge stable."""
        previous_end = self._visible_end()
        self._visible_count = self._normalize_visible_count(visible_count)
        if self._follow_latest:
            self._visible_start = self._latest_start()
            return
        self._visible_start = self._clamp_start(
            previous_end - self._visible_count
        )
        self._follow_latest = self._visible_start == self._latest_start()

    def zoom_in(self) -> None:
        """Show fewer bars around the current right edge."""
        target = max(
            MIN_WORKSPACE_CHART_VISIBLE_EVENTS,
            int(round(self._visible_count * 0.8)),
        )
        self.set_visible_count(target)

    def zoom_out(self) -> None:
        """Show more bars around the current right edge."""
        target = min(
            self._maximum_visible_count(),
            int(round(self._visible_count * 1.25)),
        )
        self.set_visible_count(target)

    def scroll_to(self, visible_start: int) -> None:
        """Move the viewport to an absolute available history index."""
        self._visible_start = self._clamp_start(int(visible_start))
        self._follow_latest = self._visible_start == self._latest_start()

    def scroll_by(self, delta: int) -> None:
        """Move the viewport by signed bars."""
        self.scroll_to(self._visible_start + int(delta))

    def scroll_to_timestamp(
        self,
        timestamp: datetime,
        *,
        exact: bool = True,
    ) -> bool:
        """Перейти до exact bar або до останнього bar не пізніше timestamp."""
        history = self._available_history()
        low = 0
        high = len(history)
        while low < high:
            middle = (low + high) // 2
            middle_timestamp = history[middle].timestamp
            if middle_timestamp < timestamp:
                low = middle + 1
            else:
                high = middle
        if exact:
            if low >= len(history) or history[low].timestamp != timestamp:
                return False
            target_index = low
        elif low < len(history) and history[low].timestamp == timestamp:
            target_index = low
        else:
            target_index = low - 1
            if target_index < 0:
                return False
        self.scroll_to(target_index - self._visible_count // 2)
        return True

    def scroll_to_latest(self) -> None:
        """Follow the newest market event."""
        self._follow_latest = True
        self._visible_start = self._latest_start()

    def snapshot(self) -> WorkspaceChartSnapshot:
        """Return one immutable chart snapshot for UI rendering and tests."""
        total_events = self.total_events
        visible_start = self._clamp_start(self._visible_start)
        visible_end = min(total_events, visible_start + self._visible_count)
        visible_events = self._visible_events(visible_start, visible_end)
        cursor_index = self._cursor_index
        cursor_event = self._cursor_event(cursor_index, total_events)

        return WorkspaceChartSnapshot(
            events=tuple(self._events),
            visible_events=visible_events,
            total_events=total_events,
            visible_start=visible_start,
            visible_end=visible_end,
            visible_count=self._visible_count,
            cursor_index=cursor_index,
            cursor_timestamp=(
                cursor_event.timestamp if cursor_event is not None else None
            ),
            current_close=(
                cursor_event.close if cursor_event is not None else None
            ),
            current_bid=cursor_event.bid if cursor_event is not None else None,
            current_ask=cursor_event.ask if cursor_event is not None else None,
            current_spread=(
                cursor_event.spread if cursor_event is not None else None
            ),
            at_latest=self._follow_latest,
        )

    def _align_viewport_after_event(self) -> None:
        if self._follow_latest:
            self._visible_start = self._latest_start()
        else:
            self._visible_start = self._clamp_start(self._visible_start)

    def _visible_end(self) -> int:
        return min(self.total_events, self._visible_start + self._visible_count)

    def _latest_start(self) -> int:
        return max(0, self.total_events - self._visible_count)

    def _available_history(self) -> tuple[WorkspaceMarketEvent, ...]:
        full_history = self._full_history
        if full_history is None:
            return tuple(self._events)
        return full_history[: self._processed_history_count]

    def _visible_events(
        self,
        visible_start: int,
        visible_end: int,
    ) -> tuple[WorkspaceMarketEvent, ...]:
        full_history = self._full_history
        if full_history is None:
            return tuple(self._events[visible_start:visible_end])
        return full_history[visible_start:visible_end]

    def _cursor_event(
        self,
        cursor_index: int | None,
        total_events: int,
    ) -> WorkspaceMarketEvent | None:
        if cursor_index is None or not 0 <= cursor_index < total_events:
            return None
        full_history = self._full_history
        if full_history is not None:
            return full_history[cursor_index]
        return self._events[cursor_index]

    def _validate_full_history_append(
        self,
        event: WorkspaceMarketEvent,
    ) -> None:
        full_history = self._full_history
        if full_history is None:
            return
        index = self._processed_history_count
        if index >= len(full_history) or event != full_history[index]:
            raise WorkspaceChartError(
                "Replay chart event does not match attached full history"
            )

    def _validate_full_history_replacement(
        self,
        event: WorkspaceMarketEvent,
    ) -> None:
        full_history = self._full_history
        if full_history is None:
            return
        index = self._processed_history_count - 1
        if index < 0 or event != full_history[index]:
            raise WorkspaceChartError(
                "Replay chart replacement does not match full history"
            )

    def _maximum_visible_count(self) -> int:
        return min(MAX_WORKSPACE_CHART_VISIBLE_EVENTS, self.max_events)

    def _normalize_visible_count(self, visible_count: int) -> int:
        return min(
            self._maximum_visible_count(),
            max(MIN_WORKSPACE_CHART_VISIBLE_EVENTS, int(visible_count)),
        )

    def _clamp_start(self, visible_start: int) -> int:
        return min(self._latest_start(), max(0, int(visible_start)))
