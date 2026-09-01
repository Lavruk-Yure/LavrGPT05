# -*- coding: utf-8 -*-
"""core.workspace_replay_settings

Validated per-WSP configuration for synthetic and CSV Historical Replay.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.algorithm_workspace import AlgorithmWorkspace
from core.workspace_market_event import normalize_market_timestamp
from core.timeframes import get_timeframe
from core.workspace_replay import REPLAY_SPEEDS
from engine.risk.constants import (
    DEFAULT_REPLAY_RISK_EQUITY,
    MAXIMUM_REPLAY_RISK_EQUITY,
    MINIMUM_REPLAY_RISK_EQUITY,
    REPLAY_RISK_SETTING_EQUITY,
)
from engine.runtime_constants import (
    DEFAULT_WORKSPACE_HISTORY_DECIMAL_SEPARATOR,
    DEFAULT_WORKSPACE_HISTORY_DELIMITER,
    DEFAULT_WORKSPACE_HISTORY_SPREAD,
    DEFAULT_WORKSPACE_HISTORY_TIMEZONE,
    DEFAULT_WORKSPACE_REPLAY_SOURCE,
    WORKSPACE_HISTORY_DECIMAL_SEPARATORS,
    WORKSPACE_HISTORY_DELIMITERS,
    WORKSPACE_REPLAY_SOURCE_CSV,
    WORKSPACE_REPLAY_SOURCES,
    resolve_workspace_history_default_spread,
)


class WorkspaceReplaySettingsError(ValueError):
    """Invalid WSP Replay configuration."""


@dataclass(frozen=True, slots=True)
class WorkspaceReplaySettings:
    """Canonical persisted settings for one WSP Replay source and test."""

    source_type: str = DEFAULT_WORKSPACE_REPLAY_SOURCE
    file_path: str | None = None
    start_utc: str | None = None
    end_utc: str | None = None
    source_timezone: str = DEFAULT_WORKSPACE_HISTORY_TIMEZONE
    delimiter: str = DEFAULT_WORKSPACE_HISTORY_DELIMITER
    decimal_separator: str = DEFAULT_WORKSPACE_HISTORY_DECIMAL_SEPARATOR
    spread: float = DEFAULT_WORKSPACE_HISTORY_SPREAD
    source_name: str = ""
    source_timeframe: str | None = None
    initial_balance: float = DEFAULT_REPLAY_RISK_EQUITY
    speed: int = 1

    def __post_init__(self) -> None:
        source_type = str(self.source_type or "").strip().upper()
        if source_type not in WORKSPACE_REPLAY_SOURCES:
            raise WorkspaceReplaySettingsError(
                f"Unsupported Replay source_type: {source_type}"
            )
        object.__setattr__(self, "source_type", source_type)

        file_path = str(self.file_path or "").strip()
        if source_type == WORKSPACE_REPLAY_SOURCE_CSV and not file_path:
            raise WorkspaceReplaySettingsError(
                "Historical CSV Replay requires a file path"
            )
        object.__setattr__(self, "file_path", file_path or None)

        start_utc = self._optional_utc(self.start_utc, "start_utc")
        end_utc = self._optional_utc(self.end_utc, "end_utc")
        if start_utc is not None and end_utc is not None:
            if start_utc >= end_utc:
                raise WorkspaceReplaySettingsError(
                    "Replay start_utc must be earlier than end_utc"
                )
        object.__setattr__(
            self,
            "start_utc",
            start_utc.isoformat() if start_utc is not None else None,
        )
        object.__setattr__(
            self,
            "end_utc",
            end_utc.isoformat() if end_utc is not None else None,
        )

        source_timezone = self._timezone_name(
            self.source_timezone,
            "source timezone",
        )
        object.__setattr__(self, "source_timezone", source_timezone)

        delimiter = str(self.delimiter or "").strip().upper()
        if self.delimiter == "\t":
            delimiter = "\t"
        if delimiter not in WORKSPACE_HISTORY_DELIMITERS:
            raise WorkspaceReplaySettingsError(
                f"Unsupported CSV delimiter: {self.delimiter}"
            )
        object.__setattr__(self, "delimiter", delimiter)

        decimal_separator = str(self.decimal_separator or "").strip()
        if decimal_separator not in WORKSPACE_HISTORY_DECIMAL_SEPARATORS:
            raise WorkspaceReplaySettingsError(
                "CSV decimal_separator must be '.' or ','"
            )
        object.__setattr__(self, "decimal_separator", decimal_separator)

        spread = float(self.spread)
        if not math.isfinite(spread) or spread < 0.0:
            raise WorkspaceReplaySettingsError(
                "Replay spread must be finite and non-negative"
            )
        object.__setattr__(self, "spread", spread)

        source_name = str(self.source_name or "").strip()
        object.__setattr__(self, "source_name", source_name)

        source_timeframe = str(self.source_timeframe or "").strip().upper() or None
        if source_timeframe is not None:
            try:
                source_timeframe = get_timeframe(source_timeframe).name
            except KeyError as exc:
                raise WorkspaceReplaySettingsError(
                    f"Unknown source timeframe: {source_timeframe}"
                ) from exc
        object.__setattr__(self, "source_timeframe", source_timeframe)

        initial_balance = float(self.initial_balance)
        if not math.isfinite(initial_balance):
            raise WorkspaceReplaySettingsError("Replay initial balance must be finite")
        if not (
            MINIMUM_REPLAY_RISK_EQUITY <= initial_balance <= MAXIMUM_REPLAY_RISK_EQUITY
        ):
            raise WorkspaceReplaySettingsError(
                "Replay initial balance must be between "
                f"{MINIMUM_REPLAY_RISK_EQUITY:.2f} and "
                f"{MAXIMUM_REPLAY_RISK_EQUITY:.2f} USD"
            )
        object.__setattr__(self, "initial_balance", initial_balance)

        speed = int(self.speed)
        if speed not in REPLAY_SPEEDS:
            raise WorkspaceReplaySettingsError(f"Unsupported Replay speed: {speed}")
        object.__setattr__(self, "speed", speed)

    @classmethod
    def from_workspace(
        cls,
        workspace: AlgorithmWorkspace,
    ) -> WorkspaceReplaySettings:
        """Read canonical Replay-only values from one WSP."""
        data = dict(workspace.replay_settings)
        return cls(
            source_type=data.get(
                "source_type",
                DEFAULT_WORKSPACE_REPLAY_SOURCE,
            ),
            file_path=data.get("file_path"),
            start_utc=data.get("start_utc"),
            end_utc=data.get("end_utc"),
            source_timezone=data.get(
                "source_timezone",
                DEFAULT_WORKSPACE_HISTORY_TIMEZONE,
            ),
            delimiter=data.get(
                "delimiter",
                DEFAULT_WORKSPACE_HISTORY_DELIMITER,
            ),
            decimal_separator=data.get(
                "decimal_separator",
                DEFAULT_WORKSPACE_HISTORY_DECIMAL_SEPARATOR,
            ),
            spread=data.get(
                "spread",
                resolve_workspace_history_default_spread(workspace.symbol),
            ),
            source_name=data.get("source", ""),
            source_timeframe=data.get("source_timeframe"),
            initial_balance=data.get(
                REPLAY_RISK_SETTING_EQUITY,
                DEFAULT_REPLAY_RISK_EQUITY,
            ),
            speed=data.get("speed", 1),
        )

    def merge_settings(self, existing: dict[str, object]) -> dict[str, object]:
        """Update Replay keys and remove migrated download-period keys."""
        merged = dict(existing)
        for legacy_key in (
            "download_start_date",
            "download_end_date",
            "download_timezone",
        ):
            merged.pop(legacy_key, None)
        merged.update(
            {
                "source_type": self.source_type,
                "file_path": self.file_path,
                "start_utc": self.start_utc,
                "end_utc": self.end_utc,
                "source_timezone": self.source_timezone,
                "delimiter": self.delimiter,
                "decimal_separator": self.decimal_separator,
                "spread": self.spread,
                "source": self.source_name,
                "source_timeframe": self.source_timeframe,
                REPLAY_RISK_SETTING_EQUITY: self.initial_balance,
                "speed": self.speed,
            }
        )
        return merged

    def require_existing_csv(self) -> Path:
        """Return the selected CSV path or raise before saving/running."""
        if self.source_type != WORKSPACE_REPLAY_SOURCE_CSV:
            raise WorkspaceReplaySettingsError("Current Replay source is not CSV")
        path = Path(self.file_path or "").expanduser()
        if not path.is_file():
            raise WorkspaceReplaySettingsError(
                f"Historical CSV file does not exist: {path}"
            )
        return path.resolve()

    @staticmethod
    def _timezone_name(value: object, field_name: str) -> str:
        timezone_name = str(value or "").strip()
        if not timezone_name:
            timezone_name = DEFAULT_WORKSPACE_HISTORY_TIMEZONE
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise WorkspaceReplaySettingsError(
                f"Unknown {field_name}: {timezone_name}"
            ) from exc
        return timezone_name

    @staticmethod
    def _optional_utc(
        value: datetime | str | None,
        field_name: str,
    ) -> datetime | None:
        if value is None or value == "":
            return None
        try:
            normalized = normalize_market_timestamp(value)
        except ValueError as exc:
            raise WorkspaceReplaySettingsError(f"Invalid {field_name}") from exc
        return normalized.astimezone(UTC)
