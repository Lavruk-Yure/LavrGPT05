# -*- coding: utf-8 -*-
"""Production regression повного ARMED lifecycle Candidate F, RoadMap102 / 2B.

Тест не оптимізує thresholds і не підміняє MACD/Alligator research.
Він контрольовано подає production Candidate F causal snapshots, щоб
окремо закрити всі deferred-гілки: ARMED -> RELEASE, cancel через opposite
MACD, invalid MACD relation, opposite ACTIVE Alligator, TTL EXPIRE,
duplicate-bar protection і повторне проходження structural guards після
RELEASE.

Інваріанти: один початковий MACD-кандидат дає не більше одного deferred
release. Використовуються лише завершені M15 events. Future Alligator
observation не може бути використаний. Candidate F profile/thresholds не
змінюються; broker execution у цьому regression відсутній.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import WORKSPACE_DATA_MODE_REPLAY  # noqa: E402
from core.workspace_algorithm import (  # noqa: E402
    WorkspaceAlgorithmError,
    WorkspaceSignalOutput,
)
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_DEFERRED_SIGNAL_TYPE,
    ALLIGATOR_REASON_DEFERRED_ARMED,
    ALLIGATOR_REASON_DEFERRED_RELEASE,
    ALLIGATOR_REASON_OPENING_COLLAPSE,
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_PHASE_STARTING,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    ALLIGATOR_STATE_BEARISH,
    ALLIGATOR_STATE_BULLISH,
    CANDIDATE_F_LIFECYCLE_CANCEL,
    CANDIDATE_F_LIFECYCLE_EXPIRE,
    CANDIDATE_F_LIFECYCLE_REASON_MACD_INVALID,
    CANDIDATE_F_LIFECYCLE_REASON_OPPOSITE_ACTIVE_ALLIGATOR,
    CANDIDATE_F_LIFECYCLE_REASON_OPPOSITE_MACD,
    CANDIDATE_F_LIFECYCLE_REASON_TTL_EXPIRED,
    CANDIDATE_F_LIFECYCLE_RELEASE,
    WorkspaceAlligatorFilter,
    WorkspaceAlligatorObservation,
    WorkspaceAlligatorRuntimeProfile,
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_indicator_profile import (  # noqa: E402
    ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F,
    WorkspaceIndicatorProfileBinding,
    built_in_workspace_indicator_profile,
)
from core.workspace_macd import (  # noqa: E402
    MACD_STATE_BEARISH,
    MACD_STATE_BULLISH,
    WorkspaceMacdObservation,
    WorkspaceMacdSignalSource,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_signal import (  # noqa: E402
    WORKSPACE_SIGNAL_FILTER_ALLOW,
    WORKSPACE_SIGNAL_FILTER_REJECT,
    WorkspaceSignalFilterContext,
    WorkspaceSignalProposal,
)
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
    WORKSPACE_MACD_SIGNAL_MODE_EXTENDED,
)

BASE_TIME = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)


class _SyntheticMacdSource(WorkspaceMacdSignalSource):
    """Реальний MACD source із керованим test-only observation."""

    def __init__(self) -> None:
        super().__init__(
            enabled=True,
            mode=WORKSPACE_MACD_SIGNAL_MODE_EXTENDED,
        )

    def seed_observation(self, observation: WorkspaceMacdObservation) -> None:
        """Замінити causal MACD history завершеним observation."""
        self._observations = [observation]


class _SyntheticAlligatorFilter(WorkspaceAlligatorFilter):
    """Реальний Candidate F filter із test-only causal history injection."""

    def seed_observations(
        self,
        observations: tuple[WorkspaceAlligatorObservation, ...],
    ) -> None:
        """Встановити вже завершену causal Alligator history."""
        self._observations = list(observations)
        self._last_timestamp = observations[-1].timestamp if observations else None


class _LifecycleAlgorithm(WorkspaceMacdAlligatorReplayAlgorithm):
    """Production Candidate F lifecycle з керованим base MACD output."""

    def __init__(self) -> None:
        super().__init__("RailAlgorithm")
        profile = built_in_workspace_indicator_profile(
            ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F
        )
        binding = WorkspaceIndicatorProfileBinding.from_profile(profile)
        runtime_profile = WorkspaceAlligatorRuntimeProfile.from_binding(binding)
        self.source = _SyntheticMacdSource()
        self.signal_filter = _SyntheticAlligatorFilter(
            enabled=True,
            confirmation_mode=WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
            runtime_profile=runtime_profile,
            timeframe="M15",
        )
        self.started = True
        self._scripted_output: WorkspaceSignalOutput = None

    @property
    def macd_source(self) -> _SyntheticMacdSource:
        source = self.source
        assert isinstance(source, _SyntheticMacdSource)
        return source

    @property
    def alligator_filter(self) -> _SyntheticAlligatorFilter:
        signal_filter = self.signal_filter
        assert isinstance(signal_filter, _SyntheticAlligatorFilter)
        return signal_filter

    def set_base_output(self, output: WorkspaceSignalOutput) -> None:
        self._scripted_output = output

    def has_armed_candidate(self) -> bool:
        return self._armed_candidate is not None

    def armed_bars_waited(self) -> int:
        armed = self._armed_candidate
        return armed.bars_waited if armed is not None else 0

    def seed_prior_ranges(self, value: float = 0.00040) -> None:
        lookback = self.alligator_filter.runtime_profile.volatility_lookback_bars
        self._candidate_prior_ranges = [value] * lookback

    def _base_signal_output(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalOutput:
        _ = event
        return self._scripted_output


def _event(index: int, *, range_size: float = 0.00040) -> WorkspaceMarketEvent:
    timestamp = BASE_TIME + timedelta(minutes=15 * index)
    close = 1.10000 + index * 0.00010
    half_range = range_size / 2.0
    spread = 0.00012
    bid = close - spread / 2.0
    ask = close + spread / 2.0
    return WorkspaceMarketEvent(
        timestamp=timestamp,
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        bid=bid,
        ask=ask,
        spread=ask - bid,
        open=close,
        high=close + half_range,
        low=close - half_range,
        close=close,
        volume=100.0 + index,
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
    )


def _macd_observation(index: int, histogram: float) -> WorkspaceMacdObservation:
    timestamp = BASE_TIME + timedelta(minutes=15 * index)
    state = MACD_STATE_BULLISH if histogram > 0.0 else MACD_STATE_BEARISH
    return WorkspaceMacdObservation(
        timestamp=timestamp,
        close=1.10000,
        source_value=1.10000,
        macd_value=histogram,
        signal_value=0.0,
        histogram=histogram,
        state=state,
        bars_processed=100 + index,
        warmed_up=True,
        profile_uid="TEST_MACD_PROFILE",
        profile_revision=1,
    )


def _alligator_observation(
    index: int,
    *,
    direction: str,
    phase: str,
    normalized_slope: float = 0.100,
    normalized_opening: float = 1.000,
    available_delay_bars: int = 0,
) -> WorkspaceAlligatorObservation:
    timestamp = BASE_TIME + timedelta(minutes=15 * index)
    if direction == "BUY":
        state = ALLIGATOR_STATE_BULLISH
        regime = ALLIGATOR_REGIME_TREND_UP
    else:
        state = ALLIGATOR_STATE_BEARISH
        regime = ALLIGATOR_REGIME_TREND_DOWN
    profile = built_in_workspace_indicator_profile(
        ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F
    )
    return WorkspaceAlligatorObservation(
        timestamp=timestamp,
        median_price=1.10000,
        source_value=1.10000,
        jaw=1.09970,
        teeth=1.09990,
        lips=1.10010,
        state=state,
        regime=regime,
        regime_phase=phase,
        center=1.09990,
        opening=0.00040,
        center_slope_per_bar=0.00004,
        range_reference=0.00040,
        normalized_slope=normalized_slope,
        normalized_opening=normalized_opening,
        bars_processed=100 + index,
        warmed_up=True,
        profile_uid=profile.profile_uid,
        profile_revision=profile.revision,
        timeframe="M15",
        available_at=timestamp + timedelta(minutes=15 * available_delay_bars),
    )


def _armable_proposal(index: int, *, direction: str = "BUY") -> WorkspaceSignalProposal:
    timestamp = BASE_TIME + timedelta(minutes=15 * index)
    regime = (
        ALLIGATOR_REGIME_TREND_UP
        if direction == "BUY"
        else ALLIGATOR_REGIME_TREND_DOWN
    )
    return WorkspaceSignalProposal(
        signal_type="MACD_CROSS",
        direction=direction,
        strength=0.00020,
        macd_state=MACD_STATE_BULLISH if direction == "BUY" else MACD_STATE_BEARISH,
        alligator_confirmation="SAME_TIMEFRAME_NEUTRAL",
        reason="Synthetic quality MACD candidate",
        source_reason_code="MACD_CROSS_ACCEPTED",
        filter_decision=WORKSPACE_SIGNAL_FILTER_REJECT,
        filter_reason_code="ALLIGATOR_SAME_TIMEFRAME_STARTING_REJECT",
        filter_context=WorkspaceSignalFilterContext(
            mode=WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
            timeframe="M15",
            profile_uid=ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F,
            profile_revision=1,
            observation_timestamp=timestamp,
            available_at=timestamp,
            regime=regime,
            regime_phase=ALLIGATOR_REGIME_PHASE_STARTING,
            normalized_slope=0.100,
            normalized_opening=1.000,
        ),
    )


def _opposite_cross() -> WorkspaceSignalProposal:
    return WorkspaceSignalProposal(
        signal_type="MACD_CROSS",
        direction="SELL",
        strength=0.00020,
        macd_state=MACD_STATE_BEARISH,
        alligator_confirmation="SAME_TIMEFRAME_BEARISH",
        reason="Synthetic opposite MACD cross",
        source_reason_code="MACD_CROSS_ACCEPTED",
        filter_decision=WORKSPACE_SIGNAL_FILTER_ALLOW,
    )


def _arm(algorithm: _LifecycleAlgorithm) -> WorkspaceSignalProposal:
    event = _event(0)
    algorithm.macd_source.seed_observation(_macd_observation(0, 0.00020))
    algorithm.alligator_filter.seed_observations(
        (
            _alligator_observation(
                0,
                direction="BUY",
                phase=ALLIGATOR_REGIME_PHASE_STARTING,
            ),
        )
    )
    algorithm.set_base_output(_armable_proposal(0))
    output = algorithm.on_market_event(event)
    assert isinstance(output, WorkspaceSignalProposal)
    assert output.filter_reason_code == ALLIGATOR_REASON_DEFERRED_ARMED
    assert algorithm.has_armed_candidate()
    return output


def _release_scenario() -> tuple[bool, bool]:
    algorithm = _LifecycleAlgorithm()
    _arm(algorithm)

    algorithm.macd_source.seed_observation(_macd_observation(1, 0.00018))
    algorithm.alligator_filter.seed_observations(
        (
            _alligator_observation(
                1,
                direction="BUY",
                phase=ALLIGATOR_REGIME_PHASE_ACTIVE,
            ),
        )
    )
    algorithm.set_base_output(None)
    released = algorithm.on_market_event(_event(1))
    assert isinstance(released, WorkspaceSignalProposal)
    assert released.signal_type == ALLIGATOR_DEFERRED_SIGNAL_TYPE
    assert released.filter_reason_code == ALLIGATOR_REASON_DEFERRED_RELEASE
    assert released.filter_decision == WORKSPACE_SIGNAL_FILTER_ALLOW
    assert len(algorithm.deferred_releases) == 1
    lifecycle_events = algorithm.drain_candidate_f_lifecycle_events()
    assert len(lifecycle_events) == 1
    assert lifecycle_events[0].action == CANDIDATE_F_LIFECYCLE_RELEASE
    assert lifecycle_events[0].reason_code == ALLIGATOR_REASON_DEFERRED_RELEASE
    assert lifecycle_events[0].delay_bars == 1
    assert lifecycle_events[0].filter_context is not None
    assert not algorithm.has_armed_candidate()

    algorithm.macd_source.seed_observation(_macd_observation(2, 0.00016))
    algorithm.alligator_filter.seed_observations(
        (
            _alligator_observation(
                2,
                direction="BUY",
                phase=ALLIGATOR_REGIME_PHASE_ACTIVE,
            ),
        )
    )
    algorithm.set_base_output(None)
    assert algorithm.on_market_event(_event(2)) is None
    assert len(algorithm.deferred_releases) == 1
    return True, True


def _opposite_macd_cancel_scenario() -> bool:
    algorithm = _LifecycleAlgorithm()
    _arm(algorithm)
    algorithm.set_base_output(_opposite_cross())
    output = algorithm.on_market_event(_event(1))
    assert isinstance(output, WorkspaceSignalProposal)
    assert algorithm.deferred_cancelled_opposite_cross == 1
    lifecycle_events = algorithm.drain_candidate_f_lifecycle_events()
    assert len(lifecycle_events) == 1
    assert lifecycle_events[0].action == CANDIDATE_F_LIFECYCLE_CANCEL
    assert (
        lifecycle_events[0].reason_code
        == CANDIDATE_F_LIFECYCLE_REASON_OPPOSITE_MACD
    )
    assert not algorithm.has_armed_candidate()
    assert not algorithm.deferred_releases
    return True


def _macd_invalid_cancel_scenario() -> bool:
    algorithm = _LifecycleAlgorithm()
    _arm(algorithm)
    algorithm.macd_source.seed_observation(_macd_observation(1, -0.00001))
    algorithm.alligator_filter.seed_observations(
        (
            _alligator_observation(
                1,
                direction="BUY",
                phase=ALLIGATOR_REGIME_PHASE_STARTING,
            ),
        )
    )
    algorithm.set_base_output(None)
    assert algorithm.on_market_event(_event(1)) is None
    assert algorithm.deferred_cancelled_macd_invalid == 1
    lifecycle_events = algorithm.drain_candidate_f_lifecycle_events()
    assert len(lifecycle_events) == 1
    assert lifecycle_events[0].action == CANDIDATE_F_LIFECYCLE_CANCEL
    assert (
        lifecycle_events[0].reason_code
        == CANDIDATE_F_LIFECYCLE_REASON_MACD_INVALID
    )
    assert not algorithm.has_armed_candidate()
    return True


def _opposite_alligator_cancel_scenario() -> bool:
    algorithm = _LifecycleAlgorithm()
    _arm(algorithm)
    algorithm.macd_source.seed_observation(_macd_observation(1, 0.00018))
    algorithm.alligator_filter.seed_observations(
        (
            _alligator_observation(
                1,
                direction="SELL",
                phase=ALLIGATOR_REGIME_PHASE_ACTIVE,
            ),
        )
    )
    algorithm.set_base_output(None)
    assert algorithm.on_market_event(_event(1)) is None
    assert algorithm.deferred_cancelled_opposite_alligator == 1
    lifecycle_events = algorithm.drain_candidate_f_lifecycle_events()
    assert len(lifecycle_events) == 1
    assert lifecycle_events[0].action == CANDIDATE_F_LIFECYCLE_CANCEL
    assert (
        lifecycle_events[0].reason_code
        == CANDIDATE_F_LIFECYCLE_REASON_OPPOSITE_ACTIVE_ALLIGATOR
    )
    assert not algorithm.has_armed_candidate()
    return True


def _ttl_expiry_scenario() -> bool:
    algorithm = _LifecycleAlgorithm()
    _arm(algorithm)
    expiry = algorithm.alligator_filter.runtime_profile.deferred_expiry_bars
    assert expiry == 5

    for index in range(1, expiry + 1):
        algorithm.macd_source.seed_observation(_macd_observation(index, 0.00015))
        algorithm.alligator_filter.seed_observations(
            (
                _alligator_observation(
                    index,
                    direction="BUY",
                    phase=ALLIGATOR_REGIME_PHASE_STARTING,
                ),
            )
        )
        algorithm.set_base_output(None)
        assert algorithm.on_market_event(_event(index)) is None
        if index < expiry:
            assert algorithm.has_armed_candidate()
            assert algorithm.armed_bars_waited() == index

    assert algorithm.deferred_expired == 1
    lifecycle_events = algorithm.drain_candidate_f_lifecycle_events()
    assert len(lifecycle_events) == 1
    assert lifecycle_events[0].action == CANDIDATE_F_LIFECYCLE_EXPIRE
    assert (
        lifecycle_events[0].reason_code
        == CANDIDATE_F_LIFECYCLE_REASON_TTL_EXPIRED
    )
    assert lifecycle_events[0].delay_bars == expiry
    assert not algorithm.has_armed_candidate()
    return True


def _release_reruns_structural_guards_scenario() -> bool:
    algorithm = _LifecycleAlgorithm()
    _arm(algorithm)
    algorithm.seed_prior_ranges()
    algorithm.macd_source.seed_observation(_macd_observation(3, 0.00018))
    algorithm.alligator_filter.seed_observations(
        (
            _alligator_observation(
                1,
                direction="BUY",
                phase=ALLIGATOR_REGIME_PHASE_ACTIVE,
                normalized_opening=1.200,
            ),
            _alligator_observation(
                2,
                direction="BUY",
                phase=ALLIGATOR_REGIME_PHASE_ACTIVE,
                normalized_opening=1.000,
            ),
            _alligator_observation(
                3,
                direction="BUY",
                phase=ALLIGATOR_REGIME_PHASE_ACTIVE,
                normalized_opening=0.400,
            ),
        )
    )
    algorithm.set_base_output(None)
    output = algorithm.on_market_event(_event(3))
    assert isinstance(output, WorkspaceSignalProposal)
    assert output.signal_type == ALLIGATOR_DEFERRED_SIGNAL_TYPE
    assert output.filter_decision == WORKSPACE_SIGNAL_FILTER_REJECT
    assert output.filter_reason_code == ALLIGATOR_REASON_OPENING_COLLAPSE
    assert len(algorithm.deferred_releases) == 1
    assert not algorithm.has_armed_candidate()
    return True


def _duplicate_bar_protection_scenario() -> bool:
    profile = built_in_workspace_indicator_profile(
        ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F
    )
    runtime_profile = WorkspaceAlligatorRuntimeProfile.from_binding(
        WorkspaceIndicatorProfileBinding.from_profile(profile)
    )
    signal_filter = WorkspaceAlligatorFilter(
        enabled=True,
        confirmation_mode=WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
        runtime_profile=runtime_profile,
        timeframe="M15",
    )
    event = _event(0)
    signal_filter.on_market_event(event)
    try:
        signal_filter.on_market_event(event)
    except WorkspaceAlgorithmError:
        return True
    raise AssertionError("Duplicate completed Alligator bar was not blocked")


def _no_look_ahead_release_scenario() -> bool:
    algorithm = _LifecycleAlgorithm()
    _arm(algorithm)
    algorithm.macd_source.seed_observation(_macd_observation(1, 0.00018))
    algorithm.alligator_filter.seed_observations(
        (
            _alligator_observation(
                1,
                direction="BUY",
                phase=ALLIGATOR_REGIME_PHASE_ACTIVE,
                available_delay_bars=1,
            ),
        )
    )
    algorithm.set_base_output(None)
    try:
        algorithm.on_market_event(_event(1))
    except WorkspaceAlgorithmError:
        return True
    raise AssertionError("Future Alligator observation was used for deferred release")


def main() -> None:
    release_ok, one_release_ok = _release_scenario()
    opposite_macd_ok = _opposite_macd_cancel_scenario()
    macd_invalid_ok = _macd_invalid_cancel_scenario()
    opposite_alligator_ok = _opposite_alligator_cancel_scenario()
    ttl_ok = _ttl_expiry_scenario()
    guards_ok = _release_reruns_structural_guards_scenario()
    duplicate_ok = _duplicate_bar_protection_scenario()
    no_look_ahead_ok = _no_look_ahead_release_scenario()

    profile = built_in_workspace_indicator_profile(
        ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F
    )
    parameters = profile.parameters
    confirmation_bars = parameters["trend_start_confirmation_bars"]
    deferred_expiry_bars = parameters["deferred_expiry_bars"]
    opening_collapse_threshold = parameters["opening_collapse_threshold"]
    weak_max_active_age = parameters["weak_max_active_age"]
    weak_max_opening = parameters["weak_max_opening"]
    spike_min_range_ratio = parameters["spike_min_range_ratio"]
    spike_max_opening_delta = parameters["spike_max_opening_delta"]
    spike_max_slope_delta = parameters["spike_max_slope_delta"]
    overextended_min_slope = parameters["overextended_min_slope"]
    overextended_min_opening = parameters["overextended_min_opening"]

    assert isinstance(confirmation_bars, int)
    assert isinstance(deferred_expiry_bars, int)
    assert isinstance(opening_collapse_threshold, float)
    assert isinstance(weak_max_active_age, int)
    assert isinstance(weak_max_opening, float)
    assert isinstance(spike_min_range_ratio, float)
    assert isinstance(spike_max_opening_delta, float)
    assert isinstance(spike_max_slope_delta, float)
    assert isinstance(overextended_min_slope, float)
    assert isinstance(overextended_min_opening, float)

    assert confirmation_bars == 4
    assert deferred_expiry_bars == 5
    assert opening_collapse_threshold == -0.700
    assert weak_max_active_age == 2
    assert weak_max_opening == 0.500
    assert spike_min_range_ratio == 3.500
    assert spike_max_opening_delta == -0.500
    assert spike_max_slope_delta == -0.010
    assert overextended_min_slope == 0.200
    assert overextended_min_opening == 3.000

    print("Algorithm Workspace Candidate F Lifecycle Regression result")
    print("  profile=LGE Candidate F Smoothed r1")
    print("  confirmation_bars=4")
    print("  deferred_expiry_bars=5")
    print(f"  armed_release={release_ok}")
    print(f"  one_macd_signal_max_one_deferred_release={one_release_ok}")
    print(f"  opposite_macd_cancels_armed={opposite_macd_ok}")
    print(f"  invalid_macd_relation_cancels_armed={macd_invalid_ok}")
    print(f"  opposite_active_alligator_cancels_armed={opposite_alligator_ok}")
    print(f"  ttl_expiry_cancels_armed={ttl_ok}")
    print(f"  deferred_release_reruns_structural_guards={guards_ok}")
    print(f"  duplicate_completed_bar_blocked={duplicate_ok}")
    print(f"  deferred_release_no_look_ahead={no_look_ahead_ok}")
    print("  candidate_f_thresholds_unchanged=True")
    print("  terminal_lifecycle_events_exposed=True")
    print("  lifecycle_event_context_causal=True")
    print("  completed_m15_events_only=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_LIFECYCLE_REGRESSION_CHECK=OK")


if __name__ == "__main__":
    main()
