# -*- coding: utf-8 -*-
"""Перевірка обчислюваних spread і warm-up requirements WSP."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_parameter_catalog import (  # noqa: E402
    build_workspace_parameter_catalog,
)
from core.workspace_parameter_schema import (  # noqa: E402
    WorkspaceParameterDefinition,
)
from core.workspace_parameters import (  # noqa: E402
    WorkspaceAlgorithmParameters,
)
from core.workspace_runtime_requirements import (  # noqa: E402
    LEGACY_WORKSPACE_RUNTIME_PARAMETER_KEYS,
    WorkspaceSpreadObservation,
    WorkspaceWarmupRequirement,
    build_workspace_warmup_plan,
)


def main() -> None:
    spread = WorkspaceSpreadObservation.from_bid_ask(
        bid=1.10000,
        ask=1.10018,
        point_size=0.00001,
    )
    assert round(spread.spread_price, 5) == 0.00018
    assert spread.spread_points is not None
    assert round(spread.spread_points, 6) == 18.0

    invalid_quote_blocked = False
    try:
        WorkspaceSpreadObservation.from_bid_ask(
            bid=1.10020,
            ask=1.10010,
        )
    except ValueError:
        invalid_quote_blocked = True
    assert invalid_quote_blocked

    requirements = (
        WorkspaceWarmupRequirement("MACD", "M15", 35),
        WorkspaceWarmupRequirement("ALLIGATOR", "M15", 21),
        WorkspaceWarmupRequirement("HTF_FILTER", "H1", 50),
        WorkspaceWarmupRequirement("VOLATILITY", "M15", 35),
    )
    plan = build_workspace_warmup_plan(requirements, reserve_bars=10)
    assert plan.required_bars_for("M15") == 45
    assert plan.required_bars_for("H1") == 60
    assert plan.required_bars_for("D1") == 0
    m15 = next(item for item in plan.timeframes if item.timeframe == "M15")
    assert m15.limiting_components == ("MACD", "VOLATILITY")

    repeated = build_workspace_warmup_plan(requirements, reserve_bars=10)
    assert repeated == plan

    legacy = WorkspaceAlgorithmParameters(
        spread_limit=0.00018,
        warmup_bars=25,
    )
    parameters = legacy.merge_parameters({"future_key": "preserved"})
    assert parameters["spread_limit"] == 0.00018
    assert parameters["warmup_bars"] == 25
    assert parameters["future_key"] == "preserved"
    assert set(LEGACY_WORKSPACE_RUNTIME_PARAMETER_KEYS).issubset(parameters)

    catalog = build_workspace_parameter_catalog()
    catalog_definitions: tuple[
        WorkspaceParameterDefinition,
        ...,
    ] = catalog.parameters

    catalog_storage_keys = {
        definition.storage_key for definition in catalog_definitions
    }
    assert "spread_limit" not in catalog_storage_keys
    assert "warmup_bars" not in catalog_storage_keys

    print("Algorithm Workspace Runtime Requirements result")
    print("  spread_from_bid_ask=True")
    print("  spread_points_supported=True")
    print("  invalid_quote_blocked=True")
    print("  warmup_from_component_requirements=True")
    print("  warmup_per_timeframe=True")
    print("  warmup_reserve_applied=True")
    print("  limiting_components_visible=True")
    print("  deterministic=True")
    print("  legacy_keys_preserved=True")
    print("  legacy_keys_hidden_from_schema_tree=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_RUNTIME_REQUIREMENTS_CHECK=OK")


if __name__ == "__main__":
    main()
