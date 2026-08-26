"""Ініціалізаційний модуль пакету monitoring."""

from __future__ import annotations

# Імпортуємо класи без падіння (модулі можуть бути в розробці)
try:
    from .monitor_live import *  # noqa
    from .monitor_live_compact import *  # noqa
    from .monitor_live_compact_realtime import *  # noqa
    from .monitor_live_graph import *  # noqa
    from .monitor_live_graph_matplotlib import *  # noqa
    from .monitor_live_graph_stats import *  # noqa
    from .monitor_live_graph_stats_compact import *  # noqa
    from .monitor_live_graph_stats_orders import *  # noqa
    from .monitor_live_realtime import *  # noqa
    from .monitor_live_stats import *  # noqa
except ImportError:
    pass

__all__ = [
    "monitor_live",
    "monitor_live_compact",
    "monitor_live_compact_realtime",
    "monitor_live_graph",
    "monitor_live_graph_matplotlib",
    "monitor_live_graph_stats",
    "monitor_live_graph_stats_compact",
    "monitor_live_graph_stats_orders",
    "monitor_live_realtime",
    "monitor_live_stats",
]
