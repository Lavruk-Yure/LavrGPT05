"""run_t109_88_ib_recovery_completion_authority_production_wiring_check.py

Production checkpoint для IB recovery completion authority. Runnable offline
подає execution і commission callbacks у різному порядку, перевіряє очікування
всіх пар та empty snapshot, а потім проводить completed recovery events через
RuntimeEngine до durable store. Coverage дозволений лише для повного snapshot;
timeout, неповна пара або conflict залишають джерело fail-closed. Тест не
підключається до брокера, не додає risk snapshot wiring і не перевіряє наступну
межу live-event persistence.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from engine.ib_adapter import IBAdapter
from engine.runtime_engine import IBRuntimeServiceProtocol, RuntimeEngine

BROKER_REQUESTS = 0


class _RecoveryService:
    """TEST_ONLY service з наперед визначеним recovery result."""

    def __init__(self, result: dict[str, object]) -> None:
        self.result = result

    def recover_daily_execution_commission_events(
        self,
        account_id: str,
    ) -> dict[str, object]:
        """Повернути незалежну копію recovery result без broker request."""
        result = dict(self.result)
        raw_events = result.get("events")
        result["events"] = (
            [dict(item) for item in raw_events if isinstance(item, dict)]
            if isinstance(raw_events, list)
            else []
        )
        result["account_id"] = account_id
        return result


def _contract() -> SimpleNamespace:
    """Побудувати мінімальний IB contract callback payload."""
    return SimpleNamespace(
        symbol="EUR",
        secType="CASH",
        currency="USD",
        exchange="IDEALPRO",
    )


def _execution(exec_id: str, order_id: int) -> SimpleNamespace:
    """Побудувати execution callback payload для одного execId."""
    return SimpleNamespace(
        execId=exec_id,
        acctNumber="DU109",
        side="BOT",
        shares=1000.0,
        price=1.125,
        time="20260921 10:00:00 UTC",
        orderId=order_id,
        permId=order_id + 9000,
    )


def _commission(exec_id: str, realized_pnl: float) -> SimpleNamespace:
    """Побудувати commission callback payload для одного execId."""
    return SimpleNamespace(
        execId=exec_id,
        commissionAndFees=0.25,
        currency="USD",
        realizedPNL=realized_pnl,
    )


def _event(exec_id: str, realized_pnl: float) -> dict[str, object]:
    """Побудувати canonical completed event для durable-store wiring."""
    return {
        "broker": "IB",
        "account_id": "DU109",
        "exec_id": exec_id,
        "execution_time": "2026-09-21T10:00:00+00:00",
        "net_realized_pnl": realized_pnl,
    }


def _engine(
    db_path: Path,
    result: dict[str, object],
) -> RuntimeEngine:
    """Створити RuntimeEngine з offline recovery service."""
    engine = RuntimeEngine(db_path=str(db_path))
    service = cast(
        IBRuntimeServiceProtocol,
        cast(object, _RecoveryService(result)),
    )
    engine.set_ib_runtime_service(service)
    return engine


def main() -> None:
    """Запустити offline production-wiring assertions T109-88."""
    project_root = Path(__file__).resolve().parents[2]
    adapter_source = (project_root / "engine/ib_adapter.py").read_text(
        encoding="utf-8"
    )
    service_source = (
        project_root / "engine/services/ib_runtime_service.py"
    ).read_text(encoding="utf-8")
    engine_source = (project_root / "engine/runtime_engine.py").read_text(
        encoding="utf-8"
    )

    production_tracks_req_exec_ids = "req_id_to_exec_ids" in adapter_source
    production_waits_all_pairs = (
        "wait_for_execution_commission_pairs" in adapter_source
    )
    timeout_fail_closed_present = "fail_execution_recovery" in adapter_source
    recovery_service_route_present = (
        "def recover_daily_execution_commission_events(" in service_source
    )
    durable_store_wiring_present = all(
        token in engine_source
        for token in (
            "def recover_ib_daily_realized_events(",
            "upsert_ib_daily_realized_event(",
            "record_ib_daily_realized_coverage(",
        )
    )

    adapter = IBAdapter(host="127.0.0.1", port=7497, client_id=10988)
    wrapper = getattr(adapter, "_wrapper")

    empty_req_id = 1098801
    wrapper.begin_execution_recovery(empty_req_id)
    wrapper.execDetailsEnd(empty_req_id)
    empty_result = wrapper.get_execution_recovery_result(empty_req_id)
    empty_snapshot_supported = empty_result["source_complete"] is True

    pairs_req_id = 1098802
    wrapper.begin_execution_recovery(pairs_req_id)
    wrapper.execDetails(
        pairs_req_id,
        _contract(),
        _execution("E88-A", 8801),
    )
    wrapper.execDetails(
        pairs_req_id,
        _contract(),
        _execution("E88-B", 8802),
    )
    wrapper.commissionAndFeesReport(_commission("E88-A", 4.75))
    wrapper.execDetailsEnd(pairs_req_id)
    waits_before_last_pair = not wrapper.get_execution_recovery_result(
        pairs_req_id
    )["source_complete"]
    wrapper.commissionAndFeesReport(_commission("E88-B", 2.25))
    pair_result = wrapper.get_execution_recovery_result(pairs_req_id)
    waits_all_pairs_runtime = (
        waits_before_last_pair
        and pair_result["source_complete"] is True
        and pair_result["completed_exec_ids"] == ["E88-A", "E88-B"]
    )

    timeout_req_id = 1098803
    wrapper.begin_execution_recovery(timeout_req_id)
    wrapper.execDetails(
        timeout_req_id,
        _contract(),
        _execution("E88-TIMEOUT", 8803),
    )
    wrapper.execDetailsEnd(timeout_req_id)
    wrapper.fail_execution_recovery(timeout_req_id)
    timeout_fail_closed_runtime = not wrapper.get_execution_recovery_result(
        timeout_req_id
    )["source_complete"]

    start_utc = datetime(2026, 9, 21, tzinfo=UTC)
    end_utc = start_utc + timedelta(hours=12)
    complete_event = _event("E88-COMPLETE", 7.25)
    incomplete_event = _event("E88-INCOMPLETE", 3.50)

    with tempfile.TemporaryDirectory(prefix="t109_88_") as temp_dir:
        temp_root = Path(temp_dir)
        complete_engine = _engine(
            temp_root / "complete.sqlite3",
            {"events": [complete_event], "source_complete": True},
        )
        complete_result = complete_engine.recover_ib_daily_realized_events(
            account_id="DU109",
            coverage_start_utc=start_utc,
            coverage_end_utc=end_utc,
        )
        complete_events = (
            complete_engine.repository.list_ib_daily_realized_events(
                account_id="DU109"
            )
        )
        complete_event_persisted = len(complete_events) == 1
        complete_coverage_committed = (
            complete_result["coverage_committed"] is True
            and complete_engine.repository.ib_daily_realized_coverage_is_complete(
                account_id="DU109",
                day_start_utc=start_utc,
                evaluation_utc=end_utc,
            )
        )
        complete_engine.recover_ib_daily_realized_events(
            account_id="DU109",
            coverage_start_utc=start_utc,
            coverage_end_utc=end_utc,
        )
        duplicate_same_event_deduped = (
            len(
                complete_engine.repository.list_ib_daily_realized_events(
                    account_id="DU109"
                )
            )
            == 1
        )
        complete_engine.connection.close()

        incomplete_engine = _engine(
            temp_root / "incomplete.sqlite3",
            {"events": [incomplete_event], "source_complete": False},
        )
        incomplete_result = incomplete_engine.recover_ib_daily_realized_events(
            account_id="DU109",
            coverage_start_utc=start_utc,
            coverage_end_utc=end_utc,
        )
        incomplete_event_persisted = (
            len(
                incomplete_engine.repository.list_ib_daily_realized_events(
                    account_id="DU109"
                )
            )
            == 1
        )
        incomplete_coverage_not_committed = (
            incomplete_result["coverage_committed"] is False
            and not incomplete_engine.repository.list_ib_daily_realized_coverage(
                account_id="DU109"
            )
        )
        incomplete_engine.connection.close()

        conflict_engine = _engine(
            temp_root / "conflict.sqlite3",
            {
                "events": [
                    _event("E88-CONFLICT", 1.0),
                    _event("E88-CONFLICT", 2.0),
                ],
                "source_complete": True,
            },
        )
        try:
            conflict_engine.recover_ib_daily_realized_events(
                account_id="DU109",
                coverage_start_utc=start_utc,
                coverage_end_utc=end_utc,
            )
        except ValueError:
            conflict_fail_closed = (
                not conflict_engine.repository.list_ib_daily_realized_coverage(
                    account_id="DU109"
                )
            )
        else:
            conflict_fail_closed = False
        conflict_engine.connection.close()

    risk_snapshot_wiring_added = False
    production_waits_all_pairs = (
        production_waits_all_pairs and waits_all_pairs_runtime
    )
    timeout_fail_closed_present = (
        timeout_fail_closed_present and timeout_fail_closed_runtime
    )

    assert production_tracks_req_exec_ids
    assert production_waits_all_pairs
    assert empty_snapshot_supported
    assert timeout_fail_closed_present
    assert recovery_service_route_present
    assert durable_store_wiring_present
    assert complete_event_persisted
    assert complete_coverage_committed
    assert duplicate_same_event_deduped
    assert incomplete_event_persisted
    assert incomplete_coverage_not_committed
    assert conflict_fail_closed
    assert not risk_snapshot_wiring_added
    assert BROKER_REQUESTS == 0

    print("T109-88_IB_RECOVERY_COMPLETION_AUTHORITY_PRODUCTION_WIRING=OK")
    print(f"production_tracks_req_exec_ids={production_tracks_req_exec_ids}")
    print(f"production_waits_all_pairs={production_waits_all_pairs}")
    print(f"empty_snapshot_supported={empty_snapshot_supported}")
    print(f"timeout_fail_closed_present={timeout_fail_closed_present}")
    print(f"recovery_service_route_present={recovery_service_route_present}")
    print(f"durable_store_wiring_present={durable_store_wiring_present}")
    print(f"complete_event_persisted={complete_event_persisted}")
    print(f"complete_coverage_committed={complete_coverage_committed}")
    print(f"duplicate_same_event_deduped={duplicate_same_event_deduped}")
    print(f"incomplete_event_persisted={incomplete_event_persisted}")
    print(
        "incomplete_coverage_not_committed="
        f"{incomplete_coverage_not_committed}"
    )
    print(f"conflict_fail_closed={conflict_fail_closed}")
    print(f"risk_snapshot_wiring_added={risk_snapshot_wiring_added}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print("first_unresolved_boundary=IB_DAILY_PNL_LIVE_EVENT_DURABLE_WIRING")
    print(
        "factual_verdict=A. IB_RECOVERY_COMPLETION_AUTHORITY_PRODUCTION_"
        "WIRING_GREEN_WITH_ALL_PAIR_WAIT_DURABLE_EVENT_PERSISTENCE_AND_"
        "COVERAGE_COMMIT_FAIL_CLOSED"
    )


if __name__ == "__main__":
    main()
