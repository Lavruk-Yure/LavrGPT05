# -*- coding: utf-8 -*-
"""Обчислювані runtime-вимоги WSP для spread і прогріву.

Модуль не змінює чинні persisted legacy keys ``spread_limit`` і
``warmup_bars``. Вони залишаються для сумісності старих Session і тестів,
доки Runtime та єдиний Designer-діалог параметрів не будуть переведені на
обчислювані policy/requirements.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


LEGACY_WORKSPACE_SPREAD_LIMIT_KEY = "spread_limit"
LEGACY_WORKSPACE_WARMUP_BARS_KEY = "warmup_bars"

LEGACY_WORKSPACE_RUNTIME_PARAMETER_KEYS = (
    LEGACY_WORKSPACE_SPREAD_LIMIT_KEY,
    LEGACY_WORKSPACE_WARMUP_BARS_KEY,
)


class WorkspaceRuntimeRequirementError(ValueError):
    """Некоректні market-data або warm-up metadata."""


@dataclass(frozen=True, slots=True)
class WorkspaceSpreadObservation:
    """Фактичний spread, обчислений із синхронної пари bid/ask."""

    bid: float
    ask: float
    spread_price: float
    point_size: float | None = None
    spread_points: float | None = None

    @classmethod
    def from_bid_ask(
        cls,
        *,
        bid: object,
        ask: object,
        point_size: object | None = None,
    ) -> WorkspaceSpreadObservation:
        normalized_bid = _positive_float(bid, "bid")
        normalized_ask = _positive_float(ask, "ask")
        if normalized_ask < normalized_bid:
            raise WorkspaceRuntimeRequirementError("ask cannot be below bid")

        spread_price = normalized_ask - normalized_bid
        normalized_point_size: float | None = None
        spread_points: float | None = None
        if point_size is not None:
            normalized_point_size = _positive_float(point_size, "point_size")
            spread_points = spread_price / normalized_point_size

        return cls(
            bid=normalized_bid,
            ask=normalized_ask,
            spread_price=spread_price,
            point_size=normalized_point_size,
            spread_points=spread_points,
        )


@dataclass(frozen=True, slots=True)
class WorkspaceWarmupRequirement:
    """Потреба одного активного сигналу, фільтра або індикатора в історії."""

    component_code: str
    timeframe: str
    required_bars: int

    def __post_init__(self) -> None:
        _required_code(self.component_code, "component_code")
        _required_code(self.timeframe, "timeframe")
        _non_negative_int(self.required_bars, "required_bars")


@dataclass(frozen=True, slots=True)
class WorkspaceWarmupTimeframePlan:
    """Підсумкова вимога прогріву для одного timeframe."""

    timeframe: str
    component_bars: int
    reserve_bars: int
    required_bars: int
    limiting_components: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorkspaceWarmupPlan:
    """Детермінований warm-up plan для всіх активних timeframe WSP."""

    timeframes: tuple[WorkspaceWarmupTimeframePlan, ...]

    def required_bars_for(self, timeframe: str) -> int:
        normalized = _required_code(timeframe, "timeframe")
        for plan in self.timeframes:
            if plan.timeframe == normalized:
                return plan.required_bars
        return 0


def build_workspace_warmup_plan(
    requirements: tuple[WorkspaceWarmupRequirement, ...],
    *,
    reserve_bars: object = 0,
) -> WorkspaceWarmupPlan:
    """Взяти максимум вимог компонентів окремо для кожного timeframe."""
    normalized_reserve = _non_negative_int(reserve_bars, "reserve_bars")
    grouped: dict[str, list[WorkspaceWarmupRequirement]] = {}
    for requirement in requirements:
        if not isinstance(requirement, WorkspaceWarmupRequirement):
            raise WorkspaceRuntimeRequirementError(
                "requirements must contain WorkspaceWarmupRequirement values"
            )
        grouped.setdefault(requirement.timeframe, []).append(requirement)

    plans: list[WorkspaceWarmupTimeframePlan] = []
    for timeframe in sorted(grouped):
        items = grouped[timeframe]
        component_bars = max(item.required_bars for item in items)
        limiting_components = tuple(
            sorted(
                item.component_code
                for item in items
                if item.required_bars == component_bars
            )
        )
        plans.append(
            WorkspaceWarmupTimeframePlan(
                timeframe=timeframe,
                component_bars=component_bars,
                reserve_bars=normalized_reserve,
                required_bars=component_bars + normalized_reserve,
                limiting_components=limiting_components,
            )
        )

    return WorkspaceWarmupPlan(timeframes=tuple(plans))


def _positive_float(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise WorkspaceRuntimeRequirementError(
            f"{field_name} must be a positive number"
        )
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise WorkspaceRuntimeRequirementError(
            f"{field_name} must be a positive number"
        ) from exc
    if not math.isfinite(number) or number <= 0.0:
        raise WorkspaceRuntimeRequirementError(
            f"{field_name} must be a positive number"
        )
    return number


def _non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise WorkspaceRuntimeRequirementError(
            f"{field_name} must be a non-negative integer"
        )
    text = str(value).strip()
    try:
        number = int(text)
    except ValueError as exc:
        raise WorkspaceRuntimeRequirementError(
            f"{field_name} must be a non-negative integer"
        ) from exc
    if number < 0:
        raise WorkspaceRuntimeRequirementError(
            f"{field_name} must be a non-negative integer"
        )
    return number


def _required_code(value: object, field_name: str) -> str:
    text = str(value or "").strip().upper()
    if not text:
        raise WorkspaceRuntimeRequirementError(f"{field_name} is required")
    return text
