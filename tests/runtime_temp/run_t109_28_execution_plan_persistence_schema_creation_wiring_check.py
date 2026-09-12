"""T109-28 — persisted Workspace execution plan production check.

Перевіряє один вузький production boundary після GREEN T109-27:
- WorkspaceSignalRecord зберігає causal stop_loss;
- schema v10 додає nullable order_plans.stop_loss через additive migration;
- RuntimeRepository.create_order_plan лишається сумісним з manual caller;
- post-risk ALLOW зберігає trade_uid і створює один persisted WORKSPACE plan;
- повторне спостереження того самого signal не дублює plan;
- AUTO/SEMI execution_state лишається на persisted trade;
- broker order, position та broker request не створюються.

Daily PnL та open positions у цьому isolated boundary подаються TEST_ONLY як
causal snapshot values 0.0 / 0, бо їх production acquisition лишається окремим
відомим blocker-ом RoadMap109.
"""

from __future__ import annotations

import importlib
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_TEST_ROOT = PROJECT_ROOT / "tests" / "runtime_workspace"
RUNTIME_TEMP_ROOT = PROJECT_ROOT / "tests" / "runtime_temp"
for import_path in (PROJECT_ROOT, WORKSPACE_TEST_ROOT, RUNTIME_TEMP_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))


def _load(module_name: str, name: str) -> Any:
    """Завантажити production або TEST_ONLY symbol після налаштування sys.path."""
    module = importlib.import_module(module_name)
    value = getattr(module, name, None)
    if value is None:
        raise AssertionError(f"missing symbol: {module_name}.{name}")
    return value


WORKSPACE_CONTROL_MODE_AUTO = _load(
    "core.algorithm_workspace",
    "WORKSPACE_CONTROL_MODE_AUTO",
)
WORKSPACE_CONTROL_MODE_SEMI = _load(
    "core.algorithm_workspace",
    "WORKSPACE_CONTROL_MODE_SEMI",
)
WORKSPACE_DATA_MODE_BROKER = _load(
    "core.algorithm_workspace",
    "WORKSPACE_DATA_MODE_BROKER",
)
AlgorithmWorkspaceController = _load(
    "core.algorithm_workspace_controller",
    "AlgorithmWorkspaceController",
)
SessionRepository = _load("core.session_repository", "SessionRepository")
create_registered_workspace_algorithm = _load(
    "core.workspace_algorithm",
    "create_registered_workspace_algorithm",
)
WorkspaceMacdAlligatorReplayAlgorithm = _load(
    "core.workspace_alligator",
    "WorkspaceMacdAlligatorReplayAlgorithm",
)
WorkspaceMarketEvent = _load(
    "core.workspace_market_event",
    "WorkspaceMarketEvent",
)
WorkspaceRuntime = _load("core.workspace_runtime", "WorkspaceRuntime")
WorkspaceSignalRecord = _load("core.workspace_signal", "WorkspaceSignalRecord")
connect_runtime_db = _load("engine.db.runtime_db", "connect_runtime_db")
SCHEMA_VERSION = _load("engine.db.runtime_db", "SCHEMA_VERSION")
WorkspaceRiskAccountSnapshot = _load(
    "engine.risk.account_snapshot",
    "WorkspaceRiskAccountSnapshot",
)
RISK_DECISION_ALLOW = _load("engine.risk.constants", "RISK_DECISION_ALLOW")
RuntimeRepository = _load("engine.runtime_repository", "RuntimeRepository")

CANONICAL_PERIODS = _load(
    "run_t105_18_stochastic_current_bar_production_regression_check",
    "PERIODS",
)
run_canonical_period = _load(
    "run_t105_18_stochastic_current_bar_production_regression_check",
    "_run_period",
)
create_workspace_fixture = _load(
    "run_t105_18_stochastic_current_bar_production_regression_check",
    "_workspace",
)
CompletedHistoryBrokerProvider = _load(
    "run_t109_01_broker_signal_to_execution_path_anatomy_check",
    "CompletedHistoryBrokerProvider",
)
broker_events = _load(
    "run_t109_01_broker_signal_to_execution_path_anatomy_check",
    "_broker_events",
)

TEST_ID = "T109-28"
EXPECTED_2025 = "42/30/11/1/+4.03/1.5424/3.58"
EXPECTED_2026 = "18/15/2/1/+3.68/3.7669/1.20"
FACTUAL_VERDICT = "A. EXECUTION_PLAN_PERSISTENCE_SCHEMA_CREATION_WIRING_GREEN"
FIRST_UNRESOLVED_BOUNDARY = "EXECUTION_PLAN_TO_BROKER_SUBMISSION_BOUNDARY"
BOUNDARY_CONTRACT = (
    "PERSISTED_WORKSPACE_EXECUTION_PLAN_MUST_EXIST_BEFORE_ANY_BROKER_SUBMISSION"
)


class _UnusedSessionRepository(SessionRepository):
    """Не торкатися persisted Session у standalone runtime check."""


@dataclass(slots=True)
class _RuntimeEngineStub:
    """Надати controller-у лише production RuntimeRepository."""

    repository: Any


@dataclass(frozen=True, slots=True)
class ModeFact:
    """Observable result одного AUTO/SEMI execution-plan проходу."""

    control_mode: str
    record: Any
    trade_uid: str
    order_plan_uid: str
    execution_state: str
    stop_loss: float
    trade_rows: int
    order_plan_rows: int
    broker_order_rows: int
    position_rows: int
    completed_bars_delivered: int
    broker_requests: int
    broker_execution_attempted: bool


def _baseline_key(runtime: Any) -> str:
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


def _allow_snapshot(runtime: Any, first_event: Any) -> Any:
    """Подати TEST_ONLY complete snapshot лише для ізоляції boundary."""
    account_id = str(runtime.context.account_id or "").strip()
    if not account_id:
        raise AssertionError("BROKER account_id missing")
    return runtime.set_risk_account_snapshot(
        WorkspaceRiskAccountSnapshot(
            snapshot_utc=first_event.timestamp,
            workspace_uid=runtime.context.workspace_uid,
            broker=runtime.context.broker,
            account_id=account_id,
            source_mode=runtime.context.data_mode,
            equity=100_000.0,
            daily_realized_pnl=0.0,
            open_positions_count=0,
            currency="USD",
            binding_verified=True,
            synthetic=True,
        )
    )


def _run_mode(
    control_mode: str,
    events: tuple[Any, ...],
    repository: Any,
    connection: sqlite3.Connection,
) -> ModeFact:
    """Пройти completed BROKER Candidate F до persisted execution plan."""
    workspace = create_workspace_fixture(CANONICAL_PERIODS[0])
    workspace.data_mode = WORKSPACE_DATA_MODE_BROKER
    workspace.control_mode = control_mode
    workspace.account_mode = "DEMO"
    workspace.account_id = f"T10928-{control_mode}-DEMO"

    controller = AlgorithmWorkspaceController(
        repository=_UnusedSessionRepository(),
        algorithm_factory=create_registered_workspace_algorithm,
    )
    controller.set_runtime_engine(_RuntimeEngineStub(repository))
    runtime = controller.attach_workspace_runtime(workspace)
    provider = CompletedHistoryBrokerProvider(events)
    runtime.set_broker_market_provider(provider)
    runtime.begin_start()
    runtime.complete_start()
    if type(runtime.algorithm) is not WorkspaceMacdAlligatorReplayAlgorithm:
        raise AssertionError("registered Candidate F algorithm changed")
    _allow_snapshot(runtime, events[0])

    accepted = None
    observed_records = len(runtime.signal_records())
    while accepted is None:
        market_event = runtime.advance_broker_market()
        if market_event is None:
            break
        records = runtime.signal_records()
        new_records = records[observed_records:]
        observed_records = len(records)
        accepted = next(
            (
                record
                for record in new_records
                if record.accepted and record.risk_decision == RISK_DECISION_ALLOW
            ),
            None,
        )

    if accepted is None:
        raise AssertionError(f"{control_mode} risk-ALLOW signal missing")
    if accepted.stop_loss is None:
        raise AssertionError("accepted Workspace signal lost stop_loss")

    trade_rows = connection.execute(
        """
        SELECT * FROM trades
        WHERE workspace_uid = ? AND signal_uid = ?
        """,
        (accepted.workspace_uid, accepted.signal_uid),
    ).fetchall()
    if len(trade_rows) != 1:
        raise AssertionError("Workspace trade persistence is not exactly one row")
    trade = trade_rows[0]
    plan_rows = connection.execute(
        """
        SELECT * FROM order_plans
        WHERE trade_uid = ? AND source = 'WORKSPACE'
        ORDER BY id
        """,
        (trade["trade_uid"],),
    ).fetchall()
    if len(plan_rows) != 1:
        raise AssertionError("Workspace execution plan was not persisted exactly once")
    plan = plan_rows[0]

    observer = runtime.signal_record_observer
    if observer is None:
        raise AssertionError("production post-risk persistence observer missing")
    observer(accepted)
    duplicate_plan_count = int(
        connection.execute(
            """
            SELECT COUNT(*) FROM order_plans
            WHERE trade_uid = ? AND source = 'WORKSPACE'
            """,
            (trade["trade_uid"],),
        ).fetchone()[0]
    )
    if duplicate_plan_count != 1:
        raise AssertionError("Workspace execution-plan idempotency failed")

    expected_state = (
        "READY_FOR_SUBMISSION"
        if control_mode == WORKSPACE_CONTROL_MODE_AUTO
        else "PENDING_CONFIRMATION"
    )
    assert trade["execution_state"] == expected_state
    assert plan["trade_uid"] == trade["trade_uid"]
    assert plan["order_type"] == "MARKET"
    assert plan["side"] == accepted.direction
    assert plan["volume"] == accepted.approved_volume
    assert plan["stop_loss"] == accepted.stop_loss
    assert plan["source"] == "WORKSPACE"

    fact = ModeFact(
        control_mode=control_mode,
        record=accepted,
        trade_uid=str(trade["trade_uid"]),
        order_plan_uid=str(plan["order_plan_uid"]),
        execution_state=str(trade["execution_state"]),
        stop_loss=float(plan["stop_loss"]),
        trade_rows=len(trade_rows),
        order_plan_rows=duplicate_plan_count,
        broker_order_rows=int(
            connection.execute("SELECT COUNT(*) FROM broker_orders").fetchone()[0]
        ),
        position_rows=int(
            connection.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
        ),
        completed_bars_delivered=provider.completed_bars_delivered,
        broker_requests=provider.broker_requests,
        broker_execution_attempted=provider.broker_execution_attempted,
    )
    runtime.stop(f"{TEST_ID} {control_mode} completed")
    return fact


def _migration_and_manual_compatibility() -> tuple[bool, bool]:
    """Перевірити additive v9->v10 migration і manual plan compatibility."""
    with tempfile.TemporaryDirectory(prefix="t109_28_migration_") as tmp_dir:
        db_path = Path(tmp_dir) / "runtime.db"
        connection = sqlite3.connect(db_path)
        connection.execute(
            """
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_uid TEXT NOT NULL UNIQUE,
                broker TEXT NOT NULL,
                account_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                volume REAL NOT NULL,
                created_utc TEXT NOT NULL,
                source TEXT NOT NULL,
                comment TEXT NOT NULL DEFAULT '',
                workspace_uid TEXT,
                signal_uid TEXT,
                execution_origin TEXT,
                control_mode TEXT,
                execution_state TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE order_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_plan_uid TEXT NOT NULL UNIQUE,
                trade_uid TEXT NOT NULL,
                order_type TEXT NOT NULL,
                side TEXT NOT NULL,
                volume REAL NOT NULL,
                created_utc TEXT NOT NULL,
                source TEXT NOT NULL,
                FOREIGN KEY (trade_uid) REFERENCES trades (trade_uid)
            )
            """
        )
        connection.execute("PRAGMA user_version=9")
        connection.commit()
        connection.close()

        connection = connect_runtime_db(db_path)
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(order_plans)").fetchall()
        }
        migration_ok = (
            "stop_loss" in columns
            and int(connection.execute("PRAGMA user_version").fetchone()[0]) == 10
        )
        repository = RuntimeRepository(connection)
        trade_uid = repository.create_trade(
            broker="IB",
            account_id="MANUAL-COMPAT",
            symbol="EURUSD",
            side="BUY",
            volume=1000.0,
        )
        plan_uid = repository.create_order_plan(
            trade_uid=trade_uid,
            order_type="MARKET",
            side="BUY",
            volume=1000.0,
        )
        row = connection.execute(
            "SELECT * FROM order_plans WHERE order_plan_uid = ?",
            (plan_uid,),
        ).fetchone()
        manual_compatible = row is not None and row["stop_loss"] is None
        connection.close()
        return migration_ok, manual_compatible


def main() -> None:
    """Перевірити schema, persisted plan, idempotency та Replay baseline."""
    if SCHEMA_VERSION != 10:
        raise AssertionError(f"unexpected schema version: {SCHEMA_VERSION}")

    migration_ok, manual_compatible = _migration_and_manual_compatibility()
    if not migration_ok:
        raise AssertionError("additive schema v9->v10 migration failed")
    if not manual_compatible:
        raise AssertionError("manual create_order_plan compatibility changed")

    baselines: dict[str, Any] = {}
    broker_requests = 0
    for spec in CANONICAL_PERIODS:
        runtime, _rejects, requests = run_canonical_period(spec)
        baselines[spec.code] = runtime
        broker_requests += requests
    canonical_2025_exact_match = _baseline_key(baselines["2025"]) == EXPECTED_2025
    canonical_2026_exact_match = _baseline_key(baselines["2026"]) == EXPECTED_2026
    if not canonical_2025_exact_match or not canonical_2026_exact_match:
        raise AssertionError("canonical Replay baseline changed")

    replay_session = baselines["2025"].replay_session
    if replay_session is None or not replay_session.completed:
        raise AssertionError("canonical completed M15 input missing")
    events = broker_events(tuple(replay_session.events))

    with tempfile.TemporaryDirectory(prefix="t109_28_") as tmp_dir:
        db_path = Path(tmp_dir) / "runtime.db"
        connection = connect_runtime_db(db_path)
        connection.row_factory = sqlite3.Row
        repository = RuntimeRepository(connection)
        auto = _run_mode(
            WORKSPACE_CONTROL_MODE_AUTO,
            events,
            repository,
            connection,
        )
        semi = _run_mode(
            WORKSPACE_CONTROL_MODE_SEMI,
            events,
            repository,
            connection,
        )

        for fact in (auto, semi):
            assert fact.trade_rows == 1
            assert fact.order_plan_rows == 1
            assert fact.broker_execution_attempted is False
            broker_requests += fact.broker_requests

        broker_order_rows = int(
            connection.execute("SELECT COUNT(*) FROM broker_orders").fetchone()[0]
        )
        position_rows = int(
            connection.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
        )
        connection.close()

    if broker_order_rows != 0 or position_rows != 0:
        raise AssertionError("T109-28 crossed broker submission boundary")
    if broker_requests != 0:
        raise AssertionError(f"unexpected broker requests: {broker_requests}")

    print(f"{TEST_ID}_EXECUTION_PLAN_PERSISTENCE_SCHEMA_CREATION_WIRING=OK")
    print("production_change=True")
    print(f"schema_version={SCHEMA_VERSION}")
    print("signal_record_stop_loss_preserved=True")
    print("order_plan_stop_loss_persisted=True")
    print("legacy_v9_migration_preserved=True")
    print("manual_create_order_plan_backward_compatible=True")
    print("trade_uid_retained_for_execution_plan=True")
    print("workspace_execution_plan_idempotent=True")
    print("auto_execution_state=READY_FOR_SUBMISSION")
    print("semi_execution_state=PENDING_CONFIRMATION")
    print("broker_order_created=False")
    print("position_created=False")
    print("broker_submission_wiring=False")
    print(f"canonical_2025_exact_match={canonical_2025_exact_match}")
    print(f"canonical_2026_exact_match={canonical_2026_exact_match}")
    print(f"broker_requests={broker_requests}")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


if __name__ == "__main__":
    main()
