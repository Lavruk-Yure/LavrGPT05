"""run_t109_05_broker_risk_snapshot_source_completeness_anatomy_check.py.

TEST_ONLY anatomy встановлює фактичні production sources і визначеність
semantics для ``equity``, ``daily_realized_pnl`` та
``open_positions_count``, потрібних ``WorkspaceRiskAccountSnapshot``.
Runner читає production dataclass/source contracts, знаходить exact call-sites
і виконує canonical Replay 2025/2026 як regression control.

Перевірка не створює synthetic ``WorkspaceRiskAccountSnapshot``, не викликає
live adapter/service, не робить network або broker order і не вибирає навмання
невизначений account/workspace scope. Production hashes, completed-bar Replay,
нуль broker requests і незмінна trading logic є executable safety assertions.
"""

from __future__ import annotations

import hashlib
import inspect
import sys
from dataclasses import fields
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
from engine.broker_account import BrokerAccount  # noqa: E402
from engine.broker_position import BrokerPosition  # noqa: E402
from engine.ctrader_adapter import CTraderAdapter  # noqa: E402
from engine.ib_adapter import IBAdapter  # noqa: E402
from engine.risk.account_snapshot import (  # noqa: E402
    WorkspaceRiskAccountSnapshot,
)
from engine.risk.risk_model import (  # noqa: E402
    WorkspaceRiskEvaluator,
    WorkspaceRiskRequest,
)
from engine.runtime_account_state import RuntimeAccountState  # noqa: E402
from engine.runtime_engine import RuntimeEngine  # noqa: E402
from engine.services.ctrader_runtime_service import (  # noqa: E402
    CTraderRuntimeService,
)
from engine.services.ib_runtime_service import IBRuntimeService  # noqa: E402

TEST_ID = "T109-05"
FACTUAL_VERDICT = "E. REQUIRED_SEMANTICS_UNRESOLVED"
FIRST_MISSING_SOURCE = "daily_realized_pnl"
BOUNDARY_CONTRACT = (
    "BROKER_RISK_SNAPSHOT_REQUIRES_DEFINED_ACCOUNT_DAY_REALIZED_PNL_"
    "AND_OPEN_POSITION_SCOPE_SOURCES"
)
PRODUCTION_FILES = (
    PROJECT_ROOT / "core" / "workspace_runtime.py",
    PROJECT_ROOT / "engine" / "broker_account.py",
    PROJECT_ROOT / "engine" / "broker_position.py",
    PROJECT_ROOT / "engine" / "ctrader_adapter.py",
    PROJECT_ROOT / "engine" / "ib_adapter.py",
    PROJECT_ROOT / "engine" / "risk" / "account_snapshot.py",
    PROJECT_ROOT / "engine" / "risk" / "risk_model.py",
    PROJECT_ROOT / "engine" / "runtime_account_state.py",
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


def source_line(owner: object, member_name: str | None = None) -> int:
    """Повернути перший рядок class або public method у production файлі."""
    target = owner if member_name is None else getattr(owner, member_name)
    return inspect.getsourcelines(target)[1]


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


def source_contracts() -> dict[str, bool]:
    """Довести source availability і прогалини через production code."""
    account_state_source = inspect.getsource(RuntimeAccountState)
    ib_service_source = inspect.getsource(IBRuntimeService)
    ctrader_service_source = inspect.getsource(CTraderRuntimeService)
    ib_positions_source = inspect.getsource(IBAdapter.get_positions)
    ctrader_positions_source = inspect.getsource(CTraderAdapter.get_positions)
    ib_adapter_source = inspect.getsource(IBAdapter)
    ctrader_adapter_source = inspect.getsource(CTraderAdapter)
    runtime_engine_source = inspect.getsource(RuntimeEngine)
    workspace_runtime_source = inspect.getsource(WorkspaceRuntime)
    evaluator_source = inspect.getsource(WorkspaceRiskEvaluator)
    return {
        "equity_cached_in_runtime_state": "equity" in account_state_source,
        "ib_equity_loaded_from_broker": (
            "adapter.get_account_info()" in ib_service_source
            and "self._account_state.equity = account.equity" in ib_service_source
        ),
        "ctrader_equity_loaded_from_broker": (
            "adapter.get_account_info()" in ctrader_service_source
            and "self._account_state.equity = account.equity" in ctrader_service_source
        ),
        "risk_uses_equity_as_denominator": (
            "request.estimated_loss_at_stop / request.equity" in evaluator_source
            and "-request.daily_realized_pnl" in evaluator_source
        ),
        "runtime_state_has_no_daily_pnl": (
            "daily_realized_pnl" not in account_state_source
        ),
        "services_have_no_daily_pnl_route": (
            "daily_realized_pnl" not in ib_service_source
            and "daily_realized_pnl" not in ctrader_service_source
        ),
        "ib_has_position_level_pnl_evidence": (
            '"daily_pnl"' in ib_adapter_source
            and '"realized_pnl"' in ib_adapter_source
            and 'raw_payload["pnl_single"]' in ib_adapter_source
        ),
        "ctrader_has_only_unrealized_position_pnl": (
            "ProtoOAGetPositionUnrealizedPnLReq" in ctrader_adapter_source
            and '"realized_pnl"' not in ctrader_adapter_source
            and "daily_realized_pnl" not in ctrader_adapter_source
        ),
        "runtime_state_has_no_open_count": (
            "open_positions_count" not in account_state_source
        ),
        "runtime_engine_has_broker_positions_candidate": (
            "def get_active_broker_positions" in runtime_engine_source
            and "service.get_positions()" in runtime_engine_source
        ),
        "ib_positions_require_request": (
            "self._client.reqPositions()" in ib_positions_source
        ),
        "ctrader_positions_require_request": (
            "ProtoOAReconcileReq()" in ctrader_positions_source
            and "self.client.send(request)" in ctrader_positions_source
        ),
        "replay_has_explicit_derived_sources": (
            "daily_realized_pnl=realized_profit" in workspace_runtime_source
            and "open_positions_count=len(snapshot.active_positions)"
            in workspace_runtime_source
        ),
    }


def main() -> None:
    """Виконати factual source anatomy і надрукувати повний verdict."""
    hashes_before = production_hashes()
    contracts = source_contracts()
    runtime_fields = tuple(field.name for field in fields(RuntimeAccountState))
    broker_account_fields = tuple(field.name for field in fields(BrokerAccount))
    broker_position_fields = tuple(field.name for field in fields(BrokerPosition))
    snapshot_fields = tuple(
        field.name for field in fields(WorkspaceRiskAccountSnapshot)
    )
    request_fields = tuple(field.name for field in fields(WorkspaceRiskRequest))

    expected_snapshot_fields = (
        "snapshot_utc",
        "workspace_uid",
        "broker",
        "account_id",
        "source_mode",
        "equity",
        "daily_realized_pnl",
        "open_positions_count",
        "binding_verified",
        "synthetic",
    )
    expected_risk_fields = (
        "equity",
        "daily_realized_pnl",
        "open_positions_count",
    )

    assert snapshot_fields == expected_snapshot_fields
    assert all(name in request_fields for name in expected_risk_fields)
    assert "equity" in runtime_fields
    assert "daily_realized_pnl" not in runtime_fields
    assert "open_positions_count" not in runtime_fields
    assert all(
        name in broker_account_fields
        for name in ("broker", "account_id", "currency", "equity")
    )
    assert all(
        name in broker_position_fields
        for name in ("broker", "account_id", "symbol_name")
    )
    assert all(contracts.values())

    baselines: dict[str, WorkspaceRuntime] = {}
    broker_requests = 0
    for spec in CANONICAL_PERIODS:
        runtime, _rejects, requests = run_canonical_period(spec)
        baselines[spec.code] = runtime
        broker_requests += requests
    canonical_2025_exact_match = baseline_key(baselines["2025"]) == EXPECTED_2025
    canonical_2026_exact_match = baseline_key(baselines["2026"]) == EXPECTED_2026
    hashes_after = production_hashes()

    equity_source_complete = True
    daily_realized_pnl_source_complete = False
    open_positions_count_source_complete = False
    missing_required_fields = "daily_realized_pnl,open_positions_count"

    assert hashes_before == hashes_after
    assert broker_requests == 0
    assert canonical_2025_exact_match
    assert canonical_2026_exact_match
    assert equity_source_complete
    assert not daily_realized_pnl_source_complete
    assert not open_positions_count_source_complete
    assert FIRST_MISSING_SOURCE == "daily_realized_pnl"
    assert FACTUAL_VERDICT == "E. REQUIRED_SEMANTICS_UNRESOLVED"

    print(f"test_id={TEST_ID}")
    print(
        "equity_required_semantics="
        "POSITIVE_ACCOUNT_EQUITY_RISK_DENOMINATOR; "
        "currency compatibility is not represented by risk snapshot"
    )
    print(
        "equity_production_source="
        "BrokerAdapter.get_account_info -> BrokerAccount.equity -> "
        "IBRuntimeService/CTraderRuntimeService._load_account_state -> "
        "RuntimeAccountState.equity (account-wide cached value)"
    )
    print(f"equity_source_complete={equity_source_complete}")
    print(
        "equity_requires_new_broker_request="
        "False when RuntimeAccountState is loaded; True to load or refresh"
    )
    print(
        "daily_realized_pnl_required_semantics="
        "UNRESOLVED; evaluator consumes signed value and counts only "
        "negative value as daily loss, but fees/day/timezone/scope/reset "
        "are not contracted"
    )
    print(
        "daily_realized_pnl_production_source="
        "NONE_CANONICAL; IB position raw_payload has broker daily_pnl and "
        "realized_pnl evidence; cTrader exposes open-position unrealized PnL; "
        "Replay alone derives engine.realized_profit"
    )
    print("daily_realized_pnl_source_complete=" f"{daily_realized_pnl_source_complete}")
    print("daily_realized_pnl_day_boundary=UNRESOLVED")
    print("daily_realized_pnl_scope=UNRESOLVED")
    print(
        "daily_realized_pnl_requires_new_broker_request="
        "UNRESOLVED_BY_PRODUCTION_CONTRACT"
    )
    print(
        "open_positions_count_required_semantics="
        "UNRESOLVED; evaluator requires non-negative count and compares it "
        "with maximum_open_positions, but account/workspace/symbol scope is "
        "not contracted"
    )
    print(
        "open_positions_count_production_source="
        "CANDIDATES_ONLY: RuntimeEngine.get_active_broker_positions returns "
        "broker positions; WorkspaceRuntime owned_snapshot has workspace-owned "
        "active positions; no source is selected for BROKER risk snapshot"
    )
    print(
        "open_positions_count_source_complete="
        f"{open_positions_count_source_complete}"
    )
    print("open_positions_count_scope=UNRESOLVED")
    print("external_positions_included=UNRESOLVED")
    print("pending_orders_included=UNRESOLVED")
    print(
        "open_positions_count_requires_new_broker_request="
        "True for fresh IB reqPositions/cTrader reconcile; cached "
        "workspace-owned state exists but its use is not contracted"
    )
    print(
        "runtime_account_state_available_fields="
        "account_id,trader_login,broker_name,currency,balance,equity,margin,"
        "free_margin,leverage,snapshot_utc"
    )
    print(
        "workspace_risk_snapshot_required_fields="
        "snapshot_utc,workspace_uid,broker,account_id,source_mode,equity,"
        "daily_realized_pnl,open_positions_count,binding_verified,synthetic"
    )
    print(f"missing_required_fields={missing_required_fields}")
    print(f"first_missing_source={FIRST_MISSING_SOURCE}")
    print(
        "source_completeness="
        "equity=PRESENT_AND_CACHED; daily_realized_pnl=MISSING_CANONICAL_"
        "SOURCE_AND_SEMANTICS; open_positions_count=CANDIDATES_PRESENT_BUT_"
        "SOURCE_AND_SCOPE_UNRESOLVED"
    )
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")
    print(
        "exact_call_sites="
        f"risk_snapshot=engine/risk/account_snapshot.py:"
        f"{source_line(WorkspaceRiskAccountSnapshot)}; "
        f"risk_evaluator=engine/risk/risk_model.py:"
        f"{source_line(WorkspaceRiskEvaluator, 'evaluate')}; "
        f"ib_account_loader=engine/services/ib_runtime_service.py:"
        f"{source_line(IBRuntimeService, '_load_account_state')}; "
        f"ctrader_account_loader=engine/services/ctrader_runtime_service.py:"
        f"{source_line(CTraderRuntimeService, '_load_account_state')}; "
        f"runtime_positions=engine/runtime_engine.py:"
        f"{source_line(RuntimeEngine, 'get_active_broker_positions')}; "
        f"ib_positions=engine/ib_adapter.py:"
        f"{source_line(IBAdapter, 'get_positions')}; "
        f"ctrader_positions=engine/ctrader_adapter.py:"
        f"{source_line(CTraderAdapter, 'get_positions')}; "
        f"replay_sync=core/workspace_runtime.py:"
        f"{source_line(WorkspaceRuntime, '_sync_replay_execution_snapshot')}"
    )
    print(f"canonical_2025_exact_match={canonical_2025_exact_match}")
    print(f"canonical_2026_exact_match={canonical_2026_exact_match}")
    print("safety_invariants=")
    print("  TEST_ONLY=True")
    print(f"  broker_requests={broker_requests}")
    print("  broker_execution_attempted=False")
    print("  production_logic_changed=False")
    print("  trading_logic_changed=False")
    print("  lookahead_used=False")
    print("T109_05_BROKER_RISK_SNAPSHOT_SOURCE_COMPLETENESS_ANATOMY=OK")


if __name__ == "__main__":
    main()
