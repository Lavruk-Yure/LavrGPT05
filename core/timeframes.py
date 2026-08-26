# timeframes.py
"""
Уніфікований список timeframe для LGE.

НЕ залежить від брокера.
Використовується як базовий рівень для:
- signals
- filters
- rails
- strategies
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.runtime_constants import (
    WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED,
    WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_1,
    WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2,
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
    WORKSPACE_ALLIGATOR_HIGHER_1_TIMEFRAME_BY_BASE,
    WORKSPACE_ALLIGATOR_HIGHER_2_TIMEFRAME_BY_BASE,
)


@dataclass(frozen=True)
class Timeframe:
    name: str
    minutes: int
    enabled: bool


TIMEFRAMES: tuple[Timeframe, ...] = (
    Timeframe("M1", 1, True),
    Timeframe("M5", 5, True),
    Timeframe("M15", 15, True),
    Timeframe("M30", 30, True),
    Timeframe("H1", 60, True),
    Timeframe("H4", 240, True),
    Timeframe("D1", 1440, True),
)


TIMEFRAME_BY_NAME: dict[str, Timeframe] = {tf.name: tf for tf in TIMEFRAMES}


def get_timeframe(name: str) -> Timeframe:
    key = name.strip().upper()
    if key not in TIMEFRAME_BY_NAME:
        raise KeyError(f"Unknown timeframe: {name}")
    return TIMEFRAME_BY_NAME[key]


def is_timeframe_enabled(name: str) -> bool:
    return get_timeframe(name).enabled


def list_enabled_timeframes() -> list[str]:
    return [tf.name for tf in TIMEFRAMES if tf.enabled]


class WorkspaceTimeframeResolutionError(ValueError):
    """Некоректний перехід timeframe WSP."""


def resolve_alligator_confirmation_timeframe(
    base_timeframe: str,
    confirmation_mode: str,
) -> str:
    """Повернути timeframe Alligator без неявного fallback."""
    base = get_timeframe(base_timeframe)
    mode = str(confirmation_mode or "").strip().upper()
    if mode in {
        WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
        WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED,
    }:
        return base.name
    if mode == WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_1:
        mapping = WORKSPACE_ALLIGATOR_HIGHER_1_TIMEFRAME_BY_BASE
    elif mode == WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2:
        mapping = WORKSPACE_ALLIGATOR_HIGHER_2_TIMEFRAME_BY_BASE
    else:
        raise WorkspaceTimeframeResolutionError(
            f"Unsupported Alligator confirmation mode: {mode or '<empty>'}"
        )

    resolved_name = mapping.get(base.name)
    if resolved_name is None:
        raise WorkspaceTimeframeResolutionError(
            f"Alligator {mode} timeframe is unavailable for {base.name}"
        )
    resolved = get_timeframe(resolved_name)
    if resolved.minutes <= base.minutes:
        raise WorkspaceTimeframeResolutionError(
            f"Alligator {mode} must resolve above {base.name}"
        )
    if resolved.minutes % base.minutes != 0:
        raise WorkspaceTimeframeResolutionError(
            f"Alligator {mode} must be an integer multiple of {base.name}"
        )
    return resolved.name
