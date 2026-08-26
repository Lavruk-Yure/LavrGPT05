# ctrader_reactor_manager.py
"""
Process-level Twisted reactor manager для cTrader runtime.

Важливо:
- Twisted reactor глобальний на process.
- Adapter-и можна створювати/retire/reconnect багато разів.
- Reactor запускається один раз за життя LGE process.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from twisted.internet import reactor  # noqa
from twisted.internet.error import ReactorNotRunning  # noqa

reactor_call_from_thread = getattr(reactor, "callFromThread")
reactor_run = getattr(reactor, "run")
reactor_stop = getattr(reactor, "stop")

logger = logging.getLogger(__name__)

_reactor_lock = threading.Lock()
_reactor_thread: threading.Thread | None = None
_reactor_started = False


def ensure_ctrader_reactor_started() -> None:
    """
    Запустити Twisted reactor один раз на process.
    """

    global _reactor_started
    global _reactor_thread

    with _reactor_lock:
        if _reactor_thread is not None and _reactor_thread.is_alive():
            return

        if _reactor_started:
            logger.debug("cTrader reactor already started for this process.")
            return

        _reactor_thread = threading.Thread(
            target=_run_reactor,
            name="LGE-cTrader-reactor",
            daemon=True,
        )
        _reactor_started = True
        _reactor_thread.start()


def call_in_ctrader_reactor(
    func: Callable[..., Any], *args: Any, **kwargs: Any
) -> None:
    """
    Виконати callable у Twisted reactor thread.
    """

    ensure_ctrader_reactor_started()
    reactor_call_from_thread(func, *args, **kwargs)


def stop_ctrader_reactor_for_diagnostics() -> None:
    """
    Diagnostic-only stop.

    У production runtime це не викликати після disconnect/reconnect.
    """

    try:
        reactor_call_from_thread(reactor_stop)
    except ReactorNotRunning:
        return


def _run_reactor() -> None:
    """
    Worker для глобального Twisted reactor.
    """

    try:
        reactor_run(installSignalHandlers=False)
    except RuntimeError as exc:
        logger.warning("Twisted reactor run skipped: %s", exc)
