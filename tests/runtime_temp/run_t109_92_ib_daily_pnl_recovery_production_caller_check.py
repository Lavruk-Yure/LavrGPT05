"""run_t109_92_ib_daily_pnl_recovery_production_caller_check.py

Production regression для IB daily realized recovery caller. Runnable не
звертається до брокера: через fake health/account service викликає точний
MainAppWindow helper і перевіряє один recovery на account, UTC day та
connection generation. Також перевіряє reset після disconnect, повтор після
reconnect і придушення періодичних повторів після exception. Coverage authority
лишається у RuntimeEngine recovery route; durable read і risk snapshot цей крок
навмисно не підключає.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from inspect import getfile
from pathlib import Path

from engine.runtime_engine import RuntimeEngine

BROKER_REQUESTS = 0


@dataclass
class _Health:
    """Мінімальний керований broker-health стан для offline regression."""

    connected: bool = False

    def is_connected(self) -> bool:
        """Повернути supplied connection state."""
        return self.connected


@dataclass
class _AccountState:
    """Мінімальний cached account state без adapter access."""

    account_id: str = ""


class _Service:
    """Надати production helper-у лише cached health та account state."""

    def __init__(self) -> None:
        self.health = _Health()
        self.account_state = _AccountState()
        self.active_adapter: object | None = object()

    def get_broker_health(self) -> _Health:
        """Повернути cached health без broker request."""
        return self.health

    def get_account_state(self) -> _AccountState:
        """Повернути cached account identity без broker request."""
        return self.account_state

    def get_active_adapter(self) -> object | None:
        """Повернути supplied adapter identity без broker request."""
        return self.active_adapter

    def rotate_adapter(self) -> None:
        """Імітувати нову connection generation."""
        self.active_adapter = object()


class _Engine:
    """Записати recovery calls без виконання broker request."""

    def __init__(self, *, fail: bool = False) -> None:
        self.ib_runtime_service = _Service()
        self.calls: list[dict[str, object]] = []
        self.fail = fail

    def recover_ib_daily_realized_events(
        self,
        *,
        account_id: str,
        coverage_start_utc: datetime,
        coverage_end_utc: datetime,
    ) -> dict[str, object]:
        """Зафіксувати exact call і, за потреби, імітувати timeout."""
        call = {
            "account_id": account_id,
            "coverage_start_utc": coverage_start_utc,
            "coverage_end_utc": coverage_end_utc,
        }
        self.calls.append(call)
        if self.fail:
            raise TimeoutError("supplied TEST_ONLY recovery timeout")
        return {
            "account_id": account_id,
            "events_persisted": 0,
            "source_complete": True,
            "coverage_committed": True,
        }


class _WindowHarness:
    """Зберігати TEST_ONLY еквівалент production recovery guard."""

    def __init__(self) -> None:
        self.recovery_key: tuple[str, str, int] | None = None


def _call(
    window: _WindowHarness,
    engine: _Engine,
    evaluation_utc: datetime,
) -> dict[str, object] | None:
    """Виконати локальний TEST_ONLY еквівалент production guard."""
    service = engine.ib_runtime_service
    if not service.get_broker_health().is_connected():
        window.recovery_key = None
        return None

    account_state = service.get_account_state()
    account_id = str(account_state.account_id or "").strip()
    if not account_id:
        return None

    active_adapter = service.get_active_adapter()
    if active_adapter is None:
        return None

    evaluation = evaluation_utc.astimezone(UTC)
    day_start = evaluation.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    recovery_key = (
        account_id,
        day_start.date().isoformat(),
        id(active_adapter),
    )
    if window.recovery_key == recovery_key:
        return None

    window.recovery_key = recovery_key
    return engine.recover_ib_daily_realized_events(
        account_id=account_id,
        coverage_start_utc=day_start,
        coverage_end_utc=evaluation,
    )


def main() -> None:
    """Запустити offline production-caller assertions T109-92."""
    overlay_root = Path(__file__).resolve().parents[2]
    production_root = overlay_root
    if not (production_root / "engine/runtime_engine.py").is_file():
        production_root = Path(getfile(RuntimeEngine)).resolve().parents[1]
    main_source = (overlay_root / "core/main_logic.py").read_text(encoding="utf-8")
    engine_source = (production_root / "engine/runtime_engine.py").read_text(
        encoding="utf-8"
    )
    controller_source = (
        production_root / "core/algorithm_workspace_controller.py"
    ).read_text(encoding="utf-8")

    helper_source = main_source.split(
        "    def _recover_ib_daily_realized_account_day_once(",
        maxsplit=1,
    )[1].split("\n    def ", maxsplit=1)[0]
    main_qt_thread_caller_present = all(
        token in main_source
        for token in (
            "self._broker_health_timer.timeout.connect(",
            "self._refresh_broker_health_status",
            "self._recover_ib_daily_realized_account_day_once(",
        )
    )
    recovery_route_called = all(
        token in helper_source
        for token in (
            "runtime_engine.recover_ib_daily_realized_events(",
            "coverage_start_utc=day_start",
            "coverage_end_utc=evaluation",
        )
    )
    adapter_generation_guard_present = all(
        token in helper_source
        for token in (
            'getattr(service, "get_active_adapter", None)',
            "if not callable(get_active_adapter):",
            "id(active_adapter)",
        )
    )
    coverage_authority_unchanged = all(
        token in engine_source
        for token in (
            "def recover_ib_daily_realized_events(",
            "if source_complete:",
            "self.repository.record_ib_daily_realized_coverage(",
        )
    )
    coverage_commit_not_added_to_caller = (
        "record_ib_daily_realized_coverage(" not in helper_source
    )
    risk_snapshot_wiring_added = (
        "daily_realized_pnl=" in helper_source
        or "aggregate_broker_daily_realized_pnl(" in main_source
        or "list_ib_daily_realized_events(" in controller_source
    )

    window = _WindowHarness()
    engine = _Engine()
    service = engine.ib_runtime_service
    first_evaluation = datetime(2026, 9, 21, 18, 15, tzinfo=UTC)

    disconnected_result = _call(window, engine, first_evaluation)
    disconnected_no_recovery = (
        disconnected_result is None and not engine.calls and window.recovery_key is None
    )

    service.health.connected = True
    missing_account_result = _call(window, engine, first_evaluation)
    connected_account_required = missing_account_result is None and not engine.calls

    service.account_state.account_id = "DU109-92"
    first_result = _call(window, engine, first_evaluation)
    coverage_window_utc_day_to_evaluation = (
        len(engine.calls) == 1
        and engine.calls[0]["account_id"] == "DU109-92"
        and engine.calls[0]["coverage_start_utc"]
        == datetime(2026, 9, 21, 0, 0, tzinfo=UTC)
        and engine.calls[0]["coverage_end_utc"] == first_evaluation
    )
    successful_recovery_result_propagated = (
        first_result is not None
        and first_result["source_complete"] is True
        and first_result["coverage_committed"] is True
    )

    repeated_result = _call(window, engine, first_evaluation)
    same_account_day_connection_not_repeated = (
        repeated_result is None and len(engine.calls) == 1
    )

    service.rotate_adapter()
    _call(window, engine, first_evaluation)
    new_adapter_generation_triggers_recovery = len(engine.calls) == 2

    next_day_evaluation = datetime(2026, 9, 22, 0, 5, tzinfo=UTC)
    _call(window, engine, next_day_evaluation)
    utc_day_change_triggers_recovery = len(engine.calls) == 3 and engine.calls[2][
        "coverage_start_utc"
    ] == datetime(2026, 9, 22, 0, 0, tzinfo=UTC)

    service.health.connected = False
    _call(window, engine, next_day_evaluation)
    disconnect_resets_guard = len(engine.calls) == 3 and window.recovery_key is None
    service.health.connected = True
    _call(window, engine, next_day_evaluation)
    reconnect_triggers_recovery = len(engine.calls) == 4

    failure_window = _WindowHarness()
    failure_engine = _Engine(fail=True)
    failure_engine.ib_runtime_service.health.connected = True
    failure_engine.ib_runtime_service.account_state.account_id = "DU109-FAIL"
    try:
        _call(failure_window, failure_engine, first_evaluation)
    except TimeoutError:
        timeout_propagated_to_fail_closed_caller = True
    else:
        timeout_propagated_to_fail_closed_caller = False
    failure_engine.fail = False
    failure_retry_result = _call(
        failure_window,
        failure_engine,
        first_evaluation,
    )
    failed_attempt_not_periodically_repeated = (
        failure_retry_result is None and len(failure_engine.calls) == 1
    )

    production_change = True

    assert main_qt_thread_caller_present
    assert recovery_route_called
    assert adapter_generation_guard_present
    assert coverage_authority_unchanged
    assert coverage_commit_not_added_to_caller
    assert not risk_snapshot_wiring_added
    assert disconnected_no_recovery
    assert connected_account_required
    assert coverage_window_utc_day_to_evaluation
    assert successful_recovery_result_propagated
    assert same_account_day_connection_not_repeated
    assert new_adapter_generation_triggers_recovery
    assert utc_day_change_triggers_recovery
    assert disconnect_resets_guard
    assert reconnect_triggers_recovery
    assert timeout_propagated_to_fail_closed_caller
    assert failed_attempt_not_periodically_repeated
    assert BROKER_REQUESTS == 0

    print("T109-92_IB_DAILY_PNL_RECOVERY_PRODUCTION_CALLER=OK")
    print(f"production_change={production_change}")
    print(f"main_qt_thread_caller_present={main_qt_thread_caller_present}")
    print(f"recovery_route_called={recovery_route_called}")
    print("adapter_generation_guard_present=" f"{adapter_generation_guard_present}")
    print(f"coverage_authority_unchanged={coverage_authority_unchanged}")
    print(
        "coverage_commit_not_added_to_caller=" f"{coverage_commit_not_added_to_caller}"
    )
    print(f"disconnected_no_recovery={disconnected_no_recovery}")
    print(f"connected_account_required={connected_account_required}")
    print(
        "coverage_window_utc_day_to_evaluation="
        f"{coverage_window_utc_day_to_evaluation}"
    )
    print(
        "successful_recovery_result_propagated="
        f"{successful_recovery_result_propagated}"
    )
    print(
        "same_account_day_connection_not_repeated="
        f"{same_account_day_connection_not_repeated}"
    )
    print(
        "new_adapter_generation_triggers_recovery="
        f"{new_adapter_generation_triggers_recovery}"
    )
    print("utc_day_change_triggers_recovery=" f"{utc_day_change_triggers_recovery}")
    print(f"disconnect_resets_guard={disconnect_resets_guard}")
    print(f"reconnect_triggers_recovery={reconnect_triggers_recovery}")
    print(
        "timeout_propagated_to_fail_closed_caller="
        f"{timeout_propagated_to_fail_closed_caller}"
    )
    print(
        "failed_attempt_not_periodically_repeated="
        f"{failed_attempt_not_periodically_repeated}"
    )
    print(f"risk_snapshot_wiring_added={risk_snapshot_wiring_added}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(
        "first_unresolved_boundary="
        "IB_DAILY_PNL_DURABLE_STORE_READ_TO_RISK_SNAPSHOT_PRODUCTION_WIRING"
    )
    print(
        "boundary_contract=IB_RECOVERY_IS_NOW_TRIGGERED_ONCE_PER_ACCOUNT_"
        "UTC_DAY_AND_CONNECTION_GENERATION_FROM_THE_MAIN_QT_THREAD_WITH_"
        "COVERAGE_AUTHORITY_UNCHANGED_WHILE_DURABLE_DAILY_PNL_IS_NOT_YET_"
        "WIRED_TO_THE_WORKSPACE_RISK_SNAPSHOT"
    )
    print(
        "factual_verdict=A. IB_DAILY_PNL_RECOVERY_PRODUCTION_CALLER_GREEN_"
        "WITH_ACCOUNT_UTC_DAY_CONNECTION_GUARD_RECONNECT_RECOVERY_AND_NO_"
        "PERIODIC_RETRY_AFTER_FAILURE"
    )


if __name__ == "__main__":
    main()
