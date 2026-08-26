# -*- coding: utf-8 -*-
"""RuntimeEngine check for read-only WSP broker binding and quote dispatch."""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.runtime_account_state import RuntimeAccountState  # noqa: E402
from engine.runtime_broker_health import RuntimeBrokerHealth  # noqa: E402
from engine.runtime_engine import RuntimeEngine  # noqa: E402


class FakeCTraderService:
    def __init__(self) -> None:
        self.health = RuntimeBrokerHealth()
        self.health.set_connected()
        self.account_state = RuntimeAccountState(
            account_id="46368962",
            broker_name="CTRADER",
        )
        self.quote_calls: list[tuple[str, ...]] = []

    def get_broker_health(self) -> RuntimeBrokerHealth:
        return self.health

    def get_account_state(self) -> RuntimeAccountState:
        return self.account_state

    def get_forex_quote_snapshot(self, symbol_names: list[str]) -> dict:
        symbols = tuple(symbol_names)
        self.quote_calls.append(symbols)
        return {
            "captured_utc": "2026-07-28T09:15:00+00:00",
            "complete": True,
            "quotes": {
                symbol: {
                    "symbol_name": symbol,
                    "bid": 1.17074,
                    "ask": 1.17086,
                    "timestamp": "2026-07-28T09:15:00+00:00",
                }
                for symbol in symbols
            },
            "subscribed_symbols": list(symbols),
        }


class FakeIBService:
    def __init__(self) -> None:
        self.health = RuntimeBrokerHealth()
        self.health.set_connected()
        self.quote_calls: list[tuple[str, ...]] = []

    def get_broker_health(self) -> RuntimeBrokerHealth:
        return self.health

    @staticmethod
    def get_managed_accounts() -> list[str]:
        return ["DUM513747"]

    def get_forex_quote_snapshot(self, symbol_names: list[str]) -> dict:
        symbols = tuple(symbol_names)
        self.quote_calls.append(symbols)
        return {
            "captured_utc": "2026-07-28T09:15:00+00:00",
            "complete": True,
            "quotes": {
                symbol: {
                    "symbol_name": symbol,
                    "bid": 1.35005,
                    "ask": 1.35015,
                    "timestamp": "2026-07-28T09:15:00+00:00",
                }
                for symbol in symbols
            },
            "subscribed_symbols": list(symbols),
        }


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        engine = RuntimeEngine(db_path=str(Path(temp_dir) / "runtime.db"))
        try:
            ctrader = FakeCTraderService()
            ib = FakeIBService()
            test_engine: Any = engine
            test_engine.ctrader_runtime_service = ctrader
            test_engine.ib_runtime_service = ib

            engine.validate_workspace_broker_binding("CTRADER", "46368962")
            engine.validate_workspace_broker_binding("IB", "DUM513747")

            ctrader_mismatch_blocked = False
            try:
                engine.validate_workspace_broker_binding("CTRADER", "999")
            except RuntimeError:
                ctrader_mismatch_blocked = True
            assert ctrader_mismatch_blocked

            ib_mismatch_blocked = False
            try:
                engine.validate_workspace_broker_binding("IB", "DU000000")
            except RuntimeError:
                ib_mismatch_blocked = True
            assert ib_mismatch_blocked

            ctrader_snapshot = engine.get_workspace_forex_quote_snapshot(
                "CTRADER",
                ["EURUSD"],
            )
            ib_snapshot = engine.get_workspace_forex_quote_snapshot(
                "IB",
                ["GBPUSD"],
            )
            assert ctrader_snapshot["quotes"]["EURUSD"]["bid"] == 1.17074
            assert ib_snapshot["quotes"]["GBPUSD"]["ask"] == 1.35015
            assert ctrader.quote_calls == [("EURUSD",)]
            assert ib.quote_calls == [("GBPUSD",)]

            unsupported_broker_blocked = False
            try:
                engine.get_workspace_forex_quote_snapshot(
                    "UNKNOWN",
                    ["EURUSD"],
                )
            except ValueError:
                unsupported_broker_blocked = True
            assert unsupported_broker_blocked

            ctrader.health.set_disconnected(error="test")
            disconnected_broker_blocked = False
            try:
                engine.get_workspace_forex_quote_snapshot(
                    "CTRADER",
                    ["EURUSD"],
                )
            except RuntimeError:
                disconnected_broker_blocked = True
            assert disconnected_broker_blocked
        finally:
            engine.connection.close()

    print("RuntimeEngine Workspace Market Data result")
    print("  ctrader_binding_validated=True")
    print("  ib_binding_validated=True")
    print("  ctrader_account_mismatch_blocked=True")
    print("  ib_account_mismatch_blocked=True")
    print("  ctrader_quote_dispatch=True")
    print("  ib_quote_dispatch=True")
    print("  unsupported_broker_blocked=True")
    print("  disconnected_broker_blocked=True")
    print("RUNTIME_ENGINE_WORKSPACE_MARKET_DATA_CHECK=OK")


if __name__ == "__main__":
    main()
