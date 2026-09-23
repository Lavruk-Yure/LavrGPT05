"""run_t109_108_ib_risk_snapshot_decision_time_freshness_contract_check.py.

TEST_ONLY contract check визначає decision-time freshness для BROKER workspace
risk snapshot. Чинний account refresh cadence є єдиним production source
числової межі; runner не прирівнює broker request timeout або сторонній cache
cadence до risk freshness.

Локальний еталон перевіряє missing, future, exact, boundary і stale timestamps,
а також окремий Replay scope. Production sources хешуються; schema, risk
evaluator, lifecycle та broker API не змінюються.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from inspect import getfile
from pathlib import Path

from core.algorithm_workspace import (
    WORKSPACE_DATA_MODE_BROKER,
    WORKSPACE_DATA_MODE_REPLAY,
)
from core.main_logic import MainAppWindow
from core.workspace_runtime import WorkspaceRuntime
from engine.risk.risk_model import WorkspaceRiskRequest
from engine.runtime_constants import RUNTIME_ACCOUNT_REFRESH_INTERVAL_SECONDS

SELECTED_MAX_AGE_SECONDS = RUNTIME_ACCOUNT_REFRESH_INTERVAL_SECONDS
SELECTED_RULE = (
    "BROKER_REQUIRES_ZERO_LE_DECISION_MINUS_ACCOUNT_SNAPSHOT_LE_"
    "ACCOUNT_REFRESH_INTERVAL"
)
FIRST_UNRESOLVED_BOUNDARY = (
    "IB_WORKSPACE_RISK_SNAPSHOT_DECISION_TIME_FRESHNESS_PRODUCTION_WIRING"
)
BOUNDARY_CONTRACT = (
    "BROKER_RISK_MUST_CARRY_ACCOUNT_SNAPSHOT_UTC_AND_BLOCK_MISSING_FUTURE_"
    "OR_OLDER_THAN_ACCOUNT_REFRESH_INTERVAL_INPUT_WHILE_REPLAY_RETAINS_"
    "ITS_EVENT_TIME_CONTRACT"
)
FACTUAL_VERDICT = (
    "A. IB_BROKER_RISK_DECISION_TIME_FRESHNESS_CONTRACT_SELECTED_WITH_"
    "ACCOUNT_REFRESH_INTERVAL_MAX_AGE_FUTURE_AND_STALE_FAIL_CLOSED_AND_"
    "REPLAY_EXCLUDED"
)


def _hashes(paths: tuple[Path, ...]) -> dict[str, str]:
    """Порахувати hashes scoped production sources."""
    return {
        path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def _reference_freshness_allows(
    *,
    source_mode: str,
    account_snapshot_utc: datetime | None,
    decision_utc: datetime,
    max_age: timedelta,
) -> bool:
    """Застосувати TEST_ONLY еталон обраного BROKER freshness contract."""
    mode = str(source_mode or "").strip().upper()
    if mode != WORKSPACE_DATA_MODE_BROKER:
        return mode == WORKSPACE_DATA_MODE_REPLAY
    if account_snapshot_utc is None:
        return False
    if (
        account_snapshot_utc.tzinfo is None
        or account_snapshot_utc.utcoffset() is None
        or decision_utc.tzinfo is None
        or decision_utc.utcoffset() is None
    ):
        return False
    age = decision_utc.astimezone(UTC) - account_snapshot_utc.astimezone(UTC)
    return timedelta(0) <= age <= max_age


def _section(source: str, start: str, end: str) -> str:
    """Виділити production class/method section для static assertions."""
    start_index = source.index(start)
    end_index = source.index(end, start_index + len(start))
    return source[start_index:end_index]


def main() -> None:
    """Запустити decision-time freshness contract assertions T109-108."""
    main_path = Path(getfile(MainAppWindow)).resolve()
    runtime_path = Path(getfile(WorkspaceRuntime)).resolve()
    risk_path = Path(getfile(WorkspaceRiskRequest)).resolve()
    constants_path = (
        main_path.parents[1] / "engine/runtime_constants.py"
    )
    risk_constants_path = main_path.parents[1] / "engine/risk/constants.py"
    production_paths = (
        main_path,
        runtime_path,
        risk_path,
        constants_path,
        risk_constants_path,
    )
    hashes_before = _hashes(production_paths)

    decision_utc = datetime(2026, 9, 23, 15, 30, 0, tzinfo=UTC)
    max_age = timedelta(seconds=SELECTED_MAX_AGE_SECONDS)
    missing_broker_snapshot_blocks = not _reference_freshness_allows(
        source_mode=WORKSPACE_DATA_MODE_BROKER,
        account_snapshot_utc=None,
        decision_utc=decision_utc,
        max_age=max_age,
    )
    future_broker_snapshot_blocks = not _reference_freshness_allows(
        source_mode=WORKSPACE_DATA_MODE_BROKER,
        account_snapshot_utc=decision_utc + timedelta(microseconds=1),
        decision_utc=decision_utc,
        max_age=max_age,
    )
    exact_timestamp_allowed = _reference_freshness_allows(
        source_mode=WORKSPACE_DATA_MODE_BROKER,
        account_snapshot_utc=decision_utc,
        decision_utc=decision_utc,
        max_age=max_age,
    )
    exact_max_age_boundary_allowed = _reference_freshness_allows(
        source_mode=WORKSPACE_DATA_MODE_BROKER,
        account_snapshot_utc=decision_utc - max_age,
        decision_utc=decision_utc,
        max_age=max_age,
    )
    older_than_boundary_blocks = not _reference_freshness_allows(
        source_mode=WORKSPACE_DATA_MODE_BROKER,
        account_snapshot_utc=(
            decision_utc - max_age - timedelta(microseconds=1)
        ),
        decision_utc=decision_utc,
        max_age=max_age,
    )
    replay_scope_unchanged = _reference_freshness_allows(
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
        account_snapshot_utc=None,
        decision_utc=decision_utc,
        max_age=max_age,
    )

    main_source = main_path.read_text(encoding="utf-8")
    risk_source = risk_path.read_text(encoding="utf-8")
    risk_constants_source = risk_constants_path.read_text(encoding="utf-8")
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
    refresh_section = _section(
        main_source,
        "    def _refresh_broker_health_status(",
        "    def _recover_ib_daily_realized_account_day_once(",
    )
    cadence_is_account_refresh_source = all(
        token in refresh_section
        for token in (
            "RUNTIME_ACCOUNT_REFRESH_INTERVAL_SECONDS",
            "ib_service.refresh_account_state()",
            "should_refresh_account",
        )
    )
    refresh_failure_can_leave_cached_state = all(
        token in refresh_section
        for token in (
            'logger.exception("IB broker health/account refresh failed.")',
            "self.page_monitoring.sync_broker_risk_account_snapshots(",
        )
    )
    request_timestamp_field_present = "account_snapshot_utc" in request_section
    evaluator_freshness_check_present = all(
        token in evaluator_section
        for token in (
            "account_snapshot_utc",
            "max_account_snapshot_age",
        )
    )
    freshness_reason_codes_present = all(
        token in risk_constants_source
        for token in (
            "ACCOUNT_SNAPSHOT_FUTURE",
            "ACCOUNT_SNAPSHOT_STALE",
        )
    )
    user_setting_selected = False
    new_schema_required = False
    hashes_after = _hashes(production_paths)
    production_change = hashes_before != hashes_after
    broker_requests = 0

    assert SELECTED_MAX_AGE_SECONDS == 30.0
    assert missing_broker_snapshot_blocks
    assert future_broker_snapshot_blocks
    assert exact_timestamp_allowed
    assert exact_max_age_boundary_allowed
    assert older_than_boundary_blocks
    assert replay_scope_unchanged
    assert cadence_is_account_refresh_source
    assert refresh_failure_can_leave_cached_state
    assert not request_timestamp_field_present
    assert not evaluator_freshness_check_present
    assert not freshness_reason_codes_present
    assert not user_setting_selected
    assert not new_schema_required
    assert not production_change
    assert broker_requests == 0

    print("T109-108_IB_RISK_DECISION_TIME_FRESHNESS_CONTRACT=OK")
    print("test_scope_test_only=True")
    print(f"production_change={production_change}")
    print(f"selected_rule={SELECTED_RULE}")
    print(f"selected_max_age_seconds={SELECTED_MAX_AGE_SECONDS}")
    print(
        "cadence_is_account_refresh_source="
        f"{cadence_is_account_refresh_source}"
    )
    print(
        "refresh_failure_can_leave_cached_state="
        f"{refresh_failure_can_leave_cached_state}"
    )
    print(
        "missing_broker_snapshot_blocks="
        f"{missing_broker_snapshot_blocks}"
    )
    print(
        "future_broker_snapshot_blocks="
        f"{future_broker_snapshot_blocks}"
    )
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
    print(f"user_setting_selected={user_setting_selected}")
    print(f"new_schema_required={new_schema_required}")
    print(f"broker_requests={broker_requests}")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


def test_t109_108_ib_risk_decision_time_freshness_contract() -> None:
    """Запустити T109-108 як pytest test."""
    main()


if __name__ == "__main__":
    main()
