# -*- coding: utf-8 -*-
"""T112-25 — незалежний USDJPY Replay 2025 із BUY/SELL-діагностикою.

TEST_ONLY / DATA_ONLY. Candidate F без підбору параметрів.
Цінові пороги переведено в pip USDJPY.
Новий USDJPY CSV перевіряється рядок у рядок зі старим джерелом.
"""

from __future__ import annotations

import csv
import hashlib
import math
import sys
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import zip_longest
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.workspace_runtime import WorkspaceRuntime

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HISTORY_DIR = PROJECT_ROOT / "data" / "history" / "CTRADER" / "USDJPY" / "M1"
NEW_SOURCE = "2024-10-22_2026-10-21_CTRADER_USDJPY_M1.csv"
LEGACY_SOURCE = "2025-01-01_2025-12-31_CTRADER_USDJPY_M1.csv"
CSV_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
FIRST_BAR = "2025-01-01T22:01:00Z"
LAST_BAR = "2025-12-31T21:58:00Z"
EXPECTED_ROWS = 369962
REASONS = ("PROFIT_DRAWDOWN", "STOP_LOSS", "TAKE_PROFIT", "SESSION_END")
TEST_ID = "T112-25"
MODE = "RM112_T112_25_USDJPY_2025_DIRECTIONAL_TEST_ONLY"


@dataclass(frozen=True)
class TradeRow:
    direction: str
    close_reason: str
    pnl: float
    pnl_r: float
    sl_basis: str
    signal_range_pips: float = 0.0
    sl_distance_pips: float = 0.0
    spread_pips: float = 0.0


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


def _year_rows(reader: Iterable[list[str]]):
    """Вибрати лише 2025 рік, не доповнюючи прогалини в M1."""
    for row in reader:
        assert len(row) == len(CSV_COLUMNS), row
        if "2025-01-01T00:00:00Z" <= row[0] <= "2025-12-31T23:59:00Z":
            yield row


def _assemble_and_compare(target: Path) -> int:
    """Створити тимчасовий рік з нового CSV і звірити зі старим."""
    new_path = HISTORY_DIR / NEW_SOURCE
    old_path = HISTORY_DIR / LEGACY_SOURCE
    assert new_path.is_file() and old_path.is_file()
    first: str | None = None
    last: str | None = None
    first_close: str | None = None
    last_close: str | None = None
    count = 0
    with (
        new_path.open("r", encoding="utf-8-sig", newline="") as new_file,
        old_path.open("r", encoding="utf-8-sig", newline="") as old_file,
        target.open("w", encoding="utf-8", newline="") as output,
    ):
        newer = csv.reader(new_file)
        legacy = csv.reader(old_file)
        assert tuple(next(newer)) == CSV_COLUMNS
        assert tuple(next(legacy)) == CSV_COLUMNS
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(CSV_COLUMNS)
        for fresh, previous in zip_longest(_year_rows(newer), _year_rows(legacy)):
            if fresh != previous:
                raise AssertionError(f"USDJPY M1 2025 mismatch at row {count + 1}")
            assert fresh is not None
            stamp = fresh[0]
            if last is not None and stamp <= last:
                raise AssertionError(f"Non-increasing M1: {last} -> {stamp}")
            if first is None:
                first = stamp
                first_close = fresh[4]
            last = stamp
            last_close = fresh[4]
            writer.writerow(fresh)
            count += 1
    assert count == EXPECTED_ROWS, count
    assert first == FIRST_BAR, first
    assert last == LAST_BAR, last
    assert float(first_close or "0") > 100.0
    assert float(last_close or "0") > 100.0
    print("source_quote_scale=JPY|raw_prices_gt_100=True")
    print(f"usdjpy_m1_2025=EXACT_ROW_MATCH|rows={count}")
    print(f"m1_range={first}..{last}")
    print(f"legacy_source={LEGACY_SOURCE}")
    print(f"new_source={NEW_SOURCE}")
    return count


def _workspace(year_path: Path):
    """Зберегти frozen Candidate F у pip-одиницях для USDJPY."""
    from engine.runtime_constants import (
        DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT,
        FOREX_STANDARD_PIP_SIZE,
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
    params = dict(workspace.parameters)
    settings = dict(workspace.replay_settings)
    assert params["spread_limit"] == 0.00020
    assert params["macd_extremum_min_prominence"] == 0.000015
    assert params["macd_extremum_to_cross_min_distance"] == 0.000050
    assert settings["spread"] == 0.00012

    pip = resolve_forex_pip_size("USDJPY")
    base_pip = resolve_forex_pip_size("EURUSD")
    assert base_pip == FOREX_STANDARD_PIP_SIZE == 0.0001
    assert pip == 0.01
    scale = pip / base_pip
    assert scale == 100.0

    params["spread_limit"] *= scale
    params["macd_extremum_min_prominence"] = (
        resolve_new_workspace_macd_extremum_min_prominence("USDJPY")
    )
    params["macd_extremum_to_cross_min_distance"] = (
        resolve_new_workspace_macd_extremum_to_cross_min_distance("USDJPY")
    )
    settings["spread"] = resolve_workspace_history_default_spread("USDJPY")
    assert math.isclose(params["spread_limit"], 0.020, abs_tol=1e-12)
    assert math.isclose(params["macd_extremum_min_prominence"], 0.0015, abs_tol=1e-12)
    assert math.isclose(
        params["macd_extremum_to_cross_min_distance"], 0.005, abs_tol=1e-12
    )
    assert math.isclose(settings["spread"], 0.012, abs_tol=1e-12)
    assert math.isclose(params["spread_limit"] / pip, 2.0, abs_tol=1e-12)
    assert math.isclose(settings["spread"] / pip, 1.2, abs_tol=1e-12)
    assert params["macd_cross_min_abc_angle"] == 2.25

    workspace.symbol = "USDJPY"
    workspace.broker = "CTRADER"
    workspace.parameters = params
    protection = dict(workspace.profit_protection)
    protection["max_profit_drawdown_percent"] = (
        DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT
    )
    workspace.profit_protection = protection
    settings.update(
        {
            "file_path": str(year_path),
            "start_utc": "2025-01-01T00:00:00+00:00",
            "end_utc": "2025-12-31T23:59:00+00:00",
            "source": year_path.stem,
            "source_timeframe": "M1",
        }
    )
    workspace.replay_settings = settings
    print("pip_contract=USDJPY:0.01|EURUSD:0.0001|raw_scale:100")
    print(
        "scaled_parameters="
        "spread_limit:0.020,spread:0.012,"
        "macd_prominence:0.0015,macd_distance:0.005"
    )
    print("unit_conversion_only=True|threshold_retuning=False")
    return workspace


def _extract_trades(runtime: WorkspaceRuntime) -> list[TradeRow]:
    """Пов'язати угоди з завершеним M15; геометрія в pip USDJPY."""
    from engine.runtime_constants import resolve_forex_pip_size

    pip_size = resolve_forex_pip_size("USDJPY")
    assert pip_size == 0.01
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
                signal_range_pips=range_distance / pip_size,
                sl_distance_pips=distance / pip_size,
                spread_pips=event.spread / pip_size,
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
    if rows:
        from statistics import median

        print(
            f"{label}|pip_geometry="
            f"median_signal_range:{median(r.signal_range_pips for r in rows):.3f},"
            f"median_sl:{median(r.sl_distance_pips for r in rows):.3f},"
            f"median_spread:{median(r.spread_pips for r in rows):.3f}"
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
    """Один USDJPY Replay без брокерських звернень."""
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
    assert summary.period_start.year == 2025
    assert summary.period_end.year == 2025
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
    _report("usdjpy_2025", rows)
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
    _report("usdjpy_2025|direction=BUY", buys)
    _report("usdjpy_2025|direction=SELL", sells)
    rejects = sum(
        record.filter_reason_code == ALLIGATOR_REASON_STOCHASTIC_CURRENT_BAR_CROSS
        for record in runtime.signal_records_for_ui()
    )
    print(f"stochastic_current_bar_rejects={rejects}")
    pf_text = "NA" if summary.profit_factor is None else f"{summary.profit_factor:.4f}"
    print(
        "production_2025_USDJPY="
        f"trades:{summary.opened_trades},W:{summary.winning_trades},"
        f"L:{summary.losing_trades},BE:{summary.break_even_trades},"
        f"net_pnl:{summary.net_profit:+.2f},"
        f"PF:{pf_text},"
        f"DD:{summary.maximum_drawdown:.2f}"
    )
    print(
        "exit_2025_USDJPY="
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
    """Перевірити USDJPY 2025 зі збереженням pip-порогів."""
    _bootstrap()
    print("T112_25_INDEPENDENT_USDJPY_2025_DIRECTIONAL_REPLAY")
    print(f"test_id={TEST_ID}|mode={MODE}")
    print("symbol=USDJPY|broker=CTRADER|source=M1|strategy=M15")
    print("period=2025|completed_bars_only=True|one_replay_only=True")
    print("parameters=EURUSD_FROZEN_PIP_EQUIVALENT_NO_RETUNE")
    print("metric_units=net_pnl:RAW_QUOTE_JPY_MODEL,net_r:INITIAL_SL_RISK")
    print("cross_symbol_comparison=PF_AND_NORMALIZED_R_NOT_RAW_PNL")
    _synthetic_contract()
    production_before = _production_hashes()
    sources = [HISTORY_DIR / name for name in (LEGACY_SOURCE, NEW_SOURCE)]
    source_before = {str(path): _hash_file(path) for path in sources}
    with tempfile.TemporaryDirectory(prefix="t112_25_") as temporary:
        path = Path(temporary) / "2025_CTRADER_USDJPY_M1.csv"
        count = _assemble_and_compare(path)
        requests = _run_replay(path, count)
        assert requests == 0
    assert source_before == {str(path): _hash_file(path) for path in sources}
    assert production_before == _production_hashes()
    print("reference_usdjpy_metrics=NOT_PREDECLARED_INDEPENDENT_SYMBOL")
    print("reference_eurusd_2025=trades:42,PF:1.5424")
    print("reference_gbpusd_2025=trades:71,PF:0.5728")
    print("cross_symbol_raw_pnl_comparison=INVALID_DIFFERENT_QUOTE_UNITS")
    print("directional_filter_counterfactual=NOT_TESTED")
    print("cross_symbol_parameter_optimization=NONE")
    print("replay_determinism=NOT_RERUN_ONE_REPLAY_ONLY")
    print("source_history_modified=False")
    print("temporary_csv_removed=True")
    print("production_logic_changed=False")
    print("exit_logic_changed=False")
    print("md7_changed=False")
    print("broker_requests=0")
    print("T112_25_INDEPENDENT_USDJPY_2025_DIRECTIONAL_REPLAY=OK")


if __name__ == "__main__":
    main()
