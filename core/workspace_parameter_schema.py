# -*- coding: utf-8 -*-
"""Декларативна схема майбутнього дерева параметрів WSP.

Схема не залежить від UI. Вона описує групи параметрів, persisted storage,
обмеження значень, ключі перекладу та вимоги до можливостей ліцензії. Чинні
WSP-діалоги працюють доти, доки їх поступово не переведуть на цю модель.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Protocol


# =============================================================================
# Групи дерева параметрів
# =============================================================================

WORKSPACE_PARAMETER_GROUP_DATA_REPLAY = "DATA_REPLAY"
WORKSPACE_PARAMETER_GROUP_ALGORITHM = "ALGORITHM"
WORKSPACE_PARAMETER_GROUP_SIGNALS = "SIGNALS"
WORKSPACE_PARAMETER_GROUP_FILTERS = "FILTERS"
WORKSPACE_PARAMETER_GROUP_RISK_MANAGEMENT = "RISK_MANAGEMENT"
WORKSPACE_PARAMETER_GROUP_EXECUTION = "EXECUTION"
WORKSPACE_PARAMETER_GROUP_DIAGNOSTICS = "DIAGNOSTICS"


# =============================================================================
# Persisted-секції AlgorithmWorkspace
# =============================================================================

WORKSPACE_PARAMETER_STORAGE_PARAMETERS = "parameters"
WORKSPACE_PARAMETER_STORAGE_RISK_SETTINGS = "risk_settings"
WORKSPACE_PARAMETER_STORAGE_PROFIT_PROTECTION = "profit_protection"
WORKSPACE_PARAMETER_STORAGE_REPLAY_SETTINGS = "replay_settings"

WORKSPACE_PARAMETER_STORAGE_SECTIONS = (
    WORKSPACE_PARAMETER_STORAGE_PARAMETERS,
    WORKSPACE_PARAMETER_STORAGE_RISK_SETTINGS,
    WORKSPACE_PARAMETER_STORAGE_PROFIT_PROTECTION,
    WORKSPACE_PARAMETER_STORAGE_REPLAY_SETTINGS,
)


# =============================================================================
# Підтримувані типи значень
# =============================================================================

WORKSPACE_PARAMETER_TYPE_FLOAT = "FLOAT"
WORKSPACE_PARAMETER_TYPE_INTEGER = "INTEGER"
WORKSPACE_PARAMETER_TYPE_BOOLEAN = "BOOLEAN"
WORKSPACE_PARAMETER_TYPE_CHOICE = "CHOICE"

WORKSPACE_PARAMETER_VALUE_TYPES = (
    WORKSPACE_PARAMETER_TYPE_FLOAT,
    WORKSPACE_PARAMETER_TYPE_INTEGER,
    WORKSPACE_PARAMETER_TYPE_BOOLEAN,
    WORKSPACE_PARAMETER_TYPE_CHOICE,
)


# =============================================================================
# Коди можливостей ліцензії
# =============================================================================

# Чинні risk settings використовують один нейтральний feature code. Матриця
# edition-to-feature лишається поза цією схемою і згодом надходитиме від
# LicenseManager.
WORKSPACE_PARAMETER_FEATURE_SIGNAL_SOURCES = "WSP_SIGNAL_SOURCES"
WORKSPACE_PARAMETER_FEATURE_SIGNAL_FILTERS = "WSP_SIGNAL_FILTERS"
WORKSPACE_PARAMETER_FEATURE_RISK_MANAGEMENT = "WSP_RISK_MANAGEMENT"

# Зарезервовано для майбутніх risk-налаштувань PRO+. До окремого погодження
# продуктової матриці чинні production-параметри до цього коду не прив'язуються.
WORKSPACE_PARAMETER_FEATURE_ADVANCED_RISK = "WSP_ADVANCED_RISK"


# =============================================================================
# Доступність редагування в Runtime і ключі перекладу
# =============================================================================

WORKSPACE_PARAMETER_EDITABLE_STATE_STOPPED = "STOPPED"
WORKSPACE_PARAMETER_EDITABLE_STATE_RESTORED = "RESTORED"

WORKSPACE_PARAMETER_AVAILABLE_KEY = "WorkspaceParameterAvailability.available"
WORKSPACE_PARAMETER_AVAILABLE_FALLBACK = "Available"
WORKSPACE_PARAMETER_LOCKED_KEY = "WorkspaceParameterAvailability.locked"
WORKSPACE_PARAMETER_LOCKED_FALLBACK = "Locked by license"
WORKSPACE_PARAMETER_FEATURE_REQUIRED_KEY = (
    "WorkspaceParameterAvailability.featureRequired"
)
WORKSPACE_PARAMETER_FEATURE_REQUIRED_FALLBACK = (
    "This parameter requires the {feature_code} feature."
)
WORKSPACE_PARAMETER_RUNTIME_LOCKED_KEY = "WorkspaceParameterAvailability.runtimeLocked"
WORKSPACE_PARAMETER_RUNTIME_LOCKED_FALLBACK = "Read-only while workspace is active"
WORKSPACE_PARAMETER_STOP_REQUIRED_KEY = "WorkspaceParameterAvailability.stopRequired"
WORKSPACE_PARAMETER_STOP_REQUIRED_FALLBACK = (
    "Stop the workspace before editing this parameter."
)


class WorkspaceParameterSchemaError(ValueError):
    """Некоректні metadata, значення або storage mapping параметра."""


class WorkspaceParameterTranslator(Protocol):
    """Мінімальний контракт перекладу, сумісний із LangManager."""

    def tr(self, key: str, fallback: str) -> str:
        """Повернути локалізований текст і зареєструвати відсутній fallback key."""


@dataclass(frozen=True, slots=True)
class WorkspaceParameterTranslation:
    """Один ключ перекладу та його канонічний англійський fallback."""

    key: str
    fallback: str

    def __post_init__(self) -> None:
        _required_text(self.key, "translation key")
        _required_text(self.fallback, "translation fallback")
        if "." not in self.key:
            raise WorkspaceParameterSchemaError(
                "translation key must contain a namespace separator"
            )


@dataclass(frozen=True, slots=True)
class WorkspaceParameterGroupDefinition:
    """Одна верхня гілка майбутнього дерева параметрів WSP."""

    code: str
    order: int
    title: WorkspaceParameterTranslation
    description: WorkspaceParameterTranslation

    def __post_init__(self) -> None:
        _required_code(self.code, "group code")
        _non_negative_int(self.order, "group order")


@dataclass(frozen=True, slots=True)
class WorkspaceParameterDefinition:
    """Декларативні metadata одного persisted-параметра WSP."""

    key: str
    storage_section: str
    storage_key: str
    group_code: str
    order: int
    value_type: str
    default: object
    title: WorkspaceParameterTranslation
    description: WorkspaceParameterTranslation
    feature_code: str
    editable_runtime_states: tuple[str, ...]
    minimum: float | int | None = None
    maximum: float | int | None = None
    step: float | int | None = None
    allowed_values: tuple[str, ...] = ()
    allowed_value_labels: tuple[WorkspaceParameterTranslation, ...] = ()
    legacy_choice_aliases: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _required_text(self.key, "parameter key")
        if "." not in self.key:
            raise WorkspaceParameterSchemaError(
                "parameter key must contain a namespace separator"
            )
        if self.storage_section not in WORKSPACE_PARAMETER_STORAGE_SECTIONS:
            raise WorkspaceParameterSchemaError(
                f"unsupported storage section: {self.storage_section}"
            )
        _required_text(self.storage_key, "storage key")
        _required_code(self.group_code, "group code")
        _non_negative_int(self.order, "parameter order")
        if self.value_type not in WORKSPACE_PARAMETER_VALUE_TYPES:
            raise WorkspaceParameterSchemaError(
                f"unsupported parameter value type: {self.value_type}"
            )
        _required_code(self.feature_code, "feature code")
        if not self.editable_runtime_states:
            raise WorkspaceParameterSchemaError(
                "editable_runtime_states cannot be empty"
            )
        for state in self.editable_runtime_states:
            _required_code(state, "editable runtime state")
        self._validate_constraints()
        self.normalize_value(self.default)

    def normalize_value(self, value: object) -> object:
        """Перевірити й нормалізувати значення за цим визначенням."""
        if self.value_type == WORKSPACE_PARAMETER_TYPE_FLOAT:
            normalized: object = _finite_float(value, self.key)
        elif self.value_type == WORKSPACE_PARAMETER_TYPE_INTEGER:
            normalized = _integer(value, self.key)
        elif self.value_type == WORKSPACE_PARAMETER_TYPE_BOOLEAN:
            normalized = _boolean(value, self.key)
        else:
            normalized_value = str(value or "").strip().upper()
            aliases = dict(self.legacy_choice_aliases)
            normalized = _choice(
                aliases.get(normalized_value, value),
                self.key,
                self.allowed_values,
            )

        if isinstance(normalized, (float, int)) and not isinstance(
            normalized,
            bool,
        ):
            if self.minimum is not None and normalized < self.minimum:
                raise WorkspaceParameterSchemaError(
                    f"{self.key} cannot be below {self.minimum}"
                )
            if self.maximum is not None and normalized > self.maximum:
                raise WorkspaceParameterSchemaError(
                    f"{self.key} cannot exceed {self.maximum}"
                )
        return normalized

    def _validate_constraints(self) -> None:
        numeric = self.value_type in (
            WORKSPACE_PARAMETER_TYPE_FLOAT,
            WORKSPACE_PARAMETER_TYPE_INTEGER,
        )
        if numeric:
            if self.allowed_values:
                raise WorkspaceParameterSchemaError(
                    "numeric parameter cannot define allowed_values"
                )
            if self.minimum is not None:
                _finite_number(self.minimum, "minimum")
            if self.maximum is not None:
                _finite_number(self.maximum, "maximum")
            if (
                self.minimum is not None
                and self.maximum is not None
                and self.minimum > self.maximum
            ):
                raise WorkspaceParameterSchemaError("minimum cannot exceed maximum")
            if self.step is not None:
                step = _finite_number(self.step, "step")
                if step <= 0:
                    raise WorkspaceParameterSchemaError(
                        "numeric parameter step must be positive"
                    )
            return

        if any(value is not None for value in (self.minimum, self.maximum, self.step)):
            raise WorkspaceParameterSchemaError(
                "non-numeric parameter cannot define numeric constraints"
            )
        if self.value_type == WORKSPACE_PARAMETER_TYPE_CHOICE:
            if not self.allowed_values:
                raise WorkspaceParameterSchemaError(
                    "choice parameter requires allowed_values"
                )
            normalized_values = tuple(
                _required_text(value, "allowed value") for value in self.allowed_values
            )
            if len(set(normalized_values)) != len(normalized_values):
                raise WorkspaceParameterSchemaError(
                    "choice allowed_values must be unique"
                )
            if self.allowed_value_labels and (
                len(self.allowed_value_labels) != len(self.allowed_values)
            ):
                raise WorkspaceParameterSchemaError(
                    "choice labels must match allowed_values"
                )
            alias_sources: set[str] = set()
            for source, target in self.legacy_choice_aliases:
                normalized_source = _required_text(
                    source,
                    "legacy choice alias source",
                ).upper()
                normalized_target = _required_text(
                    target,
                    "legacy choice alias target",
                ).upper()
                if normalized_source in alias_sources:
                    raise WorkspaceParameterSchemaError(
                        "legacy choice alias sources must be unique"
                    )
                if normalized_target not in normalized_values:
                    raise WorkspaceParameterSchemaError(
                        "legacy choice alias target must be allowed"
                    )
                alias_sources.add(normalized_source)
        elif (
            self.allowed_values
            or self.allowed_value_labels
            or self.legacy_choice_aliases
        ):
            raise WorkspaceParameterSchemaError(
                "boolean parameter cannot define choice values"
            )


@dataclass(frozen=True, slots=True)
class WorkspaceParameterFeatureProfile:
    """Набір можливостей, дозволених поточним license/runtime context."""

    edition: str
    granted_feature_codes: frozenset[str]

    def __post_init__(self) -> None:
        edition = _required_text(self.edition, "edition").lower()
        features = frozenset(
            _required_code(feature, "granted feature code")
            for feature in self.granted_feature_codes
        )
        object.__setattr__(self, "edition", edition)
        object.__setattr__(self, "granted_feature_codes", features)

    @classmethod
    def create(
        cls,
        *,
        edition: str,
        granted_feature_codes: Collection[str],
    ) -> WorkspaceParameterFeatureProfile:
        """Створити нормалізований профіль без hardcode матриці редакцій."""
        return cls(
            edition=edition,
            granted_feature_codes=frozenset(granted_feature_codes),
        )


@dataclass(frozen=True, slots=True)
class WorkspaceParameterAvailability:
    """Визначена UI-доступність параметра для конкретного feature profile."""

    available: bool
    edition: str
    feature_code: str
    status: WorkspaceParameterTranslation
    reason: WorkspaceParameterTranslation | None


@dataclass(frozen=True, slots=True)
class WorkspaceParameterStorageUpdate:
    """Перевірені копії всіх підтримуваних storage-секцій AlgorithmWorkspace."""

    parameters: dict[str, object]
    risk_settings: dict[str, object]
    profit_protection: dict[str, object]
    replay_settings: dict[str, object]


@dataclass(frozen=True, slots=True)
class WorkspaceParameterCatalog:
    """Перевірена детермінована колекція для моделі та майбутнього tree UI."""

    groups: tuple[WorkspaceParameterGroupDefinition, ...]
    parameters: tuple[WorkspaceParameterDefinition, ...]

    def __post_init__(self) -> None:
        if not self.groups:
            raise WorkspaceParameterSchemaError("parameter groups are required")
        group_codes = [group.code for group in self.groups]
        if len(set(group_codes)) != len(group_codes):
            raise WorkspaceParameterSchemaError("duplicate parameter group code")
        group_orders = [group.order for group in self.groups]
        if len(set(group_orders)) != len(group_orders):
            raise WorkspaceParameterSchemaError("duplicate parameter group order")

        parameter_keys = [parameter.key for parameter in self.parameters]
        if len(set(parameter_keys)) != len(parameter_keys):
            raise WorkspaceParameterSchemaError("duplicate parameter key")
        storage_addresses = [
            (parameter.storage_section, parameter.storage_key)
            for parameter in self.parameters
        ]
        if len(set(storage_addresses)) != len(storage_addresses):
            raise WorkspaceParameterSchemaError("duplicate parameter storage address")
        known_groups = set(group_codes)
        for parameter in self.parameters:
            if parameter.group_code not in known_groups:
                raise WorkspaceParameterSchemaError(
                    f"unknown parameter group: {parameter.group_code}"
                )

    def ordered_groups(self) -> tuple[WorkspaceParameterGroupDefinition, ...]:
        """Повернути групи у стабільному порядку дерева."""
        return tuple(sorted(self.groups, key=lambda group: group.order))

    def parameters_for_group(
        self,
        group_code: str,
    ) -> tuple[WorkspaceParameterDefinition, ...]:
        """Повернути параметри групи у стабільному порядку відображення."""
        return tuple(
            sorted(
                (
                    parameter
                    for parameter in self.parameters
                    if parameter.group_code == group_code
                ),
                key=lambda parameter: parameter.order,
            )
        )

    def definition(self, key: str) -> WorkspaceParameterDefinition:
        """Знайти визначення за стабільним schema key."""
        for parameter in self.parameters:
            if parameter.key == key:
                return parameter
        raise WorkspaceParameterSchemaError(f"unknown parameter key: {key}")

    def values_from_workspace(self, workspace: object) -> dict[str, object]:
        """Прочитати schema-owned значення із застосуванням defaults для відсутніх."""
        sections = _workspace_sections(workspace)
        values: dict[str, object] = {}
        for parameter in self.parameters:
            section = sections[parameter.storage_section]
            raw_value = section.get(parameter.storage_key, parameter.default)
            values[parameter.key] = parameter.normalize_value(raw_value)
        return values

    def merge_workspace_values(
        self,
        workspace: object,
        updates: Mapping[str, object],
    ) -> WorkspaceParameterStorageUpdate:
        """Повернути перевірені storage-копії та зберегти невідомі future keys."""
        if not isinstance(updates, Mapping):
            raise WorkspaceParameterSchemaError("updates must be a mapping")
        sections = _workspace_sections(workspace)
        for key, raw_value in updates.items():
            parameter = self.definition(str(key))
            normalized = parameter.normalize_value(raw_value)
            sections[parameter.storage_section][parameter.storage_key] = normalized
        return WorkspaceParameterStorageUpdate(
            parameters=sections[WORKSPACE_PARAMETER_STORAGE_PARAMETERS],
            risk_settings=sections[WORKSPACE_PARAMETER_STORAGE_RISK_SETTINGS],
            profit_protection=sections[WORKSPACE_PARAMETER_STORAGE_PROFIT_PROTECTION],
            replay_settings=sections[WORKSPACE_PARAMETER_STORAGE_REPLAY_SETTINGS],
        )

    def availability(
        self,
        key: str,
        profile: WorkspaceParameterFeatureProfile,
    ) -> WorkspaceParameterAvailability:
        """Визначити доступність feature без умов за назвою редакції."""
        parameter = self.definition(key)
        available = parameter.feature_code in profile.granted_feature_codes
        if available:
            return WorkspaceParameterAvailability(
                available=True,
                edition=profile.edition,
                feature_code=parameter.feature_code,
                status=WorkspaceParameterTranslation(
                    WORKSPACE_PARAMETER_AVAILABLE_KEY,
                    WORKSPACE_PARAMETER_AVAILABLE_FALLBACK,
                ),
                reason=None,
            )
        return WorkspaceParameterAvailability(
            available=False,
            edition=profile.edition,
            feature_code=parameter.feature_code,
            status=WorkspaceParameterTranslation(
                WORKSPACE_PARAMETER_LOCKED_KEY,
                WORKSPACE_PARAMETER_LOCKED_FALLBACK,
            ),
            reason=WorkspaceParameterTranslation(
                WORKSPACE_PARAMETER_FEATURE_REQUIRED_KEY,
                WORKSPACE_PARAMETER_FEATURE_REQUIRED_FALLBACK,
            ),
        )

    def translation_entries(self) -> tuple[WorkspaceParameterTranslation, ...]:
        """Повернути всі ключі, які майбутній UI має обробити через LangManager.tr()."""
        entries: list[WorkspaceParameterTranslation] = []
        for group in self.ordered_groups():
            entries.extend((group.title, group.description))
        for parameter in self.parameters:
            entries.extend((parameter.title, parameter.description))
            entries.extend(parameter.allowed_value_labels)
        entries.extend(
            (
                WorkspaceParameterTranslation(
                    WORKSPACE_PARAMETER_AVAILABLE_KEY,
                    WORKSPACE_PARAMETER_AVAILABLE_FALLBACK,
                ),
                WorkspaceParameterTranslation(
                    WORKSPACE_PARAMETER_LOCKED_KEY,
                    WORKSPACE_PARAMETER_LOCKED_FALLBACK,
                ),
                WorkspaceParameterTranslation(
                    WORKSPACE_PARAMETER_FEATURE_REQUIRED_KEY,
                    WORKSPACE_PARAMETER_FEATURE_REQUIRED_FALLBACK,
                ),
                WorkspaceParameterTranslation(
                    WORKSPACE_PARAMETER_RUNTIME_LOCKED_KEY,
                    WORKSPACE_PARAMETER_RUNTIME_LOCKED_FALLBACK,
                ),
                WorkspaceParameterTranslation(
                    WORKSPACE_PARAMETER_STOP_REQUIRED_KEY,
                    WORKSPACE_PARAMETER_STOP_REQUIRED_FALLBACK,
                ),
            )
        )
        unique: dict[str, WorkspaceParameterTranslation] = {}
        for entry in entries:
            existing = unique.get(entry.key)
            if existing is not None and existing.fallback != entry.fallback:
                raise WorkspaceParameterSchemaError(
                    f"conflicting translation fallback: {entry.key}"
                )
            unique[entry.key] = entry
        return tuple(unique[key] for key in unique)

    def register_translations(
        self,
        translator: WorkspaceParameterTranslator,
    ) -> dict[str, str]:
        """Отримати й зареєструвати всі переклади схеми через LangManager.tr()."""
        return {
            entry.key: translator.tr(entry.key, entry.fallback)
            for entry in self.translation_entries()
        }


def _workspace_sections(
    workspace: object,
) -> dict[str, dict[str, object]]:
    sections: dict[str, dict[str, object]] = {}
    for section_name in WORKSPACE_PARAMETER_STORAGE_SECTIONS:
        value = getattr(workspace, section_name, {})
        if not isinstance(value, Mapping):
            raise WorkspaceParameterSchemaError(
                f"workspace.{section_name} must be a mapping"
            )
        sections[section_name] = dict(value)
    return sections


def _required_text(value: object, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise WorkspaceParameterSchemaError(f"{field_name} is required")
    return text


def _required_code(value: object, field_name: str) -> str:
    code = _required_text(value, field_name).upper()
    if any(character.isspace() for character in code):
        raise WorkspaceParameterSchemaError(f"{field_name} cannot contain whitespace")
    return code


def _finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WorkspaceParameterSchemaError(f"{field_name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise WorkspaceParameterSchemaError(f"{field_name} must be finite")
    return number


def _finite_float(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise WorkspaceParameterSchemaError(f"{field_name} must be a number")
    try:
        if isinstance(value, (int, float)):
            number = float(value)
        elif isinstance(value, str):
            number = float(value.strip())
        else:
            raise TypeError
    except (TypeError, ValueError) as exc:
        raise WorkspaceParameterSchemaError(f"{field_name} must be a number") from exc
    if not math.isfinite(number):
        raise WorkspaceParameterSchemaError(f"{field_name} must be finite")
    return number


def _integer(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise WorkspaceParameterSchemaError(f"{field_name} must be an integer")
    try:
        if isinstance(value, int):
            number = value
        elif isinstance(value, float):
            if not value.is_integer():
                raise ValueError
            number = int(value)
        elif isinstance(value, str):
            number = int(value.strip())
        else:
            raise TypeError
    except (TypeError, ValueError) as exc:
        raise WorkspaceParameterSchemaError(f"{field_name} must be an integer") from exc
    return number


def _non_negative_int(value: object, field_name: str) -> int:
    number = _integer(value, field_name)
    if number < 0:
        raise WorkspaceParameterSchemaError(f"{field_name} cannot be negative")
    return number


def _boolean(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise WorkspaceParameterSchemaError(f"{field_name} must be boolean")
    return value


def _choice(
    value: object,
    field_name: str,
    allowed_values: tuple[str, ...],
) -> str:
    text = _required_text(value, field_name)
    if text not in allowed_values:
        raise WorkspaceParameterSchemaError(
            f"{field_name} must be one of {allowed_values}"
        )
    return text
