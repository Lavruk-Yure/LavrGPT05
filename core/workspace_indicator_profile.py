# -*- coding: utf-8 -*-
"""Редаговані профілі індикаторів WSP та відтворювані bindings.

Профіль описує математичні параметри одного індикатора незалежно від брокера.
Вбудовані профілі є незмінними шаблонами. Користувацькі профілі мають власні
редакції. WSP зберігає snapshot профілю, тому подальше редагування каталогу не
змінює старий Replay непомітно.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Mapping
from uuid import UUID, uuid4

INDICATOR_PROFILE_SCHEMA_VERSION = 1

WORKSPACE_INDICATOR_MACD = "MACD"
WORKSPACE_INDICATOR_ALLIGATOR = "ALLIGATOR"
WORKSPACE_INDICATOR_CODES = (
    WORKSPACE_INDICATOR_MACD,
    WORKSPACE_INDICATOR_ALLIGATOR,
)

WORKSPACE_INDICATOR_SOURCE_CLOSE = "CLOSE"
WORKSPACE_INDICATOR_SOURCE_OPEN = "OPEN"
WORKSPACE_INDICATOR_SOURCE_HIGH = "HIGH"
WORKSPACE_INDICATOR_SOURCE_LOW = "LOW"
WORKSPACE_INDICATOR_SOURCE_MEDIAN = "MEDIAN_PRICE"
WORKSPACE_INDICATOR_SOURCE_TYPICAL = "TYPICAL_PRICE"
WORKSPACE_INDICATOR_SOURCE_WEIGHTED = "WEIGHTED_CLOSE"
WORKSPACE_INDICATOR_SOURCES = (
    WORKSPACE_INDICATOR_SOURCE_CLOSE,
    WORKSPACE_INDICATOR_SOURCE_OPEN,
    WORKSPACE_INDICATOR_SOURCE_HIGH,
    WORKSPACE_INDICATOR_SOURCE_LOW,
    WORKSPACE_INDICATOR_SOURCE_MEDIAN,
    WORKSPACE_INDICATOR_SOURCE_TYPICAL,
    WORKSPACE_INDICATOR_SOURCE_WEIGHTED,
)

WORKSPACE_INDICATOR_MA_SIMPLE = "SIMPLE"
WORKSPACE_INDICATOR_MA_EXPONENTIAL = "EXPONENTIAL"
WORKSPACE_INDICATOR_MA_SMOOTHED = "SMOOTHED"
WORKSPACE_INDICATOR_MA_TYPES = (
    WORKSPACE_INDICATOR_MA_SIMPLE,
    WORKSPACE_INDICATOR_MA_EXPONENTIAL,
    WORKSPACE_INDICATOR_MA_SMOOTHED,
)

WORKSPACE_INDICATOR_PROFILE_SOURCE_LGE = "LGE"
WORKSPACE_INDICATOR_PROFILE_SOURCE_CTRADER = "CTRADER"
WORKSPACE_INDICATOR_PROFILE_SOURCE_TWS = "TWS"
WORKSPACE_INDICATOR_PROFILE_SOURCE_USER = "USER"
WORKSPACE_INDICATOR_PROFILE_SOURCES = (
    WORKSPACE_INDICATOR_PROFILE_SOURCE_LGE,
    WORKSPACE_INDICATOR_PROFILE_SOURCE_CTRADER,
    WORKSPACE_INDICATOR_PROFILE_SOURCE_TWS,
    WORKSPACE_INDICATOR_PROFILE_SOURCE_USER,
)

MACD_PROFILE_UID_LGE_CLASSIC = "00000000-0000-5000-8000-000000000001"
MACD_PROFILE_UID_TWS_DEFAULT = "00000000-0000-5000-8000-000000000002"
MACD_PROFILE_UID_CTRADER_REFERENCE = "00000000-0000-5000-8000-000000000003"
MACD_PROFILE_UID_LGE_DEFAULT = "00000000-0000-5000-8000-000000000004"
ALLIGATOR_PROFILE_UID_LGE_CLASSIC = "00000000-0000-5000-8000-000000000011"
ALLIGATOR_PROFILE_UID_CTRADER_DEFAULT = "00000000-0000-5000-8000-000000000012"
ALLIGATOR_PROFILE_UID_TWS_REFERENCE = "00000000-0000-5000-8000-000000000013"
ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F = "00000000-0000-5000-8000-000000000014"

ALLIGATOR_LOGIC_MODE_LEGACY = "LEGACY_3BAR_PHASE_GATE"
ALLIGATOR_LOGIC_MODE_CANDIDATE_F = "CANDIDATE_F"
ALLIGATOR_LOGIC_MODES = (
    ALLIGATOR_LOGIC_MODE_LEGACY,
    ALLIGATOR_LOGIC_MODE_CANDIDATE_F,
)

WORKSPACE_MACD_PROFILE_BINDING_KEY = "MACD"
WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY = "ALLIGATOR"
WORKSPACE_INDICATOR_PROFILE_BINDING_KEYS = (
    WORKSPACE_MACD_PROFILE_BINDING_KEY,
    WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY,
)


class WorkspaceIndicatorProfileError(ValueError):
    """Некоректний профіль, binding або параметри індикатора."""


def indicator_profile_utc_now_iso() -> str:
    """Повернути поточний UTC timestamp у стабільному ISO-форматі."""
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class WorkspaceIndicatorProfile:
    """Одна незмінна редакція профілю індикатора."""

    profile_uid: str
    indicator_code: str
    name: str
    revision: int
    built_in: bool
    archived: bool
    complete: bool
    source_reference: str
    parameters: dict[str, object]
    created_utc: str
    updated_utc: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile_uid", _normalized_uuid(self.profile_uid))
        object.__setattr__(
            self,
            "indicator_code",
            _normalized_choice(
                self.indicator_code,
                "indicator_code",
                WORKSPACE_INDICATOR_CODES,
            ),
        )
        object.__setattr__(self, "name", _required_text(self.name, "name"))
        object.__setattr__(self, "revision", _positive_int(self.revision, "revision"))
        object.__setattr__(self, "built_in", _strict_bool(self.built_in, "built_in"))
        object.__setattr__(self, "archived", _strict_bool(self.archived, "archived"))
        object.__setattr__(self, "complete", _strict_bool(self.complete, "complete"))
        object.__setattr__(
            self,
            "source_reference",
            _normalized_choice(
                self.source_reference,
                "source_reference",
                WORKSPACE_INDICATOR_PROFILE_SOURCES,
            ),
        )
        parameters = _normalize_profile_parameters(
            self.indicator_code,
            self.parameters,
            complete=self.complete,
        )
        object.__setattr__(self, "parameters", parameters)
        object.__setattr__(
            self,
            "created_utc",
            _required_text(self.created_utc, "created_utc"),
        )
        object.__setattr__(
            self,
            "updated_utc",
            _required_text(self.updated_utc, "updated_utc"),
        )
        if (
            self.built_in
            and self.source_reference == WORKSPACE_INDICATOR_PROFILE_SOURCE_USER
        ):
            raise WorkspaceIndicatorProfileError(
                "built-in profile cannot have USER source_reference"
            )
        if (
            not self.built_in
            and self.source_reference != WORKSPACE_INDICATOR_PROFILE_SOURCE_USER
        ):
            raise WorkspaceIndicatorProfileError(
                "user profile must have USER source_reference"
            )

    @property
    def usable(self) -> bool:
        """Повернути True, якщо профіль можна призначити WSP."""
        return self.complete and not self.archived

    def to_storage_dict(self) -> dict[str, object]:
        """Повернути JSON-сумісний snapshot профілю."""
        return {
            "schema_version": INDICATOR_PROFILE_SCHEMA_VERSION,
            "profile_uid": self.profile_uid,
            "indicator_code": self.indicator_code,
            "name": self.name,
            "revision": self.revision,
            "built_in": self.built_in,
            "archived": self.archived,
            "complete": self.complete,
            "source_reference": self.source_reference,
            "parameters": dict(self.parameters),
            "created_utc": self.created_utc,
            "updated_utc": self.updated_utc,
        }

    @classmethod
    def from_storage_dict(
        cls,
        data: Mapping[str, object],
    ) -> WorkspaceIndicatorProfile:
        """Відновити одну редакцію профілю з JSON payload."""
        if not isinstance(data, Mapping):
            raise WorkspaceIndicatorProfileError("profile payload must be a mapping")
        schema_version = _positive_int(
            data.get("schema_version", 0),
            "schema_version",
        )
        if schema_version != INDICATOR_PROFILE_SCHEMA_VERSION:
            raise WorkspaceIndicatorProfileError(
                f"unsupported profile schema_version: {schema_version}"
            )
        parameters = data.get("parameters", {})
        if not isinstance(parameters, Mapping):
            raise WorkspaceIndicatorProfileError("parameters must be a mapping")
        return cls(
            profile_uid=str(data.get("profile_uid") or ""),
            indicator_code=str(data.get("indicator_code") or ""),
            name=str(data.get("name") or ""),
            revision=_positive_int(
                data.get("revision", 0),
                "revision",
            ),
            built_in=_strict_bool(
                data.get("built_in", False),
                "built_in",
            ),
            archived=_strict_bool(
                data.get("archived", False),
                "archived",
            ),
            complete=_strict_bool(
                data.get("complete", False),
                "complete",
            ),
            source_reference=str(data.get("source_reference") or ""),
            parameters=dict(parameters),
            created_utc=str(data.get("created_utc") or ""),
            updated_utc=str(data.get("updated_utc") or ""),
        )

    def duplicate_as_user(self, name: str) -> WorkspaceIndicatorProfile:
        """Створити редаговану користувацьку копію поточної редакції."""
        now = indicator_profile_utc_now_iso()
        return WorkspaceIndicatorProfile(
            profile_uid=str(uuid4()),
            indicator_code=self.indicator_code,
            name=name,
            revision=1,
            built_in=False,
            archived=False,
            complete=self.complete,
            source_reference=WORKSPACE_INDICATOR_PROFILE_SOURCE_USER,
            parameters=dict(self.parameters),
            created_utc=now,
            updated_utc=now,
        )

    def revised(
        self,
        *,
        name: str,
        parameters: Mapping[str, object],
        archived: bool | None = None,
    ) -> WorkspaceIndicatorProfile:
        """Побудувати наступну редакцію користувацького профілю."""
        if self.built_in:
            raise WorkspaceIndicatorProfileError(
                "built-in profile must be duplicated before editing"
            )
        return replace(
            self,
            name=_required_text(name, "name"),
            revision=self.revision + 1,
            archived=(
                self.archived
                if archived is None
                else _strict_bool(archived, "archived")
            ),
            complete=True,
            parameters=dict(parameters),
            updated_utc=indicator_profile_utc_now_iso(),
        )


@dataclass(frozen=True, slots=True)
class WorkspaceIndicatorProfileBinding:
    """Прив'язка WSP до точної редакції та snapshot профілю."""

    indicator_code: str
    profile_uid: str
    profile_revision: int
    resolved_profile_snapshot: dict[str, object]

    def __post_init__(self) -> None:
        indicator_code = _normalized_choice(
            self.indicator_code,
            "indicator_code",
            WORKSPACE_INDICATOR_CODES,
        )
        object.__setattr__(self, "indicator_code", indicator_code)
        object.__setattr__(self, "profile_uid", _normalized_uuid(self.profile_uid))
        object.__setattr__(
            self,
            "profile_revision",
            _positive_int(self.profile_revision, "profile_revision"),
        )
        snapshot = WorkspaceIndicatorProfile.from_storage_dict(
            self.resolved_profile_snapshot
        )
        if snapshot.indicator_code != indicator_code:
            raise WorkspaceIndicatorProfileError(
                "binding indicator_code does not match snapshot"
            )
        if snapshot.profile_uid != self.profile_uid:
            raise WorkspaceIndicatorProfileError(
                "binding profile_uid does not match snapshot"
            )
        if snapshot.revision != self.profile_revision:
            raise WorkspaceIndicatorProfileError(
                "binding profile_revision does not match snapshot"
            )
        if not snapshot.complete:
            raise WorkspaceIndicatorProfileError(
                "incomplete reference profile cannot be bound to WSP"
            )
        object.__setattr__(
            self,
            "resolved_profile_snapshot",
            snapshot.to_storage_dict(),
        )

    @property
    def profile(self) -> WorkspaceIndicatorProfile:
        """Повернути профіль із зафіксованого snapshot."""
        return WorkspaceIndicatorProfile.from_storage_dict(
            self.resolved_profile_snapshot
        )

    def to_storage_dict(self) -> dict[str, object]:
        """Повернути JSON-сумісну прив'язку WSP."""
        return {
            "indicator_code": self.indicator_code,
            "profile_uid": self.profile_uid,
            "profile_revision": self.profile_revision,
            "resolved_profile_snapshot": dict(self.resolved_profile_snapshot),
        }

    @classmethod
    def from_storage_dict(
        cls,
        data: Mapping[str, object],
    ) -> WorkspaceIndicatorProfileBinding:
        """Відновити binding із persisted payload."""
        if not isinstance(data, Mapping):
            raise WorkspaceIndicatorProfileError("binding must be a mapping")
        snapshot = data.get("resolved_profile_snapshot", {})
        if not isinstance(snapshot, Mapping):
            raise WorkspaceIndicatorProfileError(
                "resolved_profile_snapshot must be a mapping"
            )
        return cls(
            indicator_code=str(data.get("indicator_code") or ""),
            profile_uid=str(data.get("profile_uid") or ""),
            profile_revision=_positive_int(
                data.get("profile_revision", 0),
                "profile_revision",
            ),
            resolved_profile_snapshot=dict(snapshot),
        )

    @classmethod
    def from_profile(
        cls,
        profile: WorkspaceIndicatorProfile,
    ) -> WorkspaceIndicatorProfileBinding:
        """Створити відтворювану прив'язку до поточної редакції профілю."""
        if not profile.usable:
            raise WorkspaceIndicatorProfileError(
                "only complete active profile can be bound to WSP"
            )
        return cls(
            indicator_code=profile.indicator_code,
            profile_uid=profile.profile_uid,
            profile_revision=profile.revision,
            resolved_profile_snapshot=profile.to_storage_dict(),
        )


def built_in_workspace_indicator_profiles() -> tuple[WorkspaceIndicatorProfile, ...]:
    """Повернути незмінні канонічні шаблони MACD і Alligator."""
    created = "2026-08-02T00:00:00+00:00"
    return (
        WorkspaceIndicatorProfile(
            profile_uid=MACD_PROFILE_UID_LGE_CLASSIC,
            indicator_code=WORKSPACE_INDICATOR_MACD,
            name="LGE Classic EMA 12/26/9 Close",
            revision=1,
            built_in=True,
            archived=False,
            complete=True,
            source_reference=WORKSPACE_INDICATOR_PROFILE_SOURCE_LGE,
            parameters={
                "source": WORKSPACE_INDICATOR_SOURCE_CLOSE,
                "fast_period": 12,
                "slow_period": 26,
                "signal_period": 9,
                "oscillator_ma_type": WORKSPACE_INDICATOR_MA_EXPONENTIAL,
                "signal_ma_type": WORKSPACE_INDICATOR_MA_EXPONENTIAL,
                "shift": 0,
            },
            created_utc=created,
            updated_utc=created,
        ),
        WorkspaceIndicatorProfile(
            profile_uid=MACD_PROFILE_UID_LGE_DEFAULT,
            indicator_code=WORKSPACE_INDICATOR_MACD,
            name="LGE Default EMA 8/17/5 Close",
            revision=1,
            built_in=True,
            archived=False,
            complete=True,
            source_reference=WORKSPACE_INDICATOR_PROFILE_SOURCE_LGE,
            parameters={
                "source": WORKSPACE_INDICATOR_SOURCE_CLOSE,
                "fast_period": 8,
                "slow_period": 17,
                "signal_period": 5,
                "oscillator_ma_type": WORKSPACE_INDICATOR_MA_EXPONENTIAL,
                "signal_ma_type": WORKSPACE_INDICATOR_MA_EXPONENTIAL,
                "shift": 0,
            },
            created_utc=created,
            updated_utc=created,
        ),
        WorkspaceIndicatorProfile(
            profile_uid=MACD_PROFILE_UID_TWS_DEFAULT,
            indicator_code=WORKSPACE_INDICATOR_MACD,
            name="TWS Default MACD",
            revision=1,
            built_in=True,
            archived=False,
            complete=True,
            source_reference=WORKSPACE_INDICATOR_PROFILE_SOURCE_TWS,
            parameters={
                "source": WORKSPACE_INDICATOR_SOURCE_CLOSE,
                "fast_period": 12,
                "slow_period": 26,
                "signal_period": 9,
                "oscillator_ma_type": WORKSPACE_INDICATOR_MA_EXPONENTIAL,
                "signal_ma_type": WORKSPACE_INDICATOR_MA_EXPONENTIAL,
                "shift": 0,
            },
            created_utc=created,
            updated_utc=created,
        ),
        WorkspaceIndicatorProfile(
            profile_uid=MACD_PROFILE_UID_CTRADER_REFERENCE,
            indicator_code=WORKSPACE_INDICATOR_MACD,
            name="cTrader Default MACD Reference",
            revision=1,
            built_in=True,
            archived=False,
            complete=False,
            source_reference=WORKSPACE_INDICATOR_PROFILE_SOURCE_CTRADER,
            parameters={
                "source": WORKSPACE_INDICATOR_SOURCE_CLOSE,
                "fast_period": 12,
                "slow_period": 26,
                "signal_period": 9,
                "shift": 0,
            },
            created_utc=created,
            updated_utc=created,
        ),
        WorkspaceIndicatorProfile(
            profile_uid=ALLIGATOR_PROFILE_UID_LGE_CLASSIC,
            indicator_code=WORKSPACE_INDICATOR_ALLIGATOR,
            name="LGE Classic Smoothed",
            revision=1,
            built_in=True,
            archived=False,
            complete=True,
            source_reference=WORKSPACE_INDICATOR_PROFILE_SOURCE_LGE,
            parameters={
                "source": WORKSPACE_INDICATOR_SOURCE_MEDIAN,
                "jaw_period": 13,
                "jaw_shift": 8,
                "teeth_period": 8,
                "teeth_shift": 5,
                "lips_period": 5,
                "lips_shift": 3,
                "ma_type": WORKSPACE_INDICATOR_MA_SMOOTHED,
            },
            created_utc=created,
            updated_utc=created,
        ),
        WorkspaceIndicatorProfile(
            profile_uid=ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F,
            indicator_code=WORKSPACE_INDICATOR_ALLIGATOR,
            name="LGE Candidate F Smoothed",
            revision=1,
            built_in=True,
            archived=False,
            complete=True,
            source_reference=WORKSPACE_INDICATOR_PROFILE_SOURCE_LGE,
            parameters={
                "source": WORKSPACE_INDICATOR_SOURCE_MEDIAN,
                "jaw_period": 13,
                "jaw_shift": 8,
                "teeth_period": 8,
                "teeth_shift": 5,
                "lips_period": 5,
                "lips_shift": 3,
                "ma_type": WORKSPACE_INDICATOR_MA_SMOOTHED,
                "logic_mode": ALLIGATOR_LOGIC_MODE_CANDIDATE_F,
                "trend_start_confirmation_bars": 4,
                "deferred_expiry_bars": 5,
                "opening_collapse_threshold": -0.700,
                "volatility_lookback_bars": 20,
                "weak_max_active_age": 2,
                "weak_max_opening": 0.500,
                "spike_min_range_ratio": 3.500,
                "spike_max_opening_delta": -0.500,
                "spike_max_slope_delta": -0.010,
                "overextended_min_slope": 0.200,
                "overextended_min_opening": 3.000,
            },
            created_utc=created,
            updated_utc=created,
        ),
        WorkspaceIndicatorProfile(
            profile_uid=ALLIGATOR_PROFILE_UID_CTRADER_DEFAULT,
            indicator_code=WORKSPACE_INDICATOR_ALLIGATOR,
            name="cTrader Default Simple Close",
            revision=1,
            built_in=True,
            archived=False,
            complete=True,
            source_reference=WORKSPACE_INDICATOR_PROFILE_SOURCE_CTRADER,
            parameters={
                "source": WORKSPACE_INDICATOR_SOURCE_CLOSE,
                "jaw_period": 13,
                "jaw_shift": 8,
                "teeth_period": 8,
                "teeth_shift": 5,
                "lips_period": 5,
                "lips_shift": 3,
                "ma_type": WORKSPACE_INDICATOR_MA_SIMPLE,
            },
            created_utc=created,
            updated_utc=created,
        ),
        WorkspaceIndicatorProfile(
            profile_uid=ALLIGATOR_PROFILE_UID_TWS_REFERENCE,
            indicator_code=WORKSPACE_INDICATOR_ALLIGATOR,
            name="TWS Default Alligator Reference",
            revision=1,
            built_in=True,
            archived=False,
            complete=False,
            source_reference=WORKSPACE_INDICATOR_PROFILE_SOURCE_TWS,
            parameters={
                "jaw_period": 21,
                "jaw_shift": 8,
                "teeth_period": 13,
                "teeth_shift": 5,
                "lips_period": 8,
                "lips_shift": 3,
            },
            created_utc=created,
            updated_utc=created,
        ),
    )


def built_in_workspace_indicator_profile(
    profile_uid: str,
) -> WorkspaceIndicatorProfile:
    """Знайти вбудований профіль за UID."""
    normalized = _normalized_uuid(profile_uid)
    for profile in built_in_workspace_indicator_profiles():
        if profile.profile_uid == normalized:
            return profile
    raise WorkspaceIndicatorProfileError(f"unknown built-in profile_uid: {normalized}")


def default_workspace_indicator_profile_bindings() -> dict[str, dict[str, object]]:
    """Повернути сумісні defaults для нового або legacy WSP."""
    macd = built_in_workspace_indicator_profile(MACD_PROFILE_UID_LGE_CLASSIC)
    alligator = built_in_workspace_indicator_profile(ALLIGATOR_PROFILE_UID_LGE_CLASSIC)
    return {
        WORKSPACE_MACD_PROFILE_BINDING_KEY: (
            WorkspaceIndicatorProfileBinding.from_profile(macd).to_storage_dict()
        ),
        WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY: (
            WorkspaceIndicatorProfileBinding.from_profile(alligator).to_storage_dict()
        ),
    }


def new_workspace_indicator_profile_bindings() -> dict[str, dict[str, object]]:
    """Повернути bindings для нового WSP без зміни legacy fallback."""
    macd = built_in_workspace_indicator_profile(MACD_PROFILE_UID_LGE_DEFAULT)
    alligator = built_in_workspace_indicator_profile(ALLIGATOR_PROFILE_UID_LGE_CLASSIC)
    return {
        WORKSPACE_MACD_PROFILE_BINDING_KEY: (
            WorkspaceIndicatorProfileBinding.from_profile(macd).to_storage_dict()
        ),
        WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY: (
            WorkspaceIndicatorProfileBinding.from_profile(alligator).to_storage_dict()
        ),
    }


def normalize_workspace_indicator_profile_bindings(
    value: object,
) -> dict[str, dict[str, object]]:
    """Перевірити bindings WSP і додати відсутні legacy defaults."""
    result = default_workspace_indicator_profile_bindings()
    if value is None:
        return result
    if not isinstance(value, Mapping):
        raise WorkspaceIndicatorProfileError(
            "indicator_profile_bindings must be a mapping"
        )
    for key, payload in value.items():
        normalized_key = str(key or "").strip().upper()
        if not isinstance(payload, Mapping):
            raise WorkspaceIndicatorProfileError(
                f"indicator profile binding {normalized_key} must be a mapping"
            )
        if normalized_key not in WORKSPACE_INDICATOR_PROFILE_BINDING_KEYS:
            result[normalized_key] = dict(payload)
            continue
        binding = WorkspaceIndicatorProfileBinding.from_storage_dict(payload)
        if binding.indicator_code != normalized_key:
            raise WorkspaceIndicatorProfileError(
                f"binding key {normalized_key} does not match indicator_code"
            )
        result[normalized_key] = binding.to_storage_dict()
    return result


def workspace_indicator_profile_binding(
    workspace: object,
    indicator_code: str,
) -> WorkspaceIndicatorProfileBinding:
    """Прочитати точний profile binding із WSP-like object."""
    code = _normalized_choice(
        indicator_code,
        "indicator_code",
        WORKSPACE_INDICATOR_CODES,
    )
    bindings = normalize_workspace_indicator_profile_bindings(
        getattr(workspace, "indicator_profile_bindings", None)
    )
    return WorkspaceIndicatorProfileBinding.from_storage_dict(bindings[code])


def merge_workspace_indicator_profile_binding(
    current: object,
    binding: WorkspaceIndicatorProfileBinding,
) -> dict[str, dict[str, object]]:
    """Замінити одну прив'язку, зберігши другу та future keys."""
    if current is None:
        result: dict[str, object] = {}
    elif isinstance(current, Mapping):
        result = dict(current)
    else:
        raise WorkspaceIndicatorProfileError(
            "indicator_profile_bindings must be a mapping"
        )
    result[binding.indicator_code] = binding.to_storage_dict()
    return normalize_workspace_indicator_profile_bindings(result)


def _normalize_profile_parameters(
    indicator_code: str,
    value: object,
    *,
    complete: bool,
) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise WorkspaceIndicatorProfileError("parameters must be a mapping")
    data = dict(value)
    if indicator_code == WORKSPACE_INDICATOR_MACD:
        return _normalize_macd_parameters(data, complete=complete)
    if indicator_code == WORKSPACE_INDICATOR_ALLIGATOR:
        return _normalize_alligator_parameters(data, complete=complete)
    raise WorkspaceIndicatorProfileError(
        f"unsupported indicator_code: {indicator_code}"
    )


def _normalize_macd_parameters(
    data: Mapping[str, object],
    *,
    complete: bool,
) -> dict[str, object]:
    required = (
        "source",
        "fast_period",
        "slow_period",
        "signal_period",
        "oscillator_ma_type",
        "signal_ma_type",
        "shift",
    )
    if complete:
        _require_keys(data, required, "MACD")
    result: dict[str, object] = {}
    if "source" in data:
        result["source"] = _normalized_choice(
            data["source"],
            "MACD source",
            WORKSPACE_INDICATOR_SOURCES,
        )
    if "fast_period" in data:
        result["fast_period"] = _positive_int(
            data["fast_period"],
            "fast_period",
        )
    if "slow_period" in data:
        result["slow_period"] = _positive_int(
            data["slow_period"],
            "slow_period",
        )
    if "signal_period" in data:
        result["signal_period"] = _positive_int(
            data["signal_period"],
            "signal_period",
        )
    if "oscillator_ma_type" in data:
        result["oscillator_ma_type"] = _normalized_choice(
            data["oscillator_ma_type"],
            "oscillator_ma_type",
            WORKSPACE_INDICATOR_MA_TYPES,
        )
    if "signal_ma_type" in data:
        result["signal_ma_type"] = _normalized_choice(
            data["signal_ma_type"],
            "signal_ma_type",
            WORKSPACE_INDICATOR_MA_TYPES,
        )
    if "shift" in data:
        result["shift"] = _non_negative_int(data["shift"], "shift")
    if "fast_period" in result and "slow_period" in result:
        fast_period = _positive_int(result["fast_period"], "fast_period")
        slow_period = _positive_int(result["slow_period"], "slow_period")
        if slow_period <= fast_period:
            raise WorkspaceIndicatorProfileError(
                "MACD slow_period must exceed fast_period"
            )
    return result


def _normalize_alligator_parameters(
    data: Mapping[str, object],
    *,
    complete: bool,
) -> dict[str, object]:
    required = (
        "source",
        "jaw_period",
        "jaw_shift",
        "teeth_period",
        "teeth_shift",
        "lips_period",
        "lips_shift",
        "ma_type",
    )
    if complete:
        _require_keys(data, required, "Alligator")
    result: dict[str, object] = {}
    if "source" in data:
        result["source"] = _normalized_choice(
            data["source"],
            "Alligator source",
            WORKSPACE_INDICATOR_SOURCES,
        )
    for key in ("jaw_period", "teeth_period", "lips_period"):
        if key in data:
            result[key] = _positive_int(data[key], key)
    for key in ("jaw_shift", "teeth_shift", "lips_shift"):
        if key in data:
            result[key] = _non_negative_int(data[key], key)
    if "ma_type" in data:
        result["ma_type"] = _normalized_choice(
            data["ma_type"],
            "Alligator ma_type",
            WORKSPACE_INDICATOR_MA_TYPES,
        )
    if "logic_mode" in data:
        result["logic_mode"] = _normalized_choice(
            data["logic_mode"],
            "Alligator logic_mode",
            ALLIGATOR_LOGIC_MODES,
        )
        if result["logic_mode"] == ALLIGATOR_LOGIC_MODE_CANDIDATE_F:
            _require_keys(
                data,
                (
                    "trend_start_confirmation_bars",
                    "deferred_expiry_bars",
                    "opening_collapse_threshold",
                    "volatility_lookback_bars",
                    "weak_max_active_age",
                    "weak_max_opening",
                    "spike_min_range_ratio",
                    "spike_max_opening_delta",
                    "spike_max_slope_delta",
                    "overextended_min_slope",
                    "overextended_min_opening",
                ),
                "Alligator Candidate F",
            )
    for key in (
        "trend_start_confirmation_bars",
        "deferred_expiry_bars",
        "volatility_lookback_bars",
    ):
        if key in data:
            result[key] = _positive_int(data[key], key)
    if "weak_max_active_age" in data:
        result["weak_max_active_age"] = _non_negative_int(
            data["weak_max_active_age"],
            "weak_max_active_age",
        )
    for key in (
        "opening_collapse_threshold",
        "weak_max_opening",
        "spike_min_range_ratio",
        "spike_max_opening_delta",
        "spike_max_slope_delta",
        "overextended_min_slope",
        "overextended_min_opening",
    ):
        if key in data:
            result[key] = _finite_float(data[key], key)
    return result


def _require_keys(
    data: Mapping[str, object],
    keys: tuple[str, ...],
    label: str,
) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        joined = ", ".join(missing)
        raise WorkspaceIndicatorProfileError(f"{label} profile is incomplete: {joined}")


def _normalized_uuid(value: object) -> str:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise WorkspaceIndicatorProfileError("invalid profile_uid") from exc


def _required_text(value: object, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise WorkspaceIndicatorProfileError(f"{field_name} is required")
    return text


def _normalized_choice(
    value: object,
    field_name: str,
    allowed: tuple[str, ...],
) -> str:
    normalized = _required_text(value, field_name).upper()
    if normalized not in allowed:
        raise WorkspaceIndicatorProfileError(f"invalid {field_name}: {normalized}")
    return normalized


def _strict_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise WorkspaceIndicatorProfileError(f"{field_name} must be bool")
    return value


def _positive_int(value: object, field_name: str) -> int:
    normalized = _strict_int(value, field_name)
    if normalized <= 0:
        raise WorkspaceIndicatorProfileError(f"{field_name} must be positive")
    return normalized


def _non_negative_int(value: object, field_name: str) -> int:
    normalized = _strict_int(value, field_name)
    if normalized < 0:
        raise WorkspaceIndicatorProfileError(f"{field_name} cannot be negative")
    return normalized


def _strict_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise WorkspaceIndicatorProfileError(f"{field_name} must be integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text)
        except ValueError as exc:
            raise WorkspaceIndicatorProfileError(
                f"{field_name} must be integer"
            ) from exc
    raise WorkspaceIndicatorProfileError(f"{field_name} must be integer")


def _finite_float(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise WorkspaceIndicatorProfileError(f"{field_name} must be numeric")
    if isinstance(value, (int, float)):
        normalized = float(value)
    elif isinstance(value, str):
        try:
            normalized = float(value.strip())
        except ValueError as exc:
            raise WorkspaceIndicatorProfileError(
                f"{field_name} must be numeric"
            ) from exc
    else:
        raise WorkspaceIndicatorProfileError(f"{field_name} must be numeric")
    if normalized != normalized or normalized in {float("inf"), float("-inf")}:
        raise WorkspaceIndicatorProfileError(f"{field_name} must be finite")
    return normalized
