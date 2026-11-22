"""T116-14C-02 · TEST_ONLY · явний дозвіл AUTO в поточній сесії.

Виконує ізольовані production GUI-методи на фіктивних об'єктах.
Не запускає Qt, мережу, БД чи файловий запис LGE.conf.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from run_t116_12_execution_mode_sync_contract import (  # noqa: E402
    SETTINGS_FILE,
    FakeEngine,
    isolate_method,
)
from run_t116_13_gui_runtime_integration_contract import (  # noqa: E402
    GUIRuntimeHarness,
)
from run_t116_14_persistent_fail_closed_contract import (  # noqa: E402
    PersistenceHarness,
)

READ_ENGINE_VALUES = isolate_method(
    SETTINGS_FILE,
    "SettingsPageTrading",
    "_read_engine_values",
    {
        "logger": Mock(),
        "DEFAULT_ENGINE": {
            "broker": "OFF",
            "account_mode": "OFF",
            "execution_mode": "OFF",
        },
    },
)


def effective_settings_mode(harness: PersistenceHarness) -> str:
    """Читати фактичне значення Settings, навіть якщо на диску AUTO."""
    fake_settings = SimpleNamespace(
        _normalize_broker=lambda value: str(value).strip().upper(),
        _normalize_account_mode=lambda value: str(value).strip().upper(),
        _normalize_execution_mode=lambda value: str(value).strip().upper(),
    )
    modules = getattr(harness, "_fake_modules")()
    setattr(modules["core.session_state"], "CURRENT_RUNTIME_ENGINE", harness.engine)
    with patch.dict(sys.modules, modules):
        values = READ_ENGINE_VALUES(fake_settings)
    return str(values["execution_mode"])


def test_t116_14c_02_session_auto_interlock() -> None:
    """Заборонити AUTO без нового явного дозволу GUI-сесії."""
    print("T116-14C-02 TEST_ONLY | Session AUTO authorization boundary")
    checks: list[bool] = []

    with (
        patch("socket.socket.connect", side_effect=AssertionError("network forbidden")),
        patch("sqlite3.connect", side_effect=AssertionError("database forbidden")),
    ):
        cold = PersistenceHarness("AUTO")
        cold.start_or_reuse()
        checks.append(
            cold.snapshot()[2:4] == ("OFF", "OFF")
            and cold.workspace_attempt() == "BLOCKED"
            and effective_settings_mode(cold) == "OFF"
        )
        print(f"cold_saved_auto_off={'OK' if checks[-1] else 'RED'}")

        enabled = PersistenceHarness("OFF")
        enabled.start_or_reuse()
        assert enabled.apply_mode("AUTO") is True
        checks.append(
            enabled.snapshot()[2:4] == ("AUTO", "AUTO")
            and getattr(enabled.engine, "execution_auto_session_armed", False) is True
            and effective_settings_mode(enabled) == "AUTO"
        )
        print(f"explicit_auto_armed={'OK' if checks[-1] else 'RED'}")

        enabled.start_or_reuse()
        checks.append(
            enabled.engine.context.execution_mode == "AUTO"
            and enabled.workspace_attempt() == "INTERCEPTED"
        )
        print(f"same_session_reuse={'OK' if checks[-1] else 'RED'}")

        cold_restart = PersistenceHarness(enabled.store.mode)
        cold_restart.start_or_reuse()
        checks.append(
            cold_restart.engine.context.execution_mode == "OFF"
            and cold_restart.workspace_attempt() == "BLOCKED"
        )
        print(f"new_process_rearm_required={'OK' if checks[-1] else 'RED'}")

        failed = PersistenceHarness("OFF")
        failed.start_or_reuse()
        assert failed.apply_mode(
            "AUTO", setter_failure="AFTER_ASSIGN", fail_protective_off=True
        ) is False
        checks.append(
            failed.store.injected_protective_failure
            and failed.store.mode == "AUTO"
            and failed.engine.context.execution_mode == "OFF"
            and getattr(failed.engine, "execution_auto_session_armed", False) is False
            and effective_settings_mode(failed) == "OFF"
            and failed.workspace_attempt() == "BLOCKED"
        )
        print(f"off_write_failure_blocked={'OK' if checks[-1] else 'RED'}")

        failed.start_or_reuse()
        checks.append(
            failed.engine.context.execution_mode == "OFF"
            and failed.workspace_attempt() == "BLOCKED"
            and failed.cold_restart_mode() == "OFF"
        )
        print(f"failure_reuse_and_cold_blocked={'OK' if checks[-1] else 'RED'}")

        revoked = PersistenceHarness("OFF")
        revoked.start_or_reuse()
        assert revoked.apply_mode("AUTO") is True
        assert revoked.apply_mode("MANUAL") is True
        revoked.config.data["engine"]["execution_mode"] = "AUTO"
        revoked.start_or_reuse()
        checks.append(
            revoked.engine.context.execution_mode == "OFF"
            and getattr(revoked.engine, "execution_auto_session_armed", False) is False
            and revoked.workspace_attempt() == "BLOCKED"
        )
        print(f"revoked_permission_stays_off={'OK' if checks[-1] else 'RED'}")

        broken = GUIRuntimeHarness("MANUAL")
        preexisting = FakeEngine("AUTO", "RUNNING")

        def failing_setter(_mode: str) -> None:
            raise RuntimeError("TEST_ONLY: startup setter failed")

        preexisting.set_execution_mode = failing_setter
        broken.session.CURRENT_RUNTIME_ENGINE = preexisting
        broken.start_or_reuse()
        checks.append(
            broken.engine.context.execution_mode == "OFF"
            and broken.workspace_attempt() == "BLOCKED"
            and broken.main.status_text == "Orders: OFF"
        )
        print(f"startup_setter_failure_off={'OK' if checks[-1] else 'RED'}")

    mismatches = sum(not result for result in checks)
    print(f"integration_cases={len(checks)}")
    print(f"integration_mismatches={mismatches}")
    print("broker_requests=0")
    print("database_writes=0")
    print("real_config_disk_writes=0")
    print("production_changes=0")
    print("actual_qt_widgets=NOT_TESTED")
    if mismatches:
        print("T116-14C-02=RED_SESSION_AUTO_INTERLOCK")
        raise AssertionError(f"Session AUTO Interlock: {mismatches} порушень")
    print("T116-14C-02=GREEN_SESSION_AUTO_INTERLOCK")


if __name__ == "__main__":
    test_t116_14c_02_session_auto_interlock()
