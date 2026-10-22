# -*- coding: utf-8 -*-
"""T112-13 — контроль production Replay EURUSD 2025 із нової історії.

TEST_ONLY: один фактичний Replay, без змін Candidate F, exit або CSV.
Перед запуском перевіряється повна рівність M1-рядків старого і нового джерел
на часовому діапазоні канонічного baseline T105-18.
"""

from __future__ import annotations

import csv
import hashlib
import math
import sys
from collections.abc import Iterable, Iterator
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.workspace_runtime import WorkspaceRuntime

PROJECT_ROOT = Path(__file__).resolve().parents[2]

TEST_ID = "T112-13"
MODE = "RM112_T112_13_NEW_CSV_PRODUCTION_REPLAY_TEST_ONLY"
HISTORY_DIR = PROJECT_ROOT / "data" / "history" / "CTRADER" / "EURUSD" / "M1"
NEW_NAME = "2024-10-22_2026-10-21_CTRADER_EURUSD_M1.csv"
CSV_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
EXPECTED_SOURCE_ROWS = 370481
EXPECTED_M15_REJECTS = 17
NET_TOLERANCE = 0.005
METRIC_TOLERANCE = 0.00005
GEOMETRY_TOLERANCE = 1e-12


def _bootstrap() -> None:
    """Додати корінь проєкту лише перед імпортом runtime-модулів."""
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _spec():
    """Повернути діапазон і налаштування канонічного T105-10."""
    from tests.runtime_workspace import (
        run_t105_10_pd_35_production_regression_check as pd_regression,
    )

    result = next(item for item in pd_regression.PERIODS if item.code == "2025")
    assert result.start_utc == "2025-01-01T22:01:00+00:00"
    assert result.end_utc == "2025-12-31T21:58:00+00:00"
    return result


def _source_hash(path: Path) -> str:
    """Вирахувати SHA-256 файла потоково, не змінюючи його."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _production_hashes() -> dict[str, str]:
    """Зафіксувати production Python і MD7 перед тестом."""
    paths = sorted(
        path
        for folder in ("core", "engine")
        for path in (PROJECT_ROOT / folder).rglob("*.py")
    )
    paths.append(PROJECT_ROOT / "doc" / "LGE_Runtime_07.md")
    assert all(path.is_file() for path in paths)
    return {str(path.relative_to(PROJECT_ROOT)): _source_hash(path) for path in paths}


def _range_rows(
    reader: Iterable[list[str]],
    start: str,
    end: str,
) -> Iterator[list[str]]:
    """Вибрати UTC-рядки за включними часовими межами baseline."""
    for row in reader:
        if len(row) != len(CSV_COLUMNS):
            raise AssertionError(f"Unexpected CSV column count: {row!r}")
        if start <= row[0] <= end:
            yield row


def _verify_source_identity(spec) -> tuple[Path, Path, int]:
    """Порівняти кожен еталонний M1-бар із новим дворічним CSV."""
    legacy_path = HISTORY_DIR / spec.file_name
    new_path = HISTORY_DIR / NEW_NAME
    assert legacy_path.is_file(), legacy_path
    assert new_path.is_file(), new_path

    start = datetime.fromisoformat(spec.start_utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = datetime.fromisoformat(spec.end_utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    count = 0
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    with legacy_path.open("r", encoding="utf-8-sig", newline="") as old_stream:
        with new_path.open("r", encoding="utf-8-sig", newline="") as new_stream:
            old_reader = csv.reader(old_stream)
            new_reader = csv.reader(new_stream)
            assert tuple(next(old_reader)) == CSV_COLUMNS
            assert tuple(next(new_reader)) == CSV_COLUMNS
            selected = iter(_range_rows(new_reader, start, end))
            for old_row in old_reader:
                new_row = next(selected, None)
                count += 1
                if new_row != old_row:
                    raise AssertionError(
                        f"M1 mismatch at row {count}: old={old_row!r}, "
                        f"new={new_row!r}"
                    )
                if first_timestamp is None:
                    first_timestamp = old_row[0]
                last_timestamp = old_row[0]
            assert next(selected, None) is None, "New source has extra range rows"

    assert count == EXPECTED_SOURCE_ROWS, count
    assert first_timestamp == start, (first_timestamp, start)
    assert last_timestamp == end, (last_timestamp, end)
    print(f"m1_comparison=EXACT_ROW_MATCH|rows={count}")
    print(f"m1_range={first_timestamp}..{last_timestamp}")
    print(f"legacy_source={legacy_path.name}")
    print(f"new_source={new_path.name}")
    return legacy_path, new_path, count


def _workspace(spec, new_path: Path):
    """Створити canonical Candidate F з новим файлом, без зміни параметрів."""
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
            "file_path": str(new_path),
            "start_utc": spec.start_utc,
            "end_utc": spec.end_utc,
            "source": Path(spec.file_name).stem,
            "source_timeframe": "M1",
        }
    )
    workspace.replay_settings = settings
    assert Path(workspace.replay_settings["file_path"]) == new_path
    assert workspace.replay_settings["source"] == Path(spec.file_name).stem
    return workspace


def _assert_summary(runtime: WorkspaceRuntime) -> None:
    """Порівняти реальні метрики, не округлюючи їх перед перевіркою."""
    from tests.runtime_workspace import (
        run_t105_18_stochastic_current_bar_production_regression_check as baseline,
    )

    expected = baseline.EXPECTATIONS["2025"]
    summary = runtime.historical_summary
    assert summary is not None
    counts = (
        summary.opened_trades,
        summary.winning_trades,
        summary.losing_trades,
        summary.break_even_trades,
    )
    expected_counts = (
        expected.trades,
        expected.wins,
        expected.losses,
        expected.break_even,
    )
    assert counts == expected_counts, (counts, expected_counts)
    for name, actual, reference, tolerance in (
        ("net_R", summary.net_profit, expected.net, NET_TOLERANCE),
        ("PF", summary.profit_factor, expected.profit_factor, METRIC_TOLERANCE),
        ("max_DD", summary.maximum_drawdown, expected.drawdown, NET_TOLERANCE),
    ):
        if not math.isclose(actual, reference, rel_tol=0.0, abs_tol=tolerance):
            raise AssertionError(f"{name}: actual={actual}, expected={reference}")
    for reason, expected_count in (
        ("PROFIT_DRAWDOWN", expected.profit_drawdown),
        ("STOP_LOSS", expected.stop_loss),
        ("TAKE_PROFIT", expected.take_profit),
        ("SESSION_END", 0),
    ):
        actual_count = summary.close_reason_count(reason)
        assert actual_count == expected_count, (reason, actual_count, expected_count)
    print(
        "production_2025="
        f"trades:{counts[0]},W:{counts[1]},L:{counts[2]},BE:{counts[3]},"
        f"net:{summary.net_profit:+.2f},PF:{summary.profit_factor:.4f},"
        f"DD:{summary.maximum_drawdown:.2f}"
    )
    print(
        "exit_2025="
        f"PD:{summary.close_reason_count('PROFIT_DRAWDOWN')},"
        f"SL:{summary.close_reason_count('STOP_LOSS')},"
        f"TP:{summary.close_reason_count('TAKE_PROFIT')},"
        f"SESSION:{summary.close_reason_count('SESSION_END')}"
    )


def _assert_execution(runtime: WorkspaceRuntime) -> None:
    """Перевірити production geometry й Stochastic без змін exit."""
    from core.workspace_alligator import (
        ALLIGATOR_REASON_STOCHASTIC_CURRENT_BAR_CROSS,
        WorkspaceMacdAlligatorReplayAlgorithm,
    )
    from core.workspace_profit_guard import (
        WorkspaceCandidateFNegativePdRecoveryGuard,
    )
    from tests.runtime_workspace import (
        run_t105_18_stochastic_current_bar_production_regression_check as baseline,
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
    accepted = {
        record.signal_uid: record
        for record in runtime.signal_records_for_ui()
        if record.accepted
    }
    trades = execution.trade_diagnostics()
    assert len(trades) == baseline.EXPECTATIONS["2025"].trades
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
    stochastic_rejects = sum(
        record.filter_reason_code == ALLIGATOR_REASON_STOCHASTIC_CURRENT_BAR_CROSS
        for record in runtime.signal_records_for_ui()
    )
    assert stochastic_rejects == EXPECTED_M15_REJECTS, stochastic_rejects
    print(f"stochastic_current_bar_rejects={stochastic_rejects}")
    print("entry_exit_geometry=PRODUCTION_BASELINE_MATCH")


def _run_one_replay(spec, new_path: Path, expected_rows: int) -> int:
    """Виконати лише EURUSD 2025 через чинний registered algorithm."""
    from core.workspace_algorithm import create_registered_workspace_algorithm
    from core.workspace_runtime import WorkspaceRuntime
    from tests.runtime_workspace import (
        run_algorithm_workspace_replay_virtual_execution_check as virtual,
    )

    probe = virtual.BrokerRequestProbe()
    runtime = WorkspaceRuntime(
        _workspace(spec, new_path),
        algorithm_factory=create_registered_workspace_algorithm,
        broker_market_provider=probe,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    assert session.source_event_count == expected_rows
    assert session.history_report is not None
    assert session.history_report.accepted_rows == expected_rows
    while not session.completed:
        runtime.advance_replay()
    _assert_summary(runtime)
    _assert_execution(runtime)
    assert probe.requests == 0, probe.requests
    assert not any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    print(f"broker_requests={probe.requests}")
    return probe.requests


def main() -> None:
    """Відтворити 2025 baseline на новому CSV без модифікацій файлів."""
    _bootstrap()
    print("T112_13_HISTORICAL_REPLAY_BASELINE_REPRODUCTION")
    print(f"test_id={TEST_ID}|mode={MODE}")
    print("period=2025|symbol=EURUSD|broker=CTRADER|source=M1|strategy=M15")
    print("one_replay_only=True|completed_bars_only=True")
    spec = _spec()
    production_before = _production_hashes()
    old_path, new_path, source_rows = _verify_source_identity(spec)
    history_before = (_source_hash(old_path), _source_hash(new_path))
    requests = _run_one_replay(spec, new_path, source_rows)
    assert requests == 0
    assert history_before == (_source_hash(old_path), _source_hash(new_path))
    assert production_before == _production_hashes()
    print("baseline_source=CANONICAL_T105_18")
    print("baseline_runtime_replayed=True")
    print("old_and_new_m1_rows_identical=True")
    print("historical_files_modified=False")
    print("production_logic_changed=False")
    print("exit_logic_changed=False")
    print("md7_changed=False")
    print("broker_requests=0")
    print("T112_13_HISTORICAL_REPLAY_BASELINE_REPRODUCTION=OK")


if __name__ == "__main__":
    main()
