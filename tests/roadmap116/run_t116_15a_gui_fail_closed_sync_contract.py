"""T116-15A · TEST_ONLY · синхронізація GUI після подвійної відмови.

Виконує фактичний production-метод Apply через AST. Всі збереження,
елементи GUI та RuntimeEngine підмінені локальними об'єктами в пам'яті.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from run_t116_12_execution_mode_sync_contract import (  # noqa: E402
    SETTINGS_FILE,
    FakeConfig,
    FakeEngine,
    isolate_method,
)


class FakeButton:
    """Лише стан активності Apply."""

    def __init__(self) -> None:
        self.enabled = True
        setattr(self, "setEnabled", self.set_enabled)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled


def check_case(name: str, *, failure: str, fail_protective_off: bool) -> bool:
    """Перевірити OFF у GUI навіть за невдалого аварійного запису."""
    config = FakeConfig("OFF")
    engine = FakeEngine("OFF")
    session = SimpleNamespace(
        CURRENT_CONFIG=config,
        CURRENT_RUNTIME_ENGINE=engine,
    )
    apply_method = isolate_method(
        SETTINGS_FILE,
        "SettingsPageTrading",
        "_apply_changes",
        {"session_state": session, "logger": Mock()},
    )

    def broken_setter(mode: str) -> None:
        if failure == "AFTER_ASSIGN":
            engine.context.execution_mode = mode
        raise RuntimeError("TEST_ONLY: setter rejected mode")

    engine.set_execution_mode = broken_setter
    combo = SimpleNamespace(value="AUTO")
    apply_button = FakeButton()
    warnings: list[str] = []
    notifications: list[str] = []
    attempts: list[str] = []

    def fake_save(values: dict[str, str]) -> bool:
        mode = values["execution_mode"]
        attempts.append(mode)
        if mode == "OFF" and fail_protective_off:
            return False
        config.data["engine"].update(values)
        return True

    settings = SimpleNamespace(
        ui=SimpleNamespace(comboExecutionMode=combo, btnApply=apply_button),
        _snapshot={
            "broker": "CTRADER",
            "account_mode": "DEMO",
            "execution_mode": "OFF",
        },
        _set_combo_by_data=lambda item, mode: setattr(item, "value", mode),
        _save_to_conf=fake_save,
        _show_warning=warnings.append,
        _notify_main_window=lambda: notifications.append(
            f"Orders: {engine.context.execution_mode}"
        ),
        _lang_mgr=SimpleNamespace(tr=lambda _key, fallback: fallback),
        _live_allowed=lambda: False,
        current_values=lambda: {
            "broker": "CTRADER",
            "account_mode": "DEMO",
            "execution_mode": "AUTO",
        },
    )
    result = apply_method(settings)
    expected_disk = "AUTO" if fail_protective_off else "OFF"
    matching = (
        result is False
        and engine.context.execution_mode == "OFF"
        and getattr(engine, "execution_auto_session_armed", None) is False
        and combo.value == "OFF"
        and apply_button.enabled is False
        and vars(settings)["_snapshot"]["execution_mode"] == "OFF"
        and config.data["engine"]["execution_mode"] == expected_disk
        and attempts == ["AUTO", "OFF"]
        and notifications == ["Orders: OFF"]
        and len(warnings) == 1
    )
    print(
        f"case={name} combo={combo.value} "
        f"apply_enabled={apply_button.enabled} "
        f"runtime={engine.context.execution_mode} "
        f"persisted={config.data['engine']['execution_mode']} "
        f"result={'OK' if matching else 'DRIFT'}"
    )
    return matching


def test_t116_15a_gui_fail_closed_sync() -> None:
    """Три сценарії, жодного запису на диск або звернення до брокера."""
    print("T116-15A TEST_ONLY | GUI OFF after runtime setter failure")
    checks = [
        check_case(
            "PROTECTIVE_WRITE_FAILED_BEFORE",
            failure="BEFORE_ASSIGN",
            fail_protective_off=True,
        ),
        check_case(
            "PROTECTIVE_WRITE_FAILED_AFTER",
            failure="AFTER_ASSIGN",
            fail_protective_off=True,
        ),
        check_case(
            "PROTECTIVE_WRITE_SAVED",
            failure="AFTER_ASSIGN",
            fail_protective_off=False,
        ),
    ]
    mismatches = sum(not passed for passed in checks)
    print(f"gui_cases={len(checks)}")
    print(f"gui_mismatches={mismatches}")
    print("broker_requests=0")
    print("real_config_disk_writes=0")
    print("production_changes=0")
    if mismatches:
        print("T116-15A=RED_GUI_FAIL_CLOSED_SYNC_CONTRACT")
        raise AssertionError(f"GUI OFF sync: {mismatches}/{len(checks)}")
    print("T116-15A=GREEN_GUI_FAIL_CLOSED_SYNC_CONTRACT")


if __name__ == "__main__":
    test_t116_15a_gui_fail_closed_sync()
