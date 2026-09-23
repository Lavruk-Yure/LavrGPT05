"""run_t109_107_ib_workspace_risk_snapshot_causal_completeness_check.py.

TEST_ONLY anatomy перевіряє повноту IB workspace risk snapshot після shared
durable watermark wiring і його фактичне споживання risk evaluator-ом. На
temporary schema v12 runner формує complete empty account-day coverage та
reconciliation authority, отримує production controller snapshot і подає його
поля у broker-neutral risk requests.

Перевіряються ALLOW, daily-loss/open-position blocks, відсутні поля та часові
межі до/після snapshot watermark. Production sources хешуються; broker API,
production SQLite, risk policy і wiring не змінюються.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from inspect import getfile
from pathlib import Path
from tempfile import TemporaryDirectory

from core.algorithm_workspace import (
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_BROKER,
    AlgorithmWorkspace,
)
from core.algorithm_workspace_controller import AlgorithmWorkspaceController
from core.workspace_runtime import WorkspaceRuntime
from engine.db.runtime_db import SCHEMA_VERSION
from engine.risk.constants import (
    RISK_REASON_APPROVED,
    RISK_REASON_DAILY_LOSS_LIMIT_REACHED,
    RISK_REASON_DAILY_PNL_SNAPSHOT_MISSING,
    RISK_REASON_MAXIMUM_OPEN_POSITIONS_REACHED,
    RISK_REASON_OPEN_POSITIONS_SNAPSHOT_MISSING,
)
from engine.risk.risk_model import (
    WorkspaceRiskEvaluator,
    WorkspaceRiskPolicy,
    WorkspaceRiskRequest,
)
from engine.runtime_account_state import RuntimeAccountState
from engine.runtime_engine import RuntimeEngine
from engine.runtime_repository import RuntimeRepository
from engine.services.ib_runtime_service import IBRuntimeService

FIRST_UNRESOLVED_BOUNDARY = (
    "IB_WORKSPACE_RISK_SNAPSHOT_DECISION_TIME_FRESHNESS_CONTRACT"
)
BOUNDARY_CONTRACT = (
    "A_COMPLETE_IB_RISK_SNAPSHOT_MUST_NOT_BE_CONSUMED_BEFORE_ITS_DURABLE_"
    "WATERMARK_OR_AFTER_ITS_ALLOWED_FRESHNESS_WINDOW_BUT_THE_CURRENT_RISK_"
    "REQUEST_CARRIES_NO_ACCOUNT_SNAPSHOT_TIMESTAMP"
)
FACTUAL_VERDICT = (
    "B. IB_DURABLE_RISK_FIELDS_FORM_ONE_COMPLETE_SNAPSHOT_AND_DRIVE_DAILY_"
    "LOSS_AND_OPEN_POSITION_LIMITS_BUT_DECISION_TIME_CAUSALITY_AND_"
    "FRESHNESS_ARE_NOT_ENFORCED"
)


class _CachedIBService(IBRuntimeService):
    """Надати supplied cached account state без broker access."""

    def __init__(self, account_state: RuntimeAccountState) -> None:
        super().__init__()
        self.account_state = account_state

    def get_account_state(self) -> RuntimeAccountState:
        """Повернути supplied cached account state."""
        return self.account_state


def _hashes(paths: tuple[Path, ...]) -> dict[str, str]:
    """Порахувати hashes scoped production sources."""
    return {
        path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


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
        display_name="T109-107 causal completeness",
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


def _request(
    *,
    timestamp: datetime,
    workspace_uid: str,
    account_id: str,
    equity: float | None,
    daily_realized_pnl: float | None,
    open_positions_count: int | None,
) -> WorkspaceRiskRequest:
    """Побудувати safe nominal request із supplied account facts."""
    return WorkspaceRiskRequest(
        timestamp=timestamp,
        workspace_uid=workspace_uid,
        broker="IB",
        account_id=account_id,
        symbol="EURUSD",
        side="BUY",
        source_mode=WORKSPACE_DATA_MODE_BROKER,
        requested_volume=1.0,
        equity=equity,
        estimated_loss_at_stop=1_000.0,
        stop_loss=1.09,
        open_positions_count=open_positions_count,
        daily_realized_pnl=daily_realized_pnl,
        runtime_ready=True,
        binding_verified=True,
        market_valid=True,
        spread_guard_passed=True,
        signal_uid="T109-107-SIGNAL",
    )


def _section(source: str, start: str, end: str) -> str:
    """Виділити production class/method section для static assertions."""
    start_index = source.index(start)
    end_index = source.index(end, start_index + len(start))
    return source[start_index:end_index]


def main() -> None:
    """Запустити causal completeness anatomy assertions T109-107."""
    repository_path = Path(getfile(RuntimeRepository)).resolve()
    production_root = repository_path.parents[1]
    engine_path = Path(getfile(RuntimeEngine)).resolve()
    controller_path = Path(getfile(AlgorithmWorkspaceController)).resolve()
    runtime_path = Path(getfile(WorkspaceRuntime)).resolve()
    risk_path = production_root / "engine/risk/risk_model.py"
    snapshot_path = production_root / "engine/risk/account_snapshot.py"
    production_paths = (
        repository_path,
        engine_path,
        controller_path,
        runtime_path,
        risk_path,
        snapshot_path,
    )
    hashes_before = _hashes(production_paths)

    account_id = "DU107"
    cached_account_utc = datetime(2026, 9, 23, 15, 0, 0, tzinfo=UTC)
    watermark = datetime(2026, 9, 23, 15, 0, 2, tzinfo=UTC)
    coverage_end = watermark + timedelta(seconds=1)
    day_start = watermark.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    with TemporaryDirectory(
        prefix="t109_107_ib_risk_completeness_",
        ignore_cleanup_errors=True,
    ) as temp_dir:
        engine = RuntimeEngine(
            db_path=str(Path(temp_dir) / "runtime.sqlite3")
        )
        service = _CachedIBService(
            _account_state(account_id, cached_account_utc)
        )
        engine.set_ib_runtime_service(service)
        controller = AlgorithmWorkspaceController()
        controller.set_runtime_engine(engine)
        workspace = _workspace(account_id)
        runtime = controller.attach_workspace_runtime(workspace)

        engine.repository.record_ib_daily_realized_coverage(
            account_id=account_id,
            start_utc=day_start,
            end_utc=coverage_end,
            source="TEST_ONLY_COMPLETE_COVERAGE",
        )
        _persist_authority(
            engine,
            account_id=account_id,
            captured_utc=watermark,
        )
        snapshot = controller.sync_workspace_risk_account_snapshot(
            workspace.workspace_uid
        )
        if snapshot is None:
            raise AssertionError("complete IB risk snapshot is missing")

        exact_watermark_preserved = snapshot.snapshot_utc == watermark
        all_required_fields_available = (
            snapshot.equity == 100_000.0
            and snapshot.daily_realized_pnl == 0.0
            and snapshot.open_positions_count == 0
            and snapshot.binding_verified
        )
        runtime_snapshot_matches = runtime.risk_account_snapshot == snapshot
        engine.connection.close()

    policy = WorkspaceRiskPolicy(
        max_risk_percent=2.0,
        maximum_position_volume=2.0,
        maximum_open_positions=1,
        max_daily_loss_percent=5.0,
        require_stop_loss=True,
    )
    evaluator = WorkspaceRiskEvaluator(policy)
    nominal_request = _request(
        timestamp=watermark + timedelta(seconds=1),
        workspace_uid=snapshot.workspace_uid,
        account_id=account_id,
        equity=snapshot.equity,
        daily_realized_pnl=snapshot.daily_realized_pnl,
        open_positions_count=snapshot.open_positions_count,
    )
    nominal_decision = evaluator.evaluate(nominal_request)
    complete_snapshot_allows_risk = (
        nominal_decision.allowed
        and nominal_decision.reason_code == RISK_REASON_APPROVED
        and not nominal_decision.execution_attempted
    )

    missing_pnl_decision = evaluator.evaluate(
        replace(nominal_request, daily_realized_pnl=None)
    )
    missing_pnl_blocks = (
        missing_pnl_decision.reason_code
        == RISK_REASON_DAILY_PNL_SNAPSHOT_MISSING
    )
    missing_count_decision = evaluator.evaluate(
        replace(nominal_request, open_positions_count=None)
    )
    missing_count_blocks = (
        missing_count_decision.reason_code
        == RISK_REASON_OPEN_POSITIONS_SNAPSHOT_MISSING
    )
    open_limit_decision = evaluator.evaluate(
        replace(nominal_request, open_positions_count=1)
    )
    open_position_limit_consumes_snapshot = (
        open_limit_decision.reason_code
        == RISK_REASON_MAXIMUM_OPEN_POSITIONS_REACHED
    )
    daily_loss_decision = evaluator.evaluate(
        replace(nominal_request, daily_realized_pnl=-5_000.0)
    )
    daily_loss_limit_consumes_snapshot = (
        daily_loss_decision.reason_code
        == RISK_REASON_DAILY_LOSS_LIMIT_REACHED
    )

    before_watermark_decision = evaluator.evaluate(
        replace(
            nominal_request,
            timestamp=watermark - timedelta(seconds=1),
        )
    )
    future_snapshot_not_rejected = before_watermark_decision.allowed
    stale_decision = evaluator.evaluate(
        replace(
            nominal_request,
            timestamp=watermark + timedelta(hours=6),
        )
    )
    stale_snapshot_not_rejected = stale_decision.allowed

    risk_source = risk_path.read_text(encoding="utf-8")
    runtime_source = runtime_path.read_text(encoding="utf-8")
    request_section = _section(
        risk_source,
        "class WorkspaceRiskRequest:",
        "class WorkspaceRiskDecision:",
    )
    evaluation_section = _section(
        runtime_source,
        "    def _evaluate_signal_risk(",
        "    def _signal_uid(",
    )
    risk_request_carries_snapshot_timestamp = (
        "snapshot_utc" in request_section
    )
    runtime_compares_snapshot_to_decision_time = (
        "snapshot.snapshot_utc" in evaluation_section
    )
    hashes_after = _hashes(production_paths)
    production_change = hashes_before != hashes_after
    risk_snapshot_wiring_added = False
    broker_requests = 0

    assert exact_watermark_preserved
    assert all_required_fields_available
    assert runtime_snapshot_matches
    assert complete_snapshot_allows_risk
    assert missing_pnl_blocks
    assert missing_count_blocks
    assert open_position_limit_consumes_snapshot
    assert daily_loss_limit_consumes_snapshot
    assert future_snapshot_not_rejected
    assert stale_snapshot_not_rejected
    assert not risk_request_carries_snapshot_timestamp
    assert not runtime_compares_snapshot_to_decision_time
    assert not production_change
    assert not risk_snapshot_wiring_added
    assert broker_requests == 0

    print("T109-107_IB_WORKSPACE_RISK_CAUSAL_COMPLETENESS=OK")
    print("test_scope_test_only=True")
    print(f"production_change={production_change}")
    print(f"schema_version={SCHEMA_VERSION}")
    print(f"exact_watermark_preserved={exact_watermark_preserved}")
    print(
        "all_required_fields_available="
        f"{all_required_fields_available}"
    )
    print(f"runtime_snapshot_matches={runtime_snapshot_matches}")
    print(
        "complete_snapshot_allows_risk="
        f"{complete_snapshot_allows_risk}"
    )
    print(f"missing_pnl_blocks={missing_pnl_blocks}")
    print(f"missing_count_blocks={missing_count_blocks}")
    print(
        "open_position_limit_consumes_snapshot="
        f"{open_position_limit_consumes_snapshot}"
    )
    print(
        "daily_loss_limit_consumes_snapshot="
        f"{daily_loss_limit_consumes_snapshot}"
    )
    print(f"future_snapshot_not_rejected={future_snapshot_not_rejected}")
    print(f"stale_snapshot_not_rejected={stale_snapshot_not_rejected}")
    print(
        "risk_request_carries_snapshot_timestamp="
        f"{risk_request_carries_snapshot_timestamp}"
    )
    print(
        "runtime_compares_snapshot_to_decision_time="
        f"{runtime_compares_snapshot_to_decision_time}"
    )
    print(f"risk_snapshot_wiring_added={risk_snapshot_wiring_added}")
    print(f"broker_requests={broker_requests}")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


def test_t109_107_ib_workspace_risk_causal_completeness() -> None:
    """Запустити T109-107 як pytest test."""
    main()


if __name__ == "__main__":
    main()
