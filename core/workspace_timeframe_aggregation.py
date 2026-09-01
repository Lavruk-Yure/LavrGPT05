# -*- coding: utf-8 -*-
"""Складання завершених старших bars із timeframe WSP."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from core.timeframes import get_timeframe
from core.workspace_market_event import WorkspaceMarketEvent


class WorkspaceTimeframeAggregationError(ValueError):
    """Порушення порядку, binding або часової сітки."""


@dataclass(frozen=True, slots=True)
class WorkspaceCompletedTimeframeBar:
    """Старший bar, доступний після завершення bucket."""

    event: WorkspaceMarketEvent
    completed_at: datetime
    source_bars: int


class WorkspaceTimeframeAggregator:
    """Скласти повні старші bars без look-ahead."""

    def __init__(self, *, source_timeframe: str, target_timeframe: str) -> None:
        source = get_timeframe(source_timeframe)
        target = get_timeframe(target_timeframe)
        if target.minutes <= source.minutes:
            raise WorkspaceTimeframeAggregationError(
                "target_timeframe must be higher than source_timeframe"
            )
        if target.minutes % source.minutes != 0:
            raise WorkspaceTimeframeAggregationError(
                "target_timeframe must be an integer source multiple"
            )
        self.source_timeframe = source.name
        self.target_timeframe = target.name
        self.source_minutes = source.minutes
        self.target_minutes = target.minutes
        self.expected_source_bars = target.minutes // source.minutes
        self._source_delta = timedelta(minutes=source.minutes)
        self._target_delta = timedelta(minutes=target.minutes)
        self._last_timestamp: datetime | None = None
        self._bucket_start: datetime | None = None
        self._bucket_events: list[WorkspaceMarketEvent] = []
        self._binding: tuple[str, str, str] | None = None
        self._completed_bars = 0
        self._dropped_incomplete_buckets = 0
        self._last_boundary_crossed = False
        self._last_boundary_was_incomplete = False

    def reset(self) -> None:
        """Очистити volatile aggregation state одного Replay run."""
        self._last_timestamp = None
        self._bucket_start = None
        self._bucket_events = []
        self._binding = None
        self._completed_bars = 0
        self._dropped_incomplete_buckets = 0
        self._last_boundary_crossed = False
        self._last_boundary_was_incomplete = False

    @property
    def completed_bars(self) -> int:
        return self._completed_bars

    @property
    def dropped_incomplete_buckets(self) -> int:
        return self._dropped_incomplete_buckets

    @property
    def active_source_bars(self) -> int:
        return len(self._bucket_events)

    @property
    def last_boundary_crossed(self) -> bool:
        return self._last_boundary_crossed

    @property
    def last_boundary_was_incomplete(self) -> bool:
        return self._last_boundary_was_incomplete

    def on_market_event(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceCompletedTimeframeBar | None:
        """Прийняти source bar і повернути готовий bucket."""
        self._validate_event(event)
        self._last_boundary_crossed = False
        self._last_boundary_was_incomplete = False
        bucket_start = self._bucket_start_for(event.timestamp)
        completed: WorkspaceCompletedTimeframeBar | None = None
        if self._bucket_start is None:
            self._bucket_start = bucket_start
        elif bucket_start != self._bucket_start:
            if bucket_start < self._bucket_start:
                raise WorkspaceTimeframeAggregationError(
                    "timeframe buckets must be strictly ordered"
                )
            self._last_boundary_crossed = True
            skipped_buckets = (
                int((bucket_start - self._bucket_start) // self._target_delta) - 1
            )
            if skipped_buckets > 0:
                self._dropped_incomplete_buckets += skipped_buckets
                self._last_boundary_was_incomplete = True
            completed = self._finish_current_bucket(event.timestamp)
            self._bucket_start = bucket_start
            self._bucket_events = []

        self._bucket_events.append(event)
        self._last_timestamp = event.timestamp
        return completed

    def complete(self) -> WorkspaceCompletedTimeframeBar | None:
        """Finish the last complete bucket without inventing source bars."""
        if self._bucket_start is None or not self._bucket_events:
            return None
        available_at = self._bucket_start + self._target_delta
        completed = self._finish_current_bucket(available_at)
        self._bucket_start = None
        self._bucket_events = []
        return completed

    def _validate_event(self, event: WorkspaceMarketEvent) -> None:
        if event.timeframe != self.source_timeframe:
            raise WorkspaceTimeframeAggregationError(
                f"expected {self.source_timeframe}, got {event.timeframe}"
            )
        if not self._timestamp_is_aligned(event.timestamp, self.source_minutes):
            raise WorkspaceTimeframeAggregationError(
                f"{self.source_timeframe} timestamp is outside its UTC grid"
            )
        if self._last_timestamp is not None:
            if event.timestamp <= self._last_timestamp:
                raise WorkspaceTimeframeAggregationError(
                    "source bars must be strictly ordered and unique"
                )

        binding = (event.broker, event.symbol, event.source_mode)
        if self._binding is None:
            self._binding = binding
        elif binding != self._binding:
            raise WorkspaceTimeframeAggregationError(
                "source bar binding changed inside one aggregator"
            )

    def _finish_current_bucket(
        self,
        available_at: datetime,
    ) -> WorkspaceCompletedTimeframeBar | None:
        bucket_start = self._bucket_start
        if bucket_start is None or not self._bucket_events:
            return None
        completed_at = bucket_start + self._target_delta
        if completed_at > available_at:
            raise WorkspaceTimeframeAggregationError(
                "higher timeframe bar cannot complete in the future"
            )
        if not self._current_bucket_is_complete():
            self._dropped_incomplete_buckets += 1
            self._last_boundary_was_incomplete = True
            return None

        first = self._bucket_events[0]
        last = self._bucket_events[-1]
        event = WorkspaceMarketEvent(
            timestamp=bucket_start,
            broker=first.broker,
            symbol=first.symbol,
            timeframe=self.target_timeframe,
            bid=last.bid,
            ask=last.ask,
            spread=last.ask - last.bid,
            open=first.open,
            high=max(item.high for item in self._bucket_events),
            low=min(item.low for item in self._bucket_events),
            close=last.close,
            volume=sum(item.volume for item in self._bucket_events),
            source_mode=first.source_mode,
        )
        self._completed_bars += 1
        return WorkspaceCompletedTimeframeBar(
            event=event,
            completed_at=completed_at,
            source_bars=len(self._bucket_events),
        )

    def _current_bucket_is_complete(self) -> bool:
        bucket_start = self._bucket_start
        if bucket_start is None:
            return False
        if len(self._bucket_events) != self.expected_source_bars:
            return False
        expected_timestamps = tuple(
            bucket_start + self._source_delta * index
            for index in range(self.expected_source_bars)
        )
        actual_timestamps = tuple(item.timestamp for item in self._bucket_events)
        return actual_timestamps == expected_timestamps

    def _bucket_start_for(self, timestamp: datetime) -> datetime:
        normalized = timestamp.astimezone(UTC)
        bucket_seconds = self.target_minutes * 60
        epoch_seconds = int(normalized.timestamp())
        start_seconds = epoch_seconds - epoch_seconds % bucket_seconds
        return datetime.fromtimestamp(start_seconds, tz=UTC)

    @staticmethod
    def _timestamp_is_aligned(timestamp: datetime, minutes: int) -> bool:
        normalized = timestamp.astimezone(UTC)
        if normalized.second != 0 or normalized.microsecond != 0:
            return False
        return int(normalized.timestamp()) % (minutes * 60) == 0
