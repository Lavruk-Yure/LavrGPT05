"""Deterministic check for the IB streaming Forex quote cache."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ibapi.client import EClient  # noqa: E402

from engine.ib_adapter import IBAdapter  # noqa: E402


class _QuoteClient(EClient):
    """Synthetic EClient surface used by IBAdapter quote subscriptions."""

    def __init__(
        self,
        adapter: "_SyntheticIBAdapter",
        wrapper: object,
    ) -> None:
        super().__init__(wrapper)
        self.adapter = adapter
        self.market_data_type_calls: list[int] = []
        self.market_data_requests: list[tuple[int, str]] = []
        self.cancelled_request_ids: list[int] = []

    def reqMarketDataType(self, market_data_type: int) -> None:  # noqa: N802
        self.market_data_type_calls.append(int(market_data_type))

    def reqMktData(  # noqa: N802
        self,
        req_id: int,
        contract,
        generic_tick_list: str,
        snapshot: bool,
        regulatory_snapshot: bool,
        market_data_options: list,
    ) -> None:
        del generic_tick_list
        del snapshot
        del regulatory_snapshot
        del market_data_options

        symbol = f"{contract.symbol}{contract.currency}".upper()
        self.market_data_requests.append((int(req_id), symbol))

        if symbol == "USDZAR":
            self.adapter.emit_market_data_type(req_id, 3)
            self.adapter.emit_tick(req_id, 66, 16.4201)
            self.adapter.emit_tick(req_id, 67, 16.4301)

        if symbol == "EURUSD":
            self.adapter.emit_market_data_type(req_id, 1)
            self.adapter.emit_tick(req_id, 1, 1.14075)
            self.adapter.emit_tick(req_id, 2, 1.14085)

    def cancelMktData(self, req_id: int) -> None:  # noqa: N802
        self.cancelled_request_ids.append(int(req_id))


class _SyntheticIBAdapter(IBAdapter):
    """Connected adapter with a deterministic market-data client."""

    def __init__(self) -> None:
        super().__init__(
            host="127.0.0.1",
            port=7497,
            client_id=1,
            logger=logging.getLogger(__name__),
        )
        self._connected = True
        self.test_client = _QuoteClient(self, self._wrapper)
        self._client = self.test_client

    def emit_tick(self, req_id: int, tick_type: int, price: float) -> None:
        self._wrapper.tickPrice(req_id, tick_type, price, None)

    def emit_market_data_type(
        self,
        req_id: int,
        market_data_type: int,
    ) -> None:
        self._wrapper.marketDataType(req_id, market_data_type)


def main() -> int:
    adapter = _SyntheticIBAdapter()

    first = adapter.get_forex_quote_snapshot(
        ["USDZAR", "EUR.USD", "unsupported"],
        wait_timeout=0.0,
    )
    first_quotes = first["quotes"]

    if not first["complete"]:
        raise AssertionError("Initial quote snapshot is incomplete")

    if first_quotes["USDZAR"]["bid"] != 16.4201:
        raise AssertionError("USDZAR delayed bid differs")

    if first_quotes["USDZAR"]["ask"] != 16.4301:
        raise AssertionError("USDZAR delayed ask differs")

    if first_quotes["USDZAR"]["market_data_type"] != 3:
        raise AssertionError("USDZAR delayed market-data type was not retained")

    if first_quotes["EURUSD"]["bid"] != 1.14075:
        raise AssertionError("EURUSD live bid differs")

    if first_quotes["EURUSD"]["ask"] != 1.14085:
        raise AssertionError("EURUSD live ask differs")

    if adapter.test_client.market_data_type_calls != [3]:
        raise AssertionError("Delayed market-data mode was not requested once")

    first_request_count = len(adapter.test_client.market_data_requests)
    repeated = adapter.get_forex_quote_snapshot(
        ["EURUSD", "USDZAR"],
        wait_timeout=0.0,
    )

    if len(adapter.test_client.market_data_requests) != first_request_count:
        raise AssertionError("Repeated refresh duplicated quote subscriptions")

    if not repeated["complete"]:
        raise AssertionError("Repeated cached quote snapshot is incomplete")

    partial = adapter.get_forex_quote_snapshot(
        ["USDZAR", "GBPUSD"],
        wait_timeout=0.0,
    )
    gbp_quote = partial["quotes"]["GBPUSD"]

    if partial["complete"]:
        raise AssertionError("Missing GBPUSD ticks were reported as complete")

    if gbp_quote["bid"] is not None or gbp_quote["ask"] is not None:
        raise AssertionError("Missing GBPUSD quote was replaced by a number")

    cancelled_before_empty = list(adapter.test_client.cancelled_request_ids)
    empty = adapter.get_forex_quote_snapshot([], wait_timeout=0.0)

    if not empty["complete"]:
        raise AssertionError("Empty subscription set must be complete")

    if empty["subscribed_symbols"]:
        raise AssertionError("Closed symbol subscriptions remained active")

    cancelled_after_empty = adapter.test_client.cancelled_request_ids

    if len(cancelled_after_empty) <= len(cancelled_before_empty):
        raise AssertionError("Final active subscriptions were not cancelled")

    print("IB Forex quote cache result")
    print(f"  delayed_bid={first_quotes['USDZAR']['bid']}")
    print(f"  delayed_ask={first_quotes['USDZAR']['ask']}")
    print(f"  live_bid={first_quotes['EURUSD']['bid']}")
    print(f"  live_ask={first_quotes['EURUSD']['ask']}")
    print("  duplicate_subscriptions=False")
    print("  missing_quote_is_none=True")
    print("  stale_subscriptions_cancelled=True")
    print("IB_FOREX_QUOTE_CACHE_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
