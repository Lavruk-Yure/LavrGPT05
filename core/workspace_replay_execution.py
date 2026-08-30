# core/workspace_replay_execution.py — virtual execution Replay WSP
# -*- coding: utf-8 -*-
"""Детермінований virtual order -> position lifecycle для Replay WSP.

Модуль реалізує NEXT_BAR_OPEN, Replay margin 1:500, SL/TP, Profit
Drawdown, session-end close та historical trade diagnostics без broker
execution. RoadMap99_04C зберігає у position snapshot два моменти:
``signal_timestamp``/``signal_uid`` алгоритмічного рішення і ``opened_at``
фактичного входу на наступному барі. RoadMap100 оптимізує довгі Replay-прогони без
зміни торгової математики: immutable snapshot закритої virtual position
кешується після першого формування і надалі повторно використовується.
Активні позиції як і раніше формують новий snapshot на кожній execution-
події, тому current price/PnL/SL/TP залишаються актуальними. Broker execution
не виконується.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from core.timeframes import get_timeframe
from core.workspace_historical_trade_diagnostics import (
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent
from core.workspace_ownership import (
    WorkspaceOrderSnapshot,
    WorkspaceOwnedSnapshot,
    WorkspacePositionSnapshot,
)
from core.workspace_profit_guard import WorkspaceProfitProtectionDecision
from core.workspace_replay_margin import (
    HISTORICAL_REPLAY_LEVERAGE,
    WorkspaceReplayMarginSnapshot,
    replay_required_margin,
)
from core.workspace_signal import WorkspaceSignalRecord

REPLAY_CLOSE_STOP_LOSS = "STOP_LOSS"
REPLAY_CLOSE_TAKE_PROFIT = "TAKE_PROFIT"
REPLAY_CLOSE_PROFIT_DRAWDOWN = "PROFIT_DRAWDOWN"
REPLAY_CLOSE_SESSION_END = "SESSION_END"
REPLAY_CLOSE_REASONS = (
    REPLAY_CLOSE_STOP_LOSS,
    REPLAY_CLOSE_TAKE_PROFIT,
    REPLAY_CLOSE_PROFIT_DRAWDOWN,
    REPLAY_CLOSE_SESSION_END,
)


MAX_REPLAY_EXECUTION_ROWS = 1000

REPLAY_ORDER_STATUS_PENDING_NEXT_BAR_OPEN = "PENDING_NEXT_BAR_OPEN"
REPLAY_ORDER_STATUS_EXPIRED_NEXT_BAR_GAP = "EXPIRED_NEXT_BAR_GAP"


@dataclass(frozen=True, slots=True)
class WorkspaceReplayExecutionPolicy:
    """Explicit first Replay policy; no broker operation is permitted."""

    fixed_volume: float
    maximum_open_positions: int
    stop_range_multiplier: float = 1.0
    take_profit_r_multiple: float = 2.0
    minimum_spread_multiples: float = 10.0
    ambiguous_bar_policy: str = "STOP_LOSS_FIRST"

    def __post_init__(self) -> None:
        fixed_volume = _positive_float(self.fixed_volume, "fixed_volume")
        maximum_open_positions = _positive_int(
            self.maximum_open_positions,
            "maximum_open_positions",
        )
        stop_range_multiplier = _positive_float(
            self.stop_range_multiplier,
            "stop_range_multiplier",
        )
        take_profit_r_multiple = _positive_float(
            self.take_profit_r_multiple,
            "take_profit_r_multiple",
        )
        minimum_spread_multiples = _positive_float(
            self.minimum_spread_multiples,
            "minimum_spread_multiples",
        )
        ambiguous_bar_policy = str(self.ambiguous_bar_policy or "").strip().upper()
        if ambiguous_bar_policy != "STOP_LOSS_FIRST":
            raise ValueError("Only STOP_LOSS_FIRST is supported")
        object.__setattr__(self, "fixed_volume", fixed_volume)
        object.__setattr__(
            self,
            "maximum_open_positions",
            maximum_open_positions,
        )
        object.__setattr__(
            self,
            "stop_range_multiplier",
            stop_range_multiplier,
        )
        object.__setattr__(
            self,
            "take_profit_r_multiple",
            take_profit_r_multiple,
        )
        object.__setattr__(
            self,
            "minimum_spread_multiples",
            minimum_spread_multiples,
        )
        object.__setattr__(
            self,
            "ambiguous_bar_policy",
            ambiguous_bar_policy,
        )


@dataclass(slots=True)
class _PendingOrder:
    order_id: str
    signal_uid: str
    side: str
    created_at: datetime
    expected_fill_at: datetime
    projected_stop_loss: float
    projected_take_profit: float
    protection_distance: float
    macd_state: str
    alligator_state: str
    alligator_timeframe: str


@dataclass(slots=True)
class _VirtualPosition:
    position_id: str
    order_id: str
    side: str
    volume: float
    entry_price: float
    current_price: float
    current_profit: float
    peak_profit: float
    stop_loss: float
    take_profit: float
    opened_at: datetime
    required_margin: float
    signal_uid: str
    signal_timestamp: datetime
    macd_state: str
    alligator_state: str
    alligator_timeframe: str
    maximum_favorable_excursion: float = 0.0
    maximum_adverse_excursion: float = 0.0
    active: bool = True
    close_reason: str | None = None
    closed_at: datetime | None = None
    closed_snapshot: WorkspacePositionSnapshot | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceReplayExecutionEvent:
    """One explainable virtual lifecycle transition for the WSP journal."""

    event: str
    message: str
    details: dict[str, object]


class WorkspaceReplayExecutionEngine:
    """Replay-only virtual execution with deterministic OHLC protection."""

    def __init__(
        self,
        *,
        workspace_uid: str,
        broker: str,
        account_id: str | None,
        symbol: str,
        policy: WorkspaceReplayExecutionPolicy,
        initial_balance: float = 1000.0,
        leverage: float = HISTORICAL_REPLAY_LEVERAGE,
    ) -> None:
        self.workspace_uid = str(workspace_uid or "").strip()
        self.broker = str(broker or "").strip().upper()
        self.account_id = str(account_id or "").strip() or None
        self.symbol = str(symbol or "").strip().upper()
        if not self.workspace_uid:
            raise ValueError("workspace_uid is required")
        if not self.broker:
            raise ValueError("broker is required")
        if not self.symbol:
            raise ValueError("symbol is required")
        self.policy = policy
        self.initial_balance = _positive_float(
            initial_balance,
            "initial_balance",
        )
        self.leverage = _positive_float(leverage, "leverage")
        self._pending_orders: list[_PendingOrder] = []
        self._positions: list[_VirtualPosition] = []
        self._order_rows: list[WorkspaceOrderSnapshot] = []
        self._trade_diagnostics: list[WorkspaceHistoricalTradeDiagnostic] = []
        self._order_counter = 0
        self._position_counter = 0
        self.realized_profit = 0.0
        self.closed_trades = 0

    def reset(self) -> None:
        """Clear only volatile Replay execution state."""
        self._pending_orders = []
        self._positions = []
        self._order_rows = []
        self._trade_diagnostics = []
        self._order_counter = 0
        self._position_counter = 0
        self.realized_profit = 0.0
        self.closed_trades = 0

    def margin_snapshot(self) -> WorkspaceReplayMarginSnapshot:
        """Return current synthetic balance/equity/margin state."""
        unrealized_profit = sum(
            position.current_profit for position in self._positions if position.active
        )
        balance = self.initial_balance + self.realized_profit
        equity = balance + unrealized_profit
        used_margin = sum(
            position.required_margin for position in self._positions if position.active
        )
        return WorkspaceReplayMarginSnapshot(
            leverage=self.leverage,
            balance=balance,
            equity=equity,
            used_margin=used_margin,
            free_margin=equity - used_margin,
        )

    def trade_diagnostics(
        self,
    ) -> tuple[WorkspaceHistoricalTradeDiagnostic, ...]:
        """Return all closed Replay trades in deterministic close order."""
        return tuple(self._trade_diagnostics)

    @property
    def active_positions_count(self) -> int:
        return sum(1 for position in self._positions if position.active)

    @property
    def pending_orders_count(self) -> int:
        return len(self._pending_orders)

    def queue_signal(
        self,
        record: WorkspaceSignalRecord,
        signal_event: WorkspaceMarketEvent,
    ) -> tuple[WorkspaceReplayExecutionEvent, ...]:
        """Queue one accepted signal for fill on the next Replay bar open."""
        if not record.accepted:
            return ()
        capacity_used = self.active_positions_count + self.pending_orders_count
        if capacity_used >= self.policy.maximum_open_positions:
            return (
                WorkspaceReplayExecutionEvent(
                    event="VIRTUAL_ORDER_BLOCKED",
                    message=(
                        "Replay virtual order blocked by maximum open "
                        "positions policy."
                    ),
                    details={
                        "signal_uid": record.signal_uid,
                        "maximum_open_positions": self.policy.maximum_open_positions,
                        "broker_execution_attempted": False,
                    },
                ),
            )
        self._order_counter += 1
        order_id = f"RPL-ORD-{self._order_counter:06d}"
        direction = record.direction.upper()
        distance = self._protection_distance(signal_event)
        reference_price = signal_event.close
        if direction == "BUY":
            stop_loss = reference_price - distance
            take_profit = (
                reference_price + distance * self.policy.take_profit_r_multiple
            )
        elif direction == "SELL":
            stop_loss = reference_price + distance
            take_profit = (
                reference_price - distance * self.policy.take_profit_r_multiple
            )
        else:
            raise ValueError(f"Unsupported Replay signal direction: {direction}")
        timeframe_minutes = get_timeframe(signal_event.timeframe).minutes
        expected_fill_at = signal_event.timestamp + timedelta(minutes=timeframe_minutes)
        pending = _PendingOrder(
            order_id=order_id,
            signal_uid=record.signal_uid,
            side=direction,
            created_at=record.timestamp,
            expected_fill_at=expected_fill_at,
            projected_stop_loss=stop_loss,
            projected_take_profit=take_profit,
            protection_distance=distance,
            macd_state=record.macd_state,
            alligator_state=record.alligator_confirmation,
            alligator_timeframe=(
                record.filter_context.timeframe
                if record.filter_context is not None
                else record.timeframe
            ),
        )
        self._pending_orders.append(pending)
        self._order_rows.append(
            WorkspaceOrderSnapshot(
                workspace_uid=self.workspace_uid,
                broker=self.broker,
                account_id=self.account_id,
                symbol=self.symbol,
                order_id=order_id,
                broker_order_id=None,
                side=direction,
                order_type="VIRTUAL_MARKET",
                volume=self.policy.fixed_volume,
                price=None,
                stop_loss=stop_loss,
                take_profit=take_profit,
                status=REPLAY_ORDER_STATUS_PENDING_NEXT_BAR_OPEN,
                created_at=record.timestamp.astimezone(UTC).isoformat(),
                profit=0.0,
                active=True,
            )
        )
        self._trim_rows()
        return (
            WorkspaceReplayExecutionEvent(
                event="VIRTUAL_ORDER_CREATED",
                message=(
                    f"Replay {direction} market order {order_id} queued for "
                    "the next bar open."
                ),
                details={
                    "order_id": order_id,
                    "signal_uid": record.signal_uid,
                    "side": direction,
                    "volume": self.policy.fixed_volume,
                    "projected_stop_loss": stop_loss,
                    "projected_take_profit": take_profit,
                    "expected_fill_at": expected_fill_at.isoformat(),
                    "broker_execution_attempted": False,
                },
            ),
        )

    def on_market_event(
        self,
        event: WorkspaceMarketEvent,
    ) -> tuple[WorkspaceReplayExecutionEvent, ...]:
        """Fill pending orders, evaluate SL/TP, then mark active positions."""
        lifecycle: list[WorkspaceReplayExecutionEvent] = []
        pending_orders = tuple(self._pending_orders)
        self._pending_orders = []
        for pending in pending_orders:
            if event.timestamp < pending.expected_fill_at:
                self._pending_orders.append(pending)
                continue
            if event.timestamp > pending.expected_fill_at:
                lifecycle.append(self._expire_pending_order_gap(pending, event))
                continue
            lifecycle.append(self._fill_pending_order(pending, event))
        for position in tuple(self._positions):
            if not position.active:
                continue
            close_reason = self._bar_close_reason(position, event)
            if close_reason is not None:
                close_price = self._protection_close_price(
                    position,
                    event,
                    close_reason,
                )
                self._update_close_excursion(position, close_price)
                lifecycle.append(
                    self._close_position(
                        position,
                        event,
                        close_price=close_price,
                        close_reason=close_reason,
                    )
                )
                continue
            self._update_open_bar_excursions(position, event)
            self._mark_position(position, event)
        return tuple(lifecycle)

    def close_profit_drawdown(
        self,
        decisions: tuple[WorkspaceProfitProtectionDecision, ...],
        event: WorkspaceMarketEvent,
    ) -> tuple[WorkspaceReplayExecutionEvent, ...]:
        """Apply CLOSE decisions only to virtual Replay positions."""
        by_id = {
            position.position_id: position
            for position in self._positions
            if position.active
        }
        lifecycle: list[WorkspaceReplayExecutionEvent] = []
        for decision in decisions:
            if not decision.close_requested:
                continue
            position = by_id.get(decision.position_id)
            if position is None:
                continue
            close_price = self._executable_close_price(position, event)
            self._update_close_excursion(position, close_price)
            lifecycle.append(
                self._close_position(
                    position,
                    event,
                    close_price=close_price,
                    close_reason=REPLAY_CLOSE_PROFIT_DRAWDOWN,
                )
            )
        return tuple(lifecycle)

    def complete(
        self,
        event: WorkspaceMarketEvent,
    ) -> tuple[WorkspaceReplayExecutionEvent, ...]:
        """Cancel unfilled orders and close open positions at session end."""
        lifecycle: list[WorkspaceReplayExecutionEvent] = []
        for pending in tuple(self._pending_orders):
            self._replace_order_row(
                pending.order_id,
                status="CANCELLED_SESSION_END",
                active=False,
            )
            lifecycle.append(
                WorkspaceReplayExecutionEvent(
                    event="VIRTUAL_ORDER_CANCELLED",
                    message=(
                        f"Replay order {pending.order_id} cancelled because "
                        "no next bar exists."
                    ),
                    details={
                        "order_id": pending.order_id,
                        "broker_execution_attempted": False,
                    },
                )
            )
        self._pending_orders = []
        for position in tuple(self._positions):
            if not position.active:
                continue
            close_price = self._executable_close_price(position, event)
            self._update_close_excursion(position, close_price)
            lifecycle.append(
                self._close_position(
                    position,
                    event,
                    close_price=close_price,
                    close_reason=REPLAY_CLOSE_SESSION_END,
                )
            )
        return tuple(lifecycle)

    def snapshot(self) -> WorkspaceOwnedSnapshot:
        """Return immutable virtual rows consumed by existing WSP UI tables."""
        positions = tuple(
            self._position_snapshot(position) for position in self._positions
        )
        return WorkspaceOwnedSnapshot(
            orders=tuple(self._order_rows),
            positions=positions,
        )

    def modify_position_protection(
        self,
        position_id: str,
        *,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        modified_at: datetime,
        effective_from: datetime,
        source: str,
    ) -> WorkspaceReplayExecutionEvent:
        """Змінити SL/TP active virtual position без reprocess поточного bar.

        Метод не читає broker state і не виконує market event повторно. Новий
        protection рівень лише записується у virtual position та починає діяти
        з наступного ще не обробленого Replay execution event, timestamp якого
        runtime передає у ``effective_from``.
        """
        normalized_id = str(position_id or "").strip()
        if not normalized_id:
            raise ValueError("position_id is required")
        if stop_loss is None and take_profit is None:
            raise ValueError("stop_loss or take_profit is required")

        position = next(
            (
                item
                for item in self._positions
                if item.position_id == normalized_id and item.active
            ),
            None,
        )
        if position is None:
            raise ValueError(f"Active Replay position not found: {normalized_id}")

        executable_price = _positive_float(position.current_price, "current_price")
        old_stop_loss = position.stop_loss
        old_take_profit = position.take_profit
        new_stop_loss = old_stop_loss
        new_take_profit = old_take_profit

        if stop_loss is not None:
            normalized_stop = _positive_float(stop_loss, "stop_loss")
            if position.side == "BUY" and normalized_stop >= executable_price:
                raise ValueError("BUY Stop Loss must be below current Bid")
            if position.side == "SELL" and normalized_stop <= executable_price:
                raise ValueError("SELL Stop Loss must be above current Ask")
            new_stop_loss = normalized_stop

        if take_profit is not None:
            normalized_take = _positive_float(take_profit, "take_profit")
            if position.side == "BUY" and normalized_take <= executable_price:
                raise ValueError("BUY Take Profit must be above current Bid")
            if position.side == "SELL" and normalized_take >= executable_price:
                raise ValueError("SELL Take Profit must be below current Ask")
            new_take_profit = normalized_take

        position.stop_loss = new_stop_loss
        position.take_profit = new_take_profit

        self._replace_order_row(
            position.order_id,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
        )
        normalized_source = str(source or "MANUAL").strip().upper()
        return WorkspaceReplayExecutionEvent(
            event="REPLAY_POSITION_PROTECTION_MODIFIED",
            message=(
                f"Replay position {position.position_id} protection modified "
                f"from {normalized_source}."
            ),
            details={
                "position_id": position.position_id,
                "order_id": position.order_id,
                "side": position.side,
                "old_stop_loss": old_stop_loss,
                "new_stop_loss": position.stop_loss,
                "old_take_profit": old_take_profit,
                "new_take_profit": position.take_profit,
                "modification_timestamp": modified_at.astimezone(UTC).isoformat(),
                "effective_from": effective_from.astimezone(UTC).isoformat(),
                "source": normalized_source,
                "broker_execution_attempted": False,
            },
        )

    def _expire_pending_order_gap(
        self,
        pending: _PendingOrder,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceReplayExecutionEvent:
        self._replace_order_row(
            pending.order_id,
            status=REPLAY_ORDER_STATUS_EXPIRED_NEXT_BAR_GAP,
            active=False,
        )
        return WorkspaceReplayExecutionEvent(
            event="VIRTUAL_ORDER_EXPIRED_NEXT_BAR_GAP",
            message=(
                f"Replay order {pending.order_id} expired because the "
                "expected next bar is missing."
            ),
            details={
                "order_id": pending.order_id,
                "signal_timestamp": pending.created_at.isoformat(),
                "expected_fill_at": pending.expected_fill_at.isoformat(),
                "first_available_at": event.timestamp.isoformat(),
                "broker_execution_attempted": False,
            },
        )

    def _fill_pending_order(
        self,
        pending: _PendingOrder,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceReplayExecutionEvent:
        half_spread = event.spread / 2.0
        if pending.side == "BUY":
            entry_price = event.open + half_spread
            stop_loss = entry_price - pending.protection_distance
            take_profit = (
                entry_price
                + pending.protection_distance * self.policy.take_profit_r_multiple
            )
        else:
            entry_price = event.open - half_spread
            stop_loss = entry_price + pending.protection_distance
            take_profit = (
                entry_price
                - pending.protection_distance * self.policy.take_profit_r_multiple
            )
        required_margin = replay_required_margin(
            volume=self.policy.fixed_volume,
            price=entry_price,
            leverage=self.leverage,
        )
        free_margin = self.margin_snapshot().free_margin
        if required_margin > free_margin:
            self._replace_order_row(
                pending.order_id,
                status="BLOCKED_MARGIN",
                active=False,
            )
            return WorkspaceReplayExecutionEvent(
                event="VIRTUAL_ORDER_BLOCKED_MARGIN",
                message=(
                    f"Replay order {pending.order_id} blocked by margin " "requirement."
                ),
                details={
                    "order_id": pending.order_id,
                    "attempted_entry_price": entry_price,
                    "required_margin": required_margin,
                    "free_margin": free_margin,
                    "leverage": self.leverage,
                    "broker_execution_attempted": False,
                },
            )
        self._position_counter += 1
        position_id = f"RPL-POS-{self._position_counter:06d}"
        position = _VirtualPosition(
            position_id=position_id,
            order_id=pending.order_id,
            side=pending.side,
            volume=self.policy.fixed_volume,
            entry_price=entry_price,
            current_price=entry_price,
            current_profit=0.0,
            peak_profit=0.0,
            stop_loss=stop_loss,
            take_profit=take_profit,
            opened_at=event.timestamp,
            required_margin=required_margin,
            signal_uid=pending.signal_uid,
            signal_timestamp=pending.created_at,
            macd_state=pending.macd_state,
            alligator_state=pending.alligator_state,
            alligator_timeframe=pending.alligator_timeframe,
        )
        self._positions.append(position)
        self._replace_order_row(
            pending.order_id,
            price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            status="FILLED",
            active=False,
        )
        self._trim_rows()
        return WorkspaceReplayExecutionEvent(
            event="VIRTUAL_POSITION_OPENED",
            message=(
                f"Replay position {position_id} opened from order "
                f"{pending.order_id}."
            ),
            details={
                "position_id": position_id,
                "order_id": pending.order_id,
                "side": pending.side,
                "volume": self.policy.fixed_volume,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "required_margin": required_margin,
                "leverage": self.leverage,
                "broker_execution_attempted": False,
            },
        )

    @staticmethod
    def _bar_close_reason(
        position: _VirtualPosition,
        event: WorkspaceMarketEvent,
    ) -> str | None:
        if position.side == "BUY":
            stop_touched = event.low <= position.stop_loss
            take_touched = event.high >= position.take_profit
        else:
            stop_touched = event.high >= position.stop_loss
            take_touched = event.low <= position.take_profit
        if stop_touched:
            return REPLAY_CLOSE_STOP_LOSS
        if take_touched:
            return REPLAY_CLOSE_TAKE_PROFIT
        return None

    @staticmethod
    def _protection_close_price(
        position: _VirtualPosition,
        event: WorkspaceMarketEvent,
        close_reason: str,
    ) -> float:
        _ = event
        if close_reason == REPLAY_CLOSE_STOP_LOSS:
            return position.stop_loss
        if close_reason == REPLAY_CLOSE_TAKE_PROFIT:
            return position.take_profit
        raise ValueError(f"Unsupported protection close reason: {close_reason}")

    def _update_open_bar_excursions(
        self,
        position: _VirtualPosition,
        event: WorkspaceMarketEvent,
    ) -> None:
        """Update diagnostic MFE/MAE for a bar survived by the trade."""
        if position.side == "BUY":
            favorable_price = event.high
            adverse_price = event.low
        else:
            favorable_price = event.low
            adverse_price = event.high
        favorable_profit = self._profit(position, favorable_price)
        adverse_profit = self._profit(position, adverse_price)
        position.maximum_favorable_excursion = max(
            position.maximum_favorable_excursion,
            favorable_profit,
            0.0,
        )
        position.maximum_adverse_excursion = min(
            position.maximum_adverse_excursion,
            adverse_profit,
            0.0,
        )

    def _update_close_excursion(
        self,
        position: _VirtualPosition,
        close_price: float,
    ) -> None:
        """Record the known close point without assuming intrabar ordering."""
        final_profit = self._profit(position, close_price)
        position.maximum_favorable_excursion = max(
            position.maximum_favorable_excursion,
            final_profit,
            0.0,
        )
        position.maximum_adverse_excursion = min(
            position.maximum_adverse_excursion,
            final_profit,
            0.0,
        )

    def _mark_position(
        self,
        position: _VirtualPosition,
        event: WorkspaceMarketEvent,
    ) -> None:
        current_price = self._executable_close_price(position, event)
        current_profit = self._profit(position, current_price)
        position.current_price = current_price
        position.current_profit = current_profit
        position.peak_profit = max(position.peak_profit, current_profit, 0.0)

    def _close_position(
        self,
        position: _VirtualPosition,
        event: WorkspaceMarketEvent,
        *,
        close_price: float,
        close_reason: str,
    ) -> WorkspaceReplayExecutionEvent:
        if close_reason not in REPLAY_CLOSE_REASONS:
            raise ValueError(f"Unsupported Replay close reason: {close_reason}")
        realized_profit = self._profit(position, close_price)
        position.current_price = close_price
        position.current_profit = realized_profit
        position.peak_profit = max(position.peak_profit, realized_profit, 0.0)
        position.active = False
        position.close_reason = close_reason
        position.closed_at = event.timestamp
        self.realized_profit += realized_profit
        self.closed_trades += 1
        self._trade_diagnostics.append(
            WorkspaceHistoricalTradeDiagnostic(
                position_id=position.position_id,
                order_id=position.order_id,
                signal_uid=position.signal_uid,
                signal_timestamp=position.signal_timestamp,
                entry_timestamp=position.opened_at,
                close_timestamp=event.timestamp,
                entry_price=position.entry_price,
                close_price=close_price,
                direction=position.side,
                volume=position.volume,
                macd_state=position.macd_state,
                alligator_state=position.alligator_state,
                alligator_timeframe=position.alligator_timeframe,
                stop_loss_distance=abs(position.entry_price - position.stop_loss),
                take_profit_distance=abs(position.take_profit - position.entry_price),
                maximum_favorable_excursion=position.maximum_favorable_excursion,
                maximum_adverse_excursion=position.maximum_adverse_excursion,
                peak_profit=position.peak_profit,
                final_profit=realized_profit,
                close_reason=close_reason,
                holding_seconds=(event.timestamp - position.opened_at).total_seconds(),
            )
        )
        self._replace_order_row(
            position.order_id,
            profit=realized_profit,
            close_reason=close_reason,
        )
        return WorkspaceReplayExecutionEvent(
            event="VIRTUAL_POSITION_CLOSED",
            message=(
                f"Replay position {position.position_id} closed by "
                f"{close_reason}; PnL={realized_profit:.2f}."
            ),
            details={
                "position_id": position.position_id,
                "order_id": position.order_id,
                "close_reason": close_reason,
                "close_price": close_price,
                "realized_profit": realized_profit,
                "broker_execution_attempted": False,
            },
        )

    @staticmethod
    def _executable_close_price(
        position: _VirtualPosition,
        event: WorkspaceMarketEvent,
    ) -> float:
        return event.bid if position.side == "BUY" else event.ask

    @staticmethod
    def _profit(position: _VirtualPosition, close_price: float) -> float:
        direction = 1.0 if position.side == "BUY" else -1.0
        return (close_price - position.entry_price) * position.volume * direction

    def _protection_distance(self, event: WorkspaceMarketEvent) -> float:
        signal_range = max(event.high - event.low, 0.0)
        spread_floor = event.spread * self.policy.minimum_spread_multiples
        distance = max(signal_range, spread_floor) * self.policy.stop_range_multiplier
        if not math.isfinite(distance) or distance <= 0.0:
            raise ValueError("Replay protection distance must be positive")
        return distance

    def _position_snapshot(
        self,
        position: _VirtualPosition,
    ) -> WorkspacePositionSnapshot:
        """Повернути DTO позиції, кешуючи незмінний закритий стан."""
        if not position.active and position.closed_snapshot is not None:
            return position.closed_snapshot

        reconciliation_status = "REPLAY_VIRTUAL_ACTIVE"
        if not position.active:
            close_reason = position.close_reason or "UNKNOWN"
            reconciliation_status = f"REPLAY_VIRTUAL_CLOSED_{close_reason}"
        snapshot = WorkspacePositionSnapshot(
            workspace_uid=self.workspace_uid,
            broker=self.broker,
            account_id=self.account_id,
            symbol=self.symbol,
            position_id=position.position_id,
            broker_position_id=None,
            side=position.side,
            volume=position.volume,
            entry_price=position.entry_price,
            current_price=position.current_price,
            current_profit=position.current_profit,
            peak_profit=position.peak_profit,
            profit_drawdown=0.0,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            opened_at=position.opened_at.astimezone(UTC).isoformat(),
            reconciliation_status=reconciliation_status,
            active=position.active,
            closed_at=(
                position.closed_at.astimezone(UTC).isoformat()
                if position.closed_at is not None
                else None
            ),
            close_reason=position.close_reason,
            signal_timestamp=(position.signal_timestamp.astimezone(UTC).isoformat()),
            signal_uid=position.signal_uid,
        )
        if not position.active:
            position.closed_snapshot = snapshot
        return snapshot

    def _replace_order_row(self, order_id: str, **changes: object) -> None:
        for index, row in enumerate(self._order_rows):
            if row.order_id != order_id:
                continue
            self._order_rows[index] = replace(row, **changes)
            return
        raise ValueError(f"Replay order row not found: {order_id}")

    def _trim_rows(self) -> None:
        if len(self._order_rows) > MAX_REPLAY_EXECUTION_ROWS:
            del self._order_rows[:-MAX_REPLAY_EXECUTION_ROWS]
        if len(self._positions) > MAX_REPLAY_EXECUTION_ROWS:
            del self._positions[:-MAX_REPLAY_EXECUTION_ROWS]


def _positive_float(value: object, field_name: str) -> float:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{field_name} must be positive")
    return number


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        number = int(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if number <= 0:
        raise ValueError(f"{field_name} must be positive")
    return number
