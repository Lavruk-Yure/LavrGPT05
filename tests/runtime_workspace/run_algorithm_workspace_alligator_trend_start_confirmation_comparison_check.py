# -*- coding: utf-8 -*-
"""Порівняння 3-bar і 4-bar підтвердження старту тренду Alligator.

Тест відтворює канонічний RM96 EURUSD M15 Historical на тому самому M1 CSV
і змінює лише ``ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS``. Окремо
рахуються Development, Validation і Holdout. Production-константа після
кожного запуску відновлюється; broker execution не виконується.

Мета — не змінити trade gate автоматично, а виміряти, які саме угоди
прибирає додатковий causal bar підтвердження та чи змінюється OOS-результат.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import core.workspace_alligator as workspace_alligator  # noqa: E402
from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_indicator_profile import (  # noqa: E402
    new_workspace_indicator_profile_bindings,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
    WORKSPACE_REPLAY_SOURCE_CSV,
)

HISTORY_FILE = (
    PROJECT_ROOT
    / "data"
    / "history"
    / "IB"
    / "EURUSD"
    / "M1"
    / "2026-01-02_2026-08-11_IB_EURUSD_M1.csv"
)

WINDOWS = (
    (
        "DEVELOPMENT",
        "2026-01-02T00:00:00+00:00",
        "2026-02-28T00:00:00+00:00",
    ),
    (
        "VALIDATION",
        "2026-03-01T00:00:00+00:00",
        "2026-05-31T23:59:00+00:00",
    ),
    (
        "HOLDOUT",
        "2026-06-01T00:00:00+00:00",
        "2026-08-11T08:24:00+00:00",
    ),
)

CURRENT_CONFIRMATION_BARS = 3
CANDIDATE_CONFIRMATION_BARS = 4
CURRENT_SINGLE_DEV_SL_SIGNAL = "2026-01-28T05:00:00+00:00"


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    """Один deterministic Replay result для однієї комбінації."""

    window: str
    confirmation_bars: int
    trades: int
    winners: int
    losers: int
    stop_loss_closes: int
    profit_drawdown_closes: int
    net_profit: float
    position_signatures: tuple[tuple[str, str, str, float], ...]


def _workspace(start_utc: str, end_utc: str) -> AlgorithmWorkspace:
    """Побудувати статичний еквівалент поточного RM96 WSP."""
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id=None,
        account_mode=None,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        display_name="RM96 Alligator Confirmation Comparison",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        parameters={
            "macd_signal_enabled": True,
            "macd_signal_mode": "EXTENDED",
            "alligator_filter_enabled": True,
            "alligator_confirmation": (WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME),
            "spread_limit": 0.00020,
            "warmup_bars": 3,
            "macd_extremum_min_prominence": 0.000015,
            "macd_extremum_to_cross_min_distance": 0.000050,
            "macd_cross_min_angle": 45.0,
            "macd_cross_angle_model": "ABC_REALTIME_SCALED",
            "macd_cross_min_abc_angle": 2.25,
        },
        risk_settings={
            "risk_percent": 0.5,
            "maximum_position_volume": 1000.0,
            "maximum_open_positions": 2,
            "max_daily_loss_percent": 2.0,
            "require_stop_loss": True,
        },
        profit_protection={
            "enabled": True,
            "activation_mode": "AFTER_SPREAD",
            "max_profit_drawdown_percent": 30.0,
            "minimum_profit": 0.0,
        },
        replay_settings={
            "source_type": WORKSPACE_REPLAY_SOURCE_CSV,
            "file_path": str(HISTORY_FILE),
            "start_utc": start_utc,
            "end_utc": end_utc,
            "source_timezone": "UTC",
            "delimiter": "AUTO",
            "decimal_separator": ".",
            "spread": 0.00012,
            "source": "2026-01-02_2026-08-11_IB_EURUSD_M1",
            "source_timeframe": "M1",
            "risk_equity": 1000.0,
            "speed": -1,
        },
        indicator_profile_bindings=new_workspace_indicator_profile_bindings(),
    )


def _run(
    window: str,
    start_utc: str,
    end_utc: str,
    confirmation_bars: int,
) -> ComparisonResult:
    """Виконати один Replay з локальною зміною confirmation bars."""
    original = workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS
    try:
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS = (
            confirmation_bars
        )
        runtime = WorkspaceRuntime(
            _workspace(start_utc, end_utc),
            algorithm_factory=create_registered_workspace_algorithm,
        )
        runtime.begin_start()
        runtime.complete_start()
        session = runtime.replay_session
        assert session is not None
        while not session.completed:
            runtime.advance_replay()

        snapshot = runtime.owned_snapshot
        positions = tuple(snapshot.positions)
        winners = sum(position.current_profit > 0.0 for position in positions)
        losers = sum(position.current_profit < 0.0 for position in positions)
        stop_loss_closes = sum(
            position.close_reason == "STOP_LOSS" for position in positions
        )
        profit_drawdown_closes = sum(
            position.close_reason == "PROFIT_DRAWDOWN" for position in positions
        )
        signatures = tuple(
            (
                str(position.signal_timestamp or ""),
                position.side,
                str(position.close_reason or ""),
                round(position.current_profit, 2),
            )
            for position in positions
        )
        broker_execution_attempted = any(
            bool(entry.details.get("broker_execution_attempted"))
            for entry in runtime.journal
            if isinstance(entry.details, dict)
        )
        assert not broker_execution_attempted

        return ComparisonResult(
            window=window,
            confirmation_bars=confirmation_bars,
            trades=len(positions),
            winners=winners,
            losers=losers,
            stop_loss_closes=stop_loss_closes,
            profit_drawdown_closes=profit_drawdown_closes,
            net_profit=runtime.context.current_profit,
            position_signatures=signatures,
        )
    finally:
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS = original


def _same_metrics(left: ComparisonResult, right: ComparisonResult) -> bool:
    """Порівняти ключові OOS-метрики без урахування параметра."""
    return bool(
        left.trades == right.trades
        and left.winners == right.winners
        and left.losers == right.losers
        and left.stop_loss_closes == right.stop_loss_closes
        and left.profit_drawdown_closes == right.profit_drawdown_closes
        and math.isclose(
            left.net_profit,
            right.net_profit,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        and left.position_signatures == right.position_signatures
    )


def _format_removed(
    current: ComparisonResult,
    candidate: ComparisonResult,
) -> str:
    """Повернути читабельний список угод, прибраних candidate."""
    candidate_keys = {
        (timestamp, side)
        for timestamp, side, _reason, _profit in candidate.position_signatures
    }
    removed = [
        signature
        for signature in current.position_signatures
        if (signature[0], signature[1]) not in candidate_keys
    ]
    return (
        "; ".join(
            f"{timestamp} {side} {reason} {profit:+.2f}"
            for timestamp, side, reason, profit in removed
        )
        or "NONE"
    )


def main() -> None:
    original = workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS
    results: dict[tuple[str, int], ComparisonResult] = {}
    for window, start_utc, end_utc in WINDOWS:
        for confirmation_bars in (
            CURRENT_CONFIRMATION_BARS,
            CANDIDATE_CONFIRMATION_BARS,
        ):
            result = _run(
                window,
                start_utc,
                end_utc,
                confirmation_bars,
            )
            results[(window, confirmation_bars)] = result

    development_current = results[("DEVELOPMENT", CURRENT_CONFIRMATION_BARS)]
    development_candidate = results[("DEVELOPMENT", CANDIDATE_CONFIRMATION_BARS)]
    validation_current = results[("VALIDATION", CURRENT_CONFIRMATION_BARS)]
    validation_candidate = results[("VALIDATION", CANDIDATE_CONFIRMATION_BARS)]
    holdout_current = results[("HOLDOUT", CURRENT_CONFIRMATION_BARS)]
    holdout_candidate = results[("HOLDOUT", CANDIDATE_CONFIRMATION_BARS)]

    current_dev_signals = {
        timestamp
        for timestamp, _side, _reason, _profit in development_current.position_signatures
    }
    candidate_dev_signals = {
        timestamp
        for timestamp, _side, _reason, _profit in development_candidate.position_signatures
    }

    assert development_current.trades == 9
    assert development_current.stop_loss_closes == 1
    assert math.isclose(
        development_current.net_profit,
        -1.06,
        rel_tol=0.0,
        abs_tol=1e-9,
    )
    assert development_candidate.trades == 7
    assert development_candidate.stop_loss_closes == 0
    assert math.isclose(
        development_candidate.net_profit,
        1.01,
        rel_tol=0.0,
        abs_tol=1e-9,
    )
    assert CURRENT_SINGLE_DEV_SL_SIGNAL in current_dev_signals
    assert CURRENT_SINGLE_DEV_SL_SIGNAL not in candidate_dev_signals
    assert _same_metrics(validation_current, validation_candidate)
    assert _same_metrics(holdout_current, holdout_candidate)
    assert (
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS == original
    )

    print("Algorithm Workspace Alligator trend-start confirmation comparison result")
    print("  controlled_variable=ALLIGATOR_TREND_START_CONFIRMATION_BARS")
    print("  fixed_workspace=RM96 EURUSD M15 Historical")
    print("  fixed_macd=8/17/5 EXTENDED prominence=0.000015 distance=0.000050 ABC=2.25")
    print("  fixed_alligator=13/8,8/5,5/3 SMOOTHED MEDIAN SAME_TIMEFRAME")
    for window, _start_utc, _end_utc in WINDOWS:
        current = results[(window, CURRENT_CONFIRMATION_BARS)]
        candidate = results[(window, CANDIDATE_CONFIRMATION_BARS)]
        print(
            f"  {window.lower()}_3="
            f"trades:{current.trades},wins:{current.winners},losses:{current.losers},"
            f"sl:{current.stop_loss_closes},pnl:{current.net_profit:.2f}"
        )
        print(
            f"  {window.lower()}_4="
            f"trades:{candidate.trades},wins:{candidate.winners},"
            f"losses:{candidate.losers},"
            f"sl:{candidate.stop_loss_closes},pnl:{candidate.net_profit:.2f}"
        )
    print(
        "  development_removed_by_4="
        f"{_format_removed(development_current, development_candidate)}"
    )
    print("  candidate_4_blocks_current_single_dev_sl=True")
    print("  candidate_4_validation_unchanged=True")
    print("  candidate_4_holdout_unchanged=True")
    print("  production_constant_restored_after_comparison=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_ALLIGATOR_TREND_START_CONFIRMATION_COMPARISON_CHECK=OK")


if __name__ == "__main__":
    main()
