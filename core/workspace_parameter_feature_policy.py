# -*- coding: utf-8 -*-
"""Поточна policy доступності параметрів WSP за редакцією ліцензії.

Каталог параметрів не знає про FREE, PRO або PRO+. Цей модуль перетворює
license edition на набір feature codes, який уже споживає read-only дерево.
Коли продуктова матриця стане ширшою, змінюватиметься саме ця policy, а не
кожен UI-вузол окремо.
"""

from __future__ import annotations

from collections.abc import Mapping

from core import session_state
from core.workspace_parameter_schema import (
    WORKSPACE_PARAMETER_FEATURE_ADVANCED_RISK,
    WORKSPACE_PARAMETER_FEATURE_RISK_MANAGEMENT,
    WORKSPACE_PARAMETER_FEATURE_SIGNAL_FILTERS,
    WORKSPACE_PARAMETER_FEATURE_SIGNAL_SOURCES,
    WorkspaceParameterFeatureProfile,
)

WORKSPACE_PARAMETER_EDITION_FREE = "free"
WORKSPACE_PARAMETER_EDITION_PRO = "pro"
WORKSPACE_PARAMETER_EDITION_PRO_PLUS = "pro_plus"

WORKSPACE_PARAMETER_EDITIONS = (
    WORKSPACE_PARAMETER_EDITION_FREE,
    WORKSPACE_PARAMETER_EDITION_PRO,
    WORKSPACE_PARAMETER_EDITION_PRO_PLUS,
)


def workspace_parameter_feature_profile_for_edition(
    edition: object,
) -> WorkspaceParameterFeatureProfile:
    """Побудувати feature profile без умов за редакцією всередині каталогу."""
    normalized = str(edition or WORKSPACE_PARAMETER_EDITION_FREE).strip().lower()
    if normalized not in WORKSPACE_PARAMETER_EDITIONS:
        normalized = WORKSPACE_PARAMETER_EDITION_FREE

    # Перші signal, filter і risk settings доступні всім редакціям.
    # Каталог не містить умов за назвою редакції.
    features = {
        WORKSPACE_PARAMETER_FEATURE_RISK_MANAGEMENT,
        WORKSPACE_PARAMETER_FEATURE_SIGNAL_FILTERS,
        WORKSPACE_PARAMETER_FEATURE_SIGNAL_SOURCES,
    }
    if normalized == WORKSPACE_PARAMETER_EDITION_PRO_PLUS:
        features.add(WORKSPACE_PARAMETER_FEATURE_ADVANCED_RISK)

    return WorkspaceParameterFeatureProfile.create(
        edition=normalized,
        granted_feature_codes=features,
    )


def current_workspace_parameter_feature_profile() -> WorkspaceParameterFeatureProfile:
    """Прочитати поточну edition з конфігурації та повернути feature profile."""
    license_block: Mapping[str, object] | None = None
    config = session_state.CURRENT_CONFIG
    if config is not None:
        payload = config.to_dict()
        if isinstance(payload, dict):
            raw_license = payload.get("license")
            if isinstance(raw_license, Mapping):
                license_block = raw_license

    edition = (
        license_block.get("edition")
        if license_block is not None
        else WORKSPACE_PARAMETER_EDITION_FREE
    )
    return workspace_parameter_feature_profile_for_edition(edition)


def workspace_parameter_edition_label(edition: object) -> str:
    """Повернути стабільну користувацьку назву редакції."""
    normalized = str(edition or WORKSPACE_PARAMETER_EDITION_FREE).strip().lower()
    labels = {
        WORKSPACE_PARAMETER_EDITION_FREE: "FREE",
        WORKSPACE_PARAMETER_EDITION_PRO: "PRO",
        WORKSPACE_PARAMETER_EDITION_PRO_PLUS: "PRO+",
    }
    return labels.get(normalized, "FREE")


def required_edition_for_feature(feature_code: object) -> str | None:
    """Повернути мінімальну редакцію для пояснення license lock у UI."""
    normalized = str(feature_code or "").strip().upper()
    if normalized == WORKSPACE_PARAMETER_FEATURE_ADVANCED_RISK:
        return "PRO+"
    if normalized in (
        WORKSPACE_PARAMETER_FEATURE_RISK_MANAGEMENT,
        WORKSPACE_PARAMETER_FEATURE_SIGNAL_FILTERS,
        WORKSPACE_PARAMETER_FEATURE_SIGNAL_SOURCES,
    ):
        return "FREE"
    return None
