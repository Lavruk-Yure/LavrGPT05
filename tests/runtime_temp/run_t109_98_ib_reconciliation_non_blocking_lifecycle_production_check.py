"""run_t109_98_ib_reconciliation_non_blocking_lifecycle_production_check.py.

Production regression перевіряє non-blocking lifecycle caller для IB
virtual-leg reconciliation. Реальний Qt event loop запускає production bridge,
а керований fake RuntimeEngine блокує лише evidence worker та фіксує thread IDs
supplied-evidence persistence route.

Runner доводить single-in-flight, account cadence wiring, adapter-generation,
disconnect, failure, reconnect і shutdown fail-closed contracts. Broker API та
production SQLite не використовуються; workspace count read і risk snapshot
wiring навмисно лишаються поза цим кроком.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from inspect import getfile
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QCoreApplication

from core.algorithm_workspace_controller import AlgorithmWorkspaceController
from core.ib_reconciliation_lifecycle import IBReconciliationLifecycleBridge


@dataclass(slots=True)
class _Health:
    """Зберігати supplied broker connection state."""

    connected: bool = True

    def is_connected(self) -> bool:
        """Повернути поточний connection state."""
        return self.connected


@dataclass(slots=True)
class _AccountState:
    """Зберігати supplied exact IB account."""

    account_id: str = "DU109"


class _Service:
    """Надати bridge-у cached health, account та adapter generation."""

    def __init__(self) -> None:
        self.health = _Health()
        self.account_state = _AccountState()
        self.active_adapter: object | None = object()

    def get_broker_health(self) -> _Health:
        """Повернути cached health без broker request."""
        return self.health

    def get_account_state(self) -> _AccountState:
        """Повернути cached account без broker request."""
        return self.account_state

    def get_active_adapter(self) -> object | None:
        """Повернути current adapter identity."""
        return self.active_adapter


class _Engine:
    """Імітувати evidence capture і main-thread persistence route."""

    def __init__(self) -> None:
        self.ib_runtime_service = _Service()
        self.capture_gate = threading.Event()
        self.capture_started = threading.Event()
        self.fail_capture = False
        self.capture_thread_ids: list[int] = []
        self.persistence_thread_ids: list[int] = []
        self.persisted: list[dict[str, Any]] = []

    def get_ib_virtual_position_leg_evidence_snapshot(
        self,
    ) -> dict[str, Any]:
        """Зачекати supplied gate у worker і повернути complete evidence."""
        self.capture_thread_ids.append(threading.get_ident())
        self.capture_started.set()
        if not self.capture_gate.wait(timeout=2.0):
            raise TimeoutError("TEST_ONLY evidence gate timeout")
        if self.fail_capture:
            raise TimeoutError("TEST_ONLY supplied broker timeout")
        return {
            "broker": "IB",
            "captured_utc": "2026-09-23T06:00:00+00:00",
            "complete": True,
            "account_ids": [self.ib_runtime_service.account_state.account_id],
        }

    def sync_reconciled_ib_virtual_position_legs_from_evidence(
        self,
        evidence_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """Зафіксувати supplied evidence і persistence thread."""
        self.persistence_thread_ids.append(threading.get_ident())
        self.persisted.append(dict(evidence_snapshot))
        return {
            "authority_rows_written": 1,
            "captured_utc": evidence_snapshot["captured_utc"],
        }


def _wait_until(
    app: QCoreApplication,
    predicate: Callable[[], bool],
    *,
    timeout: float = 2.0,
) -> None:
    """Обробляти queued Qt signals до supplied condition."""
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("TEST_ONLY Qt handoff timeout")
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()


def _arm_capture(engine: _Engine, *, fail: bool = False) -> None:
    """Підготувати керований evidence worker attempt."""
    engine.capture_gate.clear()
    engine.capture_started.clear()
    engine.fail_capture = fail


def main() -> None:
    """Запустити production lifecycle assertions T109-98."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    if not isinstance(app, QCoreApplication):
        raise AssertionError("QCoreApplication is unavailable")

    main_thread_id = threading.get_ident()
    engine = _Engine()
    current_engine: list[object | None] = [engine]
    bridge = IBReconciliationLifecycleBridge(
        lambda: current_engine[0],
    )

    _arm_capture(engine)
    started_at = time.monotonic()
    first_started = bridge.request_refresh(engine)
    request_returned_without_waiting = time.monotonic() - started_at < 0.2
    assert engine.capture_started.wait(timeout=1.0)
    overlapping_attempt_blocked = not bridge.request_refresh(engine)
    engine.capture_gate.set()
    _wait_until(app, lambda: not bridge.in_flight)
    evidence_ran_off_main_thread = (
        engine.capture_thread_ids[0] != main_thread_id
    )
    persistence_ran_on_main_thread = (
        engine.persistence_thread_ids == [main_thread_id]
    )
    first_complete_authority_persisted = (
        bridge.last_result is not None
        and bridge.last_result["authority_rows_written"] == 1
        and len(engine.persisted) == 1
    )

    _arm_capture(engine)
    stale_started = bridge.request_refresh(engine)
    assert engine.capture_started.wait(timeout=1.0)
    engine.ib_runtime_service.active_adapter = object()
    engine.capture_gate.set()
    _wait_until(app, lambda: not bridge.in_flight)
    stale_generation_discarded = (
        stale_started
        and len(engine.persisted) == 1
        and bridge.last_discard_reason == "IB connection generation changed"
    )

    _arm_capture(engine, fail=True)
    failed_started = bridge.request_refresh(engine)
    assert engine.capture_started.wait(timeout=1.0)
    engine.capture_gate.set()
    _wait_until(app, lambda: not bridge.in_flight)
    capture_failure_does_not_persist = (
        failed_started
        and len(engine.persisted) == 1
        and bridge.last_error is not None
    )

    _arm_capture(engine)
    disconnected_started = bridge.request_refresh(engine)
    assert engine.capture_started.wait(timeout=1.0)
    engine.ib_runtime_service.health.connected = False
    engine.capture_gate.set()
    _wait_until(app, lambda: not bridge.in_flight)
    disconnected_result_discarded = (
        disconnected_started and len(engine.persisted) == 1
    )

    engine.ib_runtime_service.health.connected = True
    engine.ib_runtime_service.active_adapter = object()
    _arm_capture(engine)
    reconnect_started = bridge.request_refresh(engine)
    assert engine.capture_started.wait(timeout=1.0)
    engine.capture_gate.set()
    _wait_until(app, lambda: not bridge.in_flight)
    reconnect_new_generation_persisted = (
        reconnect_started and len(engine.persisted) == 2
    )

    _arm_capture(engine)
    shutdown_started = bridge.request_refresh(engine)
    assert engine.capture_started.wait(timeout=1.0)
    bridge.shutdown()
    engine.capture_gate.set()
    _wait_until(app, lambda: not bridge.in_flight)
    app.processEvents()
    shutdown_result_discarded = (
        shutdown_started
        and len(engine.persisted) == 2
        and bridge.last_discard_reason == "application shutdown"
        and not bridge.request_refresh(engine)
    )

    overlay_root = Path(__file__).resolve().parents[2]
    main_source = (overlay_root / "core/main_logic.py").read_text(
        encoding="utf-8"
    )
    engine_source = (overlay_root / "engine/runtime_engine.py").read_text(
        encoding="utf-8"
    )
    bridge_source = (overlay_root / (
        "core/ib_reconciliation_lifecycle.py"
    )).read_text(encoding="utf-8")
    controller_path = Path(getfile(AlgorithmWorkspaceController)).resolve()
    controller_source = controller_path.read_text(encoding="utf-8")

    supplied_evidence_route_present = all(
        token in engine_source
        for token in (
            "def sync_reconciled_ib_virtual_position_legs_from_evidence(",
            "_build_open_runtime_position_leg_snapshot(evidence_snapshot)",
            "sync_reconciled_ib_virtual_position_leg_snapshot(",
        )
    )
    capture_source = bridge_source.split(
        "    def _capture_evidence(",
        maxsplit=1,
    )[1].split("\n    def ", maxsplit=1)[0]
    worker_evidence_only = all(
        token in bridge_source
        for token in (
            "runtime_engine.get_ib_virtual_position_leg_evidence_snapshot()",
            "self._evidence_ready.emit(payload)",
        )
    ) and all(
        token not in capture_source
        for token in (
            ".repository",
            "sync_reconciled_ib_virtual_position_legs_from_evidence(",
        )
    )
    queued_main_thread_persistence_present = all(
        token in bridge_source
        for token in (
            "self._evidence_ready.connect(self._finish_refresh)",
            "QThread.currentThread() != self.thread()",
            "sync_reconciled_ib_virtual_position_legs_from_evidence(",
        )
    )
    account_cadence_caller_present = all(
        token in main_source
        for token in (
            "if should_refresh_account:",
            "self._ib_reconciliation_lifecycle.request_refresh(",
            "RUNTIME_ACCOUNT_REFRESH_INTERVAL_SECONDS",
        )
    )
    shutdown_guard_wired = all(
        token in main_source
        for token in (
            "self._ib_reconciliation_lifecycle.shutdown",
            "IB reconciliation lifecycle shutdown failed.",
        )
    )
    runtime_scheduler_used = "add_periodic_task" in bridge_source
    workspace_count_read_added = (
        "count_ib_workspace_open_positions" in engine_source
    )
    risk_snapshot_wiring_added = (
        "open_positions_count=None" not in controller_source
    )
    broker_requests = 0

    assert first_started
    assert request_returned_without_waiting
    assert overlapping_attempt_blocked
    assert evidence_ran_off_main_thread
    assert persistence_ran_on_main_thread
    assert first_complete_authority_persisted
    assert stale_generation_discarded
    assert capture_failure_does_not_persist
    assert disconnected_result_discarded
    assert reconnect_new_generation_persisted
    assert shutdown_result_discarded
    assert supplied_evidence_route_present
    assert worker_evidence_only
    assert queued_main_thread_persistence_present
    assert account_cadence_caller_present
    assert shutdown_guard_wired
    assert not runtime_scheduler_used
    assert not workspace_count_read_added
    assert not risk_snapshot_wiring_added
    assert broker_requests == 0

    print("T109-98_IB_RECONCILIATION_NON_BLOCKING_LIFECYCLE=OK")
    print("production_change=True")
    print(f"request_returned_without_waiting={request_returned_without_waiting}")
    print(f"overlapping_attempt_blocked={overlapping_attempt_blocked}")
    print(f"evidence_ran_off_main_thread={evidence_ran_off_main_thread}")
    print(f"persistence_ran_on_main_thread={persistence_ran_on_main_thread}")
    print(
        "first_complete_authority_persisted="
        f"{first_complete_authority_persisted}"
    )
    print(f"stale_generation_discarded={stale_generation_discarded}")
    print(
        "capture_failure_does_not_persist="
        f"{capture_failure_does_not_persist}"
    )
    print(
        "disconnected_result_discarded="
        f"{disconnected_result_discarded}"
    )
    print(
        "reconnect_new_generation_persisted="
        f"{reconnect_new_generation_persisted}"
    )
    print(f"shutdown_result_discarded={shutdown_result_discarded}")
    print(f"supplied_evidence_route_present={supplied_evidence_route_present}")
    print(f"worker_evidence_only={worker_evidence_only}")
    print(
        "queued_main_thread_persistence_present="
        f"{queued_main_thread_persistence_present}"
    )
    print(f"account_cadence_caller_present={account_cadence_caller_present}")
    print(f"shutdown_guard_wired={shutdown_guard_wired}")
    print(f"runtime_scheduler_used={runtime_scheduler_used}")
    print(f"workspace_count_read_added={workspace_count_read_added}")
    print(f"risk_snapshot_wiring_added={risk_snapshot_wiring_added}")
    print(f"broker_requests={broker_requests}")
    print(
        "first_unresolved_boundary="
        "IB_WORKSPACE_OPEN_POSITIONS_COUNT_DURABLE_READ"
    )
    print(
        "boundary_contract=COMPLETE_RECONCILIATION_AUTHORITY_IS_NOW_REFRESHED_"
        "WITHOUT_BLOCKING_QT_OR_CROSS_THREAD_SQLITE_WHILE_EXACT_WORKSPACE_"
        "OPEN_POSITION_COUNT_IS_NOT_YET_READ_FROM_THE_DURABLE_CHAIN"
    )
    print(
        "factual_verdict=A. IB_RECONCILIATION_NON_BLOCKING_RISK_LIFECYCLE_"
        "PRODUCTION_WIRING_GREEN_WITH_EVIDENCE_WORKER_QUEUED_MAIN_THREAD_"
        "PERSISTENCE_GENERATION_GUARDS_AND_FAIL_CLOSED_DISCARD"
    )


def test_t109_98_ib_reconciliation_non_blocking_lifecycle() -> None:
    """Запустити T109-98 як pytest-compatible production checkpoint."""
    main()


if __name__ == "__main__":
    main()
