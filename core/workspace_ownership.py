# core/workspace_ownership.py — WSP snapshot та точна належність
# -*- coding: utf-8 -*-
"""Канонічні snapshot Orders/Positions WSP та точна фільтрація належності.

Модуль нормалізує broker-neutral рядки, зберігає обов’язкові поля
прив’язки до WSP і відсікає чужі broker/runtime записи. Для Replay
position snapshot додатково зберігає ``signal_timestamp`` і ``signal_uid``
окремо від ``opened_at``: це час/ідентичність рішення і час фактичного входу.
Так UI може точно зв’язати Signal -> Position -> Entry без зміни execution
rules або broker execution.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from core.algorithm_workspace import AlgorithmWorkspace, normalize_workspace_uid

TERMINAL_ORDER_STATUSES = {
    "CANCELLED",
    "CANCELED",
    "CLOSED",
    "EXPIRED",
    "FILLED",
    "REJECTED",
}
TERMINAL_POSITION_STATUSES = {
    "CLOSED",
    "FLAT",
}


class WorkspaceOwnershipError(ValueError):
    """Invalid WSP-owned order or position snapshot."""


@dataclass(frozen=True, slots=True)
class WorkspaceBinding:
    """Exact identity that isolates one WSP from every other workspace."""

    workspace_uid: str
    broker: str
    account_id: str | None
    symbol: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "workspace_uid",
            normalize_workspace_uid(self.workspace_uid),
        )
        object.__setattr__(self, "broker", _required_upper(self.broker, "broker"))
        object.__setattr__(self, "account_id", _optional_upper(self.account_id))
        object.__setattr__(self, "symbol", _required_upper(self.symbol, "symbol"))

    @classmethod
    def from_workspace(cls, workspace: AlgorithmWorkspace) -> WorkspaceBinding:
        return cls(
            workspace_uid=workspace.workspace_uid,
            broker=workspace.broker,
            account_id=workspace.account_id,
            symbol=workspace.symbol,
        )

    def owns(
        self,
        *,
        workspace_uid: str,
        broker: str,
        account_id: str | None,
        symbol: str,
    ) -> bool:
        try:
            candidate = WorkspaceBinding(
                workspace_uid=workspace_uid,
                broker=broker,
                account_id=account_id,
                symbol=symbol,
            )
        except (ValueError, TypeError):
            return False
        return candidate == self


@dataclass(frozen=True, slots=True)
class WorkspaceOrderSnapshot:
    """Broker-neutral order row carrying mandatory WSP ownership metadata."""

    workspace_uid: str
    broker: str
    account_id: str | None
    symbol: str
    order_id: str
    broker_order_id: str | None
    side: str
    order_type: str
    volume: float
    price: float | None
    stop_loss: float | None
    take_profit: float | None
    status: str
    created_at: str
    profit: float
    active: bool
    close_reason: str | None = None

    def __post_init__(self) -> None:
        binding = WorkspaceBinding(
            workspace_uid=self.workspace_uid,
            broker=self.broker,
            account_id=self.account_id,
            symbol=self.symbol,
        )
        object.__setattr__(self, "workspace_uid", binding.workspace_uid)
        object.__setattr__(self, "broker", binding.broker)
        object.__setattr__(self, "account_id", binding.account_id)
        object.__setattr__(self, "symbol", binding.symbol)
        object.__setattr__(self, "order_id", _required_text(self.order_id, "order_id"))
        object.__setattr__(
            self,
            "broker_order_id",
            _optional_text(self.broker_order_id),
        )
        object.__setattr__(self, "side", _required_upper(self.side, "side"))
        object.__setattr__(
            self,
            "order_type",
            _required_upper(self.order_type, "order_type"),
        )
        object.__setattr__(self, "volume", _non_negative_float(self.volume, "volume"))
        object.__setattr__(self, "price", _optional_finite_float(self.price, "price"))
        object.__setattr__(
            self,
            "stop_loss",
            _optional_finite_float(self.stop_loss, "stop_loss"),
        )
        object.__setattr__(
            self,
            "take_profit",
            _optional_finite_float(self.take_profit, "take_profit"),
        )
        object.__setattr__(self, "status", _required_upper(self.status, "status"))
        object.__setattr__(self, "created_at", _optional_text(self.created_at) or "")
        object.__setattr__(self, "profit", _finite_float(self.profit, "profit"))
        object.__setattr__(self, "active", bool(self.active))
        object.__setattr__(
            self,
            "close_reason",
            _optional_text(self.close_reason),
        )

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> WorkspaceOrderSnapshot:
        status = _required_upper(row.get("status"), "status")
        active_value = row.get("active")
        active = (
            status not in TERMINAL_ORDER_STATUSES
            if active_value is None
            else bool(active_value)
        )
        return cls(
            workspace_uid=str(row.get("workspace_uid") or ""),
            broker=str(row.get("broker") or ""),
            account_id=_mapping_optional_text(row.get("account_id")),
            symbol=str(row.get("symbol") or ""),
            order_id=str(row.get("order_id") or ""),
            broker_order_id=_mapping_optional_text(row.get("broker_order_id")),
            side=str(row.get("side") or ""),
            order_type=str(row.get("order_type") or ""),
            volume=_mapping_float(row.get("volume"), 0.0),
            price=_mapping_optional_float(row.get("price")),
            stop_loss=_mapping_optional_float(row.get("stop_loss")),
            take_profit=_mapping_optional_float(row.get("take_profit")),
            status=status,
            created_at=str(row.get("created_at") or ""),
            profit=_mapping_float(row.get("profit"), 0.0),
            active=active,
            close_reason=_mapping_optional_text(row.get("close_reason")),
        )


@dataclass(frozen=True, slots=True)
class WorkspacePositionSnapshot:
    """Broker-neutral position row carrying mandatory WSP ownership metadata."""

    workspace_uid: str
    broker: str
    account_id: str | None
    symbol: str
    position_id: str
    broker_position_id: str | None
    side: str
    volume: float
    entry_price: float | None
    current_price: float | None
    current_profit: float
    peak_profit: float
    profit_drawdown: float
    stop_loss: float | None
    take_profit: float | None
    opened_at: str
    reconciliation_status: str
    active: bool
    closed_at: str | None = None
    close_reason: str | None = None
    signal_timestamp: str | None = None
    signal_uid: str | None = None

    def __post_init__(self) -> None:
        binding = WorkspaceBinding(
            workspace_uid=self.workspace_uid,
            broker=self.broker,
            account_id=self.account_id,
            symbol=self.symbol,
        )
        current_profit = _finite_float(self.current_profit, "current_profit")
        peak_profit = max(
            _finite_float(self.peak_profit, "peak_profit"),
            current_profit,
            0.0,
        )
        drawdown = _profit_drawdown(current_profit, peak_profit)

        object.__setattr__(self, "workspace_uid", binding.workspace_uid)
        object.__setattr__(self, "broker", binding.broker)
        object.__setattr__(self, "account_id", binding.account_id)
        object.__setattr__(self, "symbol", binding.symbol)
        object.__setattr__(
            self,
            "position_id",
            _required_text(self.position_id, "position_id"),
        )
        object.__setattr__(
            self,
            "broker_position_id",
            _optional_text(self.broker_position_id),
        )
        object.__setattr__(self, "side", _required_upper(self.side, "side"))
        object.__setattr__(self, "volume", _non_negative_float(self.volume, "volume"))
        object.__setattr__(
            self,
            "entry_price",
            _optional_finite_float(self.entry_price, "entry_price"),
        )
        object.__setattr__(
            self,
            "current_price",
            _optional_finite_float(self.current_price, "current_price"),
        )
        object.__setattr__(self, "current_profit", current_profit)
        object.__setattr__(self, "peak_profit", peak_profit)
        object.__setattr__(self, "profit_drawdown", drawdown)
        object.__setattr__(
            self,
            "stop_loss",
            _optional_finite_float(self.stop_loss, "stop_loss"),
        )
        object.__setattr__(
            self,
            "take_profit",
            _optional_finite_float(self.take_profit, "take_profit"),
        )
        object.__setattr__(self, "opened_at", _optional_text(self.opened_at) or "")
        object.__setattr__(
            self,
            "reconciliation_status",
            _required_upper(
                self.reconciliation_status,
                "reconciliation_status",
            ),
        )
        object.__setattr__(self, "active", bool(self.active))
        object.__setattr__(
            self,
            "closed_at",
            _optional_text(self.closed_at),
        )
        object.__setattr__(
            self,
            "close_reason",
            _optional_text(self.close_reason),
        )
        object.__setattr__(
            self,
            "signal_timestamp",
            _optional_text(self.signal_timestamp),
        )
        object.__setattr__(
            self,
            "signal_uid",
            _optional_text(self.signal_uid),
        )

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> WorkspacePositionSnapshot:
        reconciliation_status = _required_upper(
            row.get("reconciliation_status") or row.get("status") or "UNKNOWN",
            "reconciliation_status",
        )
        volume = _mapping_float(row.get("volume"), 0.0)
        active_value = row.get("active")
        active = (
            volume > 0.0 and reconciliation_status not in TERMINAL_POSITION_STATUSES
            if active_value is None
            else bool(active_value)
        )
        return cls(
            workspace_uid=str(row.get("workspace_uid") or ""),
            broker=str(row.get("broker") or ""),
            account_id=_mapping_optional_text(row.get("account_id")),
            symbol=str(row.get("symbol") or ""),
            position_id=str(row.get("position_id") or ""),
            broker_position_id=_mapping_optional_text(row.get("broker_position_id")),
            side=str(row.get("side") or ""),
            volume=volume,
            entry_price=_mapping_optional_float(row.get("entry_price")),
            current_price=_mapping_optional_float(row.get("current_price")),
            current_profit=_mapping_float(row.get("current_profit"), 0.0),
            peak_profit=_mapping_float(row.get("peak_profit"), 0.0),
            profit_drawdown=0.0,
            stop_loss=_mapping_optional_float(row.get("stop_loss")),
            take_profit=_mapping_optional_float(row.get("take_profit")),
            opened_at=str(row.get("opened_at") or ""),
            reconciliation_status=reconciliation_status,
            active=active,
            closed_at=_mapping_optional_text(row.get("closed_at")),
            close_reason=_mapping_optional_text(row.get("close_reason")),
            signal_timestamp=_mapping_optional_text(row.get("signal_timestamp")),
            signal_uid=_mapping_optional_text(row.get("signal_uid")),
        )


@dataclass(frozen=True, slots=True)
class WorkspaceOwnedSnapshot:
    """Exact WSP-owned subset selected from shared broker/runtime rows."""

    orders: tuple[WorkspaceOrderSnapshot, ...]
    positions: tuple[WorkspacePositionSnapshot, ...]
    rejected_orders: int = 0
    rejected_positions: int = 0

    @property
    def active_orders(self) -> tuple[WorkspaceOrderSnapshot, ...]:
        return tuple(order for order in self.orders if order.active)

    @property
    def active_positions(self) -> tuple[WorkspacePositionSnapshot, ...]:
        return tuple(position for position in self.positions if position.active)

    @property
    def current_profit(self) -> float:
        return sum(position.current_profit for position in self.active_positions)

    @property
    def peak_profit(self) -> float:
        return sum(position.peak_profit for position in self.active_positions)


class WorkspaceOwnershipFilter:
    """Filter shared broker/runtime rows by all four WSP binding fields."""

    def __init__(self, binding: WorkspaceBinding) -> None:
        self.binding = binding

    @classmethod
    def from_workspace(
        cls,
        workspace: AlgorithmWorkspace,
    ) -> WorkspaceOwnershipFilter:
        return cls(WorkspaceBinding.from_workspace(workspace))

    def select(
        self,
        order_rows: Iterable[WorkspaceOrderSnapshot | Mapping[str, Any]],
        position_rows: Iterable[WorkspacePositionSnapshot | Mapping[str, Any]],
    ) -> WorkspaceOwnedSnapshot:
        orders: list[WorkspaceOrderSnapshot] = []
        positions: list[WorkspacePositionSnapshot] = []
        rejected_orders = 0
        rejected_positions = 0

        for row in order_rows:
            try:
                order = (
                    row
                    if isinstance(row, WorkspaceOrderSnapshot)
                    else WorkspaceOrderSnapshot.from_mapping(row)
                )
            except (TypeError, ValueError):
                rejected_orders += 1
                continue
            if self._owns_order(order):
                orders.append(order)
            else:
                rejected_orders += 1

        for row in position_rows:
            try:
                position = (
                    row
                    if isinstance(row, WorkspacePositionSnapshot)
                    else WorkspacePositionSnapshot.from_mapping(row)
                )
            except (TypeError, ValueError):
                rejected_positions += 1
                continue
            if self._owns_position(position):
                positions.append(position)
            else:
                rejected_positions += 1

        return WorkspaceOwnedSnapshot(
            orders=tuple(orders),
            positions=tuple(positions),
            rejected_orders=rejected_orders,
            rejected_positions=rejected_positions,
        )

    def _owns_order(self, order: WorkspaceOrderSnapshot) -> bool:
        return self.binding.owns(
            workspace_uid=order.workspace_uid,
            broker=order.broker,
            account_id=order.account_id,
            symbol=order.symbol,
        )

    def _owns_position(self, position: WorkspacePositionSnapshot) -> bool:
        return self.binding.owns(
            workspace_uid=position.workspace_uid,
            broker=position.broker,
            account_id=position.account_id,
            symbol=position.symbol,
        )


def _required_text(value: object, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise WorkspaceOwnershipError(f"{field_name} is required")
    return normalized


def _optional_text(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _required_upper(value: object, field_name: str) -> str:
    return _required_text(value, field_name).upper()


def _optional_upper(value: object) -> str | None:
    normalized = _optional_text(value)
    return None if normalized is None else normalized.upper()


def _finite_float(value: object, field_name: str) -> float:
    try:
        normalized = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise WorkspaceOwnershipError(f"{field_name} must be numeric") from exc
    if not math.isfinite(normalized):
        raise WorkspaceOwnershipError(f"{field_name} must be finite")
    return normalized


def _non_negative_float(value: object, field_name: str) -> float:
    normalized = _finite_float(value, field_name)
    if normalized < 0.0:
        raise WorkspaceOwnershipError(f"{field_name} cannot be negative")
    return normalized


def _optional_finite_float(value: object, field_name: str) -> float | None:
    if value is None or value == "":
        return None
    return _finite_float(value, field_name)


def _mapping_float(value: object, default: float) -> float:
    if value is None or value == "":
        return default
    return _finite_float(value, "mapping value")


def _mapping_optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return _finite_float(value, "mapping value")


def _mapping_optional_text(value: object) -> str | None:
    return _optional_text(value)


def _profit_drawdown(current_profit: float, peak_profit: float) -> float:
    if peak_profit <= 0.0:
        return 0.0
    return max(0.0, (peak_profit - current_profit) / peak_profit * 100.0)
