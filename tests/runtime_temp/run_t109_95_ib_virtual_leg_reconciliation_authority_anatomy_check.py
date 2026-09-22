"""run_t109_95_ib_virtual_leg_reconciliation_authority_anatomy_check.py.

TEST_ONLY anatomy уточнює фактичну production boundary після T109-94. Runner
відрізняє наявний on-demand reconciliation caller у OrdersPage від відсутньої
durable completeness authority, яка повинна доводити також повний empty
snapshot для exact IB account.

Static assertions перевіряють safe persistence gate, blocking broker evidence,
Qt-main-thread і RuntimeScheduler thread contracts, а також поточний Workspace
risk lifecycle. Broker API не викликається, SQLite не змінюється, production
files лишаються byte-identical. Runner не додає caller, schema чи risk wiring.
"""

from __future__ import annotations

import hashlib
from inspect import getfile
from pathlib import Path

from engine.runtime_engine import RuntimeEngine

TEST_ID = "T109-95"
FIRST_UNRESOLVED_BOUNDARY = (
    "IB_VIRTUAL_LEG_RECONCILIATION_DURABLE_COMPLETENESS_AUTHORITY"
)
BOUNDARY_CONTRACT = (
    "A_COMPLETE_IB_RECONCILIATION_INCLUDING_AN_EMPTY_ACCOUNT_SNAPSHOT_MUST_"
    "DURABLY_PERSIST_ACCOUNT_CAPTURE_TIME_AND_COMPLETENESS_BEFORE_A_RISK_"
    "LIFECYCLE_CALLER_OR_WORKSPACE_COUNT_READ_CAN_AUTHORIZE_OPEN_POSITION_COUNT"
)
FACTUAL_VERDICT = (
    "B. AN_ORDERS_PAGE_ON_DEMAND_PRODUCTION_CALLER_CAN_PERSIST_SAFE_"
    "RECONCILIATION_BUT_NO_DURABLE_COMPLETE_OR_EMPTY_SNAPSHOT_AUTHORITY_"
    "EXISTS_FOR_THE_WORKSPACE_RISK_LIFECYCLE"
)


def _read(path: Path) -> str:
    """Прочитати production source як UTF-8."""
    return path.read_text(encoding="utf-8")


def _section(source: str, start: str, end: str) -> str:
    """Виділити production method між двома declarations."""
    start_index = source.index(start)
    end_index = source.index(end, start_index + len(start))
    return source[start_index:end_index]


def _hashes(paths: tuple[Path, ...]) -> dict[str, str]:
    """Порахувати scoped production hashes до і після anatomy run."""
    return {
        path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def main() -> None:
    """Запустити offline reconciliation-authority assertions T109-95."""
    production_root = Path(getfile(RuntimeEngine)).resolve().parents[1]
    engine_path = production_root / "engine/runtime_engine.py"
    repository_path = production_root / "engine/runtime_repository.py"
    schema_path = production_root / "engine/db/runtime_db.py"
    scheduler_path = production_root / "engine/runtime_scheduler.py"
    adapter_path = production_root / "engine/ib_adapter.py"
    orders_path = production_root / "core/orders_page.py"
    controller_path = production_root / "core/algorithm_workspace_controller.py"
    main_path = production_root / "core/main_logic.py"
    production_paths = (
        engine_path,
        repository_path,
        schema_path,
        scheduler_path,
        adapter_path,
        orders_path,
        controller_path,
        main_path,
    )
    hashes_before = _hashes(production_paths)

    engine_source = _read(engine_path)
    repository_source = _read(repository_path)
    schema_source = _read(schema_path)
    scheduler_source = _read(scheduler_path)
    adapter_source = _read(adapter_path)
    orders_source = _read(orders_path)
    controller_source = _read(controller_path)
    main_source = _read(main_path)

    sync_groups = _section(
        engine_source,
        "    def sync_active_broker_position_groups(",
        "    @staticmethod\n    def _ib_snapshot_persistence_block_reason(",
    )
    persistence_gate = _section(
        engine_source,
        "    def _ib_snapshot_persistence_block_reason(",
        "    def _build_ib_position_group_snapshot(",
    )
    repository_sync = _section(
        repository_source,
        "    def sync_reconciled_ib_virtual_position_leg_snapshot(",
        "    def _sync_ib_fx_external_exposures_no_commit(",
    )
    evidence_method = _section(
        adapter_source,
        "    def get_virtual_position_leg_evidence_snapshot(",
        "    def _request_completed_orders_snapshot(",
    )
    orders_refresh = _section(
        orders_source,
        "    def _on_refresh_clicked(",
        "    def _apply_ib_position_group_snapshot(",
    )
    risk_sync = _section(
        controller_source,
        "    def sync_workspace_risk_account_snapshot(",
        "    def _ib_daily_realized_pnl_for_snapshot(",
    )

    orders_page_production_caller_present = all(
        token in orders_refresh
        for token in (
            '"sync_active_broker_position_groups"',
            "snapshot = sync_groups()",
        )
    )
    orders_page_caller_on_demand = all(
        token in orders_source
        for token in (
            "self.ui.btnRefreshPositions.clicked.connect(",
            "return self.refresh_positions()",
            "def activate_page(self) -> bool:",
        )
    )
    safe_persistence_gate_present = all(
        token in sync_groups + persistence_gate
        for token in (
            "if persistence_block_reason:",
            "if not snapshot.complete:",
            '"positions_complete"',
            '"open_orders_complete"',
            '"completed_orders_complete"',
            '"executions_complete"',
            "sync_reconciled_ib_virtual_position_leg_snapshot(",
        )
    )
    incomplete_snapshot_not_persisted = (
        "if persistence_block_reason:" in sync_groups
        and "else:" in sync_groups
    )
    complete_snapshot_persists = (
        "self.repository.sync_reconciled_ib_virtual_position_leg_snapshot("
        in sync_groups
    )
    captured_utc_returned = all(
        token in repository_sync
        for token in (
            'captured_utc = str(snapshot.captured_utc or "").strip()',
            '"captured_utc": captured_utc',
        )
    )
    durable_snapshot_authority_table_present = any(
        token in schema_source
        for token in (
            "ib_virtual_position_leg_snapshots",
            "ib_virtual_leg_reconciliation_coverage",
            "snapshot_complete INTEGER",
        )
    )
    captured_utc_durable_authority_persisted = (
        durable_snapshot_authority_table_present
        and "captured_utc" in repository_sync
    )
    empty_complete_snapshot_authority_persisted = (
        durable_snapshot_authority_table_present
        and "snapshot.complete" in repository_sync
    )
    risk_lifecycle_caller_present = any(
        "sync_active_broker_position_groups(" in source
        or "sync_reconciled_ib_virtual_position_legs(" in source
        for source in (controller_source, main_source)
    )
    workspace_scoped_durable_read_present = all(
        token in repository_source
        for token in (
            "def get_open_ib_virtual_position_leg_seeds(",
            "workspace_uid: str",
            "AND trades.workspace_uid",
        )
    )
    controller_open_positions_wiring_present = (
        "open_positions_count=None" not in risk_sync
    )
    evidence_requires_four_complete_request_series = all(
        token in evidence_method
        for token in (
            "_request_positions_snapshot_for_execution()",
            "_request_open_orders_snapshot(",
            "_request_completed_orders_snapshot(",
            "_request_virtual_leg_execution_evidence(",
        )
    )
    evidence_calls_are_blocking = all(
        token in adapter_source
        for token in (
            "position_event.wait(",
            "open_orders_event.wait(",
            "completed_orders_event.wait(",
            "execution_event.wait(",
        )
    )
    main_qt_timer_available = all(
        token in main_source
        for token in (
            "self._broker_health_timer = QTimer(self)",
            "self._refresh_broker_health_status",
            "RUNTIME_ACCOUNT_REFRESH_INTERVAL_SECONDS",
        )
    )
    runtime_scheduler_uses_separate_thread = all(
        token in scheduler_source
        for token in (
            "threading.Thread(",
            'name="RuntimeSchedulerThread"',
            "self._run_periodic_tasks()",
        )
    )
    sqlite_connection_thread_bound = (
        "sqlite3.connect(" in schema_source
        and "check_same_thread=False" not in schema_source
    )
    scheduler_store_write_unsafe = (
        runtime_scheduler_uses_separate_thread
        and sqlite_connection_thread_bound
    )
    periodic_main_thread_direct_call_may_block = (
        main_qt_timer_available
        and evidence_requires_four_complete_request_series
        and evidence_calls_are_blocking
    )

    assert orders_page_production_caller_present
    assert orders_page_caller_on_demand
    assert safe_persistence_gate_present
    assert incomplete_snapshot_not_persisted
    assert complete_snapshot_persists
    assert captured_utc_returned
    assert not captured_utc_durable_authority_persisted
    assert not empty_complete_snapshot_authority_persisted
    assert not risk_lifecycle_caller_present
    assert not workspace_scoped_durable_read_present
    assert not controller_open_positions_wiring_present
    assert evidence_requires_four_complete_request_series
    assert evidence_calls_are_blocking
    assert main_qt_timer_available
    assert runtime_scheduler_uses_separate_thread
    assert sqlite_connection_thread_bound
    assert scheduler_store_write_unsafe
    assert periodic_main_thread_direct_call_may_block

    hashes_after = _hashes(production_paths)
    production_change = hashes_before != hashes_after
    assert not production_change

    print("T109-95_IB_VIRTUAL_LEG_RECONCILIATION_AUTHORITY_ANATOMY=OK")
    print("test_scope_test_only=True")
    print(f"production_change={production_change}")
    print("t109_94_direct_caller_assumption_corrected=True")
    print(
        "orders_page_production_caller_present="
        f"{orders_page_production_caller_present}"
    )
    print(f"orders_page_caller_on_demand={orders_page_caller_on_demand}")
    print(f"safe_persistence_gate_present={safe_persistence_gate_present}")
    print(f"incomplete_snapshot_not_persisted={incomplete_snapshot_not_persisted}")
    print(f"complete_snapshot_persists={complete_snapshot_persists}")
    print(f"captured_utc_returned={captured_utc_returned}")
    print(
        "captured_utc_durable_authority_persisted="
        f"{captured_utc_durable_authority_persisted}"
    )
    print(
        "empty_complete_snapshot_authority_persisted="
        f"{empty_complete_snapshot_authority_persisted}"
    )
    print(f"risk_lifecycle_caller_present={risk_lifecycle_caller_present}")
    print(
        "workspace_scoped_durable_read_present="
        f"{workspace_scoped_durable_read_present}"
    )
    print(
        "controller_open_positions_wiring_present="
        f"{controller_open_positions_wiring_present}"
    )
    print(
        "evidence_requires_four_complete_request_series="
        f"{evidence_requires_four_complete_request_series}"
    )
    print(f"evidence_calls_are_blocking={evidence_calls_are_blocking}")
    print(f"main_qt_timer_available={main_qt_timer_available}")
    print(
        "runtime_scheduler_uses_separate_thread="
        f"{runtime_scheduler_uses_separate_thread}"
    )
    print(f"sqlite_connection_thread_bound={sqlite_connection_thread_bound}")
    print(f"scheduler_store_write_unsafe={scheduler_store_write_unsafe}")
    print(
        "periodic_main_thread_direct_call_may_block="
        f"{periodic_main_thread_direct_call_may_block}"
    )
    print("risk_snapshot_wiring_added=False")
    print("broker_requests=0")
    print(
        "recommended_sequence=PERSIST_DURABLE_COMPLETE_OR_EMPTY_ACCOUNT_"
        "SNAPSHOT_AUTHORITY_THEN_ADD_NON_BLOCKING_RISK_LIFECYCLE_REFRESH_"
        "THEN_EXACT_WORKSPACE_READ_THEN_RISK_WIRING"
    )
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


def test_t109_95_ib_virtual_leg_reconciliation_authority_anatomy() -> None:
    """Запустити T109-95 як pytest-compatible checkpoint."""
    main()


if __name__ == "__main__":
    main()
