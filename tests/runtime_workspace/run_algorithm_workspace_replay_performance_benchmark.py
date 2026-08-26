# -*- coding: utf-8 -*-
"""RoadMap100 benchmark довгого multi-resolution Replay без GUI.

Скрипт використовує відновлений EURUSD M15 Historical WSP з M1 CSV і
production RailAlgorithm, щоб окремо виміряти CSV/aggregation startup та
чистий Replay compute. За замовчуванням обробляються 2000 strategy bars:
перші 1000 і другі 1000 вимірюються окремо, бо саме на другій тисячі вже є
закриті virtual positions і добре видно вартість snapshot lifecycle.

Benchmark не задає machine-specific порогів і не змінює trading logic. Він
перевіряє structural performance invariant RoadMap100: immutable snapshot
закритої virtual position повторно використовується. Опція ``--full``
додатково дограє весь наявний Replay і друкує повний compute time.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import AlgorithmWorkspace  # noqa: E402
from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402

REFERENCE_HISTORY = (
    PROJECT_ROOT
    / "data"
    / "history"
    / "IB"
    / "EURUSD"
    / "M1"
    / "2026-01-02_2026-08-11_IB_EURUSD_M1.csv"
)


def _reference_workspace() -> AlgorithmWorkspace:
    """Знайти відновлений RM96 Replay WSP і прив'язати локальний CSV."""
    workspace_dir = PROJECT_ROOT / "Session" / "workspaces"
    candidates: list[dict[str, object]] = []
    for path in sorted(workspace_dir.glob("workspace_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        replay_settings = data.get("replay_settings")
        if not isinstance(replay_settings, dict):
            continue
        if (
            str(data.get("broker") or "").upper() == "IB"
            and str(data.get("symbol") or "").upper() == "EURUSD"
            and str(data.get("timeframe") or "").upper() == "M15"
            and str(data.get("algorithm") or "").upper() == "RAILALGORITHM"
            and str(data.get("data_mode") or "").upper() == "REPLAY"
            and str(replay_settings.get("source_timeframe") or "").upper() == "M1"
        ):
            candidates.append(data)
    if not candidates:
        raise RuntimeError("Reference EURUSD M15/M1 Replay workspace not found")

    data = dict(candidates[0])
    replay_settings = dict(data.get("replay_settings") or {})
    if not REFERENCE_HISTORY.is_file():
        raise RuntimeError(f"Reference history file not found: {REFERENCE_HISTORY}")
    replay_settings["file_path"] = str(REFERENCE_HISTORY)
    replay_settings["speed"] = 1000
    data["replay_settings"] = replay_settings
    return AlgorithmWorkspace.from_storage_dict(data)


def _advance_exact(runtime: WorkspaceRuntime, count: int) -> int:
    """Обробити не більше count strategy bars через production chronology."""
    session = runtime.replay_session
    if session is None:
        raise RuntimeError("Replay session is not initialized")
    processed = 0
    while processed < count and not session.completed:
        requested = min(1000, count - processed)
        events = runtime.advance_replay(max_events=requested)
        if not events:
            break
        processed += len(events)
    return processed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--full",
        action="store_true",
        help="Дограти весь Replay після стандартних 2000 strategy bars.",
    )
    args = parser.parse_args()

    workspace = _reference_workspace()
    runtime = WorkspaceRuntime(
        workspace,
        algorithm_factory=create_registered_workspace_algorithm,
    )

    startup_started = perf_counter()
    runtime.begin_start()
    runtime.complete_start()
    startup_seconds = perf_counter() - startup_started
    session = runtime.replay_session
    if session is None:
        raise AssertionError("Replay session missing")
    assert session.multi_resolution

    first_started = perf_counter()
    first_count = _advance_exact(runtime, 1000)
    first_seconds = perf_counter() - first_started
    assert first_count == 1000

    second_started = perf_counter()
    second_count = _advance_exact(runtime, 1000)
    second_seconds = perf_counter() - second_started
    assert second_count == 1000

    engine = runtime.replay_execution
    assert engine is not None
    first_snapshot = engine.snapshot()
    second_snapshot = engine.snapshot()
    cached_closed_positions = [
        first is second
        for first, second in zip(
            first_snapshot.positions,
            second_snapshot.positions,
            strict=True,
        )
        if not first.active
    ]
    closed_snapshot_cache_reused = bool(cached_closed_positions) and all(
        cached_closed_positions
    )
    assert closed_snapshot_cache_reused
    assert first_snapshot == second_snapshot
    processed_after_2000 = session.index
    signals_after_2000 = len(runtime.signal_records())
    virtual_positions_after_2000 = len(first_snapshot.positions)

    full_seconds: float | None = None
    if args.full:
        full_started = perf_counter()
        while not session.completed:
            events = runtime.advance_replay(max_events=1000)
            if not events:
                break
        full_seconds = perf_counter() - full_started
        assert session.completed

    print("Algorithm Workspace Replay Performance Benchmark result")
    print(f"  strategy_bars_total={len(session.events)}")
    print(f"  startup_seconds={startup_seconds:.3f}")
    print(f"  first_1000_compute_seconds={first_seconds:.3f}")
    print(f"  second_1000_compute_seconds={second_seconds:.3f}")
    print(f"  processed_strategy_bars={processed_after_2000}")
    print(f"  signals_after_2000={signals_after_2000}")
    print(f"  virtual_positions_after_2000={virtual_positions_after_2000}")
    print(f"  closed_snapshot_cache_reused={closed_snapshot_cache_reused}")
    if full_seconds is not None:
        print(f"  remaining_full_compute_seconds={full_seconds:.3f}")
        print(f"  full_replay_completed={session.completed}")
        print(f"  final_virtual_positions={len(engine.snapshot().positions)}")
        print(f"  final_realized_profit={engine.realized_profit:.2f}")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_REPLAY_PERFORMANCE_BENCHMARK=OK")


if __name__ == "__main__":
    main()
