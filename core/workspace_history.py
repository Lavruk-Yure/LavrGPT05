# -*- coding: utf-8 -*-
"""core.workspace_history

Validated CSV history loader for deterministic WSP Replay sessions.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.algorithm_workspace import WORKSPACE_DATA_MODE_REPLAY
from core.timeframes import get_timeframe, list_enabled_timeframes
from core.workspace_market_event import (
    WorkspaceMarketBar,
    WorkspaceMarketEvent,
    normalize_market_timestamp,
)
from engine.runtime_constants import (
    DEFAULT_WORKSPACE_HISTORY_DECIMAL_SEPARATOR,
    DEFAULT_WORKSPACE_HISTORY_DELIMITER,
    DEFAULT_WORKSPACE_HISTORY_SPREAD,
    DEFAULT_WORKSPACE_HISTORY_TIMEZONE,
)

_TIMESTAMP_ALIASES = ("timestamp", "time", "datetime", "date")
_VOLUME_ALIASES = ("volume", "vol", "tick_volume")
_TIMESTAMP_FORMATS = (
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%Y.%m.%d %H:%M:%S",
    "%Y.%m.%d %H:%M",
)


class WorkspaceHistoryError(ValueError):
    """Invalid historical file, row or Replay history configuration."""


@dataclass(frozen=True, slots=True)
class WorkspaceHistoryReport:
    """Deterministic data-quality report for one loaded history range."""

    file_path: str
    input_rows: int
    accepted_rows: int
    filtered_rows: int
    derived_quotes: int
    gap_count: int
    first_timestamp: datetime
    last_timestamp: datetime


@dataclass(frozen=True, slots=True)
class WorkspaceHistoryDataSet:
    """Canonical market events and their immutable load report."""

    events: tuple[WorkspaceMarketEvent, ...]
    report: WorkspaceHistoryReport
    source_name: str


@dataclass(frozen=True, slots=True)
class WorkspaceHistoryRange:
    """First/last timestamps and detected cadence for one CSV file."""

    file_path: str
    row_count: int
    first_timestamp: datetime
    last_timestamp: datetime
    detected_timeframe: str | None = None


class WorkspaceCsvHistoryLoader:
    """Load validated OHLCV CSV rows into canonical market events."""

    def inspect_range(
        self,
        *,
        file_path: str | Path,
        source_timezone: str = DEFAULT_WORKSPACE_HISTORY_TIMEZONE,
        delimiter: str = DEFAULT_WORKSPACE_HISTORY_DELIMITER,
    ) -> WorkspaceHistoryRange:
        """Return the ordered CSV time range without loading market values."""
        path = self._resolve_path(file_path)
        timezone = self._timezone(source_timezone)
        normalized_delimiter = self._normalize_delimiter(delimiter, path)
        fieldnames, rows = self._read_rows(path, normalized_delimiter)
        headers = self._header_map(fieldnames)

        first_timestamp: datetime | None = None
        previous_timestamp: datetime | None = None
        row_count = 0
        timeframe_counts: dict[int, int] = {}
        timeframe_by_minutes = {
            get_timeframe(name).minutes: get_timeframe(name).name
            for name in list_enabled_timeframes()
        }

        for row_number, row in enumerate(rows, start=2):
            timestamp = self._parse_timestamp(
                self._required_text(
                    row,
                    headers["timestamp"],
                    "timestamp",
                    row_number,
                ),
                timezone,
                row_number,
            )
            if previous_timestamp is not None:
                if timestamp <= previous_timestamp:
                    raise WorkspaceHistoryError(
                        f"row {row_number}: timestamps must be strictly increasing"
                    )
                delta_seconds = (timestamp - previous_timestamp).total_seconds()
                delta_minutes = delta_seconds / 60.0
                rounded_minutes = int(round(delta_minutes))
                if (
                    abs(delta_minutes - rounded_minutes) < 1e-9
                    and rounded_minutes in timeframe_by_minutes
                ):
                    timeframe_counts[rounded_minutes] = (
                        timeframe_counts.get(rounded_minutes, 0) + 1
                    )
            if first_timestamp is None:
                first_timestamp = timestamp
            previous_timestamp = timestamp
            row_count += 1

        if first_timestamp is None or previous_timestamp is None:
            raise WorkspaceHistoryError("Historical CSV contains no data rows")

        detected_timeframe = self._detect_timeframe_name(
            timeframe_counts,
            timeframe_by_minutes,
        )
        return WorkspaceHistoryRange(
            file_path=str(path),
            row_count=row_count,
            first_timestamp=first_timestamp,
            last_timestamp=previous_timestamp,
            detected_timeframe=detected_timeframe,
        )

    def load(
        self,
        *,
        file_path: str | Path,
        broker: str,
        symbol: str,
        timeframe: str,
        start_utc: datetime | str | None = None,
        end_utc: datetime | str | None = None,
        source_timezone: str = DEFAULT_WORKSPACE_HISTORY_TIMEZONE,
        delimiter: str = DEFAULT_WORKSPACE_HISTORY_DELIMITER,
        decimal_separator: str = DEFAULT_WORKSPACE_HISTORY_DECIMAL_SEPARATOR,
        default_spread: float = DEFAULT_WORKSPACE_HISTORY_SPREAD,
        source_name: str | None = None,
    ) -> WorkspaceHistoryDataSet:
        """Load one strictly ordered CSV range without broker access."""
        path = self._resolve_path(file_path)
        timezone = self._timezone(source_timezone)
        normalized_delimiter = self._normalize_delimiter(delimiter, path)
        normalized_decimal = self._normalize_decimal_separator(decimal_separator)
        normalized_spread = self._non_negative_float(
            default_spread,
            "default_spread",
        )
        range_start = self._optional_utc(start_utc)
        range_end = self._optional_utc(end_utc)
        if range_start is not None and range_end is not None:
            if range_end < range_start:
                raise WorkspaceHistoryError("end_utc cannot be before start_utc")

        timeframe_delta = timedelta(minutes=get_timeframe(timeframe).minutes)
        fieldnames, rows = self._read_rows(path, normalized_delimiter)
        headers = self._header_map(fieldnames)

        events: list[WorkspaceMarketEvent] = []
        input_rows = 0
        filtered_rows = 0
        derived_quotes = 0
        gap_count = 0
        previous_timestamp: datetime | None = None

        for row_number, row in enumerate(rows, start=2):
            input_rows += 1
            timestamp = self._parse_timestamp(
                self._required_text(
                    row,
                    headers["timestamp"],
                    "timestamp",
                    row_number,
                ),
                timezone,
                row_number,
            )
            if previous_timestamp is not None:
                if timestamp <= previous_timestamp:
                    raise WorkspaceHistoryError(
                        f"row {row_number}: timestamps must be strictly increasing"
                    )
                if timestamp - previous_timestamp > timeframe_delta:
                    gap_count += 1
            previous_timestamp = timestamp

            open_price = self._number(
                row,
                headers["open"],
                "open",
                row_number,
                normalized_decimal,
            )
            high_price = self._number(
                row,
                headers["high"],
                "high",
                row_number,
                normalized_decimal,
            )
            low_price = self._number(
                row,
                headers["low"],
                "low",
                row_number,
                normalized_decimal,
            )
            close_price = self._number(
                row,
                headers["close"],
                "close",
                row_number,
                normalized_decimal,
            )
            volume = self._optional_number(
                row,
                headers.get("volume"),
                row_number,
                normalized_decimal,
                default=0.0,
            )
            bid, ask, quote_derived = self._quote_values(
                row=row,
                headers=headers,
                close_price=close_price,
                row_number=row_number,
                decimal_separator=normalized_decimal,
                default_spread=normalized_spread,
            )

            try:
                bar = WorkspaceMarketBar(
                    timestamp=timestamp,
                    open=open_price,
                    high=high_price,
                    low=low_price,
                    close=close_price,
                    volume=volume,
                    bid=bid,
                    ask=ask,
                )
                event = WorkspaceMarketEvent.from_bar(
                    bar=bar,
                    broker=broker,
                    symbol=symbol,
                    timeframe=timeframe,
                    source_mode=WORKSPACE_DATA_MODE_REPLAY,
                )
            except ValueError as exc:
                raise WorkspaceHistoryError(f"row {row_number}: {exc}") from exc

            if range_start is not None and timestamp < range_start:
                filtered_rows += 1
                continue
            if range_end is not None and timestamp > range_end:
                filtered_rows += 1
                continue
            events.append(event)
            if quote_derived:
                derived_quotes += 1

        if input_rows == 0:
            raise WorkspaceHistoryError("Historical CSV contains no data rows")
        if not events:
            raise WorkspaceHistoryError("Selected history range contains no rows")

        report = WorkspaceHistoryReport(
            file_path=str(path),
            input_rows=input_rows,
            accepted_rows=len(events),
            filtered_rows=filtered_rows,
            derived_quotes=derived_quotes,
            gap_count=gap_count,
            first_timestamp=events[0].timestamp,
            last_timestamp=events[-1].timestamp,
        )
        normalized_source = str(source_name or path.stem).strip().upper()
        if not normalized_source:
            normalized_source = "CSV_HISTORY"
        return WorkspaceHistoryDataSet(
            events=tuple(events),
            report=report,
            source_name=normalized_source,
        )

    @staticmethod
    def _resolve_path(file_path: str | Path) -> Path:
        path = Path(file_path).expanduser()
        if not path.is_absolute():
            project_root = Path(__file__).resolve().parents[1]
            path = project_root / path
        path = path.resolve()
        if not path.is_file():
            raise WorkspaceHistoryError(f"Historical CSV not found: {path}")
        return path

    @staticmethod
    def _timezone(value: str) -> ZoneInfo:
        timezone_name = str(value or "").strip()
        if not timezone_name:
            raise WorkspaceHistoryError("source_timezone is required")
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise WorkspaceHistoryError(
                f"Unknown source_timezone: {timezone_name}"
            ) from exc

    @staticmethod
    def _normalize_decimal_separator(value: str) -> str:
        normalized = str(value or "").strip()
        if normalized not in {".", ","}:
            raise WorkspaceHistoryError("decimal_separator must be '.' or ','")
        return normalized

    @staticmethod
    def _detect_timeframe_name(
        counts: dict[int, int],
        timeframe_by_minutes: dict[int, str],
    ) -> str | None:
        """Return the dominant recognized timestamp cadence, if unambiguous."""
        if not counts:
            return None
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        best_minutes, best_count = ranked[0]
        second_count = ranked[1][1] if len(ranked) > 1 else 0
        recognized = sum(counts.values())
        if recognized <= 0:
            return None
        confidence = best_count / recognized
        if confidence < 0.75 and best_count < second_count * 3:
            return None
        return timeframe_by_minutes.get(best_minutes)

    @staticmethod
    def _normalize_delimiter(value: str, path: Path) -> str:
        normalized = str(value or "").strip()
        if not normalized or normalized.upper() == "AUTO":
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                sample = handle.read(4096)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            except csv.Error as exc:
                raise WorkspaceHistoryError(
                    "Cannot detect historical CSV delimiter"
                ) from exc
            return dialect.delimiter
        if normalized == "\\t":
            return "\t"
        if len(normalized) != 1:
            raise WorkspaceHistoryError("delimiter must be one character")
        return normalized

    @staticmethod
    def _read_rows(
        path: Path,
        delimiter: str,
    ) -> tuple[list[str], list[dict[str, str | None]]]:
        rows: list[dict[str, str | None]] = []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            if reader.fieldnames is None:
                raise WorkspaceHistoryError("Historical CSV header is missing")
            fieldnames = [str(name) for name in reader.fieldnames]
            for row_number, raw_row in enumerate(reader, start=2):
                if None in raw_row:
                    raise WorkspaceHistoryError(
                        f"row {row_number}: unexpected extra CSV columns"
                    )
                row = {
                    str(key): None if value is None else str(value)
                    for key, value in raw_row.items()
                }
                rows.append(row)
        return fieldnames, rows

    @classmethod
    def _header_map(cls, fieldnames: list[str] | None) -> dict[str, str]:
        if not fieldnames:
            raise WorkspaceHistoryError("Historical CSV header is missing")
        normalized = {
            cls._normalize_header(name): name for name in fieldnames if name is not None
        }
        result: dict[str, str] = {
            "timestamp": cls._find_header(
                normalized,
                _TIMESTAMP_ALIASES,
                "timestamp/time",
            ),
            "open": cls._find_header(normalized, ("open",), "open"),
            "high": cls._find_header(normalized, ("high",), "high"),
            "low": cls._find_header(normalized, ("low",), "low"),
            "close": cls._find_header(normalized, ("close",), "close"),
        }
        volume = cls._optional_header(normalized, _VOLUME_ALIASES)
        if volume is not None:
            result["volume"] = volume
        for optional in ("bid", "ask", "spread"):
            header = cls._optional_header(normalized, (optional,))
            if header is not None:
                result[optional] = header
        return result

    @staticmethod
    def _normalize_header(value: str) -> str:
        return str(value or "").strip().lower().replace(" ", "_")

    @classmethod
    def _find_header(
        cls,
        normalized: dict[str, str],
        aliases: tuple[str, ...],
        display_name: str,
    ) -> str:
        header = cls._optional_header(normalized, aliases)
        if header is None:
            raise WorkspaceHistoryError(
                f"Historical CSV column is missing: {display_name}"
            )
        return header

    @staticmethod
    def _optional_header(
        normalized: dict[str, str],
        aliases: tuple[str, ...],
    ) -> str | None:
        for alias in aliases:
            if alias in normalized:
                return normalized[alias]
        return None

    @staticmethod
    def _required_text(
        row: dict[str, str | None],
        header: str,
        field_name: str,
        row_number: int,
    ) -> str:
        text = str(row.get(header) or "").strip()
        if not text:
            raise WorkspaceHistoryError(f"row {row_number}: {field_name} is required")
        return text

    @staticmethod
    def _parse_timestamp(
        value: str,
        source_timezone: ZoneInfo,
        row_number: int,
    ) -> datetime:
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            timestamp = datetime.fromisoformat(text)
        except ValueError:
            timestamp = None
            for timestamp_format in _TIMESTAMP_FORMATS:
                try:
                    timestamp = datetime.strptime(text, timestamp_format)
                    break
                except ValueError:
                    continue
            if timestamp is None:
                raise WorkspaceHistoryError(f"row {row_number}: invalid timestamp")
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=source_timezone)
        return timestamp.astimezone(UTC)

    @classmethod
    def _number(
        cls,
        row: dict[str, str | None],
        header: str,
        field_name: str,
        row_number: int,
        decimal_separator: str,
    ) -> float:
        text = cls._required_text(row, header, field_name, row_number)
        return cls._parse_number(
            text,
            field_name,
            row_number,
            decimal_separator,
        )

    @classmethod
    def _optional_number(
        cls,
        row: dict[str, str | None],
        header: str | None,
        row_number: int,
        decimal_separator: str,
        *,
        default: float,
    ) -> float:
        if header is None:
            return default
        text = str(row.get(header) or "").strip()
        if not text:
            return default
        return cls._parse_number(
            text,
            header,
            row_number,
            decimal_separator,
        )

    @staticmethod
    def _parse_number(
        value: str,
        field_name: str,
        row_number: int,
        decimal_separator: str,
    ) -> float:
        text = value.strip().replace(" ", "")
        if decimal_separator == ",":
            text = text.replace(",", ".")
        try:
            number = float(text)
        except ValueError as exc:
            raise WorkspaceHistoryError(
                f"row {row_number}: {field_name} must be numeric"
            ) from exc
        if not math.isfinite(number):
            raise WorkspaceHistoryError(
                f"row {row_number}: {field_name} must be finite"
            )
        return number

    @classmethod
    def _quote_values(
        cls,
        *,
        row: dict[str, str | None],
        headers: dict[str, str],
        close_price: float,
        row_number: int,
        decimal_separator: str,
        default_spread: float,
    ) -> tuple[float, float, bool]:
        bid_header = headers.get("bid")
        ask_header = headers.get("ask")
        spread_header = headers.get("spread")
        has_bid = bool(bid_header and str(row.get(bid_header) or "").strip())
        has_ask = bool(ask_header and str(row.get(ask_header) or "").strip())
        if has_bid != has_ask:
            raise WorkspaceHistoryError(
                f"row {row_number}: bid and ask must be provided together"
            )
        if has_bid and has_ask:
            assert bid_header is not None
            assert ask_header is not None
            bid = cls._number(
                row,
                bid_header,
                "bid",
                row_number,
                decimal_separator,
            )
            ask = cls._number(
                row,
                ask_header,
                "ask",
                row_number,
                decimal_separator,
            )
            if spread_header is not None:
                spread_text = str(row.get(spread_header) or "").strip()
                if spread_text:
                    spread = cls._parse_number(
                        spread_text,
                        "spread",
                        row_number,
                        decimal_separator,
                    )
                    if not math.isclose(
                        ask - bid,
                        spread,
                        rel_tol=0.0,
                        abs_tol=1e-9,
                    ):
                        raise WorkspaceHistoryError(
                            f"row {row_number}: spread does not equal ask - bid"
                        )
            return bid, ask, False

        spread = default_spread
        if spread_header is not None:
            spread_text = str(row.get(spread_header) or "").strip()
            if spread_text:
                spread = cls._parse_number(
                    spread_text,
                    "spread",
                    row_number,
                    decimal_separator,
                )
                if spread < 0.0:
                    raise WorkspaceHistoryError(
                        f"row {row_number}: spread cannot be negative"
                    )
        half_spread = spread / 2.0
        return close_price - half_spread, close_price + half_spread, True

    @staticmethod
    def _optional_utc(value: datetime | str | None) -> datetime | None:
        if value is None or value == "":
            return None
        try:
            return normalize_market_timestamp(value)
        except ValueError as exc:
            raise WorkspaceHistoryError("Invalid history range timestamp") from exc

    @staticmethod
    def _non_negative_float(value: object, field_name: str) -> float:
        if isinstance(value, bool):
            raise WorkspaceHistoryError(f"{field_name} must be numeric")
        try:
            normalized = float(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise WorkspaceHistoryError(f"{field_name} must be numeric") from exc
        if not math.isfinite(normalized) or normalized < 0.0:
            raise WorkspaceHistoryError(f"{field_name} cannot be negative")
        return normalized
