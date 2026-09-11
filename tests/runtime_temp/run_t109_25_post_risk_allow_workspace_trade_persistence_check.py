"""T109-25 — post-risk ALLOW -> persisted Workspace trade production check.

Перевіряє один вузький production boundary після GREEN T109-24:
- completed BROKER Candidate F signal проходить existing risk до ALLOW;
- AlgorithmWorkspaceController до будь-якого broker submission атомарно створює
  або повторно використовує один ``trades`` row за ``workspace_uid + signal_uid``;
- AUTO отримує ``READY_FOR_SUBMISSION``;
- SEMI отримує ``PENDING_CONFIRMATION``;
- повторне спостереження того самого accepted signal не створює duplicate;
- order plan, broker order, position та broker request цим кроком не створюються.

Daily PnL та open positions для цього isolated boundary подаються TEST_ONLY як
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


def _test_helper(module_name: str, helper_name: str) -> Any:
    """Завантажити established TEST_ONLY helper без дублювання harness."""
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
CompletedHistoryBrokerProvider = _test_helper(
    "run_t109_01_broker_signal_to_execution_path_anatomy_check",
    "CompletedHistoryBrokerProvider",
)
broker_events = _test_helper(
    "run_t109_01_broker_signal_to_execution_path_anatomy_check",
    "_broker_events",
)

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_CONTROL_MODE_SEMI,
    WORKSPACE_DATA_MODE_BROKER,
)
from core.algorithm_workspace_controller import (  # noqa: E402
    AlgorithmWorkspaceController,
)
from core.session_repository import SessionRepository  # noqa: E402
from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_alligator import (  # noqa: E402
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402
from engine.db.runtime_db import connect_runtime_db  # noqa: E402
from engine.risk.account_snapshot import (  # noqa: E402
    WorkspaceRiskAccountSnapshot,
)
from engine.risk.constants import RISK_DECISION_ALLOW  # noqa: E402
from engine.runtime_repository import RuntimeRepository  # noqa: E402

TEST_ID = "T109-25"
EXPECTED_2025 = "42/30/11/1/+4.03/1.5424/3.58"
EXPECTED_2026 = "18/15/2/1/+3.68/3.7669/1.20"
FACTUAL_VERDICT = "A. POST_RISK_WORKSPACE_TRADE_PERSISTENCE_GREEN"
FIRST_UNRESOLVED_BOUNDARY = "WORKSPACE_TRADE_TO_EXECUTION_PLAN"
BOUNDARY_CONTRACT = (
    "PERSISTED_WORKSPACE_TRADE_MUST_PRECEDE_ANY_EXECUTION_PLAN_OR_BROKER_SUBMISSION"
)


class _UnusedSessionRepository(SessionRepository):
    """Не торкатися persisted Session у standalone runtime check."""


@dataclass(slots=True)
class _RuntimeEngineStub:
    """Надати controller-у лише production RuntimeRepository."""

    repository: RuntimeRepository


@dataclass(frozen=True, slots=True)
class ModeFact:
    """Observable result одного AUTO/SEMI production boundary проходу."""

    control_mode: str
    record: WorkspaceSignalRecord
    trade_uid: str
    execution_state: str
    persisted_rows: int
    order_plan_rows: int
    broker_order_rows: int
    position_rows: int
    completed_bars_delivered: int
    broker_requests: int
    broker_execution_attempted: bool


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


def _allow_snapshot(
    runtime: WorkspaceRuntime,
    first_event: WorkspaceMarketEvent,
) -> WorkspaceRiskAccountSnapshot:
    """Подати TEST_ONLY complete snapshot лише для ізоляції post-risk boundary."""
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
    events: tuple[WorkspaceMarketEvent, ...],
    repository: RuntimeRepository,
    connection: sqlite3.Connection,
) -> ModeFact:
    """Пройти completed BROKER Candidate F до persisted post-risk trade."""
    workspace = create_workspace_fixture(CANONICAL_PERIODS[0])
    workspace.data_mode = WORKSPACE_DATA_MODE_BROKER
    workspace.control_mode = control_mode
    workspace.account_mode = "DEMO"
    workspace.account_id = f"T10925-{control_mode}-DEMO"

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

    accepted: WorkspaceSignalRecord | None = None
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

    rows = connection.execute(
        """
        SELECT * FROM trades
        WHERE workspace_uid = ? AND signal_uid = ?
        """,
        (accepted.workspace_uid, accepted.signal_uid),
    ).fetchall()
    if len(rows) != 1:
        raise AssertionError("post-risk Workspace trade was not persisted exactly once")
    row = rows[0]

    observer = runtime.signal_record_observer
    if observer is None:
        raise AssertionError("production post-risk persistence observer missing")
    observer(accepted)
    duplicate_count = int(
        connection.execute(
            """
            SELECT COUNT(*) FROM trades
            WHERE workspace_uid = ? AND signal_uid = ?
            """,
            (accepted.workspace_uid, accepted.signal_uid),
        ).fetchone()[0]
    )
    if duplicate_count != 1:
        raise AssertionError("idempotent Workspace trade reuse failed")

    expected_state = (
        "READY_FOR_SUBMISSION"
        if control_mode == WORKSPACE_CONTROL_MODE_AUTO
        else "PENDING_CONFIRMATION"
    )
    assert row["broker"] == accepted.broker
    assert row["account_id"] == accepted.account_id
    assert row["symbol"] == accepted.symbol
    assert row["side"] == accepted.direction
    assert row["volume"] == accepted.approved_volume
    assert row["source"] == "WORKSPACE"
    assert row["workspace_uid"] == accepted.workspace_uid
    assert row["signal_uid"] == accepted.signal_uid
    assert row["execution_origin"] == "WORKSPACE"
    assert row["control_mode"] == control_mode
    assert row["execution_state"] == expected_state

    fact = ModeFact(
        control_mode=control_mode,
        record=accepted,
        trade_uid=str(row["trade_uid"]),
        execution_state=str(row["execution_state"]),
        persisted_rows=duplicate_count,
        order_plan_rows=int(
            connection.execute("SELECT COUNT(*) FROM order_plans").fetchone()[0]
        ),
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


def main() -> None:
    """Перевірити post-risk persistence, idempotency та Replay baseline."""
    baselines: dict[str, WorkspaceRuntime] = {}
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

    with tempfile.TemporaryDirectory(prefix="t109_25_") as tmp_dir:
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
            assert fact.persisted_rows == 1
            assert fact.order_plan_rows == 0
            assert fact.broker_order_rows == 0
            assert fact.position_rows == 0
            assert fact.broker_requests == 0
            assert not fact.broker_execution_attempted
            assert not fact.record.risk_execution_attempted
        assert auto.trade_uid != semi.trade_uid
        assert auto.execution_state == "READY_FOR_SUBMISSION"
        assert semi.execution_state == "PENDING_CONFIRMATION"
        connection.close()

    broker_requests += auto.broker_requests + semi.broker_requests
    if broker_requests != 0:
        raise AssertionError("standalone T109-25 must not request broker data")

    print(f"{TEST_ID}_POST_RISK_ALLOW_WORKSPACE_TRADE_PERSISTENCE=OK")
    print("production_change=True")
    print("post_risk_allow_persistence=True")
    print("workspace_trade_create_or_reuse_idempotent=True")
    print(f"auto_execution_state={auto.execution_state}")
    print(f"semi_execution_state={semi.execution_state}")
    print("order_plan_created=False")
    print("broker_order_created=False")
    print("position_created=False")
    print("broker_submission_wiring=False")
    print("reverse_wiring=False")
    print("semi_confirmation_submission=False")
    print(f"canonical_2025_exact_match={canonical_2025_exact_match}")
    print(f"canonical_2026_exact_match={canonical_2026_exact_match}")
    print(f"broker_requests={broker_requests}")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


if __name__ == "__main__":
    main()
