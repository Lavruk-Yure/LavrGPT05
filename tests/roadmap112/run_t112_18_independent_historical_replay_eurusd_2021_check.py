# -*- coding: utf-8 -*-
"""T112-18 — незалежний production-equivalent Replay EURUSD 2021.

TEST_ONLY: один Replay без добору параметрів і без очікуваного PnL.
Вихідний CSV читається без змін. Для Replay створюється лише
тимчасовий CSV з календарним 2021 роком, який автоматично видаляється.
"""

from __future__ import annotations

import csv
import hashlib
import math
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.workspace_runtime import WorkspaceRuntime

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HISTORY_DIR = PROJECT_ROOT / "data" / "history" / "CTRADER" / "EURUSD" / "M1"
SOURCE_NAME = "2020-10-22_2022-10-21_CTRADER_EURUSD_M1.csv"
START_UTC = "2021-01-01T00:00:00+00:00"
END_UTC = "2021-12-31T23:59:00+00:00"
YEAR_START = "2021-01-01T00:00:00Z"
YEAR_END = "2021-12-31T23:59:00Z"
EXPECTED_TOTAL_ROWS = 369088
EXPECTED_FIRST = "2021-01-03T22:01:00Z"
EXPECTED_LAST = "2021-12-31T18:59:00Z"
CSV_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
GEOMETRY_TOLERANCE = 1e-12
TEST_ID = "T112-18"
MODE = "RM112_T112_18_INDEPENDENT_EURUSD_2021_TEST_ONLY"


def _bootstrap() -> None:
    """Додати корінь проєкту для імпортів runtime лише під час запуску."""
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _hash_file(path: Path) -> str:
    """Обчислити контрольний відбиток без модифікації файла."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _production_hashes() -> dict[str, str]:
    """Контролювати незмінність production Python і канонічного MD7."""
    paths = sorted(
        path
        for folder in ("core", "engine")
        for path in (PROJECT_ROOT / folder).rglob("*.py")
    )
    paths.append(PROJECT_ROOT / "doc" / "LGE_Runtime_07.md")
    assert all(path.is_file() for path in paths)
    return {str(path.relative_to(PROJECT_ROOT)): _hash_file(path) for path in paths}


def _assemble_year(target: Path) -> int:
    """Виділити календарний 2021 рік, не змінюючи вихідний CSV."""
    source = HISTORY_DIR / SOURCE_NAME
    assert source.is_file(), source
    total = 0
    first: str | None = None
    previous: str | None = None
    with source.open("r", encoding="utf-8-sig", newline="") as input_file:
        with target.open("w", encoding="utf-8", newline="") as output:
            reader = csv.reader(input_file)
            writer = csv.writer(output, lineterminator="\n")
            assert tuple(next(reader)) == CSV_COLUMNS
            writer.writerow(CSV_COLUMNS)
            for row in reader:
                if len(row) != len(CSV_COLUMNS):
                    raise AssertionError(f"Invalid CSV row: {SOURCE_NAME}")
                timestamp = row[0]
                if not YEAR_START <= timestamp <= YEAR_END:
                    continue
                if previous is not None and timestamp <= previous:
                    raise AssertionError(
                        f"Non-increasing M1 timestamp: {previous} -> "
                        f"{timestamp}"
                    )
                if first is None:
                    first = timestamp
                previous = timestamp
                writer.writerow(row)
                total += 1
    assert total == EXPECTED_TOTAL_ROWS, total
    assert first == EXPECTED_FIRST, (first, EXPECTED_FIRST)
    assert previous == EXPECTED_LAST, (previous, EXPECTED_LAST)
    print(f"source={SOURCE_NAME}|year_rows={total}")
    print(f"temporary_2021_rows={total}|first={first}|last={previous}")
    return total


def _workspace(year_path: Path):
    """Використати незмінені налаштування production Candidate F."""
    from engine.runtime_constants import (
        DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT,
    )
    from tests.runtime_workspace import (
        run_algorithm_workspace_candidate_f_frozen_oos_2025_check as frozen,
    )

    workspace = frozen.frozen_oos_workspace()
    workspace.broker = "CTRADER"
    protection = dict(workspace.profit_protection)
    pd_threshold = DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT
    protection["max_profit_drawdown_percent"] = pd_threshold
    workspace.profit_protection = protection
    settings = dict(workspace.replay_settings)
    settings.update(
        {
            "file_path": str(year_path),
            "start_utc": START_UTC,
            "end_utc": END_UTC,
            "source": year_path.stem,
            "source_timeframe": "M1",
        }
    )
    workspace.replay_settings = settings
    assert workspace.parameters["macd_extremum_min_prominence"] == 0.000015
    assert workspace.parameters["macd_extremum_to_cross_min_distance"] == 0.000050
    assert workspace.parameters["macd_cross_min_abc_angle"] == 2.25
    return workspace


def _assert_execution(runtime: WorkspaceRuntime) -> int:
    """Перевірити клас алгоритму, SL/TP/PD і causal signal geometry."""
    from core.workspace_alligator import (
        ALLIGATOR_REASON_STOCHASTIC_CURRENT_BAR_CROSS,
        WorkspaceMacdAlligatorReplayAlgorithm,
    )
    from core.workspace_profit_guard import (
        WorkspaceCandidateFNegativePdRecoveryGuard,
    )

    session = runtime.replay_session
    execution = runtime.replay_execution
    assert session is not None and session.completed
    assert execution is not None
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

    source_events = {event.timestamp: event for event in session.events}
    records = runtime.signal_records_for_ui()
    accepted = {record.signal_uid: record for record in records if record.accepted}
    trades = execution.trade_diagnostics()
    summary = runtime.historical_summary
    assert summary is not None
    assert len(trades) == summary.opened_trades
    for trade in trades:
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
    assert all(
        record.filter_context is None
        or record.filter_context.available_at is None
        or record.filter_context.available_at <= record.timestamp
        for record in records
    )
    stochastic_rejects = sum(
        record.filter_reason_code == ALLIGATOR_REASON_STOCHASTIC_CURRENT_BAR_CROSS
        for record in records
    )
    print(f"stochastic_current_bar_rejects={stochastic_rejects}")
    print("entry_exit_geometry=PRODUCTION_POLICY_VERIFIED")
    return stochastic_rejects


def _run_replay(year_path: Path, rows: int) -> int:
    """Виконати один незалежний Replay 2021 з поточними production rules."""
    from core.workspace_algorithm import create_registered_workspace_algorithm
    from core.workspace_runtime import WorkspaceRuntime
    from tests.runtime_workspace import (
        run_algorithm_workspace_replay_virtual_execution_check as virtual,
    )

    probe = virtual.BrokerRequestProbe()
    runtime = WorkspaceRuntime(
        _workspace(year_path),
        algorithm_factory=create_registered_workspace_algorithm,
        broker_market_provider=probe,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    assert session.source_event_count == rows
    assert session.history_report is not None
    assert session.history_report.accepted_rows == rows
    while not session.completed:
        runtime.advance_replay()
    summary = runtime.historical_summary
    assert summary is not None
    assert summary.period_start.year == 2021
    assert summary.period_end.year == 2021
    assert summary.opened_trades == (
        summary.winning_trades
        + summary.losing_trades
        + summary.break_even_trades
    )
    assert math.isfinite(summary.net_profit)
    assert math.isfinite(summary.maximum_drawdown)
    _assert_execution(runtime)
    pf = "NONE" if summary.profit_factor is None else f"{summary.profit_factor:.4f}"
    print(
        "production_2021="
        f"trades:{summary.opened_trades},"
        f"W:{summary.winning_trades},"
        f"L:{summary.losing_trades},"
        f"BE:{summary.break_even_trades},"
        f"net:{summary.net_profit:+.2f},"
        f"PF:{pf},DD:{summary.maximum_drawdown:.2f}"
    )
    print(
        "exit_2021="
        f"PD:{summary.close_reason_count('PROFIT_DRAWDOWN')},"
        f"SL:{summary.close_reason_count('STOP_LOSS')},"
        f"TP:{summary.close_reason_count('TAKE_PROFIT')},"
        f"SESSION:{summary.close_reason_count('SESSION_END')}"
    )
    print(
        "observed_period="
        f"{summary.period_start.isoformat()}..{summary.period_end.isoformat()}"
    )
    assert probe.requests == 0, probe.requests
    assert not any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    print(f"broker_requests={probe.requests}")
    return probe.requests


def main() -> None:
    """Виконати незалежний Replay 2021, перевірити незмінність джерела."""
    _bootstrap()
    print("T112_18_INDEPENDENT_HISTORICAL_REPLAY_EURUSD_2021")
    print(f"test_id={TEST_ID}|mode={MODE}")
    print("period=2021|symbol=EURUSD|broker=CTRADER|source=M1|strategy=M15")
    print("one_replay_only=True|completed_bars_only=True")
    production_before = _production_hashes()
    source_path = HISTORY_DIR / SOURCE_NAME
    source_before = _hash_file(source_path)
    with tempfile.TemporaryDirectory(prefix="t112_18_") as temp_dir:
        year_path = Path(temp_dir) / "2021-01-01_2021-12-31_CTRADER_EURUSD_M1.csv"
        rows = _assemble_year(year_path)
        requests = _run_replay(year_path, rows)
        assert requests == 0
    assert source_before == _hash_file(source_path)
    assert production_before == _production_hashes()
    print("reference_trade_metrics=NOT_PREDECLARED_INDEPENDENT_PERIOD")
    print("replay_determinism=NOT_RERUN_ONE_REPLAY_ONLY")
    print("source_history_modified=False")
    print("temporary_csv_removed=True")
    print("production_logic_changed=False")
    print("exit_logic_changed=False")
    print("md7_changed=False")
    print("broker_requests=0")
    print("T112_18_INDEPENDENT_HISTORICAL_REPLAY_EURUSD_2021=OK")


if __name__ == "__main__":
    main()
