# -*- coding: utf-8 -*-
"""RoadMap103 / 7W: symbol/pip scaling foundation diagnostic.

Тест не змінює production Candidate F. Він перевіряє повний локальний M1
набір EURUSD/GBPUSD/USDJPY за 2025 і 2026 для cTrader та IB, канонічну UTC
схему CSV, базову OHLC-цілісність і узгодженість двох broker sources.

Окремо фіксується головна передумова cross-symbol Replay: EURUSD/GBPUSD
мають pip 0.0001, USDJPY — 0.01. Вже наявний MACD ABC scale resolver має
точно обернену convention, але generic history spread та raw MACD quality
thresholds поки не є symbol-normalized. Тому test diagnostic може бути GREEN,
водночас cross-symbol Candidate F execution лишається заблокованим до явної
нормалізації цих величин.
"""

from __future__ import annotations

import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_macd_cross_angle_abc import (  # noqa: E402
    resolve_workspace_macd_cross_angle_value_scale,
)
from engine.runtime_constants import (  # noqa: E402
    DEFAULT_WORKSPACE_HISTORY_SPREAD,
    NEW_WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE,
    NEW_WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE,
)

SYMBOL_PIP_SIZES = {
    "EURUSD": 0.0001,
    "GBPUSD": 0.0001,
    "USDJPY": 0.01,
}
BROKERS = ("CTRADER", "IB")
YEARS = (2025, 2026)
CANONICAL_HEADER = ("timestamp", "open", "high", "low", "close", "volume")
MINIMUM_ROWS_PER_FILE = 200_000
MINIMUM_BROKER_OVERLAP_RATIO = 0.99
MAXIMUM_MEDIAN_CLOSE_DIVERGENCE_PIPS = 0.50
MAXIMUM_P95_CLOSE_DIVERGENCE_PIPS = 1.00
ZONE_HALF_WIDTH_PIPS = 3.0
FROZEN_PROXIMITY_THRESHOLDS_PIPS = (9.0, 12.0, 15.0)


@dataclass(frozen=True, slots=True)
class HistoryFileStats:
    """Стримінгова перевірка одного локального M1 CSV."""

    broker: str
    symbol: str
    year: int
    path: Path
    rows: int
    first_timestamp: str
    last_timestamp: str
    canonical_header: bool
    utc_timestamps: bool
    strictly_increasing: bool
    ohlc_valid: bool


@dataclass(frozen=True, slots=True)
class BrokerAgreement:
    """Порівняння close на спільних M1 timestamps двох broker sources."""

    symbol: str
    year: int
    overlap: int
    overlap_ratio: float
    median_pips: float
    p95_pips: float
    p99_pips: float


def _history_path(broker: str, symbol: str, year: int) -> Path:
    if broker == "CTRADER":
        start = f"{year}-01-01"
    else:
        start = f"{year}-01-02"
    end = f"{year}-12-31" if year == 2025 else "2026-08-25"
    name = f"{start}_{end}_{broker}_{symbol}_M1.csv"
    return PROJECT_ROOT / "data" / "history" / broker / symbol / "M1" / name


def _timestamp_key(value: str) -> tuple[int, int, int, int, int, int]:
    text = value.strip()
    assert text.endswith("Z"), f"timestamp is not explicit UTC: {text}"
    date_text, time_text = text[:-1].split("T", 1)
    year, month, day = (int(item) for item in date_text.split("-"))
    hour, minute, second = (int(item) for item in time_text.split(":"))
    return year, month, day, hour, minute, second


def _inspect_history_file(
    broker: str,
    symbol: str,
    year: int,
) -> HistoryFileStats:
    path = _history_path(broker, symbol, year)
    if not path.is_file():
        raise FileNotFoundError(f"Required history file is missing: {path}")

    rows = 0
    first_timestamp = ""
    last_timestamp = ""
    previous_key: tuple[int, int, int, int, int, int] | None = None
    utc_timestamps = True
    strictly_increasing = True
    ohlc_valid = True

    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        header = tuple(reader.fieldnames or ())
        canonical_header = header == CANONICAL_HEADER
        for row in reader:
            rows += 1
            timestamp = str(row["timestamp"]).strip()
            if not first_timestamp:
                first_timestamp = timestamp
            last_timestamp = timestamp
            try:
                current_key = _timestamp_key(timestamp)
            except (AssertionError, ValueError):
                utc_timestamps = False
                current_key = previous_key
            if previous_key is not None and current_key is not None:
                if current_key <= previous_key:
                    strictly_increasing = False
            if current_key is not None:
                previous_key = current_key

            try:
                open_price = float(row["open"])
                high_price = float(row["high"])
                low_price = float(row["low"])
                close_price = float(row["close"])
            except (TypeError, ValueError):
                ohlc_valid = False
                continue
            if not (
                high_price >= max(open_price, close_price)
                and low_price <= min(open_price, close_price)
                and high_price >= low_price
            ):
                ohlc_valid = False

    return HistoryFileStats(
        broker=broker,
        symbol=symbol,
        year=year,
        path=path,
        rows=rows,
        first_timestamp=first_timestamp,
        last_timestamp=last_timestamp,
        canonical_header=canonical_header,
        utc_timestamps=utc_timestamps,
        strictly_increasing=strictly_increasing,
        ohlc_valid=ohlc_valid,
    )


def _close_map(path: Path) -> dict[str, float]:
    result: dict[str, float] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            result[str(row["timestamp"]).strip()] = float(row["close"])
    return result


def _percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        raise AssertionError("broker agreement requires overlapping timestamps")
    index = int((len(sorted_values) - 1) * fraction)
    return sorted_values[index]


def _broker_agreement(
    symbol: str,
    year: int,
    ctrader_stats: HistoryFileStats,
    ib_stats: HistoryFileStats,
) -> BrokerAgreement:
    pip_size = SYMBOL_PIP_SIZES[symbol]
    ctrader_closes = _close_map(ctrader_stats.path)
    differences: list[float] = []
    with ib_stats.path.open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            timestamp = str(row["timestamp"]).strip()
            ctrader_close = ctrader_closes.get(timestamp)
            if ctrader_close is None:
                continue
            difference = abs(ctrader_close - float(row["close"])) / pip_size
            differences.append(difference)

    differences.sort()
    overlap = len(differences)
    smaller_rows = min(ctrader_stats.rows, ib_stats.rows)
    overlap_ratio = overlap / smaller_rows if smaller_rows else 0.0
    middle = overlap // 2
    if overlap % 2:
        median = differences[middle]
    else:
        median = (differences[middle - 1] + differences[middle]) / 2.0
    return BrokerAgreement(
        symbol=symbol,
        year=year,
        overlap=overlap,
        overlap_ratio=overlap_ratio,
        median_pips=median,
        p95_pips=_percentile(differences, 0.95),
        p99_pips=_percentile(differences, 0.99),
    )


def _raw_price(symbol: str, pips: float) -> float:
    return SYMBOL_PIP_SIZES[symbol] * pips


def main() -> None:
    """Запустити RoadMap103 / 7W diagnostic foundation."""
    stats: dict[tuple[str, str, int], HistoryFileStats] = {}
    for broker in BROKERS:
        for symbol in SYMBOL_PIP_SIZES:
            for year in YEARS:
                item = _inspect_history_file(broker, symbol, year)
                stats[(broker, symbol, year)] = item

    agreements: list[BrokerAgreement] = []
    for symbol in SYMBOL_PIP_SIZES:
        for year in YEARS:
            agreements.append(
                _broker_agreement(
                    symbol,
                    year,
                    stats[("CTRADER", symbol, year)],
                    stats[("IB", symbol, year)],
                )
            )

    abc_scales = {
        symbol: resolve_workspace_macd_cross_angle_value_scale(symbol)
        for symbol in SYMBOL_PIP_SIZES
    }
    inverse_scale_matches_pip = all(
        math.isclose(1.0 / abc_scales[symbol], pip_size, abs_tol=1e-12)
        for symbol, pip_size in SYMBOL_PIP_SIZES.items()
    )
    all_history_valid = all(
        item.rows >= MINIMUM_ROWS_PER_FILE
        and item.canonical_header
        and item.utc_timestamps
        and item.strictly_increasing
        and item.ohlc_valid
        for item in stats.values()
    )
    source_agreement_valid = all(
        item.overlap_ratio >= MINIMUM_BROKER_OVERLAP_RATIO
        and item.median_pips <= MAXIMUM_MEDIAN_CLOSE_DIVERGENCE_PIPS
        and item.p95_pips <= MAXIMUM_P95_CLOSE_DIVERGENCE_PIPS
        for item in agreements
    )

    spread_pips = {
        symbol: DEFAULT_WORKSPACE_HISTORY_SPREAD / pip_size
        for symbol, pip_size in SYMBOL_PIP_SIZES.items()
    }
    spread_symbol_safe = math.isclose(
        spread_pips["EURUSD"],
        spread_pips["USDJPY"],
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    prominence_pips = {
        symbol: NEW_WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE / pip_size
        for symbol, pip_size in SYMBOL_PIP_SIZES.items()
    }
    distance_pips = {
        symbol: NEW_WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE / pip_size
        for symbol, pip_size in SYMBOL_PIP_SIZES.items()
    }
    raw_macd_thresholds_symbol_safe = bool(
        math.isclose(
            prominence_pips["EURUSD"],
            prominence_pips["USDJPY"],
            abs_tol=1e-12,
        )
        and math.isclose(
            distance_pips["EURUSD"],
            distance_pips["USDJPY"],
            abs_tol=1e-12,
        )
    )

    print("Algorithm Workspace Symbol/Pip Scaling Foundation result")
    print("  mode=RM103_7W_SYMBOL_PIP_SCALING_FOUNDATION_DIAGNOSTIC_ONLY")
    print("  production_logic_changed=False")
    print("  production_profile_changed=False")
    print("  production_entry_gate_changed=False")
    print("  production_sl_tp_changed=False")
    print("  proximity_hard_gate_reused=False")
    print("  symbols=EURUSD|GBPUSD|USDJPY")
    print("  brokers=CTRADER|IB")
    print("  periods=2025|2026_to_2026-08-25")
    print("  history_files_required=12")
    print(f"  history_files_found={len(stats)}")
    print(
        "  pip_sizes="
        + ",".join(
            f"{symbol}:{pip_size:g}" for symbol, pip_size in SYMBOL_PIP_SIZES.items()
        )
    )
    print(
        "  abc_value_scales="
        + ",".join(f"{symbol}:{abc_scales[symbol]:g}" for symbol in SYMBOL_PIP_SIZES)
    )
    print(f"  inverse_abc_scale_matches_pip={inverse_scale_matches_pip}")
    print("  history_inventory:")
    for broker in BROKERS:
        for symbol in SYMBOL_PIP_SIZES:
            for year in YEARS:
                item = stats[(broker, symbol, year)]
                print(
                    f"    {broker}/{symbol}/{year}:rows:{item.rows},"
                    f"first:{item.first_timestamp},last:{item.last_timestamp},"
                    f"schema:{item.canonical_header},utc:{item.utc_timestamps},"
                    f"ordered:{item.strictly_increasing},ohlc:{item.ohlc_valid}"
                )
    print("  broker_source_close_agreement:")
    for item in agreements:
        print(
            f"    {item.symbol}/{item.year}:overlap:{item.overlap},"
            f"ratio:{item.overlap_ratio:.4f},median:{item.median_pips:.3f}p,"
            f"p95:{item.p95_pips:.3f}p,p99:{item.p99_pips:.3f}p"
        )
    print(
        "  zone_half_width_3p_raw="
        + ",".join(
            f"{symbol}:{_raw_price(symbol, ZONE_HALF_WIDTH_PIPS):.6f}"
            for symbol in SYMBOL_PIP_SIZES
        )
    )
    print("  proximity_threshold_raw_examples:")
    for threshold in FROZEN_PROXIMITY_THRESHOLDS_PIPS:
        values = ",".join(
            f"{symbol}:{_raw_price(symbol, threshold):.6f}"
            for symbol in SYMBOL_PIP_SIZES
        )
        print(f"    {threshold:g}p={values}")
    print(f"  default_history_spread_raw={DEFAULT_WORKSPACE_HISTORY_SPREAD:.8f}")
    print(
        "  default_history_spread_pips="
        + ",".join(f"{symbol}:{spread_pips[symbol]:.4f}" for symbol in SYMBOL_PIP_SIZES)
    )
    print(f"  default_history_spread_symbol_safe={spread_symbol_safe}")
    print(
        "  macd_prominence_pip_equivalent="
        + ",".join(
            f"{symbol}:{prominence_pips[symbol]:.6f}" for symbol in SYMBOL_PIP_SIZES
        )
    )
    print(
        "  macd_distance_pip_equivalent="
        + ",".join(
            f"{symbol}:{distance_pips[symbol]:.6f}" for symbol in SYMBOL_PIP_SIZES
        )
    )
    print(
        "  raw_macd_quality_thresholds_symbol_safe="
        f"{raw_macd_thresholds_symbol_safe}"
    )
    print(f"  all_history_files_valid={all_history_valid}")
    print(f"  broker_source_price_agreement_valid={source_agreement_valid}")
    print("  cross_symbol_candidate_f_execution_started=False")
    print("  cross_symbol_scaling_blockers_identified=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")

    assert len(stats) == 12
    assert inverse_scale_matches_pip
    assert all_history_valid
    assert source_agreement_valid
    assert not spread_symbol_safe
    assert not raw_macd_thresholds_symbol_safe
    print("ALGORITHM_WORKSPACE_SYMBOL_PIP_SCALING_FOUNDATION_CHECK=OK")


if __name__ == "__main__":
    main()
