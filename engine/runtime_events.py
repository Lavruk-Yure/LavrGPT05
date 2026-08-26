# runtime_events.py
"""
Канонічні runtime events для ATS-двигуна LGE.

Модуль не залежить від:
- Qt
- SQLite
- broker API
- UI

Тут лише:
- типи runtime events;
- структура event;
- UTC timestamp helper.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class RuntimeEventType(StrEnum):
    """Канонічні типи runtime events."""

    STARTUP = "STARTUP"
    SHUTDOWN = "SHUTDOWN"

    BROKER_SELECTED = "BROKER_SELECTED"
    BROKER_ADAPTER_SELECTED = "BROKER_ADAPTER_SELECTED"
    BROKER_SERVICE_SELECTED = "BROKER_SERVICE_SELECTED"
    BROKER_CONNECTING = "BROKER_CONNECTING"
    BROKER_CONNECTED = "BROKER_CONNECTED"
    BROKER_DISCONNECTED = "BROKER_DISCONNECTED"
    BROKER_CONNECTION_ERROR = "BROKER_CONNECTION_ERROR"

    ACCOUNT_LOADED = "ACCOUNT_LOADED"
    ACCOUNT_UPDATED = "ACCOUNT_UPDATED"
    SNAPSHOT_UPDATED = "SNAPSHOT_UPDATED"
    IB_MANUAL_RECONCILIATION_RESOLVED = (
        "IB_MANUAL_RECONCILIATION_RESOLVED"
    )
    IB_FX_EXTERNAL_EXPOSURE_CONFIRMED = (
        "IB_FX_EXTERNAL_EXPOSURE_CONFIRMED"
    )
    IB_FX_EXTERNAL_EXPOSURE_STALE = "IB_FX_EXTERNAL_EXPOSURE_STALE"
    IB_FX_EXTERNAL_EXPOSURE_CLEARED = "IB_FX_EXTERNAL_EXPOSURE_CLEARED"

    RECONNECT_STARTED = "RECONNECT_STARTED"
    RECONNECT_SUCCESS = "RECONNECT_SUCCESS"
    RECONNECT_FAILED = "RECONNECT_FAILED"

    MODE_CHANGED = "MODE_CHANGED"

    ENGINE_CONFIG_CHANGED = "ENGINE_CONFIG_CHANGED"

    ERROR = "ERROR"


def utc_now_iso() -> str:
    """
    Повернути UTC timestamp у ISO-форматі.
    """

    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(slots=True)
class RuntimeEvent:
    """
    Runtime event ATS-двигуна.
    """

    event_type: RuntimeEventType

    message: str = ""

    created_utc: str = field(default_factory=utc_now_iso)

    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """
        Перетворити RuntimeEvent у dict.
        """

        return {
            "event_type": self.event_type.value,
            "message": self.message,
            "created_utc": self.created_utc,
            "payload": self.payload,
        }
