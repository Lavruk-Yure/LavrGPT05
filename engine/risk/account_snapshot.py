# -*- coding: utf-8 -*-
"""Broker-neutral account facts used by WSP risk evaluation."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from core.workspace_market_event import normalize_market_timestamp
from engine.risk.constants import (
    DEFAULT_REPLAY_RISK_DAILY_REALIZED_PNL,
    DEFAULT_REPLAY_RISK_EQUITY,
    DEFAULT_REPLAY_RISK_OPEN_POSITIONS_COUNT,
    REPLAY_RISK_SETTING_DAILY_REALIZED_PNL,
    REPLAY_RISK_SETTING_EQUITY,
    REPLAY_RISK_SETTING_OPEN_POSITIONS_COUNT,
)


@dataclass(frozen=True, slots=True)
class WorkspaceRiskAccountSnapshot:
    """Immutable account state consumed without broker execution."""

    snapshot_utc: datetime
    workspace_uid: str
    broker: str
    account_id: str | None
    source_mode: str
    equity: float | None
    daily_realized_pnl: float | None
    open_positions_count: int | None
    binding_verified: bool = True
    synthetic: bool = False

    def __post_init__(self) -> None:
        workspace_uid = str(self.workspace_uid or "").strip()
        if not workspace_uid:
            raise ValueError("workspace_uid is required")
        object.__setattr__(
            self,
            "snapshot_utc",
            normalize_market_timestamp(self.snapshot_utc),
        )
        object.__setattr__(self, "workspace_uid", workspace_uid)
        object.__setattr__(self, "broker", _required_upper(self.broker, "broker"))
        object.__setattr__(
            self,
            "account_id",
            str(self.account_id or "").strip() or None,
        )
        object.__setattr__(
            self,
            "source_mode",
            _required_upper(self.source_mode, "source_mode"),
        )
        object.__setattr__(
            self,
            "equity",
            _optional_non_negative_float(self.equity, "equity"),
        )
        object.__setattr__(
            self,
            "daily_realized_pnl",
            _optional_finite_float(
                self.daily_realized_pnl,
                "daily_realized_pnl",
            ),
        )
        object.__setattr__(
            self,
            "open_positions_count",
            _optional_non_negative_int(
                self.open_positions_count,
                "open_positions_count",
            ),
        )
        object.__setattr__(
            self,
            "binding_verified",
            _boolean(self.binding_verified, "binding_verified"),
        )
        object.__setattr__(
            self,
            "synthetic",
            _boolean(self.synthetic, "synthetic"),
        )

    @property
    def equity_available(self) -> bool:
        return self.equity is not None

    @property
    def daily_pnl_available(self) -> bool:
        return self.daily_realized_pnl is not None

    @property
    def open_positions_available(self) -> bool:
        return self.open_positions_count is not None

    def matches_binding(
        self,
        *,
        workspace_uid: str,
        broker: str,
        account_id: str | None,
        source_mode: str,
    ) -> bool:
        """Return whether the snapshot belongs to the exact WSP binding."""
        return bool(
            self.binding_verified
            and self.workspace_uid == str(workspace_uid or "").strip()
            and self.broker == str(broker or "").strip().upper()
            and self.account_id == (str(account_id or "").strip() or None)
            and self.source_mode == str(source_mode or "").strip().upper()
        )

    @classmethod
    def from_replay_settings(
        cls,
        *,
        snapshot_utc: datetime,
        workspace_uid: str,
        broker: str,
        account_id: str | None,
        source_mode: str,
        replay_settings: Mapping[str, object],
    ) -> WorkspaceRiskAccountSnapshot:
        """Build one deterministic synthetic snapshot for Replay."""
        settings = dict(replay_settings)
        equity = _optional_non_negative_float(
            settings.get(
                REPLAY_RISK_SETTING_EQUITY,
                DEFAULT_REPLAY_RISK_EQUITY,
            ),
            "equity",
        )
        daily_realized_pnl = _optional_finite_float(
            settings.get(
                REPLAY_RISK_SETTING_DAILY_REALIZED_PNL,
                DEFAULT_REPLAY_RISK_DAILY_REALIZED_PNL,
            ),
            "daily_realized_pnl",
        )
        open_positions_count = _optional_non_negative_int(
            settings.get(
                REPLAY_RISK_SETTING_OPEN_POSITIONS_COUNT,
                DEFAULT_REPLAY_RISK_OPEN_POSITIONS_COUNT,
            ),
            "open_positions_count",
        )
        return cls(
            snapshot_utc=snapshot_utc,
            workspace_uid=workspace_uid,
            broker=broker,
            account_id=account_id,
            source_mode=source_mode,
            equity=equity,
            daily_realized_pnl=daily_realized_pnl,
            open_positions_count=open_positions_count,
            binding_verified=True,
            synthetic=True,
        )


def _required_upper(value: object, field_name: str) -> str:
    text = str(value or "").strip().upper()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _finite_float(value: object, field_name: str) -> float:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


def _optional_finite_float(
    value: object | None,
    field_name: str,
) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return _finite_float(value, field_name)


def _optional_non_negative_float(
    value: object | None,
    field_name: str,
) -> float | None:
    number = _optional_finite_float(value, field_name)
    if number is not None and number < 0.0:
        raise ValueError(f"{field_name} cannot be negative")
    return number


def _integer(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        return int(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an integer") from exc


def _optional_non_negative_int(
    value: object | None,
    field_name: str,
) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    number = _integer(value, field_name)
    if number < 0:
        raise ValueError(f"{field_name} cannot be negative")
    return number


def _boolean(value: object, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field_name} must be a boolean")
