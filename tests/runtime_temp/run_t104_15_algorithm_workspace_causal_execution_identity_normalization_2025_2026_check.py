# -*- coding: utf-8 -*-
"""RoadMap104 / T104-15 / 8C.16: causal execution identity normalization.

T104-13 показав два різні класи collision у TEST_ONLY research
pipeline:
1) кілька GREEN 8C.1 opening candidates можуть бути підтверджені
   тим самим
   fresh MACD cross і вести до одного NEXT_M15_OPEN execution;
2) кілька різних first-leg TAKE_PROFIT sources можуть повторно
   використати
   один і той самий Donchian re-breakout event для однакового
   second-leg
   NEXT_M15_OPEN execution.

T104-15 не змінює production Candidate F, GREEN 8C.1 signal logic,
T104-08 Donchian pullback/re-breakout rules або T104-11 dominant acceleration
predicate. Він додає лише causal execution-identity normalization до
діагностичного inventory:
- FIRST_LEG identity = direction + entry_index; при collision лишається
  найраніший source opening candidate;
- REENTRY identity = direction + Donchian signal_index + re-entry timestamp;
  при collision лишається найраніший eligible first-leg source.

Обидва survivor rules використовують тільки дані, вже відомі на
causal signal bar. Нових numeric thresholds, outcome-based selection або
future data немає.
"""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BASE_SCRIPT_NAME = (
    "run_t104_13_algorithm_workspace_causal_identity_collision_audit_"
    "2025_2026_check.py"
)
TEST_ID = "T104-15"
ROADMAP_BLOCK = "8C.16"


def _load_base_module() -> ModuleType:
    """Завантажити T104-13 як read-only dependency."""
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm104_t104_15_identity_audit_base"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


AUDIT = _load_base_module()
BASE = getattr(AUDIT, "BASE")
WINDOWS = getattr(AUDIT, "WINDOWS")
_run_window: Callable[..., Any] = getattr(BASE, "_run_window")
_dominant_acceleration: Callable[..., bool] = getattr(
    BASE,
    "_dominant_acceleration",
)
REENTRY_BASE = getattr(BASE, "REENTRY_BASE")
_summary: Callable[..., Any] = getattr(REENTRY_BASE, "_summary")
_summary_text: Callable[..., str] = getattr(REENTRY_BASE, "_summary_text")


def _first_leg_key(candidate: Any) -> tuple[str, int]:
    return str(candidate.direction), int(candidate.entry_index)


def _reentry_key(candidate: Any, row: Any) -> tuple[str, int, Any]:
    assert row.signal_index is not None
    assert row.reentry_trade is not None
    return (
        str(candidate.direction),
        int(row.signal_index),
        row.reentry_trade.entry_timestamp,
    )


def _source_rank(candidate: Any) -> tuple[int, int, int]:
    """Повернути causal rank з пріоритетом найранішого first-leg source."""
    return (
        int(candidate.entry_index),
        int(candidate.start_index),
        int(candidate.confirm_index),
    )


def _first_leg_survivor_indices(candidates: tuple[Any, ...]) -> tuple[int, ...]:
    """Лишити один execution на direction + NEXT_M15 entry index."""
    survivors: dict[tuple[str, int], tuple[tuple[int, int, int], int]] = {}
    for index, candidate in enumerate(candidates):
        key = _first_leg_key(candidate)
        rank = _source_rank(candidate)
        current = survivors.get(key)
        if current is None or rank < current[0]:
            survivors[key] = (rank, index)

    indices = tuple(sorted(item[1] for item in survivors.values()))
    assert len(indices) == len(survivors)
    return indices


def _aligned_reentry_rows(
    data: dict[str, Any],
) -> list[tuple[int, Any, Any, Any, Any]]:
    """Відновити original candidate index для T104-11 anatomy row."""
    base = data["base"]
    candidate_rows = [
        (index, candidate, row)
        for index, (candidate, row) in enumerate(zip(base["candidates"], base["rows"]))
        if row.reentry_trade is not None
        and row.pullback_index is not None
        and row.signal_index is not None
    ]
    assert len(candidate_rows) == len(data["rows"])
    return [
        (index, candidate, row, anatomy, trade)
        for (index, candidate, row), (anatomy, trade) in zip(
            candidate_rows,
            data["rows"],
        )
    ]


def _normalize_reentries(
    rows: list[tuple[int, Any, Any, Any, Any]],
) -> list[tuple[int, Any, Any, Any, Any]]:
    """Лишити один second-leg execution на causal Donchian event."""
    survivors: dict[
        tuple[str, int, Any],
        tuple[tuple[int, int, int], tuple[int, Any, Any, Any, Any]],
    ] = {}
    for item in rows:
        _, candidate, row, _, _ = item
        key = _reentry_key(candidate, row)
        rank = _source_rank(candidate)
        current = survivors.get(key)
        if current is None or rank < current[0]:
            survivors[key] = (rank, item)

    normalized = [item[1] for item in survivors.values()]
    normalized.sort(key=lambda entry: entry[4].entry_timestamp)
    return normalized


def _collision_count(keys: list[Any]) -> int:
    counts = Counter(keys)
    return sum(value - 1 for value in counts.values() if value > 1)


def _outcome_text(trades: list[Any]) -> str:
    counter = Counter(str(trade.close_reason) for trade in trades)
    if not counter:
        return "NONE"
    return "|".join(f"{key}:{counter[key]}" for key in sorted(counter))


def _run_normalized(window: Any) -> dict[str, Any]:
    data = _run_window(window)
    base = data["base"]
    candidates = tuple(base["candidates"])
    baseline = tuple(base["baseline"])

    first_survivor_indices = _first_leg_survivor_indices(candidates)
    first_survivor_set = set(first_survivor_indices)
    normalized_baseline = [baseline[index] for index in first_survivor_indices]

    aligned_rows = _aligned_reentry_rows(data)
    after_first_leg_normalization = [
        item for item in aligned_rows if item[0] in first_survivor_set
    ]
    normalized_reentries = _normalize_reentries(after_first_leg_normalization)
    selected_reentries = [
        item for item in normalized_reentries if _dominant_acceleration(item[3])
    ]

    raw_first_keys = [_first_leg_key(candidate) for candidate in candidates]
    normalized_first_keys = [
        _first_leg_key(candidates[index]) for index in first_survivor_indices
    ]
    after_first_reentry_keys = [
        _reentry_key(item[1], item[2]) for item in after_first_leg_normalization
    ]
    normalized_reentry_keys = [
        _reentry_key(item[1], item[2]) for item in normalized_reentries
    ]
    selected_reentry_keys = [
        _reentry_key(item[1], item[2]) for item in selected_reentries
    ]

    return {
        "data": data,
        "raw_first_count": len(candidates),
        "normalized_first_count": len(normalized_baseline),
        "raw_first_collision_instances": _collision_count(raw_first_keys),
        "normalized_first_collision_instances": _collision_count(normalized_first_keys),
        "normalized_baseline": normalized_baseline,
        "raw_reentry_count": len(aligned_rows),
        "after_first_reentry_count": len(after_first_leg_normalization),
        "after_first_reentry_collision_instances": _collision_count(
            after_first_reentry_keys
        ),
        "normalized_reentries": normalized_reentries,
        "normalized_reentry_collision_instances": _collision_count(
            normalized_reentry_keys
        ),
        "selected_reentries": selected_reentries,
        "selected_reentry_collision_instances": _collision_count(selected_reentry_keys),
    }


def main() -> int:
    results = {window.label: _run_normalized(window) for window in WINDOWS}

    print("T104-15 Causal Execution Identity Normalization result")
    print(f"  test_id={TEST_ID}")
    print(f"  roadmap_block={ROADMAP_BLOCK}")
    print(
        "  mode=RM104_T104_15_8C16_CAUSAL_EXECUTION_IDENTITY_" "NORMALIZATION_TEST_ONLY"
    )
    print("  base_test_id=T104-13")
    print("  production_candidate_f_logic_changed=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  green_8c1_signal_logic_changed=False")
    print("  t104_08_reentry_signal_logic_changed=False")
    print("  t104_11_discriminator_changed=False")
    print("  normalization_scope=DIAGNOSTIC_EXECUTION_INVENTORY_ONLY")
    print("  first_leg_identity=DIRECTION_PLUS_NEXT_M15_ENTRY_INDEX")
    print("  first_leg_survivor=EARLIEST_CAUSAL_SOURCE_OPENING")
    print(
        "  reentry_identity=DIRECTION_PLUS_DONCHIAN_SIGNAL_INDEX_PLUS_"
        "NEXT_M15_ENTRY_TIMESTAMP"
    )
    print("  reentry_survivor=EARLIEST_ELIGIBLE_FIRST_LEG_SOURCE")
    print("  survivor_selection_uses_outcome=False")
    print("  new_numeric_tuning=False")
    print("  future_price_used_for_identity_normalization=False")

    normalized_all_collisions_removed = True
    selected_incremental_positive_both = True

    for window in WINDOWS:
        data = results[window.label]
        baseline_summary = _summary(tuple(data["normalized_baseline"]))
        normalized_reentry_trades = [item[4] for item in data["normalized_reentries"]]
        normalized_reentry_summary = _summary(tuple(normalized_reentry_trades))
        selected_trades = [item[4] for item in data["selected_reentries"]]
        selected_summary = _summary(tuple(selected_trades))

        normalized_all_collisions_removed = bool(
            normalized_all_collisions_removed
            and data["normalized_first_collision_instances"] == 0
            and data["normalized_reentry_collision_instances"] == 0
            and data["selected_reentry_collision_instances"] == 0
        )
        selected_incremental_positive_both = bool(
            selected_incremental_positive_both and selected_summary.net > 0
        )

        print(
            f"  {window.label}/FIRST_LEG_NORMALIZATION="
            f"raw:{data['raw_first_count']},"
            f"raw_collision_instances:{data['raw_first_collision_instances']},"
            f"normalized:{data['normalized_first_count']},"
            "normalized_collision_instances:"
            f"{data['normalized_first_collision_instances']},"
            f"summary:{_summary_text(baseline_summary)}"
        )
        print(
            f"  {window.label}/REENTRY_NORMALIZATION="
            f"raw:{data['raw_reentry_count']},"
            f"after_first_leg_normalization:{data['after_first_reentry_count']},"
            "after_first_collision_instances:"
            f"{data['after_first_reentry_collision_instances']},"
            f"normalized:{len(data['normalized_reentries'])},"
            "normalized_collision_instances:"
            f"{data['normalized_reentry_collision_instances']},"
            f"outcomes:{_outcome_text(normalized_reentry_trades)},"
            f"summary:{_summary_text(normalized_reentry_summary)}"
        )
        print(
            f"  {window.label}/DOMINANT_ACCELERATION_AFTER_NORMALIZATION="
            f"selected:{len(selected_trades)},"
            f"collision_instances:{data['selected_reentry_collision_instances']},"
            f"outcomes:{_outcome_text(selected_trades)},"
            f"summary:{_summary_text(selected_summary)},"
            f"combined_net:{baseline_summary.net + selected_summary.net:+.2f}"
        )

    print(
        "  normalized_first_and_reentry_collisions_removed="
        f"{normalized_all_collisions_removed}"
    )
    print(
        "  dominant_acceleration_incremental_net_positive_both_periods="
        f"{selected_incremental_positive_both}"
    )
    assert normalized_all_collisions_removed
    print("  identity_normalization_is_causal=True")
    print("  performance_is_diagnostic_not_pass_criterion=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print(
        "T104_15_ALGORITHM_WORKSPACE_CAUSAL_EXECUTION_IDENTITY_"
        "NORMALIZATION_CHECK=OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
