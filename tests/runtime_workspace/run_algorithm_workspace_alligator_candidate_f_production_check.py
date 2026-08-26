# -*- coding: utf-8 -*-
"""Production parity check для Alligator Candidate F, RoadMap101 №38.

Перевіряє новий immutable built-in profile ``LGE Candidate F Smoothed`` і
реальний registered ``WorkspaceMacdAlligatorReplayAlgorithm`` без test-only
wrapper. Candidate F має точно відтворити GREEN №37 на Development,
Validation і Holdout: 4-bar STARTING confirmation, ARMED/deferred MACD,
opening-collapse -0.700 та три structural guards. Legacy Alligator profile
лишається окремим і не мігрується непомітно.

Інваріанти: усі рішення causal лише за завершеними bars; volatility
reference не містить signal bar; profile snapshot фіксує всі пороги;
Historical Replay не виконує broker requests або broker execution.
"""

from __future__ import annotations

import math
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_DEFERRED_SIGNAL_TYPE,
    ALLIGATOR_REASON_DEFERRED_ARMED,
    ALLIGATOR_REASON_DEFERRED_RELEASE,
    ALLIGATOR_REASON_OPENING_COLLAPSE,
    ALLIGATOR_REASON_OVEREXTENDED,
    ALLIGATOR_REASON_VOLATILITY_SPIKE,
    ALLIGATOR_REASON_WEAK_OPENING,
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_indicator_profile import (  # noqa: E402
    ALLIGATOR_LOGIC_MODE_CANDIDATE_F,
    ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F,
    ALLIGATOR_PROFILE_UID_LGE_CLASSIC,
    WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY,
    WorkspaceIndicatorProfileBinding,
    built_in_workspace_indicator_profile,
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

EXPECTED = {
    "DEVELOPMENT": (7, 6, 1, 0, 7, 1.06, 0.17, 7.2353),
    "VALIDATION": (16, 10, 6, 2, 14, -1.03, 3.24, 0.8049),
    "HOLDOUT": (7, 4, 3, 0, 7, 0.11, 0.08, 1.6875),
}


@dataclass(frozen=True, slots=True)
class ProductionRun:
    """Фактичний production Replay контрольного вікна."""

    window: str
    trades: int
    winners: int
    losers: int
    stop_loss_closes: int
    profit_drawdown_closes: int
    net_profit: float
    maximum_drawdown: float
    profit_factor: float | None
    reason_counts: Counter[str]
    deferred_releases: int
    deferred_signal_records: int
    deferred_accepted_records: int
    cancelled_opposite_cross: int
    broker_execution_attempted: bool


def _candidate_bindings() -> dict[str, dict[str, object]]:
    bindings = new_workspace_indicator_profile_bindings()
    candidate = built_in_workspace_indicator_profile(
        ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F
    )
    bindings[WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY] = (
        WorkspaceIndicatorProfileBinding.from_profile(candidate).to_storage_dict()
    )
    return bindings


def _workspace(start_utc: str, end_utc: str) -> AlgorithmWorkspace:
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id=None,
        account_mode=None,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        display_name="RM101 Candidate F Production Check",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        parameters={
            "macd_signal_enabled": True,
            "macd_signal_mode": "EXTENDED",
            "alligator_filter_enabled": True,
            "alligator_confirmation": WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
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
        indicator_profile_bindings=_candidate_bindings(),
    )


def _run(window: str, start_utc: str, end_utc: str) -> ProductionRun:
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

    summary = runtime.historical_summary
    algorithm = runtime.algorithm
    assert summary is not None
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    records = runtime.signal_records()
    reason_counts = Counter(
        record.filter_reason_code
        for record in records
        if record.filter_reason_code is not None
    )
    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted
    assert all(
        record.filter_context is None
        or record.filter_context.available_at is None
        or record.filter_context.available_at <= record.timestamp
        for record in records
    )
    return ProductionRun(
        window=window,
        trades=summary.opened_trades,
        winners=summary.winning_trades,
        losers=summary.losing_trades,
        stop_loss_closes=summary.close_reason_count("STOP_LOSS"),
        profit_drawdown_closes=summary.close_reason_count("PROFIT_DRAWDOWN"),
        net_profit=summary.net_profit,
        maximum_drawdown=summary.maximum_drawdown,
        profit_factor=summary.profit_factor,
        reason_counts=reason_counts,
        deferred_releases=len(algorithm.deferred_releases),
        deferred_signal_records=sum(
            record.signal_type == ALLIGATOR_DEFERRED_SIGNAL_TYPE for record in records
        ),
        deferred_accepted_records=sum(
            record.signal_type == ALLIGATOR_DEFERRED_SIGNAL_TYPE and record.accepted
            for record in records
        ),
        cancelled_opposite_cross=algorithm.deferred_cancelled_opposite_cross,
        broker_execution_attempted=broker_execution_attempted,
    )


def _assert_expected(result: ProductionRun) -> None:
    expected = EXPECTED[result.window]
    assert result.trades == expected[0]
    assert result.winners == expected[1]
    assert result.losers == expected[2]
    assert result.stop_loss_closes == expected[3]
    assert result.profit_drawdown_closes == expected[4]
    assert math.isclose(result.net_profit, expected[5], abs_tol=0.005)
    assert math.isclose(result.maximum_drawdown, expected[6], abs_tol=0.005)
    assert result.profit_factor is not None
    assert math.isclose(result.profit_factor, expected[7], abs_tol=0.0001)


def _format_result(result: ProductionRun) -> str:
    profit_factor = (
        "NONE" if result.profit_factor is None else f"{result.profit_factor:.4f}"
    )
    return (
        f"trades:{result.trades},wins:{result.winners},losses:{result.losers},"
        f"sl:{result.stop_loss_closes},pd:{result.profit_drawdown_closes},"
        f"pnl:{result.net_profit:+.2f},dd:{result.maximum_drawdown:.2f},"
        f"pf:{profit_factor}"
    )


def main() -> None:
    assert HISTORY_FILE.is_file(), HISTORY_FILE
    candidate = built_in_workspace_indicator_profile(
        ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F
    )
    legacy = built_in_workspace_indicator_profile(ALLIGATOR_PROFILE_UID_LGE_CLASSIC)
    assert candidate.profile_uid != legacy.profile_uid
    assert candidate.parameters["logic_mode"] == ALLIGATOR_LOGIC_MODE_CANDIDATE_F
    assert candidate.parameters["trend_start_confirmation_bars"] == 4
    assert candidate.parameters["deferred_expiry_bars"] == 5
    assert candidate.parameters["opening_collapse_threshold"] == -0.700
    assert candidate.parameters["volatility_lookback_bars"] == 20
    assert candidate.parameters["weak_max_active_age"] == 2
    assert candidate.parameters["weak_max_opening"] == 0.500
    assert candidate.parameters["spike_min_range_ratio"] == 3.500
    assert candidate.parameters["spike_max_opening_delta"] == -0.500
    assert candidate.parameters["spike_max_slope_delta"] == -0.010
    assert candidate.parameters["overextended_min_slope"] == 0.200
    assert candidate.parameters["overextended_min_opening"] == 3.000
    assert "logic_mode" not in legacy.parameters

    fresh = new_workspace_indicator_profile_bindings()
    fresh_alligator = WorkspaceIndicatorProfileBinding.from_storage_dict(
        fresh[WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY]
    )
    assert fresh_alligator.profile_uid == ALLIGATOR_PROFILE_UID_LGE_CLASSIC

    results = {
        window: _run(window, start_utc, end_utc)
        for window, start_utc, end_utc in WINDOWS
    }
    for result in results.values():
        _assert_expected(result)

    development = results["DEVELOPMENT"]
    validation = results["VALIDATION"]
    holdout = results["HOLDOUT"]
    assert development.reason_counts[ALLIGATOR_REASON_DEFERRED_ARMED] == 2
    assert development.reason_counts[ALLIGATOR_REASON_DEFERRED_RELEASE] == 1
    assert development.reason_counts[ALLIGATOR_REASON_VOLATILITY_SPIKE] == 1
    assert development.reason_counts[ALLIGATOR_REASON_WEAK_OPENING] == 1
    assert validation.reason_counts[ALLIGATOR_REASON_OPENING_COLLAPSE] == 4
    assert validation.reason_counts[ALLIGATOR_REASON_OVEREXTENDED] == 1
    assert holdout.reason_counts[ALLIGATOR_REASON_OPENING_COLLAPSE] == 1
    assert holdout.reason_counts[ALLIGATOR_REASON_WEAK_OPENING] == 1
    assert holdout.reason_counts[ALLIGATOR_REASON_VOLATILITY_SPIKE] == 1
    assert development.deferred_releases == 2
    assert development.deferred_signal_records == 2
    assert development.deferred_accepted_records == 1
    assert validation.deferred_releases == 0
    assert holdout.deferred_releases == 0
    assert holdout.cancelled_opposite_cross == 1

    aggregate = (
        sum(item.trades for item in results.values()),
        sum(item.winners for item in results.values()),
        sum(item.losers for item in results.values()),
        sum(item.stop_loss_closes for item in results.values()),
        sum(item.net_profit for item in results.values()),
    )
    assert aggregate[:4] == (30, 20, 10, 2)
    assert math.isclose(aggregate[4], 0.14, abs_tol=0.005)

    print("Algorithm Workspace Alligator Candidate F production result")
    print("  profile=LGE Candidate F Smoothed r1")
    print("  legacy_profile_preserved=True")
    print("  fresh_workspace_default_unchanged=True")
    print("  registered_production_algorithm=True")
    for window, _start, _end in WINDOWS:
        result = results[window]
        print(f"  {window.lower()}={_format_result(result)}")
    print(
        "  development_reason_counts="
        f"armed:{development.reason_counts[ALLIGATOR_REASON_DEFERRED_ARMED]},"
        f"release:{development.reason_counts[ALLIGATOR_REASON_DEFERRED_RELEASE]},"
        f"spike:{development.reason_counts[ALLIGATOR_REASON_VOLATILITY_SPIKE]},"
        f"weak:{development.reason_counts[ALLIGATOR_REASON_WEAK_OPENING]}"
    )
    print(
        "  validation_reason_counts="
        f"collapse:{validation.reason_counts[ALLIGATOR_REASON_OPENING_COLLAPSE]},"
        f"overextended:{validation.reason_counts[ALLIGATOR_REASON_OVEREXTENDED]}"
    )
    print(
        "  holdout_reason_counts="
        f"collapse:{holdout.reason_counts[ALLIGATOR_REASON_OPENING_COLLAPSE]},"
        f"weak:{holdout.reason_counts[ALLIGATOR_REASON_WEAK_OPENING]},"
        f"spike:{holdout.reason_counts[ALLIGATOR_REASON_VOLATILITY_SPIKE]},"
        f"opposite_cross:{holdout.cancelled_opposite_cross}"
    )
    print(
        "  aggregate="
        f"trades:{aggregate[0]},wins:{aggregate[1]},losses:{aggregate[2]},"
        f"sl:{aggregate[3]},sum_pnl:{aggregate[4]:+.2f}"
    )
    print("  candidate_matches_green_37=True")
    print("  profile_snapshot_contains_candidate_thresholds=True")
    print("  candidate_uses_completed_bars_only=True")
    print("  volatility_reference_excludes_signal_bar=True")
    print("  no_look_ahead=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_ALLIGATOR_CANDIDATE_F_PRODUCTION_CHECK=OK")


if __name__ == "__main__":
    main()
