"""Typed IB order errors used across adapter, runtime, and UI layers."""

from __future__ import annotations


class IBMarketOrderTimeoutError(RuntimeError):
    """IB MARKET order callback timed out after an order ID was allocated."""

    def __init__(
        self,
        *,
        order_id: int,
        symbol_name: str,
        side: str,
        quantity: float,
        status: str = "",
        filled: float = 0.0,
        remaining: float = 0.0,
        child_order_ids: list[int] | tuple[int, ...] | None = None,
        stop_loss_order_id: int | None = None,
        take_profit_order_id: int | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        current_client_id: int | None = None,
        comment: str = "",
    ) -> None:
        self.order_id = int(order_id)
        self.symbol_name = str(symbol_name or "").strip().upper()
        self.side = str(side or "").strip().upper()
        self.quantity = abs(float(quantity))
        self.status = str(status or "").strip().upper()
        self.filled = float(filled or 0.0)
        self.remaining = float(remaining or 0.0)
        self.child_order_ids = tuple(
            int(value)
            for value in (child_order_ids or ())
            if int(value) > 0
        )
        self.stop_loss_order_id = (
            None if stop_loss_order_id is None else int(stop_loss_order_id)
        )
        self.take_profit_order_id = (
            None if take_profit_order_id is None else int(take_profit_order_id)
        )
        self.stop_loss = None if stop_loss is None else float(stop_loss)
        self.take_profit = None if take_profit is None else float(take_profit)
        self.current_client_id = (
            None if current_client_id is None else int(current_client_id)
        )
        self.comment = str(comment or "").strip()
        status_text = self.status or "UNKNOWN"
        super().__init__(
            "IB MARKET order confirmation timed out; execution state is "
            "unknown. Do not repeat the order. "
            f"order_id={self.order_id}, status={status_text}"
        )


class IBManualOpenConfirmationPendingError(RuntimeError):
    """An IB manual Open was sent but final execution is still unknown."""

    def __init__(
        self,
        *,
        trade_uid: str,
        order_id: int,
        details: str,
    ) -> None:
        self.trade_uid = str(trade_uid or "").strip()
        self.order_id = int(order_id)
        self.details = str(details or "").strip()
        super().__init__(
            "IB accepted the manual Open request, but final execution "
            "confirmation is delayed. Do not repeat Open. LGE saved the "
            "exact order and will recover it automatically during Refresh. "
            f"order_id={self.order_id}"
        )


class IBVirtualLegCloseConfirmationPendingError(RuntimeError):
    """A virtual-leg Close was sent but is not yet proven safe to persist."""

    def __init__(
        self,
        *,
        position_uid: str,
        close_order_id: int,
        details: str,
    ) -> None:
        self.position_uid = str(position_uid or "").strip()
        self.close_order_id = int(close_order_id)
        self.details = str(details or "").strip()
        super().__init__(
            "IB accepted a virtual-leg Close request, but final execution "
            "confirmation is delayed. Do not repeat Close. LGE saved the "
            "pending order and will recover it automatically during Refresh. "
            f"close_order_id={self.close_order_id}"
        )
