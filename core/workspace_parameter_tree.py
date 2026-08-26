# -*- coding: utf-8 -*-
"""UI-незалежна read-only модель дерева параметрів WSP.

Модель поєднує декларативний каталог, persisted-значення workspace,
можливості ліцензії, runtime-стан і переклади. Вона не змінює workspace та
не залежить від PySide6. Майбутній tree UI має лише відобразити готові вузли.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.workspace_parameter_catalog import WORKSPACE_PARAMETER_CATALOG
from core.workspace_parameter_schema import (
    WORKSPACE_PARAMETER_AVAILABLE_KEY,
    WORKSPACE_PARAMETER_FEATURE_REQUIRED_KEY,
    WORKSPACE_PARAMETER_LOCKED_KEY,
    WORKSPACE_PARAMETER_RUNTIME_LOCKED_KEY,
    WORKSPACE_PARAMETER_STOP_REQUIRED_KEY,
    WorkspaceParameterCatalog,
    WorkspaceParameterDefinition,
    WorkspaceParameterFeatureProfile,
    WorkspaceParameterTranslator,
)


class WorkspaceParameterTreeError(ValueError):
    """Некоректний workspace context або структура read-only дерева."""


@dataclass(frozen=True, slots=True)
class WorkspaceParameterTreeNode:
    """Один leaf-вузол параметра з готовими даними для майбутнього UI."""

    key: str
    title: str
    description: str
    value: object
    value_type: str
    feature_code: str
    available_by_license: bool
    editable_by_runtime: bool
    editable: bool
    status: str
    reason: str | None
    minimum: float | int | None
    maximum: float | int | None
    step: float | int | None
    allowed_values: tuple[str, ...]
    allowed_value_labels: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class WorkspaceParameterTreeGroup:
    """Одна локалізована верхня гілка дерева параметрів."""

    code: str
    order: int
    title: str
    description: str
    parameters: tuple[WorkspaceParameterTreeNode, ...]


@dataclass(frozen=True, slots=True)
class WorkspaceParameterTreeModel:
    """Детермінований immutable snapshot дерева параметрів одного WSP."""

    workspace_uid: str
    runtime_state: str
    edition: str
    groups: tuple[WorkspaceParameterTreeGroup, ...]

    def group(self, code: str) -> WorkspaceParameterTreeGroup:
        """Знайти групу за стабільним кодом."""
        normalized = _required_code(code, "group code")
        for group in self.groups:
            if group.code == normalized:
                return group
        raise WorkspaceParameterTreeError(
            f"unknown parameter tree group: {normalized}"
        )

    def parameter(self, key: str) -> WorkspaceParameterTreeNode:
        """Знайти параметр за стабільним schema key."""
        normalized = _required_text(key, "parameter key")
        for group in self.groups:
            for parameter in group.parameters:
                if parameter.key == normalized:
                    return parameter
        raise WorkspaceParameterTreeError(
            f"unknown parameter tree key: {normalized}"
        )


@dataclass(frozen=True, slots=True)
class WorkspaceParameterTreeBuilder:
    """Побудувати read-only дерево без зміни persisted workspace settings."""

    catalog: WorkspaceParameterCatalog

    def build(
        self,
        *,
        workspace: object,
        profile: WorkspaceParameterFeatureProfile,
        runtime_state: str,
        translator: WorkspaceParameterTranslator,
    ) -> WorkspaceParameterTreeModel:
        """Зібрати локалізований immutable snapshot параметрів WSP."""
        workspace_uid = _required_text(
            getattr(workspace, "workspace_uid", None),
            "workspace_uid",
        )
        normalized_state = _required_code(runtime_state, "runtime state")
        localized = self.catalog.register_translations(translator)
        values = self.catalog.values_from_workspace(workspace)

        groups: list[WorkspaceParameterTreeGroup] = []
        for definition in self.catalog.ordered_groups():
            parameters = tuple(
                self._parameter_node(
                    definition=parameter,
                    value=values[parameter.key],
                    profile=profile,
                    runtime_state=normalized_state,
                    localized=localized,
                )
                for parameter in self.catalog.parameters_for_group(
                    definition.code
                )
            )
            groups.append(
                WorkspaceParameterTreeGroup(
                    code=definition.code,
                    order=definition.order,
                    title=localized[definition.title.key],
                    description=localized[definition.description.key],
                    parameters=parameters,
                )
            )

        return WorkspaceParameterTreeModel(
            workspace_uid=workspace_uid,
            runtime_state=normalized_state,
            edition=profile.edition,
            groups=tuple(groups),
        )

    def _parameter_node(
        self,
        *,
        definition: WorkspaceParameterDefinition,
        value: object,
        profile: WorkspaceParameterFeatureProfile,
        runtime_state: str,
        localized: dict[str, str],
    ) -> WorkspaceParameterTreeNode:
        parameter = self.catalog.definition(definition.key)
        availability = self.catalog.availability(parameter.key, profile)
        editable_by_runtime = (
            runtime_state in parameter.editable_runtime_states
        )
        editable = availability.available and editable_by_runtime

        if not availability.available:
            status = localized[WORKSPACE_PARAMETER_LOCKED_KEY]
            reason = localized[
                WORKSPACE_PARAMETER_FEATURE_REQUIRED_KEY
            ].format(feature_code=availability.feature_code)
        elif not editable_by_runtime:
            status = localized[WORKSPACE_PARAMETER_RUNTIME_LOCKED_KEY]
            reason = localized[WORKSPACE_PARAMETER_STOP_REQUIRED_KEY]
        else:
            status = localized[WORKSPACE_PARAMETER_AVAILABLE_KEY]
            reason = None

        return WorkspaceParameterTreeNode(
            key=parameter.key,
            title=localized[parameter.title.key],
            description=localized[parameter.description.key],
            value=value,
            value_type=parameter.value_type,
            feature_code=parameter.feature_code,
            available_by_license=availability.available,
            editable_by_runtime=editable_by_runtime,
            editable=editable,
            status=status,
            reason=reason,
            minimum=parameter.minimum,
            maximum=parameter.maximum,
            step=parameter.step,
            allowed_values=parameter.allowed_values,
            allowed_value_labels=self._allowed_value_labels(
                parameter,
                localized,
            ),
        )

    @staticmethod
    def _allowed_value_labels(
        parameter: WorkspaceParameterDefinition,
        localized: dict[str, str],
    ) -> tuple[tuple[str, str], ...]:
        if not parameter.allowed_values:
            return ()
        if not parameter.allowed_value_labels:
            return tuple((value, value) for value in parameter.allowed_values)
        return tuple(
            (value, localized[label.key])
            for value, label in zip(
                parameter.allowed_values,
                parameter.allowed_value_labels,
                strict=True,
            )
        )


WORKSPACE_PARAMETER_TREE_BUILDER = WorkspaceParameterTreeBuilder(
    catalog=WORKSPACE_PARAMETER_CATALOG
)


def _required_text(value: object, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise WorkspaceParameterTreeError(f"{field_name} is required")
    return text


def _required_code(value: object, field_name: str) -> str:
    code = _required_text(value, field_name).upper()
    if any(character.isspace() for character in code):
        raise WorkspaceParameterTreeError(
            f"{field_name} cannot contain whitespace"
        )
    return code
