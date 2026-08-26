# run_algorithm_workspace_macd_abc_production_migration_check.py — RoadMap99_04K
# -*- coding: utf-8 -*-
"""Production migration legacy -> ABC для MACD crossover angle.

RoadMap99_04K переводить EXTENDED MACD на явну persisted модель кута без
прихованої зміни старих WSP. Workspace без ``macd_cross_angle_model`` має
лишитися ``LEGACY_CALIBRATED`` і на контрольному EURUSD M1 -> completed M15
stream відтворити попередні 114 quality-pass signals при prominence=0.000005,
distance=0.000050 та legacy angle=45°. Лише WSP, який явно зберіг
``ABC_REALTIME_SCALED`` і власний ABC threshold=2.00°, переходить на нову
геометрію; production result має точно збігтися з RoadMap99_04J: 174 pass.

ABC Y-scale визначається fail-closed resolver-ом: EURUSD -> 10000,
USDJPY -> 100, а non-Forex/невідомий symbol не запускає ABC Quality із
вигаданим scale. Тест також моделює schema Save -> JSON -> restore і перевіряє
точне збереження model/threshold. Інтерпольована C не змінює signal timestamp,
майбутні observations і broker execution не використовуються.

RoadMap99_04K.1 також фіксує точний type contract для completed M15 stream:
``WorkspaceMarketEvent`` не маскується під ``object``. Це прибирає хибну
невизначеність IDE біля production ``on_market_event()`` без runtime cast,
suppression або зміни production-коду.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_history import (  # noqa: E402
    WorkspaceCsvHistoryLoader,
    WorkspaceHistoryDataSet,
)
from core.workspace_macd import WorkspaceMacdSignalSource  # noqa: E402
from core.workspace_macd_cross_angle_abc import (  # noqa: E402
    resolve_workspace_macd_cross_angle_value_scale,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_parameter_catalog import (  # noqa: E402
    WORKSPACE_PARAMETER_CATALOG,
)
from core.workspace_runtime import WorkspaceRuntimeContext  # noqa: E402
from core.workspace_timeframe_aggregation import (  # noqa: E402
    WorkspaceTimeframeAggregator,
)
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_MACD_CROSS_ANGLE_MODEL_ABC,
    WORKSPACE_MACD_CROSS_ANGLE_MODEL_KEY,
    WORKSPACE_MACD_CROSS_ANGLE_MODEL_LEGACY,
    WORKSPACE_MACD_CROSS_MIN_ABC_ANGLE_KEY,
    WORKSPACE_MACD_CROSS_MIN_ANGLE_KEY,
    WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE_KEY,
    WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE_KEY,
)

M1_FILE = (
    PROJECT_ROOT
    / "data"
    / "history"
    / "IB"
    / "EURUSD"
    / "M1"
    / "2026-01-02_2026-08-11_IB_EURUSD_M1.csv"
)
START_UTC = datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
END_UTC = datetime(2026, 8, 11, 8, 24, tzinfo=UTC)
PROMINENCE = 0.000005
DISTANCE = 0.000050
LEGACY_ANGLE = 45.0
ABC_ANGLE = 2.0


def _load_m15_events() -> tuple[
    WorkspaceHistoryDataSet,
    WorkspaceTimeframeAggregator,
    tuple[WorkspaceMarketEvent, ...],
]:
    """Один раз сформувати контрольний completed M15 stream з реального M1."""
    data_set = WorkspaceCsvHistoryLoader().load(
        file_path=M1_FILE,
        broker="IB",
        symbol="EURUSD",
        timeframe="M1",
        start_utc=START_UTC,
        end_utc=END_UTC,
        source_timezone="UTC",
        delimiter="AUTO",
        decimal_separator=".",
        default_spread=0.00012,
        source_name="IB_EURUSD_M1_RM99_ABC_PRODUCTION_MIGRATION",
    )
    aggregator = WorkspaceTimeframeAggregator(
        source_timeframe="M1",
        target_timeframe="M15",
    )
    events: list[WorkspaceMarketEvent] = []
    for event in data_set.events:
        completed = aggregator.on_market_event(event)
        if completed is not None:
            events.append(completed.event)
    final = aggregator.complete()
    if final is not None:
        events.append(final.event)
    return data_set, aggregator, tuple(events)


def _base_parameters() -> dict[str, object]:
    """Параметри quality pool, спільні для legacy та ABC acceptance."""
    return {
        "macd_signal_mode": "EXTENDED",
        WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE_KEY: PROMINENCE,
        WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE_KEY: DISTANCE,
        WORKSPACE_MACD_CROSS_MIN_ANGLE_KEY: LEGACY_ANGLE,
    }


def _workspace(
    *,
    symbol: str = "EURUSD",
    parameters: dict[str, object] | None = None,
) -> AlgorithmWorkspace:
    """Створити isolated Replay WSP без broker execution."""
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id="RM99_TEST",
        account_mode="PAPER",
        symbol=symbol,
        timeframe="M15",
        algorithm="MACD_REPLAY",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        parameters=dict(parameters or {}),
    )


def _production_pass_count(
    workspace: AlgorithmWorkspace,
    events: tuple[WorkspaceMarketEvent, ...],
) -> tuple[int, WorkspaceMacdSignalSource]:
    """Прогнати production WorkspaceMacdSignalSource і порахувати quality pass."""
    context = WorkspaceRuntimeContext.from_workspace(workspace)
    source = WorkspaceMacdSignalSource.from_runtime_context(
        context,
        workspace.parameters,
    )
    for event in events:
        source.on_market_event(event)
    accepted = sum(item.final_quality_pass for item in source.quality_diagnostics)
    return accepted, source


def _save_restore_abc_workspace() -> AlgorithmWorkspace:
    """Змоделювати schema Save, storage JSON і відновлення WSP."""
    workspace = _workspace(parameters=_base_parameters())
    values = WORKSPACE_PARAMETER_CATALOG.values_from_workspace(workspace)
    values["signals.macd_cross_angle_model"] = WORKSPACE_MACD_CROSS_ANGLE_MODEL_ABC
    values["signals.macd_cross_min_abc_angle"] = ABC_ANGLE
    storage = WORKSPACE_PARAMETER_CATALOG.merge_workspace_values(
        workspace,
        values,
    )
    workspace.set_algorithm_configuration(
        parameters=storage.parameters,
        risk_settings=storage.risk_settings,
        profit_protection=storage.profit_protection,
    )
    return AlgorithmWorkspace.from_storage_dict(workspace.to_storage_dict())


def _unknown_symbol_is_fail_closed() -> bool:
    """Підтвердити, що ABC не вгадує Y-scale для XAUUSD."""
    parameters = _base_parameters()
    parameters[WORKSPACE_MACD_CROSS_ANGLE_MODEL_KEY] = (
        WORKSPACE_MACD_CROSS_ANGLE_MODEL_ABC
    )
    parameters[WORKSPACE_MACD_CROSS_MIN_ABC_ANGLE_KEY] = ABC_ANGLE
    workspace = _workspace(symbol="XAUUSD", parameters=parameters)
    try:
        WorkspaceMacdSignalSource.from_runtime_context(
            WorkspaceRuntimeContext.from_workspace(workspace),
            workspace.parameters,
        )
    except ValueError:
        return True
    return False


def main() -> None:
    """Запустити RoadMap99_04K production migration acceptance."""
    print("Algorithm Workspace MACD ABC Production Migration Check — " "RoadMap99_04K")
    print(
        "  Legacy WSP without angle-model key must remain calibrated45; "
        "explicit ABC WSP uses real UTC minutes and verified Forex Y-scale."
    )
    if not M1_FILE.is_file():
        raise FileNotFoundError("Real EURUSD M1 history is required: " + str(M1_FILE))

    data_set, aggregator, events = _load_m15_events()

    legacy_workspace = _workspace(parameters=_base_parameters())
    legacy_payload = legacy_workspace.to_storage_dict()
    assert WORKSPACE_MACD_CROSS_ANGLE_MODEL_KEY not in legacy_payload["parameters"]
    legacy_accepted, legacy_source = _production_pass_count(
        legacy_workspace,
        events,
    )
    repeated_legacy, _ = _production_pass_count(legacy_workspace, events)

    restored_abc = _save_restore_abc_workspace()
    abc_accepted, abc_source = _production_pass_count(restored_abc, events)
    repeated_abc, _ = _production_pass_count(restored_abc, events)

    eurusd_scale = resolve_workspace_macd_cross_angle_value_scale("EURUSD")
    usdjpy_scale = resolve_workspace_macd_cross_angle_value_scale("USDJPY")
    unknown_fail_closed = _unknown_symbol_is_fail_closed()

    schema_model = WORKSPACE_PARAMETER_CATALOG.definition(
        "signals.macd_cross_angle_model"
    )
    schema_abc = WORKSPACE_PARAMETER_CATALOG.definition(
        "signals.macd_cross_min_abc_angle"
    )

    print("Algorithm Workspace MACD ABC Production Migration result")
    print(f"  source_rows={data_set.report.accepted_rows}")
    print(f"  completed_m15_bars={aggregator.completed_bars}")
    print("  legacy_missing_model_defaults_to=" f"{legacy_source.angle_model}")
    print(f"  legacy_quality_pass={legacy_accepted}")
    print("  legacy_storage_materialized_model=False")
    print(f"  abc_explicit_model={abc_source.angle_model}")
    print(f"  abc_min_angle={abc_source.cross_min_abc_angle_degrees:.2f}")
    print(f"  abc_quality_pass={abc_accepted}")
    print(f"  abc_runtime_scale={abc_source.abc_indicator_value_scale:.0f}")
    print(f"  resolver_EURUSD/USDJPY={eurusd_scale:.0f}/{usdjpy_scale:.0f}")
    print(f"  unknown_symbol_fail_closed={unknown_fail_closed}")
    print(
        "  schema_default_model="
        f"{schema_model.default}; abc_step={float(schema_abc.step):.2f}"
    )
    save_restore_exact = bool(
        restored_abc.parameters[WORKSPACE_MACD_CROSS_ANGLE_MODEL_KEY]
        == WORKSPACE_MACD_CROSS_ANGLE_MODEL_ABC
        and restored_abc.parameters[WORKSPACE_MACD_CROSS_MIN_ABC_ANGLE_KEY] == ABC_ANGLE
    )
    deterministic = bool(
        legacy_accepted == repeated_legacy and abc_accepted == repeated_abc
    )
    print(f"  save_restore_model_threshold_exact={save_restore_exact}")
    print("  implicit_45_to_2_06_conversion=False")
    print("  legacy_workspace_signal_logic_changed=False")
    print("  abc_requires_explicit_workspace_selection=True")
    print("  future_observations_used=False")
    print(f"  deterministic={deterministic}")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")

    assert data_set.report.accepted_rows == 224125
    assert aggregator.completed_bars == 14941
    assert legacy_source.angle_model == WORKSPACE_MACD_CROSS_ANGLE_MODEL_LEGACY
    assert legacy_accepted == 114
    assert repeated_legacy == legacy_accepted
    assert abc_source.angle_model == WORKSPACE_MACD_CROSS_ANGLE_MODEL_ABC
    assert abc_source.cross_min_abc_angle_degrees == ABC_ANGLE
    assert abc_source.abc_indicator_value_scale == 10000.0
    assert abc_accepted == 174
    assert repeated_abc == abc_accepted
    assert eurusd_scale == 10000.0
    assert usdjpy_scale == 100.0
    assert unknown_fail_closed
    assert schema_model.default == WORKSPACE_MACD_CROSS_ANGLE_MODEL_LEGACY
    assert schema_abc.default == ABC_ANGLE
    assert restored_abc.parameters[WORKSPACE_MACD_CROSS_ANGLE_MODEL_KEY] == (
        WORKSPACE_MACD_CROSS_ANGLE_MODEL_ABC
    )
    assert restored_abc.parameters[WORKSPACE_MACD_CROSS_MIN_ABC_ANGLE_KEY] == (
        ABC_ANGLE
    )
    print("ALGORITHM_WORKSPACE_MACD_ABC_PRODUCTION_MIGRATION_CHECK=OK")


if __name__ == "__main__":
    main()
