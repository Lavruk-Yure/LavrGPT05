# -*- coding: utf-8 -*-
"""core.workspace_history_download_settings

Validated per-WSP settings for broker historical-data downloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.algorithm_workspace import AlgorithmWorkspace
from core.timeframes import get_timeframe
from engine.runtime_constants import DEFAULT_WORKSPACE_HISTORY_TIMEZONE


class WorkspaceHistoryDownloadSettingsError(ValueError):
    """Invalid WSP broker-history download configuration."""


@dataclass(frozen=True, slots=True)
class WorkspaceHistoryDownloadSettings:
    """Canonical persisted settings for one WSP history downloader."""

    broker: str
    account_id: str | None
    symbol: str
    timeframe: str
    start_date: str | None = None
    end_date: str | None = None
    timezone: str = DEFAULT_WORKSPACE_HISTORY_TIMEZONE
    destination_folder: str | None = None

    def __post_init__(self) -> None:
        broker = str(self.broker or "").strip().upper()
        if broker not in {"CTRADER", "IB"}:
            raise WorkspaceHistoryDownloadSettingsError(
                f"Unsupported history broker: {broker}"
            )
        object.__setattr__(self, "broker", broker)

        account_id = str(self.account_id or "").strip() or None
        object.__setattr__(self, "account_id", account_id)

        symbol = str(self.symbol or "").strip().upper()
        if not symbol:
            raise WorkspaceHistoryDownloadSettingsError(
                "History symbol is required"
            )
        object.__setattr__(self, "symbol", symbol)

        timeframe = str(self.timeframe or "").strip().upper()
        if not timeframe:
            raise WorkspaceHistoryDownloadSettingsError(
                "History timeframe is required"
            )
        try:
            get_timeframe(timeframe)
        except (KeyError, ValueError) as exc:
            raise WorkspaceHistoryDownloadSettingsError(
                f"Unsupported history timeframe: {timeframe}"
            ) from exc
        object.__setattr__(self, "timeframe", timeframe)

        start_date = self._optional_date(self.start_date, "start_date")
        end_date = self._optional_date(self.end_date, "end_date")
        if (start_date is None) != (end_date is None):
            raise WorkspaceHistoryDownloadSettingsError(
                "History download dates must be set together"
            )
        if (
            start_date is not None
            and end_date is not None
            and start_date > end_date
        ):
            raise WorkspaceHistoryDownloadSettingsError(
                "History download start date must not be later than end date"
            )
        object.__setattr__(
            self,
            "start_date",
            start_date.isoformat() if start_date is not None else None,
        )
        object.__setattr__(
            self,
            "end_date",
            end_date.isoformat() if end_date is not None else None,
        )

        timezone_name = str(self.timezone or "").strip()
        if not timezone_name:
            timezone_name = DEFAULT_WORKSPACE_HISTORY_TIMEZONE
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise WorkspaceHistoryDownloadSettingsError(
                f"Unknown history download timezone: {timezone_name}"
            ) from exc
        object.__setattr__(self, "timezone", timezone_name)

        destination = str(self.destination_folder or "").strip()
        if destination:
            destination = str(Path(destination).expanduser().resolve())
        object.__setattr__(self, "destination_folder", destination or None)

    @classmethod
    def from_workspace(
        cls,
        workspace: AlgorithmWorkspace,
    ) -> WorkspaceHistoryDownloadSettings:
        """Read settings, including legacy Replay download fields."""
        data = dict(workspace.history_download_settings)
        legacy = dict(workspace.replay_settings)
        return cls(
            broker=data.get("broker", workspace.broker),
            account_id=data.get("account_id", workspace.account_id),
            symbol=data.get("symbol", workspace.symbol),
            timeframe=data.get("timeframe", workspace.timeframe),
            start_date=data.get(
                "start_date",
                legacy.get("download_start_date"),
            ),
            end_date=data.get(
                "end_date",
                legacy.get("download_end_date"),
            ),
            timezone=data.get(
                "timezone",
                legacy.get(
                    "download_timezone",
                    DEFAULT_WORKSPACE_HISTORY_TIMEZONE,
                ),
            ),
            destination_folder=data.get("destination_folder"),
        )

    def merge_settings(self, existing: dict[str, object]) -> dict[str, object]:
        """Update owned settings while preserving future keys."""
        merged = dict(existing)
        merged.update(
            {
                "broker": self.broker,
                "account_id": self.account_id,
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "start_date": self.start_date,
                "end_date": self.end_date,
                "timezone": self.timezone,
                "destination_folder": self.destination_folder,
            }
        )
        return merged

    def period_utc(
        self,
        *,
        now_utc: datetime | None = None,
    ) -> tuple[datetime, datetime]:
        """Convert inclusive local dates into safe UTC broker boundaries."""
        if self.start_date is None or self.end_date is None:
            raise WorkspaceHistoryDownloadSettingsError(
                "History download dates are not configured"
            )
        start_date = date.fromisoformat(self.start_date)
        end_date = date.fromisoformat(self.end_date)
        timezone = ZoneInfo(self.timezone)
        start_local = datetime.combine(
            start_date,
            time.min,
            tzinfo=timezone,
        )
        end_local = datetime.combine(
            end_date,
            time(23, 59, 59),
            tzinfo=timezone,
        )
        current_utc = now_utc or datetime.now(UTC)
        if current_utc.tzinfo is None:
            raise WorkspaceHistoryDownloadSettingsError(
                "History current time must be timezone-aware"
            )
        current_utc = current_utc.astimezone(UTC).replace(microsecond=0)
        start_utc = start_local.astimezone(UTC)
        end_utc = min(end_local.astimezone(UTC), current_utc)
        if start_utc > end_utc:
            raise WorkspaceHistoryDownloadSettingsError(
                "History download start date is in the future"
            )
        return start_utc, end_utc

    @staticmethod
    def _optional_date(
        value: date | str | None,
        field_name: str,
    ) -> date | None:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            normalized = value.date()
        elif isinstance(value, date):
            normalized = value
        else:
            try:
                normalized = date.fromisoformat(str(value).strip())
            except ValueError as exc:
                raise WorkspaceHistoryDownloadSettingsError(
                    f"Invalid {field_name}"
                ) from exc
        return normalized
