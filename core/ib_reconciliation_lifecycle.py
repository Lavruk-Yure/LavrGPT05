"""ib_reconciliation_lifecycle.py.

Non-blocking lifecycle coordinator для повного IB virtual-leg reconciliation.
Blocking broker evidence збирається в одному daemon worker, а queued Qt signal
повертає supplied snapshot у thread affinity coordinator-а. Лише там
RuntimeEngine читає repository seeds і атомарно persist-ить reconciled legs та
durable completeness authority.

Coordinator допускає один in-flight request, перевіряє exact account, active
adapter generation, current RuntimeEngine, connection і shutdown state. Stale,
failed, disconnected та late shutdown outcomes відкидаються fail-closed. Після
accepted persistence окремий callback може продовжити PnL coverage до durable
authority; модуль не виконує workspace count read напряму.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from PySide6.QtCore import QObject, QThread, Signal

logger = logging.getLogger(__name__)


class _RuntimeEngineProtocol(Protocol):
    """Описати RuntimeEngine surface для evidence capture і persistence."""

    ib_runtime_service: Any

    def get_ib_virtual_position_leg_evidence_snapshot(
        self,
    ) -> dict[str, Any]:
        """Повернути complete broker evidence без SQLite writes."""
        ...

    def sync_reconciled_ib_virtual_position_legs_from_evidence(
        self,
        evidence_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """Побудувати та persist-ити reconciliation із supplied evidence."""
        ...


def complete_ib_risk_sources_after_reconciliation(
    ib_runtime_service: Any,
    recover_daily_realized_events: Callable[
        [str, datetime, datetime],
        dict[str, object],
    ],
    reconciliation_result: dict[str, Any],
    risk_resync: Callable[[], object],
) -> dict[str, object] | None:
    """Продовжити PnL coverage до authority і тоді rebuild risk."""
    persistence = reconciliation_result.get("persistence")
    if not isinstance(persistence, dict):
        return None
    captured_value = str(persistence.get("captured_utc") or "").strip()
    authority_accounts = {
        str(value or "").strip()
        for value in persistence.get("authority_accounts") or []
        if str(value or "").strip()
    }
    try:
        captured_utc = datetime.fromisoformat(captured_value)
    except ValueError:
        return None
    if captured_utc.tzinfo is None or captured_utc.utcoffset() is None:
        return None
    captured_utc = captured_utc.astimezone(UTC)
    day_start = captured_utc.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    if captured_utc <= day_start:
        return None

    if (
        ib_runtime_service is None
        or not ib_runtime_service.get_broker_health().is_connected()
    ):
        return None
    account_id = str(
        ib_runtime_service.get_account_state().account_id or ""
    ).strip()
    if not account_id or account_id not in authority_accounts:
        return None

    recovery = recover_daily_realized_events(
        account_id,
        day_start,
        captured_utc,
    )
    coverage_committed = recovery.get("coverage_committed")
    if not isinstance(coverage_committed, bool) or not coverage_committed:
        return recovery
    risk_resync()
    return recovery


class IBReconciliationLifecycleBridge(QObject):
    """Передати blocking IB evidence у main-thread persistence route."""

    _evidence_ready = Signal(object)

    def __init__(
        self,
        runtime_engine_provider: Callable[[], object | None],
        parent: QObject | None = None,
        *,
        persistence_callback: (
            Callable[[Any, dict[str, Any]], None] | None
        ) = None,
    ) -> None:
        """Ініціалізувати coordinator у thread affinity його owner-а."""
        super().__init__(parent)
        self._runtime_engine_provider = runtime_engine_provider
        self._persistence_callback = persistence_callback
        self._in_flight = False
        self._shutting_down = False
        self._active_key: tuple[int, str, int] | None = None
        self._worker: threading.Thread | None = None
        self._last_result: dict[str, Any] | None = None
        self._last_error: str | None = None
        self._last_discard_reason: str | None = None
        self._evidence_ready.connect(self._finish_refresh)

    @property
    def in_flight(self) -> bool:
        """Повернути ознаку активного evidence worker."""
        return self._in_flight

    @property
    def last_result(self) -> dict[str, Any] | None:
        """Повернути копію останнього успішного persistence result."""
        return dict(self._last_result) if self._last_result is not None else None

    @property
    def last_error(self) -> str | None:
        """Повернути останню capture/persistence помилку."""
        return self._last_error

    @property
    def last_discard_reason(self) -> str | None:
        """Повернути причину останнього fail-closed discard."""
        return self._last_discard_reason

    def request_refresh(self, runtime_engine: _RuntimeEngineProtocol) -> bool:
        """Запустити один evidence-only worker для current IB generation."""
        if QThread.currentThread() != self.thread():
            raise RuntimeError("IB reconciliation refresh requires owner thread")
        if self._shutting_down or self._in_flight:
            return False

        service = runtime_engine.ib_runtime_service
        if service is None:
            self._last_discard_reason = "IB runtime service is unavailable"
            return False

        get_health = getattr(service, "get_broker_health", None)
        get_account_state = getattr(service, "get_account_state", None)
        get_active_adapter = getattr(service, "get_active_adapter", None)
        if not all(
            callable(method)
            for method in (get_health, get_account_state, get_active_adapter)
        ):
            self._last_discard_reason = "IB lifecycle service surface is incomplete"
            return False

        health = get_health()
        if not health.is_connected():
            self._last_discard_reason = "IB broker is disconnected"
            return False

        account_state = get_account_state()
        account_id = str(getattr(account_state, "account_id", "") or "").strip()
        active_adapter = get_active_adapter()
        if not account_id or active_adapter is None:
            self._last_discard_reason = "IB account or adapter is unavailable"
            return False

        key = (id(runtime_engine), account_id, id(active_adapter))
        self._in_flight = True
        self._active_key = key
        self._last_error = None
        self._last_discard_reason = None
        worker = threading.Thread(
            target=self._capture_evidence,
            args=(runtime_engine, key),
            daemon=True,
            name="IBReconciliationEvidenceThread",
        )
        self._worker = worker
        worker.start()
        return True

    def shutdown(self) -> None:
        """Інвалідовувати in-flight outcome без blocking GUI shutdown."""
        self._shutting_down = True
        self._in_flight = False
        self._active_key = None
        self._last_discard_reason = "application shutdown"

    def _capture_evidence(
        self,
        runtime_engine: _RuntimeEngineProtocol,
        key: tuple[int, str, int],
    ) -> None:
        """Зібрати broker evidence у worker без repository access."""
        evidence: dict[str, Any] | None = None
        error: str | None = None
        try:
            evidence = dict(
                runtime_engine.get_ib_virtual_position_leg_evidence_snapshot()
            )
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"

        payload = {
            "key": key,
            "runtime_engine": runtime_engine,
            "evidence": evidence,
            "error": error,
        }
        try:
            self._evidence_ready.emit(payload)
        except RuntimeError:
            logger.debug(
                "IB reconciliation evidence discarded after QObject teardown."
            )

    def _finish_refresh(self, payload_object: object) -> None:
        """Persist supplied evidence у coordinator owner thread."""
        if QThread.currentThread() != self.thread():
            raise RuntimeError("IB reconciliation persistence left owner thread")
        if not isinstance(payload_object, dict):
            self._discard_current("invalid worker payload")
            return

        payload = payload_object
        key = payload.get("key")
        if key != self._active_key:
            return

        self._in_flight = False
        self._active_key = None
        self._worker = None
        if self._shutting_down:
            self._last_discard_reason = "application shutdown"
            return

        runtime_engine = payload.get("runtime_engine")
        if self._runtime_engine_provider() is not runtime_engine:
            self._last_discard_reason = "RuntimeEngine generation changed"
            return
        if not isinstance(key, tuple) or len(key) != 3:
            self._last_discard_reason = "invalid worker generation key"
            return

        service = getattr(runtime_engine, "ib_runtime_service", None)
        if service is None:
            self._last_discard_reason = "IB runtime service is unavailable"
            return

        health = service.get_broker_health()
        account_state = service.get_account_state()
        active_adapter = service.get_active_adapter()
        account_id = str(getattr(account_state, "account_id", "") or "").strip()
        current_key = (id(runtime_engine), account_id, id(active_adapter))
        if (
            not health.is_connected()
            or active_adapter is None
            or current_key != key
        ):
            self._last_discard_reason = "IB connection generation changed"
            return

        error = payload.get("error")
        if error is not None:
            self._last_error = str(error)
            logger.warning("IB reconciliation evidence failed: %s", error)
            return

        evidence = payload.get("evidence")
        if not isinstance(evidence, dict):
            self._last_discard_reason = "IB reconciliation evidence is missing"
            return

        try:
            persist_supplied_evidence = (
                runtime_engine
                .sync_reconciled_ib_virtual_position_legs_from_evidence
            )
            result = persist_supplied_evidence(evidence)
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"{type(exc).__name__}: {exc}"
            logger.exception("IB reconciliation persistence failed.")
            return

        self._last_result = dict(result)
        self._last_error = None
        self._last_discard_reason = None
        if self._persistence_callback is not None:
            try:
                self._persistence_callback(runtime_engine, self._last_result)
            except Exception as exc:  # noqa: BLE001
                self._last_error = f"{type(exc).__name__}: {exc}"
                logger.exception("IB reconciliation persistence callback failed.")

    def _discard_current(self, reason: str) -> None:
        """Завершити current request без persistence."""
        self._in_flight = False
        self._active_key = None
        self._worker = None
        self._last_discard_reason = reason
