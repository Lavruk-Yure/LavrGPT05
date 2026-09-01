"""workspace_macd.py — детерміноване MACD-джерело сигналів WSP.

MACD використовує точний ``resolved_profile_snapshot`` із прив'язки WSP.
Редагування профілю в каталозі не змінює вже збережений runtime snapshot.
Однакова MACD-математика приймає strictly ordered immutable completed bars із
Replay та read-only BROKER delivery path. Перший сигнальний контракт навмисно
обмежений перетином лінії MACD і сигнальної лінії; ``EXTENDED`` додає quality
pipeline. Модуль не агрегує partial quotes і не виконує broker operations.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.algorithm_workspace import (
    WORKSPACE_DATA_MODE_BROKER,
    WORKSPACE_DATA_MODE_REPLAY,
)
from core.timeframes import get_timeframe
from core.workspace_algorithm import (
    WorkspaceAlgorithm,
    WorkspaceAlgorithmError,
    WorkspaceSignalOutput,
)
from core.workspace_indicator_profile import (
    MACD_PROFILE_UID_LGE_CLASSIC,
    WORKSPACE_INDICATOR_MA_EXPONENTIAL,
    WORKSPACE_INDICATOR_MA_SIMPLE,
    WORKSPACE_INDICATOR_MA_SMOOTHED,
    WORKSPACE_INDICATOR_MA_TYPES,
    WORKSPACE_INDICATOR_MACD,
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
from core.workspace_macd_cross_angle_abc import (
    resolve_workspace_macd_cross_angle_value_scale,
)
from core.workspace_macd_crossover_quality import (
    WorkspaceMacdCrossoverQualityConfig,
    WorkspaceMacdCrossoverQualityDiagnostic,
    calibrated_macd_cross_angle_reference_y_per_minute,
    evaluate_workspace_macd_crossover_quality,
)
from core.workspace_market_event import WorkspaceMarketEvent
from core.workspace_runtime_requirements import WorkspaceWarmupRequirement
from core.workspace_signal import (
    WORKSPACE_SIGNAL_FILTER_ALLOW,
    WORKSPACE_SIGNAL_FILTER_REJECT,
    WorkspaceSignalProposal,
)

if TYPE_CHECKING:
    from core.workspace_runtime import WorkspaceRuntimeContext

from engine.runtime_constants import (
    DEFAULT_WORKSPACE_MACD_CROSS_ANGLE_MODEL,
    DEFAULT_WORKSPACE_MACD_CROSS_MIN_ABC_ANGLE,
    DEFAULT_WORKSPACE_MACD_CROSS_MIN_ANGLE,
    DEFAULT_WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE,
    DEFAULT_WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE,
    DEFAULT_WORKSPACE_MACD_SIGNAL_ENABLED,
    DEFAULT_WORKSPACE_MACD_SIGNAL_MODE,
    WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED,
    WORKSPACE_MACD_CROSS_ANGLE_MODEL_ABC,
    WORKSPACE_MACD_CROSS_ANGLE_MODEL_KEY,
    WORKSPACE_MACD_CROSS_ANGLE_MODELS,
    WORKSPACE_MACD_CROSS_MIN_ABC_ANGLE_KEY,
    WORKSPACE_MACD_CROSS_MIN_ANGLE_KEY,
    WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE_KEY,
    WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE_KEY,
    WORKSPACE_MACD_SIGNAL_ENABLED_KEY,
    WORKSPACE_MACD_SIGNAL_MODE_EXTENDED,
    WORKSPACE_MACD_SIGNAL_MODES,
)

MACD_COMPONENT_CODE = "MACD"
MACD_FAST_PERIOD = 12
MACD_SLOW_PERIOD = 26
MACD_SIGNAL_PERIOD = 9
MACD_REQUIRED_BARS = MACD_SLOW_PERIOD + MACD_SIGNAL_PERIOD

MACD_STATE_WARMUP = "MACD_WARMUP"
MACD_STATE_NEUTRAL = "MACD_NEUTRAL"
MACD_STATE_BULLISH = "MACD_BULLISH"
MACD_STATE_BEARISH = "MACD_BEARISH"
MACD_STATE_CROSS_UP = "MACD_CROSS_UP"
MACD_STATE_CROSS_DOWN = "MACD_CROSS_DOWN"


@dataclass(frozen=True, slots=True)
class WorkspaceMacdRuntimeProfile:
    """Перевірені параметри однієї зафіксованої редакції MACD."""

    profile_uid: str
    profile_revision: int
    profile_name: str
    source: str
    fast_period: int
    slow_period: int
    signal_period: int
    oscillator_ma_type: str
    signal_ma_type: str
    shift: int

    @classmethod
    def from_binding(
        cls,
        binding: WorkspaceIndicatorProfileBinding,
    ) -> WorkspaceMacdRuntimeProfile:
        """Побудувати runtime-профіль лише зі snapshot прив'язки WSP."""
        if binding.indicator_code != WORKSPACE_INDICATOR_MACD:
            raise WorkspaceAlgorithmError(
                "MACD runtime requires a MACD profile binding"
            )
        profile = binding.profile
        parameters = profile.parameters
        fast_period = _positive_integer(
            parameters.get("fast_period"),
            "fast_period",
        )
        slow_period = _positive_integer(
            parameters.get("slow_period"),
            "slow_period",
        )
        if slow_period <= fast_period:
            raise WorkspaceAlgorithmError("MACD slow_period must exceed fast_period")
        return cls(
            profile_uid=profile.profile_uid,
            profile_revision=profile.revision,
            profile_name=profile.name,
            source=_normalized_choice(
                parameters.get("source"),
                "MACD source",
                WORKSPACE_INDICATOR_SOURCES,
            ),
            fast_period=fast_period,
            slow_period=slow_period,
            signal_period=_positive_integer(
                parameters.get("signal_period"),
                "signal_period",
            ),
            oscillator_ma_type=_normalized_choice(
                parameters.get("oscillator_ma_type"),
                "oscillator_ma_type",
                WORKSPACE_INDICATOR_MA_TYPES,
            ),
            signal_ma_type=_normalized_choice(
                parameters.get("signal_ma_type"),
                "signal_ma_type",
                WORKSPACE_INDICATOR_MA_TYPES,
            ),
            shift=_non_negative_integer(
                parameters.get("shift"),
                "shift",
            ),
        )

    @classmethod
    def lge_default(cls) -> WorkspaceMacdRuntimeProfile:
        """Повернути сумісний профіль для прямих legacy-конструкторів."""
        profile = built_in_workspace_indicator_profile(MACD_PROFILE_UID_LGE_CLASSIC)
        binding = WorkspaceIndicatorProfileBinding.from_profile(profile)
        return cls.from_binding(binding)

    @property
    def required_bars(self) -> int:
        """Повернути консервативний warm-up із урахуванням shift."""
        return self.slow_period + self.signal_period + self.shift


@dataclass(frozen=True, slots=True)
class WorkspaceMacdObservation:
    """Один обчислений стан MACD для завершеного Replay-бару."""

    timestamp: datetime
    close: float
    source_value: float
    macd_value: float | None
    signal_value: float | None
    histogram: float | None
    state: str
    bars_processed: int
    warmed_up: bool
    profile_uid: str
    profile_revision: int


class _MovingAverageState:
    """Мінімальний детермінований стан SMA, EMA або SMMA."""

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


class WorkspaceMacdSignalSource:
    """Незалежне MACD-джерело з profile snapshot і станом у пам'яті."""

    def __init__(
        self,
        *,
        enabled: bool,
        mode: str,
        runtime_profile: WorkspaceMacdRuntimeProfile | None = None,
        extremum_min_prominence: float = (
            DEFAULT_WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE
        ),
        extremum_to_cross_min_distance: float = (
            DEFAULT_WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE
        ),
        cross_min_angle_degrees: float = DEFAULT_WORKSPACE_MACD_CROSS_MIN_ANGLE,
        angle_model: str = DEFAULT_WORKSPACE_MACD_CROSS_ANGLE_MODEL,
        cross_min_abc_angle_degrees: float = DEFAULT_WORKSPACE_MACD_CROSS_MIN_ABC_ANGLE,
        abc_indicator_value_scale: float | None = None,
    ) -> None:
        self.enabled = _strict_bool(enabled, "macd_signal_enabled")
        self.mode = _normalized_choice(
            mode,
            "macd_signal_mode",
            WORKSPACE_MACD_SIGNAL_MODES,
        )
        self.runtime_profile = (
            runtime_profile or WorkspaceMacdRuntimeProfile.lge_default()
        )
        self.extremum_min_prominence = _non_negative_float(
            extremum_min_prominence,
            WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE_KEY,
        )
        self.extremum_to_cross_min_distance = _non_negative_float(
            extremum_to_cross_min_distance,
            WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE_KEY,
        )
        self.cross_min_angle_degrees = _bounded_float(
            cross_min_angle_degrees,
            WORKSPACE_MACD_CROSS_MIN_ANGLE_KEY,
            minimum=0.0,
            maximum=180.0,
        )
        self.angle_model = _normalized_choice(
            angle_model,
            WORKSPACE_MACD_CROSS_ANGLE_MODEL_KEY,
            WORKSPACE_MACD_CROSS_ANGLE_MODELS,
        )
        self.cross_min_abc_angle_degrees = _bounded_float(
            cross_min_abc_angle_degrees,
            WORKSPACE_MACD_CROSS_MIN_ABC_ANGLE_KEY,
            minimum=0.0,
            maximum=180.0,
        )
        self.abc_indicator_value_scale = abc_indicator_value_scale
        if self.angle_model == WORKSPACE_MACD_CROSS_ANGLE_MODEL_ABC:
            if abc_indicator_value_scale is None:
                raise WorkspaceAlgorithmError(
                    "ABC MACD angle requires verified instrument value scale"
                )
            self.abc_indicator_value_scale = _positive_float(
                abc_indicator_value_scale,
                "abc_indicator_value_scale",
            )
        self._fast_average = _MovingAverageState(
            period=self.runtime_profile.fast_period,
            ma_type=self.runtime_profile.oscillator_ma_type,
        )
        self._slow_average = _MovingAverageState(
            period=self.runtime_profile.slow_period,
            ma_type=self.runtime_profile.oscillator_ma_type,
        )
        self._signal_average = _MovingAverageState(
            period=self.runtime_profile.signal_period,
            ma_type=self.runtime_profile.signal_ma_type,
        )
        self._bars_processed = 0
        self._raw_values: list[tuple[float, float, float] | None] = []
        self._previous_histogram: float | None = None
        self._last_timestamp: datetime | None = None
        self._observations: list[WorkspaceMacdObservation] = []
        self._quality_diagnostics: list[WorkspaceMacdCrossoverQualityDiagnostic] = []

    @classmethod
    def from_parameters(
        cls,
        parameters: Mapping[str, Any],
    ) -> WorkspaceMacdSignalSource:
        """Побудувати legacy-сумісне джерело з LGE default profile."""
        return cls(
            enabled=parameters.get(
                WORKSPACE_MACD_SIGNAL_ENABLED_KEY,
                DEFAULT_WORKSPACE_MACD_SIGNAL_ENABLED,
            ),
            mode=parameters.get(
                "macd_signal_mode",
                DEFAULT_WORKSPACE_MACD_SIGNAL_MODE,
            ),
            extremum_min_prominence=parameters.get(
                WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE_KEY,
                DEFAULT_WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE,
            ),
            extremum_to_cross_min_distance=parameters.get(
                WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE_KEY,
                DEFAULT_WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE,
            ),
            cross_min_angle_degrees=parameters.get(
                WORKSPACE_MACD_CROSS_MIN_ANGLE_KEY,
                DEFAULT_WORKSPACE_MACD_CROSS_MIN_ANGLE,
            ),
            angle_model=parameters.get(
                WORKSPACE_MACD_CROSS_ANGLE_MODEL_KEY,
                DEFAULT_WORKSPACE_MACD_CROSS_ANGLE_MODEL,
            ),
            cross_min_abc_angle_degrees=parameters.get(
                WORKSPACE_MACD_CROSS_MIN_ABC_ANGLE_KEY,
                DEFAULT_WORKSPACE_MACD_CROSS_MIN_ABC_ANGLE,
            ),
        )

    @classmethod
    def from_runtime_context(
        cls,
        context: WorkspaceRuntimeContext,
        parameters: Mapping[str, Any],
    ) -> WorkspaceMacdSignalSource:
        """Побудувати MACD зі snapshot профілю, збереженого у WSP."""
        binding = workspace_indicator_profile_binding(
            context,
            WORKSPACE_INDICATOR_MACD,
        )
        runtime_profile = WorkspaceMacdRuntimeProfile.from_binding(binding)
        angle_model = parameters.get(
            WORKSPACE_MACD_CROSS_ANGLE_MODEL_KEY,
            DEFAULT_WORKSPACE_MACD_CROSS_ANGLE_MODEL,
        )
        abc_scale = None
        if (
            str(angle_model or "").strip().upper()
            == WORKSPACE_MACD_CROSS_ANGLE_MODEL_ABC
        ):
            abc_scale = resolve_workspace_macd_cross_angle_value_scale(context.symbol)
        return cls(
            enabled=parameters.get(
                WORKSPACE_MACD_SIGNAL_ENABLED_KEY,
                DEFAULT_WORKSPACE_MACD_SIGNAL_ENABLED,
            ),
            mode=parameters.get(
                "macd_signal_mode",
                DEFAULT_WORKSPACE_MACD_SIGNAL_MODE,
            ),
            runtime_profile=runtime_profile,
            extremum_min_prominence=parameters.get(
                WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE_KEY,
                DEFAULT_WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE,
            ),
            extremum_to_cross_min_distance=parameters.get(
                WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE_KEY,
                DEFAULT_WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE,
            ),
            cross_min_angle_degrees=parameters.get(
                WORKSPACE_MACD_CROSS_MIN_ANGLE_KEY,
                DEFAULT_WORKSPACE_MACD_CROSS_MIN_ANGLE,
            ),
            angle_model=angle_model,
            cross_min_abc_angle_degrees=parameters.get(
                WORKSPACE_MACD_CROSS_MIN_ABC_ANGLE_KEY,
                DEFAULT_WORKSPACE_MACD_CROSS_MIN_ABC_ANGLE,
            ),
            abc_indicator_value_scale=abc_scale,
        )

    @property
    def required_bars(self) -> int:
        """Повернути warm-up вибраного profile snapshot."""
        return self.runtime_profile.required_bars if self.enabled else 0

    @property
    def profile_uid(self) -> str:
        return self.runtime_profile.profile_uid

    @property
    def profile_revision(self) -> int:
        return self.runtime_profile.profile_revision

    @property
    def observations(self) -> tuple[WorkspaceMacdObservation, ...]:
        return tuple(self._observations)

    @property
    def quality_diagnostics(
        self,
    ) -> tuple[WorkspaceMacdCrossoverQualityDiagnostic, ...]:
        return tuple(self._quality_diagnostics)

    def reset(self) -> None:
        """Очистити лише розрахунковий стан у пам'яті."""
        self._fast_average.reset()
        self._slow_average.reset()
        self._signal_average.reset()
        self._bars_processed = 0
        self._raw_values = []
        self._previous_histogram = None
        self._last_timestamp = None
        self._observations = []
        self._quality_diagnostics = []

    def on_market_event(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalProposal | None:
        """Оновити MACD завершеним Replay або BROKER bar і дати сигнал."""
        if not self.enabled:
            return None
        if event.source_mode not in {
            WORKSPACE_DATA_MODE_REPLAY,
            WORKSPACE_DATA_MODE_BROKER,
        }:
            return None
        if self._last_timestamp is not None:
            if event.timestamp <= self._last_timestamp:
                raise WorkspaceAlgorithmError(
                    "MACD bars must be strictly ordered and unique"
                )
        self._last_timestamp = event.timestamp

        close = _finite_float(event.close, "close")
        source_value = _market_source_value(
            event,
            self.runtime_profile.source,
        )
        self._bars_processed += 1
        fast_value = self._fast_average.update(source_value)
        slow_value = self._slow_average.update(source_value)

        raw_values: tuple[float, float, float] | None = None
        if fast_value is not None and slow_value is not None:
            raw_macd = fast_value - slow_value
            raw_signal = self._signal_average.update(raw_macd)
            if raw_signal is not None:
                raw_values = (
                    raw_macd,
                    raw_signal,
                    raw_macd - raw_signal,
                )
        self._raw_values.append(raw_values)
        effective = _shifted_values(
            self._raw_values,
            self.runtime_profile.shift,
        )
        macd_value: float | None = None
        signal_value: float | None = None
        histogram: float | None = None
        if effective is not None:
            macd_value, signal_value, histogram = effective

        warmed_up = bool(
            self._bars_processed >= self.required_bars and histogram is not None
        )
        state = _macd_state(histogram, warmed_up=warmed_up)

        cross_direction: str | None = None
        previous_histogram = self._previous_histogram
        if warmed_up and previous_histogram is not None and histogram is not None:
            if previous_histogram <= 0.0 < histogram:
                state = MACD_STATE_CROSS_UP
                cross_direction = "BUY"
            elif previous_histogram >= 0.0 > histogram:
                state = MACD_STATE_CROSS_DOWN
                cross_direction = "SELL"

        if histogram is not None:
            self._previous_histogram = histogram
        self._observations.append(
            WorkspaceMacdObservation(
                timestamp=event.timestamp,
                close=close,
                source_value=source_value,
                macd_value=macd_value,
                signal_value=signal_value,
                histogram=histogram,
                state=state,
                bars_processed=self._bars_processed,
                warmed_up=warmed_up,
                profile_uid=self.profile_uid,
                profile_revision=self.profile_revision,
            )
        )
        if cross_direction is None or histogram is None:
            return None
        return self._proposal(
            cross_direction,
            state,
            histogram,
            event=event,
        )

    def _proposal(
        self,
        direction: str,
        state: str,
        histogram: float,
        *,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalProposal:
        if self.mode != WORKSPACE_MACD_SIGNAL_MODE_EXTENDED:
            reason_code = "MACD_CLASSIC_CROSS"
            return WorkspaceSignalProposal(
                signal_type="MACD_CROSS",
                direction=direction,
                strength=abs(histogram),
                macd_state=state,
                alligator_confirmation=WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED,
                reason=(
                    f"{reason_code}; mode={self.mode}; "
                    f"profile_uid={self.profile_uid}; "
                    f"profile_revision={self.profile_revision}"
                ),
                source_reason_code=reason_code,
                source_profile_uid=self.profile_uid,
                source_profile_revision=self.profile_revision,
            )

        diagnostic = self._evaluate_quality(event)
        self._quality_diagnostics.append(diagnostic)
        decision = (
            WORKSPACE_SIGNAL_FILTER_ALLOW
            if diagnostic.final_quality_pass
            else WORKSPACE_SIGNAL_FILTER_REJECT
        )
        return WorkspaceSignalProposal(
            signal_type="MACD_CROSS",
            direction=direction,
            strength=abs(histogram),
            macd_state=state,
            alligator_confirmation=WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED,
            reason=self._quality_reason_text(diagnostic),
            source_reason_code=diagnostic.reason_code,
            source_profile_uid=self.profile_uid,
            source_profile_revision=self.profile_revision,
            filter_decision=decision,
            filter_reason_code=(
                diagnostic.reason_code
                if decision == WORKSPACE_SIGNAL_FILTER_REJECT
                else None
            ),
        )

    def _evaluate_quality(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceMacdCrossoverQualityDiagnostic:
        min_angle = self.cross_min_angle_degrees
        legacy_reference = calibrated_macd_cross_angle_reference_y_per_minute()
        if self.angle_model == WORKSPACE_MACD_CROSS_ANGLE_MODEL_ABC:
            min_angle = self.cross_min_abc_angle_degrees
            legacy_reference = None
        config = WorkspaceMacdCrossoverQualityConfig(
            angle_reference_y_per_minute=legacy_reference,
            strategy_bar_minutes=get_timeframe(event.timeframe).minutes,
            extremum_min_prominence=self.extremum_min_prominence,
            extremum_to_cross_min_distance=self.extremum_to_cross_min_distance,
            cross_min_angle_degrees=min_angle,
            angle_model=self.angle_model,
            abc_indicator_value_scale=self.abc_indicator_value_scale,
        )
        diagnostic = evaluate_workspace_macd_crossover_quality(
            self.observations,
            config=config,
        )
        if diagnostic is None:
            raise WorkspaceAlgorithmError(
                "EXTENDED MACD crossover has no quality diagnostic"
            )
        return diagnostic

    def _quality_reason_text(
        self,
        diagnostic: WorkspaceMacdCrossoverQualityDiagnostic,
    ) -> str:
        extremum_timestamp = (
            diagnostic.extremum_timestamp.isoformat()
            if diagnostic.extremum_timestamp is not None
            else "NONE"
        )
        return (
            f"{diagnostic.reason_code}; mode={self.mode}; "
            f"profile_uid={self.profile_uid}; "
            f"profile_revision={self.profile_revision}; "
            f"angle_model={self.angle_model}; "
            f"histogram_before={diagnostic.histogram_before:+.8f}; "
            f"histogram_after={diagnostic.histogram_after:+.8f}; "
            f"extremum_timestamp={extremum_timestamp}; "
            f"extremum_type={diagnostic.extremum_type}; "
            f"search_window={diagnostic.search_window or 'NONE'}; "
            "extremum_prominence="
            f"{_optional_diagnostic_number(diagnostic.extremum_prominence)}; "
            "extremum_to_cross_distance="
            f"{_optional_diagnostic_number(diagnostic.extremum_to_cross_distance)}; "
            f"crossover_steepness={diagnostic.crossover_steepness:.8f}; "
            f"effective_angle={diagnostic.effective_angle_degrees:.2f}; "
            f"criterion_extremum_pass={diagnostic.criterion_extremum_pass}; "
            "criterion_prominence_pass="
            f"{diagnostic.criterion_prominence_pass}; "
            f"criterion_distance_pass={diagnostic.criterion_distance_pass}; "
            f"criterion_angle_pass={diagnostic.criterion_angle_pass}; "
            f"final_quality_pass={diagnostic.final_quality_pass}"
        )


class WorkspaceMacdReplayAlgorithm(WorkspaceAlgorithm):
    """MACD-обгортка Replay без виконання ордерів."""

    def __init__(self, algorithm_id: str = "MACD_REPLAY") -> None:
        self.algorithm_id = str(algorithm_id or "").strip() or "MACD_REPLAY"
        self.context: WorkspaceRuntimeContext | None = None
        self.parameters: dict[str, Any] = {}
        self.source: WorkspaceMacdSignalSource | None = None
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

    def warmup_requirements(
        self,
    ) -> tuple[WorkspaceWarmupRequirement, ...] | None:
        source = self.source
        if source is None:
            raise WorkspaceAlgorithmError("MACD algorithm is not configured")
        if not source.enabled:
            return ()
        timeframe = str(getattr(self.context, "timeframe", "")).strip()
        return (
            WorkspaceWarmupRequirement(
                component_code=MACD_COMPONENT_CODE,
                timeframe=timeframe,
                required_bars=source.required_bars,
            ),
        )

    def start(self) -> None:
        source = self.source
        if self.context is None or source is None:
            raise WorkspaceAlgorithmError("MACD algorithm is not configured")
        source.reset()
        self.started = True

    def on_market_event(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalOutput:
        if not self.started or self.source is None:
            raise WorkspaceAlgorithmError("MACD algorithm is not started")
        return self.source.on_market_event(event)

    def on_order_event(self, event: object) -> None:
        _ = event
        if not self.started:
            raise WorkspaceAlgorithmError("MACD algorithm is not started")

    def stop(self) -> None:
        self.started = False


def _optional_diagnostic_number(value: float | None) -> str:
    if value is None:
        return "NONE"
    return f"{value:+.8f}"


def _non_negative_float(value: object, field_name: str) -> float:
    number = _finite_float(value, field_name)
    if number < 0.0:
        raise WorkspaceAlgorithmError(f"{field_name} must be non-negative")
    return number


def _positive_float(value: object, field_name: str) -> float:
    number = _finite_float(value, field_name)
    if number <= 0.0:
        raise WorkspaceAlgorithmError(f"{field_name} must be positive")
    return number


def _bounded_float(
    value: object,
    field_name: str,
    *,
    minimum: float,
    maximum: float,
) -> float:
    number = _finite_float(value, field_name)
    if number < minimum or number > maximum:
        raise WorkspaceAlgorithmError(
            f"{field_name} must be between {minimum} and {maximum}"
        )
    return number


def _next_ema(value: float, previous: float | None, period: int) -> float:
    if previous is None:
        return value
    alpha = 2.0 / (period + 1.0)
    return previous + alpha * (value - previous)


def _shifted_values(
    values: list[tuple[float, float, float] | None],
    shift: int,
) -> tuple[float, float, float] | None:
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
    raise WorkspaceAlgorithmError(f"Unsupported MACD source: {source}")


def _macd_state(
    histogram: float | None,
    *,
    warmed_up: bool,
) -> str:
    if not warmed_up or histogram is None:
        return MACD_STATE_WARMUP
    if histogram > 0.0:
        return MACD_STATE_BULLISH
    if histogram < 0.0:
        return MACD_STATE_BEARISH
    return MACD_STATE_NEUTRAL


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
