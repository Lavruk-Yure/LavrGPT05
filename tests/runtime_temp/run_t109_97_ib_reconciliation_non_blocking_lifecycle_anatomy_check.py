"""run_t109_97_ib_reconciliation_non_blocking_lifecycle_anatomy_check.py.

TEST_ONLY anatomy визначає production contract non-blocking IB virtual-leg
reconciliation lifecycle caller. Runner доводить, що blocking broker evidence
можна збирати у worker, але repository build і durable authority persistence
мають повернутися queued handoff-ом у Qt main thread.

Локальний harness перевіряє single-in-flight, adapter-generation, disconnect,
failure і reconnect semantics без Qt, broker API чи SQLite writes. Static
assertions фіксують наявні timer, shutdown і authority seams та відсутність
production bridge. Production files не змінюються, risk wiring не додається.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from inspect import getfile
from pathlib import Path
from queue import Queue

from engine.runtime_engine import RuntimeEngine

TEST_ID = "T109-97"
FIRST_UNRESOLVED_BOUNDARY = (
    "IB_VIRTUAL_LEG_RECONCILIATION_NON_BLOCKING_RISK_LIFECYCLE_"
    "PRODUCTION_WIRING"
)
RECOMMENDED_ROUTE = (
    "BACKGROUND_EVIDENCE_ONLY_QT_QUEUED_MAIN_THREAD_BUILD_AND_PERSIST_WITH_"
    "SINGLE_IN_FLIGHT_ADAPTER_GENERATION_AND_SHUTDOWN_GUARDS"
)
BOUNDARY_CONTRACT = (
    "BLOCKING_IB_EVIDENCE_MUST_RUN_OFF_THE_QT_THREAD_WHILE_ALL_REPOSITORY_"
    "READ_BUILD_AND_DURABLE_AUTHORITY_WRITES_REMAIN_ON_THE_QT_MAIN_THREAD_"
    "AND_STALE_FAILED_DISCONNECTED_OR_SHUTDOWN_RESULTS_ARE_DISCARDED"
)
FACTUAL_VERDICT = (
    "B. DURABLE_RECONCILIATION_AUTHORITY_AND_A_SAFE_QT_TIMER_SEAM_EXIST_BUT_"
    "NO_BACKGROUND_EVIDENCE_TO_MAIN_THREAD_PERSISTENCE_BRIDGE_IS_WIRED"
)


@dataclass(frozen=True, slots=True)
class _Envelope:
    """Перенести supplied worker outcome без repository access."""

    adapter_generation: int
    evidence: dict[str, object] | None
    error: str | None
    worker_thread_id: int


class _BridgeHarness:
    """Моделювати proposed thread handoff без production або Qt changes."""

    def __init__(self) -> None:
        self.main_thread_id = threading.get_ident()
        self.in_flight = False
        self.persisted: list[dict[str, object]] = []
        self.persistence_thread_ids: list[int] = []

    def begin(self, adapter: object) -> int | None:
        """Почати один capture або відхилити overlapping attempt."""
        if self.in_flight:
            return None
        self.in_flight = True
        return id(adapter)

    @staticmethod
    def capture(
        adapter_generation: int,
        *,
        fail: bool = False,
    ) -> _Envelope:
        """Зібрати supplied evidence в окремому Python worker thread."""
        outcomes: Queue[_Envelope] = Queue(maxsize=1)

        def worker() -> None:
            """Створити broker-like outcome без SQLite access."""
            outcomes.put(
                _Envelope(
                    adapter_generation=adapter_generation,
                    evidence=(
                        None
                        if fail
                        else {
                            "broker": "IB",
                            "complete": True,
                            "account_ids": ["DU109"],
                        }
                    ),
                    error="supplied timeout" if fail else None,
                    worker_thread_id=threading.get_ident(),
                )
            )

        thread = threading.Thread(
            target=worker,
            name="T109-97-evidence-worker",
        )
        thread.start()
        thread.join(timeout=2.0)
        if thread.is_alive():
            raise AssertionError("TEST_ONLY evidence worker did not finish")
        return outcomes.get_nowait()

    def finish(
        self,
        envelope: _Envelope,
        *,
        current_adapter: object | None,
        connected: bool,
        shutting_down: bool = False,
    ) -> bool:
        """Прийняти outcome у main thread або fail-closed відкинути."""
        if threading.get_ident() != self.main_thread_id:
            raise AssertionError("persistence handoff left the main thread")
        self.in_flight = False
        if (
            shutting_down
            or not connected
            or current_adapter is None
            or id(current_adapter) != envelope.adapter_generation
            or envelope.error is not None
            or envelope.evidence is None
        ):
            return False
        self.persisted.append(dict(envelope.evidence))
        self.persistence_thread_ids.append(threading.get_ident())
        return True


def _read(path: Path) -> str:
    """Прочитати production source як UTF-8."""
    return path.read_text(encoding="utf-8")


def _hashes(paths: tuple[Path, ...]) -> dict[str, str]:
    """Порахувати scoped production hashes до і після TEST_ONLY run."""
    return {
        path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def main() -> None:
    """Запустити non-blocking lifecycle anatomy assertions T109-97."""
    production_root = Path(getfile(RuntimeEngine)).resolve().parents[1]
    main_path = production_root / "core/main_logic.py"
    engine_path = production_root / "engine/runtime_engine.py"
    repository_path = production_root / "engine/runtime_repository.py"
    scheduler_path = production_root / "engine/runtime_scheduler.py"
    adapter_path = production_root / "engine/ib_adapter.py"
    controller_path = production_root / "core/algorithm_workspace_controller.py"
    production_paths = (
        main_path,
        engine_path,
        repository_path,
        scheduler_path,
        adapter_path,
        controller_path,
    )
    hashes_before = _hashes(production_paths)

    main_source = _read(main_path)
    engine_source = _read(engine_path)
    repository_source = _read(repository_path)
    scheduler_source = _read(scheduler_path)
    adapter_source = _read(adapter_path)
    controller_source = _read(controller_path)

    blocking_evidence_request_series_present = all(
        token in adapter_source
        for token in (
            "_request_positions_snapshot_for_execution()",
            "_request_open_orders_snapshot(",
            "_request_completed_orders_snapshot(",
            "_request_virtual_leg_execution_evidence(",
            "position_event.wait(",
            "open_orders_event.wait(",
            "completed_orders_event.wait(",
            "execution_event.wait(",
        )
    )
    evidence_only_service_route_present = all(
        token in engine_source
        for token in (
            "def get_ib_virtual_position_leg_evidence_snapshot(",
            "return service.get_virtual_position_leg_evidence_snapshot()",
        )
    )
    reconciliation_build_reads_repository = all(
        token in engine_source
        for token in (
            "def _build_open_runtime_position_leg_snapshot(",
            "self.repository.get_open_ib_virtual_position_leg_seeds(",
        )
    )
    reconciliation_persist_writes_repository = all(
        token in engine_source
        for token in (
            "def sync_reconciled_ib_virtual_position_legs(",
            "self.repository.sync_reconciled_ib_virtual_position_leg_snapshot(",
        )
    )
    supplied_evidence_persist_route_present = (
        "sync_reconciled_ib_virtual_position_legs_from_evidence" in engine_source
    )
    durable_authority_present = all(
        token in repository_source
        for token in (
            "def get_ib_virtual_leg_reconciliation_authority(",
            "_upsert_ib_reconciliation_authority_no_commit(",
            "SAVEPOINT ib_virtual_leg_sync",
        )
    )
    main_qt_timer_seam_present = all(
        token in main_source
        for token in (
            "self._broker_health_timer = QTimer(self)",
            "self._refresh_broker_health_status",
            "RUNTIME_ACCOUNT_REFRESH_INTERVAL_SECONDS",
            "should_refresh_account",
        )
    )
    shutdown_guards_present = all(
        token in main_source
        for token in (
            "self._shutdown_in_progress = False",
            "self._shutdown_complete = False",
            "self._stop_main_window_timers",
        )
    )
    adapter_generation_guard_pattern_present = all(
        token in main_source
        for token in (
            "active_adapter = get_active_adapter()",
            "id(active_adapter)",
            "self._ib_daily_realized_recovery_key",
        )
    )
    runtime_scheduler_separate_thread = all(
        token in scheduler_source
        for token in (
            "threading.Thread(",
            'name="RuntimeSchedulerThread"',
        )
    )
    sqlite_connection_thread_bound = (
        "sqlite3.connect(" in _read(production_root / "engine/db/runtime_db.py")
        and "check_same_thread=False"
        not in _read(production_root / "engine/db/runtime_db.py")
    )
    scheduler_persistence_unsafe = (
        runtime_scheduler_separate_thread and sqlite_connection_thread_bound
    )
    production_bridge_present = all(
        token in main_source + engine_source
        for token in (
            "Signal(object)",
            "sync_reconciled_ib_virtual_position_legs_from_evidence",
            "_ib_virtual_leg_reconciliation_in_flight",
        )
    )
    risk_snapshot_wiring_present = (
        "open_positions_count=None" not in controller_source
    )

    harness = _BridgeHarness()
    first_adapter = object()
    first_generation = harness.begin(first_adapter)
    assert first_generation is not None
    overlapping_attempt_blocked = harness.begin(first_adapter) is None
    first_envelope = harness.capture(first_generation)
    evidence_runs_off_main_thread = (
        first_envelope.worker_thread_id != harness.main_thread_id
    )
    valid_result_persisted_on_main_thread = harness.finish(
        first_envelope,
        current_adapter=first_adapter,
        connected=True,
    ) and harness.persistence_thread_ids == [harness.main_thread_id]

    stale_adapter = object()
    stale_generation = harness.begin(stale_adapter)
    assert stale_generation is not None
    stale_result_discarded = not harness.finish(
        harness.capture(stale_generation),
        current_adapter=object(),
        connected=True,
    )

    failed_generation = harness.begin(first_adapter)
    assert failed_generation is not None
    failure_does_not_persist = not harness.finish(
        harness.capture(failed_generation, fail=True),
        current_adapter=first_adapter,
        connected=True,
    )

    disconnected_generation = harness.begin(first_adapter)
    assert disconnected_generation is not None
    disconnected_result_discarded = not harness.finish(
        harness.capture(disconnected_generation),
        current_adapter=first_adapter,
        connected=False,
    )

    shutdown_generation = harness.begin(first_adapter)
    assert shutdown_generation is not None
    shutdown_result_discarded = not harness.finish(
        harness.capture(shutdown_generation),
        current_adapter=first_adapter,
        connected=True,
        shutting_down=True,
    )

    reconnect_adapter = object()
    reconnect_generation = harness.begin(reconnect_adapter)
    assert reconnect_generation is not None
    reconnect_new_generation_accepted = harness.finish(
        harness.capture(reconnect_generation),
        current_adapter=reconnect_adapter,
        connected=True,
    )
    rejected_results_did_not_persist = len(harness.persisted) == 2

    assert blocking_evidence_request_series_present
    assert evidence_only_service_route_present
    assert reconciliation_build_reads_repository
    assert reconciliation_persist_writes_repository
    assert not supplied_evidence_persist_route_present
    assert durable_authority_present
    assert main_qt_timer_seam_present
    assert shutdown_guards_present
    assert adapter_generation_guard_pattern_present
    assert scheduler_persistence_unsafe
    assert not production_bridge_present
    assert not risk_snapshot_wiring_present
    assert overlapping_attempt_blocked
    assert evidence_runs_off_main_thread
    assert valid_result_persisted_on_main_thread
    assert stale_result_discarded
    assert failure_does_not_persist
    assert disconnected_result_discarded
    assert shutdown_result_discarded
    assert reconnect_new_generation_accepted
    assert rejected_results_did_not_persist

    hashes_after = _hashes(production_paths)
    production_change = hashes_before != hashes_after
    assert not production_change

    print("T109-97_IB_RECONCILIATION_NON_BLOCKING_LIFECYCLE_ANATOMY=OK")
    print("test_scope_test_only=True")
    print(f"production_change={production_change}")
    print(
        "blocking_evidence_request_series_present="
        f"{blocking_evidence_request_series_present}"
    )
    print(
        "evidence_only_service_route_present="
        f"{evidence_only_service_route_present}"
    )
    print(
        "reconciliation_build_reads_repository="
        f"{reconciliation_build_reads_repository}"
    )
    print(
        "reconciliation_persist_writes_repository="
        f"{reconciliation_persist_writes_repository}"
    )
    print(
        "supplied_evidence_persist_route_present="
        f"{supplied_evidence_persist_route_present}"
    )
    print(f"durable_authority_present={durable_authority_present}")
    print(f"main_qt_timer_seam_present={main_qt_timer_seam_present}")
    print(f"shutdown_guards_present={shutdown_guards_present}")
    print(
        "adapter_generation_guard_pattern_present="
        f"{adapter_generation_guard_pattern_present}"
    )
    print(f"scheduler_persistence_unsafe={scheduler_persistence_unsafe}")
    print(f"production_bridge_present={production_bridge_present}")
    print(f"overlapping_attempt_blocked={overlapping_attempt_blocked}")
    print(f"evidence_runs_off_main_thread={evidence_runs_off_main_thread}")
    print(
        "valid_result_persisted_on_main_thread="
        f"{valid_result_persisted_on_main_thread}"
    )
    print(f"stale_result_discarded={stale_result_discarded}")
    print(f"failure_does_not_persist={failure_does_not_persist}")
    print(
        "disconnected_result_discarded="
        f"{disconnected_result_discarded}"
    )
    print(f"shutdown_result_discarded={shutdown_result_discarded}")
    print(
        "reconnect_new_generation_accepted="
        f"{reconnect_new_generation_accepted}"
    )
    print(
        "rejected_results_did_not_persist="
        f"{rejected_results_did_not_persist}"
    )
    print(f"risk_snapshot_wiring_added={risk_snapshot_wiring_present}")
    print("broker_requests=0")
    print(f"recommended_route={RECOMMENDED_ROUTE}")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


def test_t109_97_ib_reconciliation_non_blocking_lifecycle_anatomy() -> None:
    """Запустити T109-97 як pytest-compatible checkpoint."""
    main()


if __name__ == "__main__":
    main()
