"""T116-15 · TEST_ONLY · реальні Qt-віджети торгового режиму.

Виконує production-код SettingsPageTrading і методи MainAppWindow
на справжніх QWidget, QComboBox, QPushButton, QStatusBar і QLabel.
Не створює повне вікно LGE, RuntimeEngine або broker services.
Конфігурація та її збереження підмінені виключно оперативною пам'яттю.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QLabel,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QWidget,
)

ROOT = Path(__file__).resolve().parents[2]
MAIN_FILE = ROOT / "core" / "main_logic.py"
SETTINGS_FILE = ROOT / "core" / "settings_page_trading.py"
UI_FILE = ROOT / "ui" / "ui_settings_page_trading.py"


class FakeLanguage:
    """Стабільні fallback-переклади без мовного сховища."""

    @staticmethod
    def tr(_key: str, fallback: str) -> str:
        return fallback


class NoOpTranslator:
    """Не звертається до LANG та strings.json."""

    def __init__(self, _language: FakeLanguage) -> None:
        pass

    @staticmethod
    def apply(_widget: QWidget) -> None:
        pass


class FakeConfig:
    """Секція engine лише в оперативній пам'яті."""

    def __init__(self, mode: str) -> None:
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
    """Лише контекст і setter, без конструктора production RuntimeEngine."""

    def __init__(self) -> None:
        self.context = SimpleNamespace(execution_mode="OFF")
        self.execution_auto_session_armed = False
        self.ib_runtime_service = object()
        self.ctrader_runtime_service = object()
        self.fail_setter: str | None = None

    def set_execution_mode(self, mode: str) -> None:
        if self.fail_setter == "BEFORE_ASSIGN":
            raise RuntimeError("TEST_ONLY: setter failure before assignment")
        self.context.execution_mode = mode
        if self.fail_setter == "AFTER_ASSIGN":
            raise RuntimeError("TEST_ONLY: setter failure after assignment")


class MemoryStore:
    """Псевдодиск без фізичного запису."""

    def __init__(self, mode: str) -> None:
        self.data = FakeConfig(mode).to_dict().copy()
        self.data["engine"] = self.data["engine"].copy()
        self.attempts: list[str] = []
        self.fail_next_save = False
        self.fail_protective_off = False
        self.protective_failure_injected = False

    @property
    def mode(self) -> str:
        return str(self.data["engine"]["execution_mode"])

    def save(self, data: dict[str, Any]) -> None:
        mode = str(data["engine"]["execution_mode"])
        self.attempts.append(mode)
        if self.fail_next_save:
            self.fail_next_save = False
            raise OSError("TEST_ONLY: primary config save failed")
        if self.fail_protective_off and mode == "OFF" and self.mode == "AUTO":
            self.protective_failure_injected = True
            raise OSError("TEST_ONLY: protective OFF save failed")
        self.data = copy.deepcopy(data)


def extract_production_node(path: Path, class_name: str, method: str | None):
    """Повернути реальний AST-вузол без імпорту побічних залежностей LGE."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    if method is None:
        return cls
    return next(
        node
        for node in cls.body
        if isinstance(node, ast.FunctionDef) and node.name == method
    )


def load_production_node(
    path: Path,
    class_name: str,
    method: str | None,
    namespace: dict[str, Any],
) -> Any:
    """Виконати production AST; жодних змін вихідного коду."""
    node = copy.deepcopy(extract_production_node(path, class_name, method))
    if isinstance(node, ast.FunctionDef):
        node.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    env = namespace.copy()
    exec(compile(module, str(path), "exec"), env)
    return env[method or class_name]


def load_generated_ui():
    """Завантажити штатну Qt Designer форму без імпорту інших вікон."""
    spec = importlib.util.spec_from_file_location("t116_15_qt_form", UI_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Ui_SettingsPageTrading


STATE = ModuleType("core.session_state")
STATE.CURRENT_CONFIG = None
STATE.CURRENT_PASSWORD = None
STATE.CURRENT_RUNTIME_ENGINE = None

MAIN_ENV = {
    "session_state": STATE,
    "RuntimeEngine": FakeEngine,
    "logger": Mock(),
    "get_trial_days_left": lambda _lic: None,
}
STARTUP = load_production_node(
    MAIN_FILE, "MainAppWindow", "_init_runtime_engine", MAIN_ENV
)
STATUS_TEXT = load_production_node(
    MAIN_FILE, "MainAppWindow", "_statusbar_orders_text", MAIN_ENV
)
STATUS_UPDATE = load_production_node(
    MAIN_FILE, "MainAppWindow", "_update_statusbar", MAIN_ENV
)


class QtMainHarness(QMainWindow):
    """Справжній QMainWindow/QStatusBar, але без запуску всього LGE."""

    def __init__(self) -> None:
        super().__init__()
        self._lang_mgr = FakeLanguage()
        self.ui = SimpleNamespace(statusBarMain=self.statusBar())
        self.page_orders = SimpleNamespace(set_runtime_engine=lambda _engine: None)
        self.page_monitoring = SimpleNamespace(set_runtime_engine=lambda _engine: None)
        self._sb_app = QLabel(self)
        self._sb_lic = QLabel(self)
        self._sb_full = QLabel(self)
        self._sb_orders = QLabel(self)
        self.statusBar().addPermanentWidget(self._sb_orders)

    def start_runtime(self) -> None:
        STARTUP(self)
        self.update_statusbar()

    def _statusbar_orders_text(self) -> tuple[str, str]:
        return STATUS_TEXT(self)

    @staticmethod
    def _statusbar_license_segments(_lic: dict) -> tuple[str, str, str]:
        return "NO_LICENSE", "Full: ?", "?"

    @staticmethod
    def _update_brokers_statusbar() -> None:
        pass

    @staticmethod
    def _apply_statusbar_colors(**_kwargs: Any) -> None:
        pass

    @staticmethod
    def _handle_trial_warning_if_needed(_lic: dict) -> None:
        pass

    def update_statusbar(self) -> None:
        STATUS_UPDATE(self)

    def orders_text(self) -> str:
        return self._sb_orders.text()


class QtHarness:
    """Одна ізольована сесія з production-методами на Qt-віджетах."""

    def __init__(self, mode: str, startup_setter_failure: str | None = None) -> None:
        self.config = FakeConfig(mode)
        self.store = MemoryStore(mode)
        STATE.CURRENT_CONFIG = self.config
        STATE.CURRENT_PASSWORD = "TEST_ONLY_DUMMY_PASSWORD"
        if startup_setter_failure:
            old_engine = FakeEngine()
            old_engine.fail_setter = startup_setter_failure
            STATE.CURRENT_RUNTIME_ENGINE = old_engine
        else:
            STATE.CURRENT_RUNTIME_ENGINE = None
        self.main = QtMainHarness()
        self.main.start_runtime()
        self.session_engine = STATE.CURRENT_RUNTIME_ENGINE
        self.dialog = QDialog(self.main)
        with patch.dict(sys.modules, fake_core_modules(self.store)):
            self.settings = SafeSettingsPage(FakeLanguage(), self.dialog)

    @property
    def engine(self) -> FakeEngine:
        assert isinstance(self.session_engine, FakeEngine)
        return self.session_engine

    def activate(self) -> None:
        """Повернути власний fake session_state перед Qt callback."""
        STATE.CURRENT_CONFIG = self.config
        STATE.CURRENT_PASSWORD = "TEST_ONLY_DUMMY_PASSWORD"
        STATE.CURRENT_RUNTIME_ENGINE = self.session_engine

    def select_mode(self, mode: str) -> None:
        combo = self.settings.ui.comboExecutionMode
        idx = combo.findData(mode)
        assert idx >= 0, f"Невідомий execution_mode: {mode}"
        combo.setCurrentIndex(idx)
        QApplication.processEvents()

    def apply(self) -> None:
        self.activate()
        self.settings.ui.btnApply.click()
        QApplication.processEvents()

    def observed(self) -> tuple[str, str, str, str, bool]:
        self.activate()
        self.main.update_statusbar()
        return (
            self.settings.ui.comboExecutionMode.currentData(),
            self.main.orders_text(),
            self.engine.context.execution_mode,
            self.store.mode,
            self.settings.ui.btnApply.isEnabled(),
        )


def fake_core_modules(store: MemoryStore) -> dict[str, ModuleType]:
    """Перехопити ConfigManager.save на рівні імпортів production-коду."""
    core = ModuleType("core")
    core.__path__ = []
    core.session_state = STATE
    paths = ModuleType("core.app_paths")
    paths.ROOT_CONF_PATH = "TEST_ONLY_UNUSED_CONFIG_PATH"
    manager = ModuleType("core.config_manager")

    class MemoryConfigManager:
        def __init__(self, _path: str) -> None:
            pass

        @staticmethod
        def save(data: dict[str, Any], password: str) -> None:
            assert password == "TEST_ONLY_DUMMY_PASSWORD"
            store.save(data)

    manager.ConfigManager = MemoryConfigManager
    return {
        "core": core,
        "core.session_state": STATE,
        "core.app_paths": paths,
        "core.config_manager": manager,
    }


SETTINGS_ENV = {
    "QWidget": QWidget,
    "LangManager": FakeLanguage,
    "UITranslator": NoOpTranslator,
    "Ui_SettingsPageTrading": load_generated_ui(),
    "DEFAULT_ENGINE": {
        "broker": "OFF",
        "account_mode": "OFF",
        "execution_mode": "OFF",
    },
    "logger": Mock(),
    "session_state": STATE,
    "Any": Any,
}
SettingsPageProduction = load_production_node(
    SETTINGS_FILE, "SettingsPageTrading", None, SETTINGS_ENV
)


class SafeSettingsPage(SettingsPageProduction):
    """Штатний QWidget; модальне попередження записується в пам'ять."""

    def __init__(self, lang: FakeLanguage, parent: QWidget) -> None:
        super().__init__(lang, parent)
        self.warnings: list[str] = []

    def _show_warning(self, message: str) -> None:
        self.warnings.append(message)


def report_case(name: str, fixture: QtHarness, expected: tuple) -> bool:
    """Порівняти дані ComboBox, StatusBar, Engine, storage та Apply."""
    observed = fixture.observed()
    matching = observed == expected
    print(
        f"case={name} combo={observed[0]} status={observed[1]!r} "
        f"runtime={observed[2]} persisted={observed[3]} "
        f"apply_enabled={observed[4]} "
        f"expected_combo={expected[0]} "
        f"result={'OK' if matching else 'DRIFT'}"
    )
    return matching


def test_t116_15_actual_qt_execution_mode() -> None:
    """Перевірити інтеграцію production-методів із реальними Qt-віджетами."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    assert app is not None

    print("T116-15 TEST_ONLY | actual PySide6 widgets, isolated runtime")
    checks: list[bool] = []
    cases: list[QtHarness] = []
    total_saves = 0

    with (
        patch(
            "socket.socket.connect",
            side_effect=AssertionError("network forbidden"),
        ),
        patch(
            "sqlite3.connect",
            side_effect=AssertionError("database forbidden"),
        ),
    ):
        cold = QtHarness("AUTO")
        cases.append(cold)
        checks.append(
            report_case(
                "COLD_SAVED_AUTO",
                cold,
                ("OFF", "Orders: OFF", "OFF", "AUTO", False),
            )
        )
        checks.append(
            isinstance(cold.settings.ui.comboExecutionMode, QComboBox)
            and isinstance(cold.settings.ui.btnApply, QPushButton)
            and isinstance(cold.main.statusBar(), QStatusBar)
            and isinstance(cold.main.statusBar().findChild(QLabel), QLabel)
        )
        print("case=REAL_QT_WIDGET_TYPES " f"result={'OK' if checks[-1] else 'DRIFT'}")

        manual = QtHarness("MANUAL")
        cases.append(manual)
        checks.append(
            report_case(
                "COLD_SAVED_MANUAL",
                manual,
                ("MANUAL", "Orders: MANUAL", "MANUAL", "MANUAL", False),
            )
        )

        standard = QtHarness("OFF")
        cases.append(standard)
        standard.select_mode("AUTO")
        checks.append(standard.settings.ui.btnApply.isEnabled())
        print(
            "case=AUTO_SELECTION_ENABLES_APPLY "
            f"result={'OK' if checks[-1] else 'DRIFT'}"
        )
        with patch.dict(sys.modules, fake_core_modules(standard.store)):
            standard.apply()
        checks.append(
            report_case(
                "EXPLICIT_OFF_TO_AUTO",
                standard,
                ("AUTO", "Orders: AUTO", "AUTO", "AUTO", False),
            )
            and standard.engine.execution_auto_session_armed is True
        )

        restarted = QtHarness(standard.store.mode)
        cases.append(restarted)
        checks.append(
            report_case(
                "COLD_AFTER_AUTHORIZED_AUTO",
                restarted,
                ("OFF", "Orders: OFF", "OFF", "AUTO", False),
            )
        )

        standard.select_mode("OFF")
        with patch.dict(sys.modules, fake_core_modules(standard.store)):
            standard.apply()
        checks.append(
            report_case(
                "EXPLICIT_AUTO_TO_OFF",
                standard,
                ("OFF", "Orders: OFF", "OFF", "OFF", False),
            )
            and standard.engine.execution_auto_session_armed is False
        )

        startup_failed = QtHarness("MANUAL", startup_setter_failure="AFTER_ASSIGN")
        cases.append(startup_failed)
        checks.append(
            report_case(
                "STARTUP_SETTER_FAILED",
                startup_failed,
                ("OFF", "Orders: OFF", "OFF", "MANUAL", False),
            )
        )

        primary = QtHarness("OFF")
        cases.append(primary)
        primary.store.fail_next_save = True
        primary.select_mode("AUTO")
        with patch.dict(sys.modules, fake_core_modules(primary.store)):
            primary.apply()
        checks.append(
            report_case(
                "PRIMARY_SAVE_FAILED",
                primary,
                ("AUTO", "Orders: OFF", "OFF", "OFF", True),
            )
            and bool(primary.settings.warnings)
        )

        setter = QtHarness("OFF")
        cases.append(setter)
        setter.engine.fail_setter = "AFTER_ASSIGN"
        setter.select_mode("AUTO")
        with patch.dict(sys.modules, fake_core_modules(setter.store)):
            setter.apply()
        checks.append(
            report_case(
                "SETTER_FAILED_OFF_SAVED",
                setter,
                ("OFF", "Orders: OFF", "OFF", "OFF", False),
            )
            and bool(setter.settings.warnings)
        )

        protective = QtHarness("OFF")
        cases.append(protective)
        protective.engine.fail_setter = "BEFORE_ASSIGN"
        protective.store.fail_protective_off = True
        protective.select_mode("AUTO")
        with patch.dict(sys.modules, fake_core_modules(protective.store)):
            protective.apply()
        checks.append(
            report_case(
                "PROTECTIVE_OFF_WRITE_FAILED",
                protective,
                ("OFF", "Orders: OFF", "OFF", "AUTO", False),
            )
            and protective.store.protective_failure_injected
            and bool(protective.settings.warnings)
            and protective.engine.execution_auto_session_armed is False
        )

        recovered = QtHarness(protective.store.mode)
        cases.append(recovered)
        checks.append(
            report_case(
                "COLD_AFTER_PROTECTIVE_WRITE_FAILURE",
                recovered,
                ("OFF", "Orders: OFF", "OFF", "AUTO", False),
            )
        )

        total_saves = sum(len(case.store.attempts) for case in cases)

    mismatches = sum(not passed for passed in checks)
    print(f"qt_cases={len(checks)}")
    print(f"qt_mismatches={mismatches}")
    print(f"intercepted_config_save_attempts={total_saves}")
    print("actual_qt_widgets=TESTED")
    print("full_lge_main_window=NOT_STARTED")
    print("broker_requests=0")
    print("database_writes=0")
    print("real_config_disk_writes=0")
    print("production_changes=0")
    if mismatches:
        print("T116-15=RED_ACTUAL_QT_EXECUTION_MODE_CONTRACT")
        raise AssertionError(
            f"Actual Qt execution-mode contract: {mismatches} із {len(checks)}"
        )
    print("T116-15=GREEN_ACTUAL_QT_EXECUTION_MODE_CONTRACT")


if __name__ == "__main__":
    test_t116_15_actual_qt_execution_mode()
