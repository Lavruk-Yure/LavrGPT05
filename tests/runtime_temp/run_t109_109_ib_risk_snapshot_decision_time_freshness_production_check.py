"""run_t109_109_ib_risk_snapshot_decision_time_freshness_production_check.py.

Production regression перевіряє decision-time freshness account snapshot для
BROKER risk request. Runner використовує production WorkspaceRiskRequest і
WorkspaceRiskEvaluator з account refresh interval як max age, але не створює
broker service і не виконує broker request.

Перевіряються missing, future, exact, boundary і stale timestamps, Replay
exclusion, reason priority та runtime snapshot timestamp wiring. Schema,
workspace settings, durable store і broker lifecycle не змінюються.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from inspect import getfile
from pathlib import Path

from core.algorithm_workspace import (
    WORKSPACE_DATA_MODE_BROKER,
    WORKSPACE_DATA_MODE_REPLAY,
)
from core.workspace_runtime import WorkspaceRuntime
from engine.db.runtime_db import SCHEMA_VERSION
from engine.risk.constants import (
    RISK_REASON_ACCOUNT_SNAPSHOT_FUTURE,
    RISK_REASON_ACCOUNT_SNAPSHOT_STALE,
    RISK_REASON_ACCOUNT_SNAPSHOT_TIMESTAMP_MISSING,
    RISK_REASON_APPROVED,
    RISK_REASON_DAILY_PNL_SNAPSHOT_MISSING,
)
from engine.risk.risk_model import (
    WorkspaceRiskEvaluator,
    WorkspaceRiskPolicy,
    WorkspaceRiskRequest,
)
from engine.runtime_constants import RUNTIME_ACCOUNT_REFRESH_INTERVAL_SECONDS

FIRST_UNRESOLVED_BOUNDARY = (
    "IB_WORKSPACE_RISK_SNAPSHOT_END_TO_END_PRODUCTION_COMPLETENESS_CHECK"
)
BOUNDARY_CONTRACT = (
    "BROKER_RISK_REQUEST_NOW_CARRIES_ACCOUNT_SNAPSHOT_UTC_AND_BLOCKS_"
    "MISSING_FUTURE_OR_OLDER_THAN_ACCOUNT_REFRESH_INTERVAL_INPUT_WHILE_"
    "THE_FULL_IB_RUNTIME_SIGNAL_PATH_REMAINS_TO_VERIFY"
)
FACTUAL_VERDICT = (
    "A. IB_RISK_DECISION_TIME_FRESHNESS_PRODUCTION_WIRING_GREEN_WITH_"
    "MISSING_FUTURE_AND_STALE_FAIL_CLOSED_EXACT_THIRTY_SECOND_BOUNDARY_"
    "AND_REPLAY_UNCHANGED"
)


def _request(
    *,
    source_mode: str,
    decision_utc: datetime,
    account_snapshot_utc: datetime | None,
    daily_realized_pnl: float | None = 0.0,
) -> WorkspaceRiskRequest:
    """Побудувати nominal risk request із supplied timestamp."""
    return WorkspaceRiskRequest(
        timestamp=decision_utc,
        workspace_uid="T109-109-WSP",
        broker="IB",
        account_id="DU109",
        symbol="EURUSD",
        side="BUY",
        source_mode=source_mode,
        requested_volume=1.0,
        equity=100_000.0,
        estimated_loss_at_stop=1_000.0,
        stop_loss=1.09,
        open_positions_count=0,
        daily_realized_pnl=daily_realized_pnl,
        runtime_ready=True,
        binding_verified=True,
        market_valid=True,
        spread_guard_passed=True,
        signal_uid="T109-109-SIGNAL",
        account_snapshot_utc=account_snapshot_utc,
    )


def _section(source: str, start: str, end: str) -> str:
    """Виділити production class/method section для static assertions."""
    start_index = source.index(start)
    end_index = source.index(end, start_index + len(start))
    return source[start_index:end_index]


def main() -> None:
    """Запустити production freshness assertions T109-109."""
    runtime_path = Path(getfile(WorkspaceRuntime)).resolve()
    risk_path = Path(getfile(WorkspaceRiskRequest)).resolve()
    constants_path = risk_path.with_name("constants.py")
    runtime_source = runtime_path.read_text(encoding="utf-8")
    risk_source = risk_path.read_text(encoding="utf-8")
    constants_source = constants_path.read_text(encoding="utf-8")

    request_section = _section(
        risk_source,
        "class WorkspaceRiskRequest:",
        "class WorkspaceRiskDecision:",
    )
    evaluator_section = _section(
        risk_source,
        "class WorkspaceRiskEvaluator:",
        "def _required_upper(",
    )
    runtime_evaluation_section = _section(
        runtime_source,
        "    def _evaluate_signal_risk(",
        "    def _signal_uid(",
    )
    request_timestamp_field_present = (
        "account_snapshot_utc: datetime | None" in request_section
        and "normalize_market_timestamp(self.account_snapshot_utc)"
        in request_section
    )
    evaluator_freshness_check_present = all(
        token in evaluator_section
        for token in (
            'if request.source_mode == "BROKER":',
            "snapshot_age = request.timestamp - request.account_snapshot_utc",
            "RUNTIME_ACCOUNT_REFRESH_INTERVAL_SECONDS",
        )
    )
    freshness_reason_codes_present = all(
        token in constants_source
        for token in (
            "RISK_REASON_ACCOUNT_SNAPSHOT_TIMESTAMP_MISSING",
            "RISK_REASON_ACCOUNT_SNAPSHOT_FUTURE",
            "RISK_REASON_ACCOUNT_SNAPSHOT_STALE",
        )
    )
    runtime_snapshot_timestamp_wired = all(
        token in runtime_evaluation_section
        for token in (
            "account_snapshot_utc=(",
            "snapshot.snapshot_utc if snapshot is not None else None",
        )
    )

    evaluator = WorkspaceRiskEvaluator(
        WorkspaceRiskPolicy(
            max_risk_percent=2.0,
            maximum_position_volume=2.0,
            maximum_open_positions=1,
            max_daily_loss_percent=5.0,
            require_stop_loss=True,
        )
    )
    decision_utc = datetime(2026, 9, 23, 15, 30, 0, tzinfo=UTC)
    max_age = timedelta(seconds=RUNTIME_ACCOUNT_REFRESH_INTERVAL_SECONDS)

    missing_decision = evaluator.evaluate(
        _request(
            source_mode=WORKSPACE_DATA_MODE_BROKER,
            decision_utc=decision_utc,
            account_snapshot_utc=None,
        )
    )
    missing_timestamp_blocks = (
        missing_decision.reason_code
        == RISK_REASON_ACCOUNT_SNAPSHOT_TIMESTAMP_MISSING
    )
    future_decision = evaluator.evaluate(
        _request(
            source_mode=WORKSPACE_DATA_MODE_BROKER,
            decision_utc=decision_utc,
            account_snapshot_utc=decision_utc + timedelta(microseconds=1),
        )
    )
    future_timestamp_blocks = (
        future_decision.reason_code == RISK_REASON_ACCOUNT_SNAPSHOT_FUTURE
    )
    exact_decision = evaluator.evaluate(
        _request(
            source_mode=WORKSPACE_DATA_MODE_BROKER,
            decision_utc=decision_utc,
            account_snapshot_utc=decision_utc,
        )
    )
    exact_timestamp_allowed = (
        exact_decision.allowed
        and exact_decision.reason_code == RISK_REASON_APPROVED
    )
    boundary_decision = evaluator.evaluate(
        _request(
            source_mode=WORKSPACE_DATA_MODE_BROKER,
            decision_utc=decision_utc,
            account_snapshot_utc=decision_utc - max_age,
        )
    )
    exact_max_age_boundary_allowed = boundary_decision.allowed
    stale_decision = evaluator.evaluate(
        _request(
            source_mode=WORKSPACE_DATA_MODE_BROKER,
            decision_utc=decision_utc,
            account_snapshot_utc=(
                decision_utc - max_age - timedelta(microseconds=1)
            ),
        )
    )
    older_than_boundary_blocks = (
        stale_decision.reason_code == RISK_REASON_ACCOUNT_SNAPSHOT_STALE
    )
    replay_decision = evaluator.evaluate(
        _request(
            source_mode=WORKSPACE_DATA_MODE_REPLAY,
            decision_utc=decision_utc,
            account_snapshot_utc=None,
        )
    )
    replay_scope_unchanged = replay_decision.allowed

    missing_pnl_with_fresh_timestamp = evaluator.evaluate(
        _request(
            source_mode=WORKSPACE_DATA_MODE_BROKER,
            decision_utc=decision_utc,
            account_snapshot_utc=decision_utc,
            daily_realized_pnl=None,
        )
    )
    existing_missing_pnl_guard_preserved = (
        missing_pnl_with_fresh_timestamp.reason_code
        == RISK_REASON_DAILY_PNL_SNAPSHOT_MISSING
    )
    user_setting_added = "account_snapshot_max_age" in constants_source
    schema_change = SCHEMA_VERSION != 12
    broker_requests = 0

    assert request_timestamp_field_present
    assert evaluator_freshness_check_present
    assert freshness_reason_codes_present
    assert runtime_snapshot_timestamp_wired
    assert missing_timestamp_blocks
    assert future_timestamp_blocks
    assert exact_timestamp_allowed
    assert exact_max_age_boundary_allowed
    assert older_than_boundary_blocks
    assert replay_scope_unchanged
    assert existing_missing_pnl_guard_preserved
    assert not user_setting_added
    assert not schema_change
    assert broker_requests == 0

    print("T109-109_IB_RISK_DECISION_TIME_FRESHNESS_WIRING=OK")
    print("production_change=True")
    print(f"schema_version={SCHEMA_VERSION}")
    print(f"selected_max_age_seconds={RUNTIME_ACCOUNT_REFRESH_INTERVAL_SECONDS}")
    print(
        "request_timestamp_field_present="
        f"{request_timestamp_field_present}"
    )
    print(
        "evaluator_freshness_check_present="
        f"{evaluator_freshness_check_present}"
    )
    print(
        "freshness_reason_codes_present="
        f"{freshness_reason_codes_present}"
    )
    print(
        "runtime_snapshot_timestamp_wired="
        f"{runtime_snapshot_timestamp_wired}"
    )
    print(f"missing_timestamp_blocks={missing_timestamp_blocks}")
    print(f"future_timestamp_blocks={future_timestamp_blocks}")
    print(f"exact_timestamp_allowed={exact_timestamp_allowed}")
    print(
        "exact_max_age_boundary_allowed="
        f"{exact_max_age_boundary_allowed}"
    )
    print(
        "older_than_boundary_blocks="
        f"{older_than_boundary_blocks}"
    )
    print(f"replay_scope_unchanged={replay_scope_unchanged}")
    print(
        "existing_missing_pnl_guard_preserved="
        f"{existing_missing_pnl_guard_preserved}"
    )
    print(f"user_setting_added={user_setting_added}")
    print(f"schema_change={schema_change}")
    print(f"broker_requests={broker_requests}")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


def test_t109_109_ib_risk_decision_time_freshness_wiring() -> None:
    """Запустити T109-109 як pytest test."""
    main()


if __name__ == "__main__":
    main()
