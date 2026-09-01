# -*- coding: utf-8 -*-
"""Broker-neutral моделі сигналів і незмінні WSP signal records.

Модуль зберігає структурований evidence для MACD, Alligator, spread і risk.
Alligator regime/phase входять у structured evidence; у SAME_TIMEFRAME phase
може визначати ALLOW/REJECT, але сам signal record не ініціює broker execution.
RoadMap102 додає causal t-2/t-1/t та terminal Candidate F lifecycle evidence;
ці поля read-only і не змінюють signal decision або execution.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from core.workspace_market_event import normalize_market_timestamp

WORKSPACE_SIGNAL_SPREAD_OK = "OK"
WORKSPACE_SIGNAL_SPREAD_BLOCKED = "BLOCKED"
WORKSPACE_SIGNAL_SPREAD_UNKNOWN = "UNKNOWN"
WORKSPACE_SIGNAL_SPREAD_STATUSES = (
    WORKSPACE_SIGNAL_SPREAD_OK,
    WORKSPACE_SIGNAL_SPREAD_BLOCKED,
    WORKSPACE_SIGNAL_SPREAD_UNKNOWN,
)

WORKSPACE_SIGNAL_FILTER_ALLOW = "ALLOW"
WORKSPACE_SIGNAL_FILTER_REJECT = "REJECT"
WORKSPACE_SIGNAL_FILTER_DECISIONS = (
    WORKSPACE_SIGNAL_FILTER_ALLOW,
    WORKSPACE_SIGNAL_FILTER_REJECT,
)


@dataclass(frozen=True, slots=True)
class WorkspaceTradeIntent:
    """Broker-neutral operation intent attached to one signal proposal."""

    requested_volume: float
    estimated_loss_at_stop: float
    stop_loss: float | None
    signal_uid: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "requested_volume",
            _positive_float(self.requested_volume, "requested_volume"),
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
            "signal_uid",
            str(self.signal_uid or "").strip() or None,
        )


@dataclass(frozen=True, slots=True)
class WorkspaceSignalFilterObservation:
    """Causal read-only observation Alligator для діагностики сигналу."""

    timestamp: datetime
    available_at: datetime
    state: str
    regime: str
    regime_phase: str
    normalized_slope: float | None = None
    normalized_opening: float | None = None

    def __post_init__(self) -> None:
        timestamp = normalize_market_timestamp(self.timestamp)
        available_at = normalize_market_timestamp(self.available_at)
        if available_at < timestamp:
            raise ValueError("filter observation cannot be available before its bar")
        object.__setattr__(self, "timestamp", timestamp)
        object.__setattr__(self, "available_at", available_at)
        object.__setattr__(self, "state", _required_upper(self.state, "state"))
        object.__setattr__(self, "regime", _required_upper(self.regime, "regime"))
        object.__setattr__(
            self,
            "regime_phase",
            _required_upper(self.regime_phase, "regime_phase"),
        )
        object.__setattr__(
            self,
            "normalized_slope",
            _optional_non_negative_float(
                self.normalized_slope,
                "normalized_slope",
            ),
        )
        object.__setattr__(
            self,
            "normalized_opening",
            _optional_non_negative_float(
                self.normalized_opening,
                "normalized_opening",
            ),
        )


@dataclass(frozen=True, slots=True)
class WorkspaceSignalFilterContext:
    """Structured filter snapshot attached to one signal proposal."""

    mode: str
    timeframe: str
    profile_uid: str
    profile_revision: int
    observation_timestamp: datetime | None = None
    available_at: datetime | None = None
    regime: str | None = None
    regime_phase: str | None = None
    normalized_slope: float | None = None
    normalized_opening: float | None = None
    active_age: int | None = None
    diagnostic_observations: tuple[WorkspaceSignalFilterObservation, ...] = ()

    def __post_init__(self) -> None:
        mode = _required_upper(self.mode, "mode")
        timeframe = _required_upper(self.timeframe, "timeframe")
        profile_uid = str(self.profile_uid or "").strip()
        try:
            profile_revision = int(self.profile_revision)
        except (TypeError, ValueError) as exc:
            raise ValueError("profile_revision must be a positive integer") from exc
        if not profile_uid:
            raise ValueError("profile_uid is required")
        if profile_revision <= 0:
            raise ValueError("profile_revision must be a positive integer")
        observation_timestamp = self.observation_timestamp
        available_at = self.available_at
        if (observation_timestamp is None) != (available_at is None):
            raise ValueError(
                "observation_timestamp and available_at must be set together"
            )
        if observation_timestamp is not None and available_at is not None:
            observation_timestamp = normalize_market_timestamp(observation_timestamp)
            available_at = normalize_market_timestamp(available_at)
            if available_at < observation_timestamp:
                raise ValueError(
                    "filter observation cannot be available before its bar"
                )
        regime = str(self.regime or "").strip().upper() or None
        regime_phase = str(self.regime_phase or "").strip().upper() or None
        normalized_slope = _optional_non_negative_float(
            self.normalized_slope,
            "normalized_slope",
        )
        normalized_opening = _optional_non_negative_float(
            self.normalized_opening,
            "normalized_opening",
        )
        active_age = _optional_non_negative_integer(
            self.active_age,
            "active_age",
        )
        diagnostic_observations = tuple(self.diagnostic_observations)
        if not all(
            isinstance(item, WorkspaceSignalFilterObservation)
            for item in diagnostic_observations
        ):
            raise ValueError("diagnostic_observations must contain filter observations")
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "timeframe", timeframe)
        object.__setattr__(self, "profile_uid", profile_uid)
        object.__setattr__(self, "profile_revision", profile_revision)
        object.__setattr__(
            self,
            "observation_timestamp",
            observation_timestamp,
        )
        object.__setattr__(self, "available_at", available_at)
        object.__setattr__(self, "regime", regime)
        object.__setattr__(self, "regime_phase", regime_phase)
        object.__setattr__(self, "normalized_slope", normalized_slope)
        object.__setattr__(self, "normalized_opening", normalized_opening)
        object.__setattr__(self, "active_age", active_age)
        object.__setattr__(
            self,
            "diagnostic_observations",
            diagnostic_observations,
        )


@dataclass(frozen=True, slots=True)
class WorkspaceSignalProposal:
    """One algorithm proposal before runtime guards accept or reject it."""

    signal_type: str
    direction: str
    strength: float
    macd_state: str
    alligator_confirmation: str
    reason: str = ""
    source_reason_code: str | None = None
    source_profile_uid: str | None = None
    source_profile_revision: int | None = None
    trade_intent: WorkspaceTradeIntent | None = None
    filter_decision: str = WORKSPACE_SIGNAL_FILTER_ALLOW
    filter_reason_code: str | None = None
    filter_context: WorkspaceSignalFilterContext | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "signal_type",
            _required_upper(self.signal_type, "signal_type"),
        )
        object.__setattr__(
            self,
            "direction",
            _required_upper(self.direction, "direction"),
        )
        object.__setattr__(
            self,
            "strength",
            _non_negative_float(self.strength, "strength"),
        )
        object.__setattr__(
            self,
            "macd_state",
            _required_upper(self.macd_state, "macd_state"),
        )
        object.__setattr__(
            self,
            "alligator_confirmation",
            _required_upper(
                self.alligator_confirmation,
                "alligator_confirmation",
            ),
        )
        object.__setattr__(self, "reason", str(self.reason or "").strip())
        source_reason_code = str(self.source_reason_code or "").strip().upper() or None
        source_profile_uid = str(self.source_profile_uid or "").strip() or None
        source_profile_revision = self.source_profile_revision
        if source_profile_revision is not None:
            try:
                source_profile_revision = int(source_profile_revision)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "source_profile_revision must be a positive integer"
                ) from exc
            if source_profile_revision <= 0:
                raise ValueError("source_profile_revision must be a positive integer")
        if (source_profile_uid is None) != (source_profile_revision is None):
            raise ValueError("source profile uid and revision must be set together")
        object.__setattr__(self, "source_reason_code", source_reason_code)
        object.__setattr__(self, "source_profile_uid", source_profile_uid)
        object.__setattr__(
            self,
            "source_profile_revision",
            source_profile_revision,
        )
        filter_decision = _required_upper(
            self.filter_decision,
            "filter_decision",
        )
        if filter_decision not in WORKSPACE_SIGNAL_FILTER_DECISIONS:
            raise ValueError("Invalid filter_decision")
        filter_reason_code = str(self.filter_reason_code or "").strip().upper() or None
        if (
            filter_decision == WORKSPACE_SIGNAL_FILTER_REJECT
            and filter_reason_code is None
        ):
            raise ValueError("filter_reason_code is required for rejected proposals")
        object.__setattr__(self, "filter_decision", filter_decision)
        object.__setattr__(
            self,
            "filter_reason_code",
            filter_reason_code,
        )
        if self.trade_intent is not None and not isinstance(
            self.trade_intent,
            WorkspaceTradeIntent,
        ):
            raise ValueError("trade_intent must be WorkspaceTradeIntent")
        if self.filter_context is not None and not isinstance(
            self.filter_context,
            WorkspaceSignalFilterContext,
        ):
            raise ValueError("filter_context must be WorkspaceSignalFilterContext")


@dataclass(frozen=True, slots=True)
class WorkspaceSignalRecord:
    """One immutable accepted or rejected signal owned by one WSP."""

    timestamp: datetime
    signal_uid: str
    workspace_uid: str
    broker: str
    account_id: str | None
    symbol: str
    timeframe: str
    source_mode: str
    signal_type: str
    direction: str
    strength: float
    macd_state: str
    alligator_confirmation: str
    spread_status: str
    accepted: bool
    reason: str
    source_reason_code: str | None = None
    source_profile_uid: str | None = None
    source_profile_revision: int | None = None
    risk_decision: str | None = None
    risk_reason_code: str | None = None
    requested_volume: float | None = None
    approved_volume: float | None = None
    risk_execution_attempted: bool = False
    filter_decision: str = WORKSPACE_SIGNAL_FILTER_ALLOW
    filter_reason_code: str | None = None
    filter_context: WorkspaceSignalFilterContext | None = None
    candidate_f_lifecycle_action: str | None = None
    candidate_f_lifecycle_reason: str | None = None
    candidate_f_lifecycle_timestamp: datetime | None = None
    candidate_f_lifecycle_delay_bars: int | None = None
    candidate_f_lifecycle_context: WorkspaceSignalFilterContext | None = None

    def __post_init__(self) -> None:
        timestamp = normalize_market_timestamp(self.timestamp)
        signal_uid = str(self.signal_uid or "").strip()
        workspace_uid = str(self.workspace_uid or "").strip()
        broker = _required_upper(self.broker, "broker")
        account_id = str(self.account_id or "").strip() or None
        symbol = _required_upper(self.symbol, "symbol")
        timeframe = _required_upper(self.timeframe, "timeframe")
        source_mode = _required_upper(self.source_mode, "source_mode")
        spread_status = _required_upper(self.spread_status, "spread_status")
        if not signal_uid:
            raise ValueError("signal_uid is required")
        if not workspace_uid:
            raise ValueError("workspace_uid is required")
        if spread_status not in WORKSPACE_SIGNAL_SPREAD_STATUSES:
            raise ValueError("Invalid spread_status")

        object.__setattr__(self, "timestamp", timestamp)
        object.__setattr__(self, "signal_uid", signal_uid)
        object.__setattr__(self, "workspace_uid", workspace_uid)
        object.__setattr__(self, "broker", broker)
        object.__setattr__(self, "account_id", account_id)
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "timeframe", timeframe)
        object.__setattr__(self, "source_mode", source_mode)
        object.__setattr__(
            self,
            "signal_type",
            _required_upper(self.signal_type, "signal_type"),
        )
        object.__setattr__(
            self,
            "direction",
            _required_upper(self.direction, "direction"),
        )
        object.__setattr__(
            self,
            "strength",
            _non_negative_float(self.strength, "strength"),
        )
        object.__setattr__(
            self,
            "macd_state",
            _required_upper(self.macd_state, "macd_state"),
        )
        object.__setattr__(
            self,
            "alligator_confirmation",
            _required_upper(
                self.alligator_confirmation,
                "alligator_confirmation",
            ),
        )
        object.__setattr__(self, "spread_status", spread_status)
        object.__setattr__(self, "accepted", bool(self.accepted))
        object.__setattr__(
            self,
            "reason",
            str(self.reason or "").strip() or "—",
        )
        source_reason_code = str(self.source_reason_code or "").strip().upper() or None
        source_profile_uid = str(self.source_profile_uid or "").strip() or None
        source_profile_revision = self.source_profile_revision
        if source_profile_revision is not None:
            try:
                source_profile_revision = int(source_profile_revision)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "source_profile_revision must be a positive integer"
                ) from exc
            if source_profile_revision <= 0:
                raise ValueError("source_profile_revision must be a positive integer")
        if (source_profile_uid is None) != (source_profile_revision is None):
            raise ValueError("source profile uid and revision must be set together")
        object.__setattr__(self, "source_reason_code", source_reason_code)
        object.__setattr__(self, "source_profile_uid", source_profile_uid)
        object.__setattr__(
            self,
            "source_profile_revision",
            source_profile_revision,
        )
        risk_decision = str(self.risk_decision or "").strip().upper() or None
        risk_reason_code = str(self.risk_reason_code or "").strip().upper() or None
        requested_volume = _optional_positive_float(
            self.requested_volume,
            "requested_volume",
        )
        approved_volume = _optional_positive_float(
            self.approved_volume,
            "approved_volume",
        )
        filter_decision = _required_upper(
            self.filter_decision,
            "filter_decision",
        )
        if filter_decision not in WORKSPACE_SIGNAL_FILTER_DECISIONS:
            raise ValueError("Invalid filter_decision")
        filter_reason_code = str(self.filter_reason_code or "").strip().upper() or None
        if (
            filter_decision == WORKSPACE_SIGNAL_FILTER_REJECT
            and filter_reason_code is None
        ):
            raise ValueError("filter_reason_code is required for rejected records")
        risk_execution_attempted = bool(self.risk_execution_attempted)
        if risk_execution_attempted:
            raise ValueError("Signal risk evaluation cannot attempt broker execution")
        object.__setattr__(self, "risk_decision", risk_decision)
        object.__setattr__(self, "risk_reason_code", risk_reason_code)
        object.__setattr__(self, "requested_volume", requested_volume)
        object.__setattr__(self, "approved_volume", approved_volume)
        object.__setattr__(self, "filter_decision", filter_decision)
        object.__setattr__(
            self,
            "filter_reason_code",
            filter_reason_code,
        )
        object.__setattr__(
            self,
            "risk_execution_attempted",
            risk_execution_attempted,
        )
        if self.filter_context is not None and not isinstance(
            self.filter_context,
            WorkspaceSignalFilterContext,
        ):
            raise ValueError("filter_context must be WorkspaceSignalFilterContext")
        lifecycle_action = (
            str(self.candidate_f_lifecycle_action or "").strip().upper() or None
        )
        lifecycle_reason = (
            str(self.candidate_f_lifecycle_reason or "").strip().upper() or None
        )
        lifecycle_timestamp = self.candidate_f_lifecycle_timestamp
        if lifecycle_timestamp is not None:
            lifecycle_timestamp = normalize_market_timestamp(lifecycle_timestamp)
        lifecycle_delay_bars = _optional_non_negative_integer(
            self.candidate_f_lifecycle_delay_bars,
            "candidate_f_lifecycle_delay_bars",
        )
        lifecycle_context = self.candidate_f_lifecycle_context
        if lifecycle_context is not None and not isinstance(
            lifecycle_context,
            WorkspaceSignalFilterContext,
        ):
            raise ValueError(
                "candidate_f_lifecycle_context must be WorkspaceSignalFilterContext"
            )
        if lifecycle_action is None:
            if any(
                value is not None
                for value in (
                    lifecycle_reason,
                    lifecycle_timestamp,
                    lifecycle_delay_bars,
                    lifecycle_context,
                )
            ):
                raise ValueError(
                    "Candidate F lifecycle details require lifecycle action"
                )
        elif lifecycle_timestamp is None:
            raise ValueError(
                "Candidate F lifecycle action requires lifecycle timestamp"
            )
        object.__setattr__(
            self,
            "candidate_f_lifecycle_action",
            lifecycle_action,
        )
        object.__setattr__(
            self,
            "candidate_f_lifecycle_reason",
            lifecycle_reason,
        )
        object.__setattr__(
            self,
            "candidate_f_lifecycle_timestamp",
            lifecycle_timestamp,
        )
        object.__setattr__(
            self,
            "candidate_f_lifecycle_delay_bars",
            lifecycle_delay_bars,
        )
        object.__setattr__(
            self,
            "candidate_f_lifecycle_context",
            lifecycle_context,
        )

    @property
    def decision(self) -> str:
        return "ACCEPTED" if self.accepted else "REJECTED"


def _required_upper(value: object, field_name: str) -> str:
    text = str(value or "").strip().upper()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _non_negative_float(value: object, field_name: str) -> float:
    value_text = str(value).strip()
    try:
        number = float(value_text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a non-negative finite number") from exc
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{field_name} must be a non-negative finite number")
    return number


def _positive_float(value: object, field_name: str) -> float:
    number = _finite_float(value, field_name)
    if number <= 0.0:
        raise ValueError(f"{field_name} must be a positive finite number")
    return number


def _optional_non_negative_float(
    value: object,
    field_name: str,
) -> float | None:
    if value is None:
        return None
    number = _non_negative_float(value, field_name)
    return number


def _optional_non_negative_integer(
    value: object | None,
    field_name: str,
) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    value_text = str(value).strip()
    try:
        numeric_value = float(value_text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a non-negative integer") from exc
    if (
        not math.isfinite(numeric_value)
        or numeric_value < 0.0
        or not numeric_value.is_integer()
    ):
        raise ValueError(f"{field_name} must be a non-negative integer")
    return int(numeric_value)


def _optional_positive_float(
    value: object | None,
    field_name: str,
) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return _positive_float(value, field_name)


def _finite_float(value: object, field_name: str) -> float:
    value_text = str(value).strip()
    try:
        number = float(value_text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be a finite number")
    return number
