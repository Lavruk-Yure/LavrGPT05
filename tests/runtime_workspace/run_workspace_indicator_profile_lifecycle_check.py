# -*- coding: utf-8 -*-
"""Synthetic check for safe indicator-profile archive/delete lifecycle."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import AlgorithmWorkspace  # noqa: E402
from core.session_repository import SessionRepository  # noqa: E402
from core.workspace_indicator_profile import (  # noqa: E402
    MACD_PROFILE_UID_LGE_CLASSIC,
    WORKSPACE_INDICATOR_MACD,
    WorkspaceIndicatorProfile,
    WorkspaceIndicatorProfileBinding,
    merge_workspace_indicator_profile_binding,
    workspace_indicator_profile_binding,
)
from core.workspace_indicator_profile_repository import (  # noqa: E402
    WorkspaceIndicatorProfileLifecycleService,
    WorkspaceIndicatorProfileRepository,
    WorkspaceIndicatorProfileRepositoryError,
)


def _workspace(name: str) -> AlgorithmWorkspace:
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM000001",
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        display_name=name,
    )


def _bind_macd(
    workspace: AlgorithmWorkspace,
    profile: WorkspaceIndicatorProfile,
) -> None:
    binding = WorkspaceIndicatorProfileBinding.from_profile(profile)
    workspace.set_indicator_profile_bindings(
        merge_workspace_indicator_profile_binding(
            workspace.indicator_profile_bindings,
            binding,
        )
    )


def _delete_blocked(callable_object: Callable[[], object]) -> bool:
    try:
        callable_object()
    except WorkspaceIndicatorProfileRepositoryError:
        return True
    return False


def main() -> None:
    with TemporaryDirectory() as tmp_dir:
        session_dir = Path(tmp_dir)
        repository = WorkspaceIndicatorProfileRepository(session_dir)
        session_repository = SessionRepository(session_dir)
        lifecycle = WorkspaceIndicatorProfileLifecycleService(
            repository,
            session_repository,
        )
        repository.ensure_storage()

        built_in = lifecycle.inspect(MACD_PROFILE_UID_LGE_CLASSIC)
        assert built_in.profile.built_in
        assert not built_in.can_archive
        assert not built_in.can_delete
        assert _delete_blocked(
            lambda: lifecycle.delete_unused_profile(MACD_PROFILE_UID_LGE_CLASSIC)
        )

        unused = repository.duplicate_profile(
            MACD_PROFILE_UID_LGE_CLASSIC,
            name="Unused MACD",
        )
        unused_state = lifecycle.inspect(unused.profile_uid)
        assert not unused_state.in_use
        assert unused_state.can_archive
        assert unused_state.can_delete
        deleted_unused = lifecycle.delete_unused_profile(unused.profile_uid)
        assert deleted_unused.profile_uid == unused.profile_uid
        assert _load_profile_blocked(repository, unused.profile_uid)

        future_profile = repository.duplicate_profile(
            MACD_PROFILE_UID_LGE_CLASSIC,
            name="Future Fields MACD",
        )
        payload = json.loads(repository.path.read_text(encoding="utf-8"))
        payload["future_root"] = {"keep": True}
        for item in payload["profiles"]:
            if item["profile_uid"] == future_profile.profile_uid:
                item["future_profile"] = {"keep": "profile"}
        repository.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        future_updated = repository.update_profile(
            future_profile.profile_uid,
            name="Future Fields MACD",
            parameters=future_profile.parameters,
        )
        assert future_updated.revision == 2
        _assert_future_fields_preserved(repository, future_profile.profile_uid)

        bound = repository.duplicate_profile(
            MACD_PROFILE_UID_LGE_CLASSIC,
            name="Bound MACD",
        )
        persisted_workspace = _workspace("Persisted profile WSP")
        _bind_macd(persisted_workspace, bound)
        session_repository.save_workspace(persisted_workspace)

        bound_state = lifecycle.inspect(bound.profile_uid)
        assert bound_state.in_use
        assert not bound_state.can_delete
        assert bound_state.can_archive
        assert len(bound_state.usages) == 1
        assert bound_state.usages[0].persisted
        assert not bound_state.usages[0].pending
        assert _delete_blocked(
            lambda: lifecycle.delete_unused_profile(bound.profile_uid)
        )

        archived = repository.archive_profile(bound.profile_uid)
        assert archived.archived
        assert archived.revision == 2
        persisted_snapshot = workspace_indicator_profile_binding(
            session_repository.load_workspace(persisted_workspace.workspace_uid),
            WORKSPACE_INDICATOR_MACD,
        )
        assert persisted_snapshot.profile_uid == bound.profile_uid
        assert persisted_snapshot.profile_revision == 1
        assert not persisted_snapshot.profile.archived
        assert _delete_blocked(
            lambda: lifecycle.delete_unused_profile(bound.profile_uid)
        )

        session_repository.delete_workspace(persisted_workspace.workspace_uid)
        archived_unused = lifecycle.inspect(bound.profile_uid)
        assert not archived_unused.in_use
        assert not archived_unused.can_archive
        assert archived_unused.can_delete
        lifecycle.delete_unused_profile(bound.profile_uid)
        assert _load_profile_blocked(repository, bound.profile_uid)
        _assert_future_fields_preserved(repository, future_profile.profile_uid)

        pending_profile = repository.duplicate_profile(
            MACD_PROFILE_UID_LGE_CLASSIC,
            name="Pending MACD",
        )
        pending_workspace = _workspace("Pending profile WSP")
        _bind_macd(pending_workspace, pending_profile)
        pending_state = lifecycle.inspect(
            pending_profile.profile_uid,
            pending_workspace=pending_workspace,
            pending_bindings=pending_workspace.indicator_profile_bindings,
        )
        assert pending_state.in_use
        assert not pending_state.can_delete
        assert len(pending_state.usages) == 1
        assert not pending_state.usages[0].persisted
        assert pending_state.usages[0].pending
        assert _delete_blocked(
            lambda: lifecycle.delete_unused_profile(
                pending_profile.profile_uid,
                pending_workspace=pending_workspace,
                pending_bindings=(pending_workspace.indicator_profile_bindings),
            )
        )
        assert lifecycle.inspect(pending_profile.profile_uid).can_delete

        invalid_workspace = (
            session_repository.workspaces_dir
            / "workspace_00000000-0000-4000-8000-000000000099.json"
        )
        session_repository.ensure_storage()
        invalid_workspace.write_text("{broken", encoding="utf-8")
        assert _delete_blocked(
            lambda: lifecycle.delete_unused_profile(pending_profile.profile_uid)
        )
        invalid_workspace.unlink()
        lifecycle.delete_unused_profile(pending_profile.profile_uid)
        assert _load_profile_blocked(repository, pending_profile.profile_uid)
        _assert_future_fields_preserved(repository, future_profile.profile_uid)

    print("Workspace Indicator Profile Lifecycle result")
    print("  built_in_delete_blocked=True")
    print("  built_in_archive_blocked=True")
    print("  unused_user_profile_physically_deleted=True")
    print("  persisted_binding_blocks_delete=True")
    print("  pending_binding_blocks_delete=True")
    print("  bound_profile_archive_allowed=True")
    print("  archived_workspace_snapshot_preserved=True")
    print("  delete_allowed_after_last_usage_removed=True")
    print("  invalid_workspace_fails_closed=True")
    print("  root_future_keys_preserved=True")
    print("  profile_future_keys_preserved=True")
    print("  profile_uid_revision_snapshot_preserved=True")
    print("  broker_execution_attempted=False")
    print("WORKSPACE_INDICATOR_PROFILE_LIFECYCLE_CHECK=OK")


def _load_profile_blocked(
    repository: WorkspaceIndicatorProfileRepository,
    profile_uid: str,
) -> bool:
    try:
        repository.load_profile(profile_uid)
    except WorkspaceIndicatorProfileRepositoryError:
        return True
    return False


def _assert_future_fields_preserved(
    repository: WorkspaceIndicatorProfileRepository,
    profile_uid: str,
) -> None:
    payload = json.loads(repository.path.read_text(encoding="utf-8"))
    assert payload["future_root"] == {"keep": True}
    item = next(
        entry for entry in payload["profiles"] if entry["profile_uid"] == profile_uid
    )
    assert item["future_profile"] == {"keep": "profile"}


if __name__ == "__main__":
    main()
