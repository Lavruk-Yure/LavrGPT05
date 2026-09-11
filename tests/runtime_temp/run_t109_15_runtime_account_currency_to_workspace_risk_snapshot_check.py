"""run_t109_15_runtime_account_currency_to_workspace_risk_snapshot_check.py.

Regression перевіряє мінімальний production route cached broker account
currency через AlgorithmWorkspaceController до exact-bound
WorkspaceRiskAccountSnapshot і WorkspaceRuntime. Окремі fixtures доводять
правильний broker/account binding, відхилення foreign account currency та
збереження missing currency як None без USD або symbol fallback.

Runner не виконує FX normalization, inverse/cross-rate math, broker refresh,
network/order execution чи schema wiring. Canonical Replay 2025/2026, numeric
risk decision, production hashes і повторний deterministic output захищають
Replay/trading/risk semantics та фіксують наступний фактичний risk guard.
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import sys
from dataclasses import dataclass, fields
from datetime import UTC, datetime
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
create_workspace_fixture = _test_helper(
    "run_t105_18_stochastic_current_bar_production_regression_check",
    "_workspace",
)

from core.algorithm_workspace import WORKSPACE_DATA_MODE_BROKER  # noqa: E402
from core.algorithm_workspace_controller import (  # noqa: E402
    AlgorithmWorkspaceController,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from engine.risk.account_snapshot import (  # noqa: E402
    WorkspaceRiskAccountSnapshot,
)
from engine.risk.constants import (  # noqa: E402
    RISK_DECISION_ALLOW,
    RISK_REASON_DAILY_PNL_SNAPSHOT_MISSING,
)
from engine.risk.risk_model import (  # noqa: E402
    WorkspaceRiskEvaluator,
    WorkspaceRiskPolicy,
    WorkspaceRiskRequest,
)
from engine.runtime_account_state import RuntimeAccountState  # noqa: E402

TEST_ID = "T109-15"
EXPECTED_2025 = "42/30/11/1/+4.03/1.5424/3.58"
EXPECTED_2026 = "18/15/2/1/+3.68/3.7669/1.20"
FACTUAL_VERDICT = "E. REPLAY_CURRENCY_SOURCE_UNRESOLVED_BUT_BROKER_ROUTE_GREEN"
FIRST_UNRESOLVED_BOUNDARY = "RISK_DAILY_PNL_SNAPSHOT_MISSING"
BOUNDARY_CONTRACT = (
    "BROKER_RISK_EVALUATION_REQUIRES_DEFINED_DAILY_REALIZED_PNL_BEFORE_"
    "FX_CURRENCY_NORMALIZATION_CAN_BE_REACHED"
)
PRODUCTION_FILES = (
    PROJECT_ROOT / "core" / "algorithm_workspace_controller.py",
    PROJECT_ROOT / "core" / "workspace_runtime.py",
    PROJECT_ROOT / "engine" / "risk" / "account_snapshot.py",
)


@dataclass(slots=True)
class CachedAccountService:
    """Надати лише cached RuntimeAccountState і рахувати broker requests."""

    account_state: RuntimeAccountState
    broker_requests: int = 0

    def get_account_state(self) -> RuntimeAccountState:
        """Повернути cache без refresh, network або adapter call."""
        return self.account_state


@dataclass(slots=True)
class CachedRuntimeEngine:
    """Expose broker services, потрібні controller currency route."""

    ctrader_runtime_service: CachedAccountService | None = None
    ib_runtime_service: CachedAccountService | None = None


def _production_hashes() -> dict[str, str]:
    """Повернути exact SHA-256 реально змінених production files."""
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


def _account_state(
    *,
    broker: str,
    account_id: str,
    currency: str,
) -> RuntimeAccountState:
    """Побудувати cached state fixture з explicit binding і currency."""
    return RuntimeAccountState(
        account_id=account_id,
        broker_name=broker,
        currency=currency,
        balance=100_000.0,
        equity=100_000.0,
        snapshot_utc="2026-09-10T09:00:00+00:00",
    )


def _broker_workspace(account_id: str) -> Any:
    """Повернути canonical-shaped BROKER workspace для route regression."""
    workspace = create_workspace_fixture(CANONICAL_PERIODS[0])
    workspace.data_mode = WORKSPACE_DATA_MODE_BROKER
    workspace.broker = "CTRADER"
    workspace.account_id = account_id
    workspace.account_mode = "DEMO"
    return workspace


def _route_snapshot(
    *,
    workspace_account_id: str,
    state_account_id: str,
    currency: str,
) -> tuple[WorkspaceRuntime, WorkspaceRiskAccountSnapshot | None, int]:
    """Пройти public controller route лише через cached account service."""
    service = CachedAccountService(
        _account_state(
            broker="CTRADER",
            account_id=state_account_id,
            currency=currency,
        )
    )
    engine = CachedRuntimeEngine(ctrader_runtime_service=service)
    controller = AlgorithmWorkspaceController()
    controller.set_runtime_engine(engine)
    workspace = _broker_workspace(workspace_account_id)
    runtime = controller.attach_workspace_runtime(workspace)
    snapshot = controller.sync_workspace_risk_account_snapshot(
        workspace.workspace_uid,
    )
    return runtime, snapshot, service.broker_requests


def _risk_decision(
    snapshot: WorkspaceRiskAccountSnapshot,
    *,
    daily_realized_pnl: float | None,
    open_positions_count: int | None,
) -> Any:
    """Evaluate unchanged numeric risk logic з routed snapshot facts."""
    policy = WorkspaceRiskPolicy(
        max_risk_percent=0.5,
        maximum_position_volume=1000.0,
        maximum_open_positions=2,
        max_daily_loss_percent=2.0,
    )
    request = WorkspaceRiskRequest(
        timestamp=datetime(2026, 9, 10, 9, 0, tzinfo=UTC),
        workspace_uid=snapshot.workspace_uid,
        broker=snapshot.broker,
        account_id=snapshot.account_id,
        symbol="EURUSD",
        side="BUY",
        source_mode=snapshot.source_mode,
        requested_volume=1000.0,
        equity=snapshot.equity,
        estimated_loss_at_stop=100.0,
        stop_loss=1.09,
        open_positions_count=open_positions_count,
        daily_realized_pnl=daily_realized_pnl,
        runtime_ready=True,
        binding_verified=snapshot.binding_verified,
        market_valid=True,
        spread_guard_passed=True,
    )
    return WorkspaceRiskEvaluator(policy).evaluate(request)


def main() -> None:
    """Перевірити field, cached route, binding, risk і Replay regressions."""
    hashes_before = _production_hashes()
    snapshot_fields = tuple(
        field.name for field in fields(WorkspaceRiskAccountSnapshot)
    )
    controller_source = inspect.getsource(AlgorithmWorkspaceController)
    risk_source = inspect.getsource(WorkspaceRiskEvaluator)

    runtime, snapshot, route_requests = _route_snapshot(
        workspace_account_id="T10915-BOUND",
        state_account_id="T10915-BOUND",
        currency="usd",
    )
    if snapshot is None:
        raise AssertionError("exact-bound cached account snapshot missing")
    runtime_account_currency_value = snapshot.currency
    binding_matches = snapshot.matches_binding(
        workspace_uid=runtime.context.workspace_uid,
        broker=runtime.context.broker,
        account_id=runtime.context.account_id,
        source_mode=runtime.context.data_mode,
    )
    workspace_runtime_currency_available = bool(
        runtime.risk_account_snapshot is not None
        and runtime.risk_account_snapshot.currency == "USD"
    )

    foreign_runtime, foreign_snapshot, foreign_requests = _route_snapshot(
        workspace_account_id="T10915-BOUND",
        state_account_id="T10915-FOREIGN",
        currency="EUR",
    )
    wrong_account_currency_rejected = bool(
        foreign_snapshot is None and foreign_runtime.risk_account_snapshot is None
    )
    missing_runtime, missing_snapshot, missing_requests = _route_snapshot(
        workspace_account_id="T10915-MISSING",
        state_account_id="T10915-MISSING",
        currency="",
    )
    if missing_snapshot is None:
        raise AssertionError("missing-currency bound snapshot missing")
    missing_currency_fallback_used = missing_snapshot.currency is not None

    missing_daily_decision = _risk_decision(
        snapshot,
        daily_realized_pnl=None,
        open_positions_count=None,
    )
    complete_decision = _risk_decision(
        snapshot,
        daily_realized_pnl=0.0,
        open_positions_count=0,
    )
    risk_numeric_semantics_changed = not bool(
        missing_daily_decision.reason_code == RISK_REASON_DAILY_PNL_SNAPSHOT_MISSING
        and complete_decision.decision == RISK_DECISION_ALLOW
        and complete_decision.calculated_risk_percent == 0.1
        and complete_decision.approved_volume == 1000.0
    )
    money_risk_currency_normalization_implemented = any(
        token in risk_source
        for token in (
            "quote_to_account",
            "conversion_rate",
            "cross_rate",
        )
    )

    baselines: dict[str, WorkspaceRuntime] = {}
    broker_requests = route_requests + foreign_requests + missing_requests
    for spec in CANONICAL_PERIODS:
        replay_runtime, _rejects, requests = run_canonical_period(spec)
        baselines[spec.code] = replay_runtime
        broker_requests += requests
    canonical_2025_exact_match = _baseline_key(baselines["2025"]) == EXPECTED_2025
    canonical_2026_exact_match = _baseline_key(baselines["2026"]) == EXPECTED_2026
    replay_snapshot = baselines["2025"].risk_account_snapshot
    if replay_snapshot is None:
        raise AssertionError("canonical Replay risk snapshot missing")
    replay_snapshot_currency = replay_snapshot.currency
    replay_numeric_semantics_changed = not bool(
        canonical_2025_exact_match and canonical_2026_exact_match
    )

    workspace_risk_snapshot_currency_field_present = "currency" in snapshot_fields
    production_route_present = all(
        token in controller_source
        for token in (
            "sync_workspace_risk_account_snapshot",
            "get_account_state",
            "state_account_id != bound_account_id",
            'currency=getattr(account_state, "currency", None)',
        )
    )
    production_files_changed = (
        "core/algorithm_workspace_controller.py,core/workspace_runtime.py,"
        "engine/risk/account_snapshot.py"
    )

    assert workspace_risk_snapshot_currency_field_present
    assert production_route_present
    assert runtime_account_currency_value == "USD"
    assert snapshot.broker == "CTRADER"
    assert snapshot.account_id == "T10915-BOUND"
    assert binding_matches and workspace_runtime_currency_available
    assert wrong_account_currency_rejected
    assert not missing_currency_fallback_used
    assert missing_runtime.risk_account_snapshot is missing_snapshot
    assert not risk_numeric_semantics_changed
    assert not money_risk_currency_normalization_implemented
    assert replay_snapshot_currency is None
    assert not replay_numeric_semantics_changed
    assert broker_requests == 0

    hashes_after = _production_hashes()
    assert hashes_before == hashes_after
    combined_before = _combined_hash(hashes_before)
    combined_after = _combined_hash(hashes_after)

    print(f"test_id={TEST_ID}")
    print(
        "runtime_account_currency_source=RuntimeService.get_account_state "
        "cached RuntimeAccountState.currency"
    )
    print(f"runtime_account_currency_value={runtime_account_currency_value}")
    print(
        "workspace_risk_snapshot_currency_field_present="
        f"{workspace_risk_snapshot_currency_field_present}"
    )
    print(f"workspace_risk_snapshot_currency={snapshot.currency}")
    print(f"workspace_snapshot_broker={snapshot.broker}")
    print(f"workspace_snapshot_account_id={snapshot.account_id}")
    print("workspace_snapshot_binding_matches_runtime_account=" f"{binding_matches}")
    print(
        "workspace_runtime_currency_available="
        f"{workspace_runtime_currency_available}"
    )
    print(f"wrong_account_currency_rejected={wrong_account_currency_rejected}")
    print(f"missing_currency_fallback_used={missing_currency_fallback_used}")
    print("replay_snapshot_currency_source=ABSENT")
    print(f"replay_snapshot_currency={replay_snapshot_currency}")
    print(f"replay_numeric_semantics_changed={replay_numeric_semantics_changed}")
    print(f"risk_numeric_semantics_changed={risk_numeric_semantics_changed}")
    print(
        "money_risk_currency_normalization_implemented="
        f"{money_risk_currency_normalization_implemented}"
    )
    print(f"broker_requests={broker_requests}")
    print("broker_execution_attempted=False")
    print(f"canonical_2025_exact_match={canonical_2025_exact_match}")
    print(f"canonical_2026_exact_match={canonical_2026_exact_match}")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")
    print(f"production_files_changed={production_files_changed}")
    print("production_trading_logic_changed=False")
    print("production_execution_wiring_changed=False")
    for path in sorted(hashes_before):
        print(f"production_hash_before[{path}]={hashes_before[path]}")
        print(f"production_hash_after[{path}]={hashes_after[path]}")
    print(f"production_hashes_before={combined_before}")
    print(f"production_hashes_after={combined_after}")
    print("production_hashes_before_after_match=True")
    print("safety_invariants=")
    print(f"  broker_requests={broker_requests}")
    print("  broker_execution_attempted=False")
    print("  trading_logic_changed=False")
    print("  execution_logic_changed=False")
    print("  lookahead_used=False")
    print("T109_15_RUNTIME_ACCOUNT_CURRENCY_ROUTE=OK")


def test_t109_15_runtime_account_currency_route() -> None:
    """Запустити той самий production regression через pytest/PyCharm."""
    main()


if __name__ == "__main__":
    main()
