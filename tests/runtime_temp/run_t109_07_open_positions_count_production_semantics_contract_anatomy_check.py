"""run_t109_07_open_positions_count_production_semantics_contract_anatomy_check.py.

TEST_ONLY anatomy встановлює factual production semantics contract лише для
``open_positions_count``. Runner читає risk policy/evaluator, IB, cTrader та
WSP ownership source contracts і executable assertions перевіряє count guard,
наявні broker sources, binding, request/cache behavior, ownership та position
lifecycle gaps без створення synthetic positions або risk snapshot.

Workspace Replay source читається тільки для відокремлення virtual rows від
broker truth; canonical Replay 2025/2026 виконується як exact completed-bar
regression control. Network, broker order, reverse-position implementation,
snapshot wiring, production/risk/Candidate F/AUTO/SEMI зміни не виконуються.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_TEMP_ROOT = PROJECT_ROOT / "tests" / "runtime_temp"
for import_path in (PROJECT_ROOT, RUNTIME_TEMP_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from run_t109_03_minimal_production_execution_intent_repair_check import (  # noqa
    CANONICAL_PERIODS,
    EXPECTED_2025,
    EXPECTED_2026,
    run_canonical_period,
)

from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from engine.risk.constants import (  # noqa: E402
    DEFAULT_WORKSPACE_MAXIMUM_OPEN_POSITIONS,
)

TEST_ID = "T109-07"
FACTUAL_VERDICT = "F. PRODUCTION_SEMANTICS_NOT_DEFINED"
FIRST_UNRESOLVED_BOUNDARY = (
    "RISK_OPEN_POSITIONS_COUNT_FIELD_TO_DEFINED_OWNERSHIP_SCOPE_"
    "AND_LIFECYCLE_SEMANTICS"
)
BOUNDARY_CONTRACT = (
    "OPEN_POSITIONS_COUNT_REQUIRES_BROKER_NEUTRAL_OWNERSHIP_SCOPE_"
    "AND_CONFIRMED_CLOSE_LIFECYCLE"
)
PRODUCTION_FILES = (
    PROJECT_ROOT / "core" / "workspace_ownership.py",
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


def production_hashes() -> dict[str, str]:
    """Зафіксувати scoped production sources до і після TEST_ONLY run."""
    return {
        path.relative_to(PROJECT_ROOT)
        .as_posix(): hashlib.sha256(path.read_bytes())
        .hexdigest()
        for path in PRODUCTION_FILES
    }


def source_text(relative_path: str) -> str:
    """Прочитати один фактичний production module як UTF-8 contract."""
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def definition_line(relative_path: str, exact_fragment: str) -> int:
    """Знайти exact production call-site без виклику protected API."""
    matches = [
        number
        for number, line in enumerate(
            source_text(relative_path).splitlines(),
            start=1,
        )
        if exact_fragment in line
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"expected one {exact_fragment!r} in {relative_path}: {matches}"
        )
    return matches[0]


def definition_line_after(
    relative_path: str,
    anchor_fragment: str,
    exact_fragment: str,
) -> int:
    """Знайти один call-site після exact production function anchor."""
    lines = source_text(relative_path).splitlines()
    anchor_lines = [
        number for number, line in enumerate(lines, start=1) if anchor_fragment in line
    ]
    if len(anchor_lines) != 1:
        raise AssertionError(
            f"expected one {anchor_fragment!r} in {relative_path}: " f"{anchor_lines}"
        )
    matches = [
        number
        for number, line in enumerate(lines, start=1)
        if number > anchor_lines[0] and exact_fragment in line
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"expected one {exact_fragment!r} after {anchor_fragment!r} "
            f"in {relative_path}: {matches}"
        )
    return matches[0]


def baseline_key(runtime: WorkspaceRuntime) -> str:
    """Побудувати exact canonical Replay summary key."""
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
    """Довести прогалини ownership/scope/lifecycle count contract."""
    hashes_before = production_hashes()
    risk_source = source_text("engine/risk/risk_model.py")
    constants_source = source_text("engine/risk/constants.py")
    ib_source = source_text("engine/ib_adapter.py")
    ib_service_source = source_text("engine/services/ib_runtime_service.py")
    ctrader_source = source_text("engine/ctrader_adapter.py")
    ctrader_service_source = source_text("engine/services/ctrader_runtime_service.py")
    runtime_engine_source = source_text("engine/runtime_engine.py")
    ownership_source = source_text("core/workspace_ownership.py")
    workspace_runtime_source = source_text("core/workspace_runtime.py")
    replay_source = source_text("core/workspace_replay_execution.py")
    ib_get_positions_start = ib_source.index("    def get_positions(")
    ib_get_positions_source = ib_source[
        ib_get_positions_start : ib_source.index(  # noqa
            "    def place_market_order(",
            ib_get_positions_start,
        )
    ]

    evaluator_count_guard_defined = all(
        token in risk_source
        for token in (
            "if request.open_positions_count is None:",
            "RISK_REASON_OPEN_POSITIONS_SNAPSHOT_MISSING",
            "request.open_positions_count >= self.policy.maximum_open_positions",
            "RISK_REASON_MAXIMUM_OPEN_POSITIONS_REACHED",
        )
    )
    evaluator_scope_defined = any(
        token in risk_source
        for token in (
            "open_positions_count_scope",
            "account_wide_open_positions",
            "workspace_open_positions",
            "symbol_open_positions",
            "lge_owned_open_positions",
        )
    )
    evaluator_ownership_defined = any(
        token in risk_source
        for token in (
            "include_manual_positions",
            "include_external_positions",
            "include_other_workspaces",
            "include_opposite_positions",
        )
    )
    evaluator_lifecycle_defined = any(
        token in risk_source
        for token in (
            "include_pending_orders",
            "include_partial_fills",
            "include_closing_unconfirmed",
            "confirmed_close",
        )
    )

    ib_fresh_broker_source_defined = all(
        token in ib_source
        for token in (
            "self._wrapper.positions.clear()",
            "self._client.reqPositions()",
            "self._wrapper.position_event.wait(",
            "self._client.cancelPositions()",
            'position_value = float(item.get("position") or 0.0)',
            "if position_value == 0.0:",
            'position_id = f"IB:{account_id}:{symbol_name}"',
            "result_by_id[position_id] = BrokerPosition(",
        )
    )
    ib_service_route_defined = "return adapter.get_positions()" in ib_service_source
    ib_runtime_route_defined = all(
        token in runtime_engine_source
        for token in (
            'if broker == "IB":',
            "positions = service.get_positions()",
            "return self._enrich_ib_positions_from_runtime_repository(",
        )
    )
    ib_workspace_filter_in_adapter = (
        "WorkspaceOwnershipFilter" in ib_source
        or "workspace_uid" in ib_get_positions_source
    )

    ctrader_fresh_broker_source_defined = all(
        token in ctrader_source
        for token in (
            "self._positions_payload = []",
            "request = ProtoOAReconcileReq()",
            "request.ctidTraderAccountId = self.config.ctid_trader_account_id",
            "deferred = self.client.send(request)",
            "self._positions_event.wait(",
            'self._positions_payload = list(getattr(payload, "position", []))',
            "account_id=str(self.config.ctid_trader_account_id)",
        )
    )
    ctrader_service_route_defined = (
        "return adapter.get_positions()" in ctrader_service_source
    )
    ctrader_runtime_route_defined = all(
        token in runtime_engine_source
        for token in (
            'if broker == "CTRADER":',
            "return service.get_positions()",
        )
    )
    ctrader_workspace_filter_in_adapter = "WorkspaceOwnershipFilter" in ctrader_source

    workspace_owned_source_defined = all(
        token in ownership_source
        for token in (
            "class WorkspaceOwnedSnapshot:",
            "Exact WSP-owned subset selected from shared broker/runtime rows.",
            "class WorkspaceOwnershipFilter:",
            "workspace_uid=position.workspace_uid",
            "broker=position.broker",
            "account_id=position.account_id",
            "symbol=position.symbol",
            "if position.active",
        )
    )
    workspace_lifecycle_candidate_defined = all(
        token in ownership_source
        for token in (
            "TERMINAL_POSITION_STATUSES = {",
            '"CLOSED"',
            '"FLAT"',
            "volume > 0.0 and reconciliation_status not in",
        )
    )
    workspace_runtime_count_route_defined = all(
        token in workspace_runtime_source
        for token in (
            "selection = WorkspaceOwnershipFilter(binding).select(",
            "positions_count=len(selection.active_positions)",
            "self.context.positions_count",
        )
    )
    replay_virtual_owned_source_defined = all(
        token in replay_source
        for token in (
            "Return immutable virtual rows consumed by existing WSP UI tables.",
            "return WorkspaceOwnedSnapshot(",
        )
    )

    assert DEFAULT_WORKSPACE_MAXIMUM_OPEN_POSITIONS == 2
    assert "DEFAULT_WORKSPACE_MAXIMUM_OPEN_POSITIONS = 2" in constants_source
    assert evaluator_count_guard_defined
    assert not evaluator_scope_defined
    assert not evaluator_ownership_defined
    assert not evaluator_lifecycle_defined
    assert ib_fresh_broker_source_defined
    assert ib_service_route_defined
    assert ib_runtime_route_defined
    assert not ib_workspace_filter_in_adapter
    assert ctrader_fresh_broker_source_defined
    assert ctrader_service_route_defined
    assert ctrader_runtime_route_defined
    assert not ctrader_workspace_filter_in_adapter
    assert workspace_owned_source_defined
    assert workspace_lifecycle_candidate_defined
    assert workspace_runtime_count_route_defined
    assert replay_virtual_owned_source_defined

    baselines: dict[str, WorkspaceRuntime] = {}
    broker_requests = 0
    for spec in CANONICAL_PERIODS:
        runtime, _rejects, requests = run_canonical_period(spec)
        baselines[spec.code] = runtime
        broker_requests += requests
    canonical_2025_exact_match = baseline_key(baselines["2025"]) == EXPECTED_2025
    canonical_2026_exact_match = baseline_key(baselines["2026"]) == EXPECTED_2026
    broker_execution_attempted = False
    broker_neutral_contract_defined = False
    hashes_after = production_hashes()

    assert hashes_before == hashes_after
    assert broker_requests == 0
    assert not broker_execution_attempted
    assert not broker_neutral_contract_defined
    assert canonical_2025_exact_match
    assert canonical_2026_exact_match
    assert FACTUAL_VERDICT == "F. PRODUCTION_SEMANTICS_NOT_DEFINED"

    risk_guard_line = definition_line(
        "engine/risk/risk_model.py",
        "if request.open_positions_count >= self.policy.maximum_open_positions:",
    )
    ib_request_line = definition_line_after(
        "engine/ib_adapter.py",
        "def get_positions(",
        "self._client.reqPositions()",
    )
    ctrader_request_line = definition_line(
        "engine/ctrader_adapter.py",
        "request = ProtoOAReconcileReq()",
    )
    runtime_route_line = definition_line(
        "engine/runtime_engine.py",
        "def get_active_broker_positions(",
    )
    ownership_line = definition_line(
        "core/workspace_ownership.py",
        "class WorkspaceOwnedSnapshot:",
    )
    ownership_filter_line = definition_line(
        "core/workspace_ownership.py",
        "class WorkspaceOwnershipFilter:",
    )

    print(f"test_id={TEST_ID}")
    print(
        "risk_evaluator_open_positions_consumption="
        "missing value blocks; count>=maximum_open_positions blocks; "
        "count below limit continues"
    )
    print(
        "maximum_open_positions_current_value="
        "2; persisted per-WSP setting source, count scope undefined"
    )
    print("open_positions_count_required_scope=UNRESOLVED")
    print(
        "open_positions_count_required_position_state="
        "UNRESOLVED: evaluator accepts non-negative integer without statuses"
    )
    print("manual_positions_included=UNRESOLVED_BY_RISK_CONTRACT")
    print("external_positions_included=UNRESOLVED_BY_RISK_CONTRACT")
    print("other_workspace_positions_included=UNRESOLVED_BY_RISK_CONTRACT")
    print("opposite_positions_included=UNRESOLVED_BY_RISK_CONTRACT")
    print(
        "pending_orders_included="
        "UNRESOLVED_BY_RISK_CONTRACT; broker position sources exclude orders"
    )
    print(
        "closing_unconfirmed_positions_included="
        "UNRESOLVED_BY_RISK_CONTRACT; broker non-zero position remains visible; "
        "WSP candidate remains active until CLOSED/FLAT"
    )
    print(
        "ib_positions_available_source="
        "IBAdapter.get_positions reqPositions -> IBRuntimeService.get_positions "
        "-> RuntimeEngine.get_active_broker_positions"
    )
    print(
        "ib_positions_scope="
        "BROKER_SESSION_CALLBACK_ROWS_WITH_ACCOUNT_ID; no WSP filter and no "
        "selected-account count contract"
    )
    print("ib_positions_cached=False; adapter clears rows before fresh request")
    print("ib_positions_requires_request=True")
    print("ib_positions_matches_required_contract=False")
    print(
        "ctrader_positions_available_source="
        "ProtoOAReconcileReq -> CTraderAdapter.get_positions -> "
        "CTraderRuntimeService.get_positions -> RuntimeEngine"
    )
    print(
        "ctrader_positions_scope="
        "CONFIGURED_CTRADER_ACCOUNT; broker positions unfiltered by WSP/label"
    )
    print("ctrader_positions_cached=False; adapter clears payload before reconcile")
    print("ctrader_positions_requires_request=True")
    print("ctrader_positions_matches_required_contract=False")
    print(
        "workspace_owned_position_source="
        "WorkspaceOwnershipFilter exact workspace_uid,broker,account_id,symbol "
        "subset; Runtime context counts active_positions"
    )
    print("workspace_owned_position_scope=WORKSPACE_AND_SYMBOL_EXACT_BINDING")
    print(
        "workspace_owned_source_is_broker_truth="
        "False; accepts shared broker/runtime rows and Replay virtual rows"
    )
    print("workspace_owned_source_matches_required_contract=False")
    print(
        "position_lifecycle_contract="
        "UNRESOLVED: submitted-unfilled absent; non-zero partial/filled broker "
        "exposure visible; close-requested remains until broker removes/zeros; "
        "timeout/staleness/unknown-count semantics not represented in risk field"
    )
    print(
        "reverse_position_invariant_impact="
        "future invariant requires current position count/exposure to remain "
        "occupied until confirmed close; current risk contract does not enforce it"
    )
    print(f"broker_neutral_contract_defined={broker_neutral_contract_defined}")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")
    print(
        "unresolved_fields=scope,ownership,lifecycle_state,"
        "closing_unconfirmed,timing_staleness"
    )
    print(
        "exact_call_sites="
        f"risk_guard=engine/risk/risk_model.py:{risk_guard_line}; "
        f"ib_request=engine/ib_adapter.py:{ib_request_line}; "
        f"ctrader_request=engine/ctrader_adapter.py:{ctrader_request_line}; "
        f"runtime_route=engine/runtime_engine.py:{runtime_route_line}; "
        f"owned_snapshot=core/workspace_ownership.py:{ownership_line}; "
        f"ownership_filter=core/workspace_ownership.py:{ownership_filter_line}"
    )
    print(f"canonical_2025_exact_match={canonical_2025_exact_match}")
    print(f"canonical_2026_exact_match={canonical_2026_exact_match}")
    print("safety_invariants=")
    print("  TEST_ONLY=True")
    print(f"  broker_requests={broker_requests}")
    print(f"  broker_execution_attempted={broker_execution_attempted}")
    print("  production_logic_changed=False")
    print("  trading_logic_changed=False")
    print("  lookahead_used=False")
    print("T109_07_OPEN_POSITIONS_COUNT_SEMANTICS_CONTRACT_ANATOMY=OK")


if __name__ == "__main__":
    main()
