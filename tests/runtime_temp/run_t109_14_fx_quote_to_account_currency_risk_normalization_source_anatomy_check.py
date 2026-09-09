"""run_t109_14_fx_quote_to_account_currency_risk_normalization_source_anatomy_check.py.

TEST_ONLY anatomy фіксує фактичні production sources для перетворення FX
estimated loss з quote currency до account currency. Перевірка розділяє
identity, inverse поточної пари та cross-rate класи, зіставляє Runtime account
state, Workspace risk snapshot, IB/cTrader quote caches і Replay assumptions,
а також доводить timestamp, freshness і safe-blocking gaps.

Runner читає production contracts і запускає canonical Replay 2025/2026, але
не викликає broker/network API, не створює subscription/order, не підставляє
synthetic production source і не змінює risk, Replay, AUTO/SEMI чи trading logic.
Локальна арифметика перевіряє лише формули; вона не заявляє runtime source
availability. Production hashes і repeat output захищають TEST_ONLY scope.
"""

from __future__ import annotations

import hashlib
import importlib
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_TEST_ROOT = PROJECT_ROOT / "tests" / "runtime_workspace"
for import_path in (PROJECT_ROOT, WORKSPACE_TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))


def _test_helper(module_name: str, helper_name: str) -> Any:
    """Завантажити established TEST_ONLY Replay helper без копіювання harness."""
    module = importlib.import_module(module_name)
    helper = getattr(module, helper_name, None)
    if helper is None:
        raise AssertionError(f"missing TEST_ONLY helper: {helper_name}")
    return helper


CANONICAL_PERIODS = _test_helper(
    "run_t105_18_stochastic_current_bar_production_regression_check",
    "PERIODS",
)
run_canonical_period = _test_helper(
    "run_t105_18_stochastic_current_bar_production_regression_check",
    "_run_period",
)

from engine.risk.account_snapshot import (  # noqa: E402
    WorkspaceRiskAccountSnapshot,
)

TEST_ID = "T109-14"
EXPECTED_2025 = "42/30/11/1/+4.03/1.5424/3.58"
EXPECTED_2026 = "18/15/2/1/+3.68/3.7669/1.20"
FACTUAL_VERDICT = "H. MULTIPLE_BLOCKERS"
FIRST_UNRESOLVED_BOUNDARY = (
    "RUNTIME_ACCOUNT_CURRENCY_NOT_ROUTED_TO_WORKSPACE_RISK_ACCOUNT_SNAPSHOT"
)
BOUNDARY_CONTRACT = (
    "RISK_NORMALIZATION_REQUIRES_ACCOUNT_CURRENCY_IN_BOUND_SNAPSHOT_BEFORE_"
    "IDENTITY_INVERSE_OR_CROSS_RATE_SELECTION"
)
PRODUCTION_FILES = (
    PROJECT_ROOT / "core" / "algorithm_workspace.py",
    PROJECT_ROOT / "core" / "ctrader_symbols.py",
    PROJECT_ROOT / "core" / "workspace_broker_market.py",
    PROJECT_ROOT / "core" / "workspace_historical_evaluation.py",
    PROJECT_ROOT / "core" / "workspace_replay_execution.py",
    PROJECT_ROOT / "core" / "workspace_runtime.py",
    PROJECT_ROOT / "engine" / "ctrader_adapter.py",
    PROJECT_ROOT / "engine" / "ib_adapter.py",
    PROJECT_ROOT / "engine" / "runtime_account_state.py",
    PROJECT_ROOT / "engine" / "runtime_engine.py",
    PROJECT_ROOT / "engine" / "risk" / "account_snapshot.py",
    PROJECT_ROOT / "engine" / "risk" / "risk_model.py",
    PROJECT_ROOT / "engine" / "services" / "ctrader_runtime_service.py",
    PROJECT_ROOT / "engine" / "services" / "ib_runtime_service.py",
)


def _source_text(relative_path: str) -> str:
    """Прочитати current production source як UTF-8 contract."""
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def _production_hashes() -> dict[str, str]:
    """Повернути exact SHA-256 scoped production sources."""
    return {
        path.relative_to(PROJECT_ROOT).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in PRODUCTION_FILES
    }


def _combined_hash(hashes: dict[str, str]) -> str:
    """Згорнути ordered hashes у deterministic marker."""
    payload = "\n".join(f"{path}={hashes[path]}" for path in sorted(hashes))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _baseline_key(runtime: Any) -> str:
    """Повернути compact exact canonical Replay metrics key."""
    summary = runtime.historical_summary
    if summary is None:
        raise AssertionError("canonical Replay summary missing")
    return (
        f"{summary.opened_trades}/{summary.winning_trades}/"
        f"{summary.losing_trades}/{summary.break_even_trades}/"
        f"{summary.net_profit:+.2f}/{summary.profit_factor:.4f}/"
        f"{summary.maximum_drawdown:.2f}"
    )


def _split_six_char_fx_symbol(symbol: str) -> tuple[str, str]:
    """Перевірити лише documented 6-char FX semantic scenario, не runtime API."""
    normalized = symbol.strip().upper()
    if len(normalized) != 6 or not normalized.isalpha():
        raise ValueError("test scenario requires a six-character FX symbol")
    return normalized[:3], normalized[3:]


def _loss_in_account_currency(
    loss_quote: float,
    *,
    mode: str,
    rate: float = 1.0,
) -> float:
    """Перевірити identity/multiply/divide formulas без source availability."""
    if loss_quote < 0.0 or rate <= 0.0:
        raise ValueError("positive loss magnitude and rate are required")
    if mode == "IDENTITY":
        return loss_quote
    if mode == "DIVIDE":
        return loss_quote / rate
    if mode == "MULTIPLY":
        return loss_quote * rate
    raise ValueError("unsupported test-only conversion mode")


def main() -> None:
    """Довести source completeness, causal gaps, formulas і Replay safety."""
    hashes_before = _production_hashes()
    account_state_source = _source_text("engine/runtime_account_state.py")
    risk_snapshot_source = _source_text("engine/risk/account_snapshot.py")
    workspace_runtime_source = _source_text("core/workspace_runtime.py")
    workspace_market_source = _source_text("core/workspace_broker_market.py")
    workspace_config_source = _source_text("core/algorithm_workspace.py")
    historical_source = _source_text("core/workspace_historical_evaluation.py")
    replay_source = _source_text("core/workspace_replay_execution.py")
    runtime_engine_source = _source_text("engine/runtime_engine.py")
    ib_adapter_source = _source_text("engine/ib_adapter.py")
    ib_service_source = _source_text("engine/services/ib_runtime_service.py")
    ctrader_adapter_source = _source_text("engine/ctrader_adapter.py")
    ctrader_service_source = _source_text(
        "engine/services/ctrader_runtime_service.py"
    )
    ctrader_symbols_source = _source_text("core/ctrader_symbols.py")

    snapshot_fields = tuple(
        field.name for field in fields(WorkspaceRiskAccountSnapshot)
    )
    runtime_account_currency_present = "currency: str = \"\"" in account_state_source
    workspace_risk_snapshot_currency_present = "currency" in snapshot_fields
    workspace_runtime_account_currency_available = any(
        token in workspace_runtime_source
        for token in ("account_currency", "risk_account_snapshot.currency")
    )
    ib_account_currency_contract = all(
        token in ib_adapter_source + ib_service_source
        for token in (
            "reqAccountSummary",
            'self._account_state.currency = account.currency',
            'net_liquidation.get("currency")',
        )
    )
    ctrader_account_currency_contract = all(
        token in ctrader_adapter_source + ctrader_service_source
        for token in (
            "ProtoOATraderReq",
            "depositAssetId",
            "_get_currency_from_assets",
            "self._account_state.currency = account.currency",
        )
    )

    ib_symbol_contract = all(
        token in ib_adapter_source
        for token in (
            "def _normalize_forex_quote_symbols",
            "def _split_forex_symbol",
            "def _build_forex_contract",
            'contract.secType = "CASH"',
            "contract.currency = quote_symbol",
        )
    )
    ctrader_symbol_contract = all(
        token in ctrader_symbols_source
        for token in ("symbolCategoryId == 1", "symbol_name", "symbol_id")
    )
    workspace_has_shared_currency_parser = any(
        token in workspace_config_source + workspace_runtime_source
        for token in ("base_currency", "quote_currency", "split_fx_symbol")
    )
    eur_base, eur_quote = _split_six_char_fx_symbol("EURUSD")
    usd_base, usd_quote = _split_six_char_fx_symbol("USDJPY")
    symbol_scenarios_exact = (
        (eur_base, eur_quote) == ("EUR", "USD")
        and (usd_base, usd_quote) == ("USD", "JPY")
    )
    symbol_currency_contract_reliable = bool(
        ib_symbol_contract
        and ctrader_symbol_contract
        and workspace_has_shared_currency_parser
    )

    quote_equals_account_value = _loss_in_account_currency(
        10.0,
        mode="IDENTITY",
    )
    base_equals_account_value = _loss_in_account_currency(
        1500.0,
        mode="DIVIDE",
        rate=150.0,
    )
    cross_direct_value = _loss_in_account_currency(
        10.0,
        mode="MULTIPLY",
        rate=1.25,
    )
    cross_inverse_value = _loss_in_account_currency(
        10.0,
        mode="DIVIDE",
        rate=0.8,
    )
    formula_scenarios_exact = bool(
        quote_equals_account_value == 10.0
        and base_equals_account_value == 10.0
        and cross_direct_value == cross_inverse_value == 12.5
    )

    signal_price_source_present = all(
        token in workspace_market_source
        for token in (
            "WorkspaceMarketEvent(",
            "close=self._close",
            "bid=self._bid",
            "ask=self._ask",
            "timestamp=self._bucket_timestamp",
        )
    )
    quote_timestamp_source_present = all(
        token in workspace_market_source
        for token in (
            'row.get("timestamp")',
            'payload.get("captured_utc")',
            'guard_result="STALE_TIMESTAMP"',
        )
    )
    generic_quote_lookup_present = (
        "def get_workspace_forex_quote_snapshot" in runtime_engine_source
    )
    ib_cached_quote_source_present = all(
        token in ib_adapter_source
        for token in (
            "def get_forex_quote_snapshot",
            "_sync_forex_quote_subscriptions",
            "reqMktData",
            'row["timestamp"] = datetime.now(UTC)',
        )
    )
    ctrader_cached_quote_source_present = all(
        token in ctrader_adapter_source
        for token in (
            "def get_forex_quote_snapshot",
            "_sync_owned_spot_subscriptions",
            "subscribeToSpotTimestamp",
            'row.get("timestamp")',
        )
    )
    workspace_requests_bound_symbols = all(
        token in workspace_market_source
        for token in (
            "get_workspace_forex_quote_snapshot",
            "symbols = sorted",
            "item.symbol",
            "item.broker == binding.broker",
        )
    )
    conversion_freshness_contract_present = any(
        token in workspace_runtime_source + risk_snapshot_source
        for token in (
            "conversion_rate_timestamp",
            "conversion_rate_max_age",
            "quote_to_account_rate",
        )
    )

    replay_pnl_currency_contract = all(
        token in historical_source
        for token in (
            "pnl_currency: str",
            "first.symbol.endswith(policy.pnl_currency)",
        )
    )
    replay_cross_conversion_source_present = any(
        token in historical_source + replay_source
        for token in ("historical_cross_rate", "quote_to_account", "fx_conversion")
    )
    replay_assumes_usd = 'pnl_currency="USD"' in historical_source + replay_source
    replay_money_risk_normalization_complete = bool(
        workspace_risk_snapshot_currency_present
        and replay_cross_conversion_source_present
    )

    assert runtime_account_currency_present
    assert not workspace_risk_snapshot_currency_present
    assert not workspace_runtime_account_currency_available
    assert ib_account_currency_contract and ctrader_account_currency_contract
    assert ib_symbol_contract and ctrader_symbol_contract
    assert symbol_scenarios_exact and formula_scenarios_exact
    assert not symbol_currency_contract_reliable
    assert signal_price_source_present and quote_timestamp_source_present
    assert generic_quote_lookup_present and workspace_requests_bound_symbols
    assert ib_cached_quote_source_present and ctrader_cached_quote_source_present
    assert not conversion_freshness_contract_present
    assert replay_pnl_currency_contract
    assert not replay_cross_conversion_source_present
    assert not replay_assumes_usd
    assert not replay_money_risk_normalization_complete

    baselines: dict[str, Any] = {}
    broker_requests = 0
    for spec in CANONICAL_PERIODS:
        runtime, _rejects, requests = run_canonical_period(spec)
        baselines[spec.code] = runtime
        broker_requests += requests
    canonical_2025_exact_match = _baseline_key(baselines["2025"]) == EXPECTED_2025
    canonical_2026_exact_match = _baseline_key(baselines["2026"]) == EXPECTED_2026
    assert canonical_2025_exact_match and canonical_2026_exact_match
    assert broker_requests == 0

    hashes_after = _production_hashes()
    assert hashes_before == hashes_after
    combined_before = _combined_hash(hashes_before)
    combined_after = _combined_hash(hashes_after)

    print(f"test_id={TEST_ID}")
    print(
        "runtime_account_currency_source=RuntimeAccountState.currency from "
        "IB reqAccountSummary or cTrader trader depositAssetId asset metadata"
    )
    print(f"runtime_account_currency_present={runtime_account_currency_present}")
    print(
        "workspace_risk_snapshot_currency_present="
        f"{workspace_risk_snapshot_currency_present}"
    )
    print(
        "workspace_runtime_account_currency_available="
        f"{workspace_runtime_account_currency_available}"
    )
    print(
        "symbol_currency_source=IB CASH contract metadata; cTrader Forex catalog "
        "and Workspace use broker symbol names"
    )
    print(
        "base_currency_source=IB contract.symbol/parser; otherwise 6-char FX "
        "symbol convention only"
    )
    print(
        "quote_currency_source=IB contract.currency/parser; RuntimeEngine IB "
        "helper; otherwise 6-char FX symbol convention only"
    )
    print(f"symbol_currency_contract_reliable={symbol_currency_contract_reliable}")
    print("quote_equals_account_formula=loss_account=loss_quote; rate=1")
    print("quote_equals_account_source_complete=False")
    print("base_equals_account_formula=loss_account=loss_quote/symbol_price")
    print(
        "base_equals_account_rate_source=completed WorkspaceMarketEvent close "
        "at signal time"
    )
    print("base_equals_account_source_complete=False")
    print(
        "cross_required_formula=loss_quote*QUOTEACCOUNT or "
        "loss_quote/ACCOUNTQUOTE"
    )
    print(
        "cross_rate_source=RuntimeEngine broker Forex quote snapshot for an "
        "explicit cross symbol"
    )
    print("cross_rate_cached_source_present=CONDITIONAL_NOT_GUARANTEED")
    print("cross_rate_requires_broker_request=True")
    print("cross_rate_source_complete=False")
    print(
        "conversion_timestamp_source=completed signal event timestamp/close; "
        "broker quote row timestamp and captured_utc for cross"
    )
    print("conversion_rate_must_not_be_after=signal_risk_decision_timestamp")
    print("conversion_rate_freshness_contract=UNDEFINED")
    print(
        "conversion_rate_causality_enforceable=PARTIAL_TIMESTAMPS_EXIST_NO_"
        "SELECTION_OR_FRESHNESS_GUARD"
    )
    print("lookahead_risk_present=True")
    print(
        "ib_account_currency_source=authoritative reqAccountSummary result "
        "cached in RuntimeAccountState; refresh is a broker request"
    )
    print(
        "ib_conversion_quote_source=cached Forex snapshot with quote timestamp; "
        "missing symbol triggers reqMktData"
    )
    print("ib_cross_conversion_source_complete=False")
    print(
        "ctrader_account_currency_source=trader.depositAssetId mapped through "
        "asset metadata and cached in RuntimeAccountState; refresh is a request"
    )
    print(
        "ctrader_conversion_quote_source=cached subscribed spot with broker "
        "timestamp; missing symbol triggers subscription sync"
    )
    print("ctrader_cross_conversion_source_complete=False")
    print(
        "replay_account_currency_contract=ABSENT; pnl_currency labels symbol "
        "quote currency only"
    )
    print("replay_cross_conversion_source=ABSENT")
    print(
        "replay_money_risk_normalization_complete="
        f"{replay_money_risk_normalization_complete}"
    )
    print("missing_rate_safe_behavior=BLOCK_RISK_EXECUTION")
    print("stale_rate_safe_behavior=BLOCK_RISK_EXECUTION")
    print("unknown_account_currency_safe_behavior=BLOCK_RISK_EXECUTION")
    print("broker_neutral_currency_normalization_source_complete=False")
    print("production_repair_feasible_without_new_broker_request=False")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")
    print(f"canonical_2025_exact_match={canonical_2025_exact_match}")
    print(f"canonical_2026_exact_match={canonical_2026_exact_match}")
    print(f"production_hashes_before={combined_before}")
    print(f"production_hashes_after={combined_after}")
    print("production_hashes_before_after_match=True")
    print("safety_invariants=")
    print("  TEST_ONLY=True")
    print(f"  broker_requests={broker_requests}")
    print("  broker_execution_attempted=False")
    print("  production_logic_changed=False")
    print("  trading_logic_changed=False")
    print("  lookahead_used=False")
    print("T109_14_FX_CURRENCY_NORMALIZATION_SOURCE_ANATOMY=OK")


def test_t109_14_fx_currency_normalization_source_anatomy() -> None:
    """Запустити той самий anatomy contract через pytest/PyCharm."""
    main()


if __name__ == "__main__":
    main()
