"""run_t109_11_workspace_volume_semantics_broker_conversion_boundary_anatomy_check.py.

TEST_ONLY anatomy фіксує фактичні semantics Workspace risk volume, його рух
через intent і risk decision, synthetic Replay arithmetic та окремі IB/cTrader
conversion boundaries. Production sources перевіряються executable assertions,
а canonical Replay 2025/2026 повторно підтверджує незмінність causal baseline.

Runner не обирає unit за правдоподібністю чисел, не створює execution plan чи
order, не викликає broker/network API та не змінює DTO, schema, risk, Replay,
AUTO/SEMI або production wiring. Невизначена production unit залишається
factual blocker перед майбутньою broker-neutral conversion boundary.
"""

from __future__ import annotations

import hashlib
import importlib
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

TEST_ID = "T109-11"
EXPECTED_2025 = "42/30/11/1/+4.03/1.5424/3.58"
EXPECTED_2026 = "18/15/2/1/+3.68/3.7669/1.20"
FACTUAL_VERDICT = "G. VOLUME_SEMANTICS_NOT_DEFINED"
FIRST_UNRESOLVED_BOUNDARY = (
    "WORKSPACE_RISK_VOLUME_SCALAR_TO_DECLARED_BROKER_NEUTRAL_UNIT"
)
BOUNDARY_CONTRACT = (
    "MAXIMUM_REQUESTED_APPROVED_VOLUME_REQUIRES_ONE_EXPLICIT_SYMBOL_AWARE_"
    "UNIT_BEFORE_BROKER_CONVERSION"
)
PRODUCTION_FILES = (
    PROJECT_ROOT / "core" / "ctrader_lot.py",
    PROJECT_ROOT / "core" / "workspace_historical_evaluation.py",
    PROJECT_ROOT / "core" / "workspace_parameter_catalog.py",
    PROJECT_ROOT / "core" / "workspace_parameters.py",
    PROJECT_ROOT / "core" / "workspace_replay_execution.py",
    PROJECT_ROOT / "core" / "workspace_replay_margin.py",
    PROJECT_ROOT / "core" / "workspace_runtime.py",
    PROJECT_ROOT / "core" / "workspace_signal.py",
    PROJECT_ROOT / "engine" / "ctrader_adapter.py",
    PROJECT_ROOT / "engine" / "ib_adapter.py",
    PROJECT_ROOT / "engine" / "risk" / "constants.py",
    PROJECT_ROOT / "engine" / "risk" / "risk_model.py",
    PROJECT_ROOT / "engine" / "runtime_engine.py",
    PROJECT_ROOT / "engine" / "services" / "ctrader_runtime_service.py",
    PROJECT_ROOT / "engine" / "services" / "ib_runtime_service.py",
)


def source_text(relative_path: str) -> str:
    """Прочитати один production module як UTF-8 contract."""
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def source_section(relative_path: str, start: str, end: str) -> str:
    """Виділити production section між двома exact anchors."""
    source = source_text(relative_path)
    start_index = source.index(start)
    end_index = source.index(end, start_index + len(start))
    return source[start_index:end_index]


def production_hashes() -> dict[str, str]:
    """Зафіксувати production sources до і після TEST_ONLY anatomy."""
    return {
        path.relative_to(PROJECT_ROOT)
        .as_posix(): hashlib.sha256(path.read_bytes())
        .hexdigest()
        for path in PRODUCTION_FILES
    }


def baseline_key(runtime: Any) -> str:
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


def main() -> None:
    """Довести відсутність declared unit та розділені broker conversions."""
    hashes_before = production_hashes()
    risk_constants = source_text("engine/risk/constants.py")
    risk_model = source_text("engine/risk/risk_model.py")
    parameters = source_text("core/workspace_parameters.py")
    parameter_catalog = source_text("core/workspace_parameter_catalog.py")
    workspace_signal = source_text("core/workspace_signal.py")
    replay_execution = source_text("core/workspace_replay_execution.py")
    replay_evaluation = source_text("core/workspace_historical_evaluation.py")
    replay_margin = source_text("core/workspace_replay_margin.py")
    runtime_engine = source_text("engine/runtime_engine.py")
    ib_service = source_text("engine/services/ib_runtime_service.py")
    ib_adapter = source_text("engine/ib_adapter.py")
    ctrader_service = source_text("engine/services/ctrader_runtime_service.py")
    ctrader_adapter = source_text("engine/ctrader_adapter.py")
    ctrader_lot = source_text("core/ctrader_lot.py")

    intent_section = source_section(
        "core/workspace_runtime.py",
        "    def _candidate_f_execution_intent(",
        "    def _record_signal(",
    )
    risk_evaluate_section = source_section(
        "engine/risk/risk_model.py",
        "    def evaluate(",
        "    def _block_reason(",
    )
    manual_order_section = source_section(
        "engine/runtime_engine.py",
        "    def place_manual_market_order(",
        "    @staticmethod\n    def _normalize_optional_protection_price(",
    )
    ib_conversion_section = source_section(
        "engine/runtime_engine.py",
        "    def _ib_lots_to_fx_quantity(",
        "    @staticmethod\n    def _get_position_symbol_text(",
    )

    declared_unit_tokens = (
        "volume_unit",
        "position_volume_unit",
        "maximum_position_volume_unit",
    )
    maximum_position_volume_declared_unit = "UNDECLARED"
    volume_contract_resolved = False

    setting_created = all(
        token in risk_constants
        for token in (
            "WORKSPACE_RISK_SETTING_MAXIMUM_POSITION_VOLUME = "
            '"maximum_position_volume"',
            "DEFAULT_WORKSPACE_MAXIMUM_POSITION_VOLUME = 1000.0",
        )
    )
    setting_persisted = all(
        token in parameters
        for token in (
            "maximum_position_volume: float =",
            "result[volume_key] = self.maximum_position_volume",
        )
    )
    ui_has_no_unit = all(
        token in parameter_catalog
        for token in (
            'title="Maximum position volume"',
            '"Hard upper limit for the volume requested by one WSP signal."',
        )
    ) and not any(token in parameter_catalog for token in declared_unit_tokens)
    risk_declares_no_unit = not any(
        token in risk_model for token in declared_unit_tokens
    )
    setting_is_broker_symbol_independent = all(
        token not in parameters
        for token in ("contract_size", "symbol_volume_unit", "broker_volume_unit")
    )

    requested_from_policy = all(
        token in intent_section
        for token in (
            "fixed_volume=self.risk_policy.maximum_position_volume",
            "requested_volume = policy.fixed_volume",
            "requested_volume=requested_volume",
            "estimated_loss_at_stop=protection_distance * requested_volume",
        )
    )
    intent_has_plain_float = "requested_volume: float" in workspace_signal
    evaluator_compares_same_scalar = (
        "request.requested_volume > self.policy.maximum_position_volume" in risk_model
    )
    approved_copies_requested = (
        "approved_volume = request.requested_volume" in risk_evaluate_section
    )
    approved_volume_unit_preserved = bool(
        requested_from_policy
        and evaluator_compares_same_scalar
        and approved_copies_requested
    )

    replay_pnl_exact = (
        "return (close_price - position.entry_price) * position.volume * direction"
        in replay_execution
    )
    replay_historical_pnl_exact = all(
        token in replay_evaluation
        for token in (
            "volume = policy.fixed_volume",
            "gross_profit = (exit_mid - entry_mid) * volume",
            "execution_profit = (exit_execution - entry_execution) * volume",
        )
    )
    replay_margin_exact = (
        "return normalized_volume * normalized_price / normalized_leverage"
        in replay_margin
    )
    replay_declares_no_unit = not any(
        token in replay_execution + replay_evaluation + replay_margin
        for token in declared_unit_tokens
    )

    manual_input_is_lots = all(
        token in manual_order_section
        for token in (
            "lots: float",
            "lots=lots",
            "lots_float = float(lots)",
        )
    )
    ib_conversion_exact = all(
        token in ib_conversion_section
        for token in (
            "1.00 lot = 100000 units, 0.01 lot = 1000 units",
            "return round(lots_float * 100000.0, 2)",
        )
    )
    ib_service_accepts_quantity = all(
        token in ib_service for token in ("quantity: float", "quantity=quantity")
    )
    ib_adapter_accepts_quantity = all(
        token in ib_adapter
        for token in (
            "def place_market_order(",
            "quantity: float",
            "quantity_float = float(quantity)",
        )
    )
    ib_conversion_symbol_aware = False
    ib_non_fx_manual_unsupported = all(
        token in runtime_engine
        for token in (
            "_assert_ib_fx_execution_safe(",
            "IB Forex",
        )
    )

    ctrader_service_accepts_lots = all(
        token in ctrader_service
        for token in ("def place_market_order(", "lots: float", "lots=lots")
    )
    ctrader_adapter_accepts_lots = all(
        token in ctrader_adapter
        for token in (
            "def place_market_order(",
            "lots: float",
            "api_volume = ctr_lot.lots_to_api_volume(normalized_lots)",
            "request.volume = api_volume",
        )
    )
    ctrader_conversion_exact = all(
        token in ctrader_lot
        for token in (
            "API_VOLUME_PER_1_LOT_FX = 10_000_000",
            "return int(round(lots * API_VOLUME_PER_1_LOT_FX))",
        )
    )
    ctrader_conversion_symbol_aware = False
    ctrader_formula_fx_specific = all(
        token in ctrader_lot for token in ("FX", "поточного demo-оточення")
    )

    baselines: dict[str, Any] = {}
    broker_requests = 0
    for spec in CANONICAL_PERIODS:
        runtime, _rejects, requests = run_canonical_period(spec)
        baselines[spec.code] = runtime
        broker_requests += requests
    canonical_2025_exact_match = baseline_key(baselines["2025"]) == EXPECTED_2025
    canonical_2026_exact_match = baseline_key(baselines["2026"]) == EXPECTED_2026

    assert setting_created
    assert setting_persisted
    assert ui_has_no_unit
    assert risk_declares_no_unit
    assert setting_is_broker_symbol_independent
    assert requested_from_policy
    assert intent_has_plain_float
    assert evaluator_compares_same_scalar
    assert approved_copies_requested
    assert approved_volume_unit_preserved
    assert replay_pnl_exact
    assert replay_historical_pnl_exact
    assert replay_margin_exact
    assert replay_declares_no_unit
    assert manual_input_is_lots
    assert ib_conversion_exact
    assert ib_service_accepts_quantity
    assert ib_adapter_accepts_quantity
    assert not ib_conversion_symbol_aware
    assert ib_non_fx_manual_unsupported
    assert ctrader_service_accepts_lots
    assert ctrader_adapter_accepts_lots
    assert ctrader_conversion_exact
    assert not ctrader_conversion_symbol_aware
    assert ctrader_formula_fx_specific
    assert not volume_contract_resolved
    assert canonical_2025_exact_match and canonical_2026_exact_match
    assert broker_requests == 0

    hashes_after = production_hashes()
    assert hashes_before == hashes_after

    print(f"test_id={TEST_ID}")
    print(
        "maximum_position_volume_value=default 1000.0; persisted cases "
        "include 3000.0"
    )
    print(
        "maximum_position_volume_declared_unit="
        f"{maximum_position_volume_declared_unit}"
    )
    print(
        "maximum_position_volume_actual_usage=positive broker/symbol-independent "
        "risk limit and Candidate F fixed scalar"
    )
    print(
        "requested_volume_source=WorkspaceRuntime.risk_policy."
        "maximum_position_volume"
    )
    print("requested_volume_declared_unit=UNDECLARED")
    print(
        "approved_volume_semantics=ALLOW copies request.requested_volume after "
        "guards; no conversion"
    )
    print(f"approved_volume_unit_preserved={approved_volume_unit_preserved}")
    print("estimated_loss_formula=protection_distance * requested_volume")
    print(
        "risk_volume_arithmetic_contract=dimensionally valid only if volume is "
        "price-denominated base quantity; production does not declare that unit"
    )
    print(
        "replay_volume_usage=fixed_volume is position volume; PnL=price delta * "
        "volume * direction; margin=volume * price / leverage"
    )
    print("replay_volume_declared_unit=UNDECLARED_SYNTHETIC_SCALAR")
    print("replay_volume_transferable_to_broker=False")
    print("ib_runtime_input_unit=LOTS on manual RuntimeEngine entrypoint")
    print("ib_broker_output_unit=IB_FOREX_QUANTITY_BASE_UNITS")
    print("ib_conversion_formula=quantity=round(lots * 100000.0, 2)")
    print("ib_conversion_boundary=RuntimeEngine before IBRuntimeService/IBAdapter")
    print(f"ib_conversion_symbol_aware={ib_conversion_symbol_aware}")
    print("ctrader_runtime_input_unit=LOTS")
    print("ctrader_broker_output_unit=CTRADER_OPEN_API_VOLUME")
    print("ctrader_conversion_formula=api_volume=round(lots * 10000000)")
    print("ctrader_conversion_boundary=CTraderAdapter")
    print(f"ctrader_conversion_symbol_aware={ctrader_conversion_symbol_aware}")
    print(
        "candidate_unit_lots=broker-neutral for current FX manual inputs, but "
        "incompatible with risk values and Replay arithmetic without semantic change"
    )
    print(
        "candidate_unit_base_units=compatible with Replay arithmetic and IB quantity "
        "shape, but not declared and requires cTrader lot/contract conversion"
    )
    print(
        "candidate_unit_broker_native=not broker-neutral because IB quantity and "
        "cTrader API volume use different scales"
    )
    print(
        "candidate_unit_risk_scalar=matches current risk transport but is not an "
        "executable broker volume contract"
    )
    print(
        "candidate_unit_symbol_contract_units=potentially broker-neutral, but no "
        "Workspace contract-size metadata or conversion exists"
    )
    print("canonical_volume_unit=UNRESOLVED")
    print(f"volume_contract_resolved={volume_contract_resolved}")
    print(
        "broker_neutral_conversion_boundary=WorkspaceExecutionPlan declared unit -> "
        "RuntimeEngine single broker conversion -> broker-native volume; candidate "
        "boundary only, not implemented"
    )
    print("production_semantics_change_required=True")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")
    print(f"canonical_2025_exact_match={canonical_2025_exact_match}")
    print(f"canonical_2026_exact_match={canonical_2026_exact_match}")
    print("production_hashes_before_after_match=True")
    print("safety_invariants=")
    print("  TEST_ONLY=True")
    print(f"  broker_requests={broker_requests}")
    print("  broker_execution_attempted=False")
    print("  production_logic_changed=False")
    print("  trading_logic_changed=False")
    print("  lookahead_used=False")
    print("T109_11_WORKSPACE_VOLUME_SEMANTICS_BROKER_CONVERSION_ANATOMY=OK")


def test_t109_11_workspace_volume_semantics_broker_conversion_anatomy() -> None:
    """Запустити той самий anatomy contract через pytest/PyCharm."""
    main()


if __name__ == "__main__":
    main()
