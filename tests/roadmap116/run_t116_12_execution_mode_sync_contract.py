"""T116-12 · TEST_ONLY · контракт синхронізації LGE.conf → RuntimeEngine.

Ізольовано виконує фактичні методи GUI через AST з підставними об'єктами.
Не імпортує LGE, не відкриває конфігурацію, БД чи з'єднання з брокерами.
До production-виправлення тест повинен завершуватися RED (exit code 1).
"""

from __future__ import annotations

import ast
import copy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, cast
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
MAIN_FILE = ROOT / "core" / "main_logic.py"
SETTINGS_FILE = ROOT / "core" / "settings_page_trading.py"


class FakeConfig:
    """Конфігурація лише в оперативній пам'яті."""

    def __init__(self, mode: str):
        self.data = {
            "engine": {
                "broker": "CTRADER",
                "account_mode": "DEMO",
                "execution_mode": mode,
            }
        }

    def to_dict(self) -> dict[str, Any]:
        return self.data

    def get(self, section: str, key: str, default: Any = None) -> Any:
        return self.data.get(section, {}).get(key, default)


class FakeEngine:
    """Не має мережевих адаптерів, БД або торгової реалізації."""

    def __init__(self, mode: str = "OFF", state: str = "OFF"):
        self.context = SimpleNamespace(
            execution_mode=mode,
            runtime_state=state,
        )
        self.ib_runtime_service = object()
        self.ctrader_runtime_service = object()
        self.startup_calls = 0
        self.startup_execution_mode: str | None = None
        self.setter_calls: list[str] = []

    def startup(self) -> None:
        self.startup_calls += 1
        self.startup_execution_mode = self.context.execution_mode
        self.context.runtime_state = "RUNNING"

    def set_execution_mode(self, mode: str) -> None:
        self.setter_calls.append(mode)
        self.context.execution_mode = str(mode).strip().upper()


def isolate_method(
    path: Path,
    class_name: str,
    method_name: str,
    environment: dict[str, Any],
) -> Callable[..., Any]:
    """Витягти та виконати рівно один production-метод без імпорту модуля."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    original = next(
        node
        for node in cls.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )
    method = copy.deepcopy(original)
    method.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    namespace = dict(environment)
    exec(compile(module, str(path), "exec"), namespace)
    return cast(Callable[..., Any], namespace[method_name])


def check_startup(config_mode: str, existing_mode: str | None) -> bool:
    """Новий або повторно використаний RuntimeEngine має отримати режим до старту."""
    config = FakeConfig(config_mode)
    reused = existing_mode is not None
    existing = FakeEngine(existing_mode, "RUNNING") if reused else None
    session = SimpleNamespace(
        CURRENT_CONFIG=config,
        CURRENT_RUNTIME_ENGINE=existing,
    )
    init_method = isolate_method(
        MAIN_FILE,
        "MainAppWindow",
        "_init_runtime_engine",
        {
            "session_state": session,
            "RuntimeEngine": FakeEngine,
            "RuntimeState": SimpleNamespace(OFF="OFF"),
            "logger": Mock(),
        },
    )
    orders = Mock()
    monitoring = Mock()
    main = SimpleNamespace(page_orders=orders, page_monitoring=monitoring)
    init_method(main)
    engine = session.CURRENT_RUNTIME_ENGINE
    assert isinstance(engine, FakeEngine)
    assert main.runtime_engine is engine
    orders.set_runtime_engine.assert_called_once_with(engine)
    monitoring.set_runtime_engine.assert_called_once_with(engine)

    expected = config_mode.strip().upper()
    valid = {"OFF", "MANUAL", "SEMI", "AUTO"}
    if expected not in valid:
        expected = "OFF"
    observed = engine.context.execution_mode
    before_startup = engine.startup_execution_mode
    matching = observed == expected and (reused or before_startup == expected)
    kind = "REUSED" if reused else "NEW"
    print(
        f"startup={kind} config={config_mode} runtime={observed} "
        f"at_startup={before_startup or 'NOT_STARTED'} "
        f"result={'OK' if matching else 'DRIFT'}"
    )
    return matching


def check_apply(before: str, selected: str, *, save_ok: bool = True) -> bool:
    """Перевірити Apply, оновлення StatusBar та стан shared RuntimeEngine."""
    config = FakeConfig(before)
    engine = FakeEngine(before, "RUNNING")
    session = SimpleNamespace(
        CURRENT_CONFIG=config,
        CURRENT_RUNTIME_ENGINE=engine,
    )
    status_method = isolate_method(
        MAIN_FILE,
        "MainAppWindow",
        "_statusbar_orders_text",
        {"session_state": session},
    )
    notify_method = isolate_method(
        SETTINGS_FILE,
        "SettingsPageTrading",
        "_notify_main_window",
        {"logger": Mock()},
    )
    apply_method = isolate_method(
        SETTINGS_FILE,
        "SettingsPageTrading",
        "_apply_changes",
        {"logger": Mock(), "session_state": session},
    )

    main = SimpleNamespace(
        _lang_mgr=SimpleNamespace(tr=lambda _key, fallback: fallback),
        status_text="",
    )

    def update_statusbar() -> None:
        main.status_text = status_method(main)[0]

    main.update_statusbar = update_statusbar
    dialog = SimpleNamespace(parent=lambda: main)
    settings = SimpleNamespace(
        _snapshot={},
        current_values=lambda: {
            "broker": "CTRADER",
            "account_mode": "DEMO",
            "execution_mode": selected,
        },
        window=lambda: dialog,
    )
    save_attempts = 0

    def fake_save(values: dict[str, str]) -> bool:
        nonlocal save_attempts
        save_attempts += 1
        if save_ok:
            config.data["engine"].update(values)
        return save_ok

    settings._save_to_conf = fake_save
    settings._notify_main_window = lambda: notify_method(settings)
    settings._show_warning = lambda _message: None
    settings._set_combo_by_data = lambda *_args: None
    settings._lang_mgr = getattr(main, "_lang_mgr")
    settings.ui = SimpleNamespace(comboAccountMode=object())
    settings._live_allowed = lambda: False

    result = apply_method(settings)
    assert save_attempts == 1
    assert result == save_ok

    expected = selected if save_ok else before
    config_mode = config.data["engine"]["execution_mode"]
    runtime_mode = engine.context.execution_mode
    if not save_ok:
        matching = config_mode == before and runtime_mode == before
        print(
            f"apply=SAVE_FAILED selected={selected} config={config_mode} "
            f"runtime={runtime_mode} result={'OK' if matching else 'DRIFT'}"
        )
        return matching

    matching = (
        config_mode == expected
        and runtime_mode == expected
        and main.status_text == f"Orders: {expected}"
    )
    print(
        f"apply={before}_TO_{selected} config={config_mode} "
        f"runtime={runtime_mode} status={main.status_text!r} "
        f"result={'OK' if matching else 'DRIFT'}"
    )
    return matching


def test_execution_mode_config_runtime_sync() -> None:
    """GREEN лише тоді, коли startup і Apply синхронізують один runtime."""
    print("T116-12 TEST_ONLY | config/runtime execution-mode sync contract")
    checks = [
        check_startup("AUTO", None),
        check_startup("MANUAL", None),
        check_startup("OFF", "AUTO"),
        check_apply("AUTO", "OFF"),
        check_apply("OFF", "AUTO"),
        check_apply("SEMI", "MANUAL"),
        check_apply("OFF", "SEMI"),
        check_apply("OFF", "AUTO", save_ok=False),
    ]
    mismatches = sum(not passed for passed in checks)
    print(f"sync_cases={len(checks)}")
    print(f"sync_mismatches={mismatches}")
    print("broker_requests=0")
    print("database_writes=0")
    print("config_disk_writes=0")
    print("production_changes=0")
    print("active_lge_session=NOT_CHECKED")
    if mismatches:
        print("T116-12=RED_CONFIG_RUNTIME_SYNC_CONTRACT")
        raise AssertionError(
            f"Не виконано синхронізацію у {mismatches} з {len(checks)} сценаріїв"
        )
    print("T116-12=GREEN_CONFIG_RUNTIME_SYNC_CONTRACT")


if __name__ == "__main__":
    test_execution_mode_config_runtime_sync()
