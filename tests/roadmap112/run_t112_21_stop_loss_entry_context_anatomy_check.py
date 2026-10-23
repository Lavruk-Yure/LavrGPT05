# -*- coding: utf-8 -*-
"""T112-21 — причинний контекст входів із SL, EURUSD 2021–2025.

TEST_ONLY / DATA_ONLY: повторний незмінений Replay кожного року.
Ознаки беруться лише з завершеного сигнального бара до входу.
SL/non-SL — виключно ретроспективна мітка результату, не фільтр.
"""

from __future__ import annotations

import csv
import hashlib
import math
import statistics
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.workspace_runtime import WorkspaceRuntime

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HISTORY_DIR = PROJECT_ROOT / "data" / "history" / "CTRADER" / "EURUSD" / "M1"
SOURCE_A = "2020-10-22_2022-10-21_CTRADER_EURUSD_M1.csv"
SOURCE_B = "2022-10-23_2024-10-21_CTRADER_EURUSD_M1.csv"
SOURCE_C = "2024-10-22_2026-10-21_CTRADER_EURUSD_M1.csv"
CSV_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
REASONS = ("PROFIT_DRAWDOWN", "STOP_LOSS", "TAKE_PROFIT", "SESSION_END")
ZERO_TOLERANCE = 1e-12
GEOMETRY_TOLERANCE = 1e-12
TEST_ID = "T112-21"
MODE = "RM112_T112_21_SL_ENTRY_CONTEXT_TEST_ONLY"


@dataclass(frozen=True)
class YearSpec:
    year: int
    sources: tuple[str, ...]
    rows: int
    first: str
    last: str
    trades: int
    wins: int
    losses: int
    break_even: int
    net_pnl: float
    pf: float
    dd: float
    pd: int
    sl: int
    tp: int


YEARS = (
    YearSpec(
        2021,
        (SOURCE_A,),
        369088,
        "2021-01-03T22:01:00Z",
        "2021-12-31T18:59:00Z",
        19,
        12,
        5,
        2,
        -1.79,
        0.6590,
        2.16,
        15,
        4,
        0,
    ),
    YearSpec(
        2022,
        (SOURCE_A, SOURCE_B),
        370815,
        "2022-01-02T23:00:00Z",
        "2022-12-30T21:58:00Z",
        56,
        35,
        21,
        0,
        -8.42,
        0.5811,
        8.51,
        46,
        10,
        0,
    ),
    YearSpec(
        2023,
        (SOURCE_B,),
        368838,
        "2023-01-01T22:03:00Z",
        "2023-12-29T21:56:00Z",
        45,
        33,
        10,
        2,
        2.58,
        1.4230,
        2.58,
        41,
        4,
        0,
    ),
    YearSpec(
        2024,
        (SOURCE_B, SOURCE_C),
        372060,
        "2024-01-01T22:01:00Z",
        "2024-12-31T21:58:00Z",
        18,
        13,
        5,
        0,
        0.82,
        1.3254,
        1.71,
        17,
        1,
        0,
    ),
    YearSpec(
        2025,
        (SOURCE_C,),
        370481,
        "2025-01-01T22:01:00Z",
        "2025-12-31T21:58:00Z",
        42,
        30,
        11,
        1,
        4.03,
        1.5424,
        3.58,
        36,
        4,
        2,
    ),
)


@dataclass(frozen=True)
class EntryRow:
    year: int
    signal_uid: str
    direction: str
    close_reason: str
    is_sl: bool
    pnl: float
    pnl_r: float
    signal_hour_utc: int
    signal_weekday_utc: int
    signal_range_pips: float
    spread_pips: float
    sl_distance_pips: float
    spread_range_ratio: float | None
    stop_basis: str
    signal_strength: float
    macd_state: str
    alligator_state: str
    filter_regime: str
    filter_phase: str
    filter_active_age: int | None
    filter_slope: float | None
    filter_opening: float | None


PIP_SIZE = 0.0001  # Діагностика виключно EURUSD, не торговий параметр.
GROUPS = (
    ("EARLY_2021_2022", (2021, 2022)),
    ("LATER_2023_2025", (2023, 2024, 2025)),
)


def _bootstrap() -> None:
    """Налаштувати локальні імпорти без запуску GUI."""
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _hash_file(path: Path) -> str:
    """Прочитати відбиток файла без модифікацій."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _production_hashes() -> dict[str, str]:
    """Зберегти контрольний знімок коду й MD7."""
    paths = sorted(
        path
        for folder in ("core", "engine")
        for path in (PROJECT_ROOT / folder).rglob("*.py")
    )
    paths.append(PROJECT_ROOT / "doc" / "LGE_Runtime_07.md")
    assert all(path.is_file() for path in paths)
    return {str(path.relative_to(PROJECT_ROOT)): _hash_file(path) for path in paths}


def _assemble_year(spec: YearSpec, target: Path) -> int:
    """Скопіювати лише бари року в тимчасовий CSV, без заповнення дір."""
    lower = f"{spec.year}-01-01T00:00:00Z"
    upper = f"{spec.year}-12-31T23:59:00Z"
    first: str | None = None
    previous: str | None = None
    total = 0
    part_counts = []
    with target.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(CSV_COLUMNS)
        for name in spec.sources:
            source = HISTORY_DIR / name
            assert source.is_file(), source
            count = 0
            with source.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.reader(stream)
                assert tuple(next(reader)) == CSV_COLUMNS, name
                for row in reader:
                    assert len(row) == len(CSV_COLUMNS), name
                    timestamp = row[0]
                    if not lower <= timestamp <= upper:
                        continue
                    if previous is not None and timestamp <= previous:
                        raise AssertionError(
                            f"Non-increasing M1: {previous} -> {timestamp}"
                        )
                    if first is None:
                        first = timestamp
                    previous = timestamp
                    writer.writerow(row)
                    count += 1
                    total += 1
            part_counts.append(count)
    assert total == spec.rows, (spec.year, total, spec.rows)
    assert first == spec.first, (spec.year, first, spec.first)
    assert previous == spec.last, (spec.year, previous, spec.last)
    print(
        f"source_{spec.year}=parts:{len(spec.sources)},"
        f"part_rows:{','.join(map(str, part_counts))},"
        f"total_rows:{total},first:{first},last:{previous}"
    )
    return total


def _workspace(year_path: Path, year: int):
    """Побудувати конфігурацію чинного Candidate F без адаптації порогів."""
    from engine.runtime_constants import (
        DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT,
    )
    from tests.runtime_workspace import (
        run_algorithm_workspace_candidate_f_frozen_oos_2025_check as frozen,
    )

    workspace = frozen.frozen_oos_workspace()
    workspace.broker = "CTRADER"
    protection = dict(workspace.profit_protection)
    protection["max_profit_drawdown_percent"] = (
        DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT
    )
    workspace.profit_protection = protection
    settings = dict(workspace.replay_settings)
    settings.update(
        {
            "file_path": str(year_path),
            "start_utc": f"{year}-01-01T00:00:00+00:00",
            "end_utc": f"{year}-12-31T23:59:00+00:00",
            "source": year_path.stem,
            "source_timeframe": "M1",
        }
    )
    workspace.replay_settings = settings
    assert workspace.parameters["macd_extremum_min_prominence"] == 0.000015
    assert workspace.parameters["macd_extremum_to_cross_min_distance"] == 0.000050
    assert workspace.parameters["macd_cross_min_abc_angle"] == 2.25
    return workspace


def _check_runtime(runtime: WorkspaceRuntime, spec: YearSpec) -> None:
    """Контролювати виробничу геометрію та еталонні річні підсумки."""
    from core.workspace_alligator import WorkspaceMacdAlligatorReplayAlgorithm
    from core.workspace_profit_guard import (
        WorkspaceCandidateFNegativePdRecoveryGuard,
    )

    execution = runtime.replay_execution
    session = runtime.replay_session
    summary = runtime.historical_summary
    assert execution is not None and session is not None and session.completed
    assert summary is not None
    assert type(runtime.algorithm) is WorkspaceMacdAlligatorReplayAlgorithm
    assert isinstance(
        runtime.profit_drawdown_guard,
        WorkspaceCandidateFNegativePdRecoveryGuard,
    )
    assert runtime.profit_protection_policy.max_drawdown_percent == 35.0
    assert execution.policy.stop_range_multiplier == 1.0
    assert execution.policy.minimum_spread_multiples == 10.0
    assert execution.policy.take_profit_r_multiple == 2.0
    assert session.strategy_timeframe == "M15"
    assert session.source_timeframe == "M1"
    actual = (
        summary.opened_trades,
        summary.winning_trades,
        summary.losing_trades,
        summary.break_even_trades,
    )
    expected = (spec.trades, spec.wins, spec.losses, spec.break_even)
    assert actual == expected, (spec.year, actual, expected)
    assert math.isclose(summary.net_profit, spec.net_pnl, abs_tol=0.005)
    assert summary.profit_factor is not None
    assert math.isclose(summary.profit_factor, spec.pf, abs_tol=0.00005)
    assert math.isclose(summary.maximum_drawdown, spec.dd, abs_tol=0.005)
    assert summary.close_reason_count("PROFIT_DRAWDOWN") == spec.pd
    assert summary.close_reason_count("STOP_LOSS") == spec.sl
    assert summary.close_reason_count("TAKE_PROFIT") == spec.tp
    assert summary.close_reason_count("SESSION_END") == 0
    assert len(execution.trade_diagnostics()) == spec.trades
    assert all(
        record.filter_context is None
        or record.filter_context.available_at is None
        or record.filter_context.available_at <= record.timestamp
        for record in runtime.signal_records_for_ui()
    )
    print(
        f"baseline_{spec.year}=MATCH|trades:{spec.trades},"
        f"W:{spec.wins},L:{spec.losses},BE:{spec.break_even},"
        f"net_pnl:{summary.net_profit:+.2f},"
        f"PF:{summary.profit_factor:.4f},"
        f"DD:{summary.maximum_drawdown:.2f}"
    )


def _extract_entries(
    runtime: WorkspaceRuntime | SimpleNamespace, year: int
) -> list[EntryRow]:
    """Зіставити SL label із causal snapshot до наступного відкриття."""
    execution = runtime.replay_execution
    session = runtime.replay_session
    assert execution is not None and session is not None
    source_events = {event.timestamp: event for event in session.events}
    records = runtime.signal_records_for_ui()
    accepted = {item.signal_uid: item for item in records if item.accepted}
    rows: list[EntryRow] = []
    for trade in execution.trade_diagnostics():
        record = accepted[trade.signal_uid]
        assert record.timestamp == trade.signal_timestamp
        assert trade.signal_timestamp <= trade.entry_timestamp
        event = source_events[record.timestamp]
        assert event.timeframe == "M15" and event.source_mode == "REPLAY"
        bar_range = event.high - event.low
        spread_floor = event.spread * 10.0
        distance = max(bar_range, spread_floor)
        assert distance > 0.0 and trade.volume > 0.0
        assert math.isclose(
            trade.stop_loss_distance,
            distance,
            rel_tol=0.0,
            abs_tol=GEOMETRY_TOLERANCE,
        )
        assert math.isclose(
            trade.take_profit_distance,
            distance * 2.0,
            rel_tol=0.0,
            abs_tol=GEOMETRY_TOLERANCE,
        )
        context = record.filter_context
        if context is not None and context.available_at is not None:
            assert context.available_at <= trade.signal_timestamp
        assert trade.close_reason in REASONS
        rows.append(
            EntryRow(
                year=year,
                signal_uid=trade.signal_uid,
                direction=record.direction,
                close_reason=trade.close_reason,
                is_sl=trade.close_reason == "STOP_LOSS",
                pnl=trade.final_profit,
                pnl_r=trade.final_profit / (distance * trade.volume),
                signal_hour_utc=record.timestamp.hour,
                signal_weekday_utc=record.timestamp.weekday(),
                signal_range_pips=bar_range / PIP_SIZE,
                spread_pips=event.spread / PIP_SIZE,
                sl_distance_pips=distance / PIP_SIZE,
                spread_range_ratio=(
                    event.spread / bar_range if bar_range > 0.0 else None
                ),
                stop_basis=(
                    "SPREAD_FLOOR" if spread_floor > bar_range else "BAR_RANGE"
                ),
                signal_strength=record.strength,
                macd_state=record.macd_state,
                alligator_state=trade.alligator_state,
                filter_regime=(context.regime if context is not None else None)
                or "UNAVAILABLE",
                filter_phase=(context.regime_phase if context is not None else None)
                or "UNAVAILABLE",
                filter_active_age=(context.active_age if context is not None else None),
                filter_slope=(
                    context.normalized_slope if context is not None else None
                ),
                filter_opening=(
                    context.normalized_opening if context is not None else None
                ),
            )
        )
    return rows


def _run_year(spec: YearSpec, path: Path, count: int) -> list[EntryRow]:
    """Один незмінений Replay із зіставленням сигналів і SL-міток."""
    from core.workspace_algorithm import create_registered_workspace_algorithm
    from core.workspace_runtime import WorkspaceRuntime
    from tests.runtime_workspace import (
        run_algorithm_workspace_replay_virtual_execution_check as virtual,
    )

    probe = virtual.BrokerRequestProbe()
    runtime = WorkspaceRuntime(
        _workspace(path, spec.year),
        algorithm_factory=create_registered_workspace_algorithm,
        broker_market_provider=probe,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None and session.source_event_count == count
    assert session.history_report is not None
    assert session.history_report.accepted_rows == count
    while not session.completed:
        runtime.advance_replay()
    _check_runtime(runtime, spec)
    rows = _extract_entries(runtime, spec.year)
    assert probe.requests == 0, (spec.year, probe.requests)
    assert not any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert len(rows) == spec.trades
    assert sum(row.is_sl for row in rows) == spec.sl
    print(f"year={spec.year}|trades={len(rows)}|SL={spec.sl}|broker_requests=0")
    return rows


def _time_bucket(hour: int) -> str:
    """Фіксовані восьмигодинні UTC-групи без підбору порогів."""
    assert 0 <= hour <= 23
    return ("UTC_00_07", "UTC_08_15", "UTC_16_23")[hour // 8]


def _number(value: float | int | None) -> str:
    """Вивести медіану або позначити відсутність спостережень."""
    return "NA" if value is None else f"{value:.4f}"


def _median(rows: list[EntryRow], field: str) -> str:
    """Медіана з явним обліком відсутніх діагностичних значень."""
    values = [getattr(row, field) for row in rows]
    valid = [float(value) for value in values if value is not None]
    med = statistics.median(valid) if valid else None
    return f"{_number(med)}|available:{len(valid)}/{len(rows)}"


def _describe_categories(
    name: str,
    rows: list[EntryRow],
    field: str,
) -> None:
    """Показати знаменник і SL-rate для кожної фіксованої категорії."""
    observed = Counter(getattr(row, field) for row in rows)
    sl_counts = Counter(getattr(row, field) for row in rows if row.is_sl)
    for value, total in sorted(observed.items(), key=lambda part: str(part[0])):
        count = sl_counts[value]
        print(
            f"{name}|feature={field}|value={value}|"
            f"SL:{count},nonSL:{total - count},"
            f"SL_rate:{count / total:.4f},n:{total}"
        )


def _describe(name: str, rows: list[EntryRow]) -> None:
    """Порівняти лише pre-entry ознаки; SL є ex-post outcome."""
    sl = [row for row in rows if row.is_sl]
    other = [row for row in rows if not row.is_sl]
    print(
        f"{name}|trades:{len(rows)},SL:{len(sl)},nonSL:{len(other)},"
        f"SL_rate:{len(sl) / len(rows):.4f},"
        f"SL_net_r:{math.fsum(row.pnl_r for row in sl):+.3f}"
    )
    for label, subset in (("SL", sl), ("NON_SL", other)):
        for field in (
            "signal_range_pips",
            "spread_pips",
            "sl_distance_pips",
            "spread_range_ratio",
            "signal_strength",
            "filter_active_age",
            "filter_slope",
            "filter_opening",
        ):
            print(
                f"{name}|outcome={label}|feature={field}|"
                f"median={_median(subset, field)}"
            )
    for field in (
        "direction",
        "stop_basis",
        "utc_bucket",
        "weekday_bucket",
        "macd_state",
        "alligator_state",
        "filter_regime",
        "filter_phase",
    ):
        # Часові групи обчислюються тільки з timestamp сигнального бара.
        if field == "utc_bucket":
            categories = [
                (_time_bucket(row.signal_hour_utc), row.is_sl) for row in rows
            ]
        elif field == "weekday_bucket":
            categories = [(str(row.signal_weekday_utc), row.is_sl) for row in rows]
        else:
            _describe_categories(name, rows, field)
            continue
        total = Counter(category for category, _ in categories)
        sl_count = Counter(category for category, is_sl in categories if is_sl)
        for category, count in sorted(total.items()):
            hit = sl_count[category]
            print(
                f"{name}|feature={field}|value={category}|"
                f"SL:{hit},nonSL:{count - hit},"
                f"SL_rate:{hit / count:.4f},n:{count}"
            )


def _synthetic_contract() -> None:
    """Перевірити причинність і класифікацію на штучних угодах."""
    from datetime import UTC, datetime, timedelta

    assert [_time_bucket(h) for h in (0, 7, 8, 15, 16, 23)] == [
        "UTC_00_07",
        "UTC_00_07",
        "UTC_08_15",
        "UTC_08_15",
        "UTC_16_23",
        "UTC_16_23",
    ]
    assert _number(None) == "NA"
    assert _number(1.5) == "1.5000"
    signal_time = datetime(2021, 1, 4, 8, 15, tzinfo=UTC)
    events = []
    records = []
    trades = []
    for index, (bar_range, spread, reason) in enumerate(
        ((0.0006, 0.00002, "STOP_LOSS"), (0.0001, 0.00002, "PROFIT_DRAWDOWN"))
    ):
        timestamp = signal_time + timedelta(minutes=30 * index)
        uid = f"synthetic-{index}"
        distance = max(bar_range, spread * 10.0)
        events.append(
            SimpleNamespace(
                timestamp=timestamp,
                timeframe="M15",
                source_mode="REPLAY",
                high=1.101 + bar_range,
                low=1.101,
                spread=spread,
            )
        )
        context = SimpleNamespace(
            available_at=timestamp,
            regime="TREND_UP",
            regime_phase="ACTIVE",
            active_age=3,
            normalized_slope=0.2,
            normalized_opening=0.3,
        )
        records.append(
            SimpleNamespace(
                accepted=True,
                signal_uid=uid,
                timestamp=timestamp,
                direction="BUY",
                strength=1.0,
                macd_state="CROSS_UP",
                filter_context=context,
            )
        )
        trades.append(
            SimpleNamespace(
                signal_uid=uid,
                signal_timestamp=timestamp,
                entry_timestamp=timestamp + timedelta(minutes=15),
                stop_loss_distance=distance,
                take_profit_distance=distance * 2.0,
                volume=1000,
                close_reason=reason,
                final_profit=-distance * 1000 if index == 0 else 0.05,
                alligator_state="BULLISH",
            )
        )
    runtime = SimpleNamespace(
        replay_execution=SimpleNamespace(trade_diagnostics=lambda: trades),
        replay_session=SimpleNamespace(events=events),
        signal_records_for_ui=lambda: records,
    )
    extracted = _extract_entries(runtime, 2021)
    assert [row.stop_basis for row in extracted] == [
        "BAR_RANGE",
        "SPREAD_FLOOR",
    ]
    assert [row.is_sl for row in extracted] == [True, False]
    assert extracted[0].signal_hour_utc == 8
    assert math.isclose(extracted[0].pnl_r, -1.0)
    assert math.isclose(extracted[1].sl_distance_pips, 2.0)
    print("SYNTHETIC_ENTRY_CONTEXT_CLASSIFICATION=OK")
    print("SYNTHETIC_COMPLETED_SIGNAL_CAUSAL_JOIN=OK")


def _describe_year(name: str, rows: list[EntryRow]) -> None:
    """Стисла річна перевірка чисельника та знаменника SL."""
    sl_count = sum(row.is_sl for row in rows)
    basis = Counter(row.stop_basis for row in rows if row.is_sl)
    print(
        f"{name}|trades:{len(rows)},SL:{sl_count},"
        f"nonSL:{len(rows) - sl_count},"
        f"SL_rate:{sl_count / len(rows):.4f},"
        f"SL_by_basis:{dict(sorted(basis.items()))}"
    )


def main() -> None:
    """Порівняти доступний до входу контекст SL і решти угод."""
    _bootstrap()
    print("T112_21_STOP_LOSS_ENTRY_CONTEXT_ANATOMY")
    print(f"test_id={TEST_ID}|mode={MODE}")
    print("symbol=EURUSD|broker=CTRADER|source=M1|strategy=M15")
    print("periods=2021,2022,2023,2024,2025|completed_bars_only=True")
    print("labels=EXPOST_SL_VS_NON_SL|features=SIGNAL_BAR_CAUSAL_ONLY")
    print("time_basis=UTC|pip_size=0.0001|threshold_optimization=False")
    _synthetic_contract()
    production_before = _production_hashes()
    source_paths = {HISTORY_DIR / name for spec in YEARS for name in spec.sources}
    source_before = {str(p): _hash_file(p) for p in sorted(source_paths)}
    all_rows: list[EntryRow] = []
    with tempfile.TemporaryDirectory(prefix="t112_21_") as temp_dir:
        for spec in YEARS:
            path = Path(temp_dir) / (
                f"{spec.year}-01-01_{spec.year}-12-31_CTRADER_EURUSD_M1.csv"
            )
            count = _assemble_year(spec, path)
            rows = _run_year(spec, path, count)
            all_rows.extend(rows)
            _describe_year(f"year={spec.year}", rows)
            path.unlink()
    assert source_before == {str(p): _hash_file(p) for p in sorted(source_paths)}
    assert production_before == _production_hashes()
    assert len(all_rows) == 180
    assert len({row.signal_uid for row in all_rows}) == len(all_rows)
    assert sum(row.is_sl for row in all_rows) == 23
    for group_name, years in GROUPS:
        subset = [row for row in all_rows if row.year in years]
        _describe(f"group={group_name}", subset)
    print("outcome_labels=OBSERVATIONAL_NOT_CAUSAL_PREDICTORS")
    print("entry_filter_counterfactual=NOT_TESTED")
    print("parameter_optimization=NONE")
    print("replay_determinism=NOT_RERUN_ONE_REPLAY_PER_YEAR")
    print("source_history_modified=False")
    print("temporary_csv_removed=True")
    print("production_logic_changed=False")
    print("exit_logic_changed=False")
    print("md7_changed=False")
    print("broker_requests=0")
    print("T112_21_STOP_LOSS_ENTRY_CONTEXT_ANATOMY=OK")


if __name__ == "__main__":
    main()
