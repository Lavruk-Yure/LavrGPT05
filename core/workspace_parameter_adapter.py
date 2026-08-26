# -*- coding: utf-8 -*-
"""Міст між схемою параметрів і чинною моделлю параметрів WSP.

Адаптер дозволяє наявному діалогу й далі використовувати
WorkspaceAlgorithmParameters, тоді як schema-owned значення читаються та
об'єднуються через WorkspaceParameterCatalog. Невідомі та future storage keys
лишаються без змін.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from core.workspace_parameter_catalog import WORKSPACE_PARAMETER_CATALOG
from core.workspace_parameter_schema import (
    WORKSPACE_PARAMETER_STORAGE_PARAMETERS,
    WORKSPACE_PARAMETER_STORAGE_PROFIT_PROTECTION,
    WORKSPACE_PARAMETER_STORAGE_RISK_SETTINGS,
    WorkspaceParameterCatalog,
    WorkspaceParameterSchemaError,
    WorkspaceParameterStorageUpdate,
)
from core.workspace_parameters import WorkspaceAlgorithmParameters
from engine.risk.constants import (
    WORKSPACE_RISK_SETTING_MAXIMUM_POSITION_VOLUME,
    WORKSPACE_RISK_SETTING_RISK_PERCENT,
)


@dataclass(frozen=True, slots=True)
class _WorkspaceParameterStorageView:
    """Storage view у форматі AlgorithmWorkspace для конвертації legacy-моделі."""

    parameters: dict[str, object]
    risk_settings: dict[str, object]
    profit_protection: dict[str, object]


@dataclass(frozen=True, slots=True)
class WorkspaceAlgorithmParameterAdapter:
    """Синхронізувати legacy-модель параметрів із новою схемою."""

    catalog: WorkspaceParameterCatalog

    @staticmethod
    def legacy_values_from_workspace(
        workspace: object,
    ) -> WorkspaceAlgorithmParameters:
        """Прочитати значення, потрібні чинному діалогу параметрів."""
        return WorkspaceAlgorithmParameters.from_workspace(workspace)

    def schema_values_from_workspace(
        self,
        workspace: object,
    ) -> dict[str, object]:
        """Прочитати всі значення, якими вже керує декларативна схема."""
        return self.catalog.values_from_workspace(workspace)

    def schema_updates_from_legacy(
        self,
        values: WorkspaceAlgorithmParameters,
    ) -> dict[str, object]:
        """Зіставити legacy-поля, які вже представлені у схемі."""
        return {
            self._schema_key(
                WORKSPACE_PARAMETER_STORAGE_PARAMETERS,
                "macd_signal_mode",
            ): values.macd_signal_mode,
            self._schema_key(
                WORKSPACE_PARAMETER_STORAGE_PARAMETERS,
                "alligator_confirmation",
            ): values.alligator_confirmation,
            self._schema_key(
                WORKSPACE_PARAMETER_STORAGE_RISK_SETTINGS,
                WORKSPACE_RISK_SETTING_RISK_PERCENT,
            ): values.risk_percent,
            self._schema_key(
                WORKSPACE_PARAMETER_STORAGE_RISK_SETTINGS,
                WORKSPACE_RISK_SETTING_MAXIMUM_POSITION_VOLUME,
            ): values.maximum_position_volume,
            self._schema_key(
                WORKSPACE_PARAMETER_STORAGE_PROFIT_PROTECTION,
                "max_profit_drawdown_percent",
            ): values.profit_drawdown_close_percent,
        }

    def merge_legacy_values(
        self,
        workspace: object,
        values: WorkspaceAlgorithmParameters,
    ) -> WorkspaceParameterStorageUpdate:
        """Об'єднати модель чинного діалогу без втрати schema/future keys."""
        schema_storage = self.catalog.merge_workspace_values(
            workspace,
            self.schema_updates_from_legacy(values),
        )
        return WorkspaceParameterStorageUpdate(
            parameters=values.merge_parameters(schema_storage.parameters),
            risk_settings=schema_storage.risk_settings,
            profit_protection=schema_storage.profit_protection,
            replay_settings=schema_storage.replay_settings,
        )

    def merge_dialog_values(
        self,
        workspace: object,
        values: WorkspaceAlgorithmParameters,
        schema_updates: Mapping[str, object],
    ) -> WorkspaceParameterStorageUpdate:
        """Об'єднати єдиний редактор без втрати legacy та future keys."""
        schema_storage = self.catalog.merge_workspace_values(
            workspace,
            schema_updates,
        )
        return WorkspaceParameterStorageUpdate(
            parameters=values.merge_parameters(schema_storage.parameters),
            risk_settings=schema_storage.risk_settings,
            profit_protection=schema_storage.profit_protection,
            replay_settings=schema_storage.replay_settings,
        )

    def legacy_values_after_schema_updates(
        self,
        workspace: object,
        updates: Mapping[str, object],
    ) -> WorkspaceAlgorithmParameters:
        """Спроєктувати майбутні зміни дерева назад у модель чинного діалогу."""
        storage = self.catalog.merge_workspace_values(workspace, updates)
        view = _WorkspaceParameterStorageView(
            parameters=storage.parameters,
            risk_settings=storage.risk_settings,
            profit_protection=storage.profit_protection,
        )
        return WorkspaceAlgorithmParameters.from_workspace(view)

    def _schema_key(self, storage_section: str, storage_key: str) -> str:
        matches = tuple(
            parameter.key
            for parameter in self.catalog.parameters
            if parameter.storage_section == storage_section
            and parameter.storage_key == storage_key
        )
        if len(matches) != 1:
            address = f"{storage_section}.{storage_key}"
            raise WorkspaceParameterSchemaError(
                f"schema storage address must be unique: {address}"
            )
        return matches[0]


WORKSPACE_ALGORITHM_PARAMETER_ADAPTER = WorkspaceAlgorithmParameterAdapter(
    catalog=WORKSPACE_PARAMETER_CATALOG
)
