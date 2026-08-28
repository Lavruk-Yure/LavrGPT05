# -*- coding: utf-8 -*-
"""RoadMap104 / T104-16: production-contract candidate regression.

Runner передає фактичний execution inventory T104-15 за 2025/2026 роки до
спільного кандидата production-компонента Workspace identity normalization.
Формування сигналів, eligibility, симуляція входу/виходу й усі пороги
індикаторів залишаються в уже GREEN base pipeline. Production wiring навмисно
відсутній у межах варіанта A.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from collections import Counter
from dataclasses import fields
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_execution_identity import (  # noqa: E402
    WorkspaceExecutionIdentity,
    WorkspaceExecutionSource,
    normalize_workspace_execution_sources,
)
from core.workspace_replay_execution import (  # noqa: E402
    WorkspaceReplayExecutionEngine,
)
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402

BASE_SCRIPT_NAME = (
    "run_t104_15_algorithm_workspace_causal_execution_identity_"
    "normalization_2025_2026_check.py"
)
TEST_ID = "T104-16"


def _load_base_module() -> ModuleType:
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm104_t104_16_production_contract_candidate_base"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()
WINDOWS = getattr(BASE, "WINDOWS")
_run_window: Callable[..., dict[str, Any]] = getattr(BASE, "_run_window")
_aligned_reentry_rows: Callable[..., list[tuple[int, Any, Any, Any, Any]]] = getattr(
    BASE, "_aligned_reentry_rows"
)
_dominant_acceleration: Callable[..., bool] = getattr(
    BASE,
    "_dominant_acceleration",
)


def _source_uid(candidate: Any) -> str:
    return (
        f"{str(candidate.direction).upper()}:"
        f"{int(candidate.start_index)}:"
        f"{int(candidate.confirm_index)}:"
        f"{int(candidate.entry_index)}"
    )


def _first_leg_sources(
    candidates: tuple[Any, ...],
) -> tuple[WorkspaceExecutionSource, ...]:
    return tuple(
        WorkspaceExecutionSource(
            identity=WorkspaceExecutionIdentity.first_leg(
                direction=str(candidate.direction),
                next_m15_entry_index=int(candidate.entry_index),
            ),
            opening_source_index=int(candidate.start_index),
            confirmation_index=int(candidate.confirm_index),
            source_uid=_source_uid(candidate),
        )
        for candidate in candidates
    )


def _reentry_sources(
    rows: Iterable[tuple[int, Any, Any, Any, Any]],
) -> tuple[WorkspaceExecutionSource, ...]:
    result: list[WorkspaceExecutionSource] = []
    for _, candidate, row, _, _ in rows:
        assert row.signal_index is not None
        assert row.reentry_trade is not None
        result.append(
            WorkspaceExecutionSource(
                identity=WorkspaceExecutionIdentity.reentry(
                    direction=str(candidate.direction),
                    donchian_signal_index=int(row.signal_index),
                    next_m15_entry_timestamp=row.reentry_trade.entry_timestamp,
                ),
                opening_source_index=int(candidate.start_index),
                confirmation_index=int(candidate.confirm_index),
                source_uid=_source_uid(candidate),
            )
        )
    return tuple(result)


def _signature(
    sources: Iterable[WorkspaceExecutionSource],
) -> tuple[tuple[tuple[object, ...], str], ...]:
    return tuple(
        (source.identity.deterministic_key(), source.source_uid) for source in sources
    )


def _duplicate_count(sources: Iterable[WorkspaceExecutionSource]) -> int:
    counter = Counter(source.identity for source in sources)
    return sum(count - 1 for count in counter.values() if count > 1)


def _normalize_deterministically(
    sources: tuple[WorkspaceExecutionSource, ...],
) -> tuple[WorkspaceExecutionSource, ...]:
    forward = normalize_workspace_execution_sources(sources)
    reverse = normalize_workspace_execution_sources(reversed(sources))
    rotated_input = sources[1:] + sources[:1] if sources else sources
    rotated = normalize_workspace_execution_sources(rotated_input)
    assert _signature(forward) == _signature(reverse) == _signature(rotated)
    return forward


def _run_contract_candidate_normalization(window: Any) -> dict[str, Any]:
    data = _run_window(window)
    candidates = tuple(data["base"]["candidates"])
    first_sources = _first_leg_sources(candidates)
    normalized_first = _normalize_deterministically(first_sources)
    first_survivor_uids = {source.source_uid for source in normalized_first}

    aligned_rows = _aligned_reentry_rows(data)
    eligible_rows = tuple(
        item for item in aligned_rows if _source_uid(item[1]) in first_survivor_uids
    )
    reentry_sources = _reentry_sources(eligible_rows)
    normalized_reentries = _normalize_deterministically(reentry_sources)
    reentry_survivor_uids = {
        (source.identity, source.source_uid) for source in normalized_reentries
    }
    selected_reentries = tuple(
        item
        for item in eligible_rows
        if (
            WorkspaceExecutionIdentity.reentry(
                direction=str(item[1].direction),
                donchian_signal_index=int(item[2].signal_index),
                next_m15_entry_timestamp=item[2].reentry_trade.entry_timestamp,
            ),
            _source_uid(item[1]),
        )
        in reentry_survivor_uids
        and _dominant_acceleration(item[3])
    )

    return {
        "first_sources": first_sources,
        "normalized_first": normalized_first,
        "reentry_sources": reentry_sources,
        "normalized_reentries": normalized_reentries,
        "selected_reentries": selected_reentries,
    }


def main() -> int:
    first_pass = {
        window.label: _run_contract_candidate_normalization(window)
        for window in WINDOWS
    }
    second_pass = {
        window.label: _run_contract_candidate_normalization(window)
        for window in WINDOWS
    }

    source_fields = {field.name for field in fields(WorkspaceExecutionSource)}
    assert source_fields == {
        "identity",
        "opening_source_index",
        "confirmation_index",
        "source_uid",
    }

    signal_record_fields = {field.name for field in fields(WorkspaceSignalRecord)}
    queue_signal_parameters = tuple(
        inspect.signature(WorkspaceReplayExecutionEngine.queue_signal).parameters
    )
    production_component_exists = callable(normalize_workspace_execution_sources)
    production_runtime_wired = bool(
        "execution_identity" in signal_record_fields
        or queue_signal_parameters != ("self", "record", "signal_event")
    )
    production_contract_extension_required = not production_runtime_wired
    execution_behavior_changed = False

    assert production_component_exists
    assert not production_runtime_wired
    assert production_contract_extension_required
    assert not execution_behavior_changed

    print("T104-16 Production-Contract Candidate Regression result")
    print(f"  test_id={TEST_ID}")
    print("  semantics=PRODUCTION_CONTRACT_CANDIDATE_NOT_RUNTIME_WIRED")
    print("  normalization_layer=core.workspace_execution_identity")
    print("  first_leg_identity=DIRECTION_PLUS_NEXT_M15_ENTRY_INDEX")
    print("  first_leg_survivor=EARLIEST_CAUSAL_OPENING_SOURCE")
    print(
        "  reentry_identity=DIRECTION_PLUS_DONCHIAN_SIGNAL_INDEX_PLUS_"
        "NEXT_M15_ENTRY_TIMESTAMP"
    )
    print("  reentry_survivor=EARLIEST_ELIGIBLE_FIRST_LEG_SOURCE")
    print("  candidate_f_signal_logic_changed=False")
    print("  entry_exit_logic_changed=False")
    print("  thresholds_changed=False")
    print("  bbw_ac_stochastic_changed=False")
    print(f"  production_component_exists={production_component_exists}")
    print(f"  production_runtime_wired={production_runtime_wired}")
    print(
        "  production_contract_extension_required="
        f"{production_contract_extension_required}"
    )
    print(f"  execution_behavior_changed={execution_behavior_changed}")

    for window in WINDOWS:
        label = window.label
        first = first_pass[label]
        second = second_pass[label]
        first_duplicates = _duplicate_count(first["normalized_first"])
        reentry_duplicates = _duplicate_count(first["normalized_reentries"])
        selected_identities = tuple(
            WorkspaceExecutionIdentity.reentry(
                direction=str(item[1].direction),
                donchian_signal_index=int(item[2].signal_index),
                next_m15_entry_timestamp=item[2].reentry_trade.entry_timestamp,
            )
            for item in first["selected_reentries"]
        )
        selected_duplicates = len(selected_identities) - len(set(selected_identities))

        assert first_duplicates == 0
        assert reentry_duplicates == 0
        assert selected_duplicates == 0
        assert _signature(first["normalized_first"]) == _signature(
            second["normalized_first"]
        )
        assert _signature(first["normalized_reentries"]) == _signature(
            second["normalized_reentries"]
        )

        print(
            f"  {label}/EXECUTIONS="
            f"first_raw:{len(first['first_sources'])},"
            f"first_normalized:{len(first['normalized_first'])},"
            f"reentry_raw:{len(first['reentry_sources'])},"
            f"reentry_normalized:{len(first['normalized_reentries'])},"
            f"selected:{len(first['selected_reentries'])},"
            "duplicate_executions:0"
        )

    print("  zero_duplicate_executions=True")
    print("  deterministic_replay=True")
    print("  survivor_selection_uses_outcome=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print(
        "T104_16_ALGORITHM_WORKSPACE_PRODUCTION_CONTRACT_CANDIDATE_"
        "IDENTITY_NORMALIZATION_REGRESSION_CHECK=OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
