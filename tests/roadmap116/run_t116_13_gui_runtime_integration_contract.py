"""T116-13 · TEST_ONLY · наскрізна GUI/config/runtime/boundary інтеграція.

Зв'язує фактичні production-методи через AST в одному fake GUI-сеансі.
Не запускає PySide6/LGE, RuntimeEngine.__init__, ConfigManager чи broker SDK.
Не змінює LGE.conf, БД, production-файли та не надсилає ордерів.

Це НЕ перевірка живого процесу LGE або реальних GUI-віджетів.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

TEST_DIR = Path(__file__).resolve().parent
if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))

from run_t116_10_workspace_execution_guard_contract import (  # noqa: E402
    ACCOUNT_ID,
    PLAN_UID,
    TRADE_UID,
    AdapterIntercept,
    load_workspace_submission,
)
from run_t116_12_execution_mode_sync_contract import (  # noqa: E402
    MAIN_FILE,
    SETTINGS_FILE,
    FakeConfig,
    FakeEngine,
    isolate_method,
)


class GUIRuntimeHarness:
    """Одна тестова GUI-сесія та той самий shared RuntimeEngine."""

    def __init__(self, mode: str = "OFF") -> None:
        self.config = FakeConfig(mode)
        self.session = SimpleNamespace(
            CURRENT_CONFIG=self.config,
            CURRENT_RUNTIME_ENGINE=None,
        )
        self.main = SimpleNamespace(
            _lang_mgr=SimpleNamespace(tr=lambda _key, fallback: fallback),
            page_orders=Mock(),
            page_monitoring=Mock(),
            status_text="",
        )
        self.notifications = 0
        self.warnings: list[str] = []
        self.fake_adapter_calls = 0
        self.init = isolate_method(
            MAIN_FILE,
            "MainAppWindow",
            "_init_runtime_engine",
            {
                "session_state": self.session,
                "RuntimeEngine": FakeEngine,
                "RuntimeState": SimpleNamespace(OFF="OFF"),
                "logger": Mock(),
            },
        )
        self.status = isolate_method(
            MAIN_FILE,
            "MainAppWindow",
            "_statusbar_orders_text",
            {"session_state": self.session},
        )
        self.notify = isolate_method(
            SETTINGS_FILE,
            "SettingsPageTrading",
            "_notify_main_window",
            {"logger": Mock()},
        )
        self.apply = isolate_method(
            SETTINGS_FILE,
            "SettingsPageTrading",
            "_apply_changes",
            {"session_state": self.session, "logger": Mock()},
        )
        self.submit = load_workspace_submission()
        self.main.update_statusbar = self.refresh_status

    @property
    def engine(self) -> FakeEngine:
        result = self.session.CURRENT_RUNTIME_ENGINE
        assert isinstance(result, FakeEngine)
        return result

    def refresh_status(self) -> None:
        self.notifications += 1
        self.main.status_text = self.status(self.main)[0]

    def start_or_reuse(self) -> None:
        previous = self.session.CURRENT_RUNTIME_ENGINE
        self.init(self.main)
        assert isinstance(self.engine, FakeEngine)
        if previous is not None:
            assert self.engine is previous, "Не можна підміняти shared RuntimeEngine"
        self.refresh_status()
        self.main.page_orders.set_runtime_engine.assert_called_with(self.engine)
        self.main.page_monitoring.set_runtime_engine.assert_called_with(self.engine)

    def change_mode(
        self,
        selected: str,
        *,
        save_ok: bool = True,
        fail_setter: bool = False,
    ) -> bool:
        """Викликати реальний Settings Apply + notify + Main StatusBar."""
        old_setter = self.engine.set_execution_mode
        if fail_setter:

            def broken_setter(mode: str) -> None:
                # Сценарій: mode призначено, а журналювання події не вдалося.
                self.engine.context.execution_mode = mode
                raise RuntimeError("TEST_ONLY: runtime event write failed")

            setattr(self.engine, "set_execution_mode", broken_setter)

        def fake_save(values: dict[str, str]) -> bool:
            if save_ok:
                self.config.data["engine"].update(values)
            return save_ok

        dialog = SimpleNamespace(parent=lambda: self.main)
        settings = SimpleNamespace(
            _snapshot={},
            current_values=lambda: {
                "broker": "CTRADER",
                "account_mode": "DEMO",
                "execution_mode": selected,
            },
            _save_to_conf=fake_save,
            _show_warning=self.warnings.append,
            _lang_mgr=getattr(self.main, "_lang_mgr"),
            _live_allowed=lambda: False,
            window=lambda: dialog,
        )
        settings._notify_main_window = lambda: self.notify(settings)
        try:
            return bool(self.apply(settings))
        finally:
            setattr(self.engine, "set_execution_mode", old_setter)

    def workspace_attempt(self) -> str:
        """Виконати actual Workspace boundary до fake adapter, без persistence."""
        repo = Mock()
        repo.get_trade_chain.return_value = {
            "trade": {
                "source": "WORKSPACE",
                "broker": "CTRADER",
                "account_id": ACCOUNT_ID,
                "control_mode": "AUTO",
                "execution_state": "READY_FOR_SUBMISSION",
                "symbol": "EURUSD",
                "volume": 1000.0,
            },
            "order_plans": [
                {
                    "source": "WORKSPACE",
                    "order_plan_uid": PLAN_UID,
                    "side": "BUY",
                    "volume": 1000.0,
                    "stop_loss": 1.0800,
                }
            ],
            "broker_orders": [],
        }
        repo.create_broker_order.side_effect = AssertionError(
            "TEST_ONLY: database write is forbidden"
        )
        service = Mock()

        def stop_before_adapter(**payload: Any) -> None:
            assert payload["symbol_name"] == "EURUSD"
            assert payload["side"] == "BUY"
            self.fake_adapter_calls += 1
            raise AdapterIntercept("TEST_ONLY: no broker API")

        service.place_market_order.side_effect = stop_before_adapter
        engine = self.engine
        engine.repository = repo
        engine.ctrader_runtime_service = service

        def validate_binding(name: str, account: str) -> None:
            assert name == "CTRADER" and account == ACCOUNT_ID

        engine.validate_workspace_broker_binding = validate_binding

        try:
            self.submit(engine, TRADE_UID, PLAN_UID)
        except AdapterIntercept:
            observed = "INTERCEPTED"
        except (PermissionError, RuntimeError, ValueError):
            observed = "BLOCKED"
        else:
            raise AssertionError("Unexpected submission without interception")
        assert repo.create_broker_order.call_count == 0
        assert service.place_market_order.call_count == int(observed == "INTERCEPTED")
        return observed

    def report(self, case: str, expected: str) -> bool:
        runtime_mode = self.engine.context.execution_mode
        config_mode = self.config.data["engine"]["execution_mode"]
        gui_mode = self.main.status_text.removeprefix("Orders: ")
        actual = self.workspace_attempt()
        matching = runtime_mode == config_mode == gui_mode and actual == expected
        print(
            f"case={case} config={config_mode} gui={gui_mode} "
            f"runtime={runtime_mode} boundary={actual} "
            f"result={'OK' if matching else 'DRIFT'}"
        )
        return matching


def test_t116_13_gui_runtime_integration() -> None:
    """Перевірити повний ланцюг в одній in-memory GUI-сесії."""
    print("T116-13 TEST_ONLY | GUI -> config -> shared runtime -> Workspace boundary")
    with (
        patch("socket.socket.connect", side_effect=AssertionError("network forbidden")),
        patch("sqlite3.connect", side_effect=AssertionError("database forbidden")),
    ):
        harness = GUIRuntimeHarness("OFF")
        harness.start_or_reuse()
        checks = [harness.report("STARTUP_OFF", "BLOCKED")]

        assert harness.change_mode("AUTO") is True
        checks.append(harness.report("APPLY_OFF_TO_AUTO", "INTERCEPTED"))

        assert harness.change_mode("OFF") is True
        checks.append(harness.report("APPLY_AUTO_TO_OFF", "BLOCKED"))

        assert harness.change_mode("SEMI") is True
        checks.append(harness.report("APPLY_OFF_TO_SEMI", "BLOCKED"))

        assert harness.change_mode("OFF") is True
        assert harness.change_mode("AUTO", save_ok=False) is False
        checks.append(harness.report("SAVE_FAILED_KEEPS_OFF", "BLOCKED"))

        harness.config.data["engine"]["execution_mode"] = "AUTO"
        harness.start_or_reuse()
        checks.append(harness.report("REUSED_RUNTIME_RELOAD_AUTO", "INTERCEPTED"))

        assert harness.change_mode("OFF") is True
        assert harness.change_mode("AUTO", fail_setter=True) is False
        checks.append(harness.report("SETTER_FAILURE_FAIL_CLOSED", "BLOCKED"))
        assert len(harness.warnings) == 1
        # Після повторного init fake adapter перевіряє можливе відновлення AUTO.
        harness.start_or_reuse()
        checks.append(harness.report("REINIT_AFTER_SETTER_FAILURE", "BLOCKED"))

        mismatches = sum(not value for value in checks)
        print(f"integration_cases={len(checks)}")
        print(f"integration_mismatches={mismatches}")
        print(f"fake_adapter_intercepts={harness.fake_adapter_calls}")
        print("broker_requests=0")
        print("database_writes=0")
        print("config_disk_writes=0")
        print("production_changes=0")
        print("actual_qt_widgets=NOT_TESTED")
        print("actual_lge_process=NOT_STARTED")
        if mismatches:
            print("T116-13=RED_INTEGRATED_RUNTIME_MODE_DRIFT")
            raise AssertionError(
                f"GUI/config/runtime/boundary мають {mismatches} "
                f"розбіжності з {len(checks)} перевірок"
            )
        print("T116-13=GREEN_IN_MEMORY_INTEGRATION")


if __name__ == "__main__":
    test_t116_13_gui_runtime_integration()
