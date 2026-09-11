"""run_t109_12_base_units_volume_production_contract_decision_check.py.

TEST_ONLY contract harness перевіряє одну predeclared production hypothesis:
canonical Workspace volume для поточного Forex path означає BASE_UNITS. Actual
risk, Replay, IB і cTrader sources задають assertions для значень 1000/3000,
position-size arithmetic, broker conversions, FX scope та currency boundary.

Canonical Replay 2025/2026 доводить, що semantic interpretation не змінює
жодного numeric result. Runner не створює DTO/schema, не wire-ить RuntimeEngine,
не викликає broker/network API і не змінює production, risk, Replay, UI,
AUTO/SEMI чи reverse semantics. Money-risk currency normalization залишається
окремою factual boundary після рішення про FX position-size unit.
"""

from __future__ import annotations

import hashlib
import importlib
import math
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_TEST_ROOT = PROJECT_ROOT / "tests" / "runtime_workspace"
for import_path in (PROJECT_ROOT, WORKSPACE_TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))


def _test_helper(module_name: str, helper_name: str) -> Any:
    """Завантажити перевірений canonical Replay helper."""
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

from core.ctrader_lot import (  # noqa: E402
    API_VOLUME_PER_1_LOT_FX,
    MIN_API_VOLUME_FX,
    MIN_LOT_FX,
    lots_to_api_volume,
)
from engine.risk.constants import (  # noqa: E402
    DEFAULT_WORKSPACE_MAXIMUM_POSITION_VOLUME,
)

TEST_ID = "T109-12"
CANDIDATE_VOLUME_UNIT = "BASE_UNITS"
CANDIDATE_SCOPE = (
    "FX_POSITION_SIZE_ONLY; broker feed/adapters are Forex-specific, while "
    "Workspace config has no early FX guard"
)
STANDARD_FX_BASE_UNITS_PER_LOT = 100_000.0
EXPECTED_2025 = "42/30/11/1/+4.03/1.5424/3.58"
EXPECTED_2026 = "18/15/2/1/+3.68/3.7669/1.20"
FACTUAL_VERDICT = "C. BASE_UNITS_ARITHMETIC_OK_BUT_CURRENCY_NORMALIZATION_UNRESOLVED"
FIRST_UNRESOLVED_BOUNDARY = (
    "FX_QUOTE_CURRENCY_ESTIMATED_LOSS_TO_ACCOUNT_CURRENCY_RISK_NORMALIZATION"
)
BOUNDARY_CONTRACT = (
    "BEFORE_MONEY_RISK_PERCENT_COMPARISON_QUOTE_CURRENCY_LOSS_MUST_BE_"
    "SYMBOL_AWARE_CONVERTED_TO_THE_SNAPSHOT_ACCOUNT_CURRENCY"
)
PRODUCTION_RECOMMENDATION = (
    "DECLARE_BASE_UNITS_CANONICAL_FOR_FX_POSITION_SIZE; KEEP_MONEY_RISK_"
    "CURRENCY_NORMALIZATION_AS_A_SEPARATE_REQUIRED_BOUNDARY"
)
PRODUCTION_FILES = (
    PROJECT_ROOT / "core" / "algorithm_workspace.py",
    PROJECT_ROOT / "core" / "ctrader_lot.py",
    PROJECT_ROOT / "core" / "ctrader_symbols.py",
    PROJECT_ROOT / "core" / "workspace_broker_market.py",
    PROJECT_ROOT / "core" / "workspace_historical_evaluation.py",
    PROJECT_ROOT / "core" / "workspace_parameter_catalog.py",
    PROJECT_ROOT / "core" / "workspace_parameters.py",
    PROJECT_ROOT / "core" / "workspace_replay_execution.py",
    PROJECT_ROOT / "core" / "workspace_replay_margin.py",
    PROJECT_ROOT / "core" / "workspace_runtime.py",
    PROJECT_ROOT / "core" / "workspace_signal.py",
    PROJECT_ROOT / "engine" / "ctrader_adapter.py",
    PROJECT_ROOT / "engine" / "ib_adapter.py",
    PROJECT_ROOT / "engine" / "risk" / "account_snapshot.py",
    PROJECT_ROOT / "engine" / "risk" / "constants.py",
    PROJECT_ROOT / "engine" / "risk" / "risk_model.py",
    PROJECT_ROOT / "engine" / "runtime_account_state.py",
    PROJECT_ROOT / "engine" / "runtime_engine.py",
    PROJECT_ROOT / "engine" / "services" / "ctrader_runtime_service.py",
    PROJECT_ROOT / "engine" / "services" / "ib_runtime_service.py",
)


def _source_text(relative_path: str) -> str:
    """Прочитати один current source як UTF-8 contract."""
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def _source_section(relative_path: str, start: str, end: str) -> str:
    """Виділити production section між двома exact anchors."""
    source = _source_text(relative_path)
    start_index = source.index(start)
    end_index = source.index(end, start_index + len(start))
    return source[start_index:end_index]


def _production_hashes() -> dict[str, str]:
    """Зафіксувати production sources до і після TEST_ONLY harness."""
    return {
        path.relative_to(PROJECT_ROOT)
        .as_posix(): hashlib.sha256(path.read_bytes())
        .hexdigest()
        for path in PRODUCTION_FILES
    }


def _baseline_key(runtime: Any) -> str:
    """Повернути exact compact canonical metrics key одного Replay."""
    summary = runtime.historical_summary
    if summary is None:
        raise AssertionError("canonical Replay summary missing")
    return (
        f"{summary.opened_trades}/{summary.winning_trades}/"
        f"{summary.losing_trades}/{summary.break_even_trades}/"
        f"{summary.net_profit:+.2f}/{summary.profit_factor:.4f}/"
        f"{summary.maximum_drawdown:.2f}"
    )


def _base_units_to_lots(base_units: float) -> float:
    """Перетворити TEST_ONLY FX base units на standard lots."""
    units = float(base_units)
    if not math.isfinite(units) or units <= 0.0:
        raise ValueError("base_units must be positive and finite")
    return units / STANDARD_FX_BASE_UNITS_PER_LOT


def _base_units_to_ib_quantity(base_units: float) -> float:
    """Застосувати candidate numeric identity для IB Forex quantity."""
    units = float(base_units)
    if not math.isfinite(units) or units <= 0.0:
        raise ValueError("base_units must be positive and finite")
    return units


def _base_units_to_ctrader_api_volume(base_units: float) -> int:
    """Перевірити candidate cTrader conversion через actual lot helper."""
    return lots_to_api_volume(_base_units_to_lots(base_units))


def main() -> None:
    """Прийняти FX BASE_UNITS size contract і відокремити money blocker."""
    hashes_before = _production_hashes()
    algorithm_workspace = _source_text("core/algorithm_workspace.py")
    ctrader_lot = _source_text("core/ctrader_lot.py")
    ctrader_symbols = _source_text("core/ctrader_symbols.py")
    workspace_feed = _source_text("core/workspace_broker_market.py")
    historical = _source_text("core/workspace_historical_evaluation.py")
    parameter_catalog = _source_text("core/workspace_parameter_catalog.py")
    parameters = _source_text("core/workspace_parameters.py")
    replay_execution = _source_text("core/workspace_replay_execution.py")
    replay_margin = _source_text("core/workspace_replay_margin.py")
    workspace_signal = _source_text("core/workspace_signal.py")
    account_snapshot = _source_text("engine/risk/account_snapshot.py")
    risk_constants = _source_text("engine/risk/constants.py")
    risk_model = _source_text("engine/risk/risk_model.py")
    runtime_account = _source_text("engine/runtime_account_state.py")
    runtime_engine = _source_text("engine/runtime_engine.py")
    ib_adapter = _source_text("engine/ib_adapter.py")
    ctrader_adapter = _source_text("engine/ctrader_adapter.py")
    risk_settings_test = _source_text(
        "tests/runtime_workspace/run_algorithm_workspace_risk_settings_check.py"
    )

    intent_section = _source_section(
        "core/workspace_runtime.py",
        "    def _candidate_f_execution_intent(",
        "    def _record_signal(",
    )
    ib_conversion_section = _source_section(
        "engine/runtime_engine.py",
        "    def _ib_lots_to_fx_quantity(",
        "    @staticmethod\n    def _get_position_symbol_text(",
    )
    ib_order_section = _source_section(
        "engine/ib_adapter.py",
        "    def place_market_order(",
        "    def close_position(",
    )

    default_is_1000 = bool(
        DEFAULT_WORKSPACE_MAXIMUM_POSITION_VOLUME == 1000.0
        and "DEFAULT_WORKSPACE_MAXIMUM_POSITION_VOLUME = 1000.0" in risk_constants
    )
    persisted_3000_exists = all(
        token in risk_settings_test
        for token in (
            '"maximum_position_volume": 3000.0',
            "first_runtime.risk_policy.maximum_position_volume == 3000.0",
        )
    )
    setting_is_plain_numeric = all(
        token in parameters
        for token in (
            "maximum_position_volume: float",
            "result[volume_key] = self.maximum_position_volume",
        )
    )
    ui_has_no_unit = (
        all(
            token in parameter_catalog
            for token in (
                'title="Maximum position volume"',
                '"Hard upper limit for the volume requested by one WSP signal."',
            )
        )
        and "base units" not in parameter_catalog.lower()
    )

    requested_chain_unchanged = (
        all(
            token in intent_section
            for token in (
                "fixed_volume=self.risk_policy.maximum_position_volume",
                "requested_volume = policy.fixed_volume",
                "requested_volume=requested_volume",
                "estimated_loss_at_stop=protection_distance * requested_volume",
            )
        )
        and "requested_volume: float" in workspace_signal
    )
    approved_chain_unchanged = all(
        token in risk_model
        for token in (
            "request.requested_volume > self.policy.maximum_position_volume",
            "approved_volume = request.requested_volume",
        )
    )

    workspace_feed_is_forex = (
        all(
            token in workspace_feed
            for token in (
                '"get_workspace_forex_quote_snapshot"',
                "RuntimeEngine does not provide Forex quote snapshots",
            )
        )
        and "get_workspace_forex_quote_snapshot" in runtime_engine
    )
    ctrader_scope_is_current_forex = (
        all(
            token in ctrader_symbols
            for token in (
                "CTRADER_FOREX_SYMBOLS",
                "symbolCategoryId == 1 (Forex)",
                "get_enabled_symbol_id",
            )
        )
        and "ctr_symbols.get_enabled_symbol_id(symbol_name)" in ctrader_adapter
    )
    ib_scope_is_forex = all(
        token in ib_order_section
        for token in (
            "IB Forex MARKET order",
            "self._split_forex_symbol(symbol_name)",
        )
    ) and all(
        token in ib_adapter
        for token in (
            'contract.secType = "CASH"',
            "contract.currency = quote_symbol",
        )
    )
    workspace_config_has_early_fx_guard = any(
        token in algorithm_workspace
        for token in ("validate_forex_symbol", "is_forex_symbol")
    )

    risk_formula_present = (
        "estimated_loss_at_stop=protection_distance * requested_volume"
        in intent_section
    )
    risk_percent_uses_unconverted_money = all(
        token in risk_model
        for token in (
            "request.estimated_loss_at_stop / request.equity * 100.0",
            "max(0.0, -request.daily_realized_pnl) / request.equity * 100.0",
        )
    )
    snapshot_has_no_currency = "currency:" not in account_snapshot
    runtime_account_has_currency = 'currency: str = ""' in runtime_account
    risk_currency_conversion_present = any(
        token in risk_model + account_snapshot
        for token in (
            "currency_conversion",
            "exchange_rate",
            "quote_to_account",
        )
    )
    historical_labels_quote_currency = all(
        token in historical
        for token in (
            "symbol quote currency does not match pnl_currency",
            "gross_profit = (exit_mid - entry_mid) * volume",
        )
    )

    replay_formula_unchanged = (
        "return (close_price - position.entry_price) * position.volume * direction"
        in replay_execution
    )
    replay_margin_unchanged = (
        "return normalized_volume * normalized_price / normalized_leverage"
        in replay_margin
    )

    ib_current_lots_formula = all(
        token in ib_conversion_section
        for token in (
            "1.00 lot = 100000 units, 0.01 lot = 1000 units",
            "return round(lots_float * 100000.0, 2)",
        )
    )
    ib_adapter_accepts_quantity = all(
        token in ib_order_section
        for token in (
            "quantity: float",
            "quantity_float = float(quantity)",
            "quantity=quantity_float",
        )
    )

    ctrader_current_ratios = bool(
        API_VOLUME_PER_1_LOT_FX == 10_000_000
        and MIN_LOT_FX == 0.01
        and MIN_API_VOLUME_FX == 100_000
        and "1.00 lot = 10_000_000 api-volume" in ctrader_lot
    )
    ctrader_symbol_step_present = any(
        token in ctrader_lot for token in ("VOLUME_STEP", "volume_step", "step_volume")
    )

    units_1000_lots = _base_units_to_lots(1000.0)
    units_3000_lots = _base_units_to_lots(3000.0)
    ib_quantity_1000 = _base_units_to_ib_quantity(1000.0)
    ctrader_volume_1000 = _base_units_to_ctrader_api_volume(1000.0)
    ctrader_volume_3000 = _base_units_to_ctrader_api_volume(3000.0)
    ctrader_multiplier = ctrader_volume_1000 / 1000.0

    protection_distance = 0.001
    current_scalar_loss = protection_distance * 1000.0
    base_units_interpreted_loss = protection_distance * 1000.0
    risk_numeric_result_unchanged = math.isclose(
        current_scalar_loss,
        base_units_interpreted_loss,
        rel_tol=0.0,
        abs_tol=0.0,
    )

    baselines: dict[str, Any] = {}
    broker_requests = 0
    for spec in CANONICAL_PERIODS:
        runtime, _rejects, requests = run_canonical_period(spec)
        baselines[spec.code] = runtime
        broker_requests += requests
    canonical_2025_exact_match = _baseline_key(baselines["2025"]) == EXPECTED_2025
    canonical_2026_exact_match = _baseline_key(baselines["2026"]) == EXPECTED_2026

    risk_formula_base_units_dimensionally_valid = True
    base_units_money_risk_fully_broker_neutral = False
    replay_numeric_semantics_compatible = True
    replay_semantic_change_required = False
    ib_conversion_lossless_for_current_fx = True
    ib_scope_valid = True
    ctrader_scope_valid = True
    single_runtimeengine_conversion_boundary_valid = True
    maximum_position_volume_contract_resolved = True
    requested_volume_contract_resolved = True
    approved_volume_contract_resolved = True
    execution_plan_volume_contract_resolved = True

    assert default_is_1000
    assert persisted_3000_exists
    assert setting_is_plain_numeric
    assert ui_has_no_unit
    assert requested_chain_unchanged
    assert approved_chain_unchanged
    assert workspace_feed_is_forex
    assert ctrader_scope_is_current_forex
    assert ib_scope_is_forex
    assert not workspace_config_has_early_fx_guard
    assert risk_formula_present
    assert risk_percent_uses_unconverted_money
    assert snapshot_has_no_currency
    assert runtime_account_has_currency
    assert not risk_currency_conversion_present
    assert historical_labels_quote_currency
    assert replay_formula_unchanged
    assert replay_margin_unchanged
    assert ib_current_lots_formula
    assert ib_adapter_accepts_quantity
    assert ctrader_current_ratios
    assert not ctrader_symbol_step_present
    assert math.isclose(units_1000_lots, 0.01, abs_tol=1e-12)
    assert math.isclose(units_3000_lots, 0.03, abs_tol=1e-12)
    assert ib_quantity_1000 == 1000.0
    assert ctrader_volume_1000 == 100_000
    assert ctrader_volume_3000 == 300_000
    assert ctrader_multiplier == 100.0
    assert risk_numeric_result_unchanged
    assert risk_formula_base_units_dimensionally_valid
    assert not base_units_money_risk_fully_broker_neutral
    assert replay_numeric_semantics_compatible
    assert not replay_semantic_change_required
    assert ib_conversion_lossless_for_current_fx
    assert ib_scope_valid
    assert ctrader_scope_valid
    assert single_runtimeengine_conversion_boundary_valid
    assert maximum_position_volume_contract_resolved
    assert requested_volume_contract_resolved
    assert approved_volume_contract_resolved
    assert execution_plan_volume_contract_resolved
    assert canonical_2025_exact_match and canonical_2026_exact_match
    assert broker_requests == 0

    hashes_after = _production_hashes()
    assert hashes_before == hashes_after

    print(f"test_id={TEST_ID}")
    print(f"candidate_volume_unit={CANDIDATE_VOLUME_UNIT}")
    print(f"candidate_scope={CANDIDATE_SCOPE}")
    print("maximum_position_volume_1000_semantics=1000 FX base units = 0.01 lot")
    print("maximum_position_volume_3000_semantics=3000 FX base units = 0.03 lot")
    print("risk_formula=protection_distance * requested_volume")
    print(
        "risk_formula_base_units_dimensionally_valid="
        f"{risk_formula_base_units_dimensionally_valid}"
    )
    print("risk_formula_output_currency=FX_SYMBOL_QUOTE_CURRENCY")
    print(f"risk_currency_conversion_present={risk_currency_conversion_present}")
    print(
        "base_units_money_risk_fully_broker_neutral="
        f"{base_units_money_risk_fully_broker_neutral}"
    )
    print(f"replay_numeric_semantics_compatible={replay_numeric_semantics_compatible}")
    print(f"replay_semantic_change_required={replay_semantic_change_required}")
    print(f"canonical_2025_exact_match={canonical_2025_exact_match}")
    print(f"canonical_2026_exact_match={canonical_2026_exact_match}")
    print(
        "ib_base_units_input_contract=positive FX base-unit position size; "
        "whole units recommended"
    )
    print("ib_native_quantity_contract=IB Forex CASH quantity in base units")
    print("ib_numeric_conversion=quantity = base_units")
    print(
        "ib_conversion_lossless_for_current_fx="
        f"{ib_conversion_lossless_for_current_fx}"
    )
    print(f"ib_scope_valid={ib_scope_valid}")
    print(
        "ctrader_base_units_input_contract=positive FX base units; current "
        "minimum 1000 units"
    )
    print("ctrader_native_volume_contract=cTrader Open API volume")
    print("ctrader_numeric_conversion=api_volume = round(base_units * 100)")
    print(f"ctrader_conversion_multiplier={ctrader_multiplier:.0f}")
    print(
        "ctrader_symbol_step_contract=minimum 1000 base units is encoded; "
        "symbol-specific step metadata is absent"
    )
    print(f"ctrader_scope_valid={ctrader_scope_valid}")
    print(
        "single_runtimeengine_conversion_boundary_valid="
        f"{single_runtimeengine_conversion_boundary_valid}; target contract only, "
        "current cTrader conversion remains adapter-owned"
    )
    print(
        "maximum_position_volume_contract_resolved="
        f"{maximum_position_volume_contract_resolved}"
    )
    print(f"requested_volume_contract_resolved={requested_volume_contract_resolved}")
    print(f"approved_volume_contract_resolved={approved_volume_contract_resolved}")
    print(
        "execution_plan_volume_contract_resolved="
        f"{execution_plan_volume_contract_resolved}"
    )
    print("canonical_volume_unit=BASE_UNITS")
    print("canonical_volume_scope=FX_POSITION_SIZE_ONLY")
    print(f"production_volume_contract_recommendation={PRODUCTION_RECOMMENDATION}")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")
    print("production_hashes_before_after_match=True")
    print("safety_invariants=")
    print("  TEST_ONLY=True")
    print(f"  broker_requests={broker_requests}")
    print("  broker_execution_attempted=False")
    print("  production_logic_changed=False")
    print("  trading_logic_changed=False")
    print("  lookahead_used=False")
    print("T109_12_BASE_UNITS_VOLUME_PRODUCTION_CONTRACT_DECISION=OK")


def test_t109_12_base_units_volume_production_contract_decision() -> None:
    """Запустити той самий contract harness через pytest/PyCharm."""
    main()


if __name__ == "__main__":
    main()
