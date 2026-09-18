"""Typed cTrader order errors used by runtime recovery wiring."""

from __future__ import annotations


class CTraderMarketOrderTimeoutError(RuntimeError):
    """cTrader MARKET order timed out without an exact broker order ID."""

    def __init__(
        self,
        *,
        symbol_name: str,
        side: str,
        lots: float,
        comment: str,
    ) -> None:
        self.symbol_name = str(symbol_name or "").strip().upper()
        self.side = str(side or "").strip().upper()
        self.lots = abs(float(lots))
        self.comment = str(comment or "").strip()
        super().__init__(
            "cTrader MARKET order confirmation timed out; execution state is "
            "unknown. Do not repeat the order before broker recovery resolves "
            "the causal WSP submission."
        )
