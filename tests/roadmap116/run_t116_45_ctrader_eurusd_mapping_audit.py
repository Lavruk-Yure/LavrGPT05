"""T116-45 TEST_ONLY — аудит фактичного EURUSD symbolId у production LGE."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from core import ctrader_symbols
from tests.roadmap116.t116_45_ctrader_eurusd_mapping_audit import (
    DEMO_API_ACCOUNT_ID,
    OBSERVED_DEMO_EURUSD_ID,
    audit_current_tree,
    audit_sources,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TABLE_FILE = PROJECT_ROOT / "core" / "ctrader_symbols.py"
ADAPTER_FILE = PROJECT_ROOT / "engine" / "ctrader_adapter.py"


def test_t116_45_ctrader_eurusd_mapping_audit() -> None:
    """Перевірити відповідність DEMO=1 без викликів SDK чи брокера."""
    with (
        patch("socket.socket.connect", side_effect=AssertionError("TCP forbidden")),
        patch("socket.socket.connect_ex", side_effect=AssertionError("TCP forbidden")),
        patch("socket.create_connection", side_effect=AssertionError("TCP forbidden")),
    ):
        audit = audit_current_tree(PROJECT_ROOT)
        assert audit.accepted, audit
        assert ctrader_symbols.get_enabled_symbol_id("EURUSD") == 1
        assert ctrader_symbols.get_enabled_symbol_id(" eurusd ") == 1
        assert ctrader_symbols.get_symbol_name(1) == "EURUSD"
        assert ctrader_symbols.is_symbol_enabled("EURUSD")

        with pytest.raises(ValueError):
            ctrader_symbols.get_enabled_symbol_id("EURUSDt")
        with pytest.raises(KeyError):
            ctrader_symbols.get_enabled_symbol_id("UNKNOWN")

        table_source = TABLE_FILE.read_text(encoding="utf-8-sig")
        adapter_source = ADAPTER_FILE.read_text(encoding="utf-8-sig")
        scenarios_denied = 0

        def denied(table_text: str, adapter_text: str) -> None:
            nonlocal scenarios_denied
            try:
                changed = audit_sources(table_text, adapter_text)
            except (ValueError, SyntaxError):
                scenarios_denied += 1
                return
            assert not changed.accepted
            scenarios_denied += 1

        denied(
            table_source.replace('CTraderSymbol(1, "EURUSD", True)',
                                 'CTraderSymbol(9, "EURUSD", True)'),
            adapter_source,
        )
        denied(
            table_source.replace('CTraderSymbol(1, "EURUSD", True)',
                                 'CTraderSymbol(1, "EURUSD", False)'),
            adapter_source,
        )
        denied(
            table_source.replace('CTraderSymbol(2, "GBPUSD", True)',
                                 'CTraderSymbol(1, "GBPUSD", True)'),
            adapter_source,
        )
        denied(
            table_source.replace('CTraderSymbol(1, "EURUSD", True)',
                                 'CTraderSymbol(1, "GBPUSD", True)'),
            adapter_source,
        )
        denied(
            table_source,
            adapter_source.replace(
                'symbol_id = ctr_symbols.get_enabled_symbol_id(symbol_name)',
                'symbol_id = 2',
                1,
            ),
        )
        denied(
            table_source,
            adapter_source.replace(
                'symbol_id = ctr_symbols.get_enabled_symbol_id(symbol)',
                'symbol_id = 2',
                1,
            ),
        )
        denied(
            table_source,
            adapter_source.replace(
                'symbol_id = ctr_symbols.get_enabled_symbol_id(symbol)',
                'symbol_id = 2',
            ),
        )
        denied(
            table_source,
            adapter_source.replace('request.symbolId = symbol_id',
                                   'request.symbolId = 1', 1),
        )
        denied(
            table_source,
            adapter_source.replace('from core import ctrader_symbols as ctr_symbols',
                                   'from core import symbols as ctr_symbols', 1),
        )
        assert scenarios_denied == 9

    print("T116-45 TEST_ONLY | production EURUSD symbolId audit OFFLINE")
    print(f"demo_api_account_id={DEMO_API_ACCOUNT_ID}")
    print(f"observed_real_eurusd_symbol_id={OBSERVED_DEMO_EURUSD_ID}")
    print(f"production_eurusd_symbol_id={audit.table_id}")
    print("production_symbol_source=CORE_CTRADER_SYMBOLS_STATIC")
    print("history_order_quotes_mapping=VERIFIED_STATIC_AST")
    print("spot_and_position_reverse_lookup=VERIFIED_STATIC_AST")
    print(f"negative_scenarios_denied={scenarios_denied}")
    print("other_accounts_and_symbols=NOT_VERIFIED")
    print("sdk_client_constructor=NOT_CALLED")
    print("external_tcp=BLOCKED")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("network_launch_authorized=NO")
    print("T116-45=GREEN_OFFLINE_PRODUCTION_SYMBOL_ID_AUDIT")
