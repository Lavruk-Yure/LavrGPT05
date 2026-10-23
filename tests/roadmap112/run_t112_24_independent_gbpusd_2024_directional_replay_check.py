# -*- coding: utf-8 -*-
"""T112-24 — незалежний GBPUSD Replay 2024 із BUY/SELL-діагностикою.

TEST_ONLY / DATA_ONLY. Фіксований Candidate F без підбору параметрів.
2024 рік збирається з двох CSV без змін вихідних даних.
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
HISTORY_DIR = PROJECT_ROOT / "data" / "history" / "CTRADER" / "GBPUSD" / "M1"
SOURCE_NAMES = (
    "2022-10-23_2024-10-21_CTRADER_GBPUSD_M1.csv",
    "2024-10-22_2026-10-21_CTRADER_GBPUSD_M1.csv",
)
CSV_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
YEAR_START = "2024-01-01T00:00:00Z"
YEAR_END = "2024-12-31T23:59:00Z"
FIRST_BAR = "2024-01-01T22:01:00Z"
LAST_BAR = "2024-12-31T21:58:00Z"
EXPECTED_PART_ROWS = (301086, 71573)
EXPECTED_PART_FIRST = (
    "2024-01-01T22:01:00Z",
    "2024-10-22T00:00:00Z",
)
EXPECTED_PART_LAST = (
    "2024-10-21T23:59:00Z",
    "2024-12-31T21:58:00Z",
)
EXPECTED_ROWS = 372659
REASONS = ("PROFIT_DRAWDOWN", "STOP_LOSS", "TAKE_PROFIT", "SESSION_END")
TEST_ID = "T112-24"
MODE = "RM112_T112_24_GBPUSD_2024_DIRECTIONAL_TEST_ONLY"


@dataclass(frozen=True)
class TradeRow:
    direction: str
    close_reason: str
    pnl: float
    pnl_r: float
    sl_basis: str


def _bootstrap() -> None:
    """Додати корінь репозиторію до локального Python path."""
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _hash_file(path: Path) -> str:
    """Контрольна сума без зміни файла."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _production_hashes() -> dict[str, str]:
    """Контролювати незмінність production-модулів і MD7."""
    paths = sorted(
        path
        for folder in ("core", "engine")
        for path in (PROJECT_ROOT / folder).rglob("*.py")
    )
    paths.append(PROJECT_ROOT / "doc" / "LGE_Runtime_07.md")
    assert paths and all(path.is_file() for path in paths)
    return {str(path.relative_to(PROJECT_ROOT)): _hash_file(path) for path in paths}


def _assemble_year(target: Path) -> int:
    """Зібрати 2024 рік із двох CSV без заповнення пропусків M1."""
    counts: list[int] = []
    part_first: list[str | None] = []
    part_last: list[str | None] = []
    count_total = 0
    first: str | None = None
    last: str | None = None
    with target.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(CSV_COLUMNS)
        for name in SOURCE_NAMES:
            path = HISTORY_DIR / name
            assert path.is_file(), path
            count = 0
            first_in_part: str | None = None
            last_in_part: str | None = None
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.reader(stream)
                assert tuple(next(reader)) == CSV_COLUMNS, path
                for row in reader:
                    if len(row) != len(CSV_COLUMNS):
                        raise AssertionError(f"Invalid CSV row: {path.name}")
                    timestamp = row[0]
                    if not YEAR_START <= timestamp <= YEAR_END:
                        continue
                    if last is not None and timestamp <= last:
                        raise AssertionError(
                            f"Non-increasing M1 timestamp: {last} -> " f"{timestamp}"
                        )
                    if first is None:
                        first = timestamp
                    if first_in_part is None:
                        first_in_part = timestamp
                    last = timestamp
                    last_in_part = timestamp
                    writer.writerow(row)
                    count += 1
                    count_total += 1
            counts.append(count)
            part_first.append(first_in_part)
            part_last.append(last_in_part)
            print(f"source={name}|year_rows={count}")
    assert tuple(counts) == EXPECTED_PART_ROWS, counts
    assert tuple(part_first) == EXPECTED_PART_FIRST, part_first
    assert tuple(part_last) == EXPECTED_PART_LAST, part_last
    assert count_total == EXPECTED_ROWS, count_total
    assert first == FIRST_BAR, first
    assert last == LAST_BAR, last
    print(f"temporary_2024_rows={count_total}|first={first}|last={last}")
    print("source_boundary=2024-10-21T23:59Z_TO_2024-10-22T00:00Z")
    return count_total


def _workspace(year_path: Path):
    """Ті самі Candidate F параметри, але інструмент GBPUSD."""
    from engine.runtime_constants import (
        DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT,
    )
    from tests.runtime_workspace import (
        run_algorithm_workspace_candidate_f_frozen_oos_2025_check as frozen,
    )

    workspace = frozen.frozen_oos_workspace()
    workspace.symbol = "GBPUSD"
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
            "start_utc": "2024-01-01T00:00:00+00:00",
            "end_utc": "2024-12-31T23:59:00+00:00",
            "source": year_path.stem,
            "source_timeframe": "M1",
        }
    )
    workspace.replay_settings = settings
    assert workspace.symbol == "GBPUSD"
    assert workspace.parameters["macd_extremum_min_prominence"] == 0.000015
    assert workspace.parameters["macd_extremum_to_cross_min_distance"] == 0.000050
    assert workspace.parameters["macd_cross_min_abc_angle"] == 2.25
    assert workspace.parameters["spread_limit"] == 0.00020
    assert workspace.replay_settings["spread"] == 0.00012
    return workspace


def _extract_trades(runtime: WorkspaceRuntime) -> list[TradeRow]:
    """Пов'язати угоди з уже завершеним сигнальним M15 баром."""
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
        signal = accepted[trade.signal_uid]
        assert signal.direction == trade.direction
        assert signal.timestamp == trade.signal_timestamp
        assert trade.signal_timestamp <= trade.entry_timestamp
        event = events[signal.timestamp]
        assert event.timeframe == "M15" and event.source_mode == "REPLAY"
        range_distance = event.high - event.low
        spread_floor = event.spread * 10.0
        distance = max(range_distance, spread_floor)
        assert distance > 0.0 and trade.volume > 0.0
        assert math.isclose(
            trade.stop_loss_distance, distance, rel_tol=0.0, abs_tol=1e-12
        )
        assert math.isclose(
            trade.take_profit_distance,
            distance * 2.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        assert trade.close_reason in REASONS
        assert trade.direction in ("BUY", "SELL")
        risk = distance * trade.volume
        rows.append(
            TradeRow(
                direction=trade.direction,
                close_reason=trade.close_reason,
                pnl=trade.final_profit,
                pnl_r=trade.final_profit / risk,
                sl_basis=(
                    "SPREAD_FLOOR" if spread_floor > range_distance else "BAR_RANGE"
                ),
            )
        )
    return rows


def _classify(pnl: float) -> str:
    """Зіставити W/L/BE за фактичним PnL, без округлення."""
    if pnl > 1e-12:
        return "W"
    if pnl < -1e-12:
        return "L"
    return "BE"


def _pf(rows: list[TradeRow]) -> str:
    """PF з грошового PnL, без підміни нормалізованим R."""
    profit = math.fsum(row.pnl for row in rows if _classify(row.pnl) == "W")
    loss = -math.fsum(row.pnl for row in rows if _classify(row.pnl) == "L")
    if loss <= 1e-12:
        return "INF" if profit > 1e-12 else "NA"
    return f"{profit / loss:.4f}"


def _report(label: str, rows: list[TradeRow]) -> None:
    """Вивести зіставні торгові метрики та розклад exit."""
    wins = sum(_classify(row.pnl) == "W" for row in rows)
    losses = sum(_classify(row.pnl) == "L" for row in rows)
    sl = sum(row.close_reason == "STOP_LOSS" for row in rows)
    rate = f"{sl / len(rows):.4f}" if rows else "NA"
    print(
        f"{label}|trades:{len(rows)},W:{wins},L:{losses},"
        f"BE:{len(rows) - wins - losses},SL:{sl},SL_rate:{rate},"
        f"net_pnl:{math.fsum(r.pnl for r in rows):+.4f},"
        f"net_r:{math.fsum(r.pnl_r for r in rows):+.3f},PF:{_pf(rows)}"
    )
    for reason in REASONS:
        subset = [row for row in rows if row.close_reason == reason]
        print(
            f"{label}|reason={reason}|trades:{len(subset)},"
            f"L:{sum(_classify(r.pnl) == 'L' for r in subset)},"
            f"net_pnl:{math.fsum(r.pnl for r in subset):+.4f},"
            f"net_r:{math.fsum(r.pnl_r for r in subset):+.3f}"
        )
    for basis in ("BAR_RANGE", "SPREAD_FLOOR"):
        subset = [row for row in rows if row.sl_basis == basis]
        count_sl = sum(row.close_reason == "STOP_LOSS" for row in subset)
        print(f"{label}|stop_basis={basis}|trades:{len(subset)},SL:{count_sl}")


def _synthetic_contract() -> None:
    """Перевірити незмінне розділення BUY/SELL і PF у моделі звіту."""
    rows = [
        TradeRow("BUY", "STOP_LOSS", -1.20, -1.0, "BAR_RANGE"),
        TradeRow("BUY", "PROFIT_DRAWDOWN", 0.30, 0.25, "BAR_RANGE"),
        TradeRow("SELL", "PROFIT_DRAWDOWN", 0.60, 0.50, "SPREAD_FLOOR"),
    ]
    buys = [row for row in rows if row.direction == "BUY"]
    sells = [row for row in rows if row.direction == "SELL"]
    assert len(buys) == 2 and len(sells) == 1
    assert len(buys) + len(sells) == len(rows)
    assert _pf(rows) == "0.7500"
    assert _pf(buys) == "0.2500"
    assert _pf(sells) == "INF"
    assert math.isclose(math.fsum(row.pnl_r for row in rows), -0.25)
    assert sum(row.close_reason == "STOP_LOSS" for row in rows) == 1
    print("SYNTHETIC_DIRECTIONAL_METRICS=OK")


def _run_replay(csv_path: Path, count: int) -> int:
    """Один GBPUSD Replay з нульовими брокерськими зверненнями."""
    from core.workspace_algorithm import create_registered_workspace_algorithm
    from core.workspace_alligator import (
        ALLIGATOR_REASON_STOCHASTIC_CURRENT_BAR_CROSS,
        WorkspaceMacdAlligatorReplayAlgorithm,
    )
    from core.workspace_profit_guard import (
        WorkspaceCandidateFNegativePdRecoveryGuard,
    )
    from core.workspace_runtime import WorkspaceRuntime
    from tests.runtime_workspace import (
        run_algorithm_workspace_replay_virtual_execution_check as virtual,
    )

    probe = virtual.BrokerRequestProbe()
    runtime = WorkspaceRuntime(
        _workspace(csv_path),
        algorithm_factory=create_registered_workspace_algorithm,
        broker_market_provider=probe,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    assert session.source_event_count == count
    assert session.history_report is not None
    assert session.history_report.accepted_rows == count
    while not session.completed:
        runtime.advance_replay()
    summary = runtime.historical_summary
    execution = runtime.replay_execution
    assert summary is not None and execution is not None
    assert summary.period_start.year == 2024
    assert summary.period_end.year == 2024
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
    assert math.isfinite(summary.net_profit)
    assert math.isfinite(summary.maximum_drawdown)
    rows = _extract_trades(runtime)
    assert len(rows) == summary.opened_trades
    assert len(rows) == (
        summary.winning_trades + summary.losing_trades + summary.break_even_trades
    )
    assert sum(_classify(row.pnl) == "W" for row in rows) == (summary.winning_trades)
    assert sum(_classify(row.pnl) == "L" for row in rows) == (summary.losing_trades)
    assert math.isclose(
        math.fsum(row.pnl for row in rows), summary.net_profit, abs_tol=0.005
    )
    for reason in REASONS:
        assert sum(row.close_reason == reason for row in rows) == (
            summary.close_reason_count(reason)
        )
    print("entry_exit_geometry=PRODUCTION_POLICY_VERIFIED")
    _report("gbpusd_2024", rows)
    buys = [row for row in rows if row.direction == "BUY"]
    sells = [row for row in rows if row.direction == "SELL"]
    assert len(buys) + len(sells) == len(rows)
    for attribute in ("pnl", "pnl_r"):
        assert math.isclose(
            math.fsum(getattr(row, attribute) for row in rows),
            math.fsum(getattr(row, attribute) for row in buys)
            + math.fsum(getattr(row, attribute) for row in sells),
            abs_tol=1e-9,
        )
    print(f"direction_partition=OK|BUY:{len(buys)},SELL:{len(sells)}")
    _report("gbpusd_2024|direction=BUY", buys)
    _report("gbpusd_2024|direction=SELL", sells)
    rejects = sum(
        record.filter_reason_code == ALLIGATOR_REASON_STOCHASTIC_CURRENT_BAR_CROSS
        for record in runtime.signal_records_for_ui()
    )
    print(f"stochastic_current_bar_rejects={rejects}")
    pf_text = "NA" if summary.profit_factor is None else f"{summary.profit_factor:.4f}"
    print(
        "production_2024_GBPUSD="
        f"trades:{summary.opened_trades},W:{summary.winning_trades},"
        f"L:{summary.losing_trades},BE:{summary.break_even_trades},"
        f"net_pnl:{summary.net_profit:+.2f},"
        f"PF:{pf_text},"
        f"DD:{summary.maximum_drawdown:.2f}"
    )
    print(
        "exit_2024_GBPUSD="
        f"PD:{summary.close_reason_count('PROFIT_DRAWDOWN')},"
        f"SL:{summary.close_reason_count('STOP_LOSS')},"
        f"TP:{summary.close_reason_count('TAKE_PROFIT')},"
        f"SESSION:{summary.close_reason_count('SESSION_END')}"
    )
    assert probe.requests == 0
    assert not any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    print(f"broker_requests={probe.requests}")
    return probe.requests


def main() -> None:
    """Перевірити GBPUSD 2024 без зміни Candidate F і його exit."""
    _bootstrap()
    print("T112_24_INDEPENDENT_GBPUSD_2024_DIRECTIONAL_REPLAY")
    print(f"test_id={TEST_ID}|mode={MODE}")
    print("symbol=GBPUSD|broker=CTRADER|source=M1|strategy=M15")
    print("period=2024|completed_bars_only=True|one_replay_only=True")
    print("parameters=EURUSD_FROZEN_CANDIDATE_F_TRANSFER_NO_RETUNE")
    print("metric_units=net_pnl:VIRTUAL_PNL,net_r:INITIAL_SL_RISK")
    _synthetic_contract()
    production_before = _production_hashes()
    sources = [HISTORY_DIR / name for name in SOURCE_NAMES]
    source_before = {str(path): _hash_file(path) for path in sources}
    with tempfile.TemporaryDirectory(prefix="t112_24_") as temporary:
        path = Path(temporary) / "2024_CTRADER_GBPUSD_M1.csv"
        count = _assemble_year(path)
        requests = _run_replay(path, count)
        assert requests == 0
    assert source_before == {str(path): _hash_file(path) for path in sources}
    assert production_before == _production_hashes()
    print("reference_gbpusd_2024_metrics=NOT_PREDECLARED")
    print("reference_gbpusd_2025=trades:71,net_pnl:-7.66,PF:0.5728,DD:9.38")
    print("reference_eurusd_2024=trades:18,net_pnl:+0.82,PF:1.3254,DD:1.71")
    print("directional_filter_counterfactual=NOT_TESTED")
    print("cross_symbol_parameter_optimization=NONE")
    print("replay_determinism=NOT_RERUN_ONE_REPLAY_ONLY")
    print("source_history_modified=False")
    print("temporary_csv_removed=True")
    print("production_logic_changed=False")
    print("exit_logic_changed=False")
    print("md7_changed=False")
    print("broker_requests=0")
    print("T112_24_INDEPENDENT_GBPUSD_2024_DIRECTIONAL_REPLAY=OK")


if __name__ == "__main__":
    main()
