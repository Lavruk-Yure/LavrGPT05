"""T116-26 TEST_ONLY — реальний таймер і дочірній процес без SDK/TCP."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from threading import Event

import pytest

from tests.roadmap116.t116_26_process_watchdog import (
    CAPTURE_DEADLINE_SECONDS,
    SUPERVISOR_TIMEOUT_SECONDS,
    CaptureDeadline,
    supervise_process,
)

WATCHDOG_SOURCE = Path(__file__).with_name("t116_26_process_watchdog.py")


def test_t116_26_standalone_process_watchdog() -> None:
    """Перевірити безподієвий дедлайн та примусове завершення процесу."""
    assert CAPTURE_DEADLINE_SECONDS == 60.0
    assert SUPERVISOR_TIMEOUT_SECONDS == 75.0
    assert CAPTURE_DEADLINE_SECONDS < SUPERVISOR_TIMEOUT_SECONDS

    source_tree = ast.parse(WATCHDOG_SOURCE.read_text(encoding="utf-8"))
    imports = [
        node.module or ""
        for node in ast.walk(source_tree)
        if isinstance(node, ast.ImportFrom)
    ]
    imports.extend(
        alias.name
        for node in ast.walk(source_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    forbidden = (
        "LGE", "core", "engine", "ibapi", "ctrader_open_api",
        "PySide6", "socket", "requests", "twisted",
    )
    assert not any(
        imported == prefix or imported.startswith(prefix + ".")
        for imported in imports
        for prefix in forbidden
    )

    # Справжній таймер має спрацювати, навіть коли немає жодної SpotEvent.
    stop_received = Event()
    callbacks: list[str] = []

    def request_stop() -> None:
        callbacks.append("STOP")
        stop_received.set()

    with CaptureDeadline(request_stop, seconds=0.05) as deadline:
        assert stop_received.wait(timeout=3.0)
        assert deadline.expired.is_set()
    assert callbacks == ["STOP"]

    # Штатне завершення раніше дедлайну не повинно викликати callback.
    cancelled = Event()
    with CaptureDeadline(cancelled.set, seconds=0.4):
        pass
    assert not cancelled.wait(timeout=0.5)

    # Supervisor працює з реальною ОС, але лише з безпечним Python-child.
    success = supervise_process(
        [sys.executable, "-c", "print('TEST_ONLY_OK')"],
        hard_timeout_seconds=5.0,
    )
    assert success.returncode == 0
    assert success.hard_timeout is False
    assert success.reaped is True
    assert success.stdout.strip() == "TEST_ONLY_OK"

    error = supervise_process(
        [sys.executable, "-c", "raise RuntimeError('TEST_ONLY_ERROR')"],
        hard_timeout_seconds=5.0,
    )
    assert error.returncode != 0
    assert error.hard_timeout is False
    assert error.reaped is True
    assert "TEST_ONLY_ERROR" in error.stderr

    # Повністю завислий child не викликає жодних подій; supervisor його вбиває.
    hung = supervise_process(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        hard_timeout_seconds=0.6,
    )
    assert hung.returncode == 124
    assert hung.hard_timeout is True
    assert hung.reaped is True

    with pytest.raises(ValueError):
        CaptureDeadline(lambda: None, seconds=0.0)
    with pytest.raises(ValueError):
        supervise_process([], hard_timeout_seconds=0.1)
    with pytest.raises(ValueError):
        supervise_process([sys.executable], hard_timeout_seconds=0.0)

    print("T116-26 TEST_ONLY | standalone process watchdog")
    print("capture_deadline_seconds=60")
    print("supervisor_timeout_seconds=75")
    print("no_spot_events_soft_deadline=FIRED_REAL_TIMER")
    print("graceful_exit_cancels_deadline=VERIFIED")
    print("healthy_child_exit=VERIFIED")
    print("failed_child_exit=PROPAGATED")
    print("unresponsive_child=KILLED_AND_REAPED")
    print("sdk_client_created=NO")
    print("real_broker_requests=0")
    print("real_config_disk_writes=0")
    print("production_changes=0")
    print("live_launch_authorized=NO")
    print("T116-26=GREEN_OFFLINE_STANDALONE_PROCESS_WATCHDOG")
