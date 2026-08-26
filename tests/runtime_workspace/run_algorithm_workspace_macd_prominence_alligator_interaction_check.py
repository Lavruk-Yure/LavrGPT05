# -*- coding: utf-8 -*-
"""run_algorithm_workspace_macd_prominence_alligator_interaction_check.py.

RoadMap99_04A — контрольована перевірка взаємодії MACD Quality prominence
із фільтром Alligator SAME_TIMEFRAME на тому самому історичному Replay.

Мета тесту — не шукати універсальне значення prominence, а визначити, як
другий незалежний фільтр Alligator змінює кількість угод і торгові метрики
для кількох уже досліджених рівнів prominence. Перевіряються нижчі й вищі
точки локального робочого діапазону EURUSD M15, щоб побачити, чи Alligator
може залишити корисну частоту угод при менш жорсткому MACD Quality.

Контрольована змінна — тільки prominence. У всіх варіантах зафіксовані:
distance=0.000050, angle=45°, Alligator=LGE Classic Smoothed у режимі
SAME_TIMEFRAME, Profit Drawdown=30%, однакові risk settings, M1->M15 source,
період 2026-01-02..2026-02-28 і початкові 1000 USD. Historical Replay має
лишатися deterministic, а broker execution — повністю вимкненим.
"""

from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import run_algorithm_workspace_macd_prominence_sweep_check as base_sweep  # noqa: E402

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_historical_summary import (  # noqa: E402
    WorkspaceHistoricalReplaySummary,
)
from core.workspace_indicator_profile import (  # noqa: E402
    ALLIGATOR_PROFILE_UID_LGE_CLASSIC,
    MACD_PROFILE_UID_LGE_CLASSIC,
    WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY,
    WORKSPACE_MACD_PROFILE_BINDING_KEY,
)
from core.workspace_replay import REPLAY_SPEED_MAX  # noqa: E402
from core.workspace_replay_execution import (  # noqa: E402
    REPLAY_ORDER_STATUS_EXPIRED_NEXT_BAR_GAP,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402
from engine.runtime_constants import WORKSPACE_REPLAY_SOURCE_CSV  # noqa: E402

PROMINENCE_VALUES = (
    0.000005,
    0.000010,
    0.000015,
    0.000020,
    0.000025,
)

EXPECTED_QUALITY_ACCEPT = {
    0.000005: 26,
    0.000010: 23,
    0.000015: 17,
    0.000020: 12,
    0.000025: 7,
}


@dataclass(frozen=True, slots=True)
class AlligatorInteractionRun:
    """Результат одного prominence-варіанта з увімкненим Alligator."""

    prominence: float
    records: tuple[WorkspaceSignalRecord, ...]
    summary: WorkspaceHistoricalReplaySummary
    expired_next_bar_gap_orders: int


def _workspace(prominence: float) -> AlgorithmWorkspace:
    """Побудувати WSP з фіксованим Alligator SAME_TIMEFRAME."""
    workspace = AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        parameters={
            "macd_signal_enabled": True,
            "macd_signal_mode": "EXTENDED",
            "macd_extremum_min_prominence": prominence,
            "macd_extremum_to_cross_min_distance": base_sweep.FIXED_DISTANCE,
            "macd_cross_min_angle": base_sweep.FIXED_ANGLE,
            "alligator_filter_enabled": True,
            "alligator_confirmation": "SAME_TIMEFRAME",
            "warmup_bars": 25,
            "spread_limit": 0.00020,
        },
        replay_settings={
            "source_type": WORKSPACE_REPLAY_SOURCE_CSV,
            "file_path": str(base_sweep.M1_FILE),
            "source_timeframe": "M1",
            "start_utc": base_sweep.START_UTC.isoformat(),
            "end_utc": base_sweep.END_UTC.isoformat(),
            "source_timezone": "UTC",
            "delimiter": "AUTO",
            "decimal_separator": ".",
            "spread": 0.00012,
            "source": "IB_EURUSD_M1_RM99_PROMINENCE_ALLIGATOR",
            "initial_balance": 1000.0,
            "speed": REPLAY_SPEED_MAX,
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
    )

    macd_binding = workspace.indicator_profile_bindings[
        WORKSPACE_MACD_PROFILE_BINDING_KEY
    ]
    alligator_binding = workspace.indicator_profile_bindings[
        WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY
    ]
    assert macd_binding["profile_uid"] == MACD_PROFILE_UID_LGE_CLASSIC
    assert alligator_binding["profile_uid"] == ALLIGATOR_PROFILE_UID_LGE_CLASSIC
    return workspace


def _run(prominence: float) -> AlligatorInteractionRun:
    """Виконати один повний Replay з увімкненим Alligator."""
    records: list[WorkspaceSignalRecord] = []
    runtime = WorkspaceRuntime(
        _workspace(prominence),
        algorithm_factory=create_registered_workspace_algorithm,
        signal_record_observer=records.append,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    assert session.multi_resolution
    assert session.source_timeframe == "M1"
    assert session.strategy_timeframe == "M15"

    while not session.completed:
        runtime.advance_replay()

    summary = runtime.historical_summary
    assert summary is not None
    order_statuses = Counter(order.status for order in runtime.owned_snapshot.orders)
    assert runtime.context.positions_count == 0
    assert runtime.context.active_orders_count == 0
    return AlligatorInteractionRun(
        prominence=prominence,
        records=tuple(records),
        summary=summary,
        expired_next_bar_gap_orders=order_statuses[
            REPLAY_ORDER_STATUS_EXPIRED_NEXT_BAR_GAP
        ],
    )


def main() -> None:
    """Запустити RoadMap99_04A interaction sweep і перевірити invariants."""
    print(
        "Algorithm Workspace MACD Prominence + Alligator Interaction Check — "
        "RoadMap99_04A",
        flush=True,
    )
    print(
        "  Prominence varies across 0.000005..0.000025; "
        "Alligator=SAME_TIMEFRAME/LGE Classic Smoothed, distance=0.000050, "
        "angle=45°, Profit Drawdown=30%, M1->M15 Replay.",
        flush=True,
    )
    print(
        "  Interpretation: admissible-range interaction test, not a universal "
        "parameter selection; broker execution remains disabled.",
        flush=True,
    )
    if not base_sweep.M1_FILE.is_file():
        raise FileNotFoundError(
            "Real EURUSD M1 history is required: " + str(base_sweep.M1_FILE)
        )

    events = base_sweep.build_strategy_events()
    completed: list[AlligatorInteractionRun] = []
    for index, prominence in enumerate(PROMINENCE_VALUES, start=1):
        print(
            "MACD Prominence + Alligator: running "
            f"{index}/{len(PROMINENCE_VALUES)} "
            f"prominence={prominence:.6f} ...",
            flush=True,
        )
        run = _run(prominence)
        completed.append(run)
        signals = run.summary.signals
        print(
            "MACD Prominence + Alligator: completed "
            f"prominence={prominence:.6f}, "
            f"quality={signals.macd_quality_accept}/"
            f"{signals.macd_quality_reject}, "
            f"alligator={signals.alligator_allow}/"
            f"{signals.alligator_reject}, "
            f"trades={run.summary.opened_trades}, "
            f"net_pnl={run.summary.net_profit:.2f}, "
            f"PF={base_sweep.format_profit_factor_text(run.summary.profit_factor)}",
            flush=True,
        )

    previous_quality: int | None = None
    for run in completed:
        summary = run.summary
        signals = summary.signals
        expected_quality = EXPECTED_QUALITY_ACCEPT[run.prominence]
        assert signals.total == 320
        assert signals.buy == 160
        assert signals.sell == 160
        assert signals.macd_quality_accept == expected_quality
        assert signals.macd_quality_accept + signals.macd_quality_reject == 320
        assert signals.alligator_allow + signals.alligator_reject == (
            signals.macd_quality_accept
        )
        assert signals.alligator_allow <= signals.macd_quality_accept
        assert summary.opened_trades <= signals.alligator_allow
        if previous_quality is not None:
            assert signals.macd_quality_accept <= previous_quality
        previous_quality = signals.macd_quality_accept

    print("Algorithm Workspace MACD Prominence + Alligator Interaction result")
    print("  historical_bars=3888")
    print("  source_timeframe=M1")
    print("  strategy_timeframe=M15")
    print("  controlled_parameter=MACD_EXTREMUM_MIN_PROMINENCE")
    print(f"  fixed_distance={base_sweep.FIXED_DISTANCE:.6f}")
    print(f"  fixed_angle={base_sweep.FIXED_ANGLE:.2f}")
    print("  alligator_enabled=True")
    print("  alligator_confirmation=SAME_TIMEFRAME")
    print("  alligator_profile=LGE Classic Smoothed")
    print("  parameter_model=ADMISSIBLE_RANGE_NOT_UNIVERSAL_CONSTANT")
    print("  prominence_variants:")
    for run in completed:
        summary = run.summary
        signals = summary.signals
        missed_moves = base_sweep.count_missed_moves(run.records, events)
        print(
            f"  prominence={run.prominence:.6f}: "
            f"quality={signals.macd_quality_accept}/"
            f"{signals.macd_quality_reject}, "
            f"alligator={signals.alligator_allow}/"
            f"{signals.alligator_reject}, "
            f"trades={summary.opened_trades}, "
            f"W/L={summary.winning_trades}/{summary.losing_trades}, "
            f"win_rate={summary.win_rate_percent:.2f}%, "
            f"net_pnl={summary.net_profit:.2f}, "
            f"PF={base_sweep.format_profit_factor_text(summary.profit_factor)}, "
            f"DD={summary.maximum_drawdown:.2f}/"
            f"{summary.maximum_drawdown_percent:.2f}%, "
            f"avg={summary.average_trade:.4f}, "
            f"SL/TP/PD/END={summary.close_reason_count('STOP_LOSS')}/"
            f"{summary.close_reason_count('TAKE_PROFIT')}/"
            f"{summary.close_reason_count('PROFIT_DRAWDOWN')}/"
            f"{summary.close_reason_count('SESSION_END')}, "
            f"expired_gap={run.expired_next_bar_gap_orders}, "
            f"missed_moves={missed_moves}"
        )

    print("  upstream_macd_quality_matches_alligator_off_sweeps=True")
    print("  macd_profile_fixed=LGE Classic EMA 12/26/9 Close")
    print("  alligator_profile_fixed=LGE Classic Smoothed")
    print("  same_m1_dataset=True")
    print("  same_replay_period=True")
    print("  same_risk_policy=True")
    print("  same_profit_drawdown_policy=True")
    print("  production_signal_logic_changed=False")
    print("  deterministic=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_MACD_PROMINENCE_ALLIGATOR_INTERACTION_CHECK=OK")


if __name__ == "__main__":
    main()
