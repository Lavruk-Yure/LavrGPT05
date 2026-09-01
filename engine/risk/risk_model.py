# -*- coding: utf-8 -*-
"""Broker-neutral WSP risk request, policy, decision, and evaluator."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from core.workspace_market_event import normalize_market_timestamp
from engine.risk.constants import (
    DEFAULT_WORKSPACE_MAX_DAILY_LOSS_PERCENT,
    DEFAULT_WORKSPACE_MAXIMUM_OPEN_POSITIONS,
    DEFAULT_WORKSPACE_MAXIMUM_POSITION_VOLUME,
    DEFAULT_WORKSPACE_REQUIRE_STOP_LOSS,
    DEFAULT_WORKSPACE_RISK_PERCENT,
    RISK_DECISION_ALLOW,
    RISK_DECISION_BLOCK,
    RISK_DECISIONS,
    RISK_REASON_ACCOUNT_BINDING_MISMATCH,
    RISK_REASON_ACCOUNT_SNAPSHOT_MISSING,
    RISK_REASON_APPROVED,
    RISK_REASON_DAILY_LOSS_LIMIT_REACHED,
    RISK_REASON_DAILY_PNL_SNAPSHOT_MISSING,
    RISK_REASON_INVALID_LOSS_AT_STOP,
    RISK_REASON_MARKET_INVALID,
    RISK_REASON_MAXIMUM_OPEN_POSITIONS_REACHED,
    RISK_REASON_MAXIMUM_POSITION_VOLUME_EXCEEDED,
    RISK_REASON_OPEN_POSITIONS_SNAPSHOT_MISSING,
    RISK_REASON_RISK_PERCENT_EXCEEDED,
    RISK_REASON_RUNTIME_NOT_READY,
    RISK_REASON_SPREAD_BLOCKED,
    RISK_REASON_STOP_LOSS_REQUIRED,
    WORKSPACE_RISK_SETTING_MAX_DAILY_LOSS_PERCENT,
    WORKSPACE_RISK_SETTING_MAXIMUM_OPEN_POSITIONS,
    WORKSPACE_RISK_SETTING_MAXIMUM_POSITION_VOLUME,
    WORKSPACE_RISK_SETTING_REQUIRE_STOP_LOSS,
    WORKSPACE_RISK_SETTING_RISK_PERCENT,
)


@dataclass(frozen=True, slots=True)
class WorkspaceRiskPolicy:
    """Validated risk limits applied before any broker execution."""

    max_risk_percent: float
    maximum_position_volume: float
    maximum_open_positions: int
    max_daily_loss_percent: float
    require_stop_loss: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_risk_percent",
            _bounded_percent(
                self.max_risk_percent,
                "max_risk_percent",
                maximum_inclusive=True,
            ),
        )
        object.__setattr__(
            self,
            "maximum_position_volume",
            _positive_float(
                self.maximum_position_volume,
                "maximum_position_volume",
            ),
        )
        object.__setattr__(
            self,
            "maximum_open_positions",
            _positive_int(
                self.maximum_open_positions,
                "maximum_open_positions",
            ),
        )
        object.__setattr__(
            self,
            "max_daily_loss_percent",
            _bounded_percent(
                self.max_daily_loss_percent,
                "max_daily_loss_percent",
                maximum_inclusive=False,
            ),
        )
        object.__setattr__(
            self,
            "require_stop_loss",
            _boolean(self.require_stop_loss, "require_stop_loss"),
        )

    @classmethod
    def from_risk_settings(
        cls,
        risk_settings: Mapping[str, object],
    ) -> WorkspaceRiskPolicy:
        """Build one policy from persisted settings of a single WSP."""
        if not isinstance(risk_settings, Mapping):
            raise ValueError("risk_settings must be a mapping")
        return cls(
            max_risk_percent=risk_settings.get(
                WORKSPACE_RISK_SETTING_RISK_PERCENT,
                DEFAULT_WORKSPACE_RISK_PERCENT,
            ),
            maximum_position_volume=risk_settings.get(
                WORKSPACE_RISK_SETTING_MAXIMUM_POSITION_VOLUME,
                DEFAULT_WORKSPACE_MAXIMUM_POSITION_VOLUME,
            ),
            maximum_open_positions=risk_settings.get(
                WORKSPACE_RISK_SETTING_MAXIMUM_OPEN_POSITIONS,
                DEFAULT_WORKSPACE_MAXIMUM_OPEN_POSITIONS,
            ),
            max_daily_loss_percent=risk_settings.get(
                WORKSPACE_RISK_SETTING_MAX_DAILY_LOSS_PERCENT,
                DEFAULT_WORKSPACE_MAX_DAILY_LOSS_PERCENT,
            ),
            require_stop_loss=risk_settings.get(
                WORKSPACE_RISK_SETTING_REQUIRE_STOP_LOSS,
                DEFAULT_WORKSPACE_REQUIRE_STOP_LOSS,
            ),
        )

    @classmethod
    def from_workspace(cls, workspace: object) -> WorkspaceRiskPolicy:
        """Read persisted risk_settings from an AlgorithmWorkspace-like object."""
        risk_settings = getattr(workspace, "risk_settings", None)
        if not isinstance(risk_settings, Mapping):
            raise ValueError("workspace.risk_settings must be a mapping")
        return cls.from_risk_settings(risk_settings)


@dataclass(frozen=True, slots=True)
class WorkspaceRiskRequest:
    """One normalized WSP trade intent presented to the risk layer."""

    timestamp: datetime
    workspace_uid: str
    broker: str
    account_id: str | None
    symbol: str
    side: str
    source_mode: str
    requested_volume: float
    equity: float | None
    estimated_loss_at_stop: float
    stop_loss: float | None
    open_positions_count: int | None
    daily_realized_pnl: float | None
    runtime_ready: bool
    binding_verified: bool
    market_valid: bool
    spread_guard_passed: bool
    signal_uid: str | None = None

    def __post_init__(self) -> None:
        workspace_uid = str(self.workspace_uid or "").strip()
        if not workspace_uid:
            raise ValueError("workspace_uid is required")
        object.__setattr__(
            self,
            "timestamp",
            normalize_market_timestamp(self.timestamp),
        )
        object.__setattr__(self, "workspace_uid", workspace_uid)
        object.__setattr__(self, "broker", _required_upper(self.broker, "broker"))
        object.__setattr__(
            self,
            "account_id",
            str(self.account_id or "").strip() or None,
        )
        object.__setattr__(self, "symbol", _required_upper(self.symbol, "symbol"))
        object.__setattr__(self, "side", _required_upper(self.side, "side"))
        object.__setattr__(
            self,
            "source_mode",
            _required_upper(self.source_mode, "source_mode"),
        )
        object.__setattr__(
            self,
            "requested_volume",
            _positive_float(self.requested_volume, "requested_volume"),
        )
        object.__setattr__(
            self,
            "equity",
            _optional_non_negative_float(self.equity, "equity"),
        )
        object.__setattr__(
            self,
            "estimated_loss_at_stop",
            _non_negative_float(
                self.estimated_loss_at_stop,
                "estimated_loss_at_stop",
            ),
        )
        object.__setattr__(
            self,
            "stop_loss",
            _optional_positive_float(self.stop_loss, "stop_loss"),
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
            "daily_realized_pnl",
            _optional_finite_float(
                self.daily_realized_pnl,
                "daily_realized_pnl",
            ),
        )
        object.__setattr__(self, "runtime_ready", bool(self.runtime_ready))
        object.__setattr__(self, "binding_verified", bool(self.binding_verified))
        object.__setattr__(self, "market_valid", bool(self.market_valid))
        object.__setattr__(
            self,
            "spread_guard_passed",
            bool(self.spread_guard_passed),
        )
        object.__setattr__(
            self,
            "signal_uid",
            str(self.signal_uid or "").strip() or None,
        )


@dataclass(frozen=True, slots=True)
class WorkspaceRiskDecision:
    """Immutable ALLOW/BLOCK result that never executes a broker order."""

    timestamp: datetime
    workspace_uid: str
    broker: str
    account_id: str | None
    symbol: str
    side: str
    decision: str
    reason_code: str
    reason_text: str
    requested_volume: float
    approved_volume: float | None
    equity: float
    estimated_loss_at_stop: float
    calculated_risk_percent: float
    daily_loss_percent: float
    execution_attempted: bool = False

    def __post_init__(self) -> None:
        decision = _required_upper(self.decision, "decision")
        if decision not in RISK_DECISIONS:
            raise ValueError(f"Invalid risk decision: {decision}")
        reason_code = _required_upper(self.reason_code, "reason_code")
        reason_text = str(self.reason_text or "").strip()
        if not reason_text:
            raise ValueError("reason_text is required")
        approved_volume = self.approved_volume
        if approved_volume is not None:
            approved_volume = _positive_float(
                approved_volume,
                "approved_volume",
            )
        if decision == RISK_DECISION_ALLOW and approved_volume is None:
            raise ValueError("ALLOW decision requires approved_volume")
        if decision == RISK_DECISION_BLOCK and approved_volume is not None:
            raise ValueError("BLOCK decision cannot approve volume")
        object.__setattr__(
            self,
            "timestamp",
            normalize_market_timestamp(self.timestamp),
        )
        object.__setattr__(
            self,
            "workspace_uid",
            str(self.workspace_uid or "").strip(),
        )
        if not self.workspace_uid:
            raise ValueError("workspace_uid is required")
        object.__setattr__(self, "broker", _required_upper(self.broker, "broker"))
        object.__setattr__(
            self,
            "account_id",
            str(self.account_id or "").strip() or None,
        )
        object.__setattr__(self, "symbol", _required_upper(self.symbol, "symbol"))
        object.__setattr__(self, "side", _required_upper(self.side, "side"))
        object.__setattr__(self, "decision", decision)
        object.__setattr__(self, "reason_code", reason_code)
        object.__setattr__(self, "reason_text", reason_text)
        object.__setattr__(
            self,
            "requested_volume",
            _positive_float(self.requested_volume, "requested_volume"),
        )
        object.__setattr__(self, "approved_volume", approved_volume)
        object.__setattr__(
            self,
            "equity",
            _non_negative_float(self.equity, "equity"),
        )
        object.__setattr__(
            self,
            "estimated_loss_at_stop",
            _non_negative_float(
                self.estimated_loss_at_stop,
                "estimated_loss_at_stop",
            ),
        )
        object.__setattr__(
            self,
            "calculated_risk_percent",
            _non_negative_float(
                self.calculated_risk_percent,
                "calculated_risk_percent",
            ),
        )
        object.__setattr__(
            self,
            "daily_loss_percent",
            _non_negative_float(
                self.daily_loss_percent,
                "daily_loss_percent",
            ),
        )
        object.__setattr__(
            self,
            "execution_attempted",
            bool(self.execution_attempted),
        )
        if self.execution_attempted:
            raise ValueError("Risk decision cannot attempt broker execution")

    @property
    def allowed(self) -> bool:
        return self.decision == RISK_DECISION_ALLOW

    @property
    def blocked(self) -> bool:
        return self.decision == RISK_DECISION_BLOCK


class WorkspaceRiskEvaluator:
    """Apply deterministic risk rules to one normalized trade intent."""

    def __init__(self, policy: WorkspaceRiskPolicy) -> None:
        self.policy = policy

    def evaluate(self, request: WorkspaceRiskRequest) -> WorkspaceRiskDecision:
        calculated_risk_percent = 0.0
        daily_loss_percent = 0.0
        if request.equity is not None and request.equity > 0.0:
            calculated_risk_percent = (
                request.estimated_loss_at_stop / request.equity * 100.0
            )
            if request.daily_realized_pnl is not None:
                daily_loss_percent = (
                    max(0.0, -request.daily_realized_pnl) / request.equity * 100.0
                )
        reason_code, reason_text = self._block_reason(
            request,
            calculated_risk_percent=calculated_risk_percent,
            daily_loss_percent=daily_loss_percent,
        )
        decision = RISK_DECISION_BLOCK
        approved_volume = None
        if reason_code is None:
            decision = RISK_DECISION_ALLOW
            reason_code = RISK_REASON_APPROVED
            reason_text = (
                f"risk {calculated_risk_percent:.4f}% is within "
                f"limit {self.policy.max_risk_percent:.4f}%"
            )
            approved_volume = request.requested_volume
        return WorkspaceRiskDecision(
            timestamp=request.timestamp,
            workspace_uid=request.workspace_uid,
            broker=request.broker,
            account_id=request.account_id,
            symbol=request.symbol,
            side=request.side,
            decision=decision,
            reason_code=reason_code,
            reason_text=reason_text,
            requested_volume=request.requested_volume,
            approved_volume=approved_volume,
            equity=request.equity or 0.0,
            estimated_loss_at_stop=request.estimated_loss_at_stop,
            calculated_risk_percent=calculated_risk_percent,
            daily_loss_percent=daily_loss_percent,
            execution_attempted=False,
        )

    def _block_reason(
        self,
        request: WorkspaceRiskRequest,
        *,
        calculated_risk_percent: float,
        daily_loss_percent: float,
    ) -> tuple[str | None, str]:
        if not request.runtime_ready:
            return RISK_REASON_RUNTIME_NOT_READY, "workspace runtime is not ready"
        if not request.binding_verified:
            return (
                RISK_REASON_ACCOUNT_BINDING_MISMATCH,
                "workspace account binding is not verified",
            )
        if request.equity is None or request.equity <= 0.0:
            return (
                RISK_REASON_ACCOUNT_SNAPSHOT_MISSING,
                "positive account equity snapshot is required",
            )
        if request.daily_realized_pnl is None:
            return (
                RISK_REASON_DAILY_PNL_SNAPSHOT_MISSING,
                "daily realized PnL snapshot is required",
            )
        if request.open_positions_count is None:
            return (
                RISK_REASON_OPEN_POSITIONS_SNAPSHOT_MISSING,
                "open positions snapshot is required",
            )
        if not request.market_valid:
            return RISK_REASON_MARKET_INVALID, "market state is invalid"
        if not request.spread_guard_passed:
            return RISK_REASON_SPREAD_BLOCKED, "spread guard is not passed"
        if self.policy.require_stop_loss and request.stop_loss is None:
            return RISK_REASON_STOP_LOSS_REQUIRED, "stop loss is required"
        if request.stop_loss is not None and request.estimated_loss_at_stop <= 0.0:
            return (
                RISK_REASON_INVALID_LOSS_AT_STOP,
                "estimated loss at stop must be positive",
            )
        if request.requested_volume > self.policy.maximum_position_volume:
            return (
                RISK_REASON_MAXIMUM_POSITION_VOLUME_EXCEEDED,
                f"requested volume {request.requested_volume:.6f} exceeds "
                f"limit {self.policy.maximum_position_volume:.6f}",
            )
        if request.open_positions_count >= self.policy.maximum_open_positions:
            return (
                RISK_REASON_MAXIMUM_OPEN_POSITIONS_REACHED,
                f"open positions {request.open_positions_count} reached "
                f"limit {self.policy.maximum_open_positions}",
            )
        if daily_loss_percent >= self.policy.max_daily_loss_percent:
            return (
                RISK_REASON_DAILY_LOSS_LIMIT_REACHED,
                f"daily loss {daily_loss_percent:.4f}% reached "
                f"limit {self.policy.max_daily_loss_percent:.4f}%",
            )
        if calculated_risk_percent > self.policy.max_risk_percent:
            return (
                RISK_REASON_RISK_PERCENT_EXCEEDED,
                f"risk {calculated_risk_percent:.4f}% exceeds "
                f"limit {self.policy.max_risk_percent:.4f}%",
            )
        return None, ""


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


def _positive_float(value: object, field_name: str) -> float:
    number = _finite_float(value, field_name)
    if number <= 0.0:
        raise ValueError(f"{field_name} must be positive")
    return number


def _non_negative_float(value: object, field_name: str) -> float:
    number = _finite_float(value, field_name)
    if number < 0.0:
        raise ValueError(f"{field_name} cannot be negative")
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


def _optional_positive_float(
    value: object,
    field_name: str,
) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return _positive_float(value, field_name)


def _boolean(value: object, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field_name} must be a boolean")


def _integer(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")

    text = str(value).strip()
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an integer") from exc


def _positive_int(value: object, field_name: str) -> int:
    number = _integer(value, field_name)
    if number <= 0:
        raise ValueError(f"{field_name} must be positive")
    return number


def _non_negative_int(value: object, field_name: str) -> int:
    number = _integer(value, field_name)
    if number < 0:
        raise ValueError(f"{field_name} cannot be negative")
    return number


def _optional_non_negative_int(
    value: object | None,
    field_name: str,
) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    return _non_negative_int(value, field_name)


def _bounded_percent(
    value: object,
    field_name: str,
    *,
    maximum_inclusive: bool,
) -> float:
    number = _positive_float(value, field_name)
    maximum_valid = number <= 100.0 if maximum_inclusive else number < 100.0
    if not maximum_valid:
        relation = "at most" if maximum_inclusive else "less than"
        raise ValueError(f"{field_name} must be {relation} 100")
    return number
