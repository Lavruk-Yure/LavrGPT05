# -*- coding: utf-8 -*-
"""Broker-neutral profit drawdown decisions for WSP-owned positions."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime

from core.workspace_market_event import normalize_market_timestamp
from core.workspace_ownership import WorkspacePositionSnapshot

WORKSPACE_PROFIT_ACTION_HOLD = "HOLD"
WORKSPACE_PROFIT_ACTION_CLOSE = "CLOSE"
WORKSPACE_PROFIT_ACTIONS = (
    WORKSPACE_PROFIT_ACTION_HOLD,
    WORKSPACE_PROFIT_ACTION_CLOSE,
)


CANDIDATE_F_NEGATIVE_PD_RECOVERY_WINDOW_M1 = 3
CANDIDATE_F_NEGATIVE_PD_EARLY_ABORT_EVENT_INDEX = 2
CANDIDATE_F_NEGATIVE_PD_NUMERIC_EPSILON = 1e-9


@dataclass(slots=True)
class WorkspaceNegativePdRecoveryState:
    """Mutable causal state одного Candidate F negative-PD recovery."""

    position_id: str
    last_timestamp: datetime
    previous_profit: float
    completed_future_events: int = 0
    first_step_nonpositive: bool | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceProfitProtectionPolicy:
    """Validated per-WSP thresholds for floating-profit protection."""

    enabled: bool
    activation_mode: str
    max_drawdown_percent: float
    minimum_profit: float

    def __post_init__(self) -> None:
        activation_mode = str(self.activation_mode or "").strip().upper()
        max_drawdown = _finite_float(
            self.max_drawdown_percent,
            "max_drawdown_percent",
        )
        minimum_profit = _finite_float(self.minimum_profit, "minimum_profit")
        if not activation_mode:
            raise ValueError("activation_mode is required")
        if not 0.0 < max_drawdown < 100.0:
            raise ValueError("max_drawdown_percent must be between 0 and 100")
        if minimum_profit < 0.0:
            raise ValueError("minimum_profit cannot be negative")
        object.__setattr__(self, "enabled", bool(self.enabled))
        object.__setattr__(self, "activation_mode", activation_mode)
        object.__setattr__(self, "max_drawdown_percent", max_drawdown)
        object.__setattr__(self, "minimum_profit", minimum_profit)


@dataclass(frozen=True, slots=True)
class WorkspaceProfitProtectionDecision:
    """One current HOLD/CLOSE decision for an exact WSP-owned position."""

    timestamp: datetime
    workspace_uid: str
    broker: str
    account_id: str | None
    symbol: str
    position_id: str
    broker_position_id: str | None
    action: str
    reason: str
    current_profit: float
    peak_profit: float
    drawdown_percent: float
    drawdown_limit_percent: float
    minimum_profit: float
    ownership_verified: bool
    current_price_verified: bool
    spread_guard_passed: bool
    runtime_ready: bool
    execution_attempted: bool = False

    def __post_init__(self) -> None:
        action = str(self.action or "").strip().upper()
        if action not in WORKSPACE_PROFIT_ACTIONS:
            raise ValueError(f"Invalid profit protection action: {action}")
        workspace_uid = str(self.workspace_uid or "").strip()
        broker = str(self.broker or "").strip().upper()
        account_id = str(self.account_id or "").strip() or None
        symbol = str(self.symbol or "").strip().upper()
        position_id = str(self.position_id or "").strip()
        reason = str(self.reason or "").strip()
        if not workspace_uid:
            raise ValueError("workspace_uid is required")
        if not broker:
            raise ValueError("broker is required")
        if not symbol:
            raise ValueError("symbol is required")
        if not position_id:
            raise ValueError("position_id is required")
        if not reason:
            raise ValueError("reason is required")
        object.__setattr__(
            self,
            "timestamp",
            normalize_market_timestamp(self.timestamp),
        )
        object.__setattr__(self, "workspace_uid", workspace_uid)
        object.__setattr__(self, "broker", broker)
        object.__setattr__(self, "account_id", account_id)
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "position_id", position_id)
        object.__setattr__(
            self,
            "broker_position_id",
            str(self.broker_position_id or "").strip() or None,
        )
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(
            self,
            "current_profit",
            _finite_float(self.current_profit, "current_profit"),
        )
        object.__setattr__(
            self,
            "peak_profit",
            _finite_float(self.peak_profit, "peak_profit"),
        )
        object.__setattr__(
            self,
            "drawdown_percent",
            _finite_float(self.drawdown_percent, "drawdown_percent"),
        )
        object.__setattr__(
            self,
            "drawdown_limit_percent",
            _finite_float(
                self.drawdown_limit_percent,
                "drawdown_limit_percent",
            ),
        )
        object.__setattr__(
            self,
            "minimum_profit",
            _finite_float(self.minimum_profit, "minimum_profit"),
        )
        object.__setattr__(self, "ownership_verified", bool(self.ownership_verified))
        object.__setattr__(
            self,
            "current_price_verified",
            bool(self.current_price_verified),
        )
        object.__setattr__(
            self,
            "spread_guard_passed",
            bool(self.spread_guard_passed),
        )
        object.__setattr__(self, "runtime_ready", bool(self.runtime_ready))
        object.__setattr__(
            self,
            "execution_attempted",
            bool(self.execution_attempted),
        )

    @property
    def close_requested(self) -> bool:
        return self.action == WORKSPACE_PROFIT_ACTION_CLOSE


class WorkspaceProfitDrawdownGuard:
    """Evaluate owned positions without calling broker execution services."""

    def __init__(self, policy: WorkspaceProfitProtectionPolicy) -> None:
        self.policy = policy

    def evaluate(
        self,
        position: WorkspacePositionSnapshot,
        *,
        timestamp: datetime,
        runtime_ready: bool,
        spread_guard_passed: bool,
    ) -> WorkspaceProfitProtectionDecision:
        current_price_verified = bool(
            position.current_price is not None
            and math.isfinite(position.current_price)
            and position.current_price > 0.0
        )
        action = WORKSPACE_PROFIT_ACTION_HOLD
        reason = self._hold_reason(
            position,
            runtime_ready=runtime_ready,
            spread_guard_passed=spread_guard_passed,
            current_price_verified=current_price_verified,
        )
        if reason is None:
            action = WORKSPACE_PROFIT_ACTION_CLOSE
            reason = (
                f"profit drawdown {position.profit_drawdown:.2f}% exceeds "
                f"limit {self.policy.max_drawdown_percent:.2f}%"
            )
        return WorkspaceProfitProtectionDecision(
            timestamp=timestamp,
            workspace_uid=position.workspace_uid,
            broker=position.broker,
            account_id=position.account_id,
            symbol=position.symbol,
            position_id=position.position_id,
            broker_position_id=position.broker_position_id,
            action=action,
            reason=reason,
            current_profit=position.current_profit,
            peak_profit=position.peak_profit,
            drawdown_percent=position.profit_drawdown,
            drawdown_limit_percent=self.policy.max_drawdown_percent,
            minimum_profit=self.policy.minimum_profit,
            ownership_verified=True,
            current_price_verified=current_price_verified,
            spread_guard_passed=spread_guard_passed,
            runtime_ready=runtime_ready,
            execution_attempted=False,
        )

    def _hold_reason(
        self,
        position: WorkspacePositionSnapshot,
        *,
        runtime_ready: bool,
        spread_guard_passed: bool,
        current_price_verified: bool,
    ) -> str | None:
        if not self.policy.enabled:
            return "profit protection is disabled"
        if not runtime_ready:
            return "runtime is not ready"
        if self.policy.activation_mode == "AFTER_SPREAD" and not spread_guard_passed:
            return "spread guard is not passed"
        if not current_price_verified:
            return "current price is unavailable"
        if position.peak_profit < self.policy.minimum_profit:
            return "minimum profit is not reached"
        if position.peak_profit <= 0.0:
            return "position has no positive peak profit"
        if position.profit_drawdown <= self.policy.max_drawdown_percent:
            return "profit drawdown is within limit"
        return None


class WorkspaceCandidateFNegativePdRecoveryGuard(WorkspaceProfitDrawdownGuard):
    """Candidate F Replay recovery lifecycle поверх production PD guard.

    Negative PROFIT_DRAWDOWN не закривається негайно. Позиція отримує до
    трьох наступних completed M1 execution events для recovery до PnL >= 0.
    Після M2 дві послідовні непозитивні M1 зміни завершують recovery раніше.
    Positive-PD рішення лишається негайним. Клас не виконує broker operations.
    """

    def __init__(self, policy: WorkspaceProfitProtectionPolicy) -> None:
        super().__init__(policy)
        self.pending: dict[str, WorkspaceNegativePdRecoveryState] = {}
        self.started_position_ids: set[str] = set()
        self.recovery_close_ids: set[str] = set()
        self.early_abort_close_ids: set[str] = set()
        self.timeout_close_ids: set[str] = set()

    def synchronize_active_positions(self, position_ids: set[str]) -> None:
        """Прибрати recovery-state позицій, які вже закриті protective exit."""
        active_ids = {str(position_id) for position_id in position_ids}
        for position_id in tuple(self.pending):
            if position_id not in active_ids:
                self.pending.pop(position_id, None)

    def evaluate(
        self,
        position: WorkspacePositionSnapshot,
        *,
        timestamp: datetime,
        runtime_ready: bool,
        spread_guard_passed: bool,
    ) -> WorkspaceProfitProtectionDecision:
        """Застосувати fixed 3-M1 recovery та M2 two-step early-abort."""
        decision = super().evaluate(
            position,
            timestamp=timestamp,
            runtime_ready=runtime_ready,
            spread_guard_passed=spread_guard_passed,
        )
        pending = self.pending.get(position.position_id)

        if pending is not None and not _recovery_runtime_available(
            decision,
            self.policy,
        ):
            return decision

        if pending is None:
            if not decision.close_requested:
                return decision
            if (
                position.current_profit
                + CANDIDATE_F_NEGATIVE_PD_NUMERIC_EPSILON
                >= 0.0
            ):
                return decision
            self.pending[position.position_id] = WorkspaceNegativePdRecoveryState(
                position_id=position.position_id,
                last_timestamp=decision.timestamp,
                previous_profit=position.current_profit,
            )
            self.started_position_ids.add(position.position_id)
            return replace(
                decision,
                action=WORKSPACE_PROFIT_ACTION_HOLD,
                reason=(
                    "Candidate F negative profit drawdown entered "
                    "3-M1 recovery pending"
                ),
            )

        if decision.timestamp <= pending.last_timestamp:
            return replace(
                decision,
                action=WORKSPACE_PROFIT_ACTION_HOLD,
                reason=(
                    "Candidate F negative profit drawdown remains inside "
                    "recovery pending"
                ),
            )

        pending.completed_future_events += 1
        pending.last_timestamp = decision.timestamp
        step = position.current_profit - pending.previous_profit
        pending.previous_profit = position.current_profit

        if (
            position.current_profit
            + CANDIDATE_F_NEGATIVE_PD_NUMERIC_EPSILON
            >= 0.0
        ):
            self.pending.pop(position.position_id, None)
            self.recovery_close_ids.add(position.position_id)
            return replace(
                decision,
                action=WORKSPACE_PROFIT_ACTION_CLOSE,
                reason=(
                    "Candidate F negative profit drawdown recovered to "
                    "non-negative PnL"
                ),
            )

        if pending.completed_future_events == 1:
            pending.first_step_nonpositive = (
                step <= CANDIDATE_F_NEGATIVE_PD_NUMERIC_EPSILON
            )

        if (
            pending.completed_future_events
            == CANDIDATE_F_NEGATIVE_PD_EARLY_ABORT_EVENT_INDEX
        ):
            second_step_nonpositive = (
                step <= CANDIDATE_F_NEGATIVE_PD_NUMERIC_EPSILON
            )
            if pending.first_step_nonpositive and second_step_nonpositive:
                self.pending.pop(position.position_id, None)
                self.early_abort_close_ids.add(position.position_id)
                return replace(
                    decision,
                    action=WORKSPACE_PROFIT_ACTION_CLOSE,
                    reason=(
                        "Candidate F negative profit drawdown two-step "
                        "M1 deterioration abort"
                    ),
                )

        if (
            pending.completed_future_events
            >= CANDIDATE_F_NEGATIVE_PD_RECOVERY_WINDOW_M1
        ):
            self.pending.pop(position.position_id, None)
            self.timeout_close_ids.add(position.position_id)
            return replace(
                decision,
                action=WORKSPACE_PROFIT_ACTION_CLOSE,
                reason=(
                    "Candidate F negative profit drawdown recovery window "
                    "expired after 3 M1"
                ),
            )

        return replace(
            decision,
            action=WORKSPACE_PROFIT_ACTION_HOLD,
            reason=(
                "Candidate F negative profit drawdown remains inside "
                "3-M1 recovery pending"
            ),
        )


def _recovery_runtime_available(
    decision: WorkspaceProfitProtectionDecision,
    policy: WorkspaceProfitProtectionPolicy,
) -> bool:
    """Не обходити базові runtime/spread/current-price guard-и під час recovery."""
    if not policy.enabled or not decision.runtime_ready:
        return False
    if policy.activation_mode == "AFTER_SPREAD" and not decision.spread_guard_passed:
        return False
    return decision.current_price_verified


def _finite_float(value: object, field_name: str) -> float:
    try:
        normalized = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized
