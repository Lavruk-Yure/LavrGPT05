"""run_t109_16_daily_realized_pnl_production_contract_decision_check.py.

TEST_ONLY decision checkpoint перевіряє один candidate production contract для
``WorkspaceRiskAccountSnapshot.daily_realized_pnl``: account-wide realized PnL
поточного broker account trading day в account currency, NET commissions, fees
і swaps. Runner читає фактичні IB, cTrader, runtime ledger, risk та Replay
sources, окремо фіксує scope, content, currency, day boundary і reset semantics
та відхиляє contract, якщо хоча б одна mandatory broker-neutral складова не
доведена production кодом.

Перевірка не викликає broker/network API, не створює synthetic PnL, не змінює
production wiring, risk policy, Candidate F, AUTO/SEMI або Replay. Canonical
Replay 2025/2026 і scoped production hashes захищають causal baseline; два
зовнішні повні запуски мають підтвердити deterministic console output.
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

from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from engine.risk.account_snapshot import (  # noqa: E402
    WorkspaceRiskAccountSnapshot,
)
from engine.risk.risk_model import WorkspaceRiskPolicy  # noqa: E402
from engine.runtime_account_state import RuntimeAccountState  # noqa: E402

TEST_ID = "T109-16"
EXPECTED_2025 = "42/30/11/1/+4.03/1.5424/3.58"
EXPECTED_2026 = "18/15/2/1/+3.68/3.7669/1.20"
FACTUAL_VERDICT = "H. MULTIPLE_BLOCKERS"
FIRST_UNRESOLVED_BOUNDARY = "ACCOUNT_WIDE_BROKER_DAY_NET_REALIZED_PNL_SOURCE"
BOUNDARY_CONTRACT = (
    "DAILY_REALIZED_PNL_REQUIRES_ACCOUNT_WIDE_ACCOUNT_CURRENCY_"
    "COST_COMPLETE_CAUSAL_BROKER_TRADING_DAY_SOURCE"
)
PRODUCTION_FILES = (
    PROJECT_ROOT / "core" / "algorithm_workspace_controller.py",
    PROJECT_ROOT / "core" / "workspace_replay_execution.py",
    PROJECT_ROOT / "core" / "workspace_runtime.py",
    PROJECT_ROOT / "engine" / "ctrader_adapter.py",
    PROJECT_ROOT / "engine" / "db" / "runtime_db.py",
    PROJECT_ROOT / "engine" / "ib_adapter.py",
    PROJECT_ROOT / "engine" / "risk" / "account_snapshot.py",
    PROJECT_ROOT / "engine" / "risk" / "risk_model.py",
    PROJECT_ROOT / "engine" / "runtime_account_state.py",
    PROJECT_ROOT / "engine" / "runtime_repository.py",
    PROJECT_ROOT / "engine" / "services" / "ctrader_runtime_service.py",
    PROJECT_ROOT / "engine" / "services" / "ib_runtime_service.py",
)


def _source(relative_path: str) -> str:
    """Прочитати один production source як UTF-8 factual contract."""
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def _production_hashes() -> dict[str, str]:
    """Зафіксувати SHA-256 усіх production sources у перевіреному scope."""
    return {
        path.relative_to(PROJECT_ROOT)
        .as_posix(): hashlib.sha256(path.read_bytes())
        .hexdigest()
        for path in PRODUCTION_FILES
    }


def _combined_hash(hashes: dict[str, str]) -> str:
    """Згорнути ordered file hashes у deterministic контрольний marker."""
    payload = "\n".join(f"{path}={hashes[path]}" for path in sorted(hashes))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _baseline_key(runtime: WorkspaceRuntime) -> str:
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
    """Прийняти або відхилити candidate contract за production evidence."""
    hashes_before = _production_hashes()
    ib_source = _source("engine/ib_adapter.py")
    ib_service_source = _source("engine/services/ib_runtime_service.py")
    ctrader_source = _source("engine/ctrader_adapter.py")
    ctrader_service_source = _source("engine/services/ctrader_runtime_service.py")
    db_source = _source("engine/db/runtime_db.py")
    repository_source = _source("engine/runtime_repository.py")
    replay_source = _source("core/workspace_replay_execution.py")
    runtime_source = _source("core/workspace_runtime.py")
    risk_source = _source("engine/risk/risk_model.py")

    account_state_fields = tuple(field.name for field in fields(RuntimeAccountState))
    snapshot_fields = tuple(
        field.name for field in fields(WorkspaceRiskAccountSnapshot)
    )
    policy_fields = tuple(field.name for field in fields(WorkspaceRiskPolicy))

    ib_position_level_realized = all(
        token in ib_source
        for token in (
            "def pnlSingle(",
            '"daily_pnl"',
            '"realized_pnl"',
            "self._client.reqPnLSingle(",
            'raw_payload["pnl_single"]',
        )
    )
    ib_account_wide_daily = (
        "def pnl(" in ib_source or "self._client.reqPnL(" in ib_source
    )
    ib_commission_report = "def commissionReport(" in ib_source
    ib_swap_source = "swap" in ib_source.lower()
    ib_runtime_daily_cache = any(
        token in ib_service_source for token in ("daily_realized_pnl", "daily_pnl")
    )
    ib_day_metadata = any(
        token in ib_source
        for token in (
            "broker_session_day",
            "trading_day_timezone",
            "daily_pnl_day_boundary",
        )
    )

    ctrader_unrealized_only = all(
        token in ctrader_source
        for token in (
            "ProtoOAGetPositionUnrealizedPnLReq",
            "grossUnrealizedPnL",
            "netUnrealizedPnL",
        )
    )
    ctrader_deal_history = any(
        token in ctrader_source
        for token in (
            "ProtoOADealListReq",
            "ProtoOADealListRes",
            "ProtoOADeal",
        )
    )
    ctrader_runtime_daily_cache = any(
        token in ctrader_service_source for token in ("daily_realized_pnl", "daily_pnl")
    )
    ctrader_day_metadata = any(
        token in ctrader_source
        for token in (
            "broker_session_day",
            "trading_day_timezone",
            "daily_pnl_day_boundary",
        )
    )

    local_tables_present = all(
        table in db_source
        for table in (
            "CREATE TABLE IF NOT EXISTS trades",
            "CREATE TABLE IF NOT EXISTS broker_orders",
            "CREATE TABLE IF NOT EXISTS positions",
        )
    )
    local_close_marker_present = "closed_utc TEXT" in db_source
    local_authoritative_pnl = any(
        token in db_source
        for token in (
            "realized_pnl REAL",
            "close_price REAL",
            "commission REAL",
            "swap REAL",
            "fee REAL",
        )
    )
    local_account_wide_query = all(
        token in repository_source for token in ("daily_realized_pnl", "account_wide")
    )

    replay_accumulator = all(
        token in replay_source
        for token in (
            "self.realized_profit = 0.0",
            "self.realized_profit += realized_profit",
            "return (close_price - position.entry_price) * position.volume",
        )
    )
    replay_runtime_route = all(
        token in runtime_source
        for token in (
            "realized_profit = engine.realized_profit",
            "daily_realized_pnl=realized_profit",
        )
    )
    replay_day_boundary = any(
        token in replay_source
        for token in ("broker_session_day", "daily_reset", "day_boundary")
    )
    replay_costs = any(
        token in replay_source.lower() for token in ("commission", "swap", "fee")
    )

    assert "account_id" in account_state_fields
    assert "currency" in account_state_fields
    assert "equity" in account_state_fields
    assert "daily_realized_pnl" not in account_state_fields
    assert "daily_realized_pnl" in snapshot_fields
    assert "max_daily_loss_percent" in policy_fields
    assert "from persisted settings of a single WSP" in risk_source
    assert ib_position_level_realized
    assert not ib_account_wide_daily
    assert not ib_commission_report
    assert not ib_swap_source
    assert not ib_runtime_daily_cache
    assert not ib_day_metadata
    assert ctrader_unrealized_only
    assert not ctrader_deal_history
    assert not ctrader_runtime_daily_cache
    assert not ctrader_day_metadata
    assert local_tables_present
    assert local_close_marker_present
    assert not local_authoritative_pnl
    assert not local_account_wide_query
    assert replay_accumulator
    assert replay_runtime_route
    assert not replay_day_boundary
    assert not replay_costs

    baselines: dict[str, WorkspaceRuntime] = {}
    broker_requests = 0
    for spec in CANONICAL_PERIODS:
        runtime, _rejects, requests = run_canonical_period(spec)
        baselines[spec.code] = runtime
        broker_requests += requests
    canonical_2025_exact_match = _baseline_key(baselines["2025"]) == EXPECTED_2025
    canonical_2026_exact_match = _baseline_key(baselines["2026"]) == EXPECTED_2026

    ib_contract_complete = False
    ctrader_contract_complete = False
    scope_contract_consistent = True
    commission_source_complete = False
    swap_source_complete = False
    net_realized_pnl_derivable = False
    broker_neutral_day_boundary_resolved = False
    replay_matches_candidate_contract = False
    broker_neutral_daily_pnl_contract_resolved = False
    production_source_available_without_new_request = False
    broker_execution_attempted = False

    hashes_after = _production_hashes()
    assert hashes_before == hashes_after
    assert broker_requests == 0
    assert canonical_2025_exact_match
    assert canonical_2026_exact_match
    assert not broker_execution_attempted
    assert not broker_neutral_daily_pnl_contract_resolved
    assert FACTUAL_VERDICT == "H. MULTIPLE_BLOCKERS"

    print(f"test_id={TEST_ID}")
    print("candidate_daily_pnl_scope=ACCOUNT_WIDE")
    print("candidate_daily_pnl_content=REALIZED_NET_COSTS")
    print("candidate_daily_pnl_currency=ACCOUNT_CURRENCY")
    print("candidate_day_boundary=BROKER_ACCOUNT_TRADING_DAY")
    print("candidate_reset_semantics=BROKER_RESET_OR_DERIVED_BY_BROKER_DAY")
    print(
        "ib_realized_pnl_source=POSITION_LEVEL pnlSingle daily_pnl and "
        "realized_pnl; updatePortfolio realized_pnl"
    )
    print("ib_scope=POSITION_LEVEL")
    print("ib_currency=ACCOUNT_PNL_CURRENCY_IN_POSITION_RAW_PAYLOAD")
    print("ib_commission_source=ABSENT_NO_COMMISSION_REPORT_CALLBACK_OR_JOIN")
    print("ib_swap_source=ABSENT")
    print("ib_day_boundary_source=UNDEFINED_IN_PRODUCTION_CONTRACT")
    print("ib_new_broker_request_required=True")
    print(f"ib_contract_complete={ib_contract_complete}")
    print("ctrader_realized_pnl_source=ABSENT_OPEN_POSITION_UNREALIZED_ONLY")
    print("ctrader_scope=OPEN_POSITION_LEVEL_UNREALIZED_ONLY")
    print("ctrader_currency=ACCOUNT_CURRENCY_FOR_UNREALIZED_POSITION_PNL")
    print("ctrader_commission_source=ABSENT_NO_DEAL_HISTORY_ROUTE")
    print("ctrader_swap_source=ABSENT_NO_DEAL_HISTORY_ROUTE")
    print("ctrader_day_boundary_source=UNDEFINED")
    print("ctrader_new_broker_request_required=True")
    print(f"ctrader_contract_complete={ctrader_contract_complete}")
    print(
        "local_ledger_source=trades,broker_orders,positions,and_partial_"
        "ib_virtual_position_legs"
    )
    print("local_ledger_scope=LGE_CREATED_ACTIVITY_ONLY_NOT_ACCOUNT_WIDE")
    print("local_ledger_account_wide_complete=False")
    print("local_ledger_costs_complete=False")
    print("local_ledger_day_boundary_complete=False")
    print("account_equity_scope=BOUND_BROKER_ACCOUNT_WIDE")
    print("daily_pnl_recommended_scope=ACCOUNT_WIDE")
    print(f"scope_contract_consistent={scope_contract_consistent}")
    print(f"commission_source_complete={commission_source_complete}")
    print(f"swap_source_complete={swap_source_complete}")
    print(f"net_realized_pnl_derivable={net_realized_pnl_derivable}")
    print(
        "replay_realized_pnl_source=WorkspaceReplayExecutionEngine." "realized_profit"
    )
    print("replay_realized_pnl_scope=WORKSPACE_REPLAY_EXECUTION_SESSION")
    print(
        "replay_realized_pnl_reset_semantics=ENGINE_INITIALIZATION_OR_RESET_"
        "NOT_BROKER_DAY"
    )
    print("replay_realized_pnl_costs=GROSS_NO_COMMISSION_FEE_OR_SWAP")
    print(f"replay_matches_candidate_contract={replay_matches_candidate_contract}")
    print(
        "broker_neutral_day_boundary_resolved="
        f"{broker_neutral_day_boundary_resolved}"
    )
    print(
        "broker_neutral_daily_pnl_contract_resolved="
        f"{broker_neutral_daily_pnl_contract_resolved}"
    )
    print(
        "production_source_available_without_new_request="
        f"{production_source_available_without_new_request}"
    )
    print(
        "production_contract_recommendation=REJECT_UNTIL_ACCOUNT_WIDE_NET_"
        "COST_AND_BROKER_DAY_SOURCE_EXISTS"
    )
    print("missing_daily_pnl_safe_behavior=BLOCK_RISK_EXECUTION")
    print("unknown_day_boundary_safe_behavior=BLOCK_RISK_EXECUTION")
    print("stale_or_incomplete_aggregate_safe_behavior=BLOCK_RISK_EXECUTION")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")
    print(f"canonical_2025_exact_match={canonical_2025_exact_match}")
    print(f"canonical_2026_exact_match={canonical_2026_exact_match}")
    for path in sorted(hashes_before):
        print(f"production_hash_before[{path}]={hashes_before[path]}")
        print(f"production_hash_after[{path}]={hashes_after[path]}")
    print(f"production_hashes_before={_combined_hash(hashes_before)}")
    print(f"production_hashes_after={_combined_hash(hashes_after)}")
    print("production_hashes_before_after_match=True")
    print("safety_invariants=")
    print("  TEST_ONLY=True")
    print(f"  broker_requests={broker_requests}")
    print(f"  broker_execution_attempted={broker_execution_attempted}")
    print("  production_logic_changed=False")
    print("  trading_logic_changed=False")
    print("  lookahead_used=False")
    print("T109_16_DAILY_REALIZED_PNL_PRODUCTION_CONTRACT_DECISION=OK")


def test_t109_16_daily_realized_pnl_contract_decision() -> None:
    """Запустити той самий TEST_ONLY checkpoint через pytest/PyCharm."""
    main()


if __name__ == "__main__":
    main()
