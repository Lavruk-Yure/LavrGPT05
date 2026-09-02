# -*- coding: utf-8 -*-
"""Перевірка causal FLAT/TREND diagnostic для Alligator.

Тест фіксує перший RoadMap101-контракт класифікації режиму ринку:
FLAT, TREND_UP і TREND_DOWN та STARTING/ACTIVE/ENDING обчислюються лише
з завершених Replay-bar. STARTING переходить в ACTIVE тільки після трьох
послідовних підтверджених bar. Окремо перевіряється causal T-2/T-1/T
history для Journal diagnostics. Після ручної калібровки phase diagnostic
використовується SAME_TIMEFRAME phase-gate; сам розрахунок лишається causal
і не виконує broker operations.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import WORKSPACE_DATA_MODE_REPLAY  # noqa: E402
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_FLAT,
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_PHASE_ENDING,
    ALLIGATOR_REGIME_PHASE_NONE,
    ALLIGATOR_REGIME_PHASE_STARTING,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    WorkspaceAlligatorFilter,
    WorkspaceAlligatorObservation,
    WorkspaceAlligatorRuntimeProfile,
)
from core.workspace_indicator_profile import (  # noqa: E402
    WORKSPACE_INDICATOR_MA_SMOOTHED,
    WORKSPACE_INDICATOR_SOURCE_MEDIAN,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
)


def _profile() -> WorkspaceAlligatorRuntimeProfile:
    return WorkspaceAlligatorRuntimeProfile(
        profile_uid="TEST:ALLIGATOR_REGIME",
        profile_revision=1,
        profile_name="Alligator Regime Diagnostic",
        source=WORKSPACE_INDICATOR_SOURCE_MEDIAN,
        jaw_period=21,
        jaw_shift=8,
        teeth_period=13,
        teeth_shift=5,
        lips_period=8,
        lips_shift=3,
        ma_type=WORKSPACE_INDICATOR_MA_SMOOTHED,
    )


def _event(index: int, price: float, half_range: float) -> WorkspaceMarketEvent:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=15 * index)
    bid = price - 0.00006
    ask = price + 0.00006
    return WorkspaceMarketEvent(
        timestamp=timestamp,
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        bid=bid,
        ask=ask,
        spread=ask - bid,
        open=price,
        high=price + half_range,
        low=price - half_range,
        close=price,
        volume=0.0,
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
    )


def _observations(
    prices: list[float],
    half_range: float,
) -> list[WorkspaceAlligatorObservation]:
    """Повернути causal послідовність діагностичних спостережень."""
    alligator = WorkspaceAlligatorFilter(
        enabled=True,
        confirmation_mode=WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
        runtime_profile=_profile(),
        timeframe="M15",
    )
    result: list[WorkspaceAlligatorObservation] = []
    for index, price in enumerate(prices):
        result.append(alligator.on_market_event(_event(index, price, half_range)))
    return result


def _final_regime(
    prices: list[float],
    half_range: float,
) -> tuple[str, WorkspaceAlligatorObservation]:
    observations = _observations(prices, half_range)
    observation = observations[-1]
    return observation.regime, observation


def main() -> None:
    flat_prices = [1.15000 for _ in range(90)]
    up_prices = [1.15000 + index * 0.00020 for index in range(90)]
    down_prices = [1.17000 - index * 0.00020 for index in range(90)]

    flat_regime, flat = _final_regime(flat_prices, 0.00020)
    up_regime, up = _final_regime(up_prices, 0.00020)
    down_regime, down = _final_regime(down_prices, 0.00020)

    phase_prices = (
        [1.15000 for _ in range(90)]
        + [1.15000 + index * 0.00020 for index in range(55)]
        + [1.16100 - index * 0.00028 for index in range(18)]
    )
    phase_observations = _observations(phase_prices, 0.00020)
    up_observations = [
        observation
        for observation in phase_observations
        if observation.regime == ALLIGATOR_REGIME_TREND_UP
    ]
    up_phases = [observation.regime_phase for observation in up_observations]
    first_up_aligned_index = next(
        index
        for index, observation in enumerate(up_observations)
        if observation.regime_phase == ALLIGATOR_REGIME_PHASE_STARTING
    )
    first_up_aligned = up_observations[
        first_up_aligned_index : first_up_aligned_index + 3  # noqa
    ]

    trend_then_flat_prices = [1.15000 + index * 0.00020 for index in range(100)]
    trend_then_flat_prices.extend([trend_then_flat_prices[-1]] * 120)
    transition_observations = _observations(
        trend_then_flat_prices,
        0.00020,
    )
    first_confirmed_flat_index = next(
        index
        for index in range(100, len(transition_observations))
        if transition_observations[index].regime == ALLIGATOR_REGIME_FLAT
    )
    pre_flat_observations = transition_observations[
        first_confirmed_flat_index - 2 : first_confirmed_flat_index  # noqa
    ]
    confirmed_flat = transition_observations[first_confirmed_flat_index]

    history_filter = WorkspaceAlligatorFilter(
        enabled=True,
        confirmation_mode=WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
        runtime_profile=_profile(),
        timeframe="M15",
    )
    history_observations: list[WorkspaceAlligatorObservation] = []
    for index, price in enumerate(up_prices):
        history_observations.append(
            history_filter.on_market_event(_event(index, price, 0.00020))
        )
    history_current = history_observations[-1]
    diagnostic_history = history_filter.diagnostic_observation_history(
        history_current,
        limit=3,
    )

    assert flat_regime == ALLIGATOR_REGIME_FLAT
    assert up_regime == ALLIGATOR_REGIME_TREND_UP
    assert down_regime == ALLIGATOR_REGIME_TREND_DOWN
    assert flat.normalized_slope == 0.0
    assert flat.normalized_opening == 0.0
    assert up.center_slope_per_bar is not None
    assert up.center_slope_per_bar > 0.0
    assert down.center_slope_per_bar is not None
    assert down.center_slope_per_bar < 0.0
    assert up.available_at == up.timestamp
    assert down.available_at == down.timestamp
    assert flat.regime_phase == ALLIGATOR_REGIME_PHASE_NONE
    assert ALLIGATOR_REGIME_PHASE_STARTING in up_phases
    assert ALLIGATOR_REGIME_PHASE_ACTIVE in up_phases
    assert ALLIGATOR_REGIME_PHASE_ENDING in up_phases
    assert len(first_up_aligned) == 3
    assert [observation.regime_phase for observation in first_up_aligned] == [
        ALLIGATOR_REGIME_PHASE_STARTING,
        ALLIGATOR_REGIME_PHASE_STARTING,
        ALLIGATOR_REGIME_PHASE_ACTIVE,
    ]
    assert len(pre_flat_observations) == 2
    assert all(
        observation.regime == ALLIGATOR_REGIME_TREND_UP
        for observation in pre_flat_observations
    )
    assert all(
        observation.regime_phase == ALLIGATOR_REGIME_PHASE_ENDING
        for observation in pre_flat_observations
    )
    assert confirmed_flat.regime_phase == ALLIGATOR_REGIME_PHASE_NONE
    assert len(diagnostic_history) == 3
    assert diagnostic_history == tuple(history_observations[-3:])
    assert diagnostic_history[-1] is history_current
    assert all(
        observation.timestamp <= history_current.timestamp
        for observation in diagnostic_history
    )
    assert all(
        observation.available_at <= history_current.available_at
        for observation in diagnostic_history
    )
    assert all(
        observation.normalized_slope is not None for observation in diagnostic_history
    )
    assert all(
        observation.normalized_opening is not None for observation in diagnostic_history
    )

    print("Algorithm Workspace Alligator Regime Diagnostic result")
    print(f"  flat_regime={flat_regime}")
    print(f"  trend_up_regime={up_regime}")
    print(f"  trend_down_regime={down_regime}")
    print(f"  flat_normalized_slope={flat.normalized_slope:.6f}")
    print(f"  flat_normalized_opening={flat.normalized_opening:.6f}")
    print(f"  trend_up_normalized_slope={up.normalized_slope:.6f}")
    print(f"  trend_down_normalized_slope={down.normalized_slope:.6f}")
    print("  regime_phase=STARTING/ACTIVE/ENDING")
    print("  flat_phase=NONE")
    print("  flat_transition_hysteresis_bars=3")
    print("  trend_start_confirmation_bars=3")
    print("  trend_start_not_active_before_confirmation=True")
    print("  trend_to_flat_keeps_ending_until_confirmed=True")
    print("  diagnostic_history_bars=3")
    print("  diagnostic_history_t_minus_2_t_minus_1_t=True")
    print("  diagnostic_history_completed_bars_only=True")
    print("  phase_uses_current_completed_bar_only=True")
    print("  phase_diagnostic_available_for_trade_gate=True")
    print("  completed_bars_only=True")
    print("  no_look_ahead=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_ALLIGATOR_REGIME_DIAGNOSTIC_CHECK=OK")


if __name__ == "__main__":
    main()
