"""Synthetic cTrader spot-cache and current-price check."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import ctrader_symbols as ctr_symbols  # noqa: E402
from engine.broker_account import BrokerAccount  # noqa: E402
from engine.ctrader_adapter import (  # noqa: E402
    CTraderAdapter,
    CTraderRuntimeConfig,
    CTraderSessionState,
)


class _SpotPayload:
    def __init__(
        self,
        *,
        account_id: int,
        symbol_id: int,
        bid: int | None,
        ask: int | None,
        timestamp: int = 0,
    ) -> None:
        self.ctidTraderAccountId = account_id
        self.symbolId = symbol_id
        self.bid = int(bid or 0)
        self.ask = int(ask or 0)
        self.timestamp = timestamp
        self._present = {
            name
            for name, value in {
                "bid": bid,
                "ask": ask,
                "timestamp": timestamp or None,
            }.items()
            if value is not None
        }

    def __getattr__(self, attribute_name: str):
        if attribute_name == "HasField":
            return self._has_field

        raise AttributeError(attribute_name)

    def _has_field(self, field_name: str) -> bool:
        return field_name in self._present


class _SyntheticCTraderAdapter(CTraderAdapter):
    """Minimal adapter fixture exposing public synthetic helpers."""

    def __init__(self) -> None:
        config = CTraderRuntimeConfig(
            client_id="test",
            client_secret="test",
            access_token="test",
            ctid_trader_account_id=46368962,
            account_mode="DEMO",
        )
        super().__init__(config=config)
        self.state = CTraderSessionState(
            account_info=BrokerAccount(
                broker="CTRADER",
                account_id="46368962",
                account_mode="DEMO",
                currency="USD",
            )
        )
        self._positions_pnl_payload = {
            "900001": 2.0,
            "900002": -1.0,
        }

    def apply_spot_event(self, payload: _SpotPayload) -> None:
        """Apply one synthetic quote through production parsing."""
        self._on_spot_event(payload)

    def set_positions(self, positions: list[SimpleNamespace]) -> None:
        """Provide synthetic reconcile rows."""
        self._positions_payload = list(positions)

    def build_positions_for_test(self):
        """Build canonical rows through production mapping."""
        return self._build_positions()


def _position(
    *,
    position_id: int,
    symbol_id: int,
    trade_side: int,
) -> SimpleNamespace:
    trade_data = SimpleNamespace(
        tradeSide=trade_side,
        volume=100_000,
        symbolId=symbol_id,
        openTimestamp=1_753_171_200_000,
        label="LGE_MANUAL",
        comment="[LGE:M] current price test",
    )
    return SimpleNamespace(
        positionId=position_id,
        tradeData=trade_data,
        price=1.14000,
        stopLoss=0.0,
        takeProfit=0.0,
    )


def main() -> int:
    adapter = _SyntheticCTraderAdapter()
    symbol_id = ctr_symbols.get_enabled_symbol_id("EURUSD")
    adapter.apply_spot_event(
        _SpotPayload(
            account_id=46368962,
            symbol_id=symbol_id,
            bid=114075,
            ask=114085,
            timestamp=1_753_171_201_000,
        )
    )
    adapter.set_positions(
        [
            _position(
                position_id=900001,
                symbol_id=symbol_id,
                trade_side=1,
            ),
            _position(
                position_id=900002,
                symbol_id=symbol_id,
                trade_side=2,
            ),
        ]
    )

    positions = adapter.build_positions_for_test()
    buy_position = positions[0]
    sell_position = positions[1]

    assert buy_position.current_price == 1.14075
    assert sell_position.current_price == 1.14085
    assert buy_position.currency == "USD"
    assert sell_position.currency == "USD"
    buy_raw_payload = buy_position.raw_payload
    assert buy_raw_payload is not None
    assert buy_raw_payload.get("bid") == 1.14075
    assert buy_raw_payload.get("ask") == 1.14085
    assert buy_raw_payload.get("pnl_currency") == "USD"

    print("cTrader current price result")
    print(f"  buy_close_price={buy_position.current_price}")
    print(f"  sell_close_price={sell_position.current_price}")
    print(f"  pnl_currency={buy_position.currency}")
    print("  buy_uses_bid=True")
    print("  sell_uses_ask=True")
    print("CTRADER_CURRENT_PRICE_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
