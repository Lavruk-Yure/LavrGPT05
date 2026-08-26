# runtime_broker_health.py
"""
Runtime broker health state.

Це runtime-стан здоров'я broker connection.
Не зберігається в LGE.conf.
Використовується RuntimeService / ReconnectTask.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

HEALTH_UNKNOWN = "UNKNOWN"
HEALTH_CONNECTED = "CONNECTED"
HEALTH_DISCONNECTED = "DISCONNECTED"
HEALTH_SAFE_DISCONNECTED = "SAFE_DISCONNECTED"
HEALTH_RECONNECTING = "RECONNECTING"
HEALTH_ERROR = "ERROR"


def utc_now_text() -> str:
    """
    Повернути поточний UTC-час у канонічному runtime ISO-форматі.
    """
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass
class RuntimeBrokerHealth:
    """
    Runtime-стан broker health.
    """

    state: str = HEALTH_UNKNOWN
    last_error: str = ""
    updated_utc: str = ""
    manual_disconnect: bool = False

    def is_connected(self) -> bool:
        """
        Перевірити, чи broker вважається підключеним.
        """
        return self.state == HEALTH_CONNECTED

    def allows_automatic_reconnect(self) -> bool:
        """Return whether reconnect-watch may restore this connection."""
        return not self.manual_disconnect

    def set_connected(self, updated_utc: str = "") -> None:
        """
        Встановити стан CONNECTED.
        """
        self.state = HEALTH_CONNECTED
        self.last_error = ""
        self.updated_utc = updated_utc or utc_now_text()
        self.manual_disconnect = False

    def set_disconnected(
        self,
        updated_utc: str = "",
        error: str = "",
        manual: bool = False,
    ) -> None:
        """
        Встановити стан DISCONNECTED.
        """
        self.state = HEALTH_DISCONNECTED
        self.last_error = error
        self.updated_utc = updated_utc or utc_now_text()
        self.manual_disconnect = bool(manual)

    def set_safe_disconnected(
        self,
        updated_utc: str = "",
        error: str = "",
    ) -> None:
        """
        Встановити стан SAFE_DISCONNECTED.
        """
        self.state = HEALTH_SAFE_DISCONNECTED
        self.last_error = error
        self.updated_utc = updated_utc or utc_now_text()
        self.manual_disconnect = False

    def set_reconnecting(self, updated_utc: str = "") -> None:
        """
        Встановити стан RECONNECTING.
        """
        self.state = HEALTH_RECONNECTING
        self.last_error = ""
        self.updated_utc = updated_utc or utc_now_text()
        self.manual_disconnect = False

    def set_error(
        self,
        updated_utc: str = "",
        error: str = "",
    ) -> None:
        """
        Встановити стан ERROR.
        """
        self.state = HEALTH_ERROR
        self.last_error = error
        self.updated_utc = updated_utc or utc_now_text()
        self.manual_disconnect = False

    def clear(self) -> None:
        """
        Очистити broker health state.
        """
        self.state = HEALTH_UNKNOWN
        self.last_error = ""
        self.updated_utc = ""
        self.manual_disconnect = False
