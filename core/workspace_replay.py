# -*- coding: utf-8 -*-
"""Детерміновані Replay providers для Algorithm Workspace runtime.

Модуль формує immutable Replay sessions, керує швидкостями від 1x до MAX
і MAX FAST та гарантує кероване повернення в UI event loop. MAX лишається
консервативним bounded режимом для живої діагностики. MAX FAST використовує
ту саму deterministic chronology, але адаптує compute batch до короткого
часового бюджету та рідше виконує важкий UI refresh. Trading/replay events при
цьому не пропускаються, а Pause/Stop мають регулярну точку обробки Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from core.algorithm_workspace import WORKSPACE_DATA_MODE_REPLAY
from core.timeframes import get_timeframe
from core.workspace_history import (
    WorkspaceCsvHistoryLoader,
    WorkspaceHistoryError,
    WorkspaceHistoryReport,
)
from core.workspace_market_event import (
    WorkspaceMarketBar,
    WorkspaceMarketEvent,
    normalize_market_timestamp,
)
from core.workspace_timeframe_aggregation import (
    WorkspaceCompletedTimeframeBar,
    WorkspaceTimeframeAggregationError,
    WorkspaceTimeframeAggregator,
)
from engine.runtime_constants import (
    DEFAULT_WORKSPACE_HISTORY_DECIMAL_SEPARATOR,
    DEFAULT_WORKSPACE_HISTORY_DELIMITER,
    DEFAULT_WORKSPACE_HISTORY_SPREAD,
    DEFAULT_WORKSPACE_HISTORY_TIMEZONE,
    DEFAULT_WORKSPACE_REPLAY_SOURCE,
    WORKSPACE_REPLAY_SOURCE_CSV,
    WORKSPACE_REPLAY_SOURCE_SYNTHETIC,
    resolve_workspace_history_default_spread,
)

# ``0`` is a persisted sentinel for MAX; ``-1`` is MAX FAST. Neither value
# means paused or stopped. Both modes yield to Qt after a bounded compute chunk.
# MAX refreshes normal diagnostics after every chunk. MAX FAST keeps all Replay
# calculations but throttles expensive full UI refresh to a short interval.
REPLAY_SPEED_MAX = 0
REPLAY_SPEED_MAX_FAST = -1
REPLAY_MAX_EVENTS_PER_CYCLE = 16
REPLAY_MAX_FAST_TIME_BUDGET_SECONDS = 0.040
REPLAY_MAX_FAST_ADAPTIVE_MAX_EVENTS = 256
REPLAY_MAX_FAST_UI_REFRESH_SECONDS = 0.50
REPLAY_SPEEDS = (
    1,
    2,
    5,
    10,
    100,
    1000,
    REPLAY_SPEED_MAX,
    REPLAY_SPEED_MAX_FAST,
)
REPLAY_STATE_READY = "READY"
REPLAY_STATE_RUNNING = "RUNNING"
REPLAY_STATE_PAUSED = "PAUSED"
REPLAY_STATE_COMPLETED = "COMPLETED"
REPLAY_STATE_STOPPED = "STOPPED"


class WorkspaceReplayError(RuntimeError):
    """Replay lifecycle or configuration error."""


def replay_speed_label(speed: int) -> str:
    """Return the canonical UI/journal label for a persisted Replay speed."""
    normalized = int(speed)
    if normalized == REPLAY_SPEED_MAX:
        return "MAX"
    if normalized == REPLAY_SPEED_MAX_FAST:
        return "MAX FAST"
    return f"{normalized}x"


def replay_events_per_cycle(speed: int) -> int:
    """Return the logical number of strategy events requested by one cycle."""
    normalized = int(speed)
    if normalized not in REPLAY_SPEEDS:
        raise WorkspaceReplayError(f"Unsupported Replay speed: {speed}")
    if normalized in {REPLAY_SPEED_MAX, REPLAY_SPEED_MAX_FAST}:
        return REPLAY_MAX_EVENTS_PER_CYCLE
    return normalized


def replay_ui_cycle_quota(speed: int) -> int | None:
    """Return logical per-cycle quota; ``None`` means continuous MAX burst."""
    normalized = int(speed)
    if normalized not in REPLAY_SPEEDS:
        raise WorkspaceReplayError(f"Unsupported Replay speed: {speed}")
    if normalized in {REPLAY_SPEED_MAX, REPLAY_SPEED_MAX_FAST}:
        return None
    return normalized


def replay_max_fast_next_batch_size(
    previous_events: int,
    elapsed_seconds: float,
) -> int:
    """Estimate the next MAX FAST batch inside the short UI time budget.

    The estimate follows measured throughput, but growth/shrink per batch is
    deliberately bounded. This prevents one unusually cheap batch from
    creating a long uninterruptible GUI-thread call. The legacy 16-event
    chunk remains the minimum safety rail; the adaptive ceiling is intentionally
    finite and does not alter Replay chronology.
    """
    previous = max(REPLAY_MAX_EVENTS_PER_CYCLE, int(previous_events))
    elapsed = max(0.000001, float(elapsed_seconds))
    throughput_target = int(
        round(previous * REPLAY_MAX_FAST_TIME_BUDGET_SECONDS / elapsed)
    )
    lower_bound = max(REPLAY_MAX_EVENTS_PER_CYCLE, previous // 2)
    upper_bound = min(
        REPLAY_MAX_FAST_ADAPTIVE_MAX_EVENTS,
        max(REPLAY_MAX_EVENTS_PER_CYCLE, previous * 2),
    )
    return max(lower_bound, min(upper_bound, throughput_target))


def replay_ui_should_refresh(speed: int, elapsed_seconds: float) -> bool:
    """Return whether a high-speed burst should perform one full UI refresh.

    Normal speeds and MAX refresh after every bounded chunk. MAX FAST alone
    throttles heavy chart/table/journal synchronization while compute keeps
    running; Pause/Stop still remain responsive because every compute chunk
    yields to the Qt event loop.
    """
    normalized = int(speed)
    if normalized not in REPLAY_SPEEDS:
        raise WorkspaceReplayError(f"Unsupported Replay speed: {speed}")
    if normalized != REPLAY_SPEED_MAX_FAST:
        return True
    return max(0.0, float(elapsed_seconds)) >= REPLAY_MAX_FAST_UI_REFRESH_SECONDS


def replay_ui_batch_size(remaining: int | None) -> int:
    """Bound one GUI-thread Replay chunk before yielding to the Qt event loop."""
    if remaining is None:
        return REPLAY_MAX_EVENTS_PER_CYCLE
    normalized = max(0, int(remaining))
    return min(REPLAY_MAX_EVENTS_PER_CYCLE, normalized)


@dataclass(slots=True)
class WorkspaceReplaySession:
    """Cursor over one immutable, repeatable sequence of market events."""

    events: tuple[WorkspaceMarketEvent, ...]
    source_name: str = "SYNTHETIC"
    speed: int = 1
    index: int = 0
    state: str = REPLAY_STATE_READY
    in_step: bool = False
    history_report: WorkspaceHistoryReport | None = None
    execution_windows: tuple[tuple[WorkspaceMarketEvent, ...], ...] = ()
    source_timeframe: str | None = None
    strategy_timeframe: str | None = None
    source_event_count: int = 0
    dropped_incomplete_strategy_buckets: int = 0

    def __post_init__(self) -> None:
        if not self.events:
            raise WorkspaceReplayError("Replay session requires market events")
        self.source_name = str(self.source_name or "SYNTHETIC").strip().upper()
        self.set_speed(self.speed)
        if self.index < 0 or self.index > len(self.events):
            raise WorkspaceReplayError("Invalid Replay index")
        if self.execution_windows and len(self.execution_windows) != len(self.events):
            raise WorkspaceReplayError(
                "execution_windows must match strategy event count"
            )
        self.source_timeframe = str(self.source_timeframe or "").strip().upper() or None
        self.strategy_timeframe = (
            str(self.strategy_timeframe or "").strip().upper() or None
        )
        if self.source_event_count < 0:
            raise WorkspaceReplayError("source_event_count cannot be negative")
        if self.dropped_incomplete_strategy_buckets < 0:
            raise WorkspaceReplayError(
                "dropped_incomplete_strategy_buckets cannot be negative"
            )

    @property
    def multi_resolution(self) -> bool:
        return bool(
            self.execution_windows
            and self.source_timeframe
            and self.strategy_timeframe
            and self.source_timeframe != self.strategy_timeframe
        )

    @property
    def last_execution_event(self) -> WorkspaceMarketEvent | None:
        if not self.execution_windows:
            return None
        for window in reversed(self.execution_windows):
            if window:
                return window[-1]
        return None

    def execution_events_for_index(
        self,
        index: int,
    ) -> tuple[WorkspaceMarketEvent, ...]:
        if not self.execution_windows:
            return ()
        if index < 0 or index >= len(self.execution_windows):
            raise WorkspaceReplayError("Invalid Replay execution window index")
        return self.execution_windows[index]

    @property
    def paused(self) -> bool:
        return self.state == REPLAY_STATE_PAUSED

    @property
    def completed(self) -> bool:
        return self.state == REPLAY_STATE_COMPLETED

    @property
    def remaining_count(self) -> int:
        return max(0, len(self.events) - self.index)

    @property
    def current_event(self) -> WorkspaceMarketEvent | None:
        if self.index <= 0:
            return None
        return self.events[self.index - 1]

    def start(self) -> None:
        if self.completed:
            self.index = 0
        self.state = REPLAY_STATE_RUNNING

    def stop(self) -> None:
        self.state = REPLAY_STATE_STOPPED
        self.in_step = False

    def pause(self) -> None:
        if self.state != REPLAY_STATE_RUNNING:
            raise WorkspaceReplayError("Replay is not running")
        self.state = REPLAY_STATE_PAUSED

    def resume(self) -> None:
        if self.state != REPLAY_STATE_PAUSED:
            raise WorkspaceReplayError("Replay is not paused")
        self.state = REPLAY_STATE_RUNNING

    def toggle_pause(self) -> bool:
        if self.state == REPLAY_STATE_PAUSED:
            self.resume()
        else:
            self.pause()
        return self.paused

    def set_speed(self, speed: int) -> None:
        normalized = int(speed)
        if normalized not in REPLAY_SPEEDS:
            raise WorkspaceReplayError(f"Unsupported Replay speed: {speed}")
        self.speed = normalized

    def step(self) -> WorkspaceMarketEvent | None:
        if self.state not in {REPLAY_STATE_RUNNING, REPLAY_STATE_PAUSED}:
            raise WorkspaceReplayError("Replay is not active")
        self.in_step = True
        try:
            return self._next_event()
        finally:
            self.in_step = False

    def advance(
        self,
        *,
        max_events: int | None = None,
    ) -> list[WorkspaceMarketEvent]:
        """Advance deterministically, optionally limiting one caller-owned chunk."""
        if self.state != REPLAY_STATE_RUNNING:
            return []
        event_limit = replay_events_per_cycle(self.speed)
        if max_events is not None:
            event_limit = min(event_limit, max(0, int(max_events)))
        emitted: list[WorkspaceMarketEvent] = []
        for _unused in range(event_limit):
            event = self._next_event()
            if event is None:
                break
            emitted.append(event)
        return emitted

    def _next_event(self) -> WorkspaceMarketEvent | None:
        if self.index >= len(self.events):
            self.state = REPLAY_STATE_COMPLETED
            return None
        event = self.events[self.index]
        self.index += 1
        if self.index >= len(self.events):
            self.state = REPLAY_STATE_COMPLETED
        return event


class WorkspaceReplayService:
    """Build deterministic Replay sessions without broker access."""

    def __init__(
        self,
        history_loader: WorkspaceCsvHistoryLoader | None = None,
    ) -> None:
        self.history_loader = history_loader or WorkspaceCsvHistoryLoader()

    DEFAULT_START_UTC = datetime(2026, 1, 2, 8, 0, tzinfo=UTC)
    DEFAULT_EVENT_COUNT = 64
    DEFAULT_BASE_PRICE = 1.10000
    DEFAULT_SPREAD = DEFAULT_WORKSPACE_HISTORY_SPREAD

    _MOVEMENTS = (
        0.00000,
        0.00018,
        0.00011,
        -0.00007,
        0.00023,
        0.00015,
        -0.00012,
        -0.00004,
        0.00009,
        0.00021,
        0.00005,
        -0.00016,
    )

    def create_session(
        self,
        *,
        broker: str,
        symbol: str,
        timeframe: str,
        replay_settings: dict[str, Any] | None = None,
    ) -> WorkspaceReplaySession:
        """Create a synthetic or CSV-backed deterministic Replay session."""
        settings = dict(replay_settings or {})
        source_type = (
            str(settings.get("source_type") or DEFAULT_WORKSPACE_REPLAY_SOURCE)
            .strip()
            .upper()
        )
        if source_type == WORKSPACE_REPLAY_SOURCE_SYNTHETIC:
            return self.create_synthetic_session(
                broker=broker,
                symbol=symbol,
                timeframe=timeframe,
                replay_settings=settings,
            )
        if source_type == WORKSPACE_REPLAY_SOURCE_CSV:
            return self.create_historical_session(
                broker=broker,
                symbol=symbol,
                timeframe=timeframe,
                replay_settings=settings,
            )
        raise WorkspaceReplayError(f"Unsupported Replay source_type: {source_type}")

    def create_historical_session(
        self,
        *,
        broker: str,
        symbol: str,
        timeframe: str,
        replay_settings: dict[str, Any] | None = None,
    ) -> WorkspaceReplaySession:
        """Create Replay from a validated local historical CSV file."""
        settings = dict(replay_settings or {})
        file_path = settings.get("file_path")
        if file_path is None or str(file_path).strip() == "":
            raise WorkspaceReplayError(
                "Historical Replay requires replay_settings.file_path"
            )
        source_timeframe = (
            str(settings.get("source_timeframe") or timeframe).strip().upper()
        )
        strategy_timeframe = str(timeframe or "").strip().upper()
        try:
            source = get_timeframe(source_timeframe)
            strategy = get_timeframe(strategy_timeframe)
        except KeyError as exc:
            raise WorkspaceReplayError(str(exc)) from exc
        if source.minutes > strategy.minutes:
            raise WorkspaceReplayError(
                "Historical source timeframe cannot exceed WSP timeframe"
            )
        if strategy.minutes % source.minutes != 0:
            raise WorkspaceReplayError(
                "WSP timeframe must be an integer source timeframe multiple"
            )
        try:
            data_set = self.history_loader.load(
                file_path=str(file_path),
                broker=broker,
                symbol=symbol,
                timeframe=source.name,
                start_utc=settings.get("start_utc"),
                end_utc=settings.get("end_utc"),
                source_timezone=str(
                    settings.get("source_timezone")
                    or DEFAULT_WORKSPACE_HISTORY_TIMEZONE
                ),
                delimiter=str(
                    settings.get("delimiter") or DEFAULT_WORKSPACE_HISTORY_DELIMITER
                ),
                decimal_separator=str(
                    settings.get("decimal_separator")
                    or DEFAULT_WORKSPACE_HISTORY_DECIMAL_SEPARATOR
                ),
                default_spread=self._positive_float(
                    settings.get("spread"),
                    resolve_workspace_history_default_spread(symbol),
                    "spread",
                    allow_zero=True,
                ),
                source_name=str(settings.get("source") or "").strip() or None,
            )
        except WorkspaceHistoryError as exc:
            raise WorkspaceReplayError(str(exc)) from exc
        if source.name == strategy.name:
            return WorkspaceReplaySession(
                events=data_set.events,
                source_name=data_set.source_name,
                speed=int(settings.get("speed", 1)),
                history_report=data_set.report,
                source_timeframe=source.name,
                strategy_timeframe=strategy.name,
                source_event_count=len(data_set.events),
            )
        try:
            completed, dropped = self._aggregate_strategy_events(
                data_set.events,
                source_timeframe=source.name,
                strategy_timeframe=strategy.name,
            )
        except WorkspaceTimeframeAggregationError as exc:
            raise WorkspaceReplayError(str(exc)) from exc
        if not completed:
            raise WorkspaceReplayError(
                "Historical source contains no complete WSP timeframe bars"
            )
        execution_windows = self._execution_windows(
            data_set.events,
            completed,
        )
        return WorkspaceReplaySession(
            events=tuple(item.event for item in completed),
            source_name=data_set.source_name,
            speed=int(settings.get("speed", 1)),
            history_report=data_set.report,
            execution_windows=execution_windows,
            source_timeframe=source.name,
            strategy_timeframe=strategy.name,
            source_event_count=len(data_set.events),
            dropped_incomplete_strategy_buckets=dropped,
        )

    @staticmethod
    def _aggregate_strategy_events(
        source_events: tuple[WorkspaceMarketEvent, ...],
        *,
        source_timeframe: str,
        strategy_timeframe: str,
    ) -> tuple[tuple[WorkspaceCompletedTimeframeBar, ...], int]:
        aggregator = WorkspaceTimeframeAggregator(
            source_timeframe=source_timeframe,
            target_timeframe=strategy_timeframe,
        )
        completed: list[WorkspaceCompletedTimeframeBar] = []
        for event in source_events:
            item = aggregator.on_market_event(event)
            if item is not None:
                completed.append(item)
        final_item = aggregator.complete()
        if final_item is not None:
            completed.append(final_item)
        return tuple(completed), aggregator.dropped_incomplete_buckets

    @staticmethod
    def _execution_windows(
        source_events: tuple[WorkspaceMarketEvent, ...],
        completed: tuple[WorkspaceCompletedTimeframeBar, ...],
    ) -> tuple[tuple[WorkspaceMarketEvent, ...], ...]:
        windows: list[tuple[WorkspaceMarketEvent, ...]] = []
        source_index = 0
        for item_index, item in enumerate(completed):
            start = item.completed_at
            end = (
                completed[item_index + 1].completed_at
                if item_index + 1 < len(completed)
                else None
            )
            while (
                source_index < len(source_events)
                and source_events[source_index].timestamp < start
            ):
                source_index += 1
            window: list[WorkspaceMarketEvent] = []
            scan_index = source_index
            while scan_index < len(source_events):
                event = source_events[scan_index]
                if end is not None and event.timestamp >= end:
                    break
                window.append(event)
                scan_index += 1
            windows.append(tuple(window))
            source_index = scan_index
        return tuple(windows)

    def create_synthetic_session(
        self,
        *,
        broker: str,
        symbol: str,
        timeframe: str,
        replay_settings: dict[str, Any] | None = None,
    ) -> WorkspaceReplaySession:
        """Create the same event sequence for the same input settings."""
        settings = dict(replay_settings or {})
        start_utc = self._parse_start(settings.get("start_utc"))
        event_count = self._positive_int(
            settings.get("event_count"),
            self.DEFAULT_EVENT_COUNT,
            "event_count",
        )
        base_price = self._positive_float(
            settings.get("base_price"),
            self.DEFAULT_BASE_PRICE,
            "base_price",
        )
        spread = self._positive_float(
            settings.get("spread"),
            resolve_workspace_history_default_spread(symbol),
            "spread",
            allow_zero=True,
        )
        speed = int(settings.get("speed", 1))
        source_name = str(settings.get("source") or "SYNTHETIC").strip().upper()
        timeframe_minutes = get_timeframe(timeframe).minutes

        bars = self._build_bars(
            start_utc=start_utc,
            timeframe_minutes=timeframe_minutes,
            event_count=event_count,
            base_price=base_price,
            spread=spread,
        )
        events = tuple(
            WorkspaceMarketEvent.from_bar(
                bar=bar,
                broker=broker,
                symbol=symbol,
                timeframe=timeframe,
                source_mode=WORKSPACE_DATA_MODE_REPLAY,
            )
            for bar in bars
        )
        return WorkspaceReplaySession(
            events=events,
            source_name=source_name,
            speed=speed,
        )

    def _build_bars(
        self,
        *,
        start_utc: datetime,
        timeframe_minutes: int,
        event_count: int,
        base_price: float,
        spread: float,
    ) -> tuple[WorkspaceMarketBar, ...]:
        bars: list[WorkspaceMarketBar] = []
        previous_close = base_price
        half_spread = spread / 2.0

        for index in range(event_count):
            movement = self._MOVEMENTS[index % len(self._MOVEMENTS)]
            drift = (index // len(self._MOVEMENTS)) * 0.00003
            open_price = previous_close
            close_price = base_price + movement + drift
            high_price = max(open_price, close_price) + 0.00009
            low_price = min(open_price, close_price) - 0.00008
            bid = close_price - half_spread
            ask = close_price + half_spread
            timestamp = start_utc + timedelta(minutes=timeframe_minutes * index)
            bars.append(
                WorkspaceMarketBar(
                    timestamp=timestamp,
                    open=round(open_price, 6),
                    high=round(high_price, 6),
                    low=round(low_price, 6),
                    close=round(close_price, 6),
                    volume=float(100 + index * 7),
                    bid=round(bid, 6),
                    ask=round(ask, 6),
                )
            )
            previous_close = close_price
        return tuple(bars)

    @classmethod
    def _parse_start(cls, value: object) -> datetime:
        if value is None or value == "":
            return cls.DEFAULT_START_UTC
        return normalize_market_timestamp(str(value))

    @staticmethod
    def _positive_int(value: object, default: int, field_name: str) -> int:
        if value is None or value == "":
            normalized = default
        else:
            value_text = str(value).strip()
            try:
                normalized = int(value_text)
            except ValueError as exc:
                try:
                    numeric_value = float(value_text)
                except ValueError:
                    raise WorkspaceReplayError(
                        f"{field_name} must be an integer"
                    ) from exc
                if not numeric_value.is_integer():
                    raise WorkspaceReplayError(
                        f"{field_name} must be an integer"
                    ) from exc
                normalized = int(numeric_value)
        if normalized <= 0:
            raise WorkspaceReplayError(f"{field_name} must be positive")
        return normalized

    @staticmethod
    def _positive_float(
        value: object,
        default: float,
        field_name: str,
        *,
        allow_zero: bool = False,
    ) -> float:
        if value is None or value == "":
            normalized = default
        else:
            value_text = str(value).strip()
            try:
                normalized = float(value_text)
            except ValueError as exc:
                raise WorkspaceReplayError(f"{field_name} must be numeric") from exc
        if normalized < 0.0 or (normalized == 0.0 and not allow_zero):
            raise WorkspaceReplayError(f"{field_name} must be positive")
        return normalized
