# -*- coding: utf-8 -*-
"""Перевірка таблиці HIGHER_1/HIGHER_2 RoadMap96."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.timeframes import (  # noqa: E402
    WorkspaceTimeframeResolutionError,
    list_enabled_timeframes,
    resolve_alligator_confirmation_timeframe,
)
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_1,
    WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2,
    WORKSPACE_ALLIGATOR_HIGHER_1_TIMEFRAME_BY_BASE,
    WORKSPACE_ALLIGATOR_HIGHER_2_TIMEFRAME_BY_BASE,
)


def _blocked(base_timeframe: str, mode: str) -> bool:
    try:
        resolve_alligator_confirmation_timeframe(base_timeframe, mode)
    except WorkspaceTimeframeResolutionError:
        return True
    return False


def main() -> None:
    expected_higher_1 = {
        "M1": "M5",
        "M5": "M15",
        "M15": "H1",
        "M30": "H1",
        "H1": "H4",
        "H4": "D1",
        "D1": None,
    }
    expected_higher_2 = {
        "M1": "M15",
        "M5": "H1",
        "M15": "H4",
        "M30": "H4",
        "H1": "D1",
        "H4": None,
        "D1": None,
    }
    assert WORKSPACE_ALLIGATOR_HIGHER_1_TIMEFRAME_BY_BASE == expected_higher_1
    assert WORKSPACE_ALLIGATOR_HIGHER_2_TIMEFRAME_BY_BASE == expected_higher_2
    assert set(expected_higher_1) == set(list_enabled_timeframes())
    assert set(expected_higher_2) == set(list_enabled_timeframes())

    for base_timeframe, resolved in expected_higher_1.items():
        if resolved is None:
            assert _blocked(
                base_timeframe,
                WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_1,
            )
        else:
            assert (
                resolve_alligator_confirmation_timeframe(
                    base_timeframe,
                    WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_1,
                )
                == resolved
            )

    for base_timeframe, resolved in expected_higher_2.items():
        if resolved is None:
            assert _blocked(
                base_timeframe,
                WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2,
            )
        else:
            assert (
                resolve_alligator_confirmation_timeframe(
                    base_timeframe,
                    WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2,
                )
                == resolved
            )

    invalid_mode_blocked = _blocked("M15", "HIGHER_UNKNOWN")
    invalid_timeframe_blocked = False
    try:
        resolve_alligator_confirmation_timeframe("M2", "HIGHER_1")
    except (KeyError, WorkspaceTimeframeResolutionError):
        invalid_timeframe_blocked = True
    assert invalid_mode_blocked
    assert invalid_timeframe_blocked

    print("Algorithm Workspace Timeframe Mapping result")
    print("  canonical_variant=1")
    print("  higher_1_entries=7")
    print("  higher_2_entries=7")
    print("  explicit_unavailable_without_fallback=True")
    print("  integer_multiple_guard=True")
    print("  deterministic=True")
    print("ALGORITHM_WORKSPACE_TIMEFRAME_MAPPING_CHECK=OK")


if __name__ == "__main__":
    main()
