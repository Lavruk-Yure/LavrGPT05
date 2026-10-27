# -*- coding: utf-8 -*-
"""T112-28 — порівняння PD/SL/TP трьох пар за 2024–2025 роки.

TEST_ONLY / DATA_ONLY. Шість незмінних Replay, без брокерських запитів.
Порівняння між парами ведеться в R, а не за сирим PnL.
"""

from __future__ import annotations

import csv
import hashlib
import math
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.workspace_runtime import WorkspaceRuntime

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HISTORY_ROOT = PROJECT_ROOT / "data" / "history" / "CTRADER"
CSV_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
REASONS = ("PROFIT_DRAWDOWN", "STOP_LOSS", "TAKE_PROFIT", "SESSION_END")
TEST_ID = "T112-28"
MODE = "RM112_T112_28_CROSS_SYMBOL_EXIT_ANATOMY_TEST_ONLY"


@dataclass(frozen=True)
class Spec:
    symbol: str
    year: int
    rows: int
    part_rows: tuple[int, ...]
    trades: int
    wins: int
    losses: int
    be: int
    net_pnl: float
    net_r: float
    pf: float
    dd: float
    pd: int
    sl: int
    tp: int
    pd_r: float


SPECS = (
    Spec("EURUSD", 2024, 372060, (300544, 71516),
         18, 13, 5, 0, 0.82, 1.015, 1.3254, 1.71, 17, 1, 0, 2.015),
    Spec("GBPUSD", 2024, 372659, (301086, 71573),
         29, 18, 10, 1, -5.63, -5.267, 0.4086, 6.78, 22, 7, 0, 1.733),
    Spec("USDJPY", 2024, 372474, (300956, 71518),
         34, 21, 13, 0, -855.00, -4.434, 0.3262, 879.00, 29, 5, 0,
         0.566),
    Spec("EURUSD", 2025, 370481, (370481,),
         42, 30, 11, 1, 4.03, 2.630, 1.5424, 3.58, 36, 4, 2, 2.630),
    Spec("GBPUSD", 2025, 369938, (369938,),
         71, 49, 20, 2, -7.66, -4.279, 0.5728, 9.38, 63, 8, 0, 3.721),
    Spec("USDJPY", 2025, 369962, (369962,),
         39, 28, 10, 1, -795.00, -2.882, 0.4502, 823.00, 34, 5, 0,
         2.118),
)


@dataclass(frozen=True)
class TradeRow:
    direction: str
    reason: str
    pnl: float
    pnl_r: float
    stop_basis: str
    signal_range_pips: float
    sl_distance_pips: float


def _bootstrap() -> None:
    """Дозволити запуск файла без налаштування PYTHONPATH."""
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _sha256(path: Path) -> str:
    """Обчислити контрольну суму файла лише для читання."""
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def _production_hashes() -> dict[str, str]:
    """Перевірити, що production і MD7 не змінюються тестом."""
    paths = sorted(
        path
        for folder in ("core", "engine")
        for path in (PROJECT_ROOT / folder).rglob("*.py")
    )
    paths.append(PROJECT_ROOT / "doc" / "LGE_Runtime_07.md")
    assert paths and all(path.is_file() for path in paths)
    return {str(path.relative_to(PROJECT_ROOT)): _sha256(path)
            for path in paths}


def _sources(spec: Spec) -> tuple[Path, ...]:
    """Повернути перевірені cTrader-частини потрібного року."""
    folder = HISTORY_ROOT / spec.symbol / "M1"
    if spec.year == 2024:
        names = (
            f"2022-10-23_2024-10-21_CTRADER_{spec.symbol}_M1.csv",
            f"2024-10-22_2026-10-21_CTRADER_{spec.symbol}_M1.csv",
        )
    else:
        names = (f"2024-10-22_2026-10-21_CTRADER_{spec.symbol}_M1.csv",)
    return tuple(folder / name for name in names)


def _legacy_2025(spec: Spec) -> Path:
    """Повернути старий 2025 CSV для точного порівняння."""
    return (
        HISTORY_ROOT / spec.symbol / "M1"
        / f"2025-01-01_2025-12-31_CTRADER_{spec.symbol}_M1.csv"
    )


def _assemble(spec: Spec, target: Path) -> None:
    """Зібрати рік без заповнення M1 і без зміни джерел."""
    counts = []
    previous = None
    first = None
    start = f"{spec.year}-01-01T00:00:00Z"
    end = f"{spec.year}-12-31T23:59:00Z"
    with target.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(CSV_COLUMNS)
        for source in _sources(spec):
            assert source.is_file(), source
            count = 0
            with source.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.reader(stream)
                assert tuple(next(reader)) == CSV_COLUMNS, source
                for row in reader:
                    assert len(row) == len(CSV_COLUMNS), source
                    stamp = row[0]
                    if not start <= stamp <= end:
                        continue
                    assert previous is None or stamp > previous, (
                        previous, stamp
                    )
                    if first is None:
                        first = stamp
                    previous = stamp
                    writer.writerow(row)
                    count += 1
            counts.append(count)
            print(f"source={source.name}|year_rows={count}")
    assert tuple(counts) == spec.part_rows, (spec, counts)
    assert sum(counts) == spec.rows, (spec, counts)
    assert first == f"{spec.year}-01-01T22:01:00Z", first
    assert previous == f"{spec.year}-12-31T21:58:00Z", previous
    print(f"history={spec.symbol}_{spec.year}|M1:{spec.rows}")
    if spec.year == 2025:
        legacy = _legacy_2025(spec)
        assert legacy.is_file(), legacy
        with (
            target.open("r", encoding="utf-8", newline="") as new_stream,
            legacy.open("r", encoding="utf-8-sig", newline="") as old_stream,
        ):
            fresh = csv.reader(new_stream)
            old = csv.reader(old_stream)
            assert next(fresh) == next(old) == list(CSV_COLUMNS)
            count = 0
            for current, previous_row in zip(fresh, old, strict=True):
                assert current == previous_row, (spec.symbol, count)
                count += 1
            assert count == spec.rows
        print(f"legacy_{spec.symbol}_2025=EXACT_ROW_MATCH|rows:{count}")


def _workspace(spec: Spec, path: Path):
    """Створити frozen Candidate F, змінюючи лише інструмент і UTC-рік."""
    from engine.runtime_constants import (
        DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT,
        resolve_forex_pip_size,
        resolve_new_workspace_macd_extremum_min_prominence,
        resolve_new_workspace_macd_extremum_to_cross_min_distance,
        resolve_workspace_history_default_spread,
    )
    from tests.runtime_workspace import (
        run_algorithm_workspace_candidate_f_frozen_oos_2025_check as frozen,
    )

    workspace = frozen.frozen_oos_workspace()
    assert workspace.symbol == "EURUSD"
    parameters = dict(workspace.parameters)
    settings = dict(workspace.replay_settings)
    if spec.symbol == "USDJPY":
        base_pip = resolve_forex_pip_size("EURUSD")
        pip = resolve_forex_pip_size("USDJPY")
        assert base_pip == 0.0001 and pip == 0.01
        assert parameters["spread_limit"] == 0.00020
        assert parameters["macd_extremum_min_prominence"] == 0.000015
        assert parameters["macd_extremum_to_cross_min_distance"] == 0.000050
        assert settings["spread"] == 0.00012
        parameters["spread_limit"] *= pip / base_pip
        parameters["macd_extremum_min_prominence"] = (
            resolve_new_workspace_macd_extremum_min_prominence("USDJPY")
        )
        parameters["macd_extremum_to_cross_min_distance"] = (
            resolve_new_workspace_macd_extremum_to_cross_min_distance("USDJPY")
        )
        settings["spread"] = resolve_workspace_history_default_spread(
            "USDJPY"
        )
        assert math.isclose(parameters["spread_limit"], 0.020)
        assert math.isclose(
            parameters["macd_extremum_min_prominence"], 0.0015
        )
        assert math.isclose(
            parameters["macd_extremum_to_cross_min_distance"], 0.005
        )
        assert math.isclose(settings["spread"], 0.012)
        print("USDJPY_pip_contract=0.01|threshold_retuning=False")
    else:
        assert parameters["spread_limit"] == 0.00020
        assert settings["spread"] == 0.00012
    assert parameters["macd_cross_min_abc_angle"] == 2.25
    workspace.symbol = spec.symbol
    workspace.broker = "CTRADER"
    workspace.parameters = parameters
    protection = dict(workspace.profit_protection)
    protection["max_profit_drawdown_percent"] = (
        DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT
    )
    workspace.profit_protection = protection
    settings.update({
        "file_path": str(path),
        "start_utc": f"{spec.year}-01-01T00:00:00+00:00",
        "end_utc": f"{spec.year}-12-31T23:59:00+00:00",
        "source": path.stem,
        "source_timeframe": "M1",
    })
    workspace.replay_settings = settings
    return workspace


def _classify(pnl: float) -> str:
    """Розрізняти W/L/BE за незакругленим PnL."""
    if pnl > 1e-12:
        return "W"
    if pnl < -1e-12:
        return "L"
    return "BE"


def _extract_trades(runtime: WorkspaceRuntime, symbol: str) -> list[TradeRow]:
    """Оцінити R від початкового SL без використання майбутніх ознак."""
    from engine.runtime_constants import resolve_forex_pip_size

    pip = resolve_forex_pip_size(symbol)
    session = runtime.replay_session
    execution = runtime.replay_execution
    assert session is not None and session.completed
    assert execution is not None
    events = {event.timestamp: event for event in session.events}
    records = runtime.signal_records_for_ui()
    accepted = {record.signal_uid: record for record in records if record.accepted}
    assert all(
        record.filter_context is None
        or record.filter_context.available_at is None
        or record.filter_context.available_at <= record.timestamp
        for record in records
    )
    rows = []
    for trade in execution.trade_diagnostics():
        record = accepted[trade.signal_uid]
        assert record.direction == trade.direction
        assert record.timestamp == trade.signal_timestamp
        assert trade.signal_timestamp <= trade.entry_timestamp
        event = events[record.timestamp]
        assert event.timeframe == "M15" and event.source_mode == "REPLAY"
        signal_range = event.high - event.low
        spread_floor = event.spread * 10.0
        distance = max(signal_range, spread_floor)
        assert distance > 0.0 and trade.volume > 0.0
        assert math.isclose(
            trade.stop_loss_distance, distance, rel_tol=0.0, abs_tol=1e-12
        )
        assert math.isclose(
            trade.take_profit_distance, distance * 2.0,
            rel_tol=0.0, abs_tol=1e-12,
        )
        assert trade.close_reason in REASONS
        assert trade.direction in ("BUY", "SELL")
        rows.append(TradeRow(
            direction=trade.direction,
            reason=trade.close_reason,
            pnl=trade.final_profit,
            pnl_r=trade.final_profit / (distance * trade.volume),
            stop_basis=(
                "SPREAD_FLOOR" if spread_floor > signal_range
                else "BAR_RANGE"
            ),
            signal_range_pips=signal_range / pip,
            sl_distance_pips=distance / pip,
        ))
    return rows


def _metrics(spec: Spec, summary, rows: list[TradeRow]) -> None:
    """Порівняти новий Replay із зафіксованими попередніми тестами."""
    assert len(rows) == spec.trades == summary.opened_trades
    assert summary.period_start.year == spec.year
    assert summary.period_end.year == spec.year
    counts = (
        sum(_classify(row.pnl) == "W" for row in rows),
        sum(_classify(row.pnl) == "L" for row in rows),
        sum(_classify(row.pnl) == "BE" for row in rows),
    )
    assert counts == (spec.wins, spec.losses, spec.be), (spec, counts)
    for reason, expected in (
        ("PROFIT_DRAWDOWN", spec.pd),
        ("STOP_LOSS", spec.sl),
        ("TAKE_PROFIT", spec.tp),
        ("SESSION_END", 0),
    ):
        count = sum(row.reason == reason for row in rows)
        assert count == expected == summary.close_reason_count(reason)
    assert math.isclose(summary.net_profit, spec.net_pnl, abs_tol=0.005)
    assert summary.profit_factor is not None
    assert math.isclose(summary.profit_factor, spec.pf, abs_tol=0.00006)
    assert math.isclose(summary.maximum_drawdown, spec.dd, abs_tol=0.005)
    assert math.isclose(
        math.fsum(row.pnl for row in rows), spec.net_pnl, abs_tol=0.005
    )
    net_r = math.fsum(row.pnl_r for row in rows)
    assert math.isclose(net_r, spec.net_r, abs_tol=0.002), (spec, net_r)
    pd_rows = [row for row in rows if row.reason == "PROFIT_DRAWDOWN"]
    assert math.isclose(
        math.fsum(row.pnl_r for row in pd_rows), spec.pd_r, abs_tol=0.002
    )
    print(
        f"baseline_{spec.symbol}_{spec.year}=MATCH|trades:{len(rows)},"
        f"W:{counts[0]},L:{counts[1]},BE:{counts[2]},"
        f"net_r:{net_r:+.3f},PF:{summary.profit_factor:.4f}"
    )
    for reason in REASONS:
        subset = [row for row in rows if row.reason == reason]
        positive = sum(_classify(row.pnl) == "W" for row in subset)
        negative = sum(_classify(row.pnl) == "L" for row in subset)
        total_r = math.fsum(row.pnl_r for row in subset)
        avg_r = total_r / len(subset) if subset else 0.0
        print(
            f"exit={spec.symbol}_{spec.year}|reason:{reason},"
            f"n:{len(subset)},W:{positive},L:{negative},"
            f"net_r:{total_r:+.3f},avg_r:{avg_r:+.4f}"
        )
    pd_net = math.fsum(row.pnl_r for row in pd_rows)
    coverage = pd_net / spec.sl if spec.sl else math.inf
    print(
        f"comparison={spec.symbol}_{spec.year}|SL_rate:{spec.sl / len(rows):.4f},"
        f"PD_avg_R:{pd_net / spec.pd:+.4f},"
        f"PD_to_SL_coverage:{coverage:.4f},TP_count:{spec.tp}"
    )
    buys = [row for row in rows if row.direction == "BUY"]
    sells = [row for row in rows if row.direction == "SELL"]
    assert len(buys) + len(sells) == len(rows)
    for direction, subset in (("BUY", buys), ("SELL", sells)):
        print(
            f"direction={spec.symbol}_{spec.year}|{direction}|"
            f"trades:{len(subset)},SL:"
            f"{sum(row.reason == 'STOP_LOSS' for row in subset)},"
            f"net_r:{math.fsum(row.pnl_r for row in subset):+.3f}"
        )
    assert math.isclose(
        math.fsum(row.pnl_r for row in buys)
        + math.fsum(row.pnl_r for row in sells), net_r, abs_tol=1e-9
    )


def _run(spec: Spec, path: Path) -> int:
    """Виконати один production-equivalent Replay із нулем запитів."""
    from core.workspace_algorithm import create_registered_workspace_algorithm
    from core.workspace_alligator import WorkspaceMacdAlligatorReplayAlgorithm
    from core.workspace_profit_guard import (
        WorkspaceCandidateFNegativePdRecoveryGuard,
    )
    from core.workspace_runtime import WorkspaceRuntime
    from tests.runtime_workspace import (
        run_algorithm_workspace_replay_virtual_execution_check as virtual,
    )

    probe = virtual.BrokerRequestProbe()
    runtime = WorkspaceRuntime(
        _workspace(spec, path),
        algorithm_factory=create_registered_workspace_algorithm,
        broker_market_provider=probe,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    assert session.source_event_count == spec.rows
    assert session.history_report is not None
    assert session.history_report.accepted_rows == spec.rows
    while not session.completed:
        runtime.advance_replay()
    execution = runtime.replay_execution
    summary = runtime.historical_summary
    assert execution is not None and summary is not None
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
    _metrics(spec, summary, _extract_trades(runtime, spec.symbol))
    assert probe.requests == 0
    assert not any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    print(f"run={spec.symbol}_{spec.year}|broker_requests:{probe.requests}")
    return probe.requests


def _synthetic() -> None:
    """Контроль незалежності сум R та розкладання PD/SL/TP."""
    sample = (
        TradeRow("BUY", "PROFIT_DRAWDOWN", 0.5, 0.2, "BAR_RANGE", 8.0, 12.0),
        TradeRow("BUY", "STOP_LOSS", -1.2, -1.0, "BAR_RANGE", 8.0, 12.0),
        TradeRow("SELL", "TAKE_PROFIT", 2.4, 2.0, "SPREAD_FLOOR", 4.0, 12.0),
    )
    pd = math.fsum(row.pnl_r for row in sample if row.reason == "PROFIT_DRAWDOWN")
    sl = math.fsum(row.pnl_r for row in sample if row.reason == "STOP_LOSS")
    tp = math.fsum(row.pnl_r for row in sample if row.reason == "TAKE_PROFIT")
    assert math.isclose(pd + sl + tp, 1.2)
    assert math.isclose(pd, 0.2) and math.isclose(sl, -1.0)
    assert math.isclose(tp, 2.0)
    print("SYNTHETIC_EXIT_CONTRIBUTION=OK")


def main() -> None:
    """Зіставити 6 Replay без IB/cTrader API викликів."""
    _bootstrap()
    print("T112_28_CROSS_SYMBOL_EXIT_CONTRIBUTION_ANATOMY")
    print(f"test_id={TEST_ID}|mode={MODE}")
    print("periods=2024,2025|symbols=EURUSD,GBPUSD,USDJPY")
    print("source=CTRADER_M1|strategy=M15|completed_bars_only=True")
    print("metric_units=net_r:INITIAL_SL_RISK|raw_pnl:NOT_CROSS_SYMBOL")
    print("historical_broker_download=NOT_REQUESTED")
    _synthetic()
    before = _production_hashes()
    paths = {path for spec in SPECS for path in _sources(spec)}
    paths.update(_legacy_2025(spec) for spec in SPECS if spec.year == 2025)
    assert all(path.is_file() for path in paths)
    snapshots = {str(path): _sha256(path) for path in sorted(paths)}
    total_requests = 0
    with tempfile.TemporaryDirectory(prefix="t112_28_") as directory:
        for spec in SPECS:
            target = Path(directory) / (
                f"{spec.year}_CTRADER_{spec.symbol}_M1.csv"
            )
            _assemble(spec, target)
            total_requests += _run(spec, target)
            target.unlink()
    assert total_requests == 0
    assert snapshots == {str(path): _sha256(path) for path in sorted(paths)}
    assert before == _production_hashes()
    print("cross_symbol_raw_pnl_comparison=FORBIDDEN")
    print("IB_history_comparison=SEPARATE_FUTURE_DATA_ONLY_TEST")
    print("exit_counterfactual=NOT_TESTED")
    print("parameter_optimization=NONE")
    print("replay_determinism=NOT_RERUN_ONE_REPLAY_PER_SYMBOL_YEAR")
    print("source_history_modified=False")
    print("temporary_csv_removed=True")
    print("production_logic_changed=False")
    print("exit_logic_changed=False")
    print("md7_changed=False")
    print("broker_requests=0")
    print("T112_28_CROSS_SYMBOL_EXIT_CONTRIBUTION_ANATOMY=OK")


if __name__ == "__main__":
    main()
