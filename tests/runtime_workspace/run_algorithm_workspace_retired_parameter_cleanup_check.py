# -*- coding: utf-8 -*-
"""RoadMap98: видалення відхиленого MACD Strength-параметра з WSP."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import AlgorithmWorkspace  # noqa: E402


def main() -> None:
    workspace = AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        parameters={
            "macd_signal_enabled": True,
            "macd_signal_mode": "EXTENDED",
            "macd_minimum_crossover_strength": 0.000005,
            "future_parameter": "KEEP",
        },
    )

    assert "macd_minimum_crossover_strength" not in workspace.parameters
    assert workspace.parameters["future_parameter"] == "KEEP"
    assert workspace.parameters["macd_signal_mode"] == "EXTENDED"

    restored = AlgorithmWorkspace.from_storage_dict(workspace.to_storage_dict())
    assert "macd_minimum_crossover_strength" not in restored.parameters
    assert restored.parameters["future_parameter"] == "KEEP"

    print("Algorithm Workspace Retired Parameter Cleanup result")
    print("  macd_strength_parameter_removed=True")
    print("  unknown_future_parameter_preserved=True")
    print("  extended_mode_preserved=True")
    print("ALGORITHM_WORKSPACE_RETIRED_PARAMETER_CLEANUP_CHECK=OK")


if __name__ == "__main__":
    main()
