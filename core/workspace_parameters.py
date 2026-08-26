# -*- coding: utf-8 -*-
"""core.workspace_parameters

Canonical per-WSP algorithm parameter model and validation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from engine.risk.constants import (
    DEFAULT_WORKSPACE_MAXIMUM_POSITION_VOLUME,
    DEFAULT_WORKSPACE_RISK_PERCENT,
    WORKSPACE_RISK_SETTING_MAXIMUM_POSITION_VOLUME,
    WORKSPACE_RISK_SETTING_RISK_PERCENT,
)
from engine.runtime_constants import (
    DEFAULT_WORKSPACE_ALLIGATOR_CONFIRMATION,
    DEFAULT_WORKSPACE_MACD_SIGNAL_MODE,
    DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT as DEFAULT_DRAWDOWN_PERCENT,
    DEFAULT_WORKSPACE_SPREAD_LIMIT,
    DEFAULT_WORKSPACE_WARMUP_BARS,
    WORKSPACE_ALLIGATOR_CONFIRMATIONS,
    WORKSPACE_MACD_SIGNAL_MODES,
)


class WorkspaceParametersError(ValueError):
    """Invalid persisted or user-entered WSP algorithm parameters."""


@dataclass(frozen=True, slots=True)
class WorkspaceAlgorithmParameters:
    """Validated editable parameters owned by exactly one WSP."""

    macd_signal_mode: str = DEFAULT_WORKSPACE_MACD_SIGNAL_MODE
    alligator_confirmation: str = DEFAULT_WORKSPACE_ALLIGATOR_CONFIRMATION
    spread_limit: float = DEFAULT_WORKSPACE_SPREAD_LIMIT
    warmup_bars: int = DEFAULT_WORKSPACE_WARMUP_BARS
    risk_percent: float = DEFAULT_WORKSPACE_RISK_PERCENT
    maximum_position_volume: float = DEFAULT_WORKSPACE_MAXIMUM_POSITION_VOLUME
    profit_drawdown_close_percent: float = DEFAULT_DRAWDOWN_PERCENT

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "macd_signal_mode",
            _normalized_choice(
                self.macd_signal_mode,
                "macd_signal_mode",
                WORKSPACE_MACD_SIGNAL_MODES,
            ),
        )
        object.__setattr__(
            self,
            "alligator_confirmation",
            _normalized_choice(
                self.alligator_confirmation,
                "alligator_confirmation",
                WORKSPACE_ALLIGATOR_CONFIRMATIONS,
            ),
        )
        object.__setattr__(
            self,
            "spread_limit",
            _positive_float(self.spread_limit, "spread_limit"),
        )
        object.__setattr__(
            self,
            "warmup_bars",
            _non_negative_int(self.warmup_bars, "warmup_bars"),
        )
        object.__setattr__(
            self,
            "risk_percent",
            _bounded_float(
                self.risk_percent,
                "risk_percent",
                minimum=0.0,
                maximum=100.0,
                minimum_inclusive=False,
                maximum_inclusive=True,
            ),
        )
        object.__setattr__(
            self,
            "maximum_position_volume",
            _positive_float(
                self.maximum_position_volume,
                "maximum_position_volume",
            ),
        )
        object.__setattr__(
            self,
            "profit_drawdown_close_percent",
            _bounded_float(
                self.profit_drawdown_close_percent,
                "profit_drawdown_close_percent",
                minimum=1.0,
                maximum=100.0,
                minimum_inclusive=True,
                maximum_inclusive=True,
            ),
        )

    @classmethod
    def from_workspace(cls, workspace: object) -> WorkspaceAlgorithmParameters:
        """Read editable fields from an AlgorithmWorkspace-like object."""
        parameters = _mapping_copy(
            getattr(workspace, "parameters", {}),
            "parameters",
        )
        risk_settings = _mapping_copy(
            getattr(workspace, "risk_settings", {}),
            "risk_settings",
        )
        profit_protection = _mapping_copy(
            getattr(workspace, "profit_protection", {}),
            "profit_protection",
        )
        return cls(
            macd_signal_mode=parameters.get(
                "macd_signal_mode",
                DEFAULT_WORKSPACE_MACD_SIGNAL_MODE,
            ),
            alligator_confirmation=parameters.get(
                "alligator_confirmation",
                DEFAULT_WORKSPACE_ALLIGATOR_CONFIRMATION,
            ),
            spread_limit=parameters.get(
                "spread_limit",
                DEFAULT_WORKSPACE_SPREAD_LIMIT,
            ),
            warmup_bars=parameters.get(
                "warmup_bars",
                DEFAULT_WORKSPACE_WARMUP_BARS,
            ),
            risk_percent=risk_settings.get(
                WORKSPACE_RISK_SETTING_RISK_PERCENT,
                DEFAULT_WORKSPACE_RISK_PERCENT,
            ),
            maximum_position_volume=risk_settings.get(
                WORKSPACE_RISK_SETTING_MAXIMUM_POSITION_VOLUME,
                DEFAULT_WORKSPACE_MAXIMUM_POSITION_VOLUME,
            ),
            profit_drawdown_close_percent=profit_protection.get(
                "max_profit_drawdown_percent",
                DEFAULT_DRAWDOWN_PERCENT,
            ),
        )

    def merge_parameters(self, current: Mapping[str, Any]) -> dict[str, Any]:
        """Update owned algorithm keys while preserving future keys."""
        result = dict(current)
        result.update(
            {
                "macd_signal_mode": self.macd_signal_mode,
                "alligator_confirmation": self.alligator_confirmation,
                "spread_limit": self.spread_limit,
                "warmup_bars": self.warmup_bars,
            }
        )
        return result

    def merge_risk_settings(
        self,
        current: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Update owned risk keys while preserving future keys."""
        result = dict(current)
        result[WORKSPACE_RISK_SETTING_RISK_PERCENT] = self.risk_percent
        volume_key = WORKSPACE_RISK_SETTING_MAXIMUM_POSITION_VOLUME
        result[volume_key] = self.maximum_position_volume
        return result

    def merge_profit_protection(
        self,
        current: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Update the drawdown limit without overwriting other guards."""
        result = dict(current)
        result["max_profit_drawdown_percent"] = self.profit_drawdown_close_percent
        return result


def _normalized_choice(
    value: object,
    field_name: str,
    allowed: tuple[str, ...],
) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in allowed:
        raise WorkspaceParametersError(
            f"Invalid {field_name}: {normalized or '<empty>'}"
        )
    return normalized


def _positive_float(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise WorkspaceParametersError(f"{field_name} must be a number")
    try:
        if isinstance(value, (int, float)):
            normalized = float(value)
        elif isinstance(value, str):
            normalized = float(value.strip())
        else:
            raise TypeError
    except (TypeError, ValueError) as exc:
        raise WorkspaceParametersError(
            f"{field_name} must be a number"
        ) from exc
    if not math.isfinite(normalized) or normalized <= 0.0:
        raise WorkspaceParametersError(f"{field_name} must be positive")
    return normalized


def _non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise WorkspaceParametersError(f"{field_name} must be an integer")
    try:
        if isinstance(value, int):
            normalized = value
        elif isinstance(value, float):
            if not value.is_integer():
                raise ValueError
            normalized = int(value)
        elif isinstance(value, str):
            normalized = int(value.strip())
        else:
            raise TypeError
    except (TypeError, ValueError) as exc:
        raise WorkspaceParametersError(
            f"{field_name} must be an integer"
        ) from exc
    if normalized < 0:
        raise WorkspaceParametersError(
            f"{field_name} cannot be negative"
        )
    return normalized


def _bounded_float(
    value: object,
    field_name: str,
    *,
    minimum: float,
    maximum: float,
    minimum_inclusive: bool,
    maximum_inclusive: bool,
) -> float:
    normalized = _positive_float(value, field_name)
    minimum_valid = (
        normalized >= minimum
        if minimum_inclusive
        else normalized > minimum
    )
    maximum_valid = (
        normalized <= maximum
        if maximum_inclusive
        else normalized < maximum
    )
    if not minimum_valid or not maximum_valid:
        left = "[" if minimum_inclusive else "("
        right = "]" if maximum_inclusive else ")"
        raise WorkspaceParametersError(
            f"{field_name} must be in {left}{minimum}, {maximum}{right}"
        )
    return normalized


def _mapping_copy(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise WorkspaceParametersError(f"{field_name} must be a mapping")
    return dict(value)
