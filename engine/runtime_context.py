# runtime_context.py
"""
Канонічний runtime context ATS-двигуна LGE.

Модуль не залежить від:
- Qt
- SQLite
- broker API
- UI

Тут лише:
- поточний runtime state;
- runtime metadata;
- helper-методи runtime context.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from engine.broker_connection_state import (
    BrokerConnectionState,
    normalize_broker_connection_state,
)
from engine.runtime_state import (
    RuntimeState,
    normalize_runtime_state,
    validate_transition,
)


def utc_now_iso() -> str:
    """
    Повернути UTC timestamp у ISO-форматі.
    """

    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(slots=True)
class RuntimeContext:
    """
    Поточний runtime context ATS-двигуна.
    """

    runtime_state: RuntimeState = RuntimeState.OFF

    broker: str = "OFF"

    account_mode: str = "OFF"

    execution_mode: str = "OFF"

    broker_connection_state: BrokerConnectionState = BrokerConnectionState.DISCONNECTED

    active_db: str = ""

    session_id: str = field(default_factory=lambda: str(uuid4()))

    created_utc: str = field(default_factory=utc_now_iso)

    updated_utc: str = field(default_factory=utc_now_iso)

    def set_runtime_state(
        self,
        new_state: RuntimeState | str,
    ) -> None:
        """
        Змінити runtime state з перевіркою переходу.
        """

        target_state = normalize_runtime_state(new_state)

        validate_transition(
            self.runtime_state,
            target_state,
        )

        self.runtime_state = target_state

        self.touch()

    def set_broker_connection_state(
        self,
        new_state: BrokerConnectionState | str,
    ) -> None:
        """
        Змінити broker connection state.
        """

        self.broker_connection_state = normalize_broker_connection_state(new_state)
        self.touch()

    def touch(self) -> None:
        """
        Оновити updated_utc.
        """

        self.updated_utc = utc_now_iso()

    def to_dict(self) -> dict:
        """
        Перетворити RuntimeContext у dict.
        """

        return {
            "runtime_state": self.runtime_state.value,
            "broker": self.broker,
            "account_mode": self.account_mode,
            "execution_mode": self.execution_mode,
            "broker_connection_state": self.broker_connection_state.value,
            "active_db": self.active_db,
            "session_id": self.session_id,
            "created_utc": self.created_utc,
            "updated_utc": self.updated_utc,
        }
