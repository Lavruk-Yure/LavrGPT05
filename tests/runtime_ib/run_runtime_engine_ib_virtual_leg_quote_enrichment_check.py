"""Check side-aware IB quotes for reconciled virtual-position legs."""

from __future__ import annotations

import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_position_group import (  # noqa: E402
    IBPositionGroup,
    IBPositionGroupSnapshot,
)
from engine.ib_virtual_position_leg import IBVirtualPositionLeg  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    IB_BROKER_POSITION_KIND_VIRTUAL_FX,
    IB_LEG_STATUS_CLOSED,
    IB_LEG_STATUS_OPEN,
    IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS,
    IB_PROTECTION_STATUS_COMPLETE,
    IB_PROTECTION_STATUS_NONE,
    IB_RECONCILIATION_STATUS_RECONCILED,
)
from engine.runtime_engine import RuntimeEngine  # noqa: E402


class _QuoteRuntimeEngine(RuntimeEngine):
    """Expose quote enrichment without opening a Runtime database."""

    def apply_quotes(
        self,
        snapshot: IBPositionGroupSnapshot,
        service: object,
    ) -> None:
        self._enrich_ib_position_group_quotes(
            snapshot=snapshot,
            service=service,
        )


class _QuoteService:
    """Synthetic optional quote API used by RuntimeEngine enrichment."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def get_forex_quote_snapshot(self, symbol_names: list[str]) -> dict:
        self.calls.append(list(symbol_names))
        rows = {
            "USDZAR": {
                "bid": 16.4201,
                "ask": 16.4301,
                "timestamp": "2026-07-23T09:30:00+00:00",
                "market_data_type": 3,
            },
            "EURUSD": {
                "bid": 1.14075,
                "ask": 1.14085,
                "timestamp": "2026-07-23T09:30:00+00:00",
                "market_data_type": 1,
            },
        }
        return {
            "complete": all(symbol in rows for symbol in symbol_names),
            "quotes": {
                symbol: dict(rows[symbol]) for symbol in symbol_names if symbol in rows
            },
            "subscribed_symbols": list(symbol_names),
        }


def _leg(
    *,
    uid: str,
    symbol: str,
    side: str,
    volume: float,
    entry_price: float,
    status: str = IB_LEG_STATUS_OPEN,
) -> IBVirtualPositionLeg:
    protection_status = (
        IB_PROTECTION_STATUS_COMPLETE
        if status == IB_LEG_STATUS_OPEN
        else IB_PROTECTION_STATUS_NONE
    )
    return IBVirtualPositionLeg(
        position_uid=uid,
        trade_uid=f"trade-{uid}",
        broker_position_id=f"IB:DUM513747:{symbol}",
        account_id="DUM513747",
        symbol_name=symbol,
        side=side,
        volume=volume,
        entry_price=entry_price,
        opened_utc="2026-07-23T09:00:00+00:00",
        source="MANUAL",
        leg_status=status,
        protection_status=protection_status,
        reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
    )


def _group(symbol: str, legs: list[IBVirtualPositionLeg]) -> IBPositionGroup:
    return IBPositionGroup(
        broker_position_id=f"IB:DUM513747:{symbol}",
        account_id="DUM513747",
        symbol_name=symbol,
        broker_position_present=False,
        broker_side="UNKNOWN",
        broker_volume=0.0,
        broker_signed_volume=0.0,
        broker_entry_price=None,
        broker_position_kind=IB_BROKER_POSITION_KIND_VIRTUAL_FX,
        group_mode=IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS,
        reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
        legs=legs,
    )


def main() -> int:
    zar_sell = _leg(
        uid="zar-sell",
        symbol="USDZAR",
        side="SELL",
        volume=1000.0,
        entry_price=16.41,
    )
    eur_buy = _leg(
        uid="eur-buy",
        symbol="EURUSD",
        side="BUY",
        volume=2000.0,
        entry_price=1.1405,
    )
    eur_sell = _leg(
        uid="eur-sell",
        symbol="EURUSD",
        side="SELL",
        volume=1000.0,
        entry_price=1.141,
    )
    gbp_buy = _leg(
        uid="gbp-buy",
        symbol="GBPUSD",
        side="BUY",
        volume=1000.0,
        entry_price=1.337,
    )
    closed_jpy = _leg(
        uid="jpy-closed",
        symbol="USDJPY",
        side="BUY",
        volume=1000.0,
        entry_price=150.0,
        status=IB_LEG_STATUS_CLOSED,
    )

    zar_group = _group("USDZAR", [zar_sell])
    eur_group = _group("EURUSD", [eur_buy, eur_sell])
    gbp_group = _group("GBPUSD", [gbp_buy])
    closed_group = _group("USDJPY", [closed_jpy])
    snapshot = IBPositionGroupSnapshot(
        captured_utc="2026-07-23T09:30:00+00:00",
        complete=True,
        groups=[zar_group, eur_group, gbp_group, closed_group],
        unmapped_protective_order_ids=[],
    )
    service = _QuoteService()
    engine = object.__new__(_QuoteRuntimeEngine)
    engine.apply_quotes(snapshot, service)

    if service.calls != [["EURUSD", "GBPUSD", "USDZAR"]]:
        raise AssertionError(f"Unexpected quote symbols: {service.calls}")

    if zar_group.current_price != 16.4301:
        raise AssertionError("SELL virtual leg did not use ask")

    if zar_group.current_price_for_side("BUY") != 16.4201:
        raise AssertionError("BUY close-side quote did not use bid")

    if zar_group.current_price_for_side("SELL") != 16.4301:
        raise AssertionError("SELL close-side quote did not use ask")

    if zar_group.pnl_currency != "ZAR" or zar_group.currency != "ZAR":
        raise AssertionError("USDZAR quote currency was not attached")

    if eur_group.current_price != 1.14075:
        raise AssertionError("Net BUY group did not use bid")

    if eur_group.current_price_for_side("BUY") != 1.14075:
        raise AssertionError("EURUSD BUY leg did not use bid")

    if eur_group.current_price_for_side("SELL") != 1.14085:
        raise AssertionError("EURUSD SELL leg did not use ask")

    if gbp_group.current_price is not None:
        raise AssertionError("Missing GBPUSD quote was replaced by zero")

    if closed_group.current_price is not None:
        raise AssertionError("Closed-only group received a quote")

    zar_pnl = (zar_sell.entry_price - 16.4301) * zar_sell.volume
    eur_buy_pnl = (1.14075 - eur_buy.entry_price) * eur_buy.volume
    eur_sell_pnl = (eur_sell.entry_price - 1.14085) * eur_sell.volume

    if not math.isclose(zar_pnl, -20.1, abs_tol=1e-9):
        raise AssertionError("USDZAR SELL PnL differs")

    if not math.isclose(eur_buy_pnl, 0.5, abs_tol=1e-9):
        raise AssertionError("EURUSD BUY PnL differs")

    if not math.isclose(eur_sell_pnl, 0.15, abs_tol=1e-9):
        raise AssertionError("EURUSD SELL PnL differs")

    empty_snapshot = IBPositionGroupSnapshot(
        captured_utc="2026-07-23T09:31:00+00:00",
        complete=True,
        groups=[closed_group],
        unmapped_protective_order_ids=[],
    )
    engine.apply_quotes(empty_snapshot, service)

    if service.calls[-1]:
        raise AssertionError("No-open-leg refresh did not clear subscriptions")

    print("RuntimeEngine IB virtual-leg quote enrichment result")
    print(f"  usdzar_sell_price={zar_group.current_price}")
    print(f"  usdzar_pnl={zar_pnl:.2f} ZAR")
    print(f"  eurusd_buy_price={eur_group.current_price_for_side('BUY')}")
    print(f"  eurusd_sell_price={eur_group.current_price_for_side('SELL')}")
    print("  mixed_side_bid_ask=True")
    print("  missing_quote_is_none=True")
    print("  closed_symbols_unsubscribed=True")
    print("RUNTIME_ENGINE_IB_VIRTUAL_LEG_QUOTE_ENRICHMENT_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
