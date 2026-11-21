"""T116-14 · TEST_ONLY · контракт стійкого fail-closed після помилок Apply.

AST-виконання фактичних GUI-методів із підставною конфігурацією та
in-memory сховищем. Порівнює конфігурацію в пам'яті, умовно збережену
конфігурацію, StatusBar, RuntimeEngine та Workspace execution boundary.

Не відкриває LGE.conf, не створює RuntimeEngine, Qt, БД чи broker connection.
Очікується fail-first RED до окремо погодженого production-виправлення.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from run_t116_12_execution_mode_sync_contract import (  # noqa: E402
    FakeConfig,
    FakeEngine,
    SETTINGS_FILE,
    isolate_method,
)
from run_t116_13_gui_runtime_integration_contract import (  # noqa: E402
    GUIRuntimeHarness,
)


class MutableConfig(FakeConfig):
    """Імітація ConfigCollection: set() змінює саме in-memory dict."""

    def set(self, section: str, key: str, value: str) -> None:
        self.data.setdefault(section, {})[key] = value


class FakePersistentStore:
    """Модель збереженої конфігурації, без жодної операції з диском."""

    def __init__(self, mode: str) -> None:
        self.snapshot = copy.deepcopy(MutableConfig(mode).to_dict())
        self.attempts: list[str] = []
        self.fail_next_save = False
        self.fail_protective_off = False
        self.injected_protective_failure = False

    @property
    def mode(self) -> str:
        return str(self.snapshot["engine"]["execution_mode"])

    def save(self, data: dict[str, Any]) -> None:
        mode = str(data.get("engine", {}).get("execution_mode", ""))
        self.attempts.append(mode)
        if self.fail_next_save:
            self.fail_next_save = False
            raise OSError("TEST_ONLY: primary config save failed")
        if self.fail_protective_off and mode == "OFF" and self.mode == "AUTO":
            self.injected_protective_failure = True
            raise OSError("TEST_ONLY: protective OFF persistence failed")
        self.snapshot = copy.deepcopy(data)


class PersistenceHarness(GUIRuntimeHarness):
    """Наскрізний тест з відокремленими memory і persisted станами."""

    def __init__(self, mode: str = "OFF") -> None:
        super().__init__(mode)
        self.config = MutableConfig(mode)
        self.session.CURRENT_CONFIG = self.config
        self.store = FakePersistentStore(mode)
        self.save_method = isolate_method(
            SETTINGS_FILE,
            "SettingsPageTrading",
            "_save_to_conf",
            {"logger": Mock()},
        )

    def _fake_modules(self) -> dict[str, ModuleType]:
        """Замінити імпорти ConfigManager лише в межах тестового Apply."""
        root = ModuleType("core")
        setattr(root, "__path__", [])
        state = ModuleType("core.session_state")
        setattr(state, "CURRENT_CONFIG", self.config)
        setattr(state, "CURRENT_PASSWORD", "TEST_ONLY_DUMMY_PASSWORD")
        setattr(root, "session_state", state)

        paths = ModuleType("core.app_paths")
        setattr(paths, "ROOT_CONF_PATH", Path("TEST_ONLY_UNUSED_CONF_PATH"))

        manager_module = ModuleType("core.config_manager")
        store = self.store

        class FakeConfigManager:
            """Не використовує шлях або файлову систему."""

            def __init__(self, _path: Path) -> None:
                pass

            @staticmethod
            def save(data: dict[str, Any], password: str) -> None:
                assert password == "TEST_ONLY_DUMMY_PASSWORD"
                store.save(data)

        setattr(manager_module, "ConfigManager", FakeConfigManager)
        return {
            "core": root,
            "core.session_state": state,
            "core.app_paths": paths,
            "core.config_manager": manager_module,
        }

    def apply_mode(
        self,
        selected: str,
        *,
        setter_failure: str | None = None,
        fail_primary_save: bool = False,
        fail_protective_off: bool = False,
    ) -> bool:
        """Виконати production Apply і production _save_to_conf через AST."""
        self.store.fail_next_save = fail_primary_save
        self.store.fail_protective_off = fail_protective_off
        previous_setter = self.engine.set_execution_mode
        if setter_failure:

            def broken_setter(mode: str) -> None:
                if setter_failure == "AFTER_ASSIGN":
                    self.engine.context.execution_mode = mode
                raise RuntimeError("TEST_ONLY: runtime event write failed")

            setattr(self.engine, "set_execution_mode", broken_setter)

        window = SimpleNamespace(parent=lambda: self.main)
        settings = SimpleNamespace(
            _snapshot={},
            current_values=lambda: {
                "broker": "CTRADER",
                "account_mode": "DEMO",
                "execution_mode": selected,
            },
            _show_warning=self.warnings.append,
            _set_combo_by_data=lambda *_args: None,
            _lang_mgr=getattr(self.main, "_lang_mgr"),
            _live_allowed=lambda: False,
            ui=SimpleNamespace(comboAccountMode=object()),
            window=lambda: window,
        )
        settings._save_to_conf = lambda values: self.save_method(settings, values)
        settings._notify_main_window = lambda: self.notify(settings)

        try:
            with patch.dict(sys.modules, self._fake_modules()):
                return bool(self.apply(settings))
        finally:
            setattr(self.engine, "set_execution_mode", previous_setter)

    def observed_status(self) -> tuple[str, str]:
        """Повернути StatusBar після явного read-only refresh."""
        self.refresh_status()
        text = self.main.status_text
        return text, text.removeprefix("Orders: ")

    def snapshot(self) -> tuple[str, str, str, str, str]:
        """Спостережувані стани без повторної ініціалізації."""
        _text, gui_mode = self.observed_status()
        return (
            self.config.data["engine"]["execution_mode"],
            self.store.mode,
            gui_mode,
            self.engine.context.execution_mode,
            self.workspace_attempt(),
        )

    def reuse_mode(self) -> str:
        """Повторна ініціалізація з тим самим in-memory конфігом."""
        self.start_or_reuse()
        return self.engine.context.execution_mode

    def cold_restart_mode(self) -> str:
        """Імітація нового процесу з останньої збереженої конфігурації."""
        self.config = MutableConfig(self.store.mode)
        self.session.CURRENT_CONFIG = self.config
        self.session.CURRENT_RUNTIME_ENGINE = FakeEngine("OFF", "RUNNING")
        self.start_or_reuse()
        return self.engine.context.execution_mode


def check_case(
    name: str,
    *,
    initial: str = "OFF",
    requested: str = "AUTO",
    setter_failure: str | None = None,
    fail_primary_save: bool = False,
    fail_protective_off: bool = False,
    expected_apply: bool,
    expected_safe_mode: str,
) -> bool:
    """Вимагати узгодженого стану після Apply та повторної ініціалізації."""
    harness = PersistenceHarness(initial)
    harness.start_or_reuse()
    outcome = harness.apply_mode(
        requested,
        setter_failure=setter_failure,
        fail_primary_save=fail_primary_save,
        fail_protective_off=fail_protective_off,
    )
    memory, disk, gui, runtime, boundary = harness.snapshot()
    reuse = harness.reuse_mode()
    cold = harness.cold_restart_mode()
    expected_boundary = (
        "INTERCEPTED" if expected_safe_mode == "AUTO" else "BLOCKED"
    )
    matching = (
        outcome is expected_apply
        and memory == disk == gui == runtime == expected_safe_mode
        and reuse == cold == expected_safe_mode
        and boundary == expected_boundary
    )
    print(
        f"case={name} apply={'OK' if outcome else 'FAILED'} "
        f"memory={memory} disk={disk} gui={gui} runtime={runtime} "
        f"boundary={boundary} reuse={reuse} cold={cold} "
        f"writes={','.join(harness.store.attempts)} "
        f"result={'OK' if matching else 'DRIFT'}"
    )
    if fail_protective_off:
        print(
            "protective_off_write_failure_injected="
            f"{'YES' if harness.store.injected_protective_failure else 'NO'}"
        )
    return matching


def test_t116_14_persistent_fail_closed() -> None:
    """Fail-first: навіть збій відновлення не повинен повертати AUTO."""
    print("T116-14 TEST_ONLY | persistent fail-closed recovery")
    with (
        patch("socket.socket.connect", side_effect=AssertionError("network forbidden")),
        patch("sqlite3.connect", side_effect=AssertionError("database forbidden")),
    ):
        checks = [
            check_case(
                "NORMAL_OFF_TO_AUTO", expected_apply=True,
                expected_safe_mode="AUTO",
            ),
            check_case(
                "NORMAL_AUTO_TO_OFF", initial="AUTO", requested="OFF",
                expected_apply=True, expected_safe_mode="OFF",
            ),
            check_case(
                "SETTER_FAIL_BEFORE_ASSIGN", setter_failure="BEFORE_ASSIGN",
                expected_apply=False, expected_safe_mode="OFF",
            ),
            check_case(
                "SETTER_FAIL_AFTER_ASSIGN", setter_failure="AFTER_ASSIGN",
                expected_apply=False, expected_safe_mode="OFF",
            ),
            check_case(
                "SETTER_FAIL_OFF_SAVE_FAIL", setter_failure="AFTER_ASSIGN",
                fail_protective_off=True, expected_apply=False,
                expected_safe_mode="OFF",
            ),
            check_case(
                "PRIMARY_SAVE_FAILURE_STALE_MEMORY", fail_primary_save=True,
                expected_apply=False, expected_safe_mode="OFF",
            ),
        ]

    mismatches = sum(not item for item in checks)
    print(f"recovery_cases={len(checks)}")
    print(f"recovery_mismatches={mismatches}")
    print("broker_requests=0")
    print("database_writes=0")
    print("real_config_disk_writes=0")
    print("production_changes=0")
    print("actual_qt_widgets=NOT_TESTED")
    print("active_lge_process=NOT_STARTED")
    if mismatches:
        print("T116-14=RED_PERSISTENT_FAIL_CLOSED_CONTRACT")
        raise AssertionError(
            f"Persistent fail-closed порушено в {mismatches} "
            f"із {len(checks)} сценаріїв"
        )
    print("T116-14=GREEN_PERSISTENT_FAIL_CLOSED_CONTRACT")


if __name__ == "__main__":
    test_t116_14_persistent_fail_closed()
