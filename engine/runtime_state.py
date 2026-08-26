# runtime_state.py
"""
Канонічні runtime-стани ATS-двигуна LGE.

Модуль навмисно не залежить від:
- Qt
- SQLite
- broker API
- UI
- config

Тут лише:
- стани runtime;
- дозволені переходи;
- перевірка переходів;
- helper-функції.
"""

from enum import StrEnum


class RuntimeStateError(ValueError):
    """Помилка runtime-стану або переходу."""


class RuntimeState(StrEnum):
    """Канонічні runtime-стани ATS."""

    OFF = "OFF"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    ERROR = "ERROR"


# Дозволені переходи між runtime-станами.
ALLOWED_TRANSITIONS: dict[RuntimeState, set[RuntimeState]] = {
    RuntimeState.OFF: {RuntimeState.STARTING},
    RuntimeState.STARTING: {
        RuntimeState.RUNNING,
        RuntimeState.ERROR,
    },
    RuntimeState.RUNNING: {
        RuntimeState.STOPPING,
        RuntimeState.ERROR,
    },
    RuntimeState.STOPPING: {
        RuntimeState.OFF,
        RuntimeState.ERROR,
    },
    RuntimeState.ERROR: {
        RuntimeState.OFF,
    },
}


def normalize_runtime_state(value: RuntimeState | str) -> RuntimeState:
    """
    Нормалізувати значення у RuntimeState.
    """

    if isinstance(value, RuntimeState):
        return value

    try:
        return RuntimeState(str(value).strip().upper())
    except ValueError as exc:
        raise RuntimeStateError(f"Невідомий runtime state: {value!r}") from exc


def can_transition(
    current: RuntimeState | str,
    target: RuntimeState | str,
) -> bool:
    """
    Перевірити, чи дозволений перехід current -> target.
    """

    current_state = normalize_runtime_state(current)
    target_state = normalize_runtime_state(target)

    return target_state in ALLOWED_TRANSITIONS[current_state]


def validate_transition(
    current: RuntimeState | str,
    target: RuntimeState | str,
) -> None:
    """
    Перевірити коректність переходу current -> target.

    Якщо перехід заборонений —
    підняти RuntimeStateError.
    """

    current_state = normalize_runtime_state(current)
    target_state = normalize_runtime_state(target)

    if target_state not in ALLOWED_TRANSITIONS[current_state]:
        raise RuntimeStateError(
            f"Недозволений runtime transition: "
            f"{current_state.value} -> {target_state.value}"
        )


def is_active(state: RuntimeState | str) -> bool:
    """
    Перевірити, чи runtime зараз активний.
    """

    runtime_state = normalize_runtime_state(state)

    return runtime_state in {
        RuntimeState.STARTING,
        RuntimeState.RUNNING,
        RuntimeState.STOPPING,
    }


def can_start(state: RuntimeState | str) -> bool:
    """
    Перевірити, чи можна запускати runtime.
    """

    return can_transition(state, RuntimeState.STARTING)


def can_stop(state: RuntimeState | str) -> bool:
    """
    Перевірити, чи можна зупиняти runtime.
    """

    return can_transition(state, RuntimeState.STOPPING)
