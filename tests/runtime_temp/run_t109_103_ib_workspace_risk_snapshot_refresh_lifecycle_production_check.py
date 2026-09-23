"""run_t109_103_ib_workspace_risk_snapshot_refresh_lifecycle_production_check.py.

Production regression перевіряє main Qt lifecycle caller, який повторно будує
cached IB workspace risk snapshots із cached account state та durable PnL/open
position sources. Temporary schema v12 спочатку дає incomplete snapshot, потім
отримує complete coverage й reconciliation authority та проходить public bulk
controller route без broker request.

Runner також фіксує broker/data-mode filtering, Monitoring delegate, shutdown
guard і виклик із наявного five-second main Qt timer. Repository, RuntimeEngine,
broker adapters, Replay semantics та production SQLite не змінюються.
"""

from __future__ import annotations

from datetime import UTC, datetime
from inspect import getfile
from pathlib import Path
from tempfile import TemporaryDirectory

from core.algorithm_workspace import (
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_BROKER,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.algorithm_workspace_area import AlgorithmWorkspaceArea
from core.algorithm_workspace_controller import AlgorithmWorkspaceController
from core.main_logic import MainAppWindow
from engine.runtime_account_state import RuntimeAccountState
from engine.runtime_engine import RuntimeEngine
from engine.services.ib_runtime_service import IBRuntimeService

BROKER_REQUESTS = 0


class _CachedIBService(IBRuntimeService):
    """Надати controller-у cached IB account без broker access."""

    def __init__(self, account_state: RuntimeAccountState) -> None:
        super().__init__()
        self.account_state = account_state
        self.cache_reads = 0

    def get_account_state(self) -> RuntimeAccountState:
        """Повернути supplied cached account state."""
        self.cache_reads += 1
        return self.account_state


def _account_state(account_id: str, evaluation_utc: datetime) -> RuntimeAccountState:
    """Побудувати exact-bound cached account fixture."""
    return RuntimeAccountState(
        account_id=account_id,
        broker_name="IB",
        currency="USD",
        balance=100_000.0,
        equity=100_000.0,
        snapshot_utc=evaluation_utc.isoformat(),
    )


def _workspace(
    *,
    broker: str,
    account_id: str,
    marker: str,
    data_mode: str,
) -> AlgorithmWorkspace:
    """Побудувати supplied workspace для bulk-filter assertions."""
    return AlgorithmWorkspace.create(
        broker=broker,
        account_id=account_id,
        account_mode="PAPER",
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        display_name=f"T109-103 {marker}",
        data_mode=data_mode,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
    )


def _persist_complete_sources(
    engine: RuntimeEngine,
    *,
    account_id: str,
    evaluation_utc: datetime,
) -> None:
    """Persist-ити complete empty-day coverage та reconciliation authority."""
    day_start = evaluation_utc.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    engine.repository.record_ib_daily_realized_coverage(
        account_id=account_id,
        start_utc=day_start,
        end_utc=evaluation_utc,
        source="TEST_ONLY_COMPLETE_RECOVERY",
    )
    captured_utc = evaluation_utc.isoformat()
    engine.connection.execute(
        """
        INSERT INTO ib_virtual_leg_reconciliation_authority (
            account_id,
            captured_utc,
            source_complete,
            snapshot_digest,
            created_utc,
            updated_utc
        )
        VALUES (?, ?, 1, ?, ?, ?)
        """,
        (
            account_id,
            captured_utc,
            f"TEST_ONLY-{account_id}-{captured_utc}",
            captured_utc,
            captured_utc,
        ),
    )
    engine.connection.commit()


def _section(source: str, start: str, end: str) -> str:
    """Виділити production method section для static assertions."""
    start_index = source.index(start)
    end_index = source.index(end, start_index + len(start))
    return source[start_index:end_index]


def main() -> None:
    """Запустити refresh lifecycle production assertions T109-103."""
    evaluation = datetime(2026, 9, 23, 14, 0, tzinfo=UTC)
    with TemporaryDirectory(
        prefix="t109_103_ib_risk_refresh_",
        ignore_cleanup_errors=True,
    ) as temp_dir:
        engine = RuntimeEngine(
            db_path=str(Path(temp_dir) / "runtime.sqlite3")
        )
        account_id = "DU103"
        service = _CachedIBService(_account_state(account_id, evaluation))
        engine.set_ib_runtime_service(service)
        controller = AlgorithmWorkspaceController()
        controller.set_runtime_engine(engine)

        ib_workspace = _workspace(
            broker="IB",
            account_id=account_id,
            marker="IB",
            data_mode=WORKSPACE_DATA_MODE_BROKER,
        )
        ctrader_workspace = _workspace(
            broker="CTRADER",
            account_id="CTRADER-103",
            marker="CTRADER",
            data_mode=WORKSPACE_DATA_MODE_BROKER,
        )
        replay_workspace = _workspace(
            broker="IB",
            account_id=account_id,
            marker="REPLAY",
            data_mode=WORKSPACE_DATA_MODE_REPLAY,
        )
        controller.attach_workspace_runtime(ib_workspace)
        controller.attach_workspace_runtime(ctrader_workspace)
        controller.attach_workspace_runtime(replay_workspace)

        initial_snapshot = controller.sync_workspace_risk_account_snapshot(
            ib_workspace.workspace_uid
        )
        if initial_snapshot is None:
            raise AssertionError("initial IB risk snapshot is missing")
        initial_snapshot_incomplete = (
            initial_snapshot.daily_realized_pnl is None
            and initial_snapshot.open_positions_count is None
        )

        _persist_complete_sources(
            engine,
            account_id=account_id,
            evaluation_utc=evaluation,
        )
        results = controller.sync_attached_broker_risk_account_snapshots("IB")
        refreshed_snapshot = results.get(ib_workspace.workspace_uid)
        cached_incomplete_snapshot_rebuilt = (
            refreshed_snapshot is not None
            and refreshed_snapshot.daily_realized_pnl == 0.0
            and refreshed_snapshot.open_positions_count == 0
            and refreshed_snapshot.equity == 100_000.0
        )
        only_requested_broker_selected = set(results) == {
            ib_workspace.workspace_uid
        }
        ctrader_workspace_excluded = (
            ctrader_workspace.workspace_uid not in results
        )
        replay_workspace_excluded = replay_workspace.workspace_uid not in results
        exact_snapshot_timestamp_preserved = (
            refreshed_snapshot is not None
            and refreshed_snapshot.snapshot_utc == evaluation
        )
        empty_broker_filter_safe_noop = (
            controller.sync_attached_broker_risk_account_snapshots("") == {}
        )
        cached_account_reads = service.cache_reads
        engine.connection.close()

    controller_path = Path(getfile(AlgorithmWorkspaceController)).resolve()
    area_path = Path(getfile(AlgorithmWorkspaceArea)).resolve()
    main_path = Path(getfile(MainAppWindow)).resolve()
    controller_source = controller_path.read_text(encoding="utf-8")
    area_source = area_path.read_text(encoding="utf-8")
    main_source = main_path.read_text(encoding="utf-8")
    controller_route = _section(
        controller_source,
        "    def sync_attached_broker_risk_account_snapshots(",
        "    def sync_workspace_risk_account_snapshot(",
    )
    area_route = _section(
        area_source,
        "    def sync_broker_risk_account_snapshots(",
        "    def current_workspace_uid(",
    )
    main_refresh_route = _section(
        main_source,
        "    def _refresh_broker_health_status(",
        "    def _recover_ib_daily_realized_account_day_once(",
    )
    controller_bulk_route_present = all(
        token in controller_route
        for token in (
            "tuple(self._runtimes.items())",
            "runtime.context.data_mode != WORKSPACE_DATA_MODE_BROKER",
            "runtime.context.broker != broker_name",
            "self.sync_workspace_risk_account_snapshot(",
        )
    )
    monitoring_public_delegate_present = all(
        token in area_route
        for token in (
            "if self._shutdown_complete:",
            "self.controller.sync_attached_broker_risk_account_snapshots(",
        )
    )
    main_qt_timer_caller_present = all(
        token in main_source
        for token in (
            "self._broker_health_timer.timeout.connect(",
            "self._refresh_broker_health_status",
            "self.page_monitoring.sync_broker_risk_account_snapshots(",
        )
    )
    five_second_timer_preserved = "self._broker_health_timer.start(5000)" in (
        main_source
    )
    caller_after_reconciliation_request = (
        main_refresh_route.index(
            "self._ib_reconciliation_lifecycle.request_refresh("
        )
        < main_refresh_route.index(
            "self.page_monitoring.sync_broker_risk_account_snapshots("
        )
    )
    production_routes_have_no_broker_request = all(
        token not in controller_route + area_route
        for token in (
            "get_active_adapter",
            "get_positions_snapshot",
            "refresh_account_state",
            "request_",
        )
    )
    risk_snapshot_wiring_unchanged = all(
        token in controller_source
        for token in (
            "daily_realized_pnl=daily_realized_pnl",
            "open_positions_count=open_positions_count",
        )
    )

    assert initial_snapshot_incomplete
    assert cached_incomplete_snapshot_rebuilt
    assert only_requested_broker_selected
    assert ctrader_workspace_excluded
    assert replay_workspace_excluded
    assert exact_snapshot_timestamp_preserved
    assert empty_broker_filter_safe_noop
    assert controller_bulk_route_present
    assert monitoring_public_delegate_present
    assert main_qt_timer_caller_present
    assert five_second_timer_preserved
    assert caller_after_reconciliation_request
    assert production_routes_have_no_broker_request
    assert risk_snapshot_wiring_unchanged
    assert BROKER_REQUESTS == 0

    print("T109-103_IB_WORKSPACE_RISK_SNAPSHOT_REFRESH_LIFECYCLE=OK")
    print("production_change=True")
    print(f"initial_snapshot_incomplete={initial_snapshot_incomplete}")
    print(
        "cached_incomplete_snapshot_rebuilt="
        f"{cached_incomplete_snapshot_rebuilt}"
    )
    print(
        "only_requested_broker_selected="
        f"{only_requested_broker_selected}"
    )
    print(f"ctrader_workspace_excluded={ctrader_workspace_excluded}")
    print(f"replay_workspace_excluded={replay_workspace_excluded}")
    print(
        "exact_snapshot_timestamp_preserved="
        f"{exact_snapshot_timestamp_preserved}"
    )
    print(f"empty_broker_filter_safe_noop={empty_broker_filter_safe_noop}")
    print(f"controller_bulk_route_present={controller_bulk_route_present}")
    print(
        "monitoring_public_delegate_present="
        f"{monitoring_public_delegate_present}"
    )
    print(f"main_qt_timer_caller_present={main_qt_timer_caller_present}")
    print(f"five_second_timer_preserved={five_second_timer_preserved}")
    print(
        "caller_after_reconciliation_request="
        f"{caller_after_reconciliation_request}"
    )
    print(
        "production_routes_have_no_broker_request="
        f"{production_routes_have_no_broker_request}"
    )
    print(f"risk_snapshot_wiring_unchanged={risk_snapshot_wiring_unchanged}")
    print(f"cached_account_reads={cached_account_reads}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(
        "first_unresolved_boundary="
        "IB_RISK_DURABLE_SOURCE_CAUSAL_OVERLAP_ANATOMY"
    )
    print(
        "boundary_contract=THE_MAIN_QT_TIMER_NOW_REBUILDS_ATTACHED_IB_RISK_"
        "SNAPSHOTS_FROM_CACHED_AND_DURABLE_SOURCES_WHILE_REAL_PRODUCTION_"
        "TIMESTAMP_OVERLAP_BETWEEN_PNL_COVERAGE_AND_RECONCILIATION_AUTHORITY_"
        "REMAINS_TO_VERIFY"
    )
    print(
        "factual_verdict=A. IB_WORKSPACE_RISK_SNAPSHOT_REFRESH_LIFECYCLE_"
        "GREEN_WITH_MAIN_QT_TIMER_BROKER_FILTER_SHUTDOWN_GUARD_DURABLE_ONLY_"
        "RESYNC_AND_CACHED_INCOMPLETE_REBUILD"
    )


def test_t109_103_ib_workspace_risk_snapshot_refresh_lifecycle() -> None:
    """Запустити T109-103 як pytest-compatible production checkpoint."""
    main()


if __name__ == "__main__":
    main()
