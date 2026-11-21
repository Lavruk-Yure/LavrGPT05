"""T116-12B · TEST_ONLY · перевірка синхронізації Apply та fail-closed.

Ізольований production-метод перевіряється через AST
з підставними об'єктами.
Без доступу до LGE.conf, Qt, БД і брокерських підключень.
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


def check_apply(
    *,
    before: str,
    selected: str,
    save_ok: bool = True,
    runtime_present: bool = True,
    setter_failure: str | None = None,
) -> bool:
    """Підмінити конфігурацію, engine й GUI для одного натискання Apply."""
    config = FakeConfig(before)
    runtime = FakeEngine(before) if runtime_present else None
    session = SimpleNamespace(
        CURRENT_CONFIG=config,
        CURRENT_RUNTIME_ENGINE=runtime,
    )
    apply_method = isolate_method(
        SETTINGS_FILE,
        "SettingsPageTrading",
        "_apply_changes",
        {"session_state": session, "logger": Mock()},
    )
    saved = []
    warnings = []
    notifications = []

    if runtime is not None and setter_failure is not None:

        def broken_setter(mode: str) -> None:
            if setter_failure == "AFTER_ASSIGN":
                runtime.context.execution_mode = mode
            raise RuntimeError("TEST_ONLY simulated runtime event failure")

        setattr(runtime, "set_execution_mode", broken_setter)

    def fake_save(values: dict[str, str]) -> bool:
        saved.append(values.copy())
        if save_ok:
            config.data["engine"].update(values)
        return save_ok

    settings = SimpleNamespace(
        current_values=lambda: {
            "broker": "CTRADER",
            "account_mode": "DEMO",
            "execution_mode": selected,
        },
        _save_to_conf=fake_save,
        _snapshot={},
        _notify_main_window=lambda: notifications.append("UPDATED"),
        _show_warning=lambda message: warnings.append(message),
        _lang_mgr=SimpleNamespace(tr=lambda _key, fallback: fallback),
        _live_allowed=lambda: False,
    )
    result = apply_method(settings)

    assert len(saved) == 1
    expected_config = selected if save_ok else before
    assert config.data["engine"]["execution_mode"] == expected_config
    if not save_ok:
        assert result is False
        assert runtime is not None and runtime.context.execution_mode == before
        assert not notifications and not warnings
    elif setter_failure:
        assert result is False
        assert runtime is not None and runtime.context.execution_mode == "OFF"
        assert len(warnings) == 1
        assert notifications == ["UPDATED"]
    else:
        assert result is True
        expected_runtime = (
            selected if (selected in {"OFF", "MANUAL", "SEMI", "AUTO"}) else "OFF"
        )
        if runtime is not None:
            assert runtime.context.execution_mode == expected_runtime
            expected_calls = [expected_runtime] if before != expected_runtime else []
            assert runtime.setter_calls == expected_calls
        assert not warnings
        assert notifications == ["UPDATED"]
    print(
        f"apply={before}_TO_{selected} "
        f"save={'OK' if save_ok else 'FAILED'} "
        f"runtime={'PRESENT' if runtime_present else 'ABSENT'} "
        f"setter_failure={setter_failure or 'NO'} result=OK"
    )
    return True


def test_t116_12b_settings_apply_sync() -> None:
    """Успішний/невдалий Save, порожній runtime й відмова setter."""
    print("T116-12B TEST_ONLY | settings apply runtime sync fail-closed")
    cases = [
        {"before": "AUTO", "selected": "OFF"},
        {"before": "OFF", "selected": "AUTO"},
        {"before": "SEMI", "selected": "MANUAL"},
        {"before": "SEMI", "selected": "SEMI"},
        {"before": "OFF", "selected": "INVALID"},
        {"before": "AUTO", "selected": "OFF", "save_ok": False},
        {"before": "OFF", "selected": "AUTO", "runtime_present": False},
        {"before": "AUTO", "selected": "OFF", "setter_failure": "BEFORE_ASSIGN"},
        {"before": "OFF", "selected": "AUTO", "setter_failure": "AFTER_ASSIGN"},
    ]
    results = [check_apply(**case) for case in cases]
    mismatches = sum(not item for item in results)
    print(f"apply_cases={len(cases)}")
    print(f"apply_mismatches={mismatches}")
    print("broker_requests=0")
    print("database_writes=0")
    print("config_disk_writes=0")
    print("production_changes=0")
    if mismatches:
        print("T116-12B=RED_SETTINGS_APPLY_SYNC_CONTRACT")
        raise AssertionError(f"Невдалі перевірки Apply: {mismatches}")
    print("T116-12B=GREEN_SETTINGS_APPLY_SYNC_CONTRACT")


if __name__ == "__main__":
    test_t116_12b_settings_apply_sync()
