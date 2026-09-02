# -*- coding: utf-8 -*-
"""Діагностика ознак виснаження ACTIVE-тренду Alligator RoadMap101 №32.

Тест повторно використовує незмінний Replay-збір №31 і аналізує лише causal
entry-time evidence фактично відкритих угод: вік ACTIVE/regime, зміну
normalized slope/opening між t-2 і t та поточні normalized slope/opening.
Для Development, Validation, Holdout і Validation+Holdout будує неперекривні
bucket-агрегати count/wins/losses/PnL.

Bucket-статистика є observational diagnostic, а не контрфактичним trade gate:
вона не модифікує production, не перезапускає Replay із новими порогами і не
трактує MFE/MAE як доступні при вході ознаки. Completed bars/no-look-ahead та
незмінність production baseline успадковуються й повторно перевіряються через
runner №31.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SOURCE_TEST = Path(__file__).with_name(
    "run_algorithm_workspace_alligator_allowed_trade_diagnostic_check.py"
)


@dataclass(frozen=True, slots=True)
class Bucket:
    """Один неперекривний інтервал causal entry feature."""

    label: str
    predicate: Callable[[float], bool]


@dataclass(frozen=True, slots=True)
class Outcome:
    """Фактичний outcome subset без зміни Replay execution."""

    count: int
    winners: int
    losers: int
    net_profit: float


def _load_source_module():
    """Завантажити sibling diagnostic №31 без залежності від tests package."""
    assert SOURCE_TEST.is_file(), SOURCE_TEST
    spec = importlib.util.spec_from_file_location(
        "roadmap101_allowed_trade_diagnostic_31",
        SOURCE_TEST,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _outcome(trades) -> Outcome:
    """Порахувати фактичний count/win/loss/PnL для subset."""
    return Outcome(
        count=len(trades),
        winners=sum(trade.winner for trade in trades),
        losers=sum(trade.loser for trade in trades),
        net_profit=sum(trade.final_profit for trade in trades),
    )


def _format_outcome(outcome: Outcome) -> str:
    return (
        f"count:{outcome.count},wins:{outcome.winners},"
        f"losses:{outcome.losers},pnl:{outcome.net_profit:+.2f}"
    )


def _bucket_report(name: str, trades, getter, buckets: tuple[Bucket, ...]) -> list[str]:
    """Побудувати неперекривний bucket report і перевірити повне покриття."""
    lines: list[str] = []
    assigned = 0
    for bucket in buckets:
        subset = tuple(
            trade for trade in trades if bucket.predicate(float(getter(trade)))
        )
        assigned += len(subset)
        lines.append(f"{name}[{bucket.label}]={_format_outcome(_outcome(subset))}")
    assert assigned == len(trades), (name, assigned, len(trades))
    return lines


def _screen_report(name: str, trades, predicate) -> str:
    """Показати observational subset, який відповідає одній гіпотезі."""
    subset = tuple(trade for trade in trades if predicate(trade))
    return f"{name}={_format_outcome(_outcome(subset))}"


def main() -> None:
    source = _load_source_module()

    run_source = getattr(source, "_run")
    assert_source_baseline = getattr(source, "_assert_baseline")
    results = {
        window: run_source(window, start_utc, end_utc)
        for window, start_utc, end_utc in source.WINDOWS
    }
    for result in results.values():
        assert_source_baseline(result)

    development = results["DEVELOPMENT"].trades
    validation = results["VALIDATION"].trades
    holdout = results["HOLDOUT"].trades
    validation_holdout = validation + holdout
    all_trades = development + validation_holdout

    assert len(development) == 9
    assert len(validation) == 21
    assert len(holdout) == 10
    assert len(validation_holdout) == 31
    assert len(all_trades) == 40

    active_age_buckets = (
        Bucket("1-5", lambda value: 1 <= value <= 5),
        Bucket("6-10", lambda value: 6 <= value <= 10),
        Bucket("11-15", lambda value: 11 <= value <= 15),
        Bucket("16-20", lambda value: 16 <= value <= 20),
        Bucket("21-30", lambda value: 21 <= value <= 30),
        Bucket("31+", lambda value: value >= 31),
    )
    regime_age_buckets = (
        Bucket("1-10", lambda value: 1 <= value <= 10),
        Bucket("11-20", lambda value: 11 <= value <= 20),
        Bucket("21-30", lambda value: 21 <= value <= 30),
        Bucket("31-50", lambda value: 31 <= value <= 50),
        Bucket("51+", lambda value: value >= 51),
    )
    slope_delta_buckets = (
        Bucket("<-0.020", lambda value: value < -0.020),
        Bucket("-0.020..-0.010", lambda value: -0.020 <= value < -0.010),
        Bucket("-0.010..0", lambda value: -0.010 <= value < 0.0),
        Bucket("0..+0.010", lambda value: 0.0 <= value < 0.010),
        Bucket(">=+0.010", lambda value: value >= 0.010),
    )
    opening_delta_buckets = (
        Bucket("<-0.750", lambda value: value < -0.750),
        Bucket("-0.750..-0.500", lambda value: -0.750 <= value < -0.500),
        Bucket("-0.500..-0.250", lambda value: -0.500 <= value < -0.250),
        Bucket("-0.250..0", lambda value: -0.250 <= value < 0.0),
        Bucket(">=0", lambda value: value >= 0.0),
    )
    opening_level_buckets = (
        Bucket("<0.75", lambda value: value < 0.75),
        Bucket("0.75..1.00", lambda value: 0.75 <= value < 1.00),
        Bucket("1.00..1.25", lambda value: 1.00 <= value < 1.25),
        Bucket("1.25..1.50", lambda value: 1.25 <= value < 1.50),
        Bucket(">=1.50", lambda value: value >= 1.50),
    )

    feature_specs = (
        (
            "active_age",
            lambda trade: trade.active_age_bars,
            active_age_buckets,
        ),
        (
            "regime_age",
            lambda trade: trade.regime_age_bars,
            regime_age_buckets,
        ),
        (
            "slope_delta_t2_t",
            lambda trade: (
                trade.current.normalized_slope - trade.t_minus_2.normalized_slope
            ),
            slope_delta_buckets,
        ),
        (
            "opening_delta_t2_t",
            lambda trade: (
                trade.current.normalized_opening - trade.t_minus_2.normalized_opening
            ),
            opening_delta_buckets,
        ),
        (
            "opening_level_t",
            lambda trade: trade.current.normalized_opening,
            opening_level_buckets,
        ),
    )

    scopes = (
        ("development", development),
        ("validation", validation),
        ("holdout", holdout),
        ("validation_holdout", validation_holdout),
    )

    print("Algorithm Workspace Alligator ACTIVE exhaustion diagnostic result")
    print("  mode=DIAGNOSTIC_ONLY_NO_GATE_CHANGE")
    print("  source=ROADMAP101_31_ACTUAL_3BAR_TRADES")
    print("  features=ACTIVE_AGE/REGIME_AGE/SLOPE_DELTA/OPENING_DELTA/OPENING_LEVEL")
    print("  deltas=ENTRY_TIME_t_minus_2_TO_t_COMPLETED_BARS_ONLY")
    print("  buckets=OBSERVATIONAL_NOT_COUNTERFACTUAL_REPLAY")

    for scope_name, trades in scopes:
        print(f"  {scope_name}_baseline={_format_outcome(_outcome(trades))}")
        for feature_name, getter, buckets in feature_specs:
            for line in _bucket_report(
                f"{scope_name}_{feature_name}",
                trades,
                getter,
                buckets,
            ):
                print(f"  {line}")

    # Обмежена кількість наперед визначених screening hypotheses. Вони лише
    # показують, де концентруються outcome, і не є production thresholds.
    print(
        "  vh_screen_late_active_gt30="
        + _screen_report(
            "value",
            validation_holdout,
            lambda trade: trade.active_age_bars > 30,
        ).split("=", 1)[1]
    )
    print(
        "  vh_screen_slope_decay_lt_minus_0_010="
        + _screen_report(
            "value",
            validation_holdout,
            lambda trade: (
                trade.current.normalized_slope - trade.t_minus_2.normalized_slope
            )
            < -0.010,
        ).split("=", 1)[1]
    )
    print(
        "  vh_screen_opening_collapse_lt_minus_0_500="
        + _screen_report(
            "value",
            validation_holdout,
            lambda trade: (
                trade.current.normalized_opening - trade.t_minus_2.normalized_opening
            )
            < -0.500,
        ).split("=", 1)[1]
    )
    print(
        "  vh_screen_low_opening_lt_1_000="
        + _screen_report(
            "value",
            validation_holdout,
            lambda trade: trade.current.normalized_opening < 1.000,
        ).split("=", 1)[1]
    )

    vh_winners = tuple(trade for trade in validation_holdout if trade.winner)
    vh_losers = tuple(trade for trade in validation_holdout if trade.loser)
    winner_slope_decay = sum(
        (trade.current.normalized_slope - trade.t_minus_2.normalized_slope) < -0.010
        for trade in vh_winners
    )
    loser_slope_decay = sum(
        (trade.current.normalized_slope - trade.t_minus_2.normalized_slope) < -0.010
        for trade in vh_losers
    )
    winner_opening_collapse = sum(
        (trade.current.normalized_opening - trade.t_minus_2.normalized_opening) < -0.500
        for trade in vh_winners
    )
    loser_opening_collapse = sum(
        (trade.current.normalized_opening - trade.t_minus_2.normalized_opening) < -0.500
        for trade in vh_losers
    )

    print(
        "  vh_decay_concentration="
        f"slope_lt_-0.010:winners:{winner_slope_decay}/{len(vh_winners)},"
        f"losers:{loser_slope_decay}/{len(vh_losers)};"
        f"opening_lt_-0.500:winners:{winner_opening_collapse}/{len(vh_winners)},"
        f"losers:{loser_opening_collapse}/{len(vh_losers)}"
    )

    assert len(vh_winners) == 14
    assert len(vh_losers) == 17
    assert all(not result.broker_execution_attempted for result in results.values())
    assert math.isclose(
        sum(trade.final_profit for trade in validation_holdout),
        -7.90,
        rel_tol=0.0,
        abs_tol=1e-9,
    )

    print("  mfe_mae_not_used_as_entry_features=True")
    print("  completed_bars_only=True")
    print("  no_look_ahead=True")
    print("  production_trade_gate_changed=False")
    print("  production_algorithm_registration_changed=False")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_ALLIGATOR_ACTIVE_EXHAUSTION_DIAGNOSTIC_CHECK=OK")


if __name__ == "__main__":
    main()
