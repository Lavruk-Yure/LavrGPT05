"""T116-49 TEST_ONLY — фактичний шлях SpotEvent до Workspace без SDK і мережі."""

from __future__ import annotations

import ast
import copy
import threading
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from core import ctrader_symbols

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_FILE = PROJECT_ROOT / "engine" / "ctrader_adapter.py"
MANAGER_FILE = PROJECT_ROOT / "engine" / "ctrader_session_manager.py"
SERVICE_FILE = PROJECT_ROOT / "engine" / "services" / "ctrader_runtime_service.py"
ENGINE_FILE = PROJECT_ROOT / "engine" / "runtime_engine.py"
DEMO_ACCOUNT_ID = 46368962
EURUSD_SYMBOL_ID = 1


class FakeSpot:
    """Синтетичний protobuf-подібний SpotEvent із явною присутністю полів."""

    def __init__(
        self,
        *,
        account_id: int = DEMO_ACCOUNT_ID,
        symbol_id: int = EURUSD_SYMBOL_ID,
        bid: int | None = None,
        ask: int | None = None,
        timestamp: int | None = None,
    ) -> None:
        self.ctidTraderAccountId = account_id
        self.symbolId = symbol_id
        self._present: set[str] = set()
        for field_name, value in (
            ("bid", bid),
            ("ask", ask),
            ("timestamp", timestamp),
        ):
            if value is not None:
                setattr(self, field_name, value)
                self._present.add(field_name)

    # noinspection PyPep8Naming
    def HasField(self, field_name: str) -> bool:
        return field_name in self._present


def isolated_production_class(
    path: Path,
    original_class: str,
    methods: tuple[str, ...],
    globals_for_methods: dict[str, object],
) -> type[Any]:
    """Виконати незмінені методи з AST production без імпорту SDK/GUI."""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    definitions = (
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == original_class
    )
    owner = next(definitions, None)
    if owner is None:
        raise AssertionError(f"Відсутній production class: {original_class}")
    selected = [
        copy.deepcopy(node)
        for node in owner.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in methods
    ]
    if {node.name for node in selected} != set(methods):
        raise AssertionError(f"Production API змінився: {original_class}")
    new_class = ast.ClassDef(
        name=f"TestOnly{original_class}",
        bases=[],
        keywords=[],
        body=selected,
        decorator_list=[],
        type_params=[],
    )
    module = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__",
                names=[ast.alias(name="annotations")],
                level=0,
            ),
            new_class,
        ],
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    namespace: dict[str, object] = dict(globals_for_methods)
    exec(compile(module, str(path), "exec"), namespace)
    class_type = namespace.get(new_class.name)
    if not isinstance(class_type, type):
        raise AssertionError(f"Не вдалося створити клас: {original_class}")
    return class_type


def build_isolated_chain() -> (
    tuple[Any, Any, Any, list[dict[str, object]], list[set[int]]]
):
    """Зібрати справжні методи чотирьох production-класів без конструкторів."""
    traces: list[dict[str, object]] = []
    requested: list[set[int]] = []
    trace_sink = SimpleNamespace(
        record_ctrader_spot_callback=lambda **values: traces.append(values),
    )
    adapter_type = isolated_production_class(
        ADAPTER_FILE,
        "CTraderAdapter",
        (
            "_on_spot_event",
            "_optional_proto_scalar",
            "_spot_timestamp_iso",
            "get_forex_quote_snapshot",
        ),
        {
            "ctr_symbols": ctrader_symbols,
            "broker_live_trace": trace_sink,
            "datetime": datetime,
            "UTC": UTC,
            "CTRADER_SPOT_TIMEOUT_SECONDS": 2.0,
        },
    )
    adapter = adapter_type()
    adapter.config = SimpleNamespace(ctid_trader_account_id=DEMO_ACCOUNT_ID)
    adapter._spot_event = threading.Event()
    adapter._spot_prices = {}
    adapter._workspace_spot_symbol_ids = set()
    adapter.is_session_alive = lambda: True
    adapter.is_connected = lambda: True
    adapter._sync_owned_spot_subscriptions = lambda: requested.append(
        set(getattr(adapter, "_workspace_spot_symbol_ids"))
    )

    manager_type = isolated_production_class(
        MANAGER_FILE,
        "CTraderSessionManager",
        ("get_forex_quote_snapshot",),
        {},
    )
    manager = manager_type()
    manager.get_active_adapter = lambda: adapter

    service_type = isolated_production_class(
        SERVICE_FILE,
        "CTraderRuntimeService",
        ("get_forex_quote_snapshot",),
        {},
    )
    service = service_type()
    service._session_manager = manager

    engine_type = isolated_production_class(
        ENGINE_FILE,
        "RuntimeEngine",
        ("get_workspace_forex_quote_snapshot",),
        {},
    )
    engine = engine_type()
    engine.ctrader_runtime_service = service
    engine.ib_runtime_service = None
    engine.is_named_broker_connected = lambda broker: broker == "CTRADER"
    return adapter, manager, engine, traces, requested


def test_t116_49_ctrader_spot_workspace_integration() -> None:
    """Перевірити production-маршрут на completed SpotEvent без look-ahead."""
    denied = 0
    timestamp_ms = 1795786258279
    expected_timestamp = datetime.fromtimestamp(
        timestamp_ms / 1000,
        tz=UTC,
    ).isoformat()
    with (
        patch("socket.socket.connect", side_effect=AssertionError("TCP forbidden")),
        patch("socket.socket.connect_ex", side_effect=AssertionError("TCP forbidden")),
        patch("socket.create_connection", side_effect=AssertionError("TCP forbidden")),
    ):
        adapter, manager, engine, traces, requested = build_isolated_chain()
        assert ctrader_symbols.get_enabled_symbol_id("EURUSD") == EURUSD_SYMBOL_ID

        def snapshot(*symbols: str) -> dict[str, Any]:
            return engine.get_workspace_forex_quote_snapshot(
                "CTRADER",
                list(symbols),
            )

        initial = snapshot(" EUR/USD ", "EURUSD")
        assert initial["complete"] is False
        assert list(initial["quotes"]) == ["EURUSD"]
        assert initial["quotes"]["EURUSD"]["bid"] is None
        assert requested == [{EURUSD_SYMBOL_ID}]

        # Лише Bid: до наступного SpotEvent Ask іще невідомий.
        adapter._on_spot_event(FakeSpot(bid=109441, timestamp=timestamp_ms))
        partial = snapshot("EURUSD")
        assert partial["complete"] is False
        assert partial["quotes"]["EURUSD"]["bid"] == pytest.approx(1.09441)
        assert partial["quotes"]["EURUSD"]["ask"] is None
        assert partial["quotes"]["EURUSD"]["timestamp"] == expected_timestamp

        # Лише Ask: попередній Bid має залишитися, без підглядання наперед.
        adapter._on_spot_event(FakeSpot(ask=109442, timestamp=timestamp_ms + 1000))
        complete = snapshot("eurusd")
        row = complete["quotes"]["EURUSD"]
        assert complete["complete"] is True
        assert row["bid"] == pytest.approx(1.09441)
        assert row["ask"] == pytest.approx(1.09442)
        assert (
            row["timestamp"]
            == datetime.fromtimestamp(
                (timestamp_ms + 1000) / 1000,
                tz=UTC,
            ).isoformat()
        )
        assert row["volume"] == 0.0
        assert complete["subscribed_symbols"] == ["EURUSD"]

        # Уже досліджений нульовий спред: шлях LGE має передати значення без зміни.
        adapter._on_spot_event(FakeSpot(ask=109441, timestamp=timestamp_ms + 2000))
        zero = snapshot("EURUSD")
        assert zero["complete"] is True
        assert zero["quotes"]["EURUSD"]["bid"] == zero["quotes"]["EURUSD"]["ask"]

        before = dict(adapter._spot_prices[EURUSD_SYMBOL_ID])
        for event in (
            FakeSpot(account_id=DEMO_ACCOUNT_ID + 1, bid=123456),
            FakeSpot(symbol_id=0, bid=123456),
            FakeSpot(),
        ):
            adapter._on_spot_event(event)
            assert adapter._spot_prices[EURUSD_SYMBOL_ID] == before
            denied += 1

        adapter._on_spot_event(FakeSpot(symbol_id=2, bid=111111))
        assert snapshot("EURUSD")["quotes"]["EURUSD"]["bid"] == pytest.approx(1.09441)
        denied += 1

        adapter._on_spot_event(FakeSpot(bid=0, ask=0))
        assert adapter._spot_prices[EURUSD_SYMBOL_ID] == before
        denied += 1

        ignored = snapshot("EURUSDt", "UNKNOWN")
        assert ignored["complete"] is False
        assert ignored["quotes"] == {}
        assert ignored["subscribed_symbols"] == []
        denied += 2

        engine.is_named_broker_connected = lambda broker: False
        with pytest.raises(RuntimeError, match="not connected"):
            snapshot("EURUSD")
        denied += 1
        engine.is_named_broker_connected = lambda broker: broker == "CTRADER"

        engine.ctrader_runtime_service = None
        with pytest.raises(RuntimeError, match="not set"):
            snapshot("EURUSD")
        denied += 1
        engine.ctrader_runtime_service = manager

        manager.get_active_adapter = lambda: None
        empty = manager.get_forex_quote_snapshot(["EURUSD"])
        assert empty["complete"] is False
        assert empty["quotes"] == {}
        denied += 1

        assert len(traces) >= 3
        assert traces[0]["symbol"] == "EURUSD"
        assert traces[0]["bid"] == pytest.approx(1.09441)
        assert traces[1]["ask"] == pytest.approx(1.09442)
        assert all(record.get("volume") is None for record in traces)
        assert denied == 10

    print("T116-49 TEST_ONLY | production cTrader SpotEvent → Workspace OFFLINE")
    print("demo_api_account_id=46368962")
    print("eurusd_symbol_id=1")
    print("production_methods=EXECUTED_FROM_CURRENT_AST")
    print("route=SPOT_CACHE_SESSION_MANAGER_RUNTIME_SERVICE_RUNTIME_ENGINE")
    print("partial_bid_ask=VERIFIED_NO_LOOKAHEAD")
    print("timestamp=VERIFIED_UTC")
    print("zero_spread=PASSTHROUGH_PREVIOUSLY_ACCEPTED")
    print(f"negative_scenarios_denied={denied}")
    print("sdk_client_constructor=NOT_CALLED")
    print("external_tcp=BLOCKED")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("network_launch_authorized=NO")
    print("T116-49=GREEN_OFFLINE_SPOT_TO_WORKSPACE_CONTRACT")
