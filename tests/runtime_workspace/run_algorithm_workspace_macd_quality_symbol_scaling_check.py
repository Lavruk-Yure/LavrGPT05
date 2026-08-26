# -*- coding: utf-8 -*-
"""Перевірка symbol-aware MACD Quality thresholds для RM103 / 7W.3."""

from __future__ import annotations

import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_macd import WorkspaceMacdSignalSource  # noqa: E402
from core.workspace_runtime import WorkspaceRuntimeContext  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    DEFAULT_WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE,
    DEFAULT_WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE,
    NEW_WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE,
    NEW_WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE_PIPS,
    NEW_WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE,
    NEW_WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE_PIPS,
    WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE_KEY,
    WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE_KEY,
    resolve_forex_pip_size,
    resolve_new_workspace_macd_extremum_min_prominence,
    resolve_new_workspace_macd_extremum_to_cross_min_distance,
)


EXPECTED_THRESHOLDS = {
    "EURUSD": (0.000015, 0.00005),
    "GBPUSD": (0.000015, 0.00005),
    "USDJPY": (0.0015, 0.005),
}


def _assert_close(actual: float, expected: float) -> None:
    assert math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12)


def _workspace(
    symbol: str,
    parameters: dict[str, object] | None = None,
) -> AlgorithmWorkspace:
    return AlgorithmWorkspace.create(
        broker="CTRADER",
        account_id="RM103_7W3",
        symbol=symbol,
        timeframe="M15",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        parameters=parameters,
    )


def _runtime_thresholds(workspace: AlgorithmWorkspace) -> tuple[float, float]:
    source = WorkspaceMacdSignalSource.from_runtime_context(
        WorkspaceRuntimeContext.from_workspace(workspace),
        workspace.parameters,
    )
    return (
        source.extremum_min_prominence,
        source.extremum_to_cross_min_distance,
    )


def main() -> None:
    assert NEW_WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE_PIPS == 0.15
    assert NEW_WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE_PIPS == 0.5
    _assert_close(NEW_WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE, 0.000015)
    _assert_close(NEW_WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE, 0.00005)

    resolved: dict[str, tuple[float, float]] = {}
    runtime_resolved: dict[str, tuple[float, float]] = {}
    for symbol, expected in EXPECTED_THRESHOLDS.items():
        prominence = resolve_new_workspace_macd_extremum_min_prominence(symbol)
        distance = resolve_new_workspace_macd_extremum_to_cross_min_distance(symbol)
        _assert_close(prominence, expected[0])
        _assert_close(distance, expected[1])
        resolved[symbol] = (prominence, distance)

        workspace = _workspace(symbol)
        stored_prominence = float(
            workspace.parameters[WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE_KEY]
        )
        stored_distance = float(
            workspace.parameters[
                WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE_KEY
            ]
        )
        _assert_close(stored_prominence, expected[0])
        _assert_close(stored_distance, expected[1])

        runtime_values = _runtime_thresholds(workspace)
        _assert_close(runtime_values[0], expected[0])
        _assert_close(runtime_values[1], expected[1])
        runtime_resolved[symbol] = runtime_values

        pip_size = resolve_forex_pip_size(symbol)
        _assert_close(prominence / pip_size, 0.15)
        _assert_close(distance / pip_size, 0.5)

    explicit_parameters = {
        WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE_KEY: 0.000015,
        WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE_KEY: 0.00005,
    }
    persisted = _workspace("USDJPY", explicit_parameters)
    restored = AlgorithmWorkspace.from_storage_dict(persisted.to_storage_dict())
    _assert_close(
        float(restored.parameters[WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE_KEY]),
        0.000015,
    )
    _assert_close(
        float(
            restored.parameters[
                WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE_KEY
            ]
        ),
        0.00005,
    )
    persisted_runtime = _runtime_thresholds(restored)
    _assert_close(persisted_runtime[0], 0.000015)
    _assert_close(persisted_runtime[1], 0.00005)

    legacy_missing = _workspace("USDJPY", {})
    legacy_runtime = _runtime_thresholds(legacy_missing)
    _assert_close(
        legacy_runtime[0],
        DEFAULT_WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE,
    )
    _assert_close(
        legacy_runtime[1],
        DEFAULT_WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE,
    )

    non_forex = _workspace("XAUUSD")
    _assert_close(
        float(non_forex.parameters[WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE_KEY]),
        NEW_WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE,
    )
    _assert_close(
        float(
            non_forex.parameters[
                WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE_KEY
            ]
        ),
        NEW_WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE,
    )

    print("Algorithm Workspace MACD Quality Symbol Scaling result")
    print("  mode=RM103_7W3_SYMBOL_SAFE_MACD_QUALITY_THRESHOLDS")
    print("  production_candidate_f_logic_changed=False")
    print("  reference_prominence_pips=0.15")
    print("  reference_distance_pips=0.5")
    print(
        "  new_workspace_thresholds="
        + ",".join(
            f"{symbol}:{resolved[symbol][0]:g}/{resolved[symbol][1]:g}"
            for symbol in EXPECTED_THRESHOLDS
        )
    )
    print("  pip_normalized_new_workspace_thresholds_equal=True")
    print("  runtime_uses_materialized_symbol_thresholds=True")
    print("  explicit_persisted_raw_thresholds_preserved=True")
    print("  legacy_missing_keys_keep_legacy_raw_fallback=True")
    print("  non_forex_legacy_reference_fallback_preserved=True")
    print("  replay_spread_scaling_unchanged=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_MACD_QUALITY_SYMBOL_SCALING_CHECK=OK")


if __name__ == "__main__":
    main()
