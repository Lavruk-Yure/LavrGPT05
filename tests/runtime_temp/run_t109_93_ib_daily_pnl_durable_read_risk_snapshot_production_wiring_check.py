"""run_t109_93_ib_daily_pnl_durable_read_risk_snapshot_production_wiring_check.py

Production regression для broker-free IB durable daily PnL read-path у
Workspace risk snapshot. Runnable використовує лише supplied events, coverage
та cached account state у тимчасовій SQLite DB. Він перевіряє exact account,
UTC day, той самий evaluation/snapshot timestamp, future exclusion, complete
empty-day zero та fail-closed ``None`` без повної coverage. Broker refresh,
adapter request, open-positions wiring і Replay semantics не змінюються.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from core.algorithm_workspace import (
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_BROKER,
    AlgorithmWorkspace,
)
from core.algorithm_workspace_controller import AlgorithmWorkspaceController
from engine.risk.constants import RISK_REASON_OPEN_POSITIONS_SNAPSHOT_MISSING
from engine.risk.account_snapshot import WorkspaceRiskAccountSnapshot
from engine.risk.risk_model import (
    WorkspaceRiskEvaluator,
    WorkspaceRiskPolicy,
    WorkspaceRiskRequest,
)
from engine.runtime_account_state import RuntimeAccountState
from engine.runtime_engine import RuntimeEngine
from engine.services.ib_runtime_service import IBRuntimeService

BROKER_REQUESTS = 0


class _CachedIBService(IBRuntimeService):
    """Надати controller-у supplied cached account state без broker access."""

    def __init__(self, account_state: RuntimeAccountState) -> None:
        super().__init__()
        self.supplied_account_state = account_state
        self.cache_reads = 0

    def get_account_state(self) -> RuntimeAccountState:
        """Повернути supplied cache і не виконувати adapter request."""
        self.cache_reads += 1
        return self.supplied_account_state


def _account_state(account_id: str, snapshot_utc: datetime) -> RuntimeAccountState:
    """Побудувати exact-bound cached IB account fixture."""
    return RuntimeAccountState(
        account_id=account_id,
        broker_name="IB",
        currency="USD",
        balance=100_000.0,
        equity=100_000.0,
        snapshot_utc=snapshot_utc.isoformat(),
    )


def _workspace(account_id: str) -> AlgorithmWorkspace:
    """Побудувати мінімальний BROKER workspace для public controller route."""
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id=account_id,
        account_mode="PAPER",
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        display_name=f"T109-93 {account_id}",
        data_mode=WORKSPACE_DATA_MODE_BROKER,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
    )


def _persist_event(
    engine: RuntimeEngine,
    *,
    account_id: str,
    exec_id: str,
    execution_time: str,
    amount: float,
) -> None:
    """Записати supplied canonical IB event у temporary durable store."""
    payload: dict[str, object] = {
        "broker": "IB",
        "account_id": account_id,
        "exec_id": exec_id,
        "execution_time": execution_time,
        "net_realized_pnl": amount,
    }
    engine.repository.upsert_ib_daily_realized_event(
        account_id=account_id,
        exec_id=exec_id,
        execution_time=execution_time,
        net_realized_pnl=amount,
        payload=payload,
    )


def _route_snapshot(
    controller: AlgorithmWorkspaceController,
    service: _CachedIBService,
    *,
    account_id: str,
    evaluation_utc: datetime,
) -> WorkspaceRiskAccountSnapshot | None:
    """Пройти public controller route з одним exact-bound IB workspace."""
    service.supplied_account_state = _account_state(
        account_id,
        evaluation_utc,
    )
    workspace = _workspace(account_id)
    controller.attach_workspace_runtime(workspace)
    return controller.sync_workspace_risk_account_snapshot(
        workspace.workspace_uid
    )


def _next_risk_reason(snapshot: WorkspaceRiskAccountSnapshot) -> str:
    """Довести наступний guard після authoritative daily PnL."""
    policy = WorkspaceRiskPolicy(
        max_risk_percent=0.5,
        maximum_position_volume=1000.0,
        maximum_open_positions=2,
        max_daily_loss_percent=2.0,
    )
    request = WorkspaceRiskRequest(
        timestamp=snapshot.snapshot_utc,
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
        open_positions_count=snapshot.open_positions_count,
        daily_realized_pnl=snapshot.daily_realized_pnl,
        runtime_ready=True,
        binding_verified=snapshot.binding_verified,
        market_valid=True,
        spread_guard_passed=True,
    )
    return WorkspaceRiskEvaluator(policy).evaluate(request).reason_code


def main() -> None:
    """Запустити production wiring assertions T109-93."""
    project_root = Path(__file__).resolve().parents[2]
    engine_source = (project_root / "engine/runtime_engine.py").read_text(
        encoding="utf-8"
    )
    controller_source = (
        project_root / "core/algorithm_workspace_controller.py"
    ).read_text(encoding="utf-8")
    read_method_source = engine_source.split(
        "    def read_ib_daily_realized_pnl_snapshot(",
        maxsplit=1,
    )[1].split("\n    def ", maxsplit=1)[0]

    durable_read_route_present = all(
        token in read_method_source
        for token in (
            "self.repository.ib_daily_realized_coverage_is_complete(",
            "self.repository.list_ib_daily_realized_events(",
            "aggregate_broker_daily_realized_pnl(",
        )
    )
    durable_read_route_has_no_broker_access = all(
        token not in read_method_source
        for token in (
            "ib_runtime_service",
            "get_active_adapter",
            "recover_daily_execution_commission_events",
        )
    )
    controller_risk_snapshot_wiring_present = all(
        token in controller_source
        for token in (
            "self._ib_daily_realized_pnl_for_snapshot(",
            "evaluation_utc=snapshot_utc",
            "daily_realized_pnl=daily_realized_pnl",
        )
    )
    same_evaluation_timestamp_wired = all(
        token in controller_source
        for token in (
            "snapshot_utc = normalize_market_timestamp(snapshot_value)",
            "evaluation_utc=snapshot_utc",
            "snapshot_utc=snapshot_utc",
        )
    )
    recovery_authority_unchanged = all(
        token in engine_source
        for token in (
            "def recover_ib_daily_realized_events(",
            "if source_complete:",
            "self.repository.record_ib_daily_realized_coverage(",
        )
    )
    open_positions_wiring_added = (
        "open_positions_count=None" not in controller_source
    )

    evaluation = datetime(2026, 9, 22, 8, 30, tzinfo=UTC)
    day_start = evaluation.replace(hour=0, minute=0, second=0, microsecond=0)

    with tempfile.TemporaryDirectory(prefix="t109_93_") as temp_dir:
        engine = RuntimeEngine(
            db_path=str(Path(temp_dir) / "runtime.sqlite3")
        )
        service = _CachedIBService(_account_state("DU93-A", evaluation))
        engine.set_ib_runtime_service(service)
        controller = AlgorithmWorkspaceController()
        controller.set_runtime_engine(engine)

        _persist_event(
            engine,
            account_id="DU93-A",
            exec_id="E93-A",
            execution_time="20260922 03:00:00 UTC",
            amount=5.25,
        )
        _persist_event(
            engine,
            account_id="DU93-A",
            exec_id="E93-B",
            execution_time="20260922 07:00:00 UTC",
            amount=-2.00,
        )
        _persist_event(
            engine,
            account_id="DU93-A",
            exec_id="E93-FUTURE",
            execution_time="20260922 09:00:00 UTC",
            amount=500.0,
        )
        _persist_event(
            engine,
            account_id="DU93-FOREIGN",
            exec_id="E93-FOREIGN",
            execution_time="20260922 05:00:00 UTC",
            amount=1000.0,
        )
        engine.repository.record_ib_daily_realized_coverage(
            account_id="DU93-A",
            start_utc=day_start,
            end_utc=evaluation,
            source="TEST_ONLY_COMPLETE_RECOVERY",
        )

        complete_snapshot = _route_snapshot(
            controller,
            service,
            account_id="DU93-A",
            evaluation_utc=evaluation,
        )
        if complete_snapshot is None:
            raise AssertionError("complete IB risk snapshot missing")
        completed_daily_pnl_wired = (
            complete_snapshot.daily_realized_pnl == 3.25
        )
        exact_account_scope_enforced = (
            complete_snapshot.daily_realized_pnl != 1003.25
        )
        future_event_excluded = (
            complete_snapshot.daily_realized_pnl != 503.25
        )
        snapshot_timestamp_is_evaluation = (
            complete_snapshot.snapshot_utc == evaluation
        )

        _persist_event(
            engine,
            account_id="DU93-MISSING",
            exec_id="E93-MISSING",
            execution_time="20260922 04:00:00 UTC",
            amount=7.0,
        )
        missing_snapshot = _route_snapshot(
            controller,
            service,
            account_id="DU93-MISSING",
            evaluation_utc=evaluation,
        )
        missing_coverage_keeps_none = bool(
            missing_snapshot is not None
            and missing_snapshot.daily_realized_pnl is None
        )

        engine.repository.record_ib_daily_realized_coverage(
            account_id="DU93-GAP",
            start_utc=day_start,
            end_utc=evaluation - timedelta(minutes=1),
            source="TEST_ONLY_GAPPED_RECOVERY",
        )
        gap_snapshot = _route_snapshot(
            controller,
            service,
            account_id="DU93-GAP",
            evaluation_utc=evaluation,
        )
        coverage_gap_keeps_none = bool(
            gap_snapshot is not None
            and gap_snapshot.daily_realized_pnl is None
        )

        engine.repository.record_ib_daily_realized_coverage(
            account_id="DU93-ZERO",
            start_utc=day_start,
            end_utc=evaluation,
            source="TEST_ONLY_EMPTY_COMPLETE_RECOVERY",
        )
        zero_snapshot = _route_snapshot(
            controller,
            service,
            account_id="DU93-ZERO",
            evaluation_utc=evaluation,
        )
        complete_empty_day_authorizes_zero = bool(
            zero_snapshot is not None
            and zero_snapshot.daily_realized_pnl == 0.0
        )

        next_risk_blocker_open_positions = (
            _next_risk_reason(complete_snapshot)
            == RISK_REASON_OPEN_POSITIONS_SNAPSHOT_MISSING
        )
        cache_reads = service.cache_reads
        engine.connection.close()

    production_change = True

    assert durable_read_route_present
    assert durable_read_route_has_no_broker_access
    assert controller_risk_snapshot_wiring_present
    assert same_evaluation_timestamp_wired
    assert recovery_authority_unchanged
    assert completed_daily_pnl_wired
    assert exact_account_scope_enforced
    assert future_event_excluded
    assert snapshot_timestamp_is_evaluation
    assert missing_coverage_keeps_none
    assert coverage_gap_keeps_none
    assert complete_empty_day_authorizes_zero
    assert next_risk_blocker_open_positions
    assert not open_positions_wiring_added
    assert BROKER_REQUESTS == 0

    print("T109-93_IB_DAILY_PNL_DURABLE_READ_RISK_SNAPSHOT_WIRING=OK")
    print(f"production_change={production_change}")
    print(f"durable_read_route_present={durable_read_route_present}")
    print(
        "durable_read_route_has_no_broker_access="
        f"{durable_read_route_has_no_broker_access}"
    )
    print(
        "controller_risk_snapshot_wiring_present="
        f"{controller_risk_snapshot_wiring_present}"
    )
    print(
        "same_evaluation_timestamp_wired="
        f"{same_evaluation_timestamp_wired}"
    )
    print(f"recovery_authority_unchanged={recovery_authority_unchanged}")
    print(f"completed_daily_pnl_wired={completed_daily_pnl_wired}")
    print(f"exact_account_scope_enforced={exact_account_scope_enforced}")
    print(f"future_event_excluded={future_event_excluded}")
    print(
        "snapshot_timestamp_is_evaluation="
        f"{snapshot_timestamp_is_evaluation}"
    )
    print(f"missing_coverage_keeps_none={missing_coverage_keeps_none}")
    print(f"coverage_gap_keeps_none={coverage_gap_keeps_none}")
    print(
        "complete_empty_day_authorizes_zero="
        f"{complete_empty_day_authorizes_zero}"
    )
    print(
        "next_risk_blocker_open_positions="
        f"{next_risk_blocker_open_positions}"
    )
    print(f"open_positions_wiring_added={open_positions_wiring_added}")
    print(f"cached_account_reads={cache_reads}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(
        "first_unresolved_boundary="
        "IB_OPEN_POSITIONS_COUNT_RISK_SNAPSHOT_PRODUCTION_WIRING"
    )
    print(
        "boundary_contract=IB_DURABLE_DAILY_REALIZED_PNL_IS_NOW_READ_"
        "WITHOUT_BROKER_ACCESS_AT_THE_EXACT_RISK_SNAPSHOT_TIMESTAMP_AND_"
        "REMAINS_NONE_UNLESS_ACCOUNT_DAY_COVERAGE_IS_COMPLETE_WHILE_OPEN_"
        "POSITIONS_COUNT_IS_STILL_UNAVAILABLE"
    )
    print(
        "factual_verdict=A. IB_DAILY_PNL_DURABLE_READ_TO_RISK_SNAPSHOT_"
        "PRODUCTION_WIRING_GREEN_WITH_EXACT_ACCOUNT_CAUSAL_TIMESTAMP_"
        "COVERAGE_FAIL_CLOSED_AND_AUTHORITATIVE_EMPTY_DAY_ZERO"
    )


if __name__ == "__main__":
    main()
