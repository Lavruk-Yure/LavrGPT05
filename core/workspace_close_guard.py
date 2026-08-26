# -*- coding: utf-8 -*-
"""Deterministic close-safety evaluation for one Algorithm Workspace."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.algorithm_workspace import (
    WORKSPACE_STATE_RESTORED,
    WORKSPACE_STATE_STOPPED,
)

WORKSPACE_CLOSE_BLOCK_RUNTIME_ACTIVE = "RUNTIME_ACTIVE"
WORKSPACE_CLOSE_BLOCK_ACTIVE_ORDERS = "ACTIVE_ORDERS"
WORKSPACE_CLOSE_BLOCK_OPEN_POSITIONS = "OPEN_POSITIONS"
WORKSPACE_CLOSE_BLOCK_BROKER_OPERATION = "BROKER_OPERATION"
WORKSPACE_CLOSE_BLOCK_MARKET_EVENT = "MARKET_EVENT_PROCESSING"
WORKSPACE_CLOSE_BLOCK_REPLAY_STEP = "REPLAY_STEP_ACTIVE"
WORKSPACE_CLOSE_BLOCK_PENDING_CLOSE = "PENDING_CLOSE_DECISION"

WORKSPACE_CLOSE_BLOCK_CODES = (
    WORKSPACE_CLOSE_BLOCK_RUNTIME_ACTIVE,
    WORKSPACE_CLOSE_BLOCK_ACTIVE_ORDERS,
    WORKSPACE_CLOSE_BLOCK_OPEN_POSITIONS,
    WORKSPACE_CLOSE_BLOCK_BROKER_OPERATION,
    WORKSPACE_CLOSE_BLOCK_MARKET_EVENT,
    WORKSPACE_CLOSE_BLOCK_REPLAY_STEP,
    WORKSPACE_CLOSE_BLOCK_PENDING_CLOSE,
)


@dataclass(frozen=True, slots=True)
class WorkspaceCloseBlocker:
    """One exact reason that prevents a WSP from being deleted."""

    code: str
    reason: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        code = str(self.code or "").strip().upper()
        reason = str(self.reason or "").strip()
        if code not in WORKSPACE_CLOSE_BLOCK_CODES:
            raise ValueError(f"Invalid WSP close blocker code: {code}")
        if not reason:
            raise ValueError("WSP close blocker reason is required")
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "details", dict(self.details))


@dataclass(frozen=True, slots=True)
class WorkspaceCloseGuardResult:
    """Immutable close decision with every currently active blocker."""

    blockers: tuple[WorkspaceCloseBlocker, ...]

    @property
    def allowed(self) -> bool:
        return not self.blockers

    @property
    def primary_blocker(self) -> WorkspaceCloseBlocker | None:
        return self.blockers[0] if self.blockers else None

    @property
    def primary_reason(self) -> str | None:
        blocker = self.primary_blocker
        return blocker.reason if blocker is not None else None

    def has_blocker(self, code: str) -> bool:
        normalized = str(code or "").strip().upper()
        return any(blocker.code == normalized for blocker in self.blockers)


class WorkspaceCloseGuard:
    """Evaluate all close blockers in a stable, documented priority order."""

    @staticmethod
    def evaluate(
        *,
        runtime_state: str,
        active_orders_count: int,
        open_positions_count: int,
        broker_operation_active: bool,
        market_event_processing: bool,
        replay_step_active: bool,
        pending_close_decisions_count: int,
    ) -> WorkspaceCloseGuardResult:
        blockers: list[WorkspaceCloseBlocker] = []
        normalized_state = str(runtime_state or "").strip().upper()
        active_orders = max(0, int(active_orders_count))
        open_positions = max(0, int(open_positions_count))
        pending_close = max(0, int(pending_close_decisions_count))

        if normalized_state not in {
            WORKSPACE_STATE_STOPPED,
            WORKSPACE_STATE_RESTORED,
        }:
            blockers.append(
                WorkspaceCloseBlocker(
                    code=WORKSPACE_CLOSE_BLOCK_RUNTIME_ACTIVE,
                    reason=f"runtime_state={normalized_state}",
                    details={"runtime_state": normalized_state},
                )
            )
        if active_orders > 0:
            blockers.append(
                WorkspaceCloseBlocker(
                    code=WORKSPACE_CLOSE_BLOCK_ACTIVE_ORDERS,
                    reason=f"active_orders={active_orders}",
                    details={"count": active_orders},
                )
            )
        if open_positions > 0:
            blockers.append(
                WorkspaceCloseBlocker(
                    code=WORKSPACE_CLOSE_BLOCK_OPEN_POSITIONS,
                    reason=f"open_positions={open_positions}",
                    details={"count": open_positions},
                )
            )
        if broker_operation_active:
            blockers.append(
                WorkspaceCloseBlocker(
                    code=WORKSPACE_CLOSE_BLOCK_BROKER_OPERATION,
                    reason="broker_operation_active",
                )
            )
        if market_event_processing:
            blockers.append(
                WorkspaceCloseBlocker(
                    code=WORKSPACE_CLOSE_BLOCK_MARKET_EVENT,
                    reason="market_event_processing",
                )
            )
        if replay_step_active:
            blockers.append(
                WorkspaceCloseBlocker(
                    code=WORKSPACE_CLOSE_BLOCK_REPLAY_STEP,
                    reason="replay_step_active",
                )
            )
        if pending_close > 0:
            blockers.append(
                WorkspaceCloseBlocker(
                    code=WORKSPACE_CLOSE_BLOCK_PENDING_CLOSE,
                    reason=f"pending_close_decisions={pending_close}",
                    details={"count": pending_close},
                )
            )

        return WorkspaceCloseGuardResult(blockers=tuple(blockers))
