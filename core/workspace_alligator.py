# -*- coding: utf-8 -*-
"""Детермінований Alligator-фільтр для Replay WSP.

Alligator використовує точний ``resolved_profile_snapshot``
із прив'язки WSP. Редагування профілю не змінює
збережений Replay. Контракт реалізує ``SAME_TIMEFRAME``,
``HIGHER_1`` та експериментальний ``HIGHER_2`` без look-ahead bias.
RoadMap101 додає causal FLAT/TREND_UP/TREND_DOWN diagnostics і фазу
STARTING/ACTIVE/ENDING. Legacy snapshot використовує 3-bar confirmation.
Окремий immutable Candidate F profile фіксує 4-bar confirmation,
ARMED/deferred MACD, opening-collapse та structural guards. Для
SAME_TIMEFRAME phase-gate дозволяє сигнал лише в ACTIVE при збігу напряму;
STARTING, ENDING і FLAT відхиляються. HIGHER_1/HIGHER_2 не використовують
Candidate F trade gate. Journal зберігає causal T-2/T-1/T diagnostics.
RoadMap102 додає read-only terminal lifecycle evidence RELEASE/CANCEL/EXPIRE;
воно не змінює thresholds, ALLOW/REJECT або broker execution.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.algorithm_workspace import WORKSPACE_DATA_MODE_REPLAY
from core.timeframes import resolve_alligator_confirmation_timeframe
from core.workspace_algorithm import (
    WorkspaceAlgorithm,
    WorkspaceAlgorithmError,
    WorkspaceSignalOutput,
)
from core.workspace_chart import (
    WORKSPACE_CHART_ROLE_INDICATOR_HISTOGRAM,
    WORKSPACE_CHART_ROLE_INDICATOR_LINE,
    WORKSPACE_CHART_ROLE_PRICE_OVERLAY,
    WorkspaceChartSeries,
    WorkspaceChartSeriesPoint,
)
from core.workspace_indicator_profile import (
    ALLIGATOR_LOGIC_MODE_CANDIDATE_F,
    ALLIGATOR_LOGIC_MODE_LEGACY,
    ALLIGATOR_LOGIC_MODES,
    ALLIGATOR_PROFILE_UID_LGE_CLASSIC,
    WORKSPACE_INDICATOR_ALLIGATOR,
    WORKSPACE_INDICATOR_MA_EXPONENTIAL,
    WORKSPACE_INDICATOR_MA_SIMPLE,
    WORKSPACE_INDICATOR_MA_SMOOTHED,
    WORKSPACE_INDICATOR_MA_TYPES,
    WORKSPACE_INDICATOR_SOURCE_CLOSE,
    WORKSPACE_INDICATOR_SOURCE_HIGH,
    WORKSPACE_INDICATOR_SOURCE_LOW,
    WORKSPACE_INDICATOR_SOURCE_MEDIAN,
    WORKSPACE_INDICATOR_SOURCE_OPEN,
    WORKSPACE_INDICATOR_SOURCE_TYPICAL,
    WORKSPACE_INDICATOR_SOURCE_WEIGHTED,
    WORKSPACE_INDICATOR_SOURCES,
    WorkspaceIndicatorProfileBinding,
    built_in_workspace_indicator_profile,
    workspace_indicator_profile_binding,
)
from core.workspace_macd import (
    MACD_COMPONENT_CODE,
    WorkspaceMacdSignalSource,
)
from core.workspace_market_event import WorkspaceMarketEvent
from core.workspace_runtime_requirements import WorkspaceWarmupRequirement
from core.workspace_signal import (
    WORKSPACE_SIGNAL_FILTER_ALLOW,
    WORKSPACE_SIGNAL_FILTER_REJECT,
    WorkspaceSignalFilterContext,
    WorkspaceSignalFilterObservation,
    WorkspaceSignalProposal,
)
from core.workspace_timeframe_aggregation import (
    WorkspaceTimeframeAggregator,
)
from engine.runtime_constants import (
    DEFAULT_WORKSPACE_ALLIGATOR_CONFIRMATION,
    DEFAULT_WORKSPACE_ALLIGATOR_FILTER_ENABLED,
    WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED,
    WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_1,
    WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2,
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
    WORKSPACE_ALLIGATOR_CONFIRMATIONS,
    WORKSPACE_ALLIGATOR_FILTER_ENABLED_KEY,
)

if TYPE_CHECKING:
    from core.workspace_runtime import WorkspaceRuntimeContext

ALLIGATOR_COMPONENT_CODE = "ALLIGATOR"
ALLIGATOR_JAW_PERIOD = 13
ALLIGATOR_JAW_SHIFT = 8
ALLIGATOR_TEETH_PERIOD = 8
ALLIGATOR_TEETH_SHIFT = 5
ALLIGATOR_LIPS_PERIOD = 5
ALLIGATOR_LIPS_SHIFT = 3
ALLIGATOR_REQUIRED_BARS = max(
    ALLIGATOR_JAW_PERIOD + ALLIGATOR_JAW_SHIFT,
    ALLIGATOR_TEETH_PERIOD + ALLIGATOR_TEETH_SHIFT,
    ALLIGATOR_LIPS_PERIOD + ALLIGATOR_LIPS_SHIFT,
)

ALLIGATOR_STATE_DISABLED = "ALLIGATOR_DISABLED"
ALLIGATOR_STATE_WARMUP = "ALLIGATOR_WARMUP"
ALLIGATOR_STATE_NEUTRAL = "ALLIGATOR_NEUTRAL"
ALLIGATOR_STATE_BULLISH = "ALLIGATOR_BULLISH"
ALLIGATOR_STATE_BEARISH = "ALLIGATOR_BEARISH"

# RoadMap101: перший causal diagnostic режиму ринку за Alligator.
# Порогові значення поки НЕ впливають на ALLOW/REJECT: спочатку збираємо
# ручні приклади FLAT/TREND і калібруємо межі на фактичному Replay.
ALLIGATOR_REGIME_DISABLED = "ALLIGATOR_REGIME_DISABLED"
ALLIGATOR_REGIME_WARMUP = "ALLIGATOR_REGIME_WARMUP"
ALLIGATOR_REGIME_FLAT = "ALLIGATOR_REGIME_FLAT"
ALLIGATOR_REGIME_TREND_UP = "ALLIGATOR_REGIME_TREND_UP"
ALLIGATOR_REGIME_TREND_DOWN = "ALLIGATOR_REGIME_TREND_DOWN"
ALLIGATOR_REGIME_PHASE_NONE = "ALLIGATOR_REGIME_PHASE_NONE"
ALLIGATOR_REGIME_PHASE_STARTING = "ALLIGATOR_REGIME_PHASE_STARTING"
ALLIGATOR_REGIME_PHASE_ACTIVE = "ALLIGATOR_REGIME_PHASE_ACTIVE"
ALLIGATOR_REGIME_PHASE_ENDING = "ALLIGATOR_REGIME_PHASE_ENDING"
ALLIGATOR_REGIME_LOOKBACK_BARS = 20
ALLIGATOR_REGIME_RANGE_WINDOW_BARS = 20
ALLIGATOR_REGIME_FLAT_MAX_NORMALIZED_SLOPE = 0.05
ALLIGATOR_REGIME_FLAT_MAX_NORMALIZED_OPENING = 0.60
ALLIGATOR_REGIME_FLAT_CONFIRMATION_BARS = 3
ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS = 3

ALLIGATOR_CONFIRMATION_DISABLED = WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED
ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME_BULLISH = "SAME_TIMEFRAME_BULLISH"
ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME_BEARISH = "SAME_TIMEFRAME_BEARISH"
ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME_NEUTRAL = "SAME_TIMEFRAME_NEUTRAL"
ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME_WARMUP = "SAME_TIMEFRAME_WARMUP"
ALLIGATOR_CONFIRMATION_HIGHER_1_BULLISH = "HIGHER_1_BULLISH"
ALLIGATOR_CONFIRMATION_HIGHER_1_BEARISH = "HIGHER_1_BEARISH"
ALLIGATOR_CONFIRMATION_HIGHER_1_NEUTRAL = "HIGHER_1_NEUTRAL"
ALLIGATOR_CONFIRMATION_HIGHER_1_WARMUP = "HIGHER_1_WARMUP"
ALLIGATOR_CONFIRMATION_HIGHER_2_BULLISH = "HIGHER_2_BULLISH"
ALLIGATOR_CONFIRMATION_HIGHER_2_BEARISH = "HIGHER_2_BEARISH"
ALLIGATOR_CONFIRMATION_HIGHER_2_NEUTRAL = "HIGHER_2_NEUTRAL"
ALLIGATOR_CONFIRMATION_HIGHER_2_WARMUP = "HIGHER_2_WARMUP"

ALLIGATOR_REASON_DISABLED_BYPASS = "ALLIGATOR_DISABLED_BYPASS"
ALLIGATOR_REASON_BUY_ALLOW = "ALLIGATOR_SAME_TIMEFRAME_BUY_ALLOW"
ALLIGATOR_REASON_SELL_ALLOW = "ALLIGATOR_SAME_TIMEFRAME_SELL_ALLOW"
ALLIGATOR_REASON_BUY_REJECT = "ALLIGATOR_SAME_TIMEFRAME_BUY_REJECT"
ALLIGATOR_REASON_SELL_REJECT = "ALLIGATOR_SAME_TIMEFRAME_SELL_REJECT"
ALLIGATOR_REASON_NOT_READY = "ALLIGATOR_SAME_TIMEFRAME_NOT_READY"
ALLIGATOR_REASON_BUY_START_REJECT = "ALLIGATOR_SAME_TIMEFRAME_BUY_STARTING_REJECT"
ALLIGATOR_REASON_SELL_START_REJECT = "ALLIGATOR_SAME_TIMEFRAME_SELL_STARTING_REJECT"
ALLIGATOR_REASON_BUY_END_REJECT = "ALLIGATOR_SAME_TIMEFRAME_BUY_ENDING_REJECT"
ALLIGATOR_REASON_SELL_END_REJECT = "ALLIGATOR_SAME_TIMEFRAME_SELL_ENDING_REJECT"
ALLIGATOR_REASON_HIGHER_1_BUY_ALLOW = "ALLIGATOR_HIGHER_1_BUY_ALLOW"
ALLIGATOR_REASON_HIGHER_1_SELL_ALLOW = "ALLIGATOR_HIGHER_1_SELL_ALLOW"
ALLIGATOR_REASON_HIGHER_1_BUY_REJECT = "ALLIGATOR_HIGHER_1_BUY_REJECT"
ALLIGATOR_REASON_HIGHER_1_SELL_REJECT = "ALLIGATOR_HIGHER_1_SELL_REJECT"
ALLIGATOR_REASON_HIGHER_1_NOT_READY = "ALLIGATOR_HIGHER_1_NOT_READY"
ALLIGATOR_REASON_HIGHER_2_BUY_ALLOW = "ALLIGATOR_HIGHER_2_BUY_ALLOW"
ALLIGATOR_REASON_HIGHER_2_SELL_ALLOW = "ALLIGATOR_HIGHER_2_SELL_ALLOW"
ALLIGATOR_REASON_HIGHER_2_BUY_REJECT = "ALLIGATOR_HIGHER_2_BUY_REJECT"
ALLIGATOR_REASON_HIGHER_2_SELL_REJECT = "ALLIGATOR_HIGHER_2_SELL_REJECT"
ALLIGATOR_REASON_HIGHER_2_NOT_READY = "ALLIGATOR_HIGHER_2_NOT_READY"

ALLIGATOR_REASON_DEFERRED_ARMED = "ALLIGATOR_DEFERRED_ARMED"
ALLIGATOR_REASON_DEFERRED_RELEASE = "ALLIGATOR_DEFERRED_RELEASE"
ALLIGATOR_REASON_OPENING_COLLAPSE = "ALLIGATOR_OPENING_COLLAPSE_REJECT"
ALLIGATOR_REASON_WEAK_OPENING = "ALLIGATOR_WEAK_OPENING_REJECT"
ALLIGATOR_REASON_VOLATILITY_SPIKE = (
    "ALLIGATOR_VOLATILITY_SPIKE_DETERIORATION_REJECT"
)
ALLIGATOR_REASON_OVEREXTENDED = "ALLIGATOR_OVEREXTENDED_TREND_REJECT"

ALLIGATOR_DEFERRED_SIGNAL_TYPE = "MACD_DEFERRED_RELEASE"
ALLIGATOR_DEFERRED_SOURCE_REASON_CODE = "MACD_DEFERRED_RELEASE"

CANDIDATE_F_LIFECYCLE_RELEASE = "RELEASE"
CANDIDATE_F_LIFECYCLE_CANCEL = "CANCEL"
CANDIDATE_F_LIFECYCLE_EXPIRE = "EXPIRE"
CANDIDATE_F_LIFECYCLE_REASON_OPPOSITE_MACD = "OPPOSITE_MACD"
CANDIDATE_F_LIFECYCLE_REASON_MACD_INVALID = "MACD_INVALID"
CANDIDATE_F_LIFECYCLE_REASON_OPPOSITE_ACTIVE_ALLIGATOR = "OPPOSITE_ACTIVE_ALLIGATOR"
CANDIDATE_F_LIFECYCLE_REASON_TTL_EXPIRED = "TTL_EXPIRED"


@dataclass(frozen=True, slots=True)
class WorkspaceAlligatorRuntimeProfile:
    """Параметри зафіксованої редакції Alligator."""

    profile_uid: str
    profile_revision: int
    profile_name: str
    source: str
    jaw_period: int
    jaw_shift: int
    teeth_period: int
    teeth_shift: int
    lips_period: int
    lips_shift: int
    ma_type: str
    logic_mode: str
    trend_start_confirmation_bars: int | None
    deferred_expiry_bars: int
    opening_collapse_threshold: float
    volatility_lookback_bars: int
    weak_max_active_age: int
    weak_max_opening: float
    spike_min_range_ratio: float
    spike_max_opening_delta: float
    spike_max_slope_delta: float
    overextended_min_slope: float
    overextended_min_opening: float

    @classmethod
    def from_binding(
        cls,
        binding: WorkspaceIndicatorProfileBinding,
    ) -> WorkspaceAlligatorRuntimeProfile:
        """Побудувати runtime-профіль зі snapshot WSP."""
        if binding.indicator_code != WORKSPACE_INDICATOR_ALLIGATOR:
            raise WorkspaceAlgorithmError(
                "Alligator runtime requires an Alligator profile binding"
            )
        profile = binding.profile
        parameters = profile.parameters
        return cls(
            profile_uid=profile.profile_uid,
            profile_revision=profile.revision,
            profile_name=profile.name,
            source=_normalized_choice(
                parameters.get("source"),
                "Alligator source",
                WORKSPACE_INDICATOR_SOURCES,
            ),
            jaw_period=_positive_integer(
                parameters.get("jaw_period"),
                "jaw_period",
            ),
            jaw_shift=_non_negative_integer(
                parameters.get("jaw_shift"),
                "jaw_shift",
            ),
            teeth_period=_positive_integer(
                parameters.get("teeth_period"),
                "teeth_period",
            ),
            teeth_shift=_non_negative_integer(
                parameters.get("teeth_shift"),
                "teeth_shift",
            ),
            lips_period=_positive_integer(
                parameters.get("lips_period"),
                "lips_period",
            ),
            lips_shift=_non_negative_integer(
                parameters.get("lips_shift"),
                "lips_shift",
            ),
            ma_type=_normalized_choice(
                parameters.get("ma_type"),
                "Alligator ma_type",
                WORKSPACE_INDICATOR_MA_TYPES,
            ),
            logic_mode=_normalized_choice(
                parameters.get("logic_mode", ALLIGATOR_LOGIC_MODE_LEGACY),
                "Alligator logic_mode",
                ALLIGATOR_LOGIC_MODES,
            ),
            trend_start_confirmation_bars=(
                _positive_integer(
                    parameters.get("trend_start_confirmation_bars"),
                    "trend_start_confirmation_bars",
                )
                if "trend_start_confirmation_bars" in parameters
                else None
            ),
            deferred_expiry_bars=_positive_integer(
                parameters.get("deferred_expiry_bars", 5),
                "deferred_expiry_bars",
            ),
            opening_collapse_threshold=_finite_float(
                parameters.get("opening_collapse_threshold", -0.700),
                "opening_collapse_threshold",
            ),
            volatility_lookback_bars=_positive_integer(
                parameters.get("volatility_lookback_bars", 20),
                "volatility_lookback_bars",
            ),
            weak_max_active_age=_non_negative_integer(
                parameters.get("weak_max_active_age", 2),
                "weak_max_active_age",
            ),
            weak_max_opening=_finite_float(
                parameters.get("weak_max_opening", 0.500),
                "weak_max_opening",
            ),
            spike_min_range_ratio=_finite_float(
                parameters.get("spike_min_range_ratio", 3.500),
                "spike_min_range_ratio",
            ),
            spike_max_opening_delta=_finite_float(
                parameters.get("spike_max_opening_delta", -0.500),
                "spike_max_opening_delta",
            ),
            spike_max_slope_delta=_finite_float(
                parameters.get("spike_max_slope_delta", -0.010),
                "spike_max_slope_delta",
            ),
            overextended_min_slope=_finite_float(
                parameters.get("overextended_min_slope", 0.200),
                "overextended_min_slope",
            ),
            overextended_min_opening=_finite_float(
                parameters.get("overextended_min_opening", 3.000),
                "overextended_min_opening",
            ),
        )

    @classmethod
    def lge_default(cls) -> WorkspaceAlligatorRuntimeProfile:
        """Повернути legacy-профіль."""
        profile = built_in_workspace_indicator_profile(
            ALLIGATOR_PROFILE_UID_LGE_CLASSIC
        )
        binding = WorkspaceIndicatorProfileBinding.from_profile(profile)
        return cls.from_binding(binding)

    @property
    def required_bars(self) -> int:
        """Повернути warm-up ліній з урахуванням shifts."""
        return max(
            self.jaw_period + self.jaw_shift,
            self.teeth_period + self.teeth_shift,
            self.lips_period + self.lips_shift,
        )

    @property
    def candidate_f_enabled(self) -> bool:
        """Повернути True лише для зафіксованої Candidate F revision."""
        return self.logic_mode == ALLIGATOR_LOGIC_MODE_CANDIDATE_F

    @property
    def effective_trend_start_confirmation_bars(self) -> int:
        """Повернути profile value або legacy runtime constant."""
        if self.trend_start_confirmation_bars is not None:
            return self.trend_start_confirmation_bars
        return ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS


@dataclass(frozen=True, slots=True)
class WorkspaceAlligatorObservation:
    """Один стан Alligator після завершеного Replay-бару."""

    timestamp: datetime
    median_price: float
    source_value: float
    jaw: float | None
    teeth: float | None
    lips: float | None
    state: str
    regime: str
    regime_phase: str
    center: float | None
    opening: float | None
    center_slope_per_bar: float | None
    range_reference: float | None
    normalized_slope: float | None
    normalized_opening: float | None
    bars_processed: int
    warmed_up: bool
    profile_uid: str
    profile_revision: int
    timeframe: str
    available_at: datetime


@dataclass(frozen=True, slots=True)
class WorkspaceAlligatorDecision:
    """Рішення фільтра для пропозиції сигналу."""

    allowed: bool
    confirmation: str
    reason_code: str
    reason_text: str


@dataclass(slots=True)
class _WorkspaceArmedMacdCandidate:
    """Внутрішній causal MACD-кандидат Candidate F."""

    proposal: WorkspaceSignalProposal
    armed_timestamp: datetime
    bars_waited: int = 0


@dataclass(frozen=True, slots=True)
class WorkspaceDeferredMacdRelease:
    """Факт production deferred release без broker execution."""

    original_signal_timestamp: datetime
    release_timestamp: datetime
    direction: str
    delay_bars: int


@dataclass(frozen=True, slots=True)
class WorkspaceCandidateFLifecycleEvent:
    """Read-only terminal lifecycle evidence Candidate F для UI/Journal."""

    action: str
    original_signal_timestamp: datetime
    event_timestamp: datetime
    direction: str
    reason_code: str
    delay_bars: int
    filter_context: WorkspaceSignalFilterContext | None


class _MovingAverageState:
    """Детермінований стан SMA, EMA або SMMA."""

    def __init__(self, *, period: int, ma_type: str) -> None:
        self.period = _positive_integer(period, "period")
        self.ma_type = _normalized_choice(
            ma_type,
            "ma_type",
            WORKSPACE_INDICATOR_MA_TYPES,
        )
        self._samples: list[float] = []
        self._value: float | None = None

    def reset(self) -> None:
        self._samples = []
        self._value = None

    def update(self, value: float) -> float | None:
        number = _finite_float(value, "moving_average_value")
        if self.ma_type == WORKSPACE_INDICATOR_MA_EXPONENTIAL:
            self._value = _next_ema(number, self._value, self.period)
            return self._value

        self._samples.append(number)
        if len(self._samples) > self.period:
            del self._samples[0]
        if self.ma_type == WORKSPACE_INDICATOR_MA_SIMPLE:
            if len(self._samples) < self.period:
                return None
            self._value = sum(self._samples) / self.period
            return self._value

        if self.ma_type == WORKSPACE_INDICATOR_MA_SMOOTHED:
            if self._value is None:
                if len(self._samples) < self.period:
                    return None
                self._value = sum(self._samples) / self.period
                return self._value
            self._value = (self._value * (self.period - 1) + number) / self.period
            return self._value

        raise WorkspaceAlgorithmError(
            f"Unsupported moving average type: {self.ma_type}"
        )


class WorkspaceAlligatorFilter:
    """Alligator-фільтр із profile snapshot і станом."""

    def __init__(
        self,
        *,
        enabled: bool,
        confirmation_mode: str,
        runtime_profile: WorkspaceAlligatorRuntimeProfile | None = None,
        timeframe: str | None = None,
    ) -> None:
        self.enabled = _strict_bool(enabled, "alligator_filter_enabled")
        self.confirmation_mode = _normalized_choice(
            confirmation_mode,
            "alligator_confirmation",
            WORKSPACE_ALLIGATOR_CONFIRMATIONS,
        )
        self.runtime_profile = (
            runtime_profile or WorkspaceAlligatorRuntimeProfile.lge_default()
        )
        self.timeframe = str(timeframe or "").strip().upper() or None
        self._jaw_average = _MovingAverageState(
            period=self.runtime_profile.jaw_period,
            ma_type=self.runtime_profile.ma_type,
        )
        self._teeth_average = _MovingAverageState(
            period=self.runtime_profile.teeth_period,
            ma_type=self.runtime_profile.ma_type,
        )
        self._lips_average = _MovingAverageState(
            period=self.runtime_profile.lips_period,
            ma_type=self.runtime_profile.ma_type,
        )
        self._bars_processed = 0
        self._jaw_history: list[float | None] = []
        self._teeth_history: list[float | None] = []
        self._lips_history: list[float | None] = []
        self._center_history: list[float | None] = []
        self._bar_range_history: list[float] = []
        self._raw_regime_history: list[str] = []
        self._last_timestamp: datetime | None = None
        self._observations: list[WorkspaceAlligatorObservation] = []

    @classmethod
    def from_parameters(
        cls,
        parameters: Mapping[str, Any],
    ) -> WorkspaceAlligatorFilter:
        """Побудувати legacy-фільтр з LGE default profile."""
        return cls(
            enabled=parameters.get(
                WORKSPACE_ALLIGATOR_FILTER_ENABLED_KEY,
                DEFAULT_WORKSPACE_ALLIGATOR_FILTER_ENABLED,
            ),
            confirmation_mode=parameters.get(
                "alligator_confirmation",
                DEFAULT_WORKSPACE_ALLIGATOR_CONFIRMATION,
            ),
        )

    @classmethod
    def from_runtime_context(
        cls,
        context: WorkspaceRuntimeContext,
        parameters: Mapping[str, Any],
    ) -> WorkspaceAlligatorFilter:
        """Побудувати Alligator зі snapshot профілю WSP."""
        binding = workspace_indicator_profile_binding(
            context,
            WORKSPACE_INDICATOR_ALLIGATOR,
        )
        runtime_profile = WorkspaceAlligatorRuntimeProfile.from_binding(binding)
        confirmation_mode = parameters.get(
            "alligator_confirmation",
            DEFAULT_WORKSPACE_ALLIGATOR_CONFIRMATION,
        )
        enabled = _strict_bool(
            parameters.get(
                WORKSPACE_ALLIGATOR_FILTER_ENABLED_KEY,
                DEFAULT_WORKSPACE_ALLIGATOR_FILTER_ENABLED,
            ),
            WORKSPACE_ALLIGATOR_FILTER_ENABLED_KEY,
        )
        if enabled:
            timeframe = resolve_alligator_confirmation_timeframe(
                context.timeframe,
                str(confirmation_mode),
            )
        else:
            # Inactive filters must not fail on a stale unavailable mode.
            timeframe = context.timeframe
        return cls(
            enabled=enabled,
            confirmation_mode=confirmation_mode,
            runtime_profile=runtime_profile,
            timeframe=timeframe,
        )

    @property
    def active(self) -> bool:
        return bool(
            self.enabled
            and self.confirmation_mode != WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED
        )

    @property
    def required_bars(self) -> int:
        """Повернути потребу активного Alligator timeframe."""
        if not self.active:
            return 0
        self.validate_runtime_mode()
        return self.runtime_profile.required_bars

    @property
    def profile_uid(self) -> str:
        return self.runtime_profile.profile_uid

    @property
    def profile_revision(self) -> int:
        return self.runtime_profile.profile_revision

    @property
    def observations(self) -> tuple[WorkspaceAlligatorObservation, ...]:
        return tuple(self._observations)

    @property
    def latest_observation(self) -> WorkspaceAlligatorObservation | None:
        if not self._observations:
            return None
        return self._observations[-1]

    def diagnostic_observation_history(
        self,
        observation: WorkspaceAlligatorObservation,
        *,
        limit: int = 3,
    ) -> tuple[WorkspaceAlligatorObservation, ...]:
        """Повернути causal history до вказаного observation включно.

        Метод призначений лише для Journal/test diagnostics. Він не змінює
        regime, phase або чинний ALLOW/REJECT trade gate. Пошук іде тільки
        серед уже завершених спостережень Alligator.
        """
        if limit <= 0 or not self._observations:
            return ()
        end_index: int | None = None
        for index in range(len(self._observations) - 1, -1, -1):
            candidate = self._observations[index]
            if candidate.timestamp == observation.timestamp:
                end_index = index + 1
                break
        if end_index is None:
            return ()
        start_index = max(0, end_index - limit)
        return tuple(self._observations[start_index:end_index])

    def observation_available_at(
        self,
        timestamp: datetime,
    ) -> WorkspaceAlligatorObservation | None:
        """Return the newest observation causally available at timestamp."""
        if not self._observations:
            return None
        low = 0
        high = len(self._observations)
        while low < high:
            middle = (low + high) // 2
            if self._observations[middle].available_at <= timestamp:
                low = middle + 1
            else:
                high = middle
        index = low - 1
        if index < 0:
            return None
        return self._observations[index]

    def validate_runtime_mode(self) -> None:
        """Дозволити SAME_TIMEFRAME та явні старші timeframe."""
        if self.confirmation_mode not in {
            WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
            WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_1,
            WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2,
            WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED,
        }:
            raise WorkspaceAlgorithmError(
                f"Unsupported Alligator mode: {self.confirmation_mode}"
            )
        if (
            self.active
            and self.timeframe is None
            and self.confirmation_mode
            in {
                WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_1,
                WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2,
            }
        ):
            raise WorkspaceAlgorithmError(
                f"Alligator {self.confirmation_mode} requires resolved "
                "workspace timeframe"
            )

    def reset(self) -> None:
        """Очистити розрахунковий стан у пам'яті."""
        self._jaw_average.reset()
        self._teeth_average.reset()
        self._lips_average.reset()
        self._bars_processed = 0
        self._jaw_history = []
        self._teeth_history = []
        self._lips_history = []
        self._center_history = []
        self._bar_range_history = []
        self._raw_regime_history = []
        self._last_timestamp = None
        self._observations = []

    def on_market_event(
        self,
        event: WorkspaceMarketEvent,
        *,
        available_at: datetime | None = None,
    ) -> WorkspaceAlligatorObservation:
        """Оновити Alligator завершеним causal Replay-bar."""
        effective_available_at = available_at or event.timestamp
        if effective_available_at < event.timestamp:
            raise WorkspaceAlgorithmError(
                "Alligator observation cannot be available before its bar"
            )
        if self.timeframe is not None and event.timeframe != self.timeframe:
            raise WorkspaceAlgorithmError(
                f"Alligator expected {self.timeframe}, got {event.timeframe}"
            )

        high = _finite_float(event.high, "high")
        low = _finite_float(event.low, "low")
        median_price = (high + low) / 2.0
        source_value = _market_source_value(
            event,
            self.runtime_profile.source,
        )
        if not self.active:
            observation = WorkspaceAlligatorObservation(
                timestamp=event.timestamp,
                median_price=median_price,
                source_value=source_value,
                jaw=None,
                teeth=None,
                lips=None,
                state=ALLIGATOR_STATE_DISABLED,
                regime=ALLIGATOR_REGIME_DISABLED,
                regime_phase=ALLIGATOR_REGIME_PHASE_NONE,
                center=None,
                opening=None,
                center_slope_per_bar=None,
                range_reference=None,
                normalized_slope=None,
                normalized_opening=None,
                bars_processed=self._bars_processed,
                warmed_up=True,
                profile_uid=self.profile_uid,
                profile_revision=self.profile_revision,
                timeframe=event.timeframe,
                available_at=effective_available_at,
            )
            self._observations.append(observation)
            return observation

        self.validate_runtime_mode()
        if event.source_mode != WORKSPACE_DATA_MODE_REPLAY:
            raise WorkspaceAlgorithmError(
                "Alligator runtime currently supports Replay only"
            )
        if self._last_timestamp is not None:
            if event.timestamp <= self._last_timestamp:
                raise WorkspaceAlgorithmError(
                    "Alligator Replay bars must be strictly ordered and unique"
                )
        self._last_timestamp = event.timestamp

        self._bars_processed += 1
        self._bar_range_history.append(high - low)
        self._jaw_history.append(self._jaw_average.update(source_value))
        self._teeth_history.append(self._teeth_average.update(source_value))
        self._lips_history.append(self._lips_average.update(source_value))

        jaw = _shifted_value(
            self._jaw_history,
            self.runtime_profile.jaw_shift,
        )
        teeth = _shifted_value(
            self._teeth_history,
            self.runtime_profile.teeth_shift,
        )
        lips = _shifted_value(
            self._lips_history,
            self.runtime_profile.lips_shift,
        )
        warmed_up = bool(
            self._bars_processed >= self.required_bars
            and jaw is not None
            and teeth is not None
            and lips is not None
        )
        state = _alligator_state(
            jaw,
            teeth,
            lips,
            warmed_up=warmed_up,
        )
        (
            raw_regime,
            center,
            opening,
            center_slope_per_bar,
            range_reference,
            normalized_slope,
            normalized_opening,
        ) = _alligator_regime_diagnostics(
            jaw,
            teeth,
            lips,
            center_history=self._center_history,
            bar_range_history=self._bar_range_history,
            warmed_up=warmed_up,
        )
        previous_observation = self.latest_observation
        regime = _alligator_regime_with_flat_hysteresis(
            raw_regime,
            raw_regime_history=self._raw_regime_history,
            previous_observation=previous_observation,
        )
        if raw_regime == ALLIGATOR_REGIME_FLAT and regime != raw_regime:
            regime_phase = ALLIGATOR_REGIME_PHASE_ENDING
        else:
            regime_phase = _alligator_regime_phase(
                regime,
                state,
                observation_history=self._observations,
                confirmation_bars=(
                    self.runtime_profile.effective_trend_start_confirmation_bars
                ),
            )
        self._raw_regime_history.append(raw_regime)
        self._center_history.append(center)
        observation = WorkspaceAlligatorObservation(
            timestamp=event.timestamp,
            median_price=median_price,
            source_value=source_value,
            jaw=jaw,
            teeth=teeth,
            lips=lips,
            state=state,
            regime=regime,
            regime_phase=regime_phase,
            center=center,
            opening=opening,
            center_slope_per_bar=center_slope_per_bar,
            range_reference=range_reference,
            normalized_slope=normalized_slope,
            normalized_opening=normalized_opening,
            bars_processed=self._bars_processed,
            warmed_up=warmed_up,
            profile_uid=self.profile_uid,
            profile_revision=self.profile_revision,
            timeframe=event.timeframe,
            available_at=effective_available_at,
        )
        self._observations.append(observation)
        return observation

    def evaluate(
        self,
        proposal: WorkspaceSignalProposal,
        observation: WorkspaceAlligatorObservation | None,
        *,
        proposal_timestamp: datetime | None = None,
    ) -> WorkspaceAlligatorDecision:
        """Оцінити MACD-пропозицію без торгівлі."""
        if not self.active:
            return WorkspaceAlligatorDecision(
                allowed=True,
                confirmation=ALLIGATOR_CONFIRMATION_DISABLED,
                reason_code=ALLIGATOR_REASON_DISABLED_BYPASS,
                reason_text="Alligator filter is disabled.",
            )

        self.validate_runtime_mode()
        if observation is None:
            return self._not_ready_decision()
        if observation.timestamp != self._last_timestamp:
            raise WorkspaceAlgorithmError(
                "Alligator decision requires the latest observation"
            )
        if (
            proposal_timestamp is not None
            and observation.available_at > proposal_timestamp
        ):
            raise WorkspaceAlgorithmError(
                "Alligator observation contains future higher-timeframe data"
            )
        if not observation.warmed_up:
            return self._not_ready_decision()

        direction = proposal.direction
        if direction not in {"BUY", "SELL"}:
            raise WorkspaceAlgorithmError(
                f"Alligator cannot evaluate direction: {direction}"
            )

        confirmation = _confirmation_for_state(
            observation.state,
            self.confirmation_mode,
        )
        if self.confirmation_mode == WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME:
            phase_reject = _same_timeframe_phase_reject_decision(
                direction,
                observation,
                confirmation=confirmation,
            )
            if phase_reject is not None:
                return phase_reject

        if direction == "BUY":
            allowed = observation.state == ALLIGATOR_STATE_BULLISH
        else:
            allowed = observation.state == ALLIGATOR_STATE_BEARISH
        return WorkspaceAlligatorDecision(
            allowed=allowed,
            confirmation=confirmation,
            reason_code=_decision_reason_code(
                self.confirmation_mode,
                direction,
                allowed,
            ),
            reason_text=_decision_reason_text(
                self.confirmation_mode,
                direction,
                allowed,
                observation.timeframe,
            ),
        )

    def _not_ready_decision(self) -> WorkspaceAlligatorDecision:
        mode = self.confirmation_mode
        if mode == WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_1:
            confirmation = ALLIGATOR_CONFIRMATION_HIGHER_1_WARMUP
            reason_code = ALLIGATOR_REASON_HIGHER_1_NOT_READY
            reason_text = "Higher-timeframe Alligator warm-up is incomplete."
        elif mode == WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2:
            confirmation = ALLIGATOR_CONFIRMATION_HIGHER_2_WARMUP
            reason_code = ALLIGATOR_REASON_HIGHER_2_NOT_READY
            reason_text = "Second higher-timeframe Alligator warm-up is incomplete."
        else:
            confirmation = ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME_WARMUP
            reason_code = ALLIGATOR_REASON_NOT_READY
            reason_text = "Alligator warm-up is incomplete."
        return WorkspaceAlligatorDecision(
            allowed=False,
            confirmation=confirmation,
            reason_code=reason_code,
            reason_text=reason_text,
        )


class WorkspaceMacdAlligatorReplayAlgorithm(WorkspaceAlgorithm):
    """MACD на WSP timeframe з causal Alligator SAME/HIGHER_1/HIGHER_2."""

    def __init__(self, algorithm_id: str = "MACD_ALLIGATOR_REPLAY") -> None:
        self.algorithm_id = str(algorithm_id or "").strip()
        if not self.algorithm_id:
            self.algorithm_id = "MACD_ALLIGATOR_REPLAY"
        self.context: WorkspaceRuntimeContext | None = None
        self.parameters: dict[str, Any] = {}
        self.source: WorkspaceMacdSignalSource | None = None
        self.signal_filter: WorkspaceAlligatorFilter | None = None
        self.timeframe_aggregator: WorkspaceTimeframeAggregator | None = None
        self._higher_timeframe_synchronized = True
        self._armed_candidate: _WorkspaceArmedMacdCandidate | None = None
        self._candidate_prior_ranges: list[float] = []
        self.deferred_releases: list[WorkspaceDeferredMacdRelease] = []
        self.deferred_cancelled_opposite_cross = 0
        self.deferred_cancelled_opposite_alligator = 0
        self.deferred_cancelled_macd_invalid = 0
        self.deferred_expired = 0
        self._candidate_f_lifecycle_events: list[
            WorkspaceCandidateFLifecycleEvent
        ] = []
        self.started = False

    def configure(
        self,
        context: WorkspaceRuntimeContext,
        parameters: Mapping[str, Any],
    ) -> None:
        self.context = context
        self.parameters = dict(parameters)
        self.source = WorkspaceMacdSignalSource.from_runtime_context(
            context,
            parameters,
        )
        self.signal_filter = WorkspaceAlligatorFilter.from_runtime_context(
            context,
            parameters,
        )
        self.timeframe_aggregator = None
        self._higher_timeframe_synchronized = True
        if self.signal_filter.active:
            self.signal_filter.validate_runtime_mode()
            _ = self.signal_filter.required_bars
            if self.signal_filter.confirmation_mode in {
                WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_1,
                WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2,
            }:
                target_timeframe = self.signal_filter.timeframe
                if target_timeframe is None:
                    raise WorkspaceAlgorithmError(
                        "Alligator higher timeframe was not resolved"
                    )
                self.timeframe_aggregator = WorkspaceTimeframeAggregator(
                    source_timeframe=context.timeframe,
                    target_timeframe=target_timeframe,
                )
                self._higher_timeframe_synchronized = False

    @property
    def higher_timeframe_synchronized(self) -> bool:
        return self._higher_timeframe_synchronized

    def warmup_requirements(
        self,
    ) -> tuple[WorkspaceWarmupRequirement, ...] | None:
        source = self.source
        signal_filter = self.signal_filter
        if source is None or signal_filter is None:
            raise WorkspaceAlgorithmError("MACD Alligator algorithm is not configured")
        timeframe = str(getattr(self.context, "timeframe", "")).strip()
        requirements: list[WorkspaceWarmupRequirement] = []
        if source.enabled:
            requirements.append(
                WorkspaceWarmupRequirement(
                    component_code=MACD_COMPONENT_CODE,
                    timeframe=timeframe,
                    required_bars=source.required_bars,
                )
            )
        if signal_filter.active:
            filter_timeframe = signal_filter.timeframe or timeframe
            requirements.append(
                WorkspaceWarmupRequirement(
                    component_code=ALLIGATOR_COMPONENT_CODE,
                    timeframe=filter_timeframe,
                    required_bars=signal_filter.required_bars,
                )
            )
        return tuple(requirements)

    def start(self) -> None:
        source = self.source
        signal_filter = self.signal_filter
        if self.context is None or source is None or signal_filter is None:
            raise WorkspaceAlgorithmError("MACD Alligator algorithm is not configured")
        source.reset()
        signal_filter.reset()
        if self.timeframe_aggregator is not None:
            self.timeframe_aggregator.reset()
            self._higher_timeframe_synchronized = False
        else:
            self._higher_timeframe_synchronized = True
        self._armed_candidate = None
        self._candidate_prior_ranges = []
        self.deferred_releases = []
        self.deferred_cancelled_opposite_cross = 0
        self.deferred_cancelled_opposite_alligator = 0
        self.deferred_cancelled_macd_invalid = 0
        self.deferred_expired = 0
        self._candidate_f_lifecycle_events = []
        self.started = True

    def on_market_event(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalOutput:
        base_output = self._base_signal_output(event)
        if not self._candidate_f_active():
            return base_output
        return self._candidate_f_output(event, base_output)

    def drain_candidate_f_lifecycle_events(
        self,
    ) -> tuple[WorkspaceCandidateFLifecycleEvent, ...]:
        """Віддати нові terminal lifecycle events рівно один раз.

        Виклик не змінює trade gate. Очищається лише diagnostic
        queue.
        """
        events = tuple(self._candidate_f_lifecycle_events)
        self._candidate_f_lifecycle_events = []
        return events

    def _record_candidate_f_terminal_event(
        self,
        *,
        action: str,
        reason_code: str,
        event: WorkspaceMarketEvent,
        armed: _WorkspaceArmedMacdCandidate,
    ) -> None:
        """Зберегти causal terminal evidence без зміни trade gate.

        Evidence містить тільки завершені observation, доступні
        на event time.
        """
        signal_filter = self.signal_filter
        observation = (
            signal_filter.latest_observation
            if signal_filter is not None
            else None
        )
        filter_context = (
            _workspace_alligator_filter_context(
                signal_filter,
                observation,
                event,
                direction=armed.proposal.direction,
            )
            if signal_filter is not None and observation is not None
            else armed.proposal.filter_context
        )
        self._candidate_f_lifecycle_events.append(
            WorkspaceCandidateFLifecycleEvent(
                action=action,
                original_signal_timestamp=armed.armed_timestamp,
                event_timestamp=event.timestamp,
                direction=armed.proposal.direction,
                reason_code=reason_code,
                delay_bars=armed.bars_waited,
                filter_context=filter_context,
            )
        )

    def _base_signal_output(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalOutput:
        """Виконати legacy MACD→Alligator рішення для одного bar."""
        source = self.source
        signal_filter = self.signal_filter
        if not self.started or source is None or signal_filter is None:
            raise WorkspaceAlgorithmError("MACD Alligator algorithm is not started")

        observation = self._update_alligator(event)
        proposal = source.on_market_event(event)
        if proposal is None:
            return None
        if proposal.filter_decision == WORKSPACE_SIGNAL_FILTER_REJECT:
            # RoadMap99: rejected MACD quality candidates stop before Alligator.
            return proposal

        decision = signal_filter.evaluate(
            proposal,
            observation,
            proposal_timestamp=event.timestamp,
        )
        filter_decision = (
            WORKSPACE_SIGNAL_FILTER_ALLOW
            if decision.allowed
            else WORKSPACE_SIGNAL_FILTER_REJECT
        )
        reason_parts = [part for part in (proposal.reason,) if part]
        reason_parts.append(f"{decision.reason_code}: {decision.reason_text}")
        reason_parts.append(f"alligator_profile_uid={signal_filter.profile_uid}")
        reason_parts.append(
            f"alligator_profile_revision={signal_filter.profile_revision}"
        )
        reason_parts.append(
            f"alligator_confirmation_mode={signal_filter.confirmation_mode}"
        )
        reason_parts.append(
            f"alligator_timeframe={signal_filter.timeframe or event.timeframe}"
        )
        if observation is not None:
            reason_parts.append(
                "alligator_observation_timestamp="
                f"{observation.timestamp.isoformat()}"
            )
            reason_parts.append(
                f"alligator_available_at={observation.available_at.isoformat()}"
            )
            reason_parts.append(f"alligator_state={observation.state}")
            reason_parts.append(f"alligator_regime={observation.regime}")
            reason_parts.append(f"alligator_regime_phase={observation.regime_phase}")
            if observation.center_slope_per_bar is not None:
                reason_parts.append(
                    "alligator_center_slope_per_bar="
                    f"{observation.center_slope_per_bar:.10f}"
                )
            if observation.normalized_slope is not None:
                reason_parts.append(
                    "alligator_normalized_slope=" f"{observation.normalized_slope:.6f}"
                )
            if observation.opening is not None:
                reason_parts.append(f"alligator_opening={observation.opening:.10f}")
            if observation.normalized_opening is not None:
                reason_parts.append(
                    "alligator_normalized_opening="
                    f"{observation.normalized_opening:.6f}"
                )
            diagnostic_history = signal_filter.diagnostic_observation_history(
                observation,
                limit=3,
            )
            previous_observations = tuple(reversed(diagnostic_history[:-1]))
            for offset, previous in enumerate(previous_observations, start=1):
                prefix = f"alligator_prev{offset}"
                reason_parts.append(
                    f"{prefix}_observation_timestamp={previous.timestamp.isoformat()}"
                )
                reason_parts.append(f"{prefix}_state={previous.state}")
                reason_parts.append(f"{prefix}_regime={previous.regime}")
                reason_parts.append(f"{prefix}_regime_phase={previous.regime_phase}")
                if previous.normalized_slope is not None:
                    reason_parts.append(
                        f"{prefix}_normalized_slope=" f"{previous.normalized_slope:.6f}"
                    )
                if previous.normalized_opening is not None:
                    reason_parts.append(
                        f"{prefix}_normalized_opening="
                        f"{previous.normalized_opening:.6f}"
                    )
        filter_context = (
            _workspace_alligator_filter_context(
                signal_filter,
                observation,
                event,
                direction=proposal.direction,
            )
            if observation is not None
            else WorkspaceSignalFilterContext(
                mode=signal_filter.confirmation_mode,
                timeframe=signal_filter.timeframe or event.timeframe,
                profile_uid=signal_filter.profile_uid,
                profile_revision=signal_filter.profile_revision,
            )
        )
        return replace(
            proposal,
            alligator_confirmation=decision.confirmation,
            reason="; ".join(reason_parts),
            filter_decision=filter_decision,
            filter_reason_code=decision.reason_code,
            filter_context=filter_context,
        )

    def _candidate_f_active(self) -> bool:
        """Повернути True лише для SAME_TIMEFRAME Candidate F profile."""
        signal_filter = self.signal_filter
        return bool(
            signal_filter is not None
            and signal_filter.confirmation_mode
            == WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME
            and signal_filter.runtime_profile.candidate_f_enabled
        )

    def _candidate_f_output(
        self,
        event: WorkspaceMarketEvent,
        base_output: WorkspaceSignalOutput,
    ) -> WorkspaceSignalOutput:
        """Застосувати production Candidate F після legacy phase decision."""
        base_proposals = _workspace_signal_output_tuple(base_output)
        deferred = self._advance_armed_candidate(event, base_proposals)
        base_proposals = self._arm_from_base_proposals(event, base_proposals)
        proposals = list(base_proposals)
        if deferred is not None:
            proposals.append(deferred)

        prior_range = self._candidate_prior_range()
        guarded = self._apply_candidate_f_guards(
            tuple(proposals),
            event,
            prior_range,
        )
        event_range = float(event.high - event.low)
        if event_range > 0.0:
            self._candidate_prior_ranges.append(event_range)
        return _restore_workspace_signal_output_shape(base_output, guarded)

    def _candidate_prior_range(self) -> float | None:
        signal_filter = self.signal_filter
        if signal_filter is None:
            return None
        lookback = signal_filter.runtime_profile.volatility_lookback_bars
        if len(self._candidate_prior_ranges) < lookback:
            return None
        values = self._candidate_prior_ranges[-lookback:]
        return sum(values) / float(lookback)

    def _arm_from_base_proposals(
        self,
        event: WorkspaceMarketEvent,
        proposals: tuple[WorkspaceSignalProposal, ...],
    ) -> tuple[WorkspaceSignalProposal, ...]:
        """Зафіксувати один STARTING candidate і зробити причину видимою."""
        result: list[WorkspaceSignalProposal] = []
        for proposal in proposals:
            if not _candidate_f_armable(proposal):
                result.append(proposal)
                continue
            if self._armed_candidate is None:
                self._armed_candidate = _WorkspaceArmedMacdCandidate(
                    proposal=proposal,
                    armed_timestamp=event.timestamp,
                )
                result.append(
                    replace(
                        proposal,
                        filter_reason_code=ALLIGATOR_REASON_DEFERRED_ARMED,
                        reason=(
                            f"{proposal.reason}; "
                            f"{ALLIGATOR_REASON_DEFERRED_ARMED}: "
                            "quality MACD is armed while Alligator is starting"
                        ).strip("; "),
                    )
                )
                continue
            result.append(proposal)
        return tuple(result)

    def _advance_armed_candidate(
        self,
        event: WorkspaceMarketEvent,
        base_proposals: tuple[WorkspaceSignalProposal, ...],
    ) -> WorkspaceSignalProposal | None:
        """Просунути causal ARMED lifecycle одним завершеним bar."""
        armed = self._armed_candidate
        if armed is None or event.timestamp <= armed.armed_timestamp:
            return None
        armed.bars_waited += 1

        if any(
            proposal.signal_type == "MACD_CROSS"
            and proposal.direction != armed.proposal.direction
            for proposal in base_proposals
        ):
            self.deferred_cancelled_opposite_cross += 1
            self._record_candidate_f_terminal_event(
                action=CANDIDATE_F_LIFECYCLE_CANCEL,
                reason_code=CANDIDATE_F_LIFECYCLE_REASON_OPPOSITE_MACD,
                event=event,
                armed=armed,
            )
            self._armed_candidate = None
            return None

        source = self.source
        signal_filter = self.signal_filter
        if source is None or signal_filter is None or not source.observations:
            self.deferred_cancelled_macd_invalid += 1
            self._record_candidate_f_terminal_event(
                action=CANDIDATE_F_LIFECYCLE_CANCEL,
                reason_code=CANDIDATE_F_LIFECYCLE_REASON_MACD_INVALID,
                event=event,
                armed=armed,
            )
            self._armed_candidate = None
            return None
        macd_observation = source.observations[-1]
        if not _candidate_f_macd_relation_matches(
            macd_observation.histogram,
            armed.proposal.direction,
        ):
            self.deferred_cancelled_macd_invalid += 1
            self._record_candidate_f_terminal_event(
                action=CANDIDATE_F_LIFECYCLE_CANCEL,
                reason_code=CANDIDATE_F_LIFECYCLE_REASON_MACD_INVALID,
                event=event,
                armed=armed,
            )
            self._armed_candidate = None
            return None

        observation = signal_filter.latest_observation
        if _candidate_f_active_opposite(observation, armed.proposal.direction):
            self.deferred_cancelled_opposite_alligator += 1
            self._record_candidate_f_terminal_event(
                action=CANDIDATE_F_LIFECYCLE_CANCEL,
                reason_code=CANDIDATE_F_LIFECYCLE_REASON_OPPOSITE_ACTIVE_ALLIGATOR,
                event=event,
                armed=armed,
            )
            self._armed_candidate = None
            return None

        if _candidate_f_active_matches(observation, armed.proposal.direction):
            decision = signal_filter.evaluate(
                armed.proposal,
                observation,
                proposal_timestamp=event.timestamp,
            )
            if not decision.allowed or observation is None:
                return None
            release = replace(
                armed.proposal,
                signal_type=ALLIGATOR_DEFERRED_SIGNAL_TYPE,
                strength=abs(float(macd_observation.histogram or 0.0)),
                macd_state=macd_observation.state,
                alligator_confirmation=decision.confirmation,
                reason=(
                    f"{ALLIGATOR_REASON_DEFERRED_RELEASE}: "
                    f"original_signal_timestamp={armed.armed_timestamp.isoformat()}; "
                    f"delay_bars={armed.bars_waited}; "
                    f"{decision.reason_code}: {decision.reason_text}"
                ),
                source_reason_code=ALLIGATOR_DEFERRED_SOURCE_REASON_CODE,
                filter_decision=WORKSPACE_SIGNAL_FILTER_ALLOW,
                filter_reason_code=ALLIGATOR_REASON_DEFERRED_RELEASE,
                filter_context=_workspace_alligator_filter_context(
                    signal_filter,
                    observation,
                    event,
                    direction=armed.proposal.direction,
                ),
            )
            self.deferred_releases.append(
                WorkspaceDeferredMacdRelease(
                    original_signal_timestamp=armed.armed_timestamp,
                    release_timestamp=event.timestamp,
                    direction=armed.proposal.direction,
                    delay_bars=armed.bars_waited,
                )
            )
            self._record_candidate_f_terminal_event(
                action=CANDIDATE_F_LIFECYCLE_RELEASE,
                reason_code=ALLIGATOR_REASON_DEFERRED_RELEASE,
                event=event,
                armed=armed,
            )
            self._armed_candidate = None
            return release

        expiry = signal_filter.runtime_profile.deferred_expiry_bars
        if armed.bars_waited >= expiry:
            self.deferred_expired += 1
            self._record_candidate_f_terminal_event(
                action=CANDIDATE_F_LIFECYCLE_EXPIRE,
                reason_code=CANDIDATE_F_LIFECYCLE_REASON_TTL_EXPIRED,
                event=event,
                armed=armed,
            )
            self._armed_candidate = None
        return None

    def _apply_candidate_f_guards(
        self,
        proposals: tuple[WorkspaceSignalProposal, ...],
        event: WorkspaceMarketEvent,
        prior_range: float | None,
    ) -> tuple[WorkspaceSignalProposal, ...]:
        """Застосувати collapse і structural guards лише до ALLOW proposals."""
        if not proposals:
            return proposals
        signal_filter = self.signal_filter
        if signal_filter is None:
            return proposals
        current = signal_filter.latest_observation
        if (
            current is None
            or current.regime_phase != ALLIGATOR_REGIME_PHASE_ACTIVE
            or current.normalized_slope is None
            or current.normalized_opening is None
        ):
            return proposals
        history = signal_filter.diagnostic_observation_history(current, limit=3)
        if len(history) < 3:
            return proposals
        oldest = history[0]
        if oldest.normalized_slope is None or oldest.normalized_opening is None:
            return proposals

        profile = signal_filter.runtime_profile
        slope = float(current.normalized_slope)
        opening = float(current.normalized_opening)
        slope_delta = float(slope - oldest.normalized_slope)
        opening_delta = float(opening - oldest.normalized_opening)

        collapsed: list[WorkspaceSignalProposal] = []
        for proposal in proposals:
            if (
                proposal.filter_decision == WORKSPACE_SIGNAL_FILTER_ALLOW
                and opening_delta < profile.opening_collapse_threshold
            ):
                collapsed.append(
                    _candidate_f_reject(
                        proposal,
                        ALLIGATOR_REASON_OPENING_COLLAPSE,
                        (
                            f"opening_delta_t2_t={opening_delta:.6f}; "
                            "threshold="
                            f"{profile.opening_collapse_threshold:.3f}"
                        ),
                    )
                )
            else:
                collapsed.append(proposal)

        if prior_range is None or prior_range <= 0.0:
            return tuple(collapsed)
        signal_range = float(event.high - event.low)
        if signal_range <= 0.0:
            return tuple(collapsed)
        range_ratio = signal_range / prior_range

        guarded: list[WorkspaceSignalProposal] = []
        for proposal in collapsed:
            if proposal.filter_decision != WORKSPACE_SIGNAL_FILTER_ALLOW:
                guarded.append(proposal)
                continue
            active_age = _candidate_f_active_age(
                signal_filter.observations,
                proposal.direction,
            )
            reason_code = _candidate_f_structural_reason(
                profile,
                active_age=active_age,
                slope=slope,
                opening=opening,
                slope_delta=slope_delta,
                opening_delta=opening_delta,
                range_ratio=range_ratio,
            )
            if reason_code is None:
                guarded.append(proposal)
                continue
            guarded.append(
                _candidate_f_reject(
                    proposal,
                    reason_code,
                    (
                        f"active_age={active_age}; opening={opening:.6f}; "
                        f"opening_delta={opening_delta:+.6f}; "
                        f"slope={slope:.6f}; slope_delta={slope_delta:+.6f}; "
                        f"range_ratio={range_ratio:.3f}"
                    ),
                )
            )
        return tuple(guarded)

    def _update_alligator(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceAlligatorObservation | None:
        signal_filter = self.signal_filter
        if signal_filter is None:
            raise WorkspaceAlgorithmError("MACD Alligator algorithm is not configured")
        aggregator = self.timeframe_aggregator
        if aggregator is None:
            return signal_filter.on_market_event(event)

        completed = aggregator.on_market_event(event)
        observation = signal_filter.latest_observation
        if completed is not None:
            observation = signal_filter.on_market_event(
                completed.event,
                available_at=completed.completed_at,
            )
        if aggregator.last_boundary_was_incomplete:
            self._higher_timeframe_synchronized = False
            return None
        if completed is not None:
            self._higher_timeframe_synchronized = True
        if not self._higher_timeframe_synchronized:
            return None
        return observation

    def chart_series(
        self,
        timestamps: tuple[datetime, ...],
    ) -> tuple[WorkspaceChartSeries, ...]:
        """Expose factual MACD and Alligator series for visible chart bars."""
        return self._macd_chart_series(timestamps) + self._alligator_chart_series(
            timestamps
        )

    def _macd_chart_series(
        self,
        timestamps: tuple[datetime, ...],
    ) -> tuple[WorkspaceChartSeries, ...]:
        source = self.source
        context = self.context
        if source is None or context is None or not source.enabled or not timestamps:
            return ()

        observations = {
            observation.timestamp: observation for observation in source.observations
        }
        point_lists: dict[str, list[WorkspaceChartSeriesPoint]] = {
            "MACD_VALUE": [],
            "MACD_SIGNAL": [],
            "MACD_HISTOGRAM": [],
        }
        for timestamp in timestamps:
            observation = observations.get(timestamp)
            if observation is None:
                continue
            values = (
                ("MACD_VALUE", observation.macd_value),
                ("MACD_SIGNAL", observation.signal_value),
                ("MACD_HISTOGRAM", observation.histogram),
            )
            for series_code, value in values:
                if value is None:
                    continue
                point_lists[series_code].append(
                    WorkspaceChartSeriesPoint(
                        timestamp=timestamp,
                        value=float(value),
                        source_timestamp=observation.timestamp,
                        available_at=observation.timestamp,
                    )
                )

        specs = (
            ("MACD_VALUE", WORKSPACE_CHART_ROLE_INDICATOR_LINE, "MACD"),
            ("MACD_SIGNAL", WORKSPACE_CHART_ROLE_INDICATOR_LINE, "Signal"),
            (
                "MACD_HISTOGRAM",
                WORKSPACE_CHART_ROLE_INDICATOR_HISTOGRAM,
                "Histogram",
            ),
        )
        result: list[WorkspaceChartSeries] = []
        for series_code, role, label in specs:
            points = tuple(point_lists[series_code])
            if not points:
                continue
            result.append(
                WorkspaceChartSeries(
                    series_code=series_code,
                    role=role,
                    label=label,
                    timeframe=context.timeframe,
                    profile_uid=source.profile_uid,
                    profile_revision=source.profile_revision,
                    points=points,
                )
            )
        return tuple(result)

    def _alligator_chart_series(
        self,
        timestamps: tuple[datetime, ...],
    ) -> tuple[WorkspaceChartSeries, ...]:
        signal_filter = self.signal_filter
        context = self.context
        if (
            signal_filter is None
            or context is None
            or not signal_filter.active
            or not timestamps
        ):
            return ()

        point_lists: dict[str, list[WorkspaceChartSeriesPoint]] = {
            "ALLIGATOR_JAW": [],
            "ALLIGATOR_TEETH": [],
            "ALLIGATOR_LIPS": [],
        }
        for timestamp in timestamps:
            observation = signal_filter.observation_available_at(timestamp)
            if observation is None:
                continue
            values = (
                ("ALLIGATOR_JAW", observation.jaw),
                ("ALLIGATOR_TEETH", observation.teeth),
                ("ALLIGATOR_LIPS", observation.lips),
            )
            for series_code, value in values:
                if value is None:
                    continue
                point_lists[series_code].append(
                    WorkspaceChartSeriesPoint(
                        timestamp=timestamp,
                        value=float(value),
                        source_timestamp=observation.timestamp,
                        available_at=observation.available_at,
                    )
                )

        timeframe = signal_filter.timeframe or context.timeframe
        series_specs = (
            ("ALLIGATOR_JAW", "Jaw"),
            ("ALLIGATOR_TEETH", "Teeth"),
            ("ALLIGATOR_LIPS", "Lips"),
        )
        result: list[WorkspaceChartSeries] = []
        for series_code, label in series_specs:
            points = tuple(point_lists[series_code])
            if not points:
                continue
            result.append(
                WorkspaceChartSeries(
                    series_code=series_code,
                    role=WORKSPACE_CHART_ROLE_PRICE_OVERLAY,
                    label=label,
                    timeframe=timeframe,
                    profile_uid=signal_filter.profile_uid,
                    profile_revision=signal_filter.profile_revision,
                    points=points,
                )
            )
        return tuple(result)

    def on_order_event(self, event: object) -> None:
        _ = event
        if not self.started:
            raise WorkspaceAlgorithmError("MACD Alligator algorithm is not started")

    def stop(self) -> None:
        self.started = False


def _workspace_signal_output_tuple(
    output: WorkspaceSignalOutput,
) -> tuple[WorkspaceSignalProposal, ...]:
    if output is None:
        return ()
    if isinstance(output, WorkspaceSignalProposal):
        return (output,)
    return tuple(output)


def _restore_workspace_signal_output_shape(
    base_output: WorkspaceSignalOutput,
    proposals: tuple[WorkspaceSignalProposal, ...],
) -> WorkspaceSignalOutput:
    if not proposals:
        return None
    if len(proposals) == 1 and isinstance(base_output, WorkspaceSignalProposal):
        return proposals[0]
    if len(proposals) == 1 and base_output is None:
        return proposals[0]
    return proposals


def _workspace_alligator_filter_context(
    signal_filter: WorkspaceAlligatorFilter,
    observation: WorkspaceAlligatorObservation,
    event: WorkspaceMarketEvent,
    *,
    direction: str | None = None,
) -> WorkspaceSignalFilterContext:
    history = signal_filter.diagnostic_observation_history(observation, limit=3)
    diagnostic_observations = tuple(
        WorkspaceSignalFilterObservation(
            timestamp=item.timestamp,
            available_at=item.available_at,
            state=item.state,
            regime=item.regime,
            regime_phase=item.regime_phase,
            normalized_slope=item.normalized_slope,
            normalized_opening=item.normalized_opening,
        )
        for item in history
    )
    active_age = (
        _candidate_f_active_age(signal_filter.observations, direction)
        if (
            signal_filter.runtime_profile.candidate_f_enabled
            and direction in {"BUY", "SELL"}
        )
        else None
    )
    return WorkspaceSignalFilterContext(
        mode=signal_filter.confirmation_mode,
        timeframe=signal_filter.timeframe or event.timeframe,
        profile_uid=signal_filter.profile_uid,
        profile_revision=signal_filter.profile_revision,
        observation_timestamp=observation.timestamp,
        available_at=observation.available_at,
        regime=observation.regime,
        regime_phase=observation.regime_phase,
        normalized_slope=observation.normalized_slope,
        normalized_opening=observation.normalized_opening,
        active_age=active_age,
        diagnostic_observations=diagnostic_observations,
    )


def _candidate_f_armable(proposal: WorkspaceSignalProposal) -> bool:
    context = proposal.filter_context
    return bool(
        proposal.signal_type == "MACD_CROSS"
        and proposal.source_reason_code == "MACD_CROSS_ACCEPTED"
        and proposal.filter_decision == WORKSPACE_SIGNAL_FILTER_REJECT
        and context is not None
        and context.regime_phase == ALLIGATOR_REGIME_PHASE_STARTING
        and _candidate_f_regime_matches(context.regime, proposal.direction)
    )


def _candidate_f_regime_matches(regime: str | None, direction: str) -> bool:
    if direction == "BUY":
        return regime == ALLIGATOR_REGIME_TREND_UP
    return regime == ALLIGATOR_REGIME_TREND_DOWN


def _candidate_f_macd_relation_matches(
    histogram: float | None,
    direction: str,
) -> bool:
    if histogram is None:
        return False
    if direction == "BUY":
        return histogram > 0.0
    return histogram < 0.0


def _candidate_f_active_matches(
    observation: WorkspaceAlligatorObservation | None,
    direction: str,
) -> bool:
    if observation is None:
        return False
    if observation.regime_phase != ALLIGATOR_REGIME_PHASE_ACTIVE:
        return False
    if direction == "BUY":
        return bool(
            observation.regime == ALLIGATOR_REGIME_TREND_UP
            and observation.state == ALLIGATOR_STATE_BULLISH
        )
    return bool(
        observation.regime == ALLIGATOR_REGIME_TREND_DOWN
        and observation.state == ALLIGATOR_STATE_BEARISH
    )


def _candidate_f_active_opposite(
    observation: WorkspaceAlligatorObservation | None,
    direction: str,
) -> bool:
    if observation is None:
        return False
    if observation.regime_phase != ALLIGATOR_REGIME_PHASE_ACTIVE:
        return False
    if direction == "BUY":
        return bool(
            observation.regime == ALLIGATOR_REGIME_TREND_DOWN
            and observation.state == ALLIGATOR_STATE_BEARISH
        )
    return bool(
        observation.regime == ALLIGATOR_REGIME_TREND_UP
        and observation.state == ALLIGATOR_STATE_BULLISH
    )


def _candidate_f_active_age(
    observations: tuple[WorkspaceAlligatorObservation, ...],
    direction: str,
) -> int:
    regime = (
        ALLIGATOR_REGIME_TREND_UP
        if direction == "BUY"
        else ALLIGATOR_REGIME_TREND_DOWN
    )
    state = (
        ALLIGATOR_STATE_BULLISH
        if direction == "BUY"
        else ALLIGATOR_STATE_BEARISH
    )
    count = 0
    for observation in reversed(observations):
        if not (
            observation.regime == regime
            and observation.state == state
            and observation.regime_phase == ALLIGATOR_REGIME_PHASE_ACTIVE
        ):
            break
        count += 1
    return count


def _candidate_f_structural_reason(
    profile: WorkspaceAlligatorRuntimeProfile,
    *,
    active_age: int,
    slope: float,
    opening: float,
    slope_delta: float,
    opening_delta: float,
    range_ratio: float,
) -> str | None:
    if active_age <= profile.weak_max_active_age and opening < profile.weak_max_opening:
        return ALLIGATOR_REASON_WEAK_OPENING
    deterioration = (
        opening_delta < profile.spike_max_opening_delta
        or slope_delta < profile.spike_max_slope_delta
    )
    if range_ratio >= profile.spike_min_range_ratio and deterioration:
        return ALLIGATOR_REASON_VOLATILITY_SPIKE
    if (
        slope >= profile.overextended_min_slope
        and opening >= profile.overextended_min_opening
    ):
        return ALLIGATOR_REASON_OVEREXTENDED
    return None


def _candidate_f_reject(
    proposal: WorkspaceSignalProposal,
    reason_code: str,
    detail: str,
) -> WorkspaceSignalProposal:
    return replace(
        proposal,
        filter_decision=WORKSPACE_SIGNAL_FILTER_REJECT,
        filter_reason_code=reason_code,
        reason=(
            f"{proposal.reason}; {reason_code}: {detail}"
        ).strip("; "),
    )


def _next_ema(value: float, previous: float | None, period: int) -> float:
    if previous is None:
        return value
    alpha = 2.0 / (period + 1.0)
    return alpha * value + (1.0 - alpha) * previous


def _shifted_value(
    values: list[float | None],
    shift: int,
) -> float | None:
    index = len(values) - shift - 1
    if index < 0:
        return None
    return values[index]


def _market_source_value(
    event: WorkspaceMarketEvent,
    source: str,
) -> float:
    open_value = _finite_float(event.open, "open")
    high = _finite_float(event.high, "high")
    low = _finite_float(event.low, "low")
    close = _finite_float(event.close, "close")
    if source == WORKSPACE_INDICATOR_SOURCE_OPEN:
        return open_value
    if source == WORKSPACE_INDICATOR_SOURCE_HIGH:
        return high
    if source == WORKSPACE_INDICATOR_SOURCE_LOW:
        return low
    if source == WORKSPACE_INDICATOR_SOURCE_CLOSE:
        return close
    if source == WORKSPACE_INDICATOR_SOURCE_MEDIAN:
        return (high + low) / 2.0
    if source == WORKSPACE_INDICATOR_SOURCE_TYPICAL:
        return (high + low + close) / 3.0
    if source == WORKSPACE_INDICATOR_SOURCE_WEIGHTED:
        return (high + low + 2.0 * close) / 4.0
    raise WorkspaceAlgorithmError(f"Unsupported Alligator source: {source}")


def _alligator_regime_diagnostics(
    jaw: float | None,
    teeth: float | None,
    lips: float | None,
    *,
    center_history: list[float | None],
    bar_range_history: list[float],
    warmed_up: bool,
) -> tuple[
    str,
    float | None,
    float | None,
    float | None,
    float | None,
    float | None,
    float | None,
]:
    """Обчислити causal FLAT/TREND diagnostic без зміни trade gate."""
    if not warmed_up or jaw is None or teeth is None or lips is None:
        return (
            ALLIGATOR_REGIME_WARMUP,
            None,
            None,
            None,
            None,
            None,
            None,
        )

    center = (jaw + teeth + lips) / 3.0
    opening = max(jaw, teeth, lips) - min(jaw, teeth, lips)
    if len(center_history) < ALLIGATOR_REGIME_LOOKBACK_BARS:
        return (
            ALLIGATOR_REGIME_WARMUP,
            center,
            opening,
            None,
            None,
            None,
            None,
        )
    previous_center = center_history[-ALLIGATOR_REGIME_LOOKBACK_BARS]
    if previous_center is None:
        return (
            ALLIGATOR_REGIME_WARMUP,
            center,
            opening,
            None,
            None,
            None,
            None,
        )
    if len(bar_range_history) < ALLIGATOR_REGIME_RANGE_WINDOW_BARS:
        return (
            ALLIGATOR_REGIME_WARMUP,
            center,
            opening,
            None,
            None,
            None,
            None,
        )

    recent_ranges = bar_range_history[-ALLIGATOR_REGIME_RANGE_WINDOW_BARS:]
    range_reference = sum(recent_ranges) / len(recent_ranges)
    if range_reference <= 0.0:
        return (
            ALLIGATOR_REGIME_WARMUP,
            center,
            opening,
            None,
            range_reference,
            None,
            None,
        )

    center_slope_per_bar = (center - previous_center) / ALLIGATOR_REGIME_LOOKBACK_BARS
    normalized_slope = abs(center_slope_per_bar) / range_reference
    normalized_opening = opening / range_reference
    if (
        normalized_slope <= ALLIGATOR_REGIME_FLAT_MAX_NORMALIZED_SLOPE
        and normalized_opening <= ALLIGATOR_REGIME_FLAT_MAX_NORMALIZED_OPENING
    ):
        regime = ALLIGATOR_REGIME_FLAT
    elif center_slope_per_bar > 0.0:
        regime = ALLIGATOR_REGIME_TREND_UP
    elif center_slope_per_bar < 0.0:
        regime = ALLIGATOR_REGIME_TREND_DOWN
    elif lips >= jaw:
        regime = ALLIGATOR_REGIME_TREND_UP
    else:
        regime = ALLIGATOR_REGIME_TREND_DOWN

    return (
        regime,
        center,
        opening,
        center_slope_per_bar,
        range_reference,
        normalized_slope,
        normalized_opening,
    )


def _alligator_regime_with_flat_hysteresis(
    raw_regime: str,
    *,
    raw_regime_history: list[str],
    previous_observation: WorkspaceAlligatorObservation | None,
) -> str:
    """Не втрачати ENDING на першому ж FLAT-bar після тренду.

    FLAT вважається підтвердженим лише після кількох послідовних causal
    FLAT-спостережень. До підтвердження зберігається попередній напрямок
    TREND_* і примусово ставиться ENDING незалежно від поточного порядку
    ліній. Це diagnostic hysteresis і він не змінює чинний ALLOW/REJECT
    trade gate.
    """
    if raw_regime != ALLIGATOR_REGIME_FLAT:
        return raw_regime
    if previous_observation is None:
        return raw_regime
    if previous_observation.regime not in {
        ALLIGATOR_REGIME_TREND_UP,
        ALLIGATOR_REGIME_TREND_DOWN,
    }:
        return raw_regime

    flat_streak = 1
    for previous_raw_regime in reversed(raw_regime_history):
        if previous_raw_regime != ALLIGATOR_REGIME_FLAT:
            break
        flat_streak += 1

    if flat_streak < ALLIGATOR_REGIME_FLAT_CONFIRMATION_BARS:
        return previous_observation.regime
    return raw_regime


def _alligator_regime_phase(
    regime: str,
    state: str,
    *,
    observation_history: list[WorkspaceAlligatorObservation],
    confirmation_bars: int = ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS,
) -> str:
    """Визначити causal фазу тренду без зміни торгового рішення.

    Напрямок задає довший regime diagnostic. Фаза відповідає на інше
    питання: чи підтверджує поточне взаємне розташування ліній цей напрямок.
    Новий напрямок не переходить в ACTIVE після одного bar: потрібна
    profile-defined кількість послідовних завершених bars з тим самим regime
    і правильним порядком ліній.
    До підтвердження фаза лишається STARTING. Втрата правильного порядку
    ліній скидає підтвердження і дає ENDING.
    """
    if regime == ALLIGATOR_REGIME_TREND_UP:
        aligned_state = ALLIGATOR_STATE_BULLISH
    elif regime == ALLIGATOR_REGIME_TREND_DOWN:
        aligned_state = ALLIGATOR_STATE_BEARISH
    else:
        return ALLIGATOR_REGIME_PHASE_NONE

    if state != aligned_state:
        return ALLIGATOR_REGIME_PHASE_ENDING

    aligned_streak = 1
    for previous_observation in reversed(observation_history):
        if previous_observation.regime != regime:
            break
        if previous_observation.state != aligned_state:
            break
        if previous_observation.regime_phase == ALLIGATOR_REGIME_PHASE_ENDING:
            break
        aligned_streak += 1

    if aligned_streak < confirmation_bars:
        return ALLIGATOR_REGIME_PHASE_STARTING

    return ALLIGATOR_REGIME_PHASE_ACTIVE


def _alligator_state(
    jaw: float | None,
    teeth: float | None,
    lips: float | None,
    *,
    warmed_up: bool,
) -> str:
    if not warmed_up or jaw is None or teeth is None or lips is None:
        return ALLIGATOR_STATE_WARMUP
    if lips > teeth > jaw:
        return ALLIGATOR_STATE_BULLISH
    if lips < teeth < jaw:
        return ALLIGATOR_STATE_BEARISH
    return ALLIGATOR_STATE_NEUTRAL


def _same_timeframe_phase_reject_decision(
    direction: str,
    observation: WorkspaceAlligatorObservation,
    *,
    confirmation: str,
) -> WorkspaceAlligatorDecision | None:
    """Застосувати SAME_TIMEFRAME phase-gate до завершеного bar."""
    phase = observation.regime_phase
    if phase == ALLIGATOR_REGIME_PHASE_STARTING:
        if direction == "BUY":
            reason_code = ALLIGATOR_REASON_BUY_START_REJECT
        else:
            reason_code = ALLIGATOR_REASON_SELL_START_REJECT
        return WorkspaceAlligatorDecision(
            allowed=False,
            confirmation=confirmation,
            reason_code=reason_code,
            reason_text=f"Alligator trend is still starting and rejects {direction}.",
        )
    if phase == ALLIGATOR_REGIME_PHASE_ENDING:
        if direction == "BUY":
            reason_code = ALLIGATOR_REASON_BUY_END_REJECT
        else:
            reason_code = ALLIGATOR_REASON_SELL_END_REJECT
        return WorkspaceAlligatorDecision(
            allowed=False,
            confirmation=confirmation,
            reason_code=reason_code,
            reason_text=f"Alligator trend is ending and rejects {direction}.",
        )
    if phase != ALLIGATOR_REGIME_PHASE_ACTIVE:
        return WorkspaceAlligatorDecision(
            allowed=False,
            confirmation=confirmation,
            reason_code=_decision_reason_code(
                WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
                direction,
                False,
            ),
            reason_text=_decision_reason_text(
                WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
                direction,
                False,
                observation.timeframe,
            ),
        )
    return None


def _confirmation_for_state(state: str, confirmation_mode: str) -> str:
    if confirmation_mode == WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2:
        if state == ALLIGATOR_STATE_BULLISH:
            return ALLIGATOR_CONFIRMATION_HIGHER_2_BULLISH
        if state == ALLIGATOR_STATE_BEARISH:
            return ALLIGATOR_CONFIRMATION_HIGHER_2_BEARISH
        if state == ALLIGATOR_STATE_WARMUP:
            return ALLIGATOR_CONFIRMATION_HIGHER_2_WARMUP
        return ALLIGATOR_CONFIRMATION_HIGHER_2_NEUTRAL
    if confirmation_mode == WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_1:
        if state == ALLIGATOR_STATE_BULLISH:
            return ALLIGATOR_CONFIRMATION_HIGHER_1_BULLISH
        if state == ALLIGATOR_STATE_BEARISH:
            return ALLIGATOR_CONFIRMATION_HIGHER_1_BEARISH
        if state == ALLIGATOR_STATE_WARMUP:
            return ALLIGATOR_CONFIRMATION_HIGHER_1_WARMUP
        return ALLIGATOR_CONFIRMATION_HIGHER_1_NEUTRAL
    if state == ALLIGATOR_STATE_BULLISH:
        return ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME_BULLISH
    if state == ALLIGATOR_STATE_BEARISH:
        return ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME_BEARISH
    if state == ALLIGATOR_STATE_WARMUP:
        return ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME_WARMUP
    return ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME_NEUTRAL


def _decision_reason_code(
    confirmation_mode: str,
    direction: str,
    allowed: bool,
) -> str:
    if confirmation_mode == WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2:
        if direction == "BUY":
            return (
                ALLIGATOR_REASON_HIGHER_2_BUY_ALLOW
                if allowed
                else ALLIGATOR_REASON_HIGHER_2_BUY_REJECT
            )
        return (
            ALLIGATOR_REASON_HIGHER_2_SELL_ALLOW
            if allowed
            else ALLIGATOR_REASON_HIGHER_2_SELL_REJECT
        )
    if confirmation_mode == WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_1:
        if direction == "BUY":
            return (
                ALLIGATOR_REASON_HIGHER_1_BUY_ALLOW
                if allowed
                else ALLIGATOR_REASON_HIGHER_1_BUY_REJECT
            )
        return (
            ALLIGATOR_REASON_HIGHER_1_SELL_ALLOW
            if allowed
            else ALLIGATOR_REASON_HIGHER_1_SELL_REJECT
        )
    if direction == "BUY":
        return ALLIGATOR_REASON_BUY_ALLOW if allowed else ALLIGATOR_REASON_BUY_REJECT
    return ALLIGATOR_REASON_SELL_ALLOW if allowed else ALLIGATOR_REASON_SELL_REJECT


def _decision_reason_text(
    confirmation_mode: str,
    direction: str,
    allowed: bool,
    timeframe: str,
) -> str:
    if confirmation_mode == WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2:
        scope = f"Second higher-timeframe {timeframe} Alligator"
    elif confirmation_mode == WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_1:
        scope = f"Higher-timeframe {timeframe} Alligator"
    else:
        scope = "Alligator"
    expected = "bullish" if direction == "BUY" else "bearish"
    if allowed:
        return f"{scope} is {expected} and confirms {direction}."
    return f"{scope} is not {expected} and rejects {direction}."


def _normalized_choice(
    value: object,
    field_name: str,
    allowed: tuple[str, ...],
) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in allowed:
        raise WorkspaceAlgorithmError(
            f"Invalid {field_name}: {normalized or '<empty>'}"
        )
    return normalized


def _strict_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise WorkspaceAlgorithmError(f"{field_name} must be bool")
    return value


def _positive_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise WorkspaceAlgorithmError(f"{field_name} must be positive integer")
    return value


def _non_negative_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise WorkspaceAlgorithmError(f"{field_name} must be non-negative integer")
    return value


def _finite_float(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise WorkspaceAlgorithmError(f"{field_name} must be finite")
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise WorkspaceAlgorithmError(f"{field_name} must be finite") from exc
    if not math.isfinite(number):
        raise WorkspaceAlgorithmError(f"{field_name} must be finite")
    return number
