"""T116-17 TEST_ONLY — походження Bid/Ask і нульового спреду cTrader.

Виконує справжній метод обробки ProtoOASpotEvent і штатний WSP provider.
Усі дані синтетичні. Жодних брокерських підключень або ордерів.
"""

from __future__ import annotations

import ast
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
ADAPTER_FILE = ROOT / "engine" / "ctrader_adapter.py"


class OfflineSpotSession:
    """Мінімальний локальний кеш для реального cTrader callback."""

    def __init__(self, scalar_reader: Callable[..., object]) -> None:
        self.config = SimpleNamespace(ctid_trader_account_id=777)
        self._spot_prices: dict[int, dict[str, float | int | None]] = {}
        self._spot_event = Event()
        self._optional_proto_scalar = scalar_reader

    @staticmethod
    def is_session_alive() -> bool:
        return True

    def cached_quote(self) -> dict[str, float | int | None]:
        return dict(self._spot_prices.get(55) or {})


class OfflineSymbolCatalog:
    """Одна відома тестова назва символу без broker API."""

    @staticmethod
    def get_symbol_name(symbol_id: int) -> str:
        if symbol_id != 55:
            raise KeyError(symbol_id)
        return "EURUSD"


class OfflineRuntime:
    """Передає локальний кеш у справжній WSP provider."""

    def __init__(self, session: OfflineSpotSession) -> None:
        self.session = session
        self.local_snapshot_calls = 0

    @staticmethod
    def validate_workspace_broker_binding(
        broker_name: str, account_id: str | None
    ) -> None:
        assert (broker_name, account_id) == ("CTRADER", "TEST_ONLY_DEMO")

    def get_workspace_forex_quote_snapshot(
        self, broker_name: str, symbol_names: list[str]
    ) -> dict[str, object]:
        assert broker_name == "CTRADER"
        assert symbol_names == ["EURUSD"]
        self.local_snapshot_calls += 1
        quote = self.session.cached_quote()
        raw_timestamp = quote.get("timestamp")
        quote_time = (
            datetime.fromtimestamp(float(raw_timestamp) / 1000.0, tz=UTC).isoformat()
            if raw_timestamp is not None
            else None
        )
        return {
            "captured_utc": "2026-11-23T13:15:02+00:00",
            "complete": quote.get("bid") is not None and quote.get("ask") is not None,
            "quotes": {
                "EURUSD": {
                    "timestamp": quote_time,
                    "bid": quote.get("bid"),
                    "ask": quote.get("ask"),
                    "volume": 0.0,
                }
            },
        }


def spot_payload(
    moment: datetime, *, bid: int | None = None, ask: int | None = None
) -> SimpleNamespace:
    """Зімітувати protobuf field presence, зокрема неповний SpotEvent."""
    present = {"timestamp"}
    if bid is not None:
        present.add("bid")
    if ask is not None:
        present.add("ask")
    return SimpleNamespace(
        ctidTraderAccountId=777,
        symbolId=55,
        timestamp=int(moment.timestamp() * 1000),
        bid=bid,
        ask=ask,
        HasField=lambda field_name: field_name in present,
    )


def load_actual_ctrader_method(
    name: str, globals_map: dict[str, Any]
) -> Callable[..., Any]:
    """Завантажити тільки один production-метод без мережевих імпортів."""
    tree = ast.parse(ADAPTER_FILE.read_text(encoding="utf-8"))
    adapter_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "CTraderAdapter"
    )
    method = next(
        node
        for node in adapter_class.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )
    method.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    namespace: dict[str, Any] = dict(globals_map)
    exec(compile(module, str(ADAPTER_FILE), "exec"), namespace)
    return namespace[name]


def test_t116_17_ctrader_live_bid_ask_provenance() -> None:
    """Відтворити нульовий spread із часткових cTrader SpotEvent."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    os.environ["LGE_TEST_ONLY_BROKER_LIVE_TRACE"] = "0"

    from core import workspace_broker_live_trace as trace
    from core.workspace_broker_market import RuntimeEngineWorkspaceMarketProvider

    reader = load_actual_ctrader_method("_optional_proto_scalar", {})
    callback = load_actual_ctrader_method(
        "_on_spot_event",
        {"ctr_symbols": OfflineSymbolCatalog, "broker_live_trace": trace},
    )
    session = OfflineSpotSession(reader)
    runtime = OfflineRuntime(session)
    provider = RuntimeEngineWorkspaceMarketProvider(runtime)
    uid = "T116-17-OFFLINE"
    assert (
        provider.start_workspace(
            workspace_uid=uid,
            broker="CTRADER",
            account_id="TEST_ONLY_DEMO",
            symbol="EURUSD",
            timeframe="M15",
            warmup_bars=0,
            spread_limit=0.00020,
        )
        == ()
    )

    # Початковий неповний bid, ask ще відсутній.
    callback(
        session,
        spot_payload(datetime(2026, 11, 23, 13, 0, 2, tzinfo=UTC), bid=109375),
    )
    assert session.cached_quote().get("ask") is None
    assert provider.poll_workspace(uid) is None

    # Наступний пакет містить тільки ask: формується нормальна двостороння котирування.
    callback(
        session,
        spot_payload(datetime(2026, 11, 23, 13, 0, 5, tzinfo=UTC), ask=109376),
    )
    quote = session.cached_quote()
    assert abs(float(quote["ask"]) - float(quote["bid"]) - 0.00001) < 1e-10
    assert provider.poll_workspace(uid) is None

    # Пакет містить лише bid, а попередній ask залишається в кеші.
    callback(
        session,
        spot_payload(datetime(2026, 11, 23, 13, 0, 10, tzinfo=UTC), bid=109376),
    )
    quote = session.cached_quote()
    assert quote["bid"] == quote["ask"]
    assert provider.poll_workspace(uid) is None

    # На відкритті наступного bucket штатний агрегатор видає завершений M15.
    callback(
        session,
        spot_payload(
            datetime(2026, 11, 23, 13, 15, 1, tzinfo=UTC),
            bid=109370,
            ask=109371,
        ),
    )
    completed = provider.poll_workspace(uid)
    assert completed is not None
    assert completed.timestamp == datetime(2026, 11, 23, 13, 0, tzinfo=UTC)
    assert completed.bid == completed.ask
    assert completed.spread == 0.0
    assert runtime.local_snapshot_calls == 4
    provider.stop_workspace(uid)

    print("T116-17 TEST_ONLY | cTrader SpotEvent -> WSP completed M15")
    print("spot_callback=PRODUCTION_METHOD_EXECUTED")
    print("missing_ask_initially=REJECTED_BY_PROVIDER")
    print("partial_bid_ask_cache_merge=CONFIRMED")
    print("equal_bid_ask_provider_acceptance=CONFIRMED")
    print("completed_m15_zero_spread=REPRODUCED")
    print("actual_2026_11_23_1300_quote_origin=NOT_PROVEN")
    print("local_snapshot_calls=4")
    print("real_broker_requests=0")
    print("real_config_disk_writes=0")
    print("production_changes=0")
    print("T116-17=GREEN_OFFLINE_BID_ASK_PROVENANCE_DIAGNOSTIC")


if __name__ == "__main__":
    test_t116_17_ctrader_live_bid_ask_provenance()
