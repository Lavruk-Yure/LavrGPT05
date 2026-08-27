# -*- coding: utf-8 -*-
"""RoadMap104 / T104-13 / 8C.14: causal identity collision audit.

TEST_ONLY runner не змінює production Candidate F, GREEN 8C.1 entry,
T104-08 Donchian pullback/re-breakout re-entry або T104-11 discriminator.

T104-12 показав кілька selected second-leg trades з абсолютно однаковими
entry timestamp, direction, outcome і PnL. Перед подальшим дослідженням
потрібно відокремити реальну концентрацію стратегії від повторного
використання одного causal event кількома candidate rows.

Аудит перевіряє три рівні identity без зміни permission logic:
1) FIRST_LEG: direction + entry_index GREEN 8C.1 candidate;
2) REENTRY_SIGNAL: direction + Donchian signal_index + re-entry entry time;
3) SELECTED_REENTRY: той самий re-entry identity після незмінного
   T104-11 DOMINANT_ACCELERATION predicate.

Для кожного рівня друкуються raw/unique counts, collision multiplicity та
діагностичний raw/unique PnL. Collapse до unique використовується лише для
аудиту й не є новою execution policy або production зміною.
"""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter, defaultdict
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BASE_SCRIPT_NAME = (
    "run_t104_11_algorithm_workspace_macd_relative_restart_discriminator_"
    "2025_2026_check.py"
)
TEST_ID = "T104-13"
ROADMAP_BLOCK = "8C.14"


def _load_base_module() -> ModuleType:
    """Завантажити T104-11 як read-only dependency."""
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm104_t104_13_identity_base"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()
WINDOWS = getattr(BASE, "WINDOWS")
_run_window: Callable[..., Any] = getattr(BASE, "_run_window")
_dominant_acceleration: Callable[..., bool] = getattr(
    BASE,
    "_dominant_acceleration",
)
REENTRY_BASE = getattr(BASE, "REENTRY_BASE")
_summary: Callable[..., Any] = getattr(REENTRY_BASE, "_summary")


def _summary_net(trades: Iterable[Any]) -> float:
    return float(_summary(tuple(trades)).net)


def _entry_key(candidate: Any) -> tuple[str, int]:
    return str(candidate.direction), int(candidate.entry_index)


def _reentry_key(candidate: Any, row: Any) -> tuple[str, int, Any]:
    assert row.signal_index is not None
    assert row.reentry_trade is not None
    return (
        str(candidate.direction),
        int(row.signal_index),
        row.reentry_trade.entry_timestamp,
    )


def _collapse_first_by_key(
    candidates: Iterable[Any],
    trades: Iterable[Any],
) -> tuple[list[Any], Counter[tuple[str, int]]]:
    counts: Counter[tuple[str, int]] = Counter()
    unique_trades: list[Any] = []
    seen: set[tuple[str, int]] = set()
    for candidate, trade in zip(candidates, trades):
        key = _entry_key(candidate)
        counts[key] += 1
        if key in seen:
            continue
        seen.add(key)
        unique_trades.append(trade)
    return unique_trades, counts


def _filtered_reentry_rows(data: dict[str, Any]) -> list[tuple[Any, Any, Any, Any]]:
    """Відновити alignment candidate/row/anatomy/trade з T104-11."""
    candidate_rows = [
        (candidate, row)
        for candidate, row in zip(
            data["base"]["candidates"],
            data["base"]["rows"],
        )
        if row.reentry_trade is not None
        and row.pullback_index is not None
        and row.signal_index is not None
    ]
    assert len(candidate_rows) == len(data["rows"])
    return [
        (candidate, row, anatomy, trade)
        for (candidate, row), (anatomy, trade) in zip(
            candidate_rows,
            data["rows"],
        )
    ]


def _collapse_reentries(
    rows: Iterable[tuple[Any, Any, Any, Any]],
    *,
    selected_only: bool,
) -> tuple[list[Any], Counter[tuple[str, int, Any]]]:
    counts: Counter[tuple[str, int, Any]] = Counter()
    unique_trades: list[Any] = []
    seen: set[tuple[str, int, Any]] = set()
    for candidate, row, anatomy, trade in rows:
        if selected_only and not _dominant_acceleration(anatomy):
            continue
        key = _reentry_key(candidate, row)
        counts[key] += 1
        if key in seen:
            continue
        seen.add(key)
        unique_trades.append(trade)
    return unique_trades, counts


def _collision_metrics(counter: Counter[Any]) -> tuple[int, int, int, int, int]:
    raw = sum(counter.values())
    unique = len(counter)
    duplicate_instances = raw - unique
    duplicate_groups = sum(value > 1 for value in counter.values())
    maximum = max(counter.values(), default=0)
    return raw, unique, duplicate_instances, duplicate_groups, maximum


def _first_collision_lines(
    candidates: Iterable[Any],
    counter: Counter[tuple[str, int]],
) -> list[str]:
    timestamps: defaultdict[tuple[str, int], list[Any]] = defaultdict(list)
    for candidate in candidates:
        key = _entry_key(candidate)
        timestamps[key].append(candidate.entry_timestamp)
    lines: list[str] = []
    for key, multiplicity in counter.items():
        if multiplicity <= 1:
            continue
        direction, entry_index = key
        lines.append(
            f"direction:{direction},entry_index:{entry_index},"
            f"entry_time:{timestamps[key][0].isoformat()},"
            f"multiplicity:{multiplicity}"
        )
    return lines


def _reentry_collision_lines(
    rows: Iterable[tuple[Any, Any, Any, Any]],
    counter: Counter[tuple[str, int, Any]],
    *,
    selected_only: bool,
) -> list[str]:
    source_entries: defaultdict[tuple[str, int, Any], list[Any]] = defaultdict(list)
    for candidate, row, anatomy, _ in rows:
        if selected_only and not _dominant_acceleration(anatomy):
            continue
        key = _reentry_key(candidate, row)
        source_entries[key].append(candidate.entry_timestamp)
    lines: list[str] = []
    for key, multiplicity in counter.items():
        if multiplicity <= 1:
            continue
        direction, signal_index, entry_time = key
        source_text = "|".join(
            timestamp.isoformat() for timestamp in source_entries[key]
        )
        lines.append(
            f"direction:{direction},signal_index:{signal_index},"
            f"reentry_time:{entry_time.isoformat()},multiplicity:{multiplicity},"
            f"source_first_leg_entries:{source_text}"
        )
    return lines


def main() -> int:
    print("T104-13 Causal Identity Collision Audit result")
    print(f"  test_id={TEST_ID}")
    print(f"  roadmap_block={ROADMAP_BLOCK}")
    print("  mode=RM104_T104_13_8C14_CAUSAL_IDENTITY_COLLISION_AUDIT_TEST_ONLY")
    print("  base_test_id=T104-11")
    print("  production_candidate_f_logic_changed=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  green_8c1_entry_logic_changed=False")
    print("  t104_08_reentry_logic_changed=False")
    print("  t104_11_discriminator_changed=False")
    print("  collapse_is_diagnostic_only_not_execution_policy=True")
    print("  new_filter_added=False")
    print("  new_numeric_tuning=False")

    any_first_collision = False
    any_reentry_collision = False
    any_selected_collision = False

    for window in WINDOWS:
        data = _run_window(window)
        base = data["base"]

        unique_first, first_counter = _collapse_first_by_key(
            base["candidates"],
            base["baseline"],
        )
        first_metrics = _collision_metrics(first_counter)
        any_first_collision = any_first_collision or first_metrics[2] > 0
        print(
            f"  {window.label}/FIRST_LEG_IDENTITY="
            f"raw:{first_metrics[0]},unique:{first_metrics[1]},"
            f"duplicate_instances:{first_metrics[2]},"
            f"duplicate_groups:{first_metrics[3]},"
            f"max_multiplicity:{first_metrics[4]},"
            f"raw_net:{_summary_net(base['baseline']):+.2f},"
            f"unique_net:{_summary_net(unique_first):+.2f}"
        )
        for line in _first_collision_lines(base["candidates"], first_counter):
            print(f"  {window.label}/FIRST_LEG_COLLISION={line}")

        reentry_rows = _filtered_reentry_rows(data)
        unique_reentries, reentry_counter = _collapse_reentries(
            reentry_rows,
            selected_only=False,
        )
        reentry_metrics = _collision_metrics(reentry_counter)
        any_reentry_collision = any_reentry_collision or reentry_metrics[2] > 0
        print(
            f"  {window.label}/REENTRY_IDENTITY="
            f"raw:{reentry_metrics[0]},unique:{reentry_metrics[1]},"
            f"duplicate_instances:{reentry_metrics[2]},"
            f"duplicate_groups:{reentry_metrics[3]},"
            f"max_multiplicity:{reentry_metrics[4]},"
            f"raw_net:{_summary_net(base['reentry_trades']):+.2f},"
            f"unique_net:{_summary_net(unique_reentries):+.2f}"
        )
        for line in _reentry_collision_lines(
            reentry_rows,
            reentry_counter,
            selected_only=False,
        ):
            print(f"  {window.label}/REENTRY_COLLISION={line}")

        selected_raw = [
            trade for anatomy, trade in data["rows"] if _dominant_acceleration(anatomy)
        ]
        unique_selected, selected_counter = _collapse_reentries(
            reentry_rows,
            selected_only=True,
        )
        selected_metrics = _collision_metrics(selected_counter)
        any_selected_collision = any_selected_collision or selected_metrics[2] > 0
        print(
            f"  {window.label}/SELECTED_REENTRY_IDENTITY="
            f"raw:{selected_metrics[0]},unique:{selected_metrics[1]},"
            f"duplicate_instances:{selected_metrics[2]},"
            f"duplicate_groups:{selected_metrics[3]},"
            f"max_multiplicity:{selected_metrics[4]},"
            f"raw_net:{_summary_net(selected_raw):+.2f},"
            f"unique_net:{_summary_net(unique_selected):+.2f}"
        )
        for line in _reentry_collision_lines(
            reentry_rows,
            selected_counter,
            selected_only=True,
        ):
            print(f"  {window.label}/SELECTED_REENTRY_COLLISION={line}")

    print(f"  first_leg_identity_collisions_detected={any_first_collision}")
    print(f"  reentry_identity_collisions_detected={any_reentry_collision}")
    print(f"  selected_reentry_identity_collisions_detected={any_selected_collision}")
    print("  performance_is_diagnostic_not_pass_criterion=True")
    print("  causal_identity_audit_only=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T104_13_ALGORITHM_WORKSPACE_CAUSAL_IDENTITY_COLLISION_AUDIT_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
