"""run_workspace_broker_request_accounting_check.py — broker accounting.

Regression перевіряє WSP subscription/reference counters, quote та historical
request accounting, reconnect retries і звільнення subscriptions на локальному
fake RuntimeEngine. Quote snapshots залишаються в одному відкритому bucket,
тому provider не повертає їх як completed algorithm events. Мережа та broker
execution не використовуються; Replay і торгову математику тест не змінює.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_broker_market import (  # noqa: E402
    RuntimeEngineWorkspaceMarketProvider,
    WorkspaceBrokerMarketError,
)


@dataclass(frozen=True, slots=True)
class FakeHistoricalBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class FakeHistoryResult:
    bars: tuple[FakeHistoricalBar, ...]
    request_count: int


class FakeRuntimeEngine:
    def __init__(self) -> None:
        self.quote_calls: list[tuple[str, tuple[str, ...]]] = []
        self.history_calls: list[tuple[str, str, str]] = []
        self.quote_sequence = 0
        self.fail_quote = False
        self.fail_history = False
        self.connected = {"CTRADER": True, "IB": True}

    def validate_workspace_broker_binding(
        self,
        broker: str,
        account_id: str | None,
    ) -> None:
        if not self.connected.get(broker, False):
            raise RuntimeError("broker disconnected")
        if not account_id:
            raise RuntimeError("account required")

    def is_named_broker_connected(self, broker: str) -> bool:
        return bool(self.connected.get(broker, False))

    def get_workspace_forex_quote_snapshot(
        self,
        broker: str,
        symbols: list[str],
    ) -> dict:
        normalized = tuple(sorted(symbols))
        self.quote_calls.append((broker, normalized))
        if self.fail_quote:
            raise RuntimeError("synthetic quote failure")
        self.quote_sequence += 1
        timestamp = datetime(
            2026,
            8,
            3,
            9,
            0,
            tzinfo=UTC,
        ) + timedelta(seconds=self.quote_sequence)
        return {
            "captured_utc": timestamp.isoformat(),
            "complete": True,
            "quotes": {
                symbol: {
                    "symbol_name": symbol,
                    "bid": 1.1000,
                    "ask": 1.1002,
                    "timestamp": timestamp.isoformat(),
                    "volume": 0.0,
                }
                for symbol in normalized
            },
            "subscribed_symbols": list(normalized),
        }

    def download_ctrader_historical_bars(
        self,
        symbol_name: str,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> FakeHistoryResult:
        return self._history_result(
            "CTRADER",
            symbol_name,
            timeframe,
            start_utc,
            end_utc,
        )

    def download_ib_historical_bars(
        self,
        symbol_name: str,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> FakeHistoryResult:
        return self._history_result(
            "IB",
            symbol_name,
            timeframe,
            start_utc,
            end_utc,
        )

    def _history_result(
        self,
        broker: str,
        symbol: str,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> FakeHistoryResult:
        if start_utc >= end_utc:
            raise RuntimeError("invalid synthetic history range")
        self.history_calls.append((broker, symbol, timeframe))
        if self.fail_history:
            raise RuntimeError("synthetic history failure")
        bars = tuple(
            FakeHistoricalBar(
                timestamp=end_utc - timedelta(minutes=(4 - index) * 15),
                open=1.1000 + index * 0.0001,
                high=1.1003 + index * 0.0001,
                low=1.0998 + index * 0.0001,
                close=1.1001 + index * 0.0001,
                volume=100.0 + index,
            )
            for index in range(5)
        )
        return FakeHistoryResult(bars=bars, request_count=3)


def _start(
    provider: RuntimeEngineWorkspaceMarketProvider,
    workspace_uid: str,
    *,
    broker: str = "CTRADER",
    account_id: str = "46368962",
    symbol: str = "EURUSD",
    timeframe: str = "M15",
    warmup_bars: int = 2,
) -> None:
    events = provider.start_workspace(
        workspace_uid=workspace_uid,
        broker=broker,
        account_id=account_id,
        symbol=symbol,
        timeframe=timeframe,
        warmup_bars=warmup_bars,
        spread_limit=0.0002,
    )
    assert len(events) == warmup_bars


def main() -> None:
    """Перевірити counters без dispatch незавершених quote buckets."""
    engine = FakeRuntimeEngine()
    provider = RuntimeEngineWorkspaceMarketProvider(engine)

    _start(provider, "WSP-A")
    _start(provider, "WSP-B", timeframe="M5")
    initial = provider.request_accounting_snapshot()
    assert initial.subscription_acquires == 2
    assert initial.subscription_requests == 1
    assert initial.subscription_deduplicated == 1
    assert initial.active_subscriptions == 1
    assert initial.active_references == 2
    assert initial.references_by_subscription[0][1] == 2
    assert initial.history_downloads == 2
    assert initial.history_broker_requests == 6

    assert provider.poll_workspace("WSP-A") is None
    assert provider.poll_workspace("WSP-B") is None
    after_poll = provider.request_accounting_snapshot()
    assert after_poll.quote_snapshot_requests == 2
    assert engine.quote_calls == [
        ("CTRADER", ("EURUSD",)),
        ("CTRADER", ("EURUSD",)),
    ]

    provider.suspend_workspace("WSP-A")
    assert provider.resume_workspace("WSP-A") == ()
    assert provider.poll_workspace("WSP-A") is None
    after_retry = provider.request_accounting_snapshot()
    assert after_retry.retry_requests == 1
    assert after_retry.quote_snapshot_requests == 3
    assert engine.quote_calls[-1] == ("CTRADER", ("EURUSD",))

    quote_calls_before_first_stop = len(engine.quote_calls)
    provider.stop_workspace("WSP-A")
    after_first_stop = provider.request_accounting_snapshot()
    assert len(engine.quote_calls) == quote_calls_before_first_stop
    assert after_first_stop.subscription_releases == 1
    assert after_first_stop.unsubscription_requests == 0
    assert after_first_stop.active_references == 1

    provider.stop_workspace("WSP-B")
    after_last_stop = provider.request_accounting_snapshot()
    assert engine.quote_calls[-1] == ("CTRADER", ())
    assert after_last_stop.subscription_releases == 2
    assert after_last_stop.unsubscription_requests == 1
    assert after_last_stop.active_subscriptions == 0
    assert after_last_stop.active_references == 0

    _start(
        provider,
        "WSP-IB",
        broker="IB",
        account_id="DUM513747",
        symbol="GBPUSD",
        warmup_bars=0,
    )
    engine.fail_quote = True
    quote_failure_blocked = False
    try:
        provider.poll_workspace("WSP-IB")
    except WorkspaceBrokerMarketError:
        quote_failure_blocked = True
    assert quote_failure_blocked
    engine.fail_quote = False
    provider.stop_workspace("WSP-IB")

    engine.fail_history = True
    history_failure_blocked = False
    try:
        _start(provider, "WSP-HISTORY-FAIL")
    except WorkspaceBrokerMarketError:
        history_failure_blocked = True
    assert history_failure_blocked
    provider.stop_workspace("WSP-HISTORY-FAIL")
    final = provider.request_accounting_snapshot()
    assert final.history_downloads == 3
    assert final.history_broker_requests == 6
    assert final.failed_requests == 2
    assert final.active_subscriptions == 0
    assert final.active_references == 0

    duplicate_workspace_blocked = False
    _start(provider, "WSP-DUP", warmup_bars=0)
    try:
        _start(provider, "WSP-DUP", warmup_bars=0)
    except WorkspaceBrokerMarketError:
        duplicate_workspace_blocked = True
    assert duplicate_workspace_blocked
    provider.stop_workspace("WSP-DUP")

    source = (PROJECT_ROOT / "engine" / "ctrader_adapter.py").read_text(
        encoding="utf-8"
    )
    assert "ProtoOAUnsubscribeSpotsReq" in source
    assert "_position_spot_symbol_ids" in source
    assert "_workspace_spot_symbol_ids" in source
    assert "_sync_owned_spot_subscriptions" in source

    print("Workspace Broker Request Accounting result")
    print("  subscription_deduplication=True")
    print("  same_symbol_cross_timeframe_reference_count=2")
    print("  first_workspace_stop_keeps_subscription=True")
    print("  last_workspace_stop_unsubscribes=True")
    print("  ctrader_position_and_workspace_ownership_isolated=True")
    print("  reconnect_retry_counted=True")
    print("  quote_requests_counted=True")
    print("  history_downloads_counted=True")
    print("  broker_history_chunks_counted=True")
    print("  request_failures_counted=True")
    print("  duplicate_workspace_blocked=True")
    print("  broker_execution_attempted=False")
    print("WORKSPACE_BROKER_REQUEST_ACCOUNTING_CHECK=OK")


if __name__ == "__main__":
    main()
