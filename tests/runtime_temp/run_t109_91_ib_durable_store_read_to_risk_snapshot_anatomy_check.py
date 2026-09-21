"""run_t109_91_ib_durable_store_read_to_risk_snapshot_anatomy_check.py

TEST_ONLY anatomy durable IB daily realized PnL read-path. Runnable працює
лише з тимчасовою SQLite DB: перевіряє exact-account event read, causal UTC-day
aggregation, відсікання future events та fail-closed за відсутньої або
розірваної coverage. Статична частина фіксує наявні production API, відсутній
recovery caller і ще не підключене значення до workspace risk snapshot.
Broker requests і production-зміни цей крок навмисно не виконує.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from inspect import getfile
from pathlib import Path

from engine.daily_realized_pnl import (
    BrokerDailyRealizedPnlResult,
    aggregate_broker_daily_realized_pnl,
)
from engine.runtime_engine import RuntimeEngine

BROKER_REQUESTS = 0


def _project_root() -> Path:
    """Знайти live project root і для installed, і для staging runner-а."""
    installed_root = Path(__file__).resolve().parents[2]
    if (installed_root / "engine/runtime_engine.py").is_file():
        return installed_root
    return Path(getfile(RuntimeEngine)).resolve().parents[1]


def _read(project_root: Path, relative_path: str) -> str:
    """Прочитати один production-модуль для bounded static assertions."""
    return (project_root / relative_path).read_text(encoding="utf-8")


def _persist_event(
    engine: RuntimeEngine,
    *,
    account_id: str,
    exec_id: str,
    execution_time: str,
    amount: float,
) -> None:
    """Записати supplied canonical IB event без broker access."""
    payload: dict[str, object] = {
        "broker": "IB",
        "account_id": account_id,
        "exec_id": exec_id,
        "execution_time": execution_time,
        "net_realized_pnl": amount,
    }
    engine.repository.upsert_ib_daily_realized_event(
        account_id=account_id,
        exec_id=exec_id,
        execution_time=execution_time,
        net_realized_pnl=amount,
        payload=payload,
    )


def _aggregate(
    engine: RuntimeEngine,
    *,
    account_id: str,
    evaluation_utc: datetime,
    source_complete: bool,
) -> BrokerDailyRealizedPnlResult:
    """Агрегувати durable events з явно переданою coverage authority."""
    return aggregate_broker_daily_realized_pnl(
        broker="IB",
        account_id=account_id,
        events=engine.repository.list_ib_daily_realized_events(
            account_id=account_id
        ),
        evaluation_utc=evaluation_utc,
        source_complete=source_complete,
    )


def main() -> None:
    """Запустити offline anatomy assertions T109-91."""
    project_root = _project_root()
    repository_source = _read(project_root, "engine/runtime_repository.py")
    aggregate_source = _read(project_root, "engine/daily_realized_pnl.py")
    engine_source = _read(project_root, "engine/runtime_engine.py")
    controller_source = _read(
        project_root,
        "core/algorithm_workspace_controller.py",
    )
    main_source = _read(project_root, "core/main_logic.py")
    risk_source = _read(project_root, "engine/risk/risk_model.py")

    durable_event_read_api_present = (
        "def list_ib_daily_realized_events(" in repository_source
    )
    durable_coverage_read_api_present = all(
        token in repository_source
        for token in (
            "def list_ib_daily_realized_coverage(",
            "def ib_daily_realized_coverage_is_complete(",
        )
    )
    causal_daily_aggregator_present = (
        "def aggregate_broker_daily_realized_pnl(" in aggregate_source
    )
    aggregator_requires_source_complete = all(
        token in aggregate_source
        for token in (
            "if not source_complete:",
            '"Canonical realized-event source is incomplete."',
            "daily_realized_pnl=None",
        )
    )
    aggregator_uses_exact_account_utc_day = all(
        token in aggregate_source
        for token in (
            "event_account != account",
            "day_start = evaluation.replace(",
            "day_end = day_start + timedelta(days=1)",
        )
    )
    aggregator_excludes_future_events = "timestamp >= evaluation" in (
        aggregate_source
    )
    risk_snapshot_daily_pnl_field_present = (
        "daily_realized_pnl=None" in controller_source
    )
    risk_missing_daily_pnl_fail_closed = all(
        token in risk_source
        for token in (
            "if request.daily_realized_pnl is None:",
            "RISK_REASON_DAILY_PNL_SNAPSHOT_MISSING",
        )
    )
    controller_daily_pnl_is_none = (
        "daily_realized_pnl=None" in controller_source
    )

    production_read_consumers = "\n".join(
        (engine_source, controller_source, main_source)
    )
    durable_read_to_risk_snapshot_wiring_present = any(
        token in production_read_consumers
        for token in (
            "aggregate_broker_daily_realized_pnl(",
            "list_ib_daily_realized_events(",
            "ib_daily_realized_coverage_is_complete(",
        )
    )
    recovery_route_present = all(
        token in engine_source
        for token in (
            "def recover_ib_daily_realized_events(",
            "record_ib_daily_realized_coverage(",
        )
    )
    recovery_production_caller_present = (
        engine_source.count("recover_ib_daily_realized_events(") > 1
        or "recover_ib_daily_realized_events(" in controller_source
        or "recover_ib_daily_realized_events(" in main_source
    )

    evaluation_utc = datetime(2026, 9, 21, 18, 0, tzinfo=UTC)
    day_start_utc = evaluation_utc.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    with tempfile.TemporaryDirectory(prefix="t109_91_") as temp_dir:
        engine = RuntimeEngine(
            db_path=str(Path(temp_dir) / "runtime.sqlite3")
        )
        _persist_event(
            engine,
            account_id="DU109-A",
            exec_id="E91-A",
            execution_time="20260921 10:00:00 UTC",
            amount=7.25,
        )
        _persist_event(
            engine,
            account_id="DU109-A",
            exec_id="E91-B",
            execution_time="20260921 12:30:00 UTC",
            amount=-2.00,
        )
        _persist_event(
            engine,
            account_id="DU109-B",
            exec_id="E91-WRONG-ACCOUNT",
            execution_time="20260921 11:00:00 UTC",
            amount=1000.0,
        )
        _persist_event(
            engine,
            account_id="DU109-A",
            exec_id="E91-FUTURE",
            execution_time="20260921 19:00:00 UTC",
            amount=500.0,
        )

        account_events = engine.repository.list_ib_daily_realized_events(
            account_id="DU109-A"
        )
        exact_account_scope_read = (
            len(account_events) == 3
            and all(
                event.get("account_id") == "DU109-A"
                for event in account_events
            )
        )

        no_coverage_complete = (
            engine.repository.ib_daily_realized_coverage_is_complete(
                account_id="DU109-A",
                day_start_utc=day_start_utc,
                evaluation_utc=evaluation_utc,
            )
        )
        no_coverage_result = _aggregate(
            engine,
            account_id="DU109-A",
            evaluation_utc=evaluation_utc,
            source_complete=no_coverage_complete,
        )
        live_events_alone_do_not_prove_coverage = (
            bool(account_events)
            and not no_coverage_complete
            and not no_coverage_result.success
            and no_coverage_result.daily_realized_pnl is None
        )
        missing_coverage_blocks_aggregate = (
            not no_coverage_result.success
            and no_coverage_result.daily_realized_pnl is None
        )

        engine.repository.record_ib_daily_realized_coverage(
            account_id="DU109-A",
            start_utc=day_start_utc,
            end_utc=evaluation_utc - timedelta(minutes=1),
            source="TEST_ONLY_GAPPED_RECOVERY",
        )
        gap_complete = (
            engine.repository.ib_daily_realized_coverage_is_complete(
                account_id="DU109-A",
                day_start_utc=day_start_utc,
                evaluation_utc=evaluation_utc,
            )
        )
        gap_result = _aggregate(
            engine,
            account_id="DU109-A",
            evaluation_utc=evaluation_utc,
            source_complete=gap_complete,
        )
        coverage_gap_blocks_aggregate = (
            not gap_complete
            and not gap_result.success
            and gap_result.daily_realized_pnl is None
        )

        engine.repository.record_ib_daily_realized_coverage(
            account_id="DU109-A",
            start_utc=evaluation_utc - timedelta(minutes=1),
            end_utc=evaluation_utc,
            source="TEST_ONLY_RECOVERY_COMPLETION",
        )
        complete_coverage = (
            engine.repository.ib_daily_realized_coverage_is_complete(
                account_id="DU109-A",
                day_start_utc=day_start_utc,
                evaluation_utc=evaluation_utc,
            )
        )
        complete_result = _aggregate(
            engine,
            account_id="DU109-A",
            evaluation_utc=evaluation_utc,
            source_complete=complete_coverage,
        )
        complete_coverage_allows_aggregate = (
            complete_coverage
            and complete_result.success
            and complete_result.daily_realized_pnl == 5.25
            and complete_result.event_count == 2
        )
        future_event_excluded = (
            complete_result.event_count == 2
            and complete_result.daily_realized_pnl == 5.25
        )

        wrong_account_result = _aggregate(
            engine,
            account_id="DU109-B",
            evaluation_utc=evaluation_utc,
            source_complete=True,
        )
        wrong_account_excluded = (
            wrong_account_result.success
            and wrong_account_result.event_count == 1
            and wrong_account_result.daily_realized_pnl == 1000.0
        )
        engine.connection.close()

    test_scope_test_only = True
    production_change = False
    risk_snapshot_wiring_added = False

    assert durable_event_read_api_present
    assert durable_coverage_read_api_present
    assert causal_daily_aggregator_present
    assert aggregator_requires_source_complete
    assert aggregator_uses_exact_account_utc_day
    assert aggregator_excludes_future_events
    assert risk_snapshot_daily_pnl_field_present
    assert risk_missing_daily_pnl_fail_closed
    assert controller_daily_pnl_is_none
    assert not durable_read_to_risk_snapshot_wiring_present
    assert recovery_route_present
    assert not recovery_production_caller_present
    assert live_events_alone_do_not_prove_coverage
    assert missing_coverage_blocks_aggregate
    assert coverage_gap_blocks_aggregate
    assert complete_coverage_allows_aggregate
    assert exact_account_scope_read
    assert wrong_account_excluded
    assert future_event_excluded
    assert not risk_snapshot_wiring_added
    assert BROKER_REQUESTS == 0

    print("T109-91_IB_DURABLE_STORE_READ_TO_RISK_SNAPSHOT_ANATOMY=OK")
    print(f"test_scope_test_only={test_scope_test_only}")
    print(f"production_change={production_change}")
    print(
        "durable_event_read_api_present="
        f"{durable_event_read_api_present}"
    )
    print(
        "durable_coverage_read_api_present="
        f"{durable_coverage_read_api_present}"
    )
    print(
        "causal_daily_aggregator_present="
        f"{causal_daily_aggregator_present}"
    )
    print(
        "aggregator_requires_source_complete="
        f"{aggregator_requires_source_complete}"
    )
    print(
        "aggregator_uses_exact_account_utc_day="
        f"{aggregator_uses_exact_account_utc_day}"
    )
    print(
        "aggregator_excludes_future_events="
        f"{aggregator_excludes_future_events}"
    )
    print(
        "risk_snapshot_daily_pnl_field_present="
        f"{risk_snapshot_daily_pnl_field_present}"
    )
    print(
        "risk_missing_daily_pnl_fail_closed="
        f"{risk_missing_daily_pnl_fail_closed}"
    )
    print(f"controller_daily_pnl_is_none={controller_daily_pnl_is_none}")
    print(
        "durable_read_to_risk_snapshot_wiring_present="
        f"{durable_read_to_risk_snapshot_wiring_present}"
    )
    print(f"recovery_route_present={recovery_route_present}")
    print(
        "recovery_production_caller_present="
        f"{recovery_production_caller_present}"
    )
    print(
        "live_events_alone_do_not_prove_coverage="
        f"{live_events_alone_do_not_prove_coverage}"
    )
    print(
        "missing_coverage_blocks_aggregate="
        f"{missing_coverage_blocks_aggregate}"
    )
    print(
        "coverage_gap_blocks_aggregate="
        f"{coverage_gap_blocks_aggregate}"
    )
    print(
        "complete_coverage_allows_aggregate="
        f"{complete_coverage_allows_aggregate}"
    )
    print(f"exact_account_scope_read={exact_account_scope_read}")
    print(f"wrong_account_excluded={wrong_account_excluded}")
    print(f"future_event_excluded={future_event_excluded}")
    print(f"risk_snapshot_wiring_added={risk_snapshot_wiring_added}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(
        "recommended_sequence=RECOVER_ACCOUNT_DAY_COMMIT_COVERAGE_READ_"
        "DURABLE_EVENTS_VERIFY_COVERAGE_AGGREGATE_AT_SAME_EVALUATION_UTC_"
        "SET_RISK_SNAPSHOT"
    )
    print(
        "recommended_incomplete_behavior=KEEP_DAILY_REALIZED_PNL_NONE"
    )
    print(
        "first_unresolved_boundary="
        "IB_DAILY_PNL_RECOVERY_PRODUCTION_CALLER"
    )
    print(
        "boundary_contract=DURABLE_EVENTS_CAN_AUTHORIZE_DAILY_PNL_ONLY_"
        "AFTER_CONTIGUOUS_ACCOUNT_DAY_COVERAGE_BUT_THE_EXISTING_RECOVERY_"
        "ROUTE_HAS_NO_PRODUCTION_CALLER_AND_THE_RISK_SNAPSHOT_REMAINS_NONE"
    )
    print(
        "factual_verdict=B. IB_DURABLE_READ_COVERAGE_AND_CAUSAL_"
        "AGGREGATION_EXIST_BUT_RECOVERY_HAS_NO_PRODUCTION_CALLER_AND_"
        "DAILY_REALIZED_PNL_IS_NOT_WIRED_TO_THE_RISK_SNAPSHOT"
    )


if __name__ == "__main__":
    main()
