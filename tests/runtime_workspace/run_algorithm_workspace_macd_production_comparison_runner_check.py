# -*- coding: utf-8 -*-
"""RoadMap101.3 — acceptance канонічного MACD comparison runner.

Тест запускає той самий Development Historical Replay двічі через новий
public runner. Вхід зафіксований як EURUSD M1 -> completed M15, Custom MACD
VERY FAST r3 6/13/4, EXTENDED, ABC_REALTIME_SCALED=2.00°, prominence=0.000005,
distance=0.000050 та Alligator=OFF. Перевіряється один structured report
contract, який надалі використовується без ручного переписування цифр у
RoadMap101.4–101.9.

Regression доводить causal signal->NEXT_BAR_OPEN chronology, completed M15
strategy bars, N/W/D/F coverage, virtual trading/MFE/MAE metrics, відсутність
broker I/O/execution та однакову deterministic BLAKE2 signature двох
прогонів. Trading PnL фіксується як secondary fact, а не як критерій вибору
profile.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_macd_production_comparison import (  # noqa: E402
    WorkspaceMacdComparisonProfile,
    WorkspaceMacdProductionComparisonConfig,
    run_workspace_macd_production_comparison,
)
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED,
)

M1_FILE = (
    PROJECT_ROOT
    / "data"
    / "history"
    / "IB"
    / "EURUSD"
    / "M1"
    / "2026-01-02_2026-08-11_IB_EURUSD_M1.csv"
)
DEVELOPMENT_START = datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
DEVELOPMENT_END = datetime(2026, 2, 28, 23, 59, tzinfo=UTC)
VERY_FAST_R3_UID = "b2eb706f-7861-4988-aa1a-9bb4a30eb4ce"


def _config() -> WorkspaceMacdProductionComparisonConfig:
    """Повернути стартовий Development config RoadMap101."""
    return WorkspaceMacdProductionComparisonConfig(
        dataset_path=M1_FILE,
        window_start=DEVELOPMENT_START,
        window_end=DEVELOPMENT_END,
        dataset_label="IB_EURUSD_M1_RM101_DEVELOPMENT",
        profile=WorkspaceMacdComparisonProfile(
            name="Custom MACD VERY FAST",
            profile_uid=VERY_FAST_R3_UID,
            profile_revision=3,
            fast_period=6,
            slow_period=13,
            signal_period=4,
        ),
        abc_min_angle_degrees=2.00,
        prominence=0.000005,
        distance=0.000050,
        alligator_mode=WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED,
    )


def _profit_factor(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.4f}"


def main() -> None:
    """Запустити два comparison та перевірити report contract."""
    if not M1_FILE.is_file():
        raise FileNotFoundError("Real EURUSD M1 history is required: " + str(M1_FILE))

    print("MACD Production Comparison Runner: pass 1/2 ...", flush=True)
    first = run_workspace_macd_production_comparison(_config())
    print("MACD Production Comparison Runner: pass 2/2 ...", flush=True)
    second = run_workspace_macd_production_comparison(_config())

    assert first == second
    assert first.deterministic_signature == second.deterministic_signature
    assert first.historical_m1_rows > 0
    assert first.completed_m15_bars > 0
    assert first.classic_crosses == first.buy_crosses + first.sell_crosses
    assert first.extremum_windows.window_3 + first.extremum_windows.window_5 + (
        first.extremum_windows.window_7 + first.extremum_windows.none
    ) == first.classic_crosses
    assert first.prominence_criterion.passed + first.prominence_criterion.rejected == (
        first.classic_crosses
    )
    assert first.distance_criterion.passed + first.distance_criterion.rejected == (
        first.classic_crosses
    )
    assert first.abc_angle_criterion.passed + first.abc_angle_criterion.rejected == (
        first.classic_crosses
    )
    assert first.quality_accepted + first.quality_rejected == first.classic_crosses
    assert (
        first.reject_reasons.extremum_not_found_n
        + first.reject_reasons.weak_prominence_w
        + first.reject_reasons.distance_d
        + first.reject_reasons.flat_angle_f
        == first.quality_rejected
    )
    assert first.orders_created >= first.trades
    assert first.trades == first.winners + first.losers + first.break_even
    assert first.excursions.trades == first.trades
    assert first.signal_timestamp_before_entry
    assert first.completed_m15_only
    assert first.broker_requests == 0
    assert not first.broker_execution_attempted
    assert len(first.deterministic_signature) == 32

    print("Algorithm Workspace MACD Production Comparison Runner result")
    print(f"  dataset={first.dataset_label}")
    print(
        "  window="
        f"{first.window_start.date().isoformat()}.."
        f"{first.window_end.date().isoformat()}"
    )
    print(
        "  profile="
        f"{first.profile_name} r{first.profile_revision} "
        f"{first.profile_periods}"
    )
    print(f"  profile_uid={first.profile_uid}")
    print(f"  historical_m1_rows={first.historical_m1_rows}")
    print(f"  completed_m15_bars={first.completed_m15_bars}")
    print(
        "  dropped_incomplete_m15_buckets="
        f"{first.dropped_incomplete_m15_buckets}"
    )
    print(
        "  classic_crosses="
        f"{first.classic_crosses} BUY/SELL="
        f"{first.buy_crosses}/{first.sell_crosses}"
    )
    windows = first.extremum_windows
    print(
        "  extremum_3/5/7/NONE="
        f"{windows.window_3}/{windows.window_5}/{windows.window_7}/{windows.none}"
    )
    print(
        "  prominence_pass/reject="
        f"{first.prominence_criterion.passed}/"
        f"{first.prominence_criterion.rejected}"
    )
    print(
        "  distance_pass/reject="
        f"{first.distance_criterion.passed}/{first.distance_criterion.rejected}"
    )
    print(
        "  abc_angle_pass/reject="
        f"{first.abc_angle_criterion.passed}/{first.abc_angle_criterion.rejected}"
    )
    print(
        "  quality_accept/reject="
        f"{first.quality_accepted}/{first.quality_rejected}"
    )
    reasons = first.reject_reasons
    print(
        "  N/W/D/F="
        f"{reasons.extremum_not_found_n}/{reasons.weak_prominence_w}/"
        f"{reasons.distance_d}/{reasons.flat_angle_f}"
    )
    print(
        "  density_classic/candidate_per_100_bars="
        f"{first.classic_density_per_100_bars:.4f}/"
        f"{first.candidate_density_per_100_bars:.4f}"
    )
    latency = first.price_turn_latency
    print(
        "  price_turn_latency_signal_avg/median_bars="
        f"{latency.average_signal_bars:.4f}/{latency.median_signal_bars:.4f}"
    )
    print(
        "  price_turn_latency_entry_avg/median_bars="
        f"{latency.average_entry_bars:.4f}/{latency.median_entry_bars:.4f}"
    )
    print(f"  latency_entry_gap_signals={latency.entry_gap_signals}")
    print(f"  orders/trades={first.orders_created}/{first.trades}")
    print(
        "  winners/losers/break_even="
        f"{first.winners}/{first.losers}/{first.break_even}"
    )
    print(f"  win_rate_percent={first.win_rate_percent:.4f}")
    print(f"  profit_factor={_profit_factor(first.profit_factor)}")
    print(f"  net_pnl={first.net_profit:.4f}")
    print(f"  average_trade={first.average_trade:.4f}")
    print(
        "  max_dd_usd/percent="
        f"{first.maximum_drawdown:.4f}/{first.maximum_drawdown_percent:.4f}"
    )
    print(
        "  SL/TP/PROFIT_DRAWDOWN/SESSION_END="
        f"{first.stop_loss_closes}/{first.take_profit_closes}/"
        f"{first.profit_drawdown_closes}/{first.session_end_closes}"
    )
    print(f"  NEXT_BAR_GAP={first.next_bar_gap_orders}")
    excursions = first.excursions
    print(
        "  MFE_avg/max="
        f"{excursions.average_mfe:.4f}/{excursions.maximum_mfe:.4f}"
    )
    print(
        "  MAE_avg/min="
        f"{excursions.average_mae:.4f}/{excursions.minimum_mae:.4f}"
    )
    print(f"  signal_timestamp_before_entry={first.signal_timestamp_before_entry}")
    print(f"  completed_m15_only={first.completed_m15_only}")
    print(f"  broker_requests={first.broker_requests}")
    print(f"  broker_execution_attempted={first.broker_execution_attempted}")
    print(f"  deterministic_signature={first.deterministic_signature}")
    print("  deterministic_repeat_equal=True")
    print("ALGORITHM_WORKSPACE_MACD_PRODUCTION_COMPARISON_RUNNER_CHECK=OK")


if __name__ == "__main__":
    main()
