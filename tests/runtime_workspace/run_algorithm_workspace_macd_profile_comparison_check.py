# -*- coding: utf-8 -*-
"""RoadMap101.4 — controlled comparison трьох MACD speed profiles.

Перевірка запускає канонічний RoadMap101 comparison runner один раз для
BASELINE 12/26/9, FAST 8/17/5 і VERY_FAST 6/13/4 на тому самому
Development-вікні EURUSD M1 -> completed M15. Усі signal-quality, Replay,
risk, spread, Profit Drawdown та execution умови лишаються незмінними;
контрольована змінна цього етапу — тільки MACD periods/profile snapshot.

Звіт призначений насамперед для structural comparison: classic/candidate
density, BUY/SELL symmetry, N/W/D/F, price-turn latency та MFE/MAE.
Trading WR/PF/PnL/DD друкуються як secondary facts і не використовуються
як єдиний критерій вибору MACD speed region. Historical Replay має
лишатися causal і deterministic за вже прийнятим runner contract, без
broker I/O та execution.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_indicator_profile import (  # noqa: E402
    MACD_PROFILE_UID_LGE_CLASSIC,
)
from core.workspace_macd_production_comparison import (  # noqa: E402
    WorkspaceMacdComparisonProfile,
    WorkspaceMacdProductionComparisonConfig,
    WorkspaceMacdProductionComparisonReport,
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
FAST_PROFILE_UID = "c498cd4c-12d2-4573-a96c-20a758d7e3fc"
VERY_FAST_PROFILE_UID = "b2eb706f-7861-4988-aa1a-9bb4a30eb4ce"

PROFILES = (
    WorkspaceMacdComparisonProfile(
        name="LGE Classic EMA 12/26/9 Close",
        profile_uid=MACD_PROFILE_UID_LGE_CLASSIC,
        profile_revision=1,
        fast_period=12,
        slow_period=26,
        signal_period=9,
    ),
    WorkspaceMacdComparisonProfile(
        name="Custom MACD FAST",
        profile_uid=FAST_PROFILE_UID,
        profile_revision=7,
        fast_period=8,
        slow_period=17,
        signal_period=5,
    ),
    WorkspaceMacdComparisonProfile(
        name="Custom MACD VERY FAST",
        profile_uid=VERY_FAST_PROFILE_UID,
        profile_revision=3,
        fast_period=6,
        slow_period=13,
        signal_period=4,
    ),
)


def _config(
    profile: WorkspaceMacdComparisonProfile,
) -> WorkspaceMacdProductionComparisonConfig:
    """Побудувати config з єдиною змінною — MACD profile snapshot."""
    return WorkspaceMacdProductionComparisonConfig(
        dataset_path=M1_FILE,
        window_start=DEVELOPMENT_START,
        window_end=DEVELOPMENT_END,
        dataset_label="IB_EURUSD_M1_RM101_DEVELOPMENT",
        profile=profile,
        abc_min_angle_degrees=2.00,
        prominence=0.000005,
        distance=0.000050,
        alligator_mode=WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED,
    )


def _profit_factor(value: float | None) -> str:
    """Повернути короткий printable Profit Factor."""
    return "N/A" if value is None else f"{value:.4f}"


def _symmetry_delta(report: WorkspaceMacdProductionComparisonReport) -> int:
    """Повернути абсолютну різницю BUY/SELL crossover."""
    return abs(report.buy_crosses - report.sell_crosses)


def _print_report(report: WorkspaceMacdProductionComparisonReport) -> None:
    """Надрукувати компактну колонку comparison facts."""
    reasons = report.reject_reasons
    latency = report.price_turn_latency
    excursions = report.excursions
    print(
        f"  {report.profile_periods}: classic={report.classic_crosses} "
        f"BUY/SELL={report.buy_crosses}/{report.sell_crosses} "
        f"symmetry_delta={_symmetry_delta(report)}"
    )
    print(
        "    quality="
        f"{report.quality_accepted}/{report.quality_rejected} "
        f"candidate_density={report.candidate_density_per_100_bars:.4f}"
    )
    print(
        "    N/W/D/F="
        f"{reasons.extremum_not_found_n}/{reasons.weak_prominence_w}/"
        f"{reasons.distance_d}/{reasons.flat_angle_f}"
    )
    print(
        "    latency_signal_avg/median="
        f"{latency.average_signal_bars:.4f}/{latency.median_signal_bars:.4f} "
        "entry_avg/median="
        f"{latency.average_entry_bars:.4f}/{latency.median_entry_bars:.4f}"
    )
    print(
        "    MFE/MAE_avg="
        f"{excursions.average_mfe:.4f}/{excursions.average_mae:.4f} "
        f"WR={report.win_rate_percent:.4f}% "
        f"PF={_profit_factor(report.profit_factor)} "
        f"PnL={report.net_profit:.4f} "
        f"DD={report.maximum_drawdown:.4f}/"
        f"{report.maximum_drawdown_percent:.4f}%"
    )
    print(
        "    orders/trades="
        f"{report.orders_created}/{report.trades} "
        f"NEXT_BAR_GAP={report.next_bar_gap_orders} "
        f"signature={report.deterministic_signature}"
    )


def main() -> None:
    """Запустити A/B/C comparison і перевірити controlled variable."""
    if not M1_FILE.is_file():
        raise FileNotFoundError("Real EURUSD M1 history is required: " + str(M1_FILE))

    reports: list[WorkspaceMacdProductionComparisonReport] = []
    for index, profile in enumerate(PROFILES, start=1):
        print(
            "MACD profile comparison: "
            f"{index}/{len(PROFILES)} {profile.fast_period}/"
            f"{profile.slow_period}/{profile.signal_period} ...",
            flush=True,
        )
        reports.append(run_workspace_macd_production_comparison(_config(profile)))

    baseline, fast, very_fast = reports
    assert tuple(item.profile_periods for item in reports) == (
        "12/26/9",
        "8/17/5",
        "6/13/4",
    )
    reference = baseline
    for report in reports:
        assert report.dataset_label == reference.dataset_label
        assert report.window_start == reference.window_start
        assert report.window_end == reference.window_end
        assert report.abc_min_angle_degrees == 2.00
        assert report.prominence == 0.000005
        assert report.distance == 0.000050
        assert report.alligator_mode == WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED
        assert report.historical_m1_rows == reference.historical_m1_rows
        assert report.completed_m15_bars == reference.completed_m15_bars
        assert (
            report.dropped_incomplete_m15_buckets
            == reference.dropped_incomplete_m15_buckets
        )
        assert report.classic_crosses == report.buy_crosses + report.sell_crosses
        assert report.quality_accepted + report.quality_rejected == (
            report.classic_crosses
        )
        reasons = report.reject_reasons
        assert (
            reasons.extremum_not_found_n
            + reasons.weak_prominence_w
            + reasons.distance_d
            + reasons.flat_angle_f
            == report.quality_rejected
        )
        assert report.signal_timestamp_before_entry
        assert report.completed_m15_only
        assert report.broker_requests == 0
        assert not report.broker_execution_attempted

    assert len({item.deterministic_signature for item in reports}) == 3
    assert baseline.profile_uid == MACD_PROFILE_UID_LGE_CLASSIC
    assert fast.profile_uid == FAST_PROFILE_UID
    assert very_fast.profile_uid == VERY_FAST_PROFILE_UID

    print("Algorithm Workspace MACD Profile Comparison result")
    print("  controlled_variable=MACD_PERIODS_ONLY")
    print(
        "  fixed=EURUSD M1->M15 Close EMA/EMA Shift0 "
        "Prominence0.000005 Distance0.000050 ABC2.00 AlligatorOFF"
    )
    print(
        "  window="
        f"{reference.window_start.date().isoformat()}.."
        f"{reference.window_end.date().isoformat()}"
    )
    print(
        "  historical_m1_rows/completed_m15_bars="
        f"{reference.historical_m1_rows}/{reference.completed_m15_bars}"
    )
    for report in reports:
        _print_report(report)
    print("  pnl_is_secondary_metric=True")
    print("  broker_requests_all_zero=True")
    print("  broker_execution_attempted_all_false=True")
    print("ALGORITHM_WORKSPACE_MACD_PROFILE_COMPARISON_CHECK=OK")


if __name__ == "__main__":
    main()
