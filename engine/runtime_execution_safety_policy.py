"""Broker-neutral policy безпеки runtime execution для LGE."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True, slots=True)
class RuntimeExecutionSafetyPolicy:
    """Policy fail-closed перевірок freshness перед execution."""

    position_snapshot_max_age_by_broker: Mapping[str, timedelta] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        """Нормалізувати broker keys і заморозити policy mapping."""

        normalized: dict[str, timedelta] = {}
        for broker, max_age in self.position_snapshot_max_age_by_broker.items():
            broker_name = str(broker or "").strip().upper()
            if not broker_name:
                continue
            normalized[broker_name] = max_age

        object.__setattr__(
            self,
            "position_snapshot_max_age_by_broker",
            MappingProxyType(normalized),
        )

    def resolve_position_snapshot_max_age(
        self,
        broker: str,
    ) -> timedelta | None:
        """Повернути max snapshot age для exact broker або fail closed."""

        broker_name = str(broker or "").strip().upper()
        if not broker_name:
            return None

        max_age = self.position_snapshot_max_age_by_broker.get(broker_name)
        if max_age is None or max_age <= timedelta(0):
            return None
        return max_age
