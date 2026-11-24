"""T116-26 TEST_ONLY — незалежні часові межі автономного читача.

Без cTrader SDK, LGE, брокера та GUI. Це лише компоненти майбутнього
процесу діагностики, а не дозволений мережевий запуск.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from threading import Event, Timer

CAPTURE_DEADLINE_SECONDS = 60.0
SUPERVISOR_TIMEOUT_SECONDS = 75.0


@dataclass(frozen=True)
class SupervisedResult:
    """Результат завершення дочірнього процесу без мережевих припущень."""

    returncode: int
    hard_timeout: bool
    reaped: bool
    stdout: str
    stderr: str


class CaptureDeadline:
    """Викликати зупинку незалежно від надходження ринкових подій.

    Callback виконується в потоці таймера; майбутній SDK-адаптер повинен
    передати завершення у власний потік циклу подій.
    """

    def __init__(
        self,
        stop_callback: Callable[[], None],
        *,
        seconds: float = CAPTURE_DEADLINE_SECONDS,
    ) -> None:
        if seconds <= 0:
            raise ValueError("T116-26: часовий ліміт має бути додатним")
        self.expired = Event()
        self._timer = Timer(seconds, self._expire)
        self._timer.daemon = True
        self._stop_callback = stop_callback
        self._started = False

    def _expire(self) -> None:
        self.expired.set()
        self._stop_callback()

    def __enter__(self) -> CaptureDeadline:
        if self._started:
            raise RuntimeError("T116-26: повторний запуск таймера заборонено")
        self._started = True
        self._timer.start()
        return self

    def __exit__(
        self,
        _exc_type: object,
        _exc_value: object,
        _traceback: object,
    ) -> None:
        self._timer.cancel()


def supervise_process(
    command: Sequence[str],
    *,
    hard_timeout_seconds: float = SUPERVISOR_TIMEOUT_SECONDS,
) -> SupervisedResult:
    """Контролювати дочірній процес; у разі зависання вбити та дочекатися.

    Ця функція не створює мережевий клієнт і не запускається автоматично.
    Лише безпечні тестові команди мають передаватися з T116-26.
    """
    if not command or not all(isinstance(part, str) and part for part in command):
        raise ValueError("T116-26: потрібна непорожня команда")
    if hard_timeout_seconds <= 0:
        raise ValueError("T116-26: жорсткий ліміт має бути додатним")

    process = subprocess.Popen(
        list(command),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    try:
        try:
            stdout, stderr = process.communicate(timeout=hard_timeout_seconds)
            return SupervisedResult(
                returncode=process.wait(),
                hard_timeout=False,
                reaped=process.poll() is not None,
                stdout=stdout,
                stderr=stderr,
            )
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5.0)
            return SupervisedResult(
                returncode=124,
                hard_timeout=True,
                reaped=process.poll() is not None,
                stdout=stdout,
                stderr=stderr,
            )
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5.0)
