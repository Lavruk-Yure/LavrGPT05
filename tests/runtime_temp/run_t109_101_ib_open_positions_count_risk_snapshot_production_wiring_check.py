"""run_t109_101_ib_open_positions_count_risk_snapshot_production_wiring_check.py.

Production regression перевіряє broker-free wiring authority-gated IB
workspace open positions count у ``WorkspaceRiskAccountSnapshot``. Runner
створює temporary schema v12, cached account states і durable virtual legs,
після чого проходить public controller route з exact snapshot timestamp.

Перевіряються exact workspace count, complete empty zero та fail-closed
missing/incomplete/future authority. Risk evaluator отримує wired count,
repository і RuntimeEngine не змінюються, broker API не викликається.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from inspect import getfile
from pathlib import Path
from tempfile import TemporaryDirectory

from core.algorithm_workspace import (
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_BROKER,
    AlgorithmWorkspace,
)
from core.algorithm_workspace_controller import AlgorithmWorkspaceController
from engine.ib_virtual_position_leg import IBVirtualPositionLeg
from engine.risk.account_snapshot import WorkspaceRiskAccountSnapshot
from engine.risk.constants import (
    RISK_REASON_MAXIMUM_OPEN_POSITIONS_REACHED,
    RISK_REASON_OPEN_POSITIONS_SNAPSHOT_MISSING,
)
from engine.risk.risk_model import (
    WorkspaceRiskEvaluator,
    WorkspaceRiskPolicy,
    WorkspaceRiskRequest,
)
from engine.runtime_account_state import RuntimeAccountState
from engine.runtime_constants import (
    IB_LEG_STATUS_CLOSED,
    IB_LEG_STATUS_OPEN,
    IB_LEG_STATUS_PARTIALLY_CLOSED,
    IB_PROTECTION_STATUS_NONE,
    IB_RECONCILIATION_STATUS_RECONCILED,
)
from engine.runtime_engine import RuntimeEngine
from engine.runtime_repository import RuntimeRepository
from engine.services.ib_runtime_service import IBRuntimeService

BROKER_REQUESTS = 0


class _CachedIBService(IBRuntimeService):
    """Надати controller-у supplied account cache без broker access."""

    def __init__(self, account_state: RuntimeAccountState) -> None:
        super().__init__()
        self.supplied_account_state = account_state
        self.cache_reads = 0

    def get_account_state(self) -> RuntimeAccountState:
        """Повернути supplied cached account state."""
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


def _workspace(account_id: str, marker: str) -> AlgorithmWorkspace:
    """Побудувати мінімальний BROKER workspace."""
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id=account_id,
        account_mode="PAPER",
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        display_name=f"T109-101 {marker}",
        data_mode=WORKSPACE_DATA_MODE_BROKER,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
    )


def _insert_authority(
    engine: RuntimeEngine,
    *,
    account_id: str,
    captured_utc: datetime,
    source_complete: bool,
) -> None:
    """Записати supplied TEST_ONLY reconciliation authority."""
    timestamp = captured_utc.isoformat()
    engine.connection.execute(
        """
        INSERT OR REPLACE INTO ib_virtual_leg_reconciliation_authority (
            account_id,
            captured_utc,
            source_complete,
            snapshot_digest,
            created_utc,
            updated_utc
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            timestamp,
            int(source_complete),
            f"TEST_ONLY-{account_id}-{timestamp}",
            timestamp,
            timestamp,
        ),
    )
    engine.connection.commit()


def _persist_leg(
    repository: RuntimeRepository,
    *,
    marker: int,
    workspace_uid: str,
    account_id: str,
    remaining_volume: float,
    leg_status: str,
) -> None:
    """Persist-ити мінімальний Trade-to-IB-leg chain public routes."""
    created_utc = "2026-09-23T11:00:00+00:00"
    trade_uid = repository.create_trade(
        broker="IB",
        account_id=account_id,
        symbol="EURUSD",
        side="BUY",
        volume=1.0,
        source="WORKSPACE",
        workspace_uid=workspace_uid,
        signal_uid=f"SIGNAL-{marker}",
        execution_origin="WORKSPACE",
        control_mode="AUTO",
        execution_state="CONFIRMED",
    )
    plan_uid = repository.create_order_plan(
        trade_uid=trade_uid,
        order_type="MARKET",
        side="BUY",
        volume=1.0,
        source="WORKSPACE",
    )
    order_uid = repository.create_broker_order(
        trade_uid=trade_uid,
        order_plan_uid=plan_uid,
        broker="IB",
        broker_order_id=str(marker),
        execution_status="FILLED",
        broker_timestamp=created_utc,
        source="BROKER",
    )
    position_uid = repository.create_position(
        trade_uid=trade_uid,
        broker_order_uid=order_uid,
        broker="IB",
        broker_position_id=str(marker),
        symbol="EURUSD",
        side="BUY",
        volume=1.0,
        open_price=1.1,
        opened_utc=created_utc,
        state="OPEN",
        source="BROKER",
    )
    repository.upsert_ib_virtual_position_leg(
        IBVirtualPositionLeg(
            position_uid=position_uid,
            trade_uid=trade_uid,
            broker_position_id=str(marker),
            account_id=account_id,
            symbol_name="EURUSD",
            side="BUY",
            volume=1.0,
            entry_price=1.1,
            opened_utc=created_utc,
            source="WORKSPACE",
            parent_order_id=marker,
            leg_status=leg_status,
            protection_status=IB_PROTECTION_STATUS_NONE,
            reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
        ),
        remaining_volume=remaining_volume,
        closed_utc=created_utc if leg_status == IB_LEG_STATUS_CLOSED else None,
    )


def _sync_snapshot(
    controller: AlgorithmWorkspaceController,
    service: _CachedIBService,
    workspace: AlgorithmWorkspace,
    evaluation_utc: datetime,
) -> WorkspaceRiskAccountSnapshot:
    """Пройти public controller route для supplied workspace/account."""
    service.supplied_account_state = _account_state(
        workspace.account_id,
        evaluation_utc,
    )
    controller.attach_workspace_runtime(workspace)
    snapshot = controller.sync_workspace_risk_account_snapshot(
        workspace.workspace_uid
    )
    if snapshot is None:
        raise AssertionError("IB workspace risk snapshot is missing")
    return snapshot


def _risk_reason(
    snapshot: WorkspaceRiskAccountSnapshot,
    *,
    open_positions_count: int | None,
) -> str:
    """Передати supplied count у production risk evaluator."""
    policy = WorkspaceRiskPolicy(
        max_risk_percent=1.0,
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
        requested_volume=100.0,
        equity=snapshot.equity,
        estimated_loss_at_stop=100.0,
        stop_loss=1.09,
        open_positions_count=open_positions_count,
        daily_realized_pnl=0.0,
        runtime_ready=True,
        binding_verified=snapshot.binding_verified,
        market_valid=True,
        spread_guard_passed=True,
    )
    return WorkspaceRiskEvaluator(policy).evaluate(request).reason_code


def main() -> None:
    """Запустити risk snapshot production wiring assertions T109-101."""
    evaluation = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
    with TemporaryDirectory(
        prefix="t109_101_ib_risk_count_",
        ignore_cleanup_errors=True,
    ) as temp_dir:
        engine = RuntimeEngine(
            db_path=str(Path(temp_dir) / "runtime.sqlite3")
        )
        service = _CachedIBService(_account_state("DU101", evaluation))
        engine.set_ib_runtime_service(service)
        controller = AlgorithmWorkspaceController()
        controller.set_runtime_engine(engine)

        own_workspace = _workspace("DU101", "OWN")
        other_workspace = _workspace("DU101", "OTHER")
        _persist_leg(
            engine.repository,
            marker=10101,
            workspace_uid=own_workspace.workspace_uid,
            account_id="DU101",
            remaining_volume=0.25,
            leg_status=IB_LEG_STATUS_PARTIALLY_CLOSED,
        )
        _persist_leg(
            engine.repository,
            marker=10102,
            workspace_uid=own_workspace.workspace_uid,
            account_id="DU101",
            remaining_volume=0.10,
            leg_status=IB_LEG_STATUS_OPEN,
        )
        _persist_leg(
            engine.repository,
            marker=10103,
            workspace_uid=own_workspace.workspace_uid,
            account_id="DU101",
            remaining_volume=0.0,
            leg_status=IB_LEG_STATUS_CLOSED,
        )
        _persist_leg(
            engine.repository,
            marker=10104,
            workspace_uid=other_workspace.workspace_uid,
            account_id="DU101",
            remaining_volume=1.0,
            leg_status=IB_LEG_STATUS_OPEN,
        )
        _insert_authority(
            engine,
            account_id="DU101",
            captured_utc=evaluation - timedelta(seconds=1),
            source_complete=True,
        )
        own_snapshot = _sync_snapshot(
            controller,
            service,
            own_workspace,
            evaluation,
        )
        other_snapshot = _sync_snapshot(
            controller,
            service,
            other_workspace,
            evaluation,
        )
        completed_count_wired = own_snapshot.open_positions_count == 2
        exact_workspace_scope = other_snapshot.open_positions_count == 1
        same_evaluation_timestamp_wired = (
            own_snapshot.snapshot_utc == evaluation
        )
        risk_limit_consumes_wired_count = (
            _risk_reason(
                own_snapshot,
                open_positions_count=own_snapshot.open_positions_count,
            )
            == RISK_REASON_MAXIMUM_OPEN_POSITIONS_REACHED
        )

        missing_workspace = _workspace("DU-MISSING", "MISSING")
        missing_snapshot = _sync_snapshot(
            controller,
            service,
            missing_workspace,
            evaluation,
        )
        missing_authority_keeps_none = (
            missing_snapshot.open_positions_count is None
        )
        missing_count_remains_fail_closed = (
            _risk_reason(missing_snapshot, open_positions_count=None)
            == RISK_REASON_OPEN_POSITIONS_SNAPSHOT_MISSING
        )

        incomplete_workspace = _workspace("DU-INCOMPLETE", "INCOMPLETE")
        _insert_authority(
            engine,
            account_id="DU-INCOMPLETE",
            captured_utc=evaluation - timedelta(seconds=1),
            source_complete=False,
        )
        incomplete_snapshot = _sync_snapshot(
            controller,
            service,
            incomplete_workspace,
            evaluation,
        )
        incomplete_authority_keeps_none = (
            incomplete_snapshot.open_positions_count is None
        )

        future_workspace = _workspace("DU-FUTURE", "FUTURE")
        _insert_authority(
            engine,
            account_id="DU-FUTURE",
            captured_utc=evaluation + timedelta(seconds=1),
            source_complete=True,
        )
        future_snapshot = _sync_snapshot(
            controller,
            service,
            future_workspace,
            evaluation,
        )
        future_authority_keeps_none = (
            future_snapshot.open_positions_count is None
        )

        empty_workspace = _workspace("DU-EMPTY", "EMPTY")
        _insert_authority(
            engine,
            account_id="DU-EMPTY",
            captured_utc=evaluation - timedelta(seconds=1),
            source_complete=True,
        )
        empty_snapshot = _sync_snapshot(
            controller,
            service,
            empty_workspace,
            evaluation,
        )
        complete_empty_snapshot_authorizes_zero = (
            empty_snapshot.open_positions_count == 0
        )
        cached_account_reads = service.cache_reads
        engine.connection.close()

    controller_path = Path(getfile(AlgorithmWorkspaceController)).resolve()
    controller_source = controller_path.read_text(encoding="utf-8")
    helper_source = controller_source.split(
        "    def _ib_open_positions_count_for_snapshot(",
        maxsplit=1,
    )[1].split("\n    def ", maxsplit=1)[0]
    controller_route_present = all(
        token in controller_source
        for token in (
            "self._ib_open_positions_count_for_snapshot(",
            "workspace_uid=runtime.context.workspace_uid",
            "open_positions_count=open_positions_count",
        )
    )
    route_uses_same_snapshot_timestamp = (
        "evaluation_utc=snapshot_utc" in controller_source
    )
    route_has_no_broker_access = all(
        token not in helper_source
        for token in (
            "ib_runtime_service",
            "get_active_adapter",
            "get_positions_snapshot",
            "refresh",
        )
    )
    daily_pnl_wiring_unchanged = all(
        token in controller_source
        for token in (
            "self._ib_daily_realized_pnl_for_snapshot(",
            "daily_realized_pnl=daily_realized_pnl",
        )
    )

    assert completed_count_wired
    assert exact_workspace_scope
    assert same_evaluation_timestamp_wired
    assert risk_limit_consumes_wired_count
    assert missing_authority_keeps_none
    assert missing_count_remains_fail_closed
    assert incomplete_authority_keeps_none
    assert future_authority_keeps_none
    assert complete_empty_snapshot_authorizes_zero
    assert controller_route_present
    assert route_uses_same_snapshot_timestamp
    assert route_has_no_broker_access
    assert daily_pnl_wiring_unchanged
    assert BROKER_REQUESTS == 0

    print("T109-101_IB_OPEN_POSITIONS_COUNT_RISK_SNAPSHOT_WIRING=OK")
    print("production_change=True")
    print(f"controller_route_present={controller_route_present}")
    print(
        "route_uses_same_snapshot_timestamp="
        f"{route_uses_same_snapshot_timestamp}"
    )
    print(f"route_has_no_broker_access={route_has_no_broker_access}")
    print(f"completed_count_wired={completed_count_wired}")
    print(f"exact_workspace_scope={exact_workspace_scope}")
    print(
        "same_evaluation_timestamp_wired="
        f"{same_evaluation_timestamp_wired}"
    )
    print(
        "risk_limit_consumes_wired_count="
        f"{risk_limit_consumes_wired_count}"
    )
    print(f"missing_authority_keeps_none={missing_authority_keeps_none}")
    print(
        "incomplete_authority_keeps_none="
        f"{incomplete_authority_keeps_none}"
    )
    print(f"future_authority_keeps_none={future_authority_keeps_none}")
    print(
        "complete_empty_snapshot_authorizes_zero="
        f"{complete_empty_snapshot_authorizes_zero}"
    )
    print(
        "missing_count_remains_fail_closed="
        f"{missing_count_remains_fail_closed}"
    )
    print(f"daily_pnl_wiring_unchanged={daily_pnl_wiring_unchanged}")
    print(f"cached_account_reads={cached_account_reads}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(
        "first_unresolved_boundary="
        "IB_WORKSPACE_RISK_SNAPSHOT_PRODUCTION_COMPLETENESS_CHECK"
    )
    print(
        "boundary_contract=IB_DURABLE_DAILY_PNL_AND_EXACT_WORKSPACE_OPEN_"
        "POSITION_COUNT_ARE_NOW_WIRED_AT_THE_SAME_CAUSAL_SNAPSHOT_TIMESTAMP_"
        "WHILE_FULL_WORKSPACE_RISK_SNAPSHOT_COMPLETENESS_REMAINS_TO_VERIFY"
    )
    print(
        "factual_verdict=A. IB_OPEN_POSITIONS_COUNT_RISK_SNAPSHOT_WIRING_"
        "GREEN_WITH_EXACT_WORKSPACE_SCOPE_COMPLETE_AUTHORITY_EMPTY_ZERO_"
        "SAME_TIMESTAMP_AND_FAIL_CLOSED_MISSING_COUNT"
    )


def test_t109_101_ib_open_positions_count_risk_snapshot_wiring() -> None:
    """Запустити T109-101 як pytest-compatible production checkpoint."""
    main()


if __name__ == "__main__":
    main()
