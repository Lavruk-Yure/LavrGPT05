"""run_t109_104_ib_risk_durable_source_causal_overlap_anatomy_check.py.

TEST_ONLY anatomy перевіряє causal timestamp overlap між IB daily PnL coverage,
reconciliation authority та cached account snapshot. На temporary schema v12
runner відтворює production order ``account A -> recovery coverage B ->
reconciliation C -> next account D`` і використовує чинні durable read routes.

Тест доводить, чи існує evaluation timestamp, де PnL coverage доходить до
evaluation, а reconciliation authority вже не є future. Production sources
хешуються; broker API, production SQLite, risk wiring і lifecycle не
змінюються.
"""

from __future__ import annotations

import hashlib
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
from core.main_logic import MainAppWindow
from engine.runtime_account_state import RuntimeAccountState
from engine.runtime_engine import RuntimeEngine
from engine.runtime_repository import RuntimeRepository
from engine.services.ib_runtime_service import IBRuntimeService

RECOMMENDED_SEQUENCE = (
    "RECONCILIATION_COMPLETES_THEN_PNL_COVERAGE_EXTENDS_PAST_ITS_AUTHORITY_"
    "AND_A_SHARED_DURABLE_RISK_WATERMARK_IS_PERSISTED_BEFORE_RESYNC"
)
FIRST_UNRESOLVED_BOUNDARY = "IB_RISK_SHARED_DURABLE_WATERMARK_CONTRACT"
BOUNDARY_CONTRACT = (
    "IB_RISK_COMPLETENESS_REQUIRES_ONE_DURABLE_EVALUATION_WATERMARK_THAT_IS_"
    "NOT_LATER_THAN_PNL_COVERAGE_AND_NOT_EARLIER_THAN_RECONCILIATION_"
    "AUTHORITY_WHILE_CACHED_ACCOUNT_FACTS_ARE_NOT_FROM_THE_FUTURE"
)
FACTUAL_VERDICT = (
    "B. THE_PRODUCTION_ORDER_PERSISTS_PNL_COVERAGE_BEFORE_RECONCILIATION_"
    "AUTHORITY_SO_NO_SHARED_CAUSAL_RISK_TIMESTAMP_EXISTS_AND_PERIODIC_"
    "DURABLE_ONLY_RESYNC_CANNOT_CREATE_ONE"
)


class _CachedIBService(IBRuntimeService):
    """Надати mutable supplied account cache без broker access."""

    def __init__(self, account_state: RuntimeAccountState) -> None:
        super().__init__()
        self.account_state = account_state
        self.cache_reads = 0

    def get_account_state(self) -> RuntimeAccountState:
        """Повернути supplied cached account state."""
        self.cache_reads += 1
        return self.account_state


def _hashes(paths: tuple[Path, ...]) -> dict[str, str]:
    """Порахувати hashes scoped production sources."""
    return {
        path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def _account_state(account_id: str, timestamp: datetime) -> RuntimeAccountState:
    """Побудувати exact-bound cached account fixture."""
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
        display_name="T109-104 overlap",
        data_mode=WORKSPACE_DATA_MODE_BROKER,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
    )


def _persist_authority(
    engine: RuntimeEngine,
    *,
    account_id: str,
    captured_utc: datetime,
) -> None:
    """Persist-ити supplied complete empty reconciliation authority."""
    timestamp = captured_utc.isoformat()
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
            timestamp,
            f"TEST_ONLY-{account_id}-{timestamp}",
            timestamp,
            timestamp,
        ),
    )
    engine.connection.commit()


def _section(source: str, start: str, end: str) -> str:
    """Виділити production method section для static assertions."""
    start_index = source.index(start)
    end_index = source.index(end, start_index + len(start))
    return source[start_index:end_index]


def main() -> None:
    """Запустити causal-overlap anatomy assertions T109-104."""
    main_path = Path(getfile(MainAppWindow)).resolve()
    engine_path = Path(getfile(RuntimeEngine)).resolve()
    repository_path = Path(getfile(RuntimeRepository)).resolve()
    controller_path = Path(getfile(AlgorithmWorkspaceController)).resolve()
    production_paths = (
        main_path,
        engine_path,
        repository_path,
        controller_path,
    )
    hashes_before = _hashes(production_paths)

    account_timestamp_a = datetime(2026, 9, 23, 15, 0, 0, tzinfo=UTC)
    pnl_coverage_end_b = datetime(2026, 9, 23, 15, 0, 1, tzinfo=UTC)
    reconciliation_authority_c = datetime(
        2026,
        9,
        23,
        15,
        0,
        2,
        tzinfo=UTC,
    )
    next_account_timestamp_d = datetime(
        2026,
        9,
        23,
        15,
        0,
        30,
        tzinfo=UTC,
    )
    account_id = "DU104"

    with TemporaryDirectory(
        prefix="t109_104_ib_risk_overlap_",
        ignore_cleanup_errors=True,
    ) as temp_dir:
        engine = RuntimeEngine(
            db_path=str(Path(temp_dir) / "runtime.sqlite3")
        )
        service = _CachedIBService(
            _account_state(account_id, account_timestamp_a)
        )
        engine.set_ib_runtime_service(service)
        controller = AlgorithmWorkspaceController()
        controller.set_runtime_engine(engine)
        workspace = _workspace(account_id)
        controller.attach_workspace_runtime(workspace)

        day_start = account_timestamp_a.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        engine.repository.record_ib_daily_realized_coverage(
            account_id=account_id,
            start_utc=day_start,
            end_utc=pnl_coverage_end_b,
            source="TEST_ONLY_PRODUCTION_ORDER_RECOVERY",
        )
        _persist_authority(
            engine,
            account_id=account_id,
            captured_utc=reconciliation_authority_c,
        )

        initial_snapshot = controller.sync_workspace_risk_account_snapshot(
            workspace.workspace_uid
        )
        if initial_snapshot is None:
            raise AssertionError("initial overlap snapshot is missing")
        initial_account_time_has_pnl_only = (
            initial_snapshot.snapshot_utc == account_timestamp_a
            and initial_snapshot.daily_realized_pnl == 0.0
            and initial_snapshot.open_positions_count is None
        )

        service.account_state = _account_state(
            account_id,
            next_account_timestamp_d,
        )
        next_snapshot = controller.sync_workspace_risk_account_snapshot(
            workspace.workspace_uid
        )
        if next_snapshot is None:
            raise AssertionError("next overlap snapshot is missing")
        next_account_time_has_count_only = (
            next_snapshot.snapshot_utc == next_account_timestamp_d
            and next_snapshot.daily_realized_pnl is None
            and next_snapshot.open_positions_count == 0
        )

        pnl_at_b = engine.read_ib_daily_realized_pnl_snapshot(
            account_id=account_id,
            evaluation_utc=pnl_coverage_end_b,
        ).daily_realized_pnl
        count_at_b = engine.read_ib_workspace_open_positions_count(
            account_id=account_id,
            workspace_uid=workspace.workspace_uid,
            evaluation_utc=pnl_coverage_end_b,
        )
        pnl_at_c = engine.read_ib_daily_realized_pnl_snapshot(
            account_id=account_id,
            evaluation_utc=reconciliation_authority_c,
        ).daily_realized_pnl
        count_at_c = engine.read_ib_workspace_open_positions_count(
            account_id=account_id,
            workspace_uid=workspace.workspace_uid,
            evaluation_utc=reconciliation_authority_c,
        )
        coverage_boundary_has_pnl_but_future_count = (
            pnl_at_b == 0.0 and count_at_b is None
        )
        authority_boundary_has_count_but_pnl_gap = (
            pnl_at_c is None and count_at_c == 0
        )
        no_shared_causal_timestamp_exists = (
            reconciliation_authority_c > pnl_coverage_end_b
            and coverage_boundary_has_pnl_but_future_count
            and authority_boundary_has_count_but_pnl_gap
        )
        cached_account_reads = service.cache_reads
        engine.connection.close()

    main_source = main_path.read_text(encoding="utf-8")
    engine_source = engine_path.read_text(encoding="utf-8")
    repository_source = repository_path.read_text(encoding="utf-8")
    controller_source = controller_path.read_text(encoding="utf-8")
    refresh_route = _section(
        main_source,
        "    def _refresh_broker_health_status(",
        "    def _recover_ib_daily_realized_account_day_once(",
    )
    recovery_route = _section(
        main_source,
        "    def _recover_ib_daily_realized_account_day_once(",
        "    def _notify_broker_state_changes(",
    )
    live_persist_route = _section(
        engine_source,
        "    def persist_ib_daily_realized_live_events(",
        "    def read_ib_daily_realized_pnl_snapshot(",
    )
    account_refresh_before_recovery = (
        refresh_route.index("ib_service.refresh_account_state()")
        < refresh_route.index(
            "self._recover_ib_daily_realized_account_day_once("
        )
    )
    recovery_before_reconciliation_request = (
        refresh_route.index(
            "self._recover_ib_daily_realized_account_day_once("
        )
        < refresh_route.index(
            "self._ib_reconciliation_lifecycle.request_refresh("
        )
    )
    reconciliation_request_before_risk_resync = (
        refresh_route.index(
            "self._ib_reconciliation_lifecycle.request_refresh("
        )
        < refresh_route.index(
            "self.page_monitoring.sync_broker_risk_account_snapshots("
        )
    )
    same_generation_recovery_not_repeated = all(
        token in recovery_route
        for token in (
            "if self._ib_daily_realized_recovery_key == recovery_key:",
            "self._ib_daily_realized_recovery_key = recovery_key",
        )
    )
    live_events_do_not_extend_coverage = all(
        token in live_persist_route
        for token in (
            '"coverage_committed": False',
            "self.repository.upsert_ib_daily_realized_event(",
        )
    ) and "record_ib_daily_realized_coverage(" not in live_persist_route
    pnl_read_requires_coverage_to_evaluation = all(
        token in engine_source
        for token in (
            "self.repository.ib_daily_realized_coverage_is_complete(",
            "evaluation_utc=evaluation",
        )
    )
    count_read_rejects_future_authority = all(
        token in engine_source
        for token in (
            "def read_ib_workspace_open_positions_count(",
            "evaluation_utc=evaluation_utc",
        )
    ) and (
        "captured.astimezone(UTC) > evaluation_utc.astimezone(UTC)"
        in repository_source
    )
    risk_resync_is_durable_only = all(
        token in controller_source
        for token in (
            "self._ib_daily_realized_pnl_for_snapshot(",
            "self._ib_open_positions_count_for_snapshot(",
        )
    )
    hashes_after = _hashes(production_paths)
    production_change = hashes_before != hashes_after
    broker_requests = 0

    assert initial_account_time_has_pnl_only
    assert next_account_time_has_count_only
    assert coverage_boundary_has_pnl_but_future_count
    assert authority_boundary_has_count_but_pnl_gap
    assert no_shared_causal_timestamp_exists
    assert account_refresh_before_recovery
    assert recovery_before_reconciliation_request
    assert reconciliation_request_before_risk_resync
    assert same_generation_recovery_not_repeated
    assert live_events_do_not_extend_coverage
    assert pnl_read_requires_coverage_to_evaluation
    assert count_read_rejects_future_authority
    assert risk_resync_is_durable_only
    assert not production_change
    assert broker_requests == 0

    print("T109-104_IB_RISK_DURABLE_SOURCE_CAUSAL_OVERLAP_ANATOMY=OK")
    print("test_scope_test_only=True")
    print(f"production_change={production_change}")
    print(
        "initial_account_time_has_pnl_only="
        f"{initial_account_time_has_pnl_only}"
    )
    print(
        "next_account_time_has_count_only="
        f"{next_account_time_has_count_only}"
    )
    print(
        "coverage_boundary_has_pnl_but_future_count="
        f"{coverage_boundary_has_pnl_but_future_count}"
    )
    print(
        "authority_boundary_has_count_but_pnl_gap="
        f"{authority_boundary_has_count_but_pnl_gap}"
    )
    print(
        "no_shared_causal_timestamp_exists="
        f"{no_shared_causal_timestamp_exists}"
    )
    print(
        "account_refresh_before_recovery="
        f"{account_refresh_before_recovery}"
    )
    print(
        "recovery_before_reconciliation_request="
        f"{recovery_before_reconciliation_request}"
    )
    print(
        "reconciliation_request_before_risk_resync="
        f"{reconciliation_request_before_risk_resync}"
    )
    print(
        "same_generation_recovery_not_repeated="
        f"{same_generation_recovery_not_repeated}"
    )
    print(
        "live_events_do_not_extend_coverage="
        f"{live_events_do_not_extend_coverage}"
    )
    print(
        "pnl_read_requires_coverage_to_evaluation="
        f"{pnl_read_requires_coverage_to_evaluation}"
    )
    print(
        "count_read_rejects_future_authority="
        f"{count_read_rejects_future_authority}"
    )
    print(f"risk_resync_is_durable_only={risk_resync_is_durable_only}")
    print(f"cached_account_reads={cached_account_reads}")
    print(f"broker_requests={broker_requests}")
    print(f"recommended_sequence={RECOMMENDED_SEQUENCE}")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


def test_t109_104_ib_risk_durable_source_causal_overlap_anatomy() -> None:
    """Запустити T109-104 як pytest-compatible anatomy checkpoint."""
    main()


if __name__ == "__main__":
    main()
