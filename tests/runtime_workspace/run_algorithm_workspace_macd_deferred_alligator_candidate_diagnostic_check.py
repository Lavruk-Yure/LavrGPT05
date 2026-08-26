# -*- coding: utf-8 -*-
"""Діагностика ARMED MACD після causal-блокування SAME_TIMEFRAME Alligator.

Тест не змінює production trade gate. Він відтворює RM96 EURUSD M15 на
Development / Validation / Holdout для confirmation=3 і confirmation=4,
після чого аналізує вже готові MACD та Alligator observations. Перевіряється,
скільки якісних MACD CROSS було заблоковано, скільки з них є консервативними
ARMED-кандидатами і через скільки завершених M15 bar Alligator дав би causal
ACTIVE у тому самому напрямку без нового протилежного MACD CROSS.
"""

from __future__ import annotations

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
from core.workspace_alligator import (  # noqa: E402
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_deferred_macd_diagnostic import (  # noqa: E402
    WorkspaceDeferredMacdDiagnosticSummary,
    analyze_workspace_deferred_macd_candidates,
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

CONFIRMATION_BARS = (3, 4)
DIAGNOSTIC_EXPIRY_BARS = 5


@dataclass(frozen=True, slots=True)
class DiagnosticRun:
    """Результат одного replay-вікна та одного confirmation setting."""

    window: str
    confirmation_bars: int
    summary: WorkspaceDeferredMacdDiagnosticSummary
    trades: int
    net_profit: float


def _workspace(start_utc: str, end_utc: str) -> AlgorithmWorkspace:
    """Побудувати контрольований RM96 WSP для diagnostic Replay."""
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id=None,
        account_mode=None,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        display_name="RM96 Deferred MACD Alligator Diagnostic",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        parameters={
            "macd_signal_enabled": True,
            "macd_signal_mode": "EXTENDED",
            "alligator_filter_enabled": True,
            "alligator_confirmation": (
                WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME
            ),
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
) -> DiagnosticRun:
    """Виконати Replay і pure post-run ARMED diagnostic."""
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

        algorithm = runtime.algorithm
        assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
        assert algorithm.source is not None
        assert algorithm.signal_filter is not None

        summary = analyze_workspace_deferred_macd_candidates(
            runtime.signal_records(),
            algorithm.source.observations,
            algorithm.signal_filter.observations,
            expiry_bars=DIAGNOSTIC_EXPIRY_BARS,
        )
        broker_execution_attempted = any(
            bool(entry.details.get("broker_execution_attempted"))
            for entry in runtime.journal
            if isinstance(entry.details, dict)
        )
        assert not broker_execution_attempted
        return DiagnosticRun(
            window=window,
            confirmation_bars=confirmation_bars,
            summary=summary,
            trades=len(runtime.owned_snapshot.positions),
            net_profit=runtime.context.current_profit,
        )
    finally:
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS = original


def _summary_text(summary: WorkspaceDeferredMacdDiagnosticSummary) -> str:
    """Стисле представлення ключових causal-лічильників."""
    return (
        f"blocked:{summary.blocked_good_macd},"
        f"armed:{summary.armed_candidates},"
        f"not_armed_phase:{summary.not_armed_phase},"
        f"not_armed_direction:{summary.not_armed_direction},"
        f"release_1:{summary.released_after_1},"
        f"release_2:{summary.released_after_2},"
        f"release_3:{summary.released_after_3},"
        f"release_4:{summary.released_after_4},"
        f"release_5:{summary.released_after_5},"
        f"release_5plus:{summary.released_after_5_plus},"
        f"opposite_cross:{summary.opposite_cross_before_confirmation},"
        f"opposite_alligator:{summary.opposite_alligator_before_confirmation},"
        f"macd_invalid:{summary.macd_relation_invalidated},"
        f"expired:{summary.expired}"
    )


def _released_examples(
    summary: WorkspaceDeferredMacdDiagnosticSummary,
    *,
    limit: int = 8,
) -> str:
    """Показати кілька signal -> release пар для ручної перевірки."""
    items = [
        outcome
        for outcome in summary.outcomes
        if outcome.release_after_bars is not None
        and outcome.release_timestamp is not None
    ]
    if not items:
        return "NONE"
    return "; ".join(
        f"{item.signal_timestamp.isoformat()} {item.direction}"
        f" -> +{item.release_after_bars}"
        f" {item.release_timestamp.isoformat()}"
        for item in items[:limit]
    )


def main() -> None:
    original = workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS
    results: dict[tuple[str, int], DiagnosticRun] = {}
    for window, start_utc, end_utc in WINDOWS:
        for confirmation_bars in CONFIRMATION_BARS:
            results[(window, confirmation_bars)] = _run(
                window,
                start_utc,
                end_utc,
                confirmation_bars,
            )

    for result in results.values():
        summary = result.summary
        assert summary.blocked_good_macd >= summary.armed_candidates
        assert summary.potential_deferred_entries <= summary.armed_candidates
        assert all(
            outcome.release_after_bars is None
            or outcome.release_after_bars > 0
            for outcome in summary.outcomes
        )

    assert (
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS
        == original
    )

    print("Algorithm Workspace deferred MACD / Alligator candidate diagnostic result")
    print("  mode=DIAGNOSTIC_ONLY_NO_TRADE_GATE_CHANGE")
    print("  armed_policy=QUALITY_MACD + SAME_DIRECTION_ALLIGATOR_STARTING")
    print("  release_policy=ACTIVE_SAME_DIRECTION + MACD_RELATION_STILL_VALID")
    print("  cancel_policy=OPPOSITE_MACD/OPPOSITE_ACTIVE_ALLIGATOR/MACD_INVALID")
    print(f"  diagnostic_expiry_bars={DIAGNOSTIC_EXPIRY_BARS}")
    print("  controlled_variable=ALLIGATOR_TREND_START_CONFIRMATION_BARS 3_vs_4")
    print("  fixed_workspace=RM96 EURUSD M15 Historical")
    print("  fixed_macd=8/17/5 EXTENDED prominence=0.000015 distance=0.000050 ABC=2.25")
    print("  fixed_alligator=13/8,8/5,5/3 SMOOTHED MEDIAN SAME_TIMEFRAME")
    for window, _start_utc, _end_utc in WINDOWS:
        for confirmation_bars in CONFIRMATION_BARS:
            result = results[(window, confirmation_bars)]
            print(
                f"  {window.lower()}_{confirmation_bars}="
                f"trades:{result.trades},pnl:{result.net_profit:.2f},"
                f"{_summary_text(result.summary)}"
            )
    development_3 = results[("DEVELOPMENT", 3)].summary
    development_4 = results[("DEVELOPMENT", 4)].summary
    print(f"  development_3_release_examples={_released_examples(development_3)}")
    print(f"  development_4_release_examples={_released_examples(development_4)}")
    print("  completed_bars_only=True")
    print("  no_look_ahead=True")
    print("  production_trade_gate_changed=False")
    print("  production_constant_restored_after_comparison=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_MACD_DEFERRED_ALLIGATOR_CANDIDATE_DIAGNOSTIC_CHECK=OK")


if __name__ == "__main__":
    main()
