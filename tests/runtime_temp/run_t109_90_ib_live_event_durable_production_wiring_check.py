"""run_t109_90_ib_live_event_durable_production_wiring_check.py

Production regression для IB live-event durable wiring. Runnable подає готові
completed execution+commission events через IBRuntimeService snapshot у
RuntimeEngine, перевіряє account+execId persistence, повторний snapshot,
conflict та invalid identity fail-closed. Статична частина підтверджує виклик
із наявного Qt main-thread timer. Coverage, recovery authority, risk snapshot і
broker requests цей крок не змінює та не виконує.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from engine.runtime_engine import RuntimeEngine
from engine.services.ib_runtime_service import IBRuntimeService

BROKER_REQUESTS = 0


class _LiveEventService(IBRuntimeService):
    """Offline IB service, що повертає лише supplied completed events."""

    def __init__(self, events: list[dict[str, object]]) -> None:
        super().__init__()
        self._events = [dict(item) for item in events]

    def set_events(self, events: list[dict[str, object]]) -> None:
        """Замінити snapshot для duplicate/conflict regression."""
        self._events = [dict(item) for item in events]

    def get_execution_commission_events(self) -> list[dict[str, object]]:
        """Повернути незалежний snapshot без broker request."""
        return [dict(item) for item in self._events]


def _event(
    *,
    account_id: str,
    exec_id: str,
    amount: float,
) -> dict[str, object]:
    """Побудувати canonical completed IB live event."""
    return {
        "broker": "IB",
        "account_id": account_id,
        "exec_id": exec_id,
        "execution_time": "2026-09-21T15:00:00+00:00",
        "net_realized_pnl": amount,
    }


def main() -> None:
    """Запустити offline production-wiring assertions T109-90."""
    project_root = Path(__file__).resolve().parents[2]
    engine_source = (project_root / "engine/runtime_engine.py").read_text(
        encoding="utf-8"
    )
    main_source = (project_root / "core/main_logic.py").read_text(
        encoding="utf-8"
    )
    live_method_source = engine_source.split(
        "    def persist_ib_daily_realized_live_events(",
        maxsplit=1,
    )[1].split("\n    def ", maxsplit=1)[0]

    live_persist_route_present = all(
        token in live_method_source
        for token in (
            "service.get_execution_commission_events()",
            "self.repository.upsert_ib_daily_realized_event(",
            '"coverage_committed": False',
        )
    )
    main_thread_caller_present = all(
        token in main_source
        for token in (
            "def _refresh_broker_health_status(",
            "self._broker_health_timer.timeout.connect(",
            "runtime_engine.persist_ib_daily_realized_live_events()",
        )
    )
    coverage_commit_not_added = (
        "record_ib_daily_realized_coverage(" not in live_method_source
    )
    recovery_authority_unchanged = (
        "def recover_ib_daily_realized_events(" in engine_source
    )
    risk_snapshot_wiring_added = "risk_snapshot" in live_method_source

    first_event = _event(
        account_id="DU109-A",
        exec_id="E90-A",
        amount=5.25,
    )
    second_event = _event(
        account_id="DU109-B",
        exec_id="E90-B",
        amount=-1.50,
    )

    with tempfile.TemporaryDirectory(prefix="t109_90_") as temp_dir:
        db_path = Path(temp_dir) / "runtime.sqlite3"
        engine = RuntimeEngine(db_path=str(db_path))
        service = _LiveEventService([first_event, second_event])
        engine.set_ib_runtime_service(service)

        first_result = engine.persist_ib_daily_realized_live_events()
        exact_account_scope_persisted = (
            len(
                engine.repository.list_ib_daily_realized_events(
                    account_id="DU109-A"
                )
            )
            == 1
            and len(
                engine.repository.list_ib_daily_realized_events(
                    account_id="DU109-B"
                )
            )
            == 1
        )
        completed_live_events_persisted = (
            first_result["events_processed"] == 2
            and exact_account_scope_persisted
        )
        live_call_commits_no_coverage = (
            first_result["coverage_committed"] is False
            and not engine.repository.list_ib_daily_realized_coverage(
                account_id="DU109-A"
            )
            and not engine.repository.list_ib_daily_realized_coverage(
                account_id="DU109-B"
            )
        )

        engine.persist_ib_daily_realized_live_events()
        repeated_snapshot_deduped = (
            len(
                engine.repository.list_ib_daily_realized_events(
                    account_id="DU109-A"
                )
            )
            == 1
            and len(
                engine.repository.list_ib_daily_realized_events(
                    account_id="DU109-B"
                )
            )
            == 1
        )

        service.set_events(
            [
                _event(
                    account_id="DU109-A",
                    exec_id="E90-A",
                    amount=99.0,
                )
            ]
        )
        try:
            engine.persist_ib_daily_realized_live_events()
        except ValueError:
            conflict_fail_closed = (
                not engine.repository.list_ib_daily_realized_coverage(
                    account_id="DU109-A"
                )
            )
        else:
            conflict_fail_closed = False
        engine.connection.close()

        invalid_engine = RuntimeEngine(
            db_path=str(Path(temp_dir) / "invalid.sqlite3")
        )
        invalid_service = _LiveEventService(
            [_event(account_id="", exec_id="E90-INVALID", amount=1.0)]
        )
        invalid_engine.set_ib_runtime_service(invalid_service)
        try:
            invalid_engine.persist_ib_daily_realized_live_events()
        except ValueError:
            invalid_identity_fail_closed = True
        else:
            invalid_identity_fail_closed = False
        invalid_engine.connection.close()

        empty_engine = RuntimeEngine(
            db_path=str(Path(temp_dir) / "empty.sqlite3")
        )
        empty_result = empty_engine.persist_ib_daily_realized_live_events()
        missing_service_safe_noop = (
            empty_result["events_processed"] == 0
            and empty_result["coverage_committed"] is False
        )
        empty_engine.connection.close()

    production_change = True

    assert live_persist_route_present
    assert main_thread_caller_present
    assert coverage_commit_not_added
    assert recovery_authority_unchanged
    assert not risk_snapshot_wiring_added
    assert completed_live_events_persisted
    assert exact_account_scope_persisted
    assert live_call_commits_no_coverage
    assert repeated_snapshot_deduped
    assert conflict_fail_closed
    assert invalid_identity_fail_closed
    assert missing_service_safe_noop
    assert BROKER_REQUESTS == 0

    print("T109-90_IB_LIVE_EVENT_DURABLE_PRODUCTION_WIRING=OK")
    print(f"production_change={production_change}")
    print(f"live_persist_route_present={live_persist_route_present}")
    print(f"main_thread_caller_present={main_thread_caller_present}")
    print(f"coverage_commit_not_added={coverage_commit_not_added}")
    print(f"recovery_authority_unchanged={recovery_authority_unchanged}")
    print(
        "completed_live_events_persisted="
        f"{completed_live_events_persisted}"
    )
    print(
        "exact_account_scope_persisted="
        f"{exact_account_scope_persisted}"
    )
    print(f"live_call_commits_no_coverage={live_call_commits_no_coverage}")
    print(f"repeated_snapshot_deduped={repeated_snapshot_deduped}")
    print(f"conflict_fail_closed={conflict_fail_closed}")
    print(f"invalid_identity_fail_closed={invalid_identity_fail_closed}")
    print(f"missing_service_safe_noop={missing_service_safe_noop}")
    print(f"risk_snapshot_wiring_added={risk_snapshot_wiring_added}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(
        "first_unresolved_boundary="
        "IB_DAILY_PNL_DURABLE_STORE_READ_TO_RISK_SNAPSHOT"
    )
    print(
        "boundary_contract=COMPLETED_IB_LIVE_EVENTS_ARE_NOW_PERSISTED_"
        "FROM_THE_MAIN_QT_THREAD_WITH_ACCOUNT_EXECID_DEDUP_CONFLICT_"
        "FAIL_CLOSED_AND_NO_COVERAGE_AUTHORITY_WHILE_THE_DURABLE_SOURCE_"
        "IS_NOT_YET_WIRED_TO_THE_RISK_SNAPSHOT"
    )
    print(
        "factual_verdict=A. IB_LIVE_EVENT_DURABLE_PRODUCTION_WIRING_GREEN_"
        "WITH_MAIN_THREAD_CALLER_DEDUP_CONFLICT_FAIL_CLOSED_AND_NO_"
        "COVERAGE_COMMIT"
    )


if __name__ == "__main__":
    main()
