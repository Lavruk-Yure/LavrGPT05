# -*- coding: utf-8 -*-
"""T112-20 — анатомія втрат Historical Replay EURUSD, 2021–2025.

TEST_ONLY / DATA_ONLY: повторний незмінений Replay кожного року.
Звіт порівнює фактичні закриті угоди та причини PD/SL/TP.
Результати MFE/MAE — ретроспективні, не сигнали для торгівлі.
"""

from __future__ import annotations

import csv
import hashlib
import math
import statistics
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
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
TEST_ID = "T112-20"
MODE = "RM112_T112_20_HISTORICAL_LOSS_ANATOMY_TEST_ONLY"


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
class TradeRow:
    year: int
    direction: str
    reason: str
    pnl: float
    pnl_r: float
    mfe_r: float
    mae_r: float
    hold_hours: float


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


def _extract_trades(runtime: WorkspaceRuntime, year: int) -> list[TradeRow]:
    """Обчислити post-trade PnL та нормалізовані одиниці ризику."""
    execution = runtime.replay_execution
    session = runtime.replay_session
    assert execution is not None and session is not None
    source_events = {event.timestamp: event for event in session.events}
    records = runtime.signal_records_for_ui()
    accepted = {item.signal_uid: item for item in records if item.accepted}
    rows = []
    for trade in execution.trade_diagnostics():
        record = accepted[trade.signal_uid]
        event = source_events[record.timestamp]
        distance = max(event.high - event.low, event.spread * 10.0)
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
        assert trade.signal_timestamp <= trade.entry_timestamp
        assert trade.entry_timestamp <= trade.close_timestamp
        assert trade.close_reason in REASONS
        assert trade.volume > 0.0 and distance > 0.0
        risk_unit = distance * trade.volume
        rows.append(
            TradeRow(
                year=year,
                direction=trade.direction,
                reason=trade.close_reason,
                pnl=trade.final_profit,
                pnl_r=trade.final_profit / risk_unit,
                mfe_r=trade.maximum_favorable_excursion / risk_unit,
                mae_r=trade.maximum_adverse_excursion / risk_unit,
                hold_hours=trade.holding_seconds / 3600.0,
            )
        )
    return rows


def _run_year(spec: YearSpec, path: Path, count: int) -> list[TradeRow]:
    """Виконати один factual Replay та вилучити лише діагностику угод."""
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
    rows = _extract_trades(runtime, spec.year)
    assert probe.requests == 0, (spec.year, probe.requests)
    assert not any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    print(f"year={spec.year}|trades={len(rows)}|broker_requests=0")
    return rows


def _sign(value: float) -> str:
    """Класифікувати нуль, так само як historical summary."""
    if value > ZERO_TOLERANCE:
        return "W"
    if value < -ZERO_TOLERANCE:
        return "L"
    return "BE"


def _describe(label: str, rows: list[TradeRow]) -> None:
    """Друкувати порівнянні фактичні метрики в PnL і R."""
    wins = [trade for trade in rows if _sign(trade.pnl) == "W"]
    losses = [trade for trade in rows if _sign(trade.pnl) == "L"]
    flats = [trade for trade in rows if _sign(trade.pnl) == "BE"]
    net_pnl = math.fsum(trade.pnl for trade in rows)
    net_r = math.fsum(trade.pnl_r for trade in rows)
    gross_win = math.fsum(trade.pnl for trade in wins)
    gross_loss = math.fsum(trade.pnl for trade in losses)
    pf = "NONE" if not losses else f"{gross_win / -gross_loss:.4f}"
    avg_win = math.fsum(trade.pnl_r for trade in wins) / len(wins) if wins else 0.0
    avg_loss = (
        math.fsum(trade.pnl_r for trade in losses) / len(losses) if losses else 0.0
    )
    print(
        f"{label}|trades:{len(rows)},W:{len(wins)},L:{len(losses)},"
        f"BE:{len(flats)},net_pnl:{net_pnl:+.4f},net_r:{net_r:+.3f},"
        f"PF:{pf},avg_win_r:{avg_win:+.3f},avg_loss_r:{avg_loss:+.3f}"
    )
    for reason in REASONS:
        subset = [trade for trade in rows if trade.reason == reason]
        reason_losses = [trade for trade in subset if _sign(trade.pnl) == "L"]
        reason_wins = [trade for trade in subset if _sign(trade.pnl) == "W"]
        reason_be = len(subset) - len(reason_losses) - len(reason_wins)
        print(
            f"{label}|reason={reason}|trades:{len(subset)},"
            f"W:{len(reason_wins)},L:{len(reason_losses)},BE:{reason_be},"
            f"net_pnl:{math.fsum(t.pnl for t in subset):+.4f},"
            f"net_r:{math.fsum(t.pnl_r for t in subset):+.3f},"
            f"loss_pnl:{math.fsum(t.pnl for t in reason_losses):+.4f},"
            f"loss_r:{math.fsum(t.pnl_r for t in reason_losses):+.3f}"
        )
    if losses:
        print(
            f"{label}|losers_expost="
            f"median_mfe_r:{statistics.median(t.mfe_r for t in losses):.3f},"
            f"median_mae_r:{statistics.median(t.mae_r for t in losses):.3f},"
            f"median_hold_h:{statistics.median(t.hold_hours for t in losses):.2f},"
            f"buy:{sum(t.direction == 'BUY' for t in losses)},"
            f"sell:{sum(t.direction == 'SELL' for t in losses)}"
        )


def _test_aggregation() -> None:
    """Окремо перевірити знак PnL і арифметику нормалізації R."""
    sample = [
        TradeRow(2021, "BUY", "PROFIT_DRAWDOWN", -0.5, -0.5, 0.6, -0.8, 1.0),
        TradeRow(2021, "SELL", "STOP_LOSS", -1.0, -1.0, 0.0, -1.0, 2.0),
        TradeRow(2021, "BUY", "PROFIT_DRAWDOWN", 1.0, 1.0, 1.2, -0.2, 3.0),
        TradeRow(2021, "BUY", "PROFIT_DRAWDOWN", 0.0, 0.0, 0.0, 0.0, 0.0),
    ]
    assert [_sign(t.pnl) for t in sample] == ["L", "L", "W", "BE"]
    assert math.isclose(math.fsum(t.pnl_r for t in sample), -0.5)
    assert len([t for t in sample if t.reason == "PROFIT_DRAWDOWN"]) == 3
    print("SYNTHETIC_LOSS_DECOMPOSITION=OK")


def main() -> None:
    """Порівняти збитки ранніх і пізніх років без зміни стратегії."""
    _bootstrap()
    print("T112_20_HISTORICAL_LOSS_ANATOMY")
    print(f"test_id={TEST_ID}|mode={MODE}")
    print("symbol=EURUSD|broker=CTRADER|source=M1|strategy=M15")
    print("periods=2021,2022,2023,2024,2025|completed_bars_only=True")
    print("metric_units=net_pnl:VIRTUAL_PNL,net_r:INITIAL_SL_RISK")
    _test_aggregation()
    production_before = _production_hashes()
    source_paths = {HISTORY_DIR / name for spec in YEARS for name in spec.sources}
    source_before = {str(p): _hash_file(p) for p in sorted(source_paths)}
    all_rows: list[TradeRow] = []
    with tempfile.TemporaryDirectory(prefix="t112_20_") as temp_dir:
        for spec in YEARS:
            path = Path(temp_dir) / (
                f"{spec.year}-01-01_{spec.year}-12-31_CTRADER_EURUSD_M1.csv"
            )
            count = _assemble_year(spec, path)
            rows = _run_year(spec, path, count)
            _describe(f"year={spec.year}", rows)
            all_rows.extend(rows)
            path.unlink()
    assert source_before == {str(p): _hash_file(p) for p in sorted(source_paths)}
    assert production_before == _production_hashes()
    early = [t for t in all_rows if t.year in (2021, 2022)]
    later = [t for t in all_rows if t.year in (2023, 2024, 2025)]
    assert len(early) == 75 and len(later) == 105
    print("comparative_groups=EARLY_2021_2022|LATER_2023_2025")
    _describe("group=EARLY_2021_2022", early)
    _describe("group=LATER_2023_2025", later)
    print("expost_mfe_mae=DIAGNOSTIC_ONLY_NO_CAUSAL_CLAIM")
    print("exit_counterfactual=NOT_TESTED")
    print("replay_determinism=NOT_RERUN_ONE_REPLAY_PER_YEAR")
    print("source_history_modified=False")
    print("temporary_csv_removed=True")
    print("production_logic_changed=False")
    print("exit_logic_changed=False")
    print("md7_changed=False")
    print("broker_requests=0")
    print("T112_20_HISTORICAL_LOSS_ANATOMY=OK")


if __name__ == "__main__":
    main()
