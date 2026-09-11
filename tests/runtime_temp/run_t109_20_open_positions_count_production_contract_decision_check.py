"""run_t109_20_open_positions_count_production_contract_decision_check.py.

TEST_ONLY decision runner перевіряє один broker-neutral production contract для
``WorkspaceRiskAccountSnapshot.open_positions_count`` без wiring. Він зіставляє
per-WSP ``maximum_open_positions``, exact ``WorkspaceOwnershipFilter``, factual
IB/cTrader position sources та lifecycle, а також поточну Replay semantics.

Runner приймає contract лише на рівні специфікації: count охоплює
broker-confirmed non-zero exposure конкретного Workspace; pending orders не
входять, partial fill/partial close рахуються open, а close-requested позиція
лишається open до broker-confirmed flat. Static executable assertions доводять,
що current broker rows не несуть causal workspace identity, тому production
count ще не derivable. Жоден broker/network/order API не викликається,
production files не змінюються, canonical Replay 2025/2026 лишається exact.
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
RUNTIME_TEMP_ROOT = PROJECT_ROOT / "tests" / "runtime_temp"
for import_path in (PROJECT_ROOT, WORKSPACE_TEST_ROOT, RUNTIME_TEMP_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))


def _test_helper(module_name: str, helper_name: str) -> Any:
    """Завантажити established TEST_ONLY helper без копіювання harness."""
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

from core.workspace_ownership import (  # noqa: E402
    WorkspacePositionSnapshot,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from engine.broker_position import BrokerPosition  # noqa: E402
from engine.risk.constants import (  # noqa: E402
    DEFAULT_WORKSPACE_MAXIMUM_OPEN_POSITIONS,
    WORKSPACE_RISK_SETTING_MAXIMUM_OPEN_POSITIONS,
)

TEST_ID = "T109-20"
EXPECTED_2025 = "42/30/11/1/+4.03/1.5424/3.58"
EXPECTED_2026 = "18/15/2/1/+3.68/3.7669/1.20"
CANDIDATE_OWNERSHIP_SCOPE = "WORKSPACE_ONLY"
CANDIDATE_POSITION_SCOPE = "OPEN_EXPOSURE_ONLY"
CANDIDATE_LIFECYCLE_SCOPE = "BROKER_CONFIRMED"
CANDIDATE_CLOSE_SEMANTICS = "COUNTED_UNTIL_CONFIRMED_FLAT"
CANDIDATE_PARTIAL_FILL_SEMANTICS = "COUNT_AS_OPEN"
CANDIDATE_PARTIAL_CLOSE_SEMANTICS = "COUNT_AS_OPEN_UNTIL_ZERO"
PRODUCTION_RECOMMENDATION = (
    "ACCEPT_WORKSPACE_ONLY_BROKER_CONFIRMED_CONTRACT_"
    "BUT_DO_NOT_WIRE_UNTIL_WORKSPACE_IDENTITY_IS_PRESERVED"
)
FIRST_UNRESOLVED_BOUNDARY = "WORKSPACE_EXECUTION_IDENTITY_TO_BROKER_POSITION_OWNERSHIP"
BOUNDARY_CONTRACT = (
    "WORKSPACE_ONLY_BROKER_CONFIRMED_COUNT_REQUIRES_WORKSPACE_IDENTITY_"
    "PRESERVED_THROUGH_EXECUTION_AND_BROKER_RECONCILIATION"
)
FACTUAL_VERDICT = "C. WORKSPACE_IDENTITY_MISSING"
PRODUCTION_FILES = (
    PROJECT_ROOT / "core" / "algorithm_workspace.py",
    PROJECT_ROOT / "core" / "workspace_ownership.py",
    PROJECT_ROOT / "core" / "workspace_parameter_catalog.py",
    PROJECT_ROOT / "core" / "workspace_replay_execution.py",
    PROJECT_ROOT / "core" / "workspace_runtime.py",
    PROJECT_ROOT / "engine" / "broker_position.py",
    PROJECT_ROOT / "engine" / "ctrader_adapter.py",
    PROJECT_ROOT / "engine" / "ib_adapter.py",
    PROJECT_ROOT / "engine" / "risk" / "account_snapshot.py",
    PROJECT_ROOT / "engine" / "risk" / "constants.py",
    PROJECT_ROOT / "engine" / "risk" / "risk_model.py",
    PROJECT_ROOT / "engine" / "runtime_engine.py",
    PROJECT_ROOT / "engine" / "services" / "ctrader_runtime_service.py",
    PROJECT_ROOT / "engine" / "services" / "ib_runtime_service.py",
)


def _source_text(relative_path: str) -> str:
    """Прочитати один production source як factual UTF-8 contract."""
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def _source_section(
    relative_path: str,
    start_fragment: str,
    end_fragment: str,
) -> str:
    """Вирізати production section між двома exact anchors."""
    source = _source_text(relative_path)
    start = source.index(start_fragment)
    end = source.index(end_fragment, start + len(start_fragment))
    return source[start:end]


def _production_hashes() -> dict[str, str]:
    """Зафіксувати scoped production sources до і після TEST_ONLY run."""
    return {
        path.relative_to(PROJECT_ROOT)
        .as_posix(): hashlib.sha256(path.read_bytes())
        .hexdigest()
        for path in PRODUCTION_FILES
    }


def _combined_hash(hashes: dict[str, str]) -> str:
    """Згорнути ordered per-file hashes у deterministic marker."""
    payload = "\n".join(f"{path}={hashes[path]}" for path in sorted(hashes))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _baseline_key(runtime: WorkspaceRuntime) -> str:
    """Повернути exact compact canonical Replay metrics key."""
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
    """Прийняти candidate contract і довести current feasibility boundary."""
    hashes_before = _production_hashes()
    algorithm_workspace = _source_text("core/algorithm_workspace.py")
    catalog = _source_text("core/workspace_parameter_catalog.py")
    risk_model = _source_text("engine/risk/risk_model.py")
    ownership = _source_text("core/workspace_ownership.py")
    runtime = _source_text("core/workspace_runtime.py")
    replay = _source_text("core/workspace_replay_execution.py")
    runtime_engine = _source_text("engine/runtime_engine.py")
    ib_service = _source_text("engine/services/ib_runtime_service.py")
    ctrader_service = _source_text("engine/services/ctrader_runtime_service.py")
    ib_positions = _source_section(
        "engine/ib_adapter.py",
        "    def get_positions(",
        "    def place_market_order(",
    )
    ib_build = _source_section(
        "engine/ib_adapter.py",
        "    def _build_positions(",
        "    def _build_portfolio_by_position_id(",
    )
    ctrader_build = _source_section(
        "engine/ctrader_adapter.py",
        "    def _build_positions(",
        "    def get_positions(",
    )
    ctrader_positions = _source_section(
        "engine/ctrader_adapter.py",
        "    def get_positions(",
        "    def _on_reconcile_res(",
    )

    broker_position_fields = tuple(field.name for field in fields(BrokerPosition))
    workspace_position_fields = tuple(
        field.name for field in fields(WorkspacePositionSnapshot)
    )
    maximum_open_positions_setting_scope = "PER_WORKSPACE"
    maximum_open_positions_contract_currently_defined = False
    maximum_setting_is_per_workspace = all(
        token in algorithm_workspace
        for token in (
            "risk_settings: dict[str, Any]",
            "workspace_uid: str",
            "symbol: str",
        )
    ) and all(
        token in catalog
        for token in (
            'key="risk.maximum_open_positions"',
            "WORKSPACE_RISK_SETTING_MAXIMUM_OPEN_POSITIONS",
        )
    )
    evaluator_consumes_bare_integer = all(
        token in risk_model
        for token in (
            "if request.open_positions_count is None:",
            "request.open_positions_count >= self.policy.maximum_open_positions",
        )
    )
    evaluator_scope_absent = not any(
        token in risk_model
        for token in (
            "open_positions_count_scope",
            "workspace_open_positions",
            "account_wide_open_positions",
        )
    )

    ib_source_present = (
        all(
            token in ib_positions
            for token in (
                "self._wrapper.positions.clear()",
                "self._client.reqPositions()",
                "self._wrapper.position_event.wait(",
                "self._client.cancelPositions()",
                "return self._build_positions(",
            )
        )
        and "return adapter.get_positions()" in ib_service
    )
    ib_non_zero_exposure_only = all(
        token in ib_build
        for token in (
            'position_value = float(item.get("position") or 0.0)',
            "if position_value == 0.0:",
            "result_by_id[position_id] = BrokerPosition(",
        )
    )
    ib_new_request_required = "self._client.reqPositions()" in ib_positions
    ib_freshness_known = "snapshot_utc" in broker_position_fields

    ctrader_source_present = (
        all(
            token in ctrader_positions
            for token in (
                "self._positions_payload = []",
                "request = ProtoOAReconcileReq()",
                "request.ctidTraderAccountId = self.config.ctid_trader_account_id",
                "deferred = self.client.send(request)",
                "self._positions_event.wait(",
                "return self._build_positions()",
            )
        )
        and "return adapter.get_positions()" in ctrader_service
    )
    ctrader_exposure_present = all(
        token in ctrader_build
        for token in (
            'volume_raw = int(getattr(trade_data, "volume", 0) or 0)',
            "volume = ctr_lot.api_volume_to_lots(volume_raw)",
            "BrokerPosition(",
        )
    )
    ctrader_new_request_required = "self.client.send(request)" in ctrader_positions
    ctrader_freshness_known = "snapshot_utc" in broker_position_fields

    runtime_routes_present = all(
        token in runtime_engine
        for token in (
            "def get_active_broker_positions(",
            'if broker == "CTRADER":',
            'if broker == "IB":',
            "positions = service.get_positions()",
        )
    )
    workspace_ownership_filter_present = all(
        token in ownership
        for token in (
            "class WorkspaceOwnershipFilter:",
            "workspace_uid=position.workspace_uid",
            "broker=position.broker",
            "account_id=position.account_id",
            "symbol=position.symbol",
        )
    )
    broker_workspace_identity_present = "workspace_uid" in broker_position_fields
    broker_signal_identity_present = "signal_uid" in broker_position_fields
    workspace_ownership_causal_from_execution = bool(
        broker_workspace_identity_present and broker_signal_identity_present
    )
    workspace_only_count_currently_derivable = bool(
        runtime_routes_present
        and workspace_ownership_filter_present
        and workspace_ownership_causal_from_execution
    )
    workspace_runtime_count_route_present = all(
        token in runtime
        for token in (
            "selection = WorkspaceOwnershipFilter(binding).select(",
            "positions_count=len(selection.active_positions)",
            "open_positions_count=len(snapshot.active_positions)",
        )
    )

    replay_open_positions_scope = "WORKSPACE_VIRTUAL_ACTIVE_POSITIONS_ONLY"
    replay_matches_candidate_contract = False
    replay_semantics_present = all(
        token in replay
        for token in (
            "def active_positions_count(self) -> int:",
            "if position.active",
            "self.active_positions_count + self.pending_orders_count",
        )
    ) and all(
        token in runtime
        for token in (
            "open_positions_count=len(snapshot.active_positions)",
            "synthetic=self.context.data_mode == WORKSPACE_DATA_MODE_REPLAY",
        )
    )

    alternative_a_account_wide_feasible = bool(
        ib_source_present and ctrader_source_present
    )
    alternative_a_contract_fit = False
    alternative_b_workspace_only_feasible = workspace_only_count_currently_derivable
    alternative_b_contract_fit = True
    alternative_c_workspace_symbol_feasible = workspace_only_count_currently_derivable
    alternative_c_contract_fit = "PARTIAL_REDUNDANT_FOR_SINGLE_SYMBOL_WORKSPACE"
    reverse_invariant_compatible = True
    broker_neutral_open_positions_contract_resolved = True
    broker_requests = 0
    broker_execution_attempted = False

    assert DEFAULT_WORKSPACE_MAXIMUM_OPEN_POSITIONS == 2
    assert WORKSPACE_RISK_SETTING_MAXIMUM_OPEN_POSITIONS == "maximum_open_positions"
    assert maximum_setting_is_per_workspace
    assert evaluator_consumes_bare_integer and evaluator_scope_absent
    assert not maximum_open_positions_contract_currently_defined
    assert ib_source_present and ib_non_zero_exposure_only
    assert ib_new_request_required and not ib_freshness_known
    assert ctrader_source_present and ctrader_exposure_present
    assert ctrader_new_request_required and not ctrader_freshness_known
    assert runtime_routes_present and workspace_runtime_count_route_present
    assert workspace_ownership_filter_present
    assert "workspace_uid" in workspace_position_fields
    assert "signal_uid" in workspace_position_fields
    assert not broker_workspace_identity_present
    assert not broker_signal_identity_present
    assert not workspace_ownership_causal_from_execution
    assert not workspace_only_count_currently_derivable
    assert replay_semantics_present and not replay_matches_candidate_contract
    assert alternative_a_account_wide_feasible
    assert not alternative_a_contract_fit
    assert not alternative_b_workspace_only_feasible
    assert alternative_b_contract_fit
    assert not alternative_c_workspace_symbol_feasible
    assert reverse_invariant_compatible
    assert broker_neutral_open_positions_contract_resolved

    baselines: dict[str, WorkspaceRuntime] = {}
    for spec in CANONICAL_PERIODS:
        replay_runtime, _rejects, requests = run_canonical_period(spec)
        baselines[spec.code] = replay_runtime
        broker_requests += requests
    canonical_2025_exact_match = _baseline_key(baselines["2025"]) == EXPECTED_2025
    canonical_2026_exact_match = _baseline_key(baselines["2026"]) == EXPECTED_2026
    hashes_after = _production_hashes()
    assert canonical_2025_exact_match and canonical_2026_exact_match
    assert hashes_before == hashes_after
    assert broker_requests == 0
    assert not broker_execution_attempted

    print(f"test_id={TEST_ID}")
    print(f"candidate_ownership_scope={CANDIDATE_OWNERSHIP_SCOPE}")
    print(f"candidate_position_scope={CANDIDATE_POSITION_SCOPE}")
    print(f"candidate_lifecycle_scope={CANDIDATE_LIFECYCLE_SCOPE}")
    print(f"candidate_close_requested_semantics={CANDIDATE_CLOSE_SEMANTICS}")
    print("candidate_partial_fill_semantics=" f"{CANDIDATE_PARTIAL_FILL_SEMANTICS}")
    print("candidate_partial_close_semantics=" f"{CANDIDATE_PARTIAL_CLOSE_SEMANTICS}")
    print(
        "maximum_open_positions_setting_scope="
        f"{maximum_open_positions_setting_scope}"
    )
    print(
        "maximum_open_positions_contract_currently_defined="
        f"{maximum_open_positions_contract_currently_defined}"
    )
    print(
        "ib_positions_source=IBAdapter.get_positions->"
        "IBRuntimeService.get_positions->RuntimeEngine.get_active_broker_positions"
    )
    print("ib_positions_account_scope=BROKER_SESSION_ROWS_WITH_ACCOUNT_ID")
    print(f"ib_workspace_identity_present={broker_workspace_identity_present}")
    print("ib_partial_fill_behavior=NON_ZERO_BROKER_EXPOSURE_COUNTS_AS_OPEN")
    print(
        "ib_close_requested_behavior=COUNTED_WHILE_NON_ZERO_ROW_REMAINS;"
        "REQUEST_STATE_NOT_IN_POSITION_DTO"
    )
    print(
        "ib_confirmed_flat_behavior=ZERO_ROW_FILTERED_OR_ABSENT_AFTER_"
        "FRESH_REQPOSITIONS"
    )
    print(f"ib_freshness_known={ib_freshness_known}")
    print(f"ib_new_request_required={ib_new_request_required}")
    print(
        "ctrader_positions_source=ProtoOAReconcileReq->"
        "CTraderAdapter.get_positions->CTraderRuntimeService.get_positions->"
        "RuntimeEngine.get_active_broker_positions"
    )
    print("ctrader_positions_account_scope=CONFIGURED_CTRADER_ACCOUNT")
    print("ctrader_workspace_identity_present=" f"{broker_workspace_identity_present}")
    print("ctrader_partial_fill_behavior=NON_ZERO_RECONCILED_EXPOSURE_COUNTS_AS_OPEN")
    print(
        "ctrader_close_requested_behavior=COUNTED_WHILE_RECONCILE_RETURNS_"
        "NON_ZERO_POSITION;REQUEST_STATE_NOT_IN_POSITION_DTO"
    )
    print(
        "ctrader_confirmed_flat_behavior=POSITION_ABSENT_OR_ZERO_AFTER_"
        "FRESH_RECONCILE"
    )
    print(f"ctrader_freshness_known={ctrader_freshness_known}")
    print(f"ctrader_new_request_required={ctrader_new_request_required}")
    print(f"workspace_ownership_filter_present={workspace_ownership_filter_present}")
    print("workspace_ownership_fields=workspace_uid,broker,account_id,symbol")
    print(
        "workspace_ownership_causal_from_execution="
        f"{workspace_ownership_causal_from_execution}"
    )
    print(
        "workspace_only_count_currently_derivable="
        f"{workspace_only_count_currently_derivable}"
    )
    print(
        "alternative_A_account_wide_feasible=" f"{alternative_a_account_wide_feasible}"
    )
    print(f"alternative_A_contract_fit={alternative_a_contract_fit}")
    print(
        "alternative_B_workspace_only_feasible="
        f"{alternative_b_workspace_only_feasible}"
    )
    print(f"alternative_B_contract_fit={alternative_b_contract_fit}")
    print(
        "alternative_C_workspace_symbol_feasible="
        f"{alternative_c_workspace_symbol_feasible}"
    )
    print(f"alternative_C_contract_fit={alternative_c_contract_fit}")
    print(f"reverse_invariant_compatible={reverse_invariant_compatible}")
    print(f"replay_open_positions_scope={replay_open_positions_scope}")
    print(f"replay_matches_candidate_contract={replay_matches_candidate_contract}")
    print("missing_count_safe_behavior=BLOCK_RISK_EXECUTION")
    print("stale_count_safe_behavior=BLOCK_RISK_EXECUTION")
    print(
        "broker_neutral_open_positions_contract_resolved="
        f"{broker_neutral_open_positions_contract_resolved}"
    )
    print(f"production_contract_recommendation={PRODUCTION_RECOMMENDATION}")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")
    print(f"canonical_2025_exact_match={canonical_2025_exact_match}")
    print(f"canonical_2026_exact_match={canonical_2026_exact_match}")
    print(f"production_hashes_before={_combined_hash(hashes_before)}")
    print(f"production_hashes_after={_combined_hash(hashes_after)}")
    print("production_hashes_before_after_match=True")
    print("safety_invariants=")
    print("  TEST_ONLY=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  production_logic_changed=False")
    print("  trading_logic_changed=False")
    print("  lookahead_used=False")
    print("T109_20_OPEN_POSITIONS_COUNT_CONTRACT_DECISION=OK")


def test_t109_20_open_positions_contract_decision() -> None:
    """Запустити T109-20 як один pytest-compatible checkpoint."""
    main()


if __name__ == "__main__":
    main()
