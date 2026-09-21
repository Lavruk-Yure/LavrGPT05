"""run_t109_89_ib_live_event_durable_wiring_anatomy_check.py

TEST_ONLY anatomy для наступної межі IB daily realized PnL. Модуль звіряє
production-джерело завершених execution+commission events, read-only service
route, durable repository та фактичні periodic execution seams. Окремо
перевіряє повторний snapshot, conflict fail-closed і thread ownership SQLite,
щоб наступний production-крок persist-ив тільки completed live events у
головному runtime thread та не надавав coverage authority. Broker requests,
risk snapshot wiring і production-зміни цей runnable навмисно не виконує.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from engine.db.runtime_db import connect_runtime_db
from engine.runtime_repository import RuntimeRepository

BROKER_REQUESTS = 0


def _resolve_project_root() -> Path:
    """Знайти live project root або root накладеного runnable."""
    packaged_root = Path(__file__).resolve().parents[2]
    if (packaged_root / "engine").is_dir():
        return packaged_root

    current_root = Path.cwd()
    if (current_root / "engine").is_dir():
        return current_root

    raise RuntimeError("LavrGPT05 project root is unavailable")


PROJECT_ROOT = _resolve_project_root()


def _read(relative_path: str) -> str:
    """Прочитати один production source без його зміни."""
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def _event(net_realized_pnl: float) -> dict[str, object]:
    """Побудувати canonical completed IB live event для store contract."""
    return {
        "broker": "IB",
        "account_id": "DU109",
        "exec_id": "E89-LIVE",
        "execution_time": "2026-09-21T14:00:00+00:00",
        "net_realized_pnl": net_realized_pnl,
    }


def _persist(
    repository: RuntimeRepository,
    event: dict[str, object],
) -> None:
    """Виконати локальний еквівалент майбутнього live persist route."""
    repository.upsert_ib_daily_realized_event(
        account_id=str(event["account_id"]),
        exec_id=str(event["exec_id"]),
        execution_time=str(event["execution_time"]),
        net_realized_pnl=float(str(event["net_realized_pnl"])),
        payload=event,
    )


def main() -> None:
    """Запустити статичні та durable-store assertions T109-89."""
    adapter = _read("engine/ib_adapter.py")
    service = _read("engine/services/ib_runtime_service.py")
    engine = _read("engine/runtime_engine.py")
    repository_source = _read("engine/runtime_repository.py")
    runtime_db = _read("engine/db/runtime_db.py")
    scheduler = _read("engine/runtime_scheduler.py")
    main_logic = _read("core/main_logic.py")

    canonical_live_event_source_present = all(
        token in adapter
        for token in (
            "def _try_complete_execution_commission_pair(",
            "if execution is None or commission is None:",
            '"net_realized_pnl": float(realized_pnl)',
            "def get_execution_commission_events(",
        )
    )
    completed_pairs_only = all(
        token in adapter
        for token in (
            "commission_value is None",
            "realized_pnl is None",
            "not currency",
            "self.execution_commission_events.append(",
        )
    )
    live_snapshot_requires_no_request = (
        '"Return normalized IB execution/commission pairs without requests."' in adapter
    )
    runtime_service_live_route_present = all(
        token in service
        for token in (
            "def get_execution_commission_events(",
            "adapter.get_execution_commission_events()",
        )
    )
    durable_event_store_present = all(
        token in repository_source
        for token in (
            "def upsert_ib_daily_realized_event(",
            "def list_ib_daily_realized_events(",
        )
    )
    recovery_store_wiring_present = all(
        token in engine
        for token in (
            "def recover_ib_daily_realized_events(",
            "upsert_ib_daily_realized_event(",
            'source="REQ_EXECUTIONS_RECOVERY"',
        )
    )

    live_route_tokens = (
        "persist_ib_daily_realized_live_events",
        "ingest_ib_daily_realized_live_events",
        "sync_ib_daily_realized_live_events",
    )
    live_event_store_wiring_present = any(
        token in engine for token in live_route_tokens
    )
    live_event_store_caller_present = any(
        token in main_logic or token in engine for token in live_route_tokens
    )

    main_thread_periodic_seam_present = all(
        token in main_logic
        for token in (
            "self._broker_health_timer = QTimer(self)",
            "self._broker_health_timer.timeout.connect(",
            "self._refresh_broker_health_status",
            'session_state, "CURRENT_RUNTIME_ENGINE"',
        )
    )
    sqlite_connection_thread_bound = (
        all(
            token in runtime_db
            for token in (
                "connection = sqlite3.connect(",
                "db_file,",
            )
        )
        and "check_same_thread=False" not in runtime_db
    )
    runtime_scheduler_uses_separate_thread = all(
        token in scheduler
        for token in (
            "threading.Thread(",
            'name="RuntimeSchedulerThread"',
        )
    )
    scheduler_store_write_unsafe = (
        sqlite_connection_thread_bound and runtime_scheduler_uses_separate_thread
    )

    with tempfile.TemporaryDirectory(prefix="t109_89_") as temp_dir:
        connection = connect_runtime_db(Path(temp_dir) / "runtime.sqlite3")
        repository = RuntimeRepository(connection)
        live_event = _event(5.75)
        _persist(repository, live_event)
        _persist(repository, live_event)
        repeated_snapshot_dedup_supported = (
            len(repository.list_ib_daily_realized_events(account_id="DU109")) == 1
        )

        try:
            _persist(repository, _event(6.25))
        except ValueError:
            conflict_fail_closed_supported = True
        else:
            conflict_fail_closed_supported = False

        live_events_do_not_authorize_coverage = (
            not repository.list_ib_daily_realized_coverage(account_id="DU109")
        )
        connection.close()

    production_change = False
    risk_snapshot_wiring_added = False

    assert canonical_live_event_source_present
    assert completed_pairs_only
    assert live_snapshot_requires_no_request
    assert runtime_service_live_route_present
    assert durable_event_store_present
    assert recovery_store_wiring_present
    assert not live_event_store_wiring_present
    assert not live_event_store_caller_present
    assert repeated_snapshot_dedup_supported
    assert conflict_fail_closed_supported
    assert live_events_do_not_authorize_coverage
    assert main_thread_periodic_seam_present
    assert sqlite_connection_thread_bound
    assert runtime_scheduler_uses_separate_thread
    assert scheduler_store_write_unsafe
    assert not production_change
    assert not risk_snapshot_wiring_added
    assert BROKER_REQUESTS == 0

    print("T109-89_IB_LIVE_EVENT_DURABLE_WIRING_ANATOMY=OK")
    print("test_scope_test_only=True")
    print(f"production_change={production_change}")
    print(
        "canonical_live_event_source_present=" f"{canonical_live_event_source_present}"
    )
    print(f"completed_pairs_only={completed_pairs_only}")
    print("live_snapshot_requires_no_request=" f"{live_snapshot_requires_no_request}")
    print("runtime_service_live_route_present=" f"{runtime_service_live_route_present}")
    print(f"durable_event_store_present={durable_event_store_present}")
    print(f"recovery_store_wiring_present={recovery_store_wiring_present}")
    print("live_event_store_wiring_present=" f"{live_event_store_wiring_present}")
    print("live_event_store_caller_present=" f"{live_event_store_caller_present}")
    print("repeated_snapshot_dedup_supported=" f"{repeated_snapshot_dedup_supported}")
    print("conflict_fail_closed_supported=" f"{conflict_fail_closed_supported}")
    print(
        "live_events_do_not_authorize_coverage="
        f"{live_events_do_not_authorize_coverage}"
    )
    print("main_thread_periodic_seam_present=" f"{main_thread_periodic_seam_present}")
    print("sqlite_connection_thread_bound=" f"{sqlite_connection_thread_bound}")
    print(
        "runtime_scheduler_uses_separate_thread="
        f"{runtime_scheduler_uses_separate_thread}"
    )
    print(f"scheduler_store_write_unsafe={scheduler_store_write_unsafe}")
    print(f"risk_snapshot_wiring_added={risk_snapshot_wiring_added}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(
        "recommended_route=MAIN_QT_THREAD_CALLS_RUNTIME_ENGINE_TO_PERSIST_"
        "COMPLETED_SERVICE_SNAPSHOT"
    )
    print(
        "recommended_commit_rule=PERSIST_COMPLETED_LIVE_EVENTS_BY_ACCOUNT_"
        "EXEC_ID_WITH_DEDUP_AND_CONFLICT_FAIL_CLOSED_WITHOUT_COVERAGE_COMMIT"
    )
    print(
        "first_unresolved_boundary=" "IB_DAILY_PNL_LIVE_EVENT_DURABLE_PRODUCTION_WIRING"
    )
    print(
        "boundary_contract=COMPLETED_IB_LIVE_EXECUTION_COMMISSION_EVENTS_"
        "MUST_BE_PERSISTED_BY_RUNTIME_ENGINE_FROM_A_MAIN_THREAD_PERIODIC_"
        "CALLER_WITHOUT_BROKER_REQUEST_WITHOUT_COVERAGE_AUTHORITY_AND_WITH_"
        "REPOSITORY_DEDUP_CONFLICT_FAIL_CLOSED"
    )
    print(
        "factual_verdict=B. IB_COMPLETED_LIVE_EVENT_SOURCE_SERVICE_ROUTE_"
        "AND_DURABLE_STORE_EXIST_BUT_NO_MAIN_THREAD_PRODUCTION_CALLER_"
        "PERSISTS_THE_LIVE_SNAPSHOT"
    )


if __name__ == "__main__":
    main()
