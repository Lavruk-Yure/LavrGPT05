# -*- coding: utf-8 -*-
"""Runtime check for the canonical WSP market event model."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import WORKSPACE_DATA_MODE_REPLAY  # noqa: E402
from core.workspace_market_event import (  # noqa: E402
    WorkspaceMarketBar,
    WorkspaceMarketEvent,
    WorkspaceQuote,
)


def main() -> None:
    timestamp = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)
    bar = WorkspaceMarketBar(
        timestamp=timestamp,
        open=1.17000,
        high=1.17120,
        low=1.16940,
        close=1.17080,
        volume=125.0,
        bid=1.17074,
        ask=1.17086,
    )
    event = WorkspaceMarketEvent.from_bar(
        bar=bar,
        broker="ib",
        symbol="eurusd",
        timeframe="m15",
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
    )
    quote = WorkspaceQuote(
        timestamp=datetime(2026, 7, 23, 12, 0, 1, tzinfo=UTC),
        bid=1.17075,
        ask=1.17087,
        volume=3.0,
    )

    assert event.timestamp == timestamp
    assert event.broker == "IB"
    assert event.symbol == "EURUSD"
    assert event.timeframe == "M15"
    assert abs(event.spread - 0.00012) < 1e-12
    assert event.close == bar.close
    assert event.source_mode == WORKSPACE_DATA_MODE_REPLAY
    assert quote.timestamp.tzinfo is not None
    assert abs(quote.ask - quote.bid - 0.00012) < 1e-12

    invalid_spread_blocked = False
    try:
        WorkspaceMarketEvent(
            timestamp=timestamp,
            broker="IB",
            symbol="EURUSD",
            timeframe="M15",
            bid=1.17074,
            ask=1.17086,
            spread=0.00020,
            open=1.17000,
            high=1.17120,
            low=1.16940,
            close=1.17080,
            volume=125.0,
            source_mode=WORKSPACE_DATA_MODE_REPLAY,
        )
    except ValueError:
        invalid_spread_blocked = True
    assert invalid_spread_blocked

    print("Algorithm Workspace Market Event result")
    print(f"  timestamp={event.timestamp.isoformat()}")
    print(f"  broker={event.broker}")
    print(f"  symbol={event.symbol}")
    print(f"  timeframe={event.timeframe}")
    print(f"  spread={event.spread:.6f}")
    print(f"  source_mode={event.source_mode}")
    print(f"  invalid_spread_blocked={invalid_spread_blocked}")
    print("ALGORITHM_WORKSPACE_MARKET_EVENT_CHECK=OK")


if __name__ == "__main__":
    main()
