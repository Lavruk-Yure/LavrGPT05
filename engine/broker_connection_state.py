# broker_connection_state.py
"""
Канонічні стани broker connection для LGE runtime.

Це окремий стан від RuntimeState.
RuntimeState описує стан ATS engine.
BrokerConnectionState описує тільки підключення до брокера.
"""

from enum import StrEnum


class BrokerConnectionState(StrEnum):
    """Канонічні стани підключення до broker."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    ERROR = "ERROR"


def normalize_broker_connection_state(
    value: BrokerConnectionState | str,
) -> BrokerConnectionState:
    """
    Нормалізувати значення у BrokerConnectionState.
    """

    if isinstance(value, BrokerConnectionState):
        return value

    return BrokerConnectionState(str(value).strip().upper())
