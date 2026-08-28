# core/workspace_execution_identity.py — causal identity виконання Workspace
# -*- coding: utf-8 -*-
"""Спільна causal-нормалізація identity виконання для Workspace.

Модуль працює після визначення сигналу та допустимості входу. Він не оцінює
індикатори й не змінює пороги виконання, а лише гарантує один детермінований
causal source-survivor для кожної execution identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from core.workspace_market_event import normalize_market_timestamp

WORKSPACE_EXECUTION_FIRST_LEG = "FIRST_LEG"
WORKSPACE_EXECUTION_REENTRY = "REENTRY"


@dataclass(frozen=True, slots=True)
class WorkspaceExecutionIdentity:
    """Identity одного вже дозволеного виконання Workspace."""

    leg: str
    direction: str
    next_m15_entry_index: int | None = None
    donchian_signal_index: int | None = None
    next_m15_entry_timestamp: datetime | None = None

    def __post_init__(self) -> None:
        leg = str(self.leg or "").strip().upper()
        direction = str(self.direction or "").strip().upper()
        if leg not in (
            WORKSPACE_EXECUTION_FIRST_LEG,
            WORKSPACE_EXECUTION_REENTRY,
        ):
            raise ValueError("Непідтримуваний тип виконання Workspace")
        if direction not in ("BUY", "SELL"):
            raise ValueError("Напрям виконання Workspace має бути BUY або SELL")

        entry_index = _optional_non_negative_int(
            self.next_m15_entry_index,
            "next_m15_entry_index",
        )
        signal_index = _optional_non_negative_int(
            self.donchian_signal_index,
            "donchian_signal_index",
        )
        entry_timestamp = self.next_m15_entry_timestamp
        if entry_timestamp is not None:
            entry_timestamp = normalize_market_timestamp(entry_timestamp)

        if leg == WORKSPACE_EXECUTION_FIRST_LEG:
            if entry_index is None:
                raise ValueError("FIRST_LEG потребує next_m15_entry_index")
            if signal_index is not None or entry_timestamp is not None:
                raise ValueError(
                    "Identity FIRST_LEG: напрям + індекс наступного M15-входу"
                )
        else:
            if signal_index is None or entry_timestamp is None:
                raise ValueError(
                    "REENTRY потребує індекс сигналу Donchian і timestamp "
                    "наступного M15-входу"
                )
            if entry_index is not None:
                raise ValueError(
                    "Identity REENTRY не використовує next_m15_entry_index"
                )

        object.__setattr__(self, "leg", leg)
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "next_m15_entry_index", entry_index)
        object.__setattr__(self, "donchian_signal_index", signal_index)
        object.__setattr__(self, "next_m15_entry_timestamp", entry_timestamp)

    @classmethod
    def first_leg(
        cls,
        *,
        direction: str,
        next_m15_entry_index: int,
    ) -> WorkspaceExecutionIdentity:
        return cls(
            leg=WORKSPACE_EXECUTION_FIRST_LEG,
            direction=direction,
            next_m15_entry_index=next_m15_entry_index,
        )

    @classmethod
    def reentry(
        cls,
        *,
        direction: str,
        donchian_signal_index: int,
        next_m15_entry_timestamp: datetime,
    ) -> WorkspaceExecutionIdentity:
        return cls(
            leg=WORKSPACE_EXECUTION_REENTRY,
            direction=direction,
            donchian_signal_index=donchian_signal_index,
            next_m15_entry_timestamp=next_m15_entry_timestamp,
        )

    def deterministic_key(self) -> tuple[object, ...]:
        """Повернути сталий ключ лише для сортування результату."""
        if self.leg == WORKSPACE_EXECUTION_FIRST_LEG:
            return self.leg, self.direction, self.next_m15_entry_index
        assert self.next_m15_entry_timestamp is not None
        return (
            self.leg,
            self.direction,
            self.donchian_signal_index,
            self.next_m15_entry_timestamp,
        )


@dataclass(frozen=True, slots=True)
class WorkspaceExecutionSource:
    """Один causal source, що претендує на execution identity.

    Контракт не приймає outcome угоди, тому вибір survivor структурно не
    залежить від результату виконання.
    """

    identity: WorkspaceExecutionIdentity
    opening_source_index: int
    confirmation_index: int
    source_uid: str

    def __post_init__(self) -> None:
        if not isinstance(self.identity, WorkspaceExecutionIdentity):
            raise ValueError("identity має бути WorkspaceExecutionIdentity")
        opening_index = _non_negative_int(
            self.opening_source_index,
            "opening_source_index",
        )
        confirmation_index = _non_negative_int(
            self.confirmation_index,
            "confirmation_index",
        )
        source_uid = str(self.source_uid or "").strip()
        if not source_uid:
            raise ValueError("source_uid є обов'язковим")
        object.__setattr__(self, "opening_source_index", opening_index)
        object.__setattr__(self, "confirmation_index", confirmation_index)
        object.__setattr__(self, "source_uid", source_uid)

    def causal_rank(self) -> tuple[int, int, str]:
        """Ранжувати за найранішим opening, потім за confirmation."""
        return (
            self.opening_source_index,
            self.confirmation_index,
            self.source_uid,
        )


def normalize_workspace_execution_sources(
    sources: Iterable[WorkspaceExecutionSource],
) -> tuple[WorkspaceExecutionSource, ...]:
    """Лишити один найраніший deterministic causal source на identity."""
    survivors: dict[WorkspaceExecutionIdentity, WorkspaceExecutionSource] = {}
    for source in sources:
        if not isinstance(source, WorkspaceExecutionSource):
            raise ValueError("sources має містити WorkspaceExecutionSource")
        current = survivors.get(source.identity)
        if current is None or _source_precedes(source, current):
            survivors[source.identity] = source
    return tuple(
        sorted(
            survivors.values(),
            key=lambda item: (
                item.identity.deterministic_key(),
                item.causal_rank(),
            ),
        )
    )


def _source_precedes(
    candidate: WorkspaceExecutionSource,
    current: WorkspaceExecutionSource,
) -> bool:
    """Порівняти causal sources без неоднорідного tuple-comparison."""
    if candidate.opening_source_index != current.opening_source_index:
        return candidate.opening_source_index < current.opening_source_index
    if candidate.confirmation_index != current.confirmation_index:
        return candidate.confirmation_index < current.confirmation_index
    return candidate.source_uid < current.source_uid


def _optional_non_negative_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    return _non_negative_int(value, field_name)


def _non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a non-negative integer")
    try:
        normalized = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a non-negative integer") from exc
    if normalized < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return normalized
