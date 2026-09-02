# -*- coding: utf-8 -*-
"""RoadMap103 / 7X.1: GBPUSD pipeline attribution snapshot.

Швидка diagnostic-only перевірка пояснює вже GREEN 7X cross-symbol result без
повторного багатохвилинного Replay. Вона фіксує signal-stage snapshots,
отримані з тих самих completed cTrader M1 -> M15 Candidate F runs, і розкладає
EURUSD -> GBPUSD різницю на MACD Quality, Alligator conversion та deferred
Candidate F release. Production logic/profile/entry/exit не змінюються.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from run_algorithm_workspace_candidate_f_gbpusd_cross_symbol_check import (  # noqa
    EURUSD_REFERENCE,
    EXPECTED_GBPUSD,
)


@dataclass(frozen=True, slots=True)
class SignalStageSnapshot:
    """Frozen signal-stage counters from one completed 7X-equivalent run."""

    total_records: int
    macd_accept: int
    extremum_not_found: int
    extremum_too_weak: int
    distance_too_small: int
    cross_too_flat: int
    deferred_release: int
    alligator_allow: int
    alligator_reject: int
    direct_allow_from_macd_accept: int
    allow_active_age_median: float
    allow_opening_median: float
    allow_slope_median: float

    @property
    def macd_reject(self) -> int:
        return (
            self.extremum_not_found
            + self.extremum_too_weak
            + self.distance_too_small
            + self.cross_too_flat
        )

    @property
    def macd_accept_rate(self) -> float:
        return self.macd_accept / self.total_records

    @property
    def direct_alligator_allow_rate(self) -> float:
        return self.direct_allow_from_macd_accept / self.macd_accept


SNAPSHOTS = {
    ("2025", "EURUSD"): SignalStageSnapshot(
        total_records=3042,
        macd_accept=414,
        extremum_not_found=248,
        extremum_too_weak=1679,
        distance_too_small=404,
        cross_too_flat=295,
        deferred_release=2,
        alligator_allow=59,
        alligator_reject=357,
        direct_allow_from_macd_accept=57,
        allow_active_age_median=14.0,
        allow_opening_median=1.2478129955399855,
        allow_slope_median=0.10761794509791354,
    ),
    ("2025", "GBPUSD"): SignalStageSnapshot(
        total_records=3072,
        macd_accept=540,
        extremum_not_found=232,
        extremum_too_weak=1561,
        distance_too_small=428,
        cross_too_flat=307,
        deferred_release=4,
        alligator_allow=92,
        alligator_reject=452,
        direct_allow_from_macd_accept=88,
        allow_active_age_median=15.0,
        allow_opening_median=1.358629846686267,
        allow_slope_median=0.11883958554688892,
    ),
    ("2026", "EURUSD"): SignalStageSnapshot(
        total_records=1962,
        macd_accept=183,
        extremum_not_found=160,
        extremum_too_weak=1209,
        distance_too_small=225,
        cross_too_flat=185,
        deferred_release=0,
        alligator_allow=29,
        alligator_reject=154,
        direct_allow_from_macd_accept=29,
        allow_active_age_median=14.0,
        allow_opening_median=1.2797701402697703,
        allow_slope_median=0.1063207726105256,
    ),
    ("2026", "GBPUSD"): SignalStageSnapshot(
        total_records=1953,
        macd_accept=338,
        extremum_not_found=148,
        extremum_too_weak=1017,
        distance_too_small=258,
        cross_too_flat=187,
        deferred_release=5,
        alligator_allow=58,
        alligator_reject=285,
        direct_allow_from_macd_accept=53,
        allow_active_age_median=11.0,
        allow_opening_median=1.1551628822364748,
        allow_slope_median=0.09118387330202113,
    ),
}


def _assert_internal_consistency(
    snapshot: SignalStageSnapshot,
    expected_trades: int,
) -> None:
    """Validate record accounting and Candidate F release accounting."""
    assert (
        snapshot.macd_accept + snapshot.macd_reject + snapshot.deferred_release
        == snapshot.total_records
    )
    assert (
        snapshot.macd_accept
        == snapshot.direct_allow_from_macd_accept + snapshot.alligator_reject
    )
    assert (
        snapshot.direct_allow_from_macd_accept + snapshot.deferred_release
        == snapshot.alligator_allow
    )
    assert snapshot.alligator_allow == expected_trades


def _percent(value: float) -> str:
    return f"{value * 100.0:.2f}%"


def _delta_line(period: str) -> str:
    eur = SNAPSHOTS[(period, "EURUSD")]
    gbp = SNAPSHOTS[(period, "GBPUSD")]
    direct_allow_delta = (
        gbp.direct_allow_from_macd_accept - eur.direct_allow_from_macd_accept
    )
    return (
        f"raw:{gbp.total_records - eur.total_records:+d},"
        f"macd_accept:{gbp.macd_accept - eur.macd_accept:+d},"
        f"too_weak:{gbp.extremum_too_weak - eur.extremum_too_weak:+d},"
        f"distance:{gbp.distance_too_small - eur.distance_too_small:+d},"
        f"flat:{gbp.cross_too_flat - eur.cross_too_flat:+d},"
        f"not_found:{gbp.extremum_not_found - eur.extremum_not_found:+d},"
        f"direct_allow:{direct_allow_delta:+d},"
        f"deferred_release:{gbp.deferred_release - eur.deferred_release:+d}"
    )


def main() -> None:
    """Run frozen attribution checks without repeating Historical Replay."""
    for period, reference_key in (
        ("2025", "2025"),
        ("2026", "2026_TO_2026-08-25_15:07"),
    ):
        _assert_internal_consistency(
            SNAPSHOTS[(period, "EURUSD")],
            EURUSD_REFERENCE[reference_key].trades,
        )
        _assert_internal_consistency(
            SNAPSHOTS[(period, "GBPUSD")],
            EXPECTED_GBPUSD[reference_key].trades,
        )

    eur25 = SNAPSHOTS[("2025", "EURUSD")]
    gbp25 = SNAPSHOTS[("2025", "GBPUSD")]
    eur26 = SNAPSHOTS[("2026", "EURUSD")]
    gbp26 = SNAPSHOTS[("2026", "GBPUSD")]

    raw_delta_2025 = gbp25.total_records / eur25.total_records - 1.0
    raw_delta_2026 = gbp26.total_records / eur26.total_records - 1.0
    raw_volume_similar_2025 = abs(raw_delta_2025) < 0.02
    raw_volume_similar_2026 = abs(raw_delta_2026) < 0.02
    assert raw_volume_similar_2025
    assert raw_volume_similar_2026

    macd_accept_ratio_2025 = gbp25.macd_accept / eur25.macd_accept
    macd_accept_ratio_2026 = gbp26.macd_accept / eur26.macd_accept
    assert macd_accept_ratio_2025 > 1.25
    assert macd_accept_ratio_2026 > 1.80

    too_weak_drop_2025 = eur25.extremum_too_weak - gbp25.extremum_too_weak
    too_weak_drop_2026 = eur26.extremum_too_weak - gbp26.extremum_too_weak
    assert too_weak_drop_2025 == 118
    assert too_weak_drop_2026 == 192
    assert too_weak_drop_2025 > 0
    assert too_weak_drop_2026 > 0

    alligator_rate_delta_2025 = (
        gbp25.direct_alligator_allow_rate - eur25.direct_alligator_allow_rate
    )
    alligator_rate_delta_2026 = (
        gbp26.direct_alligator_allow_rate - eur26.direct_alligator_allow_rate
    )
    assert alligator_rate_delta_2025 > 0.02
    assert abs(alligator_rate_delta_2026) < 0.005

    lifecycle_age_consistent_direction = (
        gbp25.allow_active_age_median - eur25.allow_active_age_median
    ) * (gbp26.allow_active_age_median - eur26.allow_active_age_median) > 0.0
    assert not lifecycle_age_consistent_direction

    print("Algorithm Workspace Candidate F GBPUSD Pipeline Attribution result")
    print("  mode=RM103_7X1_GBPUSD_PIPELINE_ATTRIBUTION_SNAPSHOT")
    print("  production_candidate_f_logic_changed=False")
    print("  repeated_historical_replay=False")
    print("  source=GREEN_7X_COMPLETED_REPLAY_SIGNAL_STAGE_SNAPSHOTS")
    print(f"  raw_signal_volume_similar_2025={raw_volume_similar_2025}")
    print(f"  raw_signal_volume_similar_2026={raw_volume_similar_2026}")
    print(
        "  macd_accept_rates_2025="
        f"EURUSD:{_percent(eur25.macd_accept_rate)},"
        f"GBPUSD:{_percent(gbp25.macd_accept_rate)}"
    )
    print(
        "  macd_accept_rates_2026="
        f"EURUSD:{_percent(eur26.macd_accept_rate)},"
        f"GBPUSD:{_percent(gbp26.macd_accept_rate)}"
    )
    print(f"  macd_accept_ratio_GBP_to_EUR_2025={macd_accept_ratio_2025:.4f}")
    print(f"  macd_accept_ratio_GBP_to_EUR_2026={macd_accept_ratio_2026:.4f}")
    print(f"  rejection_delta_2025={_delta_line('2025')}")
    print(f"  rejection_delta_2026={_delta_line('2026')}")
    print(f"  extremum_too_weak_drop_2025={too_weak_drop_2025}")
    print(f"  extremum_too_weak_drop_2026={too_weak_drop_2026}")
    print(
        "  direct_alligator_allow_rate_2025="
        f"EURUSD:{_percent(eur25.direct_alligator_allow_rate)},"
        f"GBPUSD:{_percent(gbp25.direct_alligator_allow_rate)}"
    )
    print(
        "  direct_alligator_allow_rate_2026="
        f"EURUSD:{_percent(eur26.direct_alligator_allow_rate)},"
        f"GBPUSD:{_percent(gbp26.direct_alligator_allow_rate)}"
    )
    print(
        "  direct_alligator_allow_rate_delta_2025=" f"{alligator_rate_delta_2025:+.4f}"
    )
    print(
        "  direct_alligator_allow_rate_delta_2026=" f"{alligator_rate_delta_2026:+.4f}"
    )
    print(
        "  allow_active_age_median="
        f"2025_EUR:{eur25.allow_active_age_median:.0f},"
        f"2025_GBP:{gbp25.allow_active_age_median:.0f},"
        f"2026_EUR:{eur26.allow_active_age_median:.0f},"
        f"2026_GBP:{gbp26.allow_active_age_median:.0f}"
    )
    print(
        "  lifecycle_entry_age_consistent_direction="
        f"{lifecycle_age_consistent_direction}"
    )
    print("  primary_volume_driver=MACD_QUALITY_ACCEPTANCE")
    print("  primary_rejection_shift=EXTREMUM_TOO_WEAK_DROP")
    print("  alligator_conversion_driver_2025=SECONDARY")
    print("  alligator_conversion_driver_2026=NO")
    print("  fixed_pip_prominence_cross_symbol_portability=SUSPECT_DIAGNOSTIC_ONLY")
    print("  symbol_specific_tuning_applied=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_GBPUSD_PIPELINE_ATTRIBUTION_CHECK=OK")


if __name__ == "__main__":
    main()
