"""Broker-neutral typed order failures for terminal execution outcomes."""

from __future__ import annotations


class BrokerTerminalOrderFailure(RuntimeError):
    """Terminal broker order failure that preserves execution identity."""

    def __init__(
        self,
        *,
        broker: str,
        broker_order_id: str,
        status: str,
        filled: float,
        remaining: float,
        failure_reason: str,
        confirmed_price: float | None = None,
        broker_position_id: str | None = None,
    ) -> None:
        self.broker = str(broker or "").strip().upper()
        self.broker_order_id = str(broker_order_id or "").strip()
        self.status = str(status or "").strip().upper()
        self.filled = max(float(filled or 0.0), 0.0)
        self.remaining = max(float(remaining or 0.0), 0.0)
        self.failure_reason = str(failure_reason or "").strip()
        self.confirmed_price = (
            None if confirmed_price is None else float(confirmed_price)
        )
        self.broker_position_id = (
            None
            if broker_position_id is None
            else str(broker_position_id or "").strip() or None
        )
        if not self.broker:
            raise ValueError("Terminal broker failure requires broker")
        if not self.broker_order_id:
            raise ValueError("Terminal broker failure requires broker order id")
        if not self.status:
            raise ValueError("Terminal broker failure requires status")
        if not self.failure_reason:
            raise ValueError("Terminal broker failure requires failure reason")
        super().__init__(
            f"{self.broker} terminal order failure: "
            f"order_id={self.broker_order_id}, status={self.status}, "
            f"filled={self.filled}, remaining={self.remaining}. "
            f"{self.failure_reason}"
        )
