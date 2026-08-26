# -*- coding: utf-8 -*-
"""Декларативний каталог параметрів WSP.

Каталог описує групи, persisted storage, типи, обмеження та переклади.
Designer UI і матриця edition-to-feature залишаються окремими шарами.
"""

from __future__ import annotations

from core.workspace_parameter_schema import (
    WORKSPACE_PARAMETER_EDITABLE_STATE_RESTORED,
    WORKSPACE_PARAMETER_EDITABLE_STATE_STOPPED,
    WORKSPACE_PARAMETER_FEATURE_RISK_MANAGEMENT,
    WORKSPACE_PARAMETER_FEATURE_SIGNAL_FILTERS,
    WORKSPACE_PARAMETER_FEATURE_SIGNAL_SOURCES,
    WORKSPACE_PARAMETER_GROUP_ALGORITHM,
    WORKSPACE_PARAMETER_GROUP_DATA_REPLAY,
    WORKSPACE_PARAMETER_GROUP_DIAGNOSTICS,
    WORKSPACE_PARAMETER_GROUP_EXECUTION,
    WORKSPACE_PARAMETER_GROUP_FILTERS,
    WORKSPACE_PARAMETER_GROUP_RISK_MANAGEMENT,
    WORKSPACE_PARAMETER_GROUP_SIGNALS,
    WORKSPACE_PARAMETER_STORAGE_PARAMETERS,
    WORKSPACE_PARAMETER_STORAGE_PROFIT_PROTECTION,
    WORKSPACE_PARAMETER_STORAGE_RISK_SETTINGS,
    WORKSPACE_PARAMETER_TYPE_BOOLEAN,
    WORKSPACE_PARAMETER_TYPE_CHOICE,
    WORKSPACE_PARAMETER_TYPE_FLOAT,
    WORKSPACE_PARAMETER_TYPE_INTEGER,
    WorkspaceParameterCatalog,
    WorkspaceParameterDefinition,
    WorkspaceParameterGroupDefinition,
    WorkspaceParameterTranslation,
)
from engine.risk.constants import (
    DEFAULT_WORKSPACE_MAX_DAILY_LOSS_PERCENT,
    DEFAULT_WORKSPACE_MAXIMUM_OPEN_POSITIONS,
    DEFAULT_WORKSPACE_MAXIMUM_POSITION_VOLUME,
    DEFAULT_WORKSPACE_REQUIRE_STOP_LOSS,
    DEFAULT_WORKSPACE_RISK_PERCENT,
    WORKSPACE_RISK_SETTING_MAX_DAILY_LOSS_PERCENT,
    WORKSPACE_RISK_SETTING_MAXIMUM_OPEN_POSITIONS,
    WORKSPACE_RISK_SETTING_MAXIMUM_POSITION_VOLUME,
    WORKSPACE_RISK_SETTING_REQUIRE_STOP_LOSS,
    WORKSPACE_RISK_SETTING_RISK_PERCENT,
)
from engine.runtime_constants import (
    DEFAULT_WORKSPACE_ALLIGATOR_CONFIRMATION,
    DEFAULT_WORKSPACE_ALLIGATOR_FILTER_ENABLED,
    DEFAULT_WORKSPACE_MACD_CROSS_ANGLE_MODEL,
    DEFAULT_WORKSPACE_MACD_CROSS_MIN_ABC_ANGLE,
    DEFAULT_WORKSPACE_MACD_CROSS_MIN_ANGLE,
    DEFAULT_WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE,
    DEFAULT_WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE,
    DEFAULT_WORKSPACE_MACD_SIGNAL_ENABLED,
    DEFAULT_WORKSPACE_MACD_SIGNAL_MODE,
    DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT,
    WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED,
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
    WORKSPACE_ALLIGATOR_CONFIRMATION_UI_CHOICES,
    WORKSPACE_ALLIGATOR_FILTER_ENABLED_KEY,
    WORKSPACE_MACD_CROSS_ANGLE_MODEL_KEY,
    WORKSPACE_MACD_CROSS_ANGLE_MODELS,
    WORKSPACE_MACD_CROSS_MIN_ABC_ANGLE_KEY,
    WORKSPACE_MACD_CROSS_MIN_ANGLE_KEY,
    WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE_KEY,
    WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE_KEY,
    WORKSPACE_MACD_SIGNAL_ENABLED_KEY,
    WORKSPACE_MACD_SIGNAL_MODES,
)


def build_workspace_parameter_catalog() -> WorkspaceParameterCatalog:
    """Побудувати схему перших signal, filter і risk settings WSP."""
    inactive_states = (
        WORKSPACE_PARAMETER_EDITABLE_STATE_STOPPED,
        WORKSPACE_PARAMETER_EDITABLE_STATE_RESTORED,
    )
    groups = (
        _group(
            WORKSPACE_PARAMETER_GROUP_DATA_REPLAY,
            10,
            "dataReplay",
            "Data and Replay",
            "Historical sources, Replay environment and market-data settings.",
        ),
        _group(
            WORKSPACE_PARAMETER_GROUP_ALGORITHM,
            20,
            "algorithm",
            "Algorithm",
            "Algorithm-specific detection and confirmation settings.",
        ),
        _group(
            WORKSPACE_PARAMETER_GROUP_SIGNALS,
            30,
            "signals",
            "Signals",
            "Independent signal sources added one by one during testing.",
        ),
        _group(
            WORKSPACE_PARAMETER_GROUP_FILTERS,
            35,
            "filters",
            "Filters and confirmations",
            "Independent filters and confirmations added one by one during testing.",
        ),
        _group(
            WORKSPACE_PARAMETER_GROUP_RISK_MANAGEMENT,
            40,
            "riskManagement",
            "Risk management",
            "Limits applied before any broker execution is permitted.",
        ),
        _group(
            WORKSPACE_PARAMETER_GROUP_EXECUTION,
            50,
            "execution",
            "Execution",
            "Paper and Live execution settings reserved for later RoadMaps.",
        ),
        _group(
            WORKSPACE_PARAMETER_GROUP_DIAGNOSTICS,
            60,
            "diagnostics",
            "Diagnostics and chart",
            "Journal, chart overlays and runtime diagnostic settings.",
        ),
    )
    parameters = (
        WorkspaceParameterDefinition(
            key="signals.macd_enabled",
            storage_section=WORKSPACE_PARAMETER_STORAGE_PARAMETERS,
            storage_key=WORKSPACE_MACD_SIGNAL_ENABLED_KEY,
            group_code=WORKSPACE_PARAMETER_GROUP_SIGNALS,
            order=10,
            value_type=WORKSPACE_PARAMETER_TYPE_BOOLEAN,
            default=DEFAULT_WORKSPACE_MACD_SIGNAL_ENABLED,
            title=_parameter_translation(
                "macdEnabled",
                "title",
                "Enable MACD signal source",
            ),
            description=_parameter_translation(
                "macdEnabled",
                "description",
                "Enable MACD as one independent source of WSP signals.",
            ),
            feature_code=WORKSPACE_PARAMETER_FEATURE_SIGNAL_SOURCES,
            editable_runtime_states=inactive_states,
        ),
        WorkspaceParameterDefinition(
            key="signals.macd_signal_mode",
            storage_section=WORKSPACE_PARAMETER_STORAGE_PARAMETERS,
            storage_key="macd_signal_mode",
            group_code=WORKSPACE_PARAMETER_GROUP_SIGNALS,
            order=20,
            value_type=WORKSPACE_PARAMETER_TYPE_CHOICE,
            default=DEFAULT_WORKSPACE_MACD_SIGNAL_MODE,
            title=_parameter_translation(
                "macdSignalMode",
                "title",
                "MACD signal mode",
            ),
            description=_parameter_translation(
                "macdSignalMode",
                "description",
                "Select how the independent MACD signal source forms a signal.",
            ),
            feature_code=WORKSPACE_PARAMETER_FEATURE_SIGNAL_SOURCES,
            editable_runtime_states=inactive_states,
            allowed_values=WORKSPACE_MACD_SIGNAL_MODES,
            allowed_value_labels=(
                WorkspaceParameterTranslation(
                    "AlgorithmWorkspaceParametersDialog.macdLinear",
                    "Linear",
                ),
                WorkspaceParameterTranslation(
                    "AlgorithmWorkspaceParametersDialog.macdExtended",
                    "Extended",
                ),
            ),
        ),
        WorkspaceParameterDefinition(
            key="signals.macd_extremum_min_prominence",
            storage_section=WORKSPACE_PARAMETER_STORAGE_PARAMETERS,
            storage_key=WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE_KEY,
            group_code=WORKSPACE_PARAMETER_GROUP_SIGNALS,
            order=30,
            value_type=WORKSPACE_PARAMETER_TYPE_FLOAT,
            default=DEFAULT_WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE,
            title=_parameter_translation(
                "macdExtremumMinProminence",
                "title",
                "MACD extremum minimum prominence",
            ),
            description=_parameter_translation(
                "macdExtremumMinProminence",
                "description",
                "Minimum local histogram extremum prominence in EXTENDED mode.",
            ),
            feature_code=WORKSPACE_PARAMETER_FEATURE_SIGNAL_SOURCES,
            editable_runtime_states=inactive_states,
            minimum=0.0,
            maximum=0.01,
            step=0.000001,
        ),
        WorkspaceParameterDefinition(
            key="signals.macd_extremum_to_cross_min_distance",
            storage_section=WORKSPACE_PARAMETER_STORAGE_PARAMETERS,
            storage_key=WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE_KEY,
            group_code=WORKSPACE_PARAMETER_GROUP_SIGNALS,
            order=40,
            value_type=WORKSPACE_PARAMETER_TYPE_FLOAT,
            default=DEFAULT_WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE,
            title=_parameter_translation(
                "macdExtremumToCrossMinDistance",
                "title",
                "MACD extremum to cross minimum distance",
            ),
            description=_parameter_translation(
                "macdExtremumToCrossMinDistance",
                "description",
                "Minimum absolute histogram distance from extremum to crossover.",
            ),
            feature_code=WORKSPACE_PARAMETER_FEATURE_SIGNAL_SOURCES,
            editable_runtime_states=inactive_states,
            minimum=0.0,
            maximum=0.01,
            step=0.000001,
        ),
        WorkspaceParameterDefinition(
            key="signals.macd_cross_angle_model",
            storage_section=WORKSPACE_PARAMETER_STORAGE_PARAMETERS,
            storage_key=WORKSPACE_MACD_CROSS_ANGLE_MODEL_KEY,
            group_code=WORKSPACE_PARAMETER_GROUP_SIGNALS,
            order=50,
            value_type=WORKSPACE_PARAMETER_TYPE_CHOICE,
            default=DEFAULT_WORKSPACE_MACD_CROSS_ANGLE_MODEL,
            title=_parameter_translation(
                "macdCrossAngleModel",
                "title",
                "MACD crossover angle model",
            ),
            description=_parameter_translation(
                "macdCrossAngleModel",
                "description",
                "Select legacy calibrated or ABC real-time scaled angle.",
            ),
            feature_code=WORKSPACE_PARAMETER_FEATURE_SIGNAL_SOURCES,
            editable_runtime_states=inactive_states,
            allowed_values=WORKSPACE_MACD_CROSS_ANGLE_MODELS,
            allowed_value_labels=(
                WorkspaceParameterTranslation(
                    "AlgorithmWorkspaceParametersDialog.macdAngleLegacy",
                    "Legacy calibrated",
                ),
                WorkspaceParameterTranslation(
                    "AlgorithmWorkspaceParametersDialog.macdAngleAbc",
                    "ABC, real time",
                ),
            ),
        ),
        WorkspaceParameterDefinition(
            key="signals.macd_cross_min_angle",
            storage_section=WORKSPACE_PARAMETER_STORAGE_PARAMETERS,
            storage_key=WORKSPACE_MACD_CROSS_MIN_ANGLE_KEY,
            group_code=WORKSPACE_PARAMETER_GROUP_SIGNALS,
            order=60,
            value_type=WORKSPACE_PARAMETER_TYPE_FLOAT,
            default=DEFAULT_WORKSPACE_MACD_CROSS_MIN_ANGLE,
            title=_parameter_translation(
                "macdCrossMinAngle",
                "title",
                "Legacy MACD crossover minimum angle, degrees",
            ),
            description=_parameter_translation(
                "macdCrossMinAngle",
                "description",
                "Minimum angle used only by LEGACY_CALIBRATED mode.",
            ),
            feature_code=WORKSPACE_PARAMETER_FEATURE_SIGNAL_SOURCES,
            editable_runtime_states=inactive_states,
            minimum=0.0,
            maximum=180.0,
            step=1.0,
        ),
        WorkspaceParameterDefinition(
            key="signals.macd_cross_min_abc_angle",
            storage_section=WORKSPACE_PARAMETER_STORAGE_PARAMETERS,
            storage_key=WORKSPACE_MACD_CROSS_MIN_ABC_ANGLE_KEY,
            group_code=WORKSPACE_PARAMETER_GROUP_SIGNALS,
            order=70,
            value_type=WORKSPACE_PARAMETER_TYPE_FLOAT,
            default=DEFAULT_WORKSPACE_MACD_CROSS_MIN_ABC_ANGLE,
            title=_parameter_translation(
                "macdCrossMinAbcAngle",
                "title",
                "ABC MACD crossover minimum angle, degrees",
            ),
            description=_parameter_translation(
                "macdCrossMinAbcAngle",
                "description",
                "Minimum angle used only by ABC_REALTIME_SCALED mode.",
            ),
            feature_code=WORKSPACE_PARAMETER_FEATURE_SIGNAL_SOURCES,
            editable_runtime_states=inactive_states,
            minimum=0.0,
            maximum=180.0,
            step=0.01,
        ),
        WorkspaceParameterDefinition(
            key="filters.alligator_enabled",
            storage_section=WORKSPACE_PARAMETER_STORAGE_PARAMETERS,
            storage_key=WORKSPACE_ALLIGATOR_FILTER_ENABLED_KEY,
            group_code=WORKSPACE_PARAMETER_GROUP_FILTERS,
            order=10,
            value_type=WORKSPACE_PARAMETER_TYPE_BOOLEAN,
            default=DEFAULT_WORKSPACE_ALLIGATOR_FILTER_ENABLED,
            title=_parameter_translation(
                "alligatorEnabled",
                "title",
                "Enable Alligator filter",
            ),
            description=_parameter_translation(
                "alligatorEnabled",
                "description",
                "Enable Alligator as one independent signal filter.",
            ),
            feature_code=WORKSPACE_PARAMETER_FEATURE_SIGNAL_FILTERS,
            editable_runtime_states=inactive_states,
        ),
        WorkspaceParameterDefinition(
            key="filters.alligator_confirmation",
            storage_section=WORKSPACE_PARAMETER_STORAGE_PARAMETERS,
            storage_key="alligator_confirmation",
            group_code=WORKSPACE_PARAMETER_GROUP_FILTERS,
            order=20,
            value_type=WORKSPACE_PARAMETER_TYPE_CHOICE,
            default=DEFAULT_WORKSPACE_ALLIGATOR_CONFIRMATION,
            title=_parameter_translation(
                "alligatorConfirmation",
                "title",
                "Alligator confirmation mode",
            ),
            description=_parameter_translation(
                "alligatorConfirmation",
                "description",
                "Select the timeframe used by the independent Alligator filter.",
            ),
            feature_code=WORKSPACE_PARAMETER_FEATURE_SIGNAL_FILTERS,
            editable_runtime_states=inactive_states,
            allowed_values=WORKSPACE_ALLIGATOR_CONFIRMATION_UI_CHOICES,
            allowed_value_labels=(
                WorkspaceParameterTranslation(
                    "AlgorithmWorkspaceParametersDialog.alligatorSameTimeframe",
                    "Same timeframe",
                ),
                WorkspaceParameterTranslation(
                    "AlgorithmWorkspaceParametersDialog.alligatorHigher1",
                    "One timeframe higher",
                ),
                WorkspaceParameterTranslation(
                    "AlgorithmWorkspaceParametersDialog.alligatorHigher2",
                    "Two timeframes higher",
                ),
            ),
            legacy_choice_aliases=((
                WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED,
                WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
            ),),
        ),
        _risk_float_parameter(
            key="risk.risk_percent",
            storage_key=WORKSPACE_RISK_SETTING_RISK_PERCENT,
            order=10,
            name="riskPercent",
            default=DEFAULT_WORKSPACE_RISK_PERCENT,
            minimum=0.01,
            maximum=100.0,
            step=0.01,
            title="Risk per trade, %",
            description=(
                "Maximum estimated loss of one trade as a percentage of "
                "account equity."
            ),
            editable_runtime_states=inactive_states,
        ),
        _risk_float_parameter(
            key="risk.maximum_position_volume",
            storage_key=WORKSPACE_RISK_SETTING_MAXIMUM_POSITION_VOLUME,
            order=20,
            name="maximumPositionVolume",
            default=DEFAULT_WORKSPACE_MAXIMUM_POSITION_VOLUME,
            minimum=0.01,
            maximum=None,
            step=1.0,
            title="Maximum position volume",
            description=(
                "Hard upper limit for the volume requested by one WSP signal."
            ),
            editable_runtime_states=inactive_states,
        ),
        _risk_integer_parameter(
            key="risk.maximum_open_positions",
            storage_key=WORKSPACE_RISK_SETTING_MAXIMUM_OPEN_POSITIONS,
            order=30,
            name="maximumOpenPositions",
            default=DEFAULT_WORKSPACE_MAXIMUM_OPEN_POSITIONS,
            minimum=1,
            maximum=None,
            step=1,
            title="Maximum open positions",
            description=(
                "Maximum number of positions allowed by this WSP risk policy."
            ),
            editable_runtime_states=inactive_states,
        ),
        _risk_float_parameter(
            key="risk.max_daily_loss_percent",
            storage_key=WORKSPACE_RISK_SETTING_MAX_DAILY_LOSS_PERCENT,
            order=40,
            name="maximumDailyLossPercent",
            default=DEFAULT_WORKSPACE_MAX_DAILY_LOSS_PERCENT,
            minimum=0.01,
            maximum=100.0,
            step=0.01,
            title="Maximum daily loss, %",
            description=(
                "Blocks new signals after the configured daily loss limit "
                "is reached."
            ),
            editable_runtime_states=inactive_states,
        ),
        WorkspaceParameterDefinition(
            key="risk.require_stop_loss",
            storage_section=WORKSPACE_PARAMETER_STORAGE_RISK_SETTINGS,
            storage_key=WORKSPACE_RISK_SETTING_REQUIRE_STOP_LOSS,
            group_code=WORKSPACE_PARAMETER_GROUP_RISK_MANAGEMENT,
            order=50,
            value_type=WORKSPACE_PARAMETER_TYPE_BOOLEAN,
            default=DEFAULT_WORKSPACE_REQUIRE_STOP_LOSS,
            title=_parameter_translation(
                "requireStopLoss",
                "title",
                "Require Stop Loss",
            ),
            description=_parameter_translation(
                "requireStopLoss",
                "description",
                "Reject every trade intent that has no Stop Loss.",
            ),
            feature_code=WORKSPACE_PARAMETER_FEATURE_RISK_MANAGEMENT,
            editable_runtime_states=inactive_states,
        ),
        WorkspaceParameterDefinition(
            key="risk.profit_drawdown_close_percent",
            storage_section=WORKSPACE_PARAMETER_STORAGE_PROFIT_PROTECTION,
            storage_key="max_profit_drawdown_percent",
            group_code=WORKSPACE_PARAMETER_GROUP_RISK_MANAGEMENT,
            order=60,
            value_type=WORKSPACE_PARAMETER_TYPE_FLOAT,
            default=DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT,
            title=_parameter_translation(
                "profitDrawdownClosePercent",
                "title",
                "Profit drawdown close, %",
            ),
            description=_parameter_translation(
                "profitDrawdownClosePercent",
                "description",
                "Local close decision after the configured profit drawdown.",
            ),
            feature_code=WORKSPACE_PARAMETER_FEATURE_RISK_MANAGEMENT,
            editable_runtime_states=inactive_states,
            minimum=1.0,
            maximum=100.0,
            step=1.0,
        ),
    )
    return WorkspaceParameterCatalog(groups=groups, parameters=parameters)


def _group(
    code: str,
    order: int,
    name: str,
    title: str,
    description: str,
) -> WorkspaceParameterGroupDefinition:
    return WorkspaceParameterGroupDefinition(
        code=code,
        order=order,
        title=WorkspaceParameterTranslation(
            f"WorkspaceParameterGroup.{name}.title",
            title,
        ),
        description=WorkspaceParameterTranslation(
            f"WorkspaceParameterGroup.{name}.description",
            description,
        ),
    )


def _risk_float_parameter(
    *,
    key: str,
    storage_key: str,
    order: int,
    name: str,
    default: float,
    minimum: float | None,
    maximum: float | None,
    step: float,
    title: str,
    description: str,
    editable_runtime_states: tuple[str, ...],
) -> WorkspaceParameterDefinition:
    return WorkspaceParameterDefinition(
        key=key,
        storage_section=WORKSPACE_PARAMETER_STORAGE_RISK_SETTINGS,
        storage_key=storage_key,
        group_code=WORKSPACE_PARAMETER_GROUP_RISK_MANAGEMENT,
        order=order,
        value_type=WORKSPACE_PARAMETER_TYPE_FLOAT,
        default=default,
        title=_parameter_translation(name, "title", title),
        description=_parameter_translation(
            name,
            "description",
            description,
        ),
        feature_code=WORKSPACE_PARAMETER_FEATURE_RISK_MANAGEMENT,
        editable_runtime_states=editable_runtime_states,
        minimum=minimum,
        maximum=maximum,
        step=step,
    )


def _risk_integer_parameter(
    *,
    key: str,
    storage_key: str,
    order: int,
    name: str,
    default: int,
    minimum: int | None,
    maximum: int | None,
    step: int,
    title: str,
    description: str,
    editable_runtime_states: tuple[str, ...],
) -> WorkspaceParameterDefinition:
    return WorkspaceParameterDefinition(
        key=key,
        storage_section=WORKSPACE_PARAMETER_STORAGE_RISK_SETTINGS,
        storage_key=storage_key,
        group_code=WORKSPACE_PARAMETER_GROUP_RISK_MANAGEMENT,
        order=order,
        value_type=WORKSPACE_PARAMETER_TYPE_INTEGER,
        default=default,
        title=_parameter_translation(name, "title", title),
        description=_parameter_translation(
            name,
            "description",
            description,
        ),
        feature_code=WORKSPACE_PARAMETER_FEATURE_RISK_MANAGEMENT,
        editable_runtime_states=editable_runtime_states,
        minimum=minimum,
        maximum=maximum,
        step=step,
    )


def _parameter_translation(
    name: str,
    field: str,
    fallback: str,
) -> WorkspaceParameterTranslation:
    return WorkspaceParameterTranslation(
        f"WorkspaceParameter.{name}.{field}",
        fallback,
    )


WORKSPACE_PARAMETER_CATALOG = build_workspace_parameter_catalog()
