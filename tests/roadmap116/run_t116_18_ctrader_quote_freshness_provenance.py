"""T116-18 TEST_ONLY — свіжість сторін котировки та походження zero spread.

Використовує production cTrader SpotEvent callback, snapshot і WSP provider.
Синтетичні повідомлення; без мережі, торгових ордерів та production-змін.
"""

from __future__ import annotations

import ast
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from typing import Any, Callable, cast

ROOT = Path(__file__).resolve().parents[2]
ADAPTER_FILE = ROOT / "engine" / "ctrader_adapter.py"
SYMBOL_ID = 55
ACCOUNT_ID = 777


class TestSymbolCatalog:
    """Локальний каталог замість запитів до cTrader."""

    @staticmethod
    def get_symbol_name(symbol_id: int) -> str:
        if symbol_id != SYMBOL_ID:
            raise KeyError(symbol_id)
        return "EURUSD"

    @staticmethod
    def get_enabled_symbol_id(symbol: str) -> int:
        if symbol != "EURUSD":
            raise KeyError(symbol)
        return SYMBOL_ID


class TraceRecorder:
    """Перехоплює виклик наявної TEST_ONLY телеметрії без файлового I/O."""

    def __init__(self) -> None:
        self.samples: list[dict[str, object]] = []

    def record_ctrader_spot_callback(self, **fields: object) -> None:
        self.samples.append(dict(fields))


class OfflineSpotSession:
    """Мінімальні поля, потрібні справжнім методам адаптера."""

    def __init__(
        self,
        scalar_reader: Callable[..., object],
        timestamp_converter: Callable[..., str],
    ) -> None:
        self.config = SimpleNamespace(ctid_trader_account_id=ACCOUNT_ID)
        self._spot_prices: dict[int, dict[str, float | int | None]] = {}
        self._spot_event = Event()
        self._workspace_spot_symbol_ids: set[int] = set()
        self._optional_proto_scalar = scalar_reader
        self._spot_timestamp_iso = timestamp_converter
        self.subscription_sync_calls = 0

    @staticmethod
    def is_session_alive() -> bool:
        return True

    @staticmethod
    def is_connected() -> bool:
        return True

    def _sync_owned_spot_subscriptions(self) -> None:
        self.subscription_sync_calls += 1

    def cached_quote(self) -> dict[str, float | int | None]:
        return dict(self._spot_prices.get(SYMBOL_ID) or {})


class OfflineRuntime:
    """Передає штатний cTrader snapshot у production WSP provider."""

    def __init__(
        self,
        session: OfflineSpotSession,
        snapshot_method: Callable[..., dict[str, object]],
    ) -> None:
        self.session = session
        self.snapshot_method = snapshot_method
        self.snapshot_calls = 0

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
        self.snapshot_calls += 1
        return self.snapshot_method(self.session, symbol_names, wait_timeout=0)


def load_adapter_method(name: str, globals_map: dict[str, Any]) -> Callable[..., Any]:
    """Виконати один штатний метод без імпорту мережевих бібліотек."""
    tree = ast.parse(ADAPTER_FILE.read_text(encoding="utf-8"))
    adapter = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "CTraderAdapter"
    )
    method = next(
        node for node in adapter.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )
    method.decorator_list = []
    namespace: dict[str, Any] = dict(globals_map)
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    exec(compile(module, str(ADAPTER_FILE), "exec"), namespace)
    return namespace[name]


def spot_event(
    timestamp: datetime, *, bid: int | None = None, ask: int | None = None
) -> SimpleNamespace:
    """Задати дійсну присутність protobuf-полів на кожній події."""
    present = {"timestamp"}
    if bid is not None:
        present.add("bid")
    if ask is not None:
        present.add("ask")
    return SimpleNamespace(
        ctidTraderAccountId=ACCOUNT_ID,
        symbolId=SYMBOL_ID,
        timestamp=int(timestamp.timestamp() * 1000),
        bid=bid,
        ask=ask,
        HasField=lambda field: field in present,
    )


def test_t116_18_ctrader_quote_freshness_provenance() -> None:
    """Відокремити raw-походження Bid/Ask від merged snapshot."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    os.environ["LGE_TEST_ONLY_BROKER_LIVE_TRACE"] = "0"

    from core.workspace_broker_market import RuntimeEngineWorkspaceMarketProvider

    scalar_reader = load_adapter_method("_optional_proto_scalar", {})
    converter = load_adapter_method(
        "_spot_timestamp_iso", {"datetime": datetime, "UTC": UTC}
    )
    snapshot_method = load_adapter_method(
        "get_forex_quote_snapshot",
        {
            "ctr_symbols": TestSymbolCatalog,
            "CTRADER_SPOT_TIMEOUT_SECONDS": 5.0,
            "datetime": datetime,
            "UTC": UTC,
        },
    )
    recorder = TraceRecorder()
    callback = load_adapter_method(
        "_on_spot_event",
        {"ctr_symbols": TestSymbolCatalog, "broker_live_trace": recorder},
    )
    session = OfflineSpotSession(scalar_reader, converter)
    runtime = OfflineRuntime(session, snapshot_method)
    provider = RuntimeEngineWorkspaceMarketProvider(runtime)
    uid = "T116-18-OFFLINE"
    assert provider.start_workspace(
        workspace_uid=uid,
        broker="CTRADER",
        account_id="TEST_ONLY_DEMO",
        symbol="EURUSD",
        timeframe="M15",
        warmup_bars=0,
        spread_limit=0.00020,
    ) == ()

    t0 = datetime(2026, 11, 23, 13, 0, tzinfo=UTC)
    late = t0 + timedelta(minutes=5)
    rollover = t0 + timedelta(minutes=15, seconds=1)

    # Одночасне оновлення обох сторін — єдина достовірна пара в raw payload.
    callback(session, spot_event(t0, bid=109375, ask=109377))
    start = runtime.get_workspace_forex_quote_snapshot("CTRADER", ["EURUSD"])
    start_row = cast(dict[str, dict[str, object]], start["quotes"])["EURUSD"]
    assert start_row["ask"] > start_row["bid"]
    assert provider.poll_workspace(uid) is None

    # Лише Bid оновився через п'ять хвилин; Ask лишився з t0.
    callback(session, spot_event(late, bid=109377))
    mixed = runtime.get_workspace_forex_quote_snapshot("CTRADER", ["EURUSD"])
    mixed_row = cast(dict[str, dict[str, object]], mixed["quotes"])["EURUSD"]
    assert mixed["complete"] is True
    assert mixed_row["bid"] == mixed_row["ask"]
    assert mixed_row["timestamp"] == late.isoformat()
    assert "bid_timestamp" not in mixed_row
    assert "ask_timestamp" not in mixed_row
    assert "bid_updated_utc" not in session.cached_quote()
    assert "ask_updated_utc" not in session.cached_quote()
    assert provider.poll_workspace(uid) is None

    # Наступний bucket повертає завершений M15 із нульовим спредом.
    callback(session, spot_event(rollover, bid=109370, ask=109371))
    completed = provider.poll_workspace(uid)
    assert completed is not None
    assert completed.timestamp == t0
    assert completed.spread == 0.0
    assert completed.bid == completed.ask
    provider.stop_workspace(uid)

    # Незалежна послідовність: обидві рівні сторони прийшли в ОДНОМУ пакеті.
    raw_equal_session = OfflineSpotSession(scalar_reader, converter)
    raw_equal_recorder = TraceRecorder()
    raw_equal_callback = load_adapter_method(
        "_on_spot_event",
        {
            "ctr_symbols": TestSymbolCatalog,
            "broker_live_trace": raw_equal_recorder,
        },
    )
    raw_equal_callback(raw_equal_session, spot_event(late, bid=109377, ask=109377))
    assert raw_equal_session.cached_quote()["bid"] == mixed_row["bid"]
    assert raw_equal_session.cached_quote()["ask"] == mixed_row["ask"]
    assert raw_equal_recorder.samples[-1] == recorder.samples[1]

    # Фактична raw-присутність сторін відома лише тестовому генератору подій.
    assert abs((late - t0).total_seconds() - 300.0) < 1e-9
    assert session.subscription_sync_calls == 5
    assert runtime.snapshot_calls == 5

    print("T116-18 TEST_ONLY | cTrader raw sides -> merged quote -> WSP M15")
    print("production_spot_callback=EXECUTED")
    print("production_ctrader_snapshot=EXECUTED")
    print("production_wsp_provider=EXECUTED")
    print("raw_bid_ask_side_times=ONLY_IN_TEST_EVENT_LEDGER")
    print("mixed_side_age_seconds=300")
    print("production_side_timestamps=NOT_RECORDED")
    print("single_quote_timestamp_masks_stale_ask=CONFIRMED")
    print("zero_spread_from_partial_merge=CONFIRMED")
    print("zero_spread_from_raw_equal_event=CONFIRMED")
    print("existing_trace_cannot_disambiguate_origins=CONFIRMED")
    print("completed_m15_zero_spread=REPRODUCED")
    print("actual_2026_11_23_1300_quote_origin=NOT_PROVEN")
    print("real_broker_requests=0")
    print("real_database_writes=0")
    print("real_config_disk_writes=0")
    print("production_changes=0")
    print("T116-18=GREEN_OFFLINE_QUOTE_FRESHNESS_PROVENANCE_DIAGNOSTIC")


if __name__ == "__main__":
    test_t116_18_ctrader_quote_freshness_provenance()
