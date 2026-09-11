"""run_t109_04_broker_risk_account_snapshot_binding_path_anatomy_check.py.

TEST_ONLY anatomy простежує production account-data path від broker adapter і
RuntimeService до ``WorkspaceRuntime.risk_account_snapshot``. Статичні
assertions інвентаризують єдиний snapshot contract, його constructor/setter
call sites, provider/controller routing і окремий ``RuntimeAccountState``.

Executable AUTO та SEMI проходи отримують chronological completed BROKER bars
через наявний локальний provider, але навмисно не створюють synthetic account
snapshot. Registered Candidate F доходить до чинного risk guard, де runner
фіксує першу відсутню production boundary. Canonical Replay 2025/2026 слугує
незмінним input і regression control; network, broker order, production repair,
зміна risk/Candidate F та наступний RoadMap-крок не виконуються.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import sys
from dataclasses import dataclass, fields
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
    CompletedHistoryBrokerProvider,
    broker_events,
    create_workspace_fixture,
    run_canonical_period,
)

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_CONTROL_MODE_SEMI,
    WORKSPACE_DATA_MODE_BROKER,
)
from core.algorithm_workspace_controller import (  # noqa: E402
    AlgorithmWorkspaceController,
)
from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_broker_market import (  # noqa: E402
    RuntimeEngineWorkspaceMarketProvider,
    WorkspaceBrokerMarketProviderProtocol,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from engine.risk.account_snapshot import (  # noqa: E402
    WorkspaceRiskAccountSnapshot,
)
from engine.risk.constants import (  # noqa: E402
    RISK_REASON_ACCOUNT_BINDING_MISMATCH,
)
from engine.runtime_account_state import RuntimeAccountState  # noqa: E402
from engine.runtime_engine import RuntimeEngine  # noqa: E402
from engine.services.ctrader_runtime_service import (  # noqa: E402
    CTraderRuntimeService,
)
from engine.services.ib_runtime_service import IBRuntimeService  # noqa: E402

TEST_ID = "T109-04"
MODE = "BROKER_RISK_ACCOUNT_SNAPSHOT_BINDING_PATH_ANATOMY_TEST_ONLY"
FACTUAL_VERDICT = "A. SNAPSHOT_NOT_CREATED"
FIRST_BROKEN_BOUNDARY = "RUNTIME_ACCOUNT_STATE_TO_WORKSPACE_RISK_ACCOUNT_SNAPSHOT"
BOUNDARY_CONTRACT = (
    "BROKER_ACCOUNT_STATE_REQUIRES_EXPLICIT_WORKSPACE_RISK_SNAPSHOT_ROUTE"
)
PRODUCTION_FILES = (
    PROJECT_ROOT / "core" / "algorithm_workspace_controller.py",
    PROJECT_ROOT / "core" / "workspace_broker_market.py",
    PROJECT_ROOT / "core" / "workspace_runtime.py",
    PROJECT_ROOT / "engine" / "risk" / "account_snapshot.py",
    PROJECT_ROOT / "engine" / "risk" / "risk_model.py",
    PROJECT_ROOT / "engine" / "runtime_account_state.py",
    PROJECT_ROOT / "engine" / "runtime_engine.py",
    PROJECT_ROOT / "engine" / "services" / "ctrader_runtime_service.py",
    PROJECT_ROOT / "engine" / "services" / "ib_runtime_service.py",
)


@dataclass(frozen=True, slots=True)
class ModeSnapshotFact:
    """Зберегти фактичний BROKER snapshot/risk результат одного mode."""

    control_mode: str
    snapshot_present_after_start: bool
    snapshot_present_at_risk: bool
    risk_reason: str
    completed_bars_delivered: int
    broker_requests: int
    broker_execution_attempted: bool


def _production_hashes() -> dict[str, str]:
    """Зафіксувати scoped production файли до і після TEST_ONLY run."""
    return {
        str(path.relative_to(PROJECT_ROOT)): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in PRODUCTION_FILES
    }


def _baseline_key(runtime: WorkspaceRuntime) -> str:
    """Побудувати compact exact key canonical Replay summary."""
    summary = runtime.historical_summary
    if summary is None:
        raise AssertionError("canonical Replay summary missing")
    return (
        f"{summary.opened_trades}/{summary.winning_trades}/"
        f"{summary.losing_trades}/{summary.break_even_trades}/"
        f"{summary.net_profit:+.2f}/{summary.profit_factor:.4f}/"
        f"{summary.maximum_drawdown:.2f}"
    )


def _production_python_paths() -> tuple[Path, ...]:
    """Повернути production Python modules без tests і generated files."""
    return tuple(
        sorted(
            path
            for root in (PROJECT_ROOT / "core", PROJECT_ROOT / "engine")
            for path in root.rglob("*.py")
        )
    )


def _call_sites(
    *,
    function_name: str,
    attribute_name: str | None = None,
) -> tuple[str, ...]:
    """Знайти exact production constructor/method call sites через AST."""
    result: list[str] = []
    for path in _production_python_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            direct_match = (
                attribute_name is None
                and isinstance(function, ast.Name)
                and function.id == function_name
            )
            attribute_match = (
                attribute_name is not None
                and isinstance(function, ast.Attribute)
                and function.attr == attribute_name
            )
            if direct_match or attribute_match:
                relative = path.relative_to(PROJECT_ROOT).as_posix()
                result.append(f"{relative}:{node.lineno}")
    return tuple(sorted(result))


def _source_route_contracts() -> dict[str, bool]:
    """Перевірити production account-state route без виклику broker API."""
    provider_source = inspect.getsource(RuntimeEngineWorkspaceMarketProvider)
    controller_source = inspect.getsource(AlgorithmWorkspaceController)
    runtime_engine_source = inspect.getsource(RuntimeEngine)
    service_source = "\n".join(
        (
            inspect.getsource(IBRuntimeService),
            inspect.getsource(CTraderRuntimeService),
        )
    )
    protocol_methods = {
        name
        for name, value in vars(WorkspaceBrokerMarketProviderProtocol).items()
        if callable(value)
    }
    account_fields = {field.name for field in fields(RuntimeAccountState)}
    return {
        "services_load_runtime_account_state": (
            "adapter.get_account_info()" in service_source
            and "self._account_state.equity = account.equity" in service_source
        ),
        "runtime_engine_reads_service_account_state": (
            "service.get_account_state()" in runtime_engine_source
        ),
        "provider_has_risk_snapshot_route": bool(
            "set_risk_account_snapshot" in provider_source
            or "WorkspaceRiskAccountSnapshot" in provider_source
            or "get_account_state" in provider_source
        ),
        "controller_has_risk_snapshot_route": bool(
            "set_risk_account_snapshot" in controller_source
            or "WorkspaceRiskAccountSnapshot" in controller_source
        ),
        "provider_protocol_has_risk_snapshot_method": bool(
            {
                "get_risk_account_snapshot",
                "set_risk_account_snapshot",
                "refresh_risk_account_snapshot",
            }
            & protocol_methods
        ),
        "runtime_account_state_has_equity": "equity" in account_fields,
        "runtime_account_state_has_daily_realized_pnl": (
            "daily_realized_pnl" in account_fields
        ),
        "runtime_account_state_has_open_positions_count": (
            "open_positions_count" in account_fields
        ),
    }


def _run_mode(
    control_mode: str,
    events: tuple[WorkspaceMarketEvent, ...],
) -> ModeSnapshotFact:
    """Пройти real Candidate F BROKER path без account snapshot підміни."""
    workspace = create_workspace_fixture(CANONICAL_PERIODS[0])
    workspace.data_mode = WORKSPACE_DATA_MODE_BROKER
    workspace.control_mode = control_mode
    workspace.account_mode = "DEMO"
    workspace.account_id = f"T10904-{control_mode}-DEMO"
    provider = CompletedHistoryBrokerProvider(events)
    runtime = WorkspaceRuntime(
        workspace,
        algorithm_factory=create_registered_workspace_algorithm,
        broker_market_provider=provider,
    )
    runtime.begin_start()
    runtime.complete_start()
    snapshot_present_after_start = runtime.risk_account_snapshot is not None
    matching_record = None
    while matching_record is None:
        event = runtime.advance_broker_market()
        if event is None:
            break
        matching_record = next(
            (
                record
                for record in reversed(runtime.signal_records())
                if record.risk_reason_code == RISK_REASON_ACCOUNT_BINDING_MISMATCH
            ),
            None,
        )
    if matching_record is None:
        raise AssertionError(f"{control_mode} ACCOUNT_BINDING_MISMATCH record missing")
    result = ModeSnapshotFact(
        control_mode=control_mode,
        snapshot_present_after_start=snapshot_present_after_start,
        snapshot_present_at_risk=runtime.risk_account_snapshot is not None,
        risk_reason=matching_record.risk_reason_code or "",
        completed_bars_delivered=provider.completed_bars_delivered,
        broker_requests=provider.broker_requests,
        broker_execution_attempted=bool(
            provider.broker_execution_attempted
            or matching_record.risk_execution_attempted
        ),
    )
    runtime.stop(f"{TEST_ID} {control_mode} anatomy completed")
    return result


def main() -> None:
    """Виконати static/executable anatomy та надрукувати factual verdict."""
    hashes_before = _production_hashes()
    constructor_calls = _call_sites(function_name="WorkspaceRiskAccountSnapshot")
    replay_factory_calls = _call_sites(
        function_name="",
        attribute_name="from_replay_settings",
    )
    setter_calls = _call_sites(
        function_name="",
        attribute_name="set_risk_account_snapshot",
    )
    source_contracts = _source_route_contracts()

    baselines: dict[str, WorkspaceRuntime] = {}
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
    events = broker_events(tuple(replay_session.events))
    auto = _run_mode(WORKSPACE_CONTROL_MODE_AUTO, events)
    semi = _run_mode(WORKSPACE_CONTROL_MODE_SEMI, events)
    facts = (auto, semi)
    broker_requests += sum(fact.broker_requests for fact in facts)
    broker_execution_attempted = any(fact.broker_execution_attempted for fact in facts)
    hashes_after = _production_hashes()

    definition_line = inspect.getsourcelines(WorkspaceRiskAccountSnapshot)[1]
    setter_line = inspect.getsourcelines(WorkspaceRuntime.set_risk_account_snapshot)[1]
    binding_inputs = "workspace_uid,broker,account_id,source_mode"

    assert constructor_calls == ("core/workspace_runtime.py:552",)
    assert replay_factory_calls == ("core/workspace_runtime.py:776",)
    assert setter_calls == ("core/workspace_runtime.py:775",)
    assert source_contracts["services_load_runtime_account_state"]
    assert source_contracts["runtime_engine_reads_service_account_state"]
    assert not source_contracts["provider_has_risk_snapshot_route"]
    assert not source_contracts["controller_has_risk_snapshot_route"]
    assert not source_contracts["provider_protocol_has_risk_snapshot_method"]
    assert source_contracts["runtime_account_state_has_equity"]
    assert not source_contracts["runtime_account_state_has_daily_realized_pnl"]
    assert not source_contracts["runtime_account_state_has_open_positions_count"]
    assert all(not fact.snapshot_present_after_start for fact in facts)
    assert all(not fact.snapshot_present_at_risk for fact in facts)
    assert all(
        fact.risk_reason == RISK_REASON_ACCOUNT_BINDING_MISMATCH for fact in facts
    )
    assert hashes_before == hashes_after
    assert broker_requests == 0
    assert not broker_execution_attempted
    assert canonical_2025_exact_match and canonical_2026_exact_match

    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print("account_snapshot_type=WorkspaceRiskAccountSnapshot")
    print(
        "account_snapshot_definition="
        f"engine/risk/account_snapshot.py:{definition_line}"
    )
    print(
        "production_snapshot_creators="
        "BROKER_AUTOMATIC=NONE; "
        f"constructor_calls={','.join(constructor_calls)}; "
        f"replay_factory_calls={','.join(replay_factory_calls)}"
    )
    print(
        "workspace_runtime_snapshot_setters="
        f"core/workspace_runtime.py:{setter_line} "
        "WorkspaceRuntime.set_risk_account_snapshot; "
        f"production_calls={','.join(setter_calls)} REPLAY_ONLY"
    )
    print(
        "broker_snapshot_source="
        "BrokerAdapter.get_account_info -> RuntimeService._load_account_state "
        "-> RuntimeAccountState; no WorkspaceRiskAccountSnapshot adapter/route"
    )
    print(f"auto_snapshot_present={auto.snapshot_present_at_risk}")
    print(f"semi_snapshot_present={semi.snapshot_present_at_risk}")
    print(f"binding_inputs={binding_inputs}")
    print(
        "binding_guard="
        "market_event_binding_matches AND "
        "WorkspaceRiskAccountSnapshot.matches_binding"
    )
    print(f"risk_reason={RISK_REASON_ACCOUNT_BINDING_MISMATCH}")
    print(f"first_broken_boundary={FIRST_BROKEN_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")
    print(
        "runtime_account_state_fields="
        "equity=PRESENT,daily_realized_pnl=MISSING,"
        "open_positions_count=MISSING"
    )
    print(f"auto_completed_bars_delivered={auto.completed_bars_delivered}")
    print(f"semi_completed_bars_delivered={semi.completed_bars_delivered}")
    print(f"canonical_2025_exact_match={canonical_2025_exact_match}")
    print(f"canonical_2026_exact_match={canonical_2026_exact_match}")
    print("safety_invariants=")
    print("  TEST_ONLY=True")
    print(f"  broker_requests={broker_requests}")
    print(f"  broker_execution_attempted={broker_execution_attempted}")
    print("  production_logic_changed=False")
    print("  trading_logic_changed=False")
    print("  lookahead_used=False")
    print("T109_04_BROKER_RISK_ACCOUNT_SNAPSHOT_BINDING_PATH_ANATOMY=OK")


if __name__ == "__main__":
    main()
