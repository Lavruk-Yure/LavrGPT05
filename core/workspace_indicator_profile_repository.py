# -*- coding: utf-8 -*-
"""JSON-сховище й безпечний lifecycle профілів індикаторів WSP."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from core.algorithm_workspace import AlgorithmWorkspace
from core.app_paths import SESSION_DIR
from core.session_repository import SessionRepository, SessionRepositoryError
from core.workspace_indicator_profile import (
    INDICATOR_PROFILE_SCHEMA_VERSION,
    WORKSPACE_INDICATOR_PROFILE_BINDING_KEYS,
    WorkspaceIndicatorProfile,
    WorkspaceIndicatorProfileBinding,
    WorkspaceIndicatorProfileError,
    built_in_workspace_indicator_profiles,
    normalize_workspace_indicator_profile_bindings,
)

INDICATOR_PROFILES_FILE_NAME = "indicator_profiles.json"


class WorkspaceIndicatorProfileRepositoryError(RuntimeError):
    """Помилка читання, запису або lifecycle профілю."""


@dataclass(frozen=True, slots=True)
class WorkspaceIndicatorProfileUsage:
    """Одна WSP-прив'язка до profile UID у persisted або pending стані."""

    workspace_uid: str
    workspace_name: str
    indicator_code: str
    profile_revisions: tuple[int, ...]
    persisted: bool
    pending: bool


@dataclass(frozen=True, slots=True)
class WorkspaceIndicatorProfileLifecycle:
    """Поточне рішення щодо archive/delete для одного профілю."""

    profile: WorkspaceIndicatorProfile
    usages: tuple[WorkspaceIndicatorProfileUsage, ...]

    @property
    def in_use(self) -> bool:
        """Повернути True, якщо profile UID прив'язаний хоча б до одного WSP."""
        return bool(self.usages)

    @property
    def can_archive(self) -> bool:
        """Built-in і вже архівований профіль архівувати не можна."""
        return not self.profile.built_in and not self.profile.archived

    @property
    def can_delete(self) -> bool:
        """Фізично видаляти можна лише невикористаний user profile."""
        return not self.profile.built_in and not self.in_use


class WorkspaceIndicatorProfileRepository:
    """Зберігати лише користувацькі профілі; built-ins надходять із коду."""

    def __init__(self, session_dir: Path | None = None) -> None:
        self.session_dir = Path(session_dir or SESSION_DIR)
        self.path = self.session_dir / INDICATOR_PROFILES_FILE_NAME

    def ensure_storage(self) -> None:
        """Створити Session та початковий файл каталогу."""
        self.session_dir.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write_catalog_payload(
                {
                    "schema_version": INDICATOR_PROFILE_SCHEMA_VERSION,
                    "profiles": [],
                }
            )

    def list_profiles(
        self,
        *,
        include_archived: bool = False,
    ) -> tuple[WorkspaceIndicatorProfile, ...]:
        """Повернути built-ins і користувацькі профілі у стабільному порядку."""
        profiles = list(built_in_workspace_indicator_profiles())
        profiles.extend(self._read_user_profiles())
        if not include_archived:
            profiles = [profile for profile in profiles if not profile.archived]
        profiles.sort(
            key=lambda profile: (
                profile.indicator_code,
                not profile.built_in,
                profile.name.casefold(),
                profile.profile_uid,
            )
        )
        return tuple(profiles)

    def load_profile(self, profile_uid: str) -> WorkspaceIndicatorProfile:
        """Знайти профіль у зведеному каталозі."""
        for profile in self.list_profiles(include_archived=True):
            if profile.profile_uid == str(profile_uid):
                return profile
        raise WorkspaceIndicatorProfileRepositoryError(
            f"Unknown indicator profile: {profile_uid}"
        )

    def save_new_profile(
        self,
        profile: WorkspaceIndicatorProfile,
    ) -> WorkspaceIndicatorProfile:
        """Додати новий користувацький профіль із revision=1."""
        if profile.built_in:
            raise WorkspaceIndicatorProfileRepositoryError(
                "Built-in profile cannot be saved as user profile"
            )
        if profile.revision != 1:
            raise WorkspaceIndicatorProfileRepositoryError(
                "New user profile must start with revision 1"
            )
        profiles = list(self._read_user_profiles())
        if any(item.profile_uid == profile.profile_uid for item in profiles):
            raise WorkspaceIndicatorProfileRepositoryError(
                f"Duplicate profile_uid: {profile.profile_uid}"
            )
        profiles.append(profile)
        self._write_user_profiles(profiles)
        return profile

    def duplicate_profile(
        self,
        profile_uid: str,
        *,
        name: str,
    ) -> WorkspaceIndicatorProfile:
        """Створити редаговану копію built-in або user профілю."""
        source = self.load_profile(profile_uid)
        duplicate = source.duplicate_as_user(name)
        return self.save_new_profile(duplicate)

    def update_profile(
        self,
        profile_uid: str,
        *,
        name: str,
        parameters: Mapping[str, object],
    ) -> WorkspaceIndicatorProfile:
        """Зберегти наступну редакцію користувацького профілю."""
        current = self.load_profile(profile_uid)
        if current.built_in:
            raise WorkspaceIndicatorProfileRepositoryError(
                "Built-in profile must be duplicated before editing"
            )
        updated = current.revised(name=name, parameters=parameters)
        profiles = [
            updated if item.profile_uid == current.profile_uid else item
            for item in self._read_user_profiles()
        ]
        self._write_user_profiles(profiles)
        return updated

    def archive_profile(
        self,
        profile_uid: str,
    ) -> WorkspaceIndicatorProfile:
        """Архівувати користувацький профіль без фізичного видалення."""
        current = self.load_profile(profile_uid)
        if current.built_in:
            raise WorkspaceIndicatorProfileRepositoryError(
                "Built-in profile cannot be archived"
            )
        if current.archived:
            return current
        archived = current.revised(
            name=current.name,
            parameters=current.parameters,
            archived=True,
        )
        profiles = [
            archived if item.profile_uid == current.profile_uid else item
            for item in self._read_user_profiles()
        ]
        self._write_user_profiles(profiles)
        return archived

    def _delete_user_profile(
        self,
        profile_uid: str,
    ) -> WorkspaceIndicatorProfile:
        """Фізично видалити user profile після зовнішньої usage-перевірки."""
        current = self.load_profile(profile_uid)
        if current.built_in:
            raise WorkspaceIndicatorProfileRepositoryError(
                "Built-in profile cannot be deleted"
            )
        profiles = [
            profile
            for profile in self._read_user_profiles()
            if profile.profile_uid != current.profile_uid
        ]
        self._write_user_profiles(profiles)
        return current

    def _read_catalog_payload(self) -> dict[str, object]:
        self.ensure_storage()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkspaceIndicatorProfileRepositoryError(
                f"Cannot read indicator profiles: {self.path}"
            ) from exc
        if not isinstance(payload, dict):
            raise WorkspaceIndicatorProfileRepositoryError(
                "Indicator profiles root must be an object"
            )
        schema_version = payload.get("schema_version")
        if schema_version != INDICATOR_PROFILE_SCHEMA_VERSION:
            raise WorkspaceIndicatorProfileRepositoryError(
                "Unsupported indicator profiles schema_version: " f"{schema_version}"
            )
        if not isinstance(payload.get("profiles", []), list):
            raise WorkspaceIndicatorProfileRepositoryError(
                "Indicator profiles must be a list"
            )
        return payload

    def _read_user_profiles(self) -> tuple[WorkspaceIndicatorProfile, ...]:
        payload = self._read_catalog_payload()
        raw_profiles = self._catalog_profiles(payload)
        profiles: list[WorkspaceIndicatorProfile] = []
        try:
            for item in raw_profiles:
                if not isinstance(item, dict):
                    raise WorkspaceIndicatorProfileError(
                        "User profile entry must be an object"
                    )
                profile = WorkspaceIndicatorProfile.from_storage_dict(item)
                if profile.built_in:
                    raise WorkspaceIndicatorProfileError(
                        "Built-in profile cannot be persisted in user catalog"
                    )
                profiles.append(profile)
        except WorkspaceIndicatorProfileError as exc:
            raise WorkspaceIndicatorProfileRepositoryError(
                "Invalid indicator profile catalog"
            ) from exc
        profile_uids = [profile.profile_uid for profile in profiles]
        if len(profile_uids) != len(set(profile_uids)):
            raise WorkspaceIndicatorProfileRepositoryError(
                "Duplicate profile_uid in user catalog"
            )
        return tuple(profiles)

    def _write_user_profiles(
        self,
        profiles: (
            tuple[WorkspaceIndicatorProfile, ...] | list[WorkspaceIndicatorProfile]
        ),
    ) -> None:
        payload = self._read_catalog_payload()
        existing_by_uid: dict[str, dict[str, object]] = {}
        raw_profiles = self._catalog_profiles(payload)
        for item in raw_profiles:
            if isinstance(item, dict):
                profile_uid = str(item.get("profile_uid") or "")
                if profile_uid:
                    existing_by_uid[profile_uid] = dict(item)
        ordered = sorted(
            profiles,
            key=lambda sort_profile: (
                sort_profile.indicator_code,
                sort_profile.name.casefold(),
                sort_profile.profile_uid,
            ),
        )
        serialized: list[dict[str, object]] = []
        for profile in ordered:
            item = existing_by_uid.get(profile.profile_uid, {}).copy()
            item.update(profile.to_storage_dict())
            serialized.append(item)
        payload["schema_version"] = INDICATOR_PROFILE_SCHEMA_VERSION
        payload["profiles"] = serialized
        self._write_catalog_payload(payload)

    @staticmethod
    def _catalog_profiles(payload: Mapping[str, object]) -> list[object]:
        raw_profiles = payload.get("profiles", [])
        if not isinstance(raw_profiles, list):
            raise WorkspaceIndicatorProfileRepositoryError(
                "Indicator profiles must be a list"
            )
        return raw_profiles

    def _write_catalog_payload(self, payload: Mapping[str, object]) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(".json.tmp")
        try:
            temp_path.write_text(
                json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temp_path.replace(self.path)
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            raise WorkspaceIndicatorProfileRepositoryError(
                f"Cannot write indicator profiles: {self.path}"
            ) from exc


class WorkspaceIndicatorProfileLifecycleService:
    """Перевіряти WSP usage й виконувати лише безпечний physical delete."""

    def __init__(
        self,
        repository: WorkspaceIndicatorProfileRepository,
        session_repository: SessionRepository | None = None,
    ) -> None:
        self.repository = repository
        self.session_repository = session_repository or SessionRepository(
            repository.session_dir
        )

    def inspect(
        self,
        profile_uid: str,
        *,
        pending_workspace: AlgorithmWorkspace | None = None,
        pending_bindings: Mapping[str, object] | None = None,
    ) -> WorkspaceIndicatorProfileLifecycle:
        """Повернути актуальне archive/delete рішення для profile UID."""
        profile = self.repository.load_profile(profile_uid)
        usages = self._find_usages(
            profile.profile_uid,
            pending_workspace=pending_workspace,
            pending_bindings=pending_bindings,
        )
        return WorkspaceIndicatorProfileLifecycle(profile, usages)

    def delete_unused_profile(
        self,
        profile_uid: str,
        *,
        pending_workspace: AlgorithmWorkspace | None = None,
        pending_bindings: Mapping[str, object] | None = None,
    ) -> WorkspaceIndicatorProfile:
        """Повторно перевірити usage й фізично видалити лише unused user profile."""
        lifecycle = self.inspect(
            profile_uid,
            pending_workspace=pending_workspace,
            pending_bindings=pending_bindings,
        )
        if lifecycle.profile.built_in:
            raise WorkspaceIndicatorProfileRepositoryError(
                "Built-in profile cannot be deleted"
            )
        if lifecycle.in_use:
            raise WorkspaceIndicatorProfileRepositoryError(
                "Profile is used by a workspace and can only be archived"
            )
        # noinspection PyProtectedMember
        return self.repository._delete_user_profile(profile_uid)

    def _find_usages(
        self,
        profile_uid: str,
        *,
        pending_workspace: AlgorithmWorkspace | None,
        pending_bindings: Mapping[str, object] | None,
    ) -> tuple[WorkspaceIndicatorProfileUsage, ...]:
        usages: dict[
            tuple[str, str],
            WorkspaceIndicatorProfileUsage,
        ] = {}
        self.session_repository.ensure_storage()
        paths = sorted(self.session_repository.workspaces_dir.glob("workspace_*.json"))
        for path in paths:
            workspace_uid = path.stem.removeprefix("workspace_")
            try:
                workspace = self.session_repository.load_workspace(workspace_uid)
            except (SessionRepositoryError, ValueError) as exc:
                raise WorkspaceIndicatorProfileRepositoryError(
                    "Cannot verify indicator profile usage because workspace "
                    f"file is invalid: {path.name}"
                ) from exc
            self._merge_workspace_usages(
                usages,
                profile_uid,
                workspace,
                workspace.indicator_profile_bindings,
                persisted=True,
                pending=False,
            )
        if pending_workspace is not None:
            bindings = (
                pending_bindings
                if pending_bindings is not None
                else pending_workspace.indicator_profile_bindings
            )
            self._merge_workspace_usages(
                usages,
                profile_uid,
                pending_workspace,
                bindings,
                persisted=False,
                pending=True,
            )
        return tuple(
            sorted(
                usages.values(),
                key=lambda usage: (
                    usage.workspace_name.casefold(),
                    usage.workspace_uid,
                    usage.indicator_code,
                ),
            )
        )

    @staticmethod
    def _merge_workspace_usages(
        usages: dict[tuple[str, str], WorkspaceIndicatorProfileUsage],
        profile_uid: str,
        workspace: AlgorithmWorkspace,
        raw_bindings: Mapping[str, object],
        *,
        persisted: bool,
        pending: bool,
    ) -> None:
        try:
            bindings = normalize_workspace_indicator_profile_bindings(raw_bindings)
            for indicator_code in WORKSPACE_INDICATOR_PROFILE_BINDING_KEYS:
                binding = WorkspaceIndicatorProfileBinding.from_storage_dict(
                    bindings[indicator_code]
                )
                if binding.profile_uid != profile_uid:
                    continue
                key = (workspace.workspace_uid, indicator_code)
                previous = usages.get(key)
                revisions = {binding.profile_revision}
                if previous is not None:
                    revisions.update(previous.profile_revisions)
                usages[key] = WorkspaceIndicatorProfileUsage(
                    workspace_uid=workspace.workspace_uid,
                    workspace_name=workspace.display_name,
                    indicator_code=indicator_code,
                    profile_revisions=tuple(sorted(revisions)),
                    persisted=(
                        persisted
                        or (previous.persisted if previous is not None else False)
                    ),
                    pending=(
                        pending or (previous.pending if previous is not None else False)
                    ),
                )
        except (KeyError, WorkspaceIndicatorProfileError) as exc:
            raise WorkspaceIndicatorProfileRepositoryError(
                "Cannot verify indicator profile usage because bindings are invalid"
            ) from exc
