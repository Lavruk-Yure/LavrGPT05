# -*- coding: utf-8 -*-
"""core.workspace_history_export

Canonical atomic CSV writer for broker historical bars used by WSP Replay.
"""

from __future__ import annotations

import csv
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Protocol

from core.app_paths import get_base_dir
from engine.ctrader_history import CTraderHistoryDownloadResult
from engine.ib_history import IBHistoryDownloadResult


class WorkspaceHistoryExportError(RuntimeError):
    """Historical data could not be exported safely."""


class _HistoricalBarProtocol(Protocol):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class WorkspaceHistoryCsvExportResult:
    """Canonical CSV export metadata."""

    file_path: Path
    broker: str
    symbol: str
    timeframe: str
    bar_count: int
    first_timestamp: datetime
    last_timestamp: datetime
    request_count: int

    @property
    def source_name(self) -> str:
        return f"{self.broker}_{self.symbol}_{self.timeframe}_HISTORY"


class WorkspaceHistoryCsvWriter:
    """Write one normalized OHLC CSV without partial-file exposure."""

    HEADER = ("timestamp", "open", "high", "low", "close", "volume")

    def __init__(self, history_root: str | Path | None = None) -> None:
        self.history_root = Path(
            history_root or get_base_dir() / "data" / "history"
        ).resolve()

    def write_ctrader(
        self,
        result: CTraderHistoryDownloadResult,
    ) -> WorkspaceHistoryCsvExportResult:
        return self._write_result(
            broker="CTRADER",
            symbol=result.symbol,
            timeframe=result.timeframe,
            bars=result.bars,
            request_count=result.request_count,
        )

    def write_ib(
        self,
        result: IBHistoryDownloadResult,
    ) -> WorkspaceHistoryCsvExportResult:
        return self._write_result(
            broker="IB",
            symbol=result.symbol,
            timeframe=result.timeframe,
            bars=result.bars,
            request_count=result.request_count,
        )

    def planned_file_path(
        self,
        *,
        broker: str,
        symbol: str,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> Path:
        """Create the broker folder and return a UTC-period CSV path."""
        if start_utc.tzinfo is None or end_utc.tzinfo is None:
            raise WorkspaceHistoryExportError(
                "Historical CSV period must be timezone-aware"
            )
        first_timestamp = start_utc.astimezone(UTC)
        last_timestamp = end_utc.astimezone(UTC)
        if last_timestamp <= first_timestamp:
            raise WorkspaceHistoryExportError(
                "Historical CSV end must be later than start"
            )
        return self.planned_file_path_for_dates(
            broker=broker,
            symbol=symbol,
            timeframe=timeframe,
            start_date=first_timestamp.date(),
            end_date=last_timestamp.date(),
        )

    def planned_file_path_for_dates(
        self,
        *,
        broker: str,
        symbol: str,
        timeframe: str,
        start_date: date,
        end_date: date,
    ) -> Path:
        """Return a planned path named by the dates shown in the UI."""
        if end_date < start_date:
            raise WorkspaceHistoryExportError(
                "Historical CSV end date must not be earlier than start date"
            )
        normalized_broker = str(broker or "").strip().upper()
        normalized_symbol = str(symbol or "").strip().upper()
        normalized_timeframe = str(timeframe or "").strip().upper()
        directory = (
            self.history_root
            / normalized_broker
            / normalized_symbol
            / normalized_timeframe
        )
        directory.mkdir(parents=True, exist_ok=True)
        filename = (
            f"{start_date:%Y-%m-%d}_{end_date:%Y-%m-%d}_"
            f"{normalized_broker}_{normalized_symbol}_"
            f"{normalized_timeframe}.csv"
        )
        return (directory / filename).resolve()

    @staticmethod
    def planned_source_name(
        *,
        broker: str,
        symbol: str,
        timeframe: str,
    ) -> str:
        """Return the canonical source label before broker download."""
        return (
            f"{str(broker or '').strip().upper()}_"
            f"{str(symbol or '').strip().upper()}_"
            f"{str(timeframe or '').strip().upper()}_HISTORY"
        )

    def _write_result(
        self,
        *,
        broker: str,
        symbol: str,
        timeframe: str,
        bars: Sequence[_HistoricalBarProtocol],
        request_count: int,
    ) -> WorkspaceHistoryCsvExportResult:
        if not bars:
            raise WorkspaceHistoryExportError(
                f"{broker} history response contains no bars"
            )

        normalized_broker = str(broker or "").strip().upper()
        normalized_symbol = str(symbol or "").strip().upper()
        normalized_timeframe = str(timeframe or "").strip().upper()
        first_timestamp = bars[0].timestamp.astimezone(UTC)
        last_timestamp = bars[-1].timestamp.astimezone(UTC)
        target = self.planned_file_path(
            broker=normalized_broker,
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            start_utc=first_timestamp,
            end_utc=last_timestamp,
        )
        directory = target.parent
        temporary_path: Path | None = None

        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                prefix=f".{target.stem}_",
                suffix=".tmp",
                dir=directory,
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                writer = csv.writer(handle, lineterminator="\n")
                writer.writerow(self.HEADER)
                for bar in bars:
                    timestamp = bar.timestamp.astimezone(UTC)
                    writer.writerow(
                        (
                            timestamp.isoformat().replace("+00:00", "Z"),
                            self._format_price(bar.open),
                            self._format_price(bar.high),
                            self._format_price(bar.low),
                            self._format_price(bar.close),
                            self._format_volume(bar.volume),
                        )
                    )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, target)
        except OSError as exc:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise WorkspaceHistoryExportError(
                f"Cannot write historical CSV: {exc}"
            ) from exc

        return WorkspaceHistoryCsvExportResult(
            file_path=target.resolve(),
            broker=normalized_broker,
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            bar_count=len(bars),
            first_timestamp=first_timestamp,
            last_timestamp=last_timestamp,
            request_count=int(request_count),
        )

    @staticmethod
    def _format_price(value: float) -> str:
        return f"{float(value):.8f}".rstrip("0").rstrip(".")

    @staticmethod
    def _format_volume(value: float) -> str:
        number = float(value)
        if number.is_integer():
            return str(int(number))
        return f"{number:.8f}".rstrip("0").rstrip(".")
