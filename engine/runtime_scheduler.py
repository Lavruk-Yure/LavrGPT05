# runtime_scheduler.py
"""
Канонічний runtime scheduler для LGE.

RoadMap68:
- без залежності від Qt;
- без asyncio;
- без APScheduler;
- окремий runtime thread;
- startup tasks;
- periodic tasks;
- безпечне завершення.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from engine.runtime_constants import (
    RUNTIME_SCHEDULER_STOP_WAIT_SECONDS,
    RUNTIME_SCHEDULER_THREAD_JOIN_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

SchedulerTask = Callable[[], None]


class RuntimeScheduler:
    """
    Канонічний scheduler для runtime-шару LGE.
    """

    def __init__(
        self,
        logger_: logging.Logger | None = None,
    ) -> None:
        self._logger = logger_ or logger

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        self._running = False

        self._startup_tasks: list[SchedulerTask] = []
        self._periodic_tasks: list[tuple[float, SchedulerTask]] = []

        self._last_run: dict[int, float] = {}

    @property
    def is_running(self) -> bool:
        """
        Повернути ознаку активного scheduler.
        """
        return self._running

    def add_startup_task(
        self,
        task: SchedulerTask,
    ) -> None:
        """
        Додати startup task.

        Startup task виконується один раз після запуску scheduler.
        """

        self._startup_tasks.append(task)

    def add_periodic_task(
        self,
        interval_seconds: float,
        task: SchedulerTask,
    ) -> None:
        """
        Додати periodic task.

        interval_seconds задає мінімальний інтервал між запусками task.
        """

        self._periodic_tasks.append(
            (interval_seconds, task),
        )

    def start(self) -> bool:
        """
        Запустити runtime scheduler.
        """

        if self._running:
            self._logger.info("RuntimeScheduler уже запущений.")
            return True

        self._logger.info("Запуск RuntimeScheduler...")

        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="RuntimeSchedulerThread",
        )

        self._thread.start()

        self._running = True

        self._logger.info("RuntimeScheduler запущено.")
        return True

    def stop(self) -> None:
        """
        Зупинити runtime scheduler.
        """

        if not self._running:
            return

        self._logger.info("Зупинка RuntimeScheduler...")

        self._stop_event.set()

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=RUNTIME_SCHEDULER_THREAD_JOIN_TIMEOUT_SECONDS)

            if self._thread.is_alive():
                self._logger.warning(
                    "RuntimeScheduler thread не завершився коректно.",
                )

        self._running = False

        self._logger.info("RuntimeScheduler зупинено.")

    def _run_loop(self) -> None:
        """
        Основний цикл scheduler.
        """

        self._logger.info("RuntimeScheduler loop запущено.")

        self._run_startup_tasks()

        while not self._stop_event.is_set():
            try:
                self._run_periodic_tasks()
            except Exception as exc:  # noqa: BLE001
                self._logger.exception(
                    "Помилка в RuntimeScheduler loop: %s",
                    exc,
                )

            self._stop_event.wait(timeout=RUNTIME_SCHEDULER_STOP_WAIT_SECONDS)

        self._logger.info("RuntimeScheduler loop зупинено.")

    def _run_startup_tasks(self) -> None:
        """
        Виконати startup tasks один раз.
        """

        for task in self._startup_tasks:
            self._run_task(task)

    def _run_periodic_tasks(self) -> None:
        """
        Виконати periodic tasks згідно з їхніми інтервалами.
        """

        now = time.monotonic()

        for interval_seconds, task in self._periodic_tasks:
            task_id = id(task)
            last_run = self._last_run.get(task_id, 0.0)

            if (now - last_run) < interval_seconds:
                continue

            self._run_task(task)
            self._last_run[task_id] = now

    def _run_task(
        self,
        task: SchedulerTask,
    ) -> None:
        """
        Безпечно виконати scheduler task.
        """

        task_name = getattr(task, "__name__", repr(task))

        self._logger.info(
            "RuntimeScheduler: запуск task=%s",
            task_name,
        )

        try:
            task()

        except Exception as exc:  # noqa: BLE001
            self._logger.exception(
                "RuntimeScheduler: помилка task=%s | error=%s",
                task_name,
                exc,
            )

        self._logger.info(
            "RuntimeScheduler: завершено task=%s",
            task_name,
        )
