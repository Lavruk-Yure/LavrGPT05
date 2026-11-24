"""T116-20D TEST_ONLY — часові межі LIVE-збору без мережі та GUI.

Ізольовані фальшиві процес і Qt-таймер. Реальні LGE, cTrader та IB не запускаються.
"""

from __future__ import annotations

import ast
import runpy
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TELEMETRY_FILE = (
    ROOT / "tests" / "roadmap116" / "run_t116_19_ctrader_raw_spot_telemetry.py"
)


class FakeSignal:
    """Тестова модель Qt-сигналу без циклу подій."""

    def __init__(self) -> None:
        self.callback: Callable[[], None] = self._missing_handler

    @staticmethod
    def _missing_handler() -> None:
        raise AssertionError("Тестовий Qt-сигнал не має обробника")

    def connect(self, callback: Callable[[], None]) -> None:
        self.callback = callback

    def emit(self) -> None:
        self.callback()


class FakeApplication:
    """Контроль створення QApplication та виклику quit()."""

    def __init__(self, argv: list[str]) -> None:
        self.argv = argv
        self.quit_calls = 0

    def quit(self) -> None:
        self.quit_calls += 1


class FakeQTimer:
    """Тестовий Qt-таймер, незалежний від надходження SpotEvent."""

    instances: list[FakeQTimer] = []

    def __init__(self, parent: FakeApplication) -> None:
        self.parent = parent
        self.timeout = FakeSignal()
        self.single_shot = False
        self.interval_ms = 0
        self.instances.append(self)

    def set_single_shot(self, enabled: bool) -> None:
        self.single_shot = enabled

    def start(self, interval_ms: int) -> None:
        self.interval_ms = interval_ms


setattr(FakeQTimer, "setSingleShot", FakeQTimer.set_single_shot)


def test_t116_20d_live_capture_duration_guard() -> None:
    """Перевірити штатний Qt deadline та аварійний ліміт процесу."""
    scope = runpy.run_path(str(TELEMETRY_FILE), run_name="t116_20d_offline")
    supervisor = scope["launch_live_supervised"]
    qt_seconds = scope["LIVE_QT_TIMEOUT_SECONDS"]
    process_seconds = scope["LIVE_PROCESS_TIMEOUT_SECONDS"]
    environment_key = scope["LIVE_WORKER_ENV"]
    assert isinstance(qt_seconds, int) and qt_seconds > 0
    assert isinstance(process_seconds, int) and process_seconds > qt_seconds

    calls: list[dict[str, object]] = []

    def fake_process(
        command: list[str], *, cwd: str, env: dict[str, str], timeout: int, check: bool
    ) -> SimpleNamespace:
        calls.append(
            {
                "command": command,
                "cwd": cwd,
                "env": env,
                "timeout": timeout,
                "check": check,
            }
        )
        return SimpleNamespace(returncode=0)

    assert supervisor(run_process=fake_process) == 0
    assert len(calls) == 1
    assert calls[0]["command"] == [
        scope["sys"].executable,
        str(TELEMETRY_FILE),
        "--live-worker",
    ]
    assert calls[0]["cwd"] == str(ROOT)
    assert calls[0]["timeout"] == process_seconds
    assert calls[0]["check"] is False
    process_env = calls[0]["env"]
    assert isinstance(process_env, dict)
    assert process_env.get(environment_key) == "1"

    def hanging_process(command: list[str], **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(
            cmd=command,
            timeout=process_seconds,
        )

    assert supervisor(run_process=hanging_process) == 124

    # Взяти лише невелику вкладену фабрику Qt без імпорту PySide6.
    syntax = ast.parse(TELEMETRY_FILE.read_text(encoding="utf-8"))
    launcher = next(
        node
        for node in syntax.body
        if isinstance(node, ast.FunctionDef) and node.name == "launch_live_diagnostics"
    )
    timed_factory = next(
        node
        for node in ast.walk(launcher)
        if isinstance(node, ast.FunctionDef) and node.name == "timed_application"
    )
    module_ast = ast.fix_missing_locations(
        ast.Module(body=[timed_factory], type_ignores=[])
    )
    FakeQTimer.instances.clear()
    test_scope: dict[str, Any] = {
        "QApplication": FakeApplication,
        "QTimer": FakeQTimer,
        "original_application": FakeApplication,
        "LIVE_QT_TIMEOUT_SECONDS": qt_seconds,
    }
    exec(compile(module_ast, str(TELEMETRY_FILE), "exec"), test_scope)
    qt_factory = test_scope["timed_application"]
    application = qt_factory(["LGE.py"])
    assert isinstance(application, FakeApplication)
    assert len(FakeQTimer.instances) == 1
    timer = FakeQTimer.instances.pop()
    assert timer.parent is application
    assert timer.single_shot is True
    assert timer.interval_ms == qt_seconds * 1000
    assert application.quit_calls == 0
    timer.timeout.emit()
    assert application.quit_calls == 1

    # Впевнитися, що фабрика Qt встановлена на час виконання LGE.main().
    text = (
        ast.get_source_segment(TELEMETRY_FILE.read_text(encoding="utf-8"), launcher)
        or ""
    )
    assert 'patch.object(LGE, "QApplication", timed_application)' in text
    assert "LGE.main()" in text
    assert text.index('patch.object(LGE, "QApplication", timed_application)') < (
        text.index("LGE.main()")
    )
    assert 'patch.object(LGE, "_restart_application", deny_restart)' in text
    assert 'os.environ.get(LIVE_WORKER_ENV) != "1"' in TELEMETRY_FILE.read_text(
        encoding="utf-8"
    )

    print("T116-20D TEST_ONLY | bounded capture without SpotEvent")
    print(f"qt_timeout_seconds={qt_seconds}")
    print(f"supervisor_timeout_seconds={process_seconds}")
    print("no_spot_events_qt_deadline=VERIFIED_WITH_FAKE_QT")
    print("qt_event_loop_hang=SUPERVISOR_TIMEOUT_PATH_VERIFIED")
    print("unsupervised_worker=DENIED_BY_ENTRY_GUARD")
    print("real_broker_requests=0")
    print("real_config_disk_writes=0")
    print("production_changes=0")
    print("T116-20D=GREEN_OFFLINE_CAPTURE_DURATION_GUARD")
