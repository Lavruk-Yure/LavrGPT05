# -*- coding: utf-8 -*-
"""RoadMap103 / 7X.2: MACD prominence normalization diagnostic.

Diagnostic-only snapshot перевіряє, чи однаковий fixed-pip prominence 0.15 pip
має однакову жорсткість для EURUSD і GBPUSD. Використовуються вже отримані
GREEN 7X/7X.1 MACD acceptance snapshots та M1-derived M15 volatility snapshots
із тих самих cTrader 2025/2026 histories. Production logic не змінюється.
"""

from __future__ import annotations

from dataclasses import dataclass


REFERENCE_PROMINENCE_PIPS = 0.15


@dataclass(frozen=True, slots=True)
class PeriodSymbolSnapshot:
    """Frozen cross-symbol signal/volatility facts одного періоду."""

    median_m15_true_range_pips: float
    median_m15_atr14_pips: float
    macd_accept_rate: float

    @property
    def prominence_burden_vs_atr(self) -> float:
        """Частка median ATR14, яку становить fixed prominence threshold."""
        return REFERENCE_PROMINENCE_PIPS / self.median_m15_atr14_pips


SNAPSHOTS = {
    ("2025", "EURUSD"): PeriodSymbolSnapshot(
        median_m15_true_range_pips=6.10,
        median_m15_atr14_pips=6.5714285714286405,
        macd_accept_rate=0.1361,
    ),
    ("2025", "GBPUSD"): PeriodSymbolSnapshot(
        median_m15_true_range_pips=7.10,
        median_m15_atr14_pips=7.74999999999986,
        macd_accept_rate=0.1758,
    ),
    ("2026", "EURUSD"): PeriodSymbolSnapshot(
        median_m15_true_range_pips=4.80,
        median_m15_atr14_pips=5.146428571428584,
        macd_accept_rate=0.0933,
    ),
    ("2026", "GBPUSD"): PeriodSymbolSnapshot(
        median_m15_true_range_pips=6.40,
        median_m15_atr14_pips=6.878571428571845,
        macd_accept_rate=0.1731,
    ),
}


def _ratio(period: str, field: str) -> float:
    eur = SNAPSHOTS[(period, "EURUSD")]
    gbp = SNAPSHOTS[(period, "GBPUSD")]
    return float(getattr(gbp, field)) / float(getattr(eur, field))


def _equivalent_gbp_prominence(period: str) -> float:
    """GBP threshold з тією ж ATR-relative burden, що EUR reference."""
    eur = SNAPSHOTS[(period, "EURUSD")]
    gbp = SNAPSHOTS[(period, "GBPUSD")]
    return (
        REFERENCE_PROMINENCE_PIPS
        * gbp.median_m15_atr14_pips
        / eur.median_m15_atr14_pips
    )


def main() -> None:
    """Run frozen cross-symbol normalization attribution checks."""
    eur25 = SNAPSHOTS[("2025", "EURUSD")]
    gbp25 = SNAPSHOTS[("2025", "GBPUSD")]
    eur26 = SNAPSHOTS[("2026", "EURUSD")]
    gbp26 = SNAPSHOTS[("2026", "GBPUSD")]

    atr_ratio_2025 = _ratio("2025", "median_m15_atr14_pips")
    atr_ratio_2026 = _ratio("2026", "median_m15_atr14_pips")
    accept_ratio_2025 = _ratio("2025", "macd_accept_rate")
    accept_ratio_2026 = _ratio("2026", "macd_accept_rate")

    burden_ratio_2025 = (
        gbp25.prominence_burden_vs_atr / eur25.prominence_burden_vs_atr
    )
    burden_ratio_2026 = (
        gbp26.prominence_burden_vs_atr / eur26.prominence_burden_vs_atr
    )
    equivalent_2025 = _equivalent_gbp_prominence("2025")
    equivalent_2026 = _equivalent_gbp_prominence("2026")

    assert gbp25.median_m15_atr14_pips > eur25.median_m15_atr14_pips
    assert gbp26.median_m15_atr14_pips > eur26.median_m15_atr14_pips
    assert burden_ratio_2025 < 0.90
    assert burden_ratio_2026 < 0.80
    assert burden_ratio_2026 < burden_ratio_2025
    assert accept_ratio_2025 > 1.25
    assert accept_ratio_2026 > 1.80
    assert equivalent_2025 > REFERENCE_PROMINENCE_PIPS
    assert equivalent_2026 > equivalent_2025

    fixed_gbp_tuning_rejected = abs(equivalent_2026 - equivalent_2025) > 0.02
    assert fixed_gbp_tuning_rejected

    print("Algorithm Workspace Candidate F GBPUSD Prominence Normalization result")
    print("  mode=RM103_7X2_MACD_PROMINENCE_NORMALIZATION_DIAGNOSTIC_ONLY")
    print("  production_candidate_f_logic_changed=False")
    print("  production_macd_threshold_changed=False")
    print("  symbol_specific_tuning_applied=False")
    print("  repeated_historical_replay=False")
    print("  reference_prominence_pips=0.15")
    print(
        "  median_m15_atr14_pips_2025="
        f"EURUSD:{eur25.median_m15_atr14_pips:.3f},"
        f"GBPUSD:{gbp25.median_m15_atr14_pips:.3f}"
    )
    print(
        "  median_m15_atr14_pips_2026="
        f"EURUSD:{eur26.median_m15_atr14_pips:.3f},"
        f"GBPUSD:{gbp26.median_m15_atr14_pips:.3f}"
    )
    print(f"  GBP_to_EUR_atr_ratio_2025={atr_ratio_2025:.4f}")
    print(f"  GBP_to_EUR_atr_ratio_2026={atr_ratio_2026:.4f}")
    print(
        "  prominence_burden_vs_atr_2025="
        f"EURUSD:{eur25.prominence_burden_vs_atr:.4%},"
        f"GBPUSD:{gbp25.prominence_burden_vs_atr:.4%}"
    )
    print(
        "  prominence_burden_vs_atr_2026="
        f"EURUSD:{eur26.prominence_burden_vs_atr:.4%},"
        f"GBPUSD:{gbp26.prominence_burden_vs_atr:.4%}"
    )
    print(f"  GBP_to_EUR_burden_ratio_2025={burden_ratio_2025:.4f}")
    print(f"  GBP_to_EUR_burden_ratio_2026={burden_ratio_2026:.4f}")
    print(f"  MACD_accept_ratio_GBP_to_EUR_2025={accept_ratio_2025:.4f}")
    print(f"  MACD_accept_ratio_GBP_to_EUR_2026={accept_ratio_2026:.4f}")
    print(
        "  atr_equivalent_GBP_prominence_pips="
        f"2025:{equivalent_2025:.4f},2026:{equivalent_2026:.4f}"
    )
    print("  fixed_GBP_specific_prominence_tuning_rejected=True")
    print("  volatility_normalization_hypothesis=SUPPORTED_FOR_NEXT_DIAGNOSTIC")
    print("  normalization_candidate=CAUSAL_M15_VOLATILITY_SCALE")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print(
        "ALGORITHM_WORKSPACE_CANDIDATE_F_GBPUSD_"
        "PROMINENCE_NORMALIZATION_CHECK=OK"
    )


if __name__ == "__main__":
    main()
