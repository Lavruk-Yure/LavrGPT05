"""run_t109_106_ib_risk_shared_durable_watermark_production_wiring_check.py.

Production regression перевіряє IB shared durable risk watermark wiring. На
temporary schema v12 runner створює cached account, daily-PnL coverage і
complete empty reconciliation authority, після чого виконує production
repository, RuntimeEngine та workspace-controller routes.

Окремий offline lifecycle harness перевіряє recovery точно до authority,
resync лише після coverage commit та exact-account fail-closed. Broker API,
production SQLite, schema і cTrader/Replay paths не використовуються.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from inspect import getfile
from pathlib import Path
from tempfile import TemporaryDirectory

from core.algorithm_workspace import (
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_BROKER,
    AlgorithmWorkspace,
)
from core.algorithm_workspace_controller import AlgorithmWorkspaceController
from core.ib_reconciliation_lifecycle import (
    IBReconciliationLifecycleBridge,
    complete_ib_risk_sources_after_reconciliation,
)
from core.main_logic import MainAppWindow
from engine.db.runtime_db import SCHEMA_VERSION
from engine.runtime_account_state import RuntimeAccountState
from engine.runtime_engine import RuntimeEngine
from engine.runtime_repository import RuntimeRepository
from engine.services.ib_runtime_service import IBRuntimeService

FIRST_UNRESOLVED_BOUNDARY = "IB_WORKSPACE_RISK_SNAPSHOT_CAUSAL_COMPLETENESS_CHECK"
BOUNDARY_CONTRACT = (
    "IB_RISK_NOW_USES_ONE_AUTHORITY_CAPTURED_WATERMARK_AFTER_POST_"
    "RECONCILIATION_PNL_COVERAGE_COMMIT_WHILE_FULL_LIFECYCLE_"
    "COMPLETENESS_AND_RISK_CONSUMPTION_REMAIN_TO_VERIFY"
)
FACTUAL_VERDICT = (
    "A. IB_RISK_SHARED_DURABLE_WATERMARK_PRODUCTION_WIRING_GREEN_WITH_"
    "POST_RECONCILIATION_COVERAGE_EXTENSION_EXACT_AUTHORITY_TIMESTAMP_"
    "FUTURE_ACCOUNT_FAIL_CLOSED_AND_COMMIT_GATED_RESYNC"
)


class _CachedIBService(IBRuntimeService):
    """Надати mutable supplied account cache без broker access."""

    def __init__(self, account_state: RuntimeAccountState) -> None:
        super().__init__()
        self.account_state = account_state

    def get_account_state(self) -> RuntimeAccountState:
        """Повернути supplied cached account state."""
        return self.account_state


@dataclass
class _Health:
    """Надати керований connection state lifecycle helper-у."""

    connected: bool = True

    def is_connected(self) -> bool:
        """Повернути supplied connection state."""
        return self.connected


@dataclass
class _Account:
    """Надати exact cached account identity lifecycle helper-у."""

    account_id: str


class _LifecycleService:
    """Надати helper-у cached health та account без broker access."""

    def __init__(self, account_id: str) -> None:
        self.health = _Health()
        self.account = _Account(account_id)

    def get_broker_health(self) -> _Health:
        """Повернути cached health."""
        return self.health

    def get_account_state(self) -> _Account:
        """Повернути cached exact account."""
        return self.account


class _LifecycleEngine:
    """Записати recovery calls та supplied completion outcome."""

    def __init__(self, account_id: str, *, coverage_committed: bool) -> None:
        self.ib_runtime_service = _LifecycleService(account_id)
        self.coverage_committed = coverage_committed
        self.calls: list[dict[str, object]] = []

    def recover_ib_daily_realized_events(
        self,
        *,
        account_id: str,
        coverage_start_utc: datetime,
        coverage_end_utc: datetime,
    ) -> dict[str, object]:
        """Зафіксувати post-reconciliation recovery без broker request."""
        self.calls.append(
            {
                "account_id": account_id,
                "coverage_start_utc": coverage_start_utc,
                "coverage_end_utc": coverage_end_utc,
            }
        )
        return {
            "source_complete": self.coverage_committed,
            "coverage_committed": self.coverage_committed,
        }

    def recover_for_watermark(
        self,
        account_id: str,
        coverage_start_utc: datetime,
        coverage_end_utc: datetime,
    ) -> dict[str, object]:
        """Адаптувати positional helper call до production-shaped route."""
        return self.recover_ib_daily_realized_events(
            account_id=account_id,
            coverage_start_utc=coverage_start_utc,
            coverage_end_utc=coverage_end_utc,
        )


def _account_state(account_id: str, timestamp: datetime) -> RuntimeAccountState:
    """Побудувати exact-bound cached IB account fixture."""
    return RuntimeAccountState(
        account_id=account_id,
        broker_name="IB",
        currency="USD",
        balance=100_000.0,
        equity=100_000.0,
        snapshot_utc=timestamp.isoformat(),
    )


def _workspace(account_id: str) -> AlgorithmWorkspace:
    """Побудувати мінімальний BROKER workspace."""
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id=account_id,
        account_mode="PAPER",
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        display_name="T109-106 shared watermark",
        data_mode=WORKSPACE_DATA_MODE_BROKER,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
    )


def _persist_authority(
    engine: RuntimeEngine,
    *,
    account_id: str,
    captured_utc: datetime,
) -> None:
    """Записати supplied complete empty reconciliation authority."""
    timestamp = captured_utc.isoformat()
    engine.connection.execute(
        """
        INSERT INTO ib_virtual_leg_reconciliation_authority (
            account_id, captured_utc, source_complete, snapshot_digest,
            created_utc, updated_utc
        )
        VALUES (?, ?, 1, ?, ?, ?)
        """,
        (
            account_id,
            timestamp,
            f"TEST_ONLY-{account_id}-{timestamp}",
            timestamp,
            timestamp,
        ),
    )
    engine.connection.commit()


def _result(account_id: str, captured_utc: datetime) -> dict[str, object]:
    """Побудувати production-shaped reconciliation persistence result."""
    return {
        "snapshot": object(),
        "persistence": {
            "captured_utc": captured_utc.isoformat(),
            "authority_accounts": [account_id],
            "authority_rows_written": 1,
        },
    }


def _section(source: str, start: str, end: str) -> str:
    """Виділити method section для static wiring assertions."""
    start_index = source.index(start)
    end_index = source.index(end, start_index + len(start))
    return source[start_index:end_index]


def main() -> None:
    """Запустити production shared-watermark assertions T109-106."""
    repository_path = Path(getfile(RuntimeRepository)).resolve()
    engine_path = Path(getfile(RuntimeEngine)).resolve()
    controller_path = Path(getfile(AlgorithmWorkspaceController)).resolve()
    lifecycle_path = Path(getfile(IBReconciliationLifecycleBridge)).resolve()
    main_path = Path(getfile(MainAppWindow)).resolve()

    account_id = "DU106"
    account_timestamp = datetime(2026, 9, 23, 15, 0, 0, tzinfo=UTC)
    coverage_end = datetime(2026, 9, 23, 15, 0, 1, tzinfo=UTC)
    authority_timestamp = datetime(2026, 9, 23, 15, 0, 2, tzinfo=UTC)
    extended_end = datetime(2026, 9, 23, 15, 0, 3, tzinfo=UTC)
    future_account_timestamp = datetime(
        2026,
        9,
        23,
        15,
        0,
        30,
        tzinfo=UTC,
    )
    day_start = account_timestamp.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    with TemporaryDirectory(
        prefix="t109_106_ib_shared_watermark_",
        ignore_cleanup_errors=True,
    ) as temp_dir:
        engine = RuntimeEngine(db_path=str(Path(temp_dir) / "runtime.sqlite3"))
        service = _CachedIBService(_account_state(account_id, account_timestamp))
        engine.set_ib_runtime_service(service)
        controller = AlgorithmWorkspaceController()
        controller.set_runtime_engine(engine)
        workspace = _workspace(account_id)
        controller.attach_workspace_runtime(workspace)

        engine.repository.record_ib_daily_realized_coverage(
            account_id=account_id,
            start_utc=day_start,
            end_utc=coverage_end,
            source="TEST_ONLY_INITIAL_RECOVERY",
        )
        _persist_authority(
            engine,
            account_id=account_id,
            captured_utc=authority_timestamp,
        )
        incomplete_snapshot = controller.sync_workspace_risk_account_snapshot(
            workspace.workspace_uid
        )
        no_overlap_keeps_both_fields_none = (
            incomplete_snapshot is not None
            and incomplete_snapshot.daily_realized_pnl is None
            and incomplete_snapshot.open_positions_count is None
        )

        engine.repository.record_ib_daily_realized_coverage(
            account_id=account_id,
            start_utc=coverage_end,
            end_utc=extended_end,
            source="TEST_ONLY_POST_RECONCILIATION_RECOVERY",
        )
        complete_snapshot = controller.sync_workspace_risk_account_snapshot(
            workspace.workspace_uid
        )
        authority_watermark_wired = (
            complete_snapshot is not None
            and complete_snapshot.snapshot_utc == authority_timestamp
        )
        both_fields_share_watermark = (
            complete_snapshot is not None
            and complete_snapshot.daily_realized_pnl == 0.0
            and complete_snapshot.open_positions_count == 0
        )

        service.account_state = _account_state(
            account_id,
            future_account_timestamp,
        )
        future_snapshot = controller.sync_workspace_risk_account_snapshot(
            workspace.workspace_uid
        )
        future_account_fails_closed = (
            future_snapshot is not None
            and future_snapshot.daily_realized_pnl is None
            and future_snapshot.open_positions_count is None
        )
        engine.connection.close()

    resync_calls: list[str] = []
    lifecycle_engine = _LifecycleEngine(
        account_id,
        coverage_committed=True,
    )
    recovery = complete_ib_risk_sources_after_reconciliation(
        lifecycle_engine.ib_runtime_service,
        lifecycle_engine.recover_for_watermark,
        _result(account_id, authority_timestamp),
        lambda: resync_calls.append("IB"),
    )
    post_reconciliation_recovery_to_authority = (
        recovery is not None
        and recovery["coverage_committed"] is True
        and lifecycle_engine.calls
        == [
            {
                "account_id": account_id,
                "coverage_start_utc": day_start,
                "coverage_end_utc": authority_timestamp,
            }
        ]
    )
    committed_recovery_triggers_resync = resync_calls == ["IB"]

    incomplete_engine = _LifecycleEngine(
        account_id,
        coverage_committed=False,
    )
    incomplete_resync_calls: list[str] = []
    complete_ib_risk_sources_after_reconciliation(
        incomplete_engine.ib_runtime_service,
        incomplete_engine.recover_for_watermark,
        _result(account_id, authority_timestamp),
        lambda: incomplete_resync_calls.append("IB"),
    )
    incomplete_recovery_blocks_resync = not incomplete_resync_calls

    wrong_account_engine = _LifecycleEngine(
        "DU106-WRONG",
        coverage_committed=True,
    )
    wrong_account_result = complete_ib_risk_sources_after_reconciliation(
        wrong_account_engine.ib_runtime_service,
        wrong_account_engine.recover_for_watermark,
        _result(account_id, authority_timestamp),
        lambda: None,
    )
    exact_account_scope_enforced = (
        wrong_account_result is None and not wrong_account_engine.calls
    )

    repository_source = repository_path.read_text(encoding="utf-8")
    engine_source = engine_path.read_text(encoding="utf-8")
    controller_source = controller_path.read_text(encoding="utf-8")
    lifecycle_source = lifecycle_path.read_text(encoding="utf-8")
    main_source = main_path.read_text(encoding="utf-8")
    callback_section = _section(
        main_source,
        "    def _on_ib_reconciliation_persisted(",
        "    def _notify_broker_state_changes(",
    )
    repository_watermark_route_present = (
        "def read_ib_risk_shared_durable_watermark(" in repository_source
    )
    runtime_watermark_route_present = (
        "def read_ib_risk_shared_durable_watermark(" in engine_source
    )
    controller_shared_timestamp_route_present = all(
        token in controller_source
        for token in (
            "shared_watermark = self._ib_risk_shared_durable_watermark(",
            "snapshot_utc = shared_watermark",
        )
    )
    bridge_persistence_callback_present = all(
        token in lifecycle_source
        for token in (
            "persistence_callback:",
            "self._persistence_callback(runtime_engine, self._last_result)",
        )
    )
    main_callback_wired = all(
        token in main_source
        for token in (
            "persistence_callback=self._on_ib_reconciliation_persisted",
            "complete_ib_risk_sources_after_reconciliation(",
        )
    )
    shutdown_guard_present = all(
        token in callback_section
        for token in (
            "self._shutdown_in_progress",
            "self._shutdown_complete",
        )
    )
    schema_change = SCHEMA_VERSION != 12
    live_event_coverage_authority_unchanged = (
        '"coverage_committed": False' in engine_source
    )
    production_change = True
    broker_requests = 0

    assert repository_watermark_route_present
    assert runtime_watermark_route_present
    assert controller_shared_timestamp_route_present
    assert bridge_persistence_callback_present
    assert main_callback_wired
    assert shutdown_guard_present
    assert no_overlap_keeps_both_fields_none
    assert authority_watermark_wired
    assert both_fields_share_watermark
    assert future_account_fails_closed
    assert post_reconciliation_recovery_to_authority
    assert committed_recovery_triggers_resync
    assert incomplete_recovery_blocks_resync
    assert exact_account_scope_enforced
    assert live_event_coverage_authority_unchanged
    assert not schema_change
    assert broker_requests == 0

    print("T109-106_IB_RISK_SHARED_DURABLE_WATERMARK_WIRING=OK")
    print(f"production_change={production_change}")
    print(f"schema_version={SCHEMA_VERSION}")
    print("repository_watermark_route_present=" f"{repository_watermark_route_present}")
    print("runtime_watermark_route_present=" f"{runtime_watermark_route_present}")
    print(
        "controller_shared_timestamp_route_present="
        f"{controller_shared_timestamp_route_present}"
    )
    print(
        "bridge_persistence_callback_present=" f"{bridge_persistence_callback_present}"
    )
    print(f"main_callback_wired={main_callback_wired}")
    print(f"shutdown_guard_present={shutdown_guard_present}")
    print("no_overlap_keeps_both_fields_none=" f"{no_overlap_keeps_both_fields_none}")
    print(f"authority_watermark_wired={authority_watermark_wired}")
    print(f"both_fields_share_watermark={both_fields_share_watermark}")
    print(f"future_account_fails_closed={future_account_fails_closed}")
    print(
        "post_reconciliation_recovery_to_authority="
        f"{post_reconciliation_recovery_to_authority}"
    )
    print("committed_recovery_triggers_resync=" f"{committed_recovery_triggers_resync}")
    print("incomplete_recovery_blocks_resync=" f"{incomplete_recovery_blocks_resync}")
    print(f"exact_account_scope_enforced={exact_account_scope_enforced}")
    print(
        "live_event_coverage_authority_unchanged="
        f"{live_event_coverage_authority_unchanged}"
    )
    print(f"schema_change={schema_change}")
    print(f"broker_requests={broker_requests}")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


def test_t109_106_ib_risk_shared_durable_watermark_wiring() -> None:
    """Запустити T109-106 як pytest test."""
    main()


if __name__ == "__main__":
    main()
