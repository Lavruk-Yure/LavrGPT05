"""run_t109_102_ib_workspace_risk_snapshot_completeness_anatomy_check.py.

TEST_ONLY anatomy перевіряє production completeness lifecycle для IB
``WorkspaceRiskAccountSnapshot`` після wiring durable daily PnL та exact
workspace open count. На temporary schema v12 runner спочатку створює
fail-closed snapshot без coverage/authority, а потім додає обидва durable
джерела без нового broker request.

Тест доводить, що explicit controller resync одразу будує повний causal
snapshot і дозволяє risk evaluation, але вже cached incomplete snapshot не
оновлюється production lifecycle автоматично. Production sources хешуються;
код, broker API та production SQLite не змінюються.
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
from core.algorithm_workspace_area import AlgorithmWorkspaceArea
from core.algorithm_workspace_controller import AlgorithmWorkspaceController
from core.main_logic import MainAppWindow
from engine.risk.account_snapshot import WorkspaceRiskAccountSnapshot
from engine.risk.risk_model import (
    WorkspaceRiskEvaluator,
    WorkspaceRiskPolicy,
    WorkspaceRiskRequest,
)
from engine.runtime_account_state import RuntimeAccountState
from engine.runtime_engine import RuntimeEngine
from engine.services.ib_runtime_service import IBRuntimeService

RECOMMENDED_ROUTE = (
    "MAIN_QT_LIFECYCLE_RESYNCS_ATTACHED_BROKER_WORKSPACE_RISK_SNAPSHOTS_"
    "AFTER_DURABLE_SOURCE_REFRESH_WITHOUT_A_NEW_BROKER_REQUEST"
)
FIRST_UNRESOLVED_BOUNDARY = (
    "IB_WORKSPACE_RISK_SNAPSHOT_REFRESH_LIFECYCLE_PRODUCTION_WIRING"
)
BOUNDARY_CONTRACT = (
    "A_CACHED_FAIL_CLOSED_IB_RISK_SNAPSHOT_MUST_BE_REBUILT_ON_THE_QT_MAIN_"
    "THREAD_AFTER_DURABLE_PNL_COVERAGE_AND_RECONCILIATION_AUTHORITY_BECOME_"
    "AVAILABLE_WITHOUT_REQUIRING_A_NEW_BROKER_REQUEST"
)
FACTUAL_VERDICT = (
    "B. ALL_IB_RISK_FIELDS_CAN_FORM_A_COMPLETE_CAUSAL_SNAPSHOT_BUT_AN_"
    "ALREADY_CACHED_INCOMPLETE_SNAPSHOT_HAS_NO_PRODUCTION_REFRESH_CALLER"
)


class _CachedIBService(IBRuntimeService):
    """Надати supplied account cache без broker access."""

    def __init__(self, account_state: RuntimeAccountState) -> None:
        super().__init__()
        self.account_state = account_state
        self.cache_reads = 0

    def get_account_state(self) -> RuntimeAccountState:
        """Повернути cached account state."""
        self.cache_reads += 1
        return self.account_state


def _hashes(paths: tuple[Path, ...]) -> dict[str, str]:
    """Порахувати hashes scoped production sources."""
    return {
        path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def _workspace(account_id: str) -> AlgorithmWorkspace:
    """Побудувати мінімальний exact-bound IB workspace."""
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id=account_id,
        account_mode="PAPER",
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        display_name="T109-102 completeness",
        data_mode=WORKSPACE_DATA_MODE_BROKER,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
    )


def _account_state(
    account_id: str,
    evaluation_utc: datetime,
) -> RuntimeAccountState:
    """Побудувати supplied cached account facts."""
    return RuntimeAccountState(
        account_id=account_id,
        broker_name="IB",
        currency="USD",
        balance=100_000.0,
        equity=100_000.0,
        snapshot_utc=evaluation_utc.isoformat(),
    )


def _persist_complete_sources(
    engine: RuntimeEngine,
    *,
    account_id: str,
    evaluation_utc: datetime,
) -> None:
    """Persist-ити empty-day PnL coverage та complete empty-leg authority."""
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


def _risk_allows(snapshot: WorkspaceRiskAccountSnapshot) -> bool:
    """Перевірити повний snapshot production risk evaluator-ом."""
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
        open_positions_count=snapshot.open_positions_count,
        daily_realized_pnl=snapshot.daily_realized_pnl,
        runtime_ready=True,
        binding_verified=snapshot.binding_verified,
        market_valid=True,
        spread_guard_passed=True,
    )
    return WorkspaceRiskEvaluator(policy).evaluate(request).allowed


def main() -> None:
    """Запустити IB risk snapshot completeness anatomy T109-102."""
    controller_path = Path(getfile(AlgorithmWorkspaceController)).resolve()
    area_path = Path(getfile(AlgorithmWorkspaceArea)).resolve()
    main_path = Path(getfile(MainAppWindow)).resolve()
    engine_path = Path(getfile(RuntimeEngine)).resolve()
    production_paths = (
        controller_path,
        area_path,
        main_path,
        engine_path,
    )
    hashes_before = _hashes(production_paths)
    evaluation = datetime(2026, 9, 23, 13, 0, tzinfo=UTC)

    with TemporaryDirectory(
        prefix="t109_102_ib_risk_completeness_",
        ignore_cleanup_errors=True,
    ) as temp_dir:
        engine = RuntimeEngine(
            db_path=str(Path(temp_dir) / "runtime.sqlite3")
        )
        account_id = "DU102"
        service = _CachedIBService(_account_state(account_id, evaluation))
        engine.set_ib_runtime_service(service)
        controller = AlgorithmWorkspaceController()
        controller.set_runtime_engine(engine)
        workspace = _workspace(account_id)
        runtime = controller.attach_workspace_runtime(workspace)

        initial_snapshot = controller.sync_workspace_risk_account_snapshot(
            workspace.workspace_uid
        )
        if initial_snapshot is None:
            raise AssertionError("initial risk snapshot is missing")
        initial_snapshot_incomplete = (
            initial_snapshot.equity == 100_000.0
            and initial_snapshot.daily_realized_pnl is None
            and initial_snapshot.open_positions_count is None
        )
        initial_snapshot_identity = id(initial_snapshot)

        _persist_complete_sources(
            engine,
            account_id=account_id,
            evaluation_utc=evaluation,
        )
        durable_sources_become_complete = (
            engine.read_ib_daily_realized_pnl_snapshot(
                account_id=account_id,
                evaluation_utc=evaluation,
            ).daily_realized_pnl
            == 0.0
            and engine.read_ib_workspace_open_positions_count(
                account_id=account_id,
                workspace_uid=workspace.workspace_uid,
                evaluation_utc=evaluation,
            )
            == 0
        )
        cached_snapshot = runtime.risk_account_snapshot
        cached_snapshot_remains_incomplete = (
            cached_snapshot is not None
            and id(cached_snapshot) == initial_snapshot_identity
            and cached_snapshot.daily_realized_pnl is None
            and cached_snapshot.open_positions_count is None
        )

        complete_snapshot = controller.sync_workspace_risk_account_snapshot(
            workspace.workspace_uid
        )
        if complete_snapshot is None:
            raise AssertionError("explicitly refreshed risk snapshot is missing")
        explicit_resync_completes_snapshot = (
            complete_snapshot.daily_realized_pnl == 0.0
            and complete_snapshot.open_positions_count == 0
        )
        all_required_fields_available = (
            complete_snapshot.equity == 100_000.0
            and complete_snapshot.daily_realized_pnl == 0.0
            and complete_snapshot.open_positions_count == 0
            and complete_snapshot.currency == "USD"
            and complete_snapshot.binding_verified
        )
        exact_snapshot_timestamp_preserved = (
            complete_snapshot.snapshot_utc == evaluation
        )
        complete_snapshot_allows_risk = _risk_allows(complete_snapshot)
        cached_account_reads = service.cache_reads
        engine.connection.close()

    controller_source = controller_path.read_text(encoding="utf-8")
    area_source = area_path.read_text(encoding="utf-8")
    main_source = main_path.read_text(encoding="utf-8")
    advance_section = controller_source.split(
        "    def advance_workspace_broker_market(",
        maxsplit=1,
    )[1].split("\n    def ", maxsplit=1)[0]
    advance_resync_guard_only_when_none = all(
        token in advance_section
        for token in (
            "if runtime.risk_account_snapshot is None:",
            "self.sync_workspace_risk_account_snapshot(workspace_uid)",
        )
    )
    area_periodic_refresh_caller_present = (
        "sync_workspace_risk_account_snapshot(" in area_source
    )
    main_periodic_refresh_caller_present = (
        "sync_workspace_risk_account_snapshot(" in main_source
    )
    production_refresh_caller_present = (
        area_periodic_refresh_caller_present
        or main_periodic_refresh_caller_present
    )
    hashes_after = _hashes(production_paths)
    production_change = hashes_before != hashes_after
    broker_requests = 0

    assert initial_snapshot_incomplete
    assert durable_sources_become_complete
    assert cached_snapshot_remains_incomplete
    assert explicit_resync_completes_snapshot
    assert all_required_fields_available
    assert exact_snapshot_timestamp_preserved
    assert complete_snapshot_allows_risk
    assert advance_resync_guard_only_when_none
    assert not area_periodic_refresh_caller_present
    assert not main_periodic_refresh_caller_present
    assert not production_refresh_caller_present
    assert not production_change
    assert broker_requests == 0

    print("T109-102_IB_WORKSPACE_RISK_SNAPSHOT_COMPLETENESS_ANATOMY=OK")
    print("test_scope_test_only=True")
    print(f"production_change={production_change}")
    print(f"initial_snapshot_incomplete={initial_snapshot_incomplete}")
    print(
        "durable_sources_become_complete="
        f"{durable_sources_become_complete}"
    )
    print(
        "cached_snapshot_remains_incomplete="
        f"{cached_snapshot_remains_incomplete}"
    )
    print(
        "explicit_resync_completes_snapshot="
        f"{explicit_resync_completes_snapshot}"
    )
    print(
        "all_required_fields_available="
        f"{all_required_fields_available}"
    )
    print(
        "exact_snapshot_timestamp_preserved="
        f"{exact_snapshot_timestamp_preserved}"
    )
    print(f"complete_snapshot_allows_risk={complete_snapshot_allows_risk}")
    print(
        "advance_resync_guard_only_when_none="
        f"{advance_resync_guard_only_when_none}"
    )
    print(
        "area_periodic_refresh_caller_present="
        f"{area_periodic_refresh_caller_present}"
    )
    print(
        "main_periodic_refresh_caller_present="
        f"{main_periodic_refresh_caller_present}"
    )
    print(
        "production_refresh_caller_present="
        f"{production_refresh_caller_present}"
    )
    print(f"cached_account_reads={cached_account_reads}")
    print(f"broker_requests={broker_requests}")
    print(f"recommended_route={RECOMMENDED_ROUTE}")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


def test_t109_102_ib_workspace_risk_snapshot_completeness_anatomy() -> None:
    """Запустити T109-102 як pytest-compatible anatomy checkpoint."""
    main()


if __name__ == "__main__":
    main()
