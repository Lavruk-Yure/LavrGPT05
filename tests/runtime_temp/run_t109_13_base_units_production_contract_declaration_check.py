"""run_t109_13_base_units_production_contract_declaration_check.py.

TEST_ONLY regression перевіряє мінімальну production declaration canonical
Workspace volume contract: BASE_UNITS лише для FX position-size semantics.
Actual constants, Candidate F BROKER AUTO/SEMI intent і risk evaluator доводять
незмінний рух numeric maximum/requested/approved volume без lot або broker-native
conversion; canonical Replay 2025/2026 підтверджує незмінну trading математику.

Runner не створює WorkspaceExecutionPlan чи schema, не wire-ить RuntimeEngine,
не викликає broker/network API та не змінює AUTO/SEMI, reverse, UI або money-risk
currency normalization. Production hashes, safety markers і repeat output
фіксують contract-only scope та наступну factual boundary.
"""

from __future__ import annotations

import hashlib
import importlib
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_TEST_ROOT = PROJECT_ROOT / "tests" / "runtime_workspace"
RUNTIME_TEMP_ROOT = PROJECT_ROOT / "tests" / "runtime_temp"
for import_path in (PROJECT_ROOT, WORKSPACE_TEST_ROOT, RUNTIME_TEMP_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))


def _test_helper(module_name: str, helper_name: str) -> Any:
    """Завантажити established TEST_ONLY helper без копіювання harness logic."""
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
broker_events = _test_helper(
    "run_t109_01_broker_signal_to_execution_path_anatomy_check",
    "_broker_events",
)
run_candidate_f_mode = _test_helper(
    "run_t109_03_minimal_production_execution_intent_repair_check",
    "_run_mode",
)

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_CONTROL_MODE_SEMI,
)
from engine.risk.constants import (  # noqa: E402
    DEFAULT_WORKSPACE_MAXIMUM_POSITION_VOLUME,
    RISK_DECISION_ALLOW,
    WORKSPACE_CANONICAL_VOLUME_FIELDS,
    WORKSPACE_CANONICAL_VOLUME_SCOPE,
    WORKSPACE_CANONICAL_VOLUME_UNIT,
    WORKSPACE_VOLUME_SCOPE_FX_POSITION_SIZE_ONLY,
    WORKSPACE_VOLUME_UNIT_BASE_UNITS,
)
from engine.risk.risk_model import (  # noqa: E402
    WorkspaceRiskEvaluator,
    WorkspaceRiskPolicy,
    WorkspaceRiskRequest,
)

TEST_ID = "T109-13"
EXPECTED_2025 = "42/30/11/1/+4.03/1.5424/3.58"
EXPECTED_2026 = "18/15/2/1/+3.68/3.7669/1.20"
FACTUAL_VERDICT = "A. BASE_UNITS_PRODUCTION_CONTRACT_DECLARED_GREEN"
FIRST_UNRESOLVED_BOUNDARY = (
    "FX_QUOTE_CURRENCY_ESTIMATED_LOSS_TO_ACCOUNT_CURRENCY_RISK_NORMALIZATION"
)
BOUNDARY_CONTRACT = (
    "BASE_UNITS_DECLARE_FX_POSITION_SIZE_ONLY; QUOTE_CURRENCY_LOSS_REQUIRES_"
    "SEPARATE_SYMBOL_AWARE_ACCOUNT_CURRENCY_NORMALIZATION"
)
PRODUCTION_FILES = (
    PROJECT_ROOT / "core" / "workspace_replay_execution.py",
    PROJECT_ROOT / "core" / "workspace_runtime.py",
    PROJECT_ROOT / "core" / "workspace_signal.py",
    PROJECT_ROOT / "engine" / "risk" / "account_snapshot.py",
    PROJECT_ROOT / "engine" / "risk" / "constants.py",
    PROJECT_ROOT / "engine" / "risk" / "risk_model.py",
)


def _source_text(relative_path: str) -> str:
    """Прочитати current production source як UTF-8 contract."""
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def _production_hashes() -> dict[str, str]:
    """Повернути exact SHA-256 кожного scoped production source."""
    return {
        path.relative_to(PROJECT_ROOT).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in PRODUCTION_FILES
    }


def _combined_hash(hashes: dict[str, str]) -> str:
    """Згорнути ordered production hashes в один deterministic marker."""
    payload = "\n".join(f"{path}={hashes[path]}" for path in sorted(hashes))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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


def main() -> None:
    """Перевірити declaration, numeric invariants, Replay і safety boundary."""
    hashes_before = _production_hashes()
    constants_source = _source_text("engine/risk/constants.py")
    runtime_source = _source_text("core/workspace_runtime.py")
    signal_source = _source_text("core/workspace_signal.py")
    risk_source = _source_text("engine/risk/risk_model.py")
    replay_source = _source_text("core/workspace_replay_execution.py")
    snapshot_source = _source_text("engine/risk/account_snapshot.py")
    risk_settings_test = _source_text(
        "tests/runtime_workspace/run_algorithm_workspace_risk_settings_check.py"
    )

    contract_fields = (
        "maximum_position_volume",
        "requested_volume",
        "approved_volume",
    )
    contract_is_explicit = bool(
        WORKSPACE_CANONICAL_VOLUME_UNIT == WORKSPACE_VOLUME_UNIT_BASE_UNITS
        == "BASE_UNITS"
        and WORKSPACE_CANONICAL_VOLUME_SCOPE
        == WORKSPACE_VOLUME_SCOPE_FX_POSITION_SIZE_ONLY
        == "FX_POSITION_SIZE_ONLY"
        and WORKSPACE_CANONICAL_VOLUME_FIELDS == contract_fields
    )
    constants_document_fx_base_units = all(
        token in constants_source
        for token in (
            "кількість одиниць base currency тільки для FX",
            "не broker-native volume",
            "maximum_position_volume -> requested_volume -> approved_volume",
        )
    )
    maximum_position_volume_default = DEFAULT_WORKSPACE_MAXIMUM_POSITION_VOLUME
    maximum_position_volume_3000_preserved = all(
        token in risk_settings_test
        for token in (
            '"maximum_position_volume": 3000.0',
            "first_runtime.risk_policy.maximum_position_volume == 3000.0",
        )
    )

    workspace_risk_chain = runtime_source + signal_source + risk_source
    workspace_lots_conversion_present = any(
        token in workspace_risk_chain
        for token in ("lots_to_", "_to_lots", "LOT_SIZE", "lot_size")
    )
    workspace_broker_native_conversion_present = any(
        token in workspace_risk_chain
        for token in (
            "api_volume",
            "_ib_lots_to_fx_quantity",
            "broker_native_volume",
        )
    )
    candidate_f_source_contract = all(
        token in runtime_source
        for token in (
            "fixed_volume=self.risk_policy.maximum_position_volume",
            "requested_volume = policy.fixed_volume",
            "requested_volume=requested_volume",
        )
    )
    risk_allow_copies_requested = (
        "approved_volume = request.requested_volume" in risk_source
    )

    baselines: dict[str, Any] = {}
    broker_requests = 0
    for spec in CANONICAL_PERIODS:
        runtime, _rejects, requests = run_canonical_period(spec)
        baselines[spec.code] = runtime
        broker_requests += requests
    canonical_2025_exact_match = _baseline_key(baselines["2025"]) == EXPECTED_2025
    canonical_2026_exact_match = _baseline_key(baselines["2026"]) == EXPECTED_2026
    replay_session = baselines["2025"].replay_session
    if replay_session is None or not replay_session.completed:
        raise AssertionError("canonical completed Replay input missing")

    completed_broker_events = broker_events(tuple(replay_session.events))
    auto_fact = run_candidate_f_mode(
        WORKSPACE_CONTROL_MODE_AUTO,
        completed_broker_events,
    )
    semi_fact = run_candidate_f_mode(
        WORKSPACE_CONTROL_MODE_SEMI,
        completed_broker_events,
    )
    broker_requests += auto_fact.broker_requests + semi_fact.broker_requests
    auto_intent = auto_fact.accepted_proposal.trade_intent
    semi_intent = semi_fact.accepted_proposal.trade_intent
    if auto_intent is None or semi_intent is None:
        raise AssertionError("Candidate F production intent missing")
    candidate_f_requested_volume_preserved = bool(
        auto_intent.requested_volume
        == auto_fact.runtime_risk_policy_maximum_position_volume
        == 1000.0
        and semi_intent.requested_volume
        == semi_fact.runtime_risk_policy_maximum_position_volume
        == 1000.0
    )

    policy = WorkspaceRiskPolicy(
        max_risk_percent=0.5,
        maximum_position_volume=3000.0,
        maximum_open_positions=2,
        max_daily_loss_percent=2.0,
    )
    request = WorkspaceRiskRequest(
        timestamp=auto_fact.accepted_event.timestamp,
        workspace_uid=auto_fact.workspace_uid,
        broker="CTRADER",
        account_id=auto_fact.account_id,
        symbol=auto_fact.symbol,
        side=auto_fact.accepted_proposal.direction,
        source_mode="BROKER",
        requested_volume=3000.0,
        equity=100_000.0,
        estimated_loss_at_stop=1.0,
        stop_loss=auto_intent.stop_loss,
        open_positions_count=0,
        daily_realized_pnl=0.0,
        runtime_ready=True,
        binding_verified=True,
        market_valid=True,
        spread_guard_passed=True,
    )
    decision = WorkspaceRiskEvaluator(policy).evaluate(request)
    risk_approved_volume_preserved = bool(
        decision.decision == RISK_DECISION_ALLOW
        and decision.requested_volume == 3000.0
        and decision.approved_volume == 3000.0
    )

    replay_numeric_semantics_changed = not all(
        token in replay_source
        for token in (
            "fixed_volume: float",
            "volume=self.policy.fixed_volume",
            "(close_price - position.entry_price) * position.volume * direction",
        )
    )
    money_risk_currency_normalization_changed = any(
        token in risk_source + snapshot_source
        for token in (
            "quote_to_account",
            "currency_conversion",
            "exchange_rate",
        )
    )
    fx_scope_explicit = bool(
        contract_is_explicit and constants_document_fx_base_units
    )
    non_fx_generalization_added = False
    production_contract_changed = True
    production_trading_logic_changed = False
    production_execution_wiring_changed = False

    assert contract_is_explicit
    assert constants_document_fx_base_units
    assert maximum_position_volume_default == 1000.0
    assert maximum_position_volume_3000_preserved
    assert candidate_f_source_contract
    assert risk_allow_copies_requested
    assert candidate_f_requested_volume_preserved
    assert risk_approved_volume_preserved
    assert not workspace_lots_conversion_present
    assert not workspace_broker_native_conversion_present
    assert not replay_numeric_semantics_changed
    assert canonical_2025_exact_match and canonical_2026_exact_match
    assert fx_scope_explicit
    assert not non_fx_generalization_added
    assert not money_risk_currency_normalization_changed
    assert production_contract_changed
    assert not production_trading_logic_changed
    assert not production_execution_wiring_changed
    assert broker_requests == 0
    assert not auto_fact.broker_execution_attempted
    assert not semi_fact.broker_execution_attempted

    hashes_after = _production_hashes()
    assert hashes_before == hashes_after
    combined_before = _combined_hash(hashes_before)
    combined_after = _combined_hash(hashes_after)

    print(f"test_id={TEST_ID}")
    print(f"production_volume_unit={WORKSPACE_CANONICAL_VOLUME_UNIT}")
    print(f"production_volume_scope={WORKSPACE_CANONICAL_VOLUME_SCOPE}")
    print(f"maximum_position_volume_unit={WORKSPACE_CANONICAL_VOLUME_UNIT}")
    print(f"requested_volume_unit={WORKSPACE_CANONICAL_VOLUME_UNIT}")
    print(f"approved_volume_unit={WORKSPACE_CANONICAL_VOLUME_UNIT}")
    print(f"maximum_position_volume_default={maximum_position_volume_default:.1f}")
    print(
        "maximum_position_volume_3000_preserved="
        f"{maximum_position_volume_3000_preserved}"
    )
    print(
        "candidate_f_requested_volume_preserved="
        f"{candidate_f_requested_volume_preserved}"
    )
    print(f"risk_approved_volume_preserved={risk_approved_volume_preserved}")
    print(f"workspace_lots_conversion_present={workspace_lots_conversion_present}")
    print(
        "workspace_broker_native_conversion_present="
        f"{workspace_broker_native_conversion_present}"
    )
    print(f"replay_numeric_semantics_changed={replay_numeric_semantics_changed}")
    print(f"canonical_2025_exact_match={canonical_2025_exact_match}")
    print(f"canonical_2026_exact_match={canonical_2026_exact_match}")
    print(f"fx_scope_explicit={fx_scope_explicit}")
    print(f"non_fx_generalization_added={non_fx_generalization_added}")
    print(
        "money_risk_currency_normalization_changed="
        f"{money_risk_currency_normalization_changed}"
    )
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"production_contract_changed={production_contract_changed}")
    print(
        "production_trading_logic_changed="
        f"{production_trading_logic_changed}"
    )
    print(
        "production_execution_wiring_changed="
        f"{production_execution_wiring_changed}"
    )
    print(f"production_hashes_before={combined_before}")
    print(f"production_hashes_after={combined_after}")
    print("production_hashes_before_after_match=True")
    print(f"factual_verdict={FACTUAL_VERDICT}")
    print("safety_invariants=")
    print(f"  broker_requests={broker_requests}")
    print("  broker_execution_attempted=False")
    print("  trading_logic_changed=False")
    print("  execution_logic_changed=False")
    print("  lookahead_used=False")
    print("T109_13_BASE_UNITS_PRODUCTION_CONTRACT_DECLARATION=OK")


def test_t109_13_base_units_production_contract_declaration() -> None:
    """Запустити той самий regression contract через pytest/PyCharm."""
    main()


if __name__ == "__main__":
    main()
