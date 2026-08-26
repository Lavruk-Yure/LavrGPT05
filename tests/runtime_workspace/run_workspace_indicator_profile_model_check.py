# -*- coding: utf-8 -*-
"""Synthetic check for editable MACD/Alligator profile foundation."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import AlgorithmWorkspace  # noqa: E402
from core.workspace_indicator_profile import (  # noqa: E402
    ALLIGATOR_LOGIC_MODE_CANDIDATE_F,
    ALLIGATOR_PROFILE_UID_CTRADER_DEFAULT,
    ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F,
    ALLIGATOR_PROFILE_UID_LGE_CLASSIC,
    ALLIGATOR_PROFILE_UID_TWS_REFERENCE,
    MACD_PROFILE_UID_CTRADER_REFERENCE,
    MACD_PROFILE_UID_LGE_CLASSIC,
    MACD_PROFILE_UID_LGE_DEFAULT,
    MACD_PROFILE_UID_TWS_DEFAULT,
    WORKSPACE_INDICATOR_ALLIGATOR,
    WORKSPACE_INDICATOR_MACD,
    WorkspaceIndicatorProfileBinding,
    WorkspaceIndicatorProfileError,
    built_in_workspace_indicator_profile,
    built_in_workspace_indicator_profiles,
    default_workspace_indicator_profile_bindings,
    merge_workspace_indicator_profile_binding,
    new_workspace_indicator_profile_bindings,
    workspace_indicator_profile_binding,
)
from core.workspace_indicator_profile_repository import (  # noqa: E402
    WorkspaceIndicatorProfileRepository,
    WorkspaceIndicatorProfileRepositoryError,
)


def main() -> None:
    built_ins = built_in_workspace_indicator_profiles()
    assert len(built_ins) == 8
    macd_profiles = tuple(
        profile
        for profile in built_ins
        if profile.indicator_code == WORKSPACE_INDICATOR_MACD
    )
    alligator_profiles = tuple(
        profile
        for profile in built_ins
        if profile.indicator_code == WORKSPACE_INDICATOR_ALLIGATOR
    )
    assert len(macd_profiles) == 4
    assert len(alligator_profiles) == 4

    macd_lge = built_in_workspace_indicator_profile(MACD_PROFILE_UID_LGE_CLASSIC)
    macd_default = built_in_workspace_indicator_profile(
        MACD_PROFILE_UID_LGE_DEFAULT
    )
    macd_tws = built_in_workspace_indicator_profile(MACD_PROFILE_UID_TWS_DEFAULT)
    macd_ctrader = built_in_workspace_indicator_profile(
        MACD_PROFILE_UID_CTRADER_REFERENCE
    )
    alligator_lge = built_in_workspace_indicator_profile(
        ALLIGATOR_PROFILE_UID_LGE_CLASSIC
    )
    alligator_candidate = built_in_workspace_indicator_profile(
        ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F
    )
    alligator_ctrader = built_in_workspace_indicator_profile(
        ALLIGATOR_PROFILE_UID_CTRADER_DEFAULT
    )
    alligator_tws = built_in_workspace_indicator_profile(
        ALLIGATOR_PROFILE_UID_TWS_REFERENCE
    )

    assert macd_lge.usable
    assert macd_default.usable
    assert macd_tws.usable
    assert not macd_ctrader.usable
    assert alligator_lge.usable
    assert alligator_candidate.usable
    assert alligator_ctrader.usable
    assert not alligator_tws.usable

    assert macd_lge.parameters["fast_period"] == 12
    assert macd_lge.parameters["slow_period"] == 26
    assert macd_lge.parameters["signal_period"] == 9
    assert macd_default.parameters["fast_period"] == 8
    assert macd_default.parameters["slow_period"] == 17
    assert macd_default.parameters["signal_period"] == 5
    assert alligator_ctrader.parameters["source"] == "CLOSE"
    assert alligator_ctrader.parameters["ma_type"] == "SIMPLE"
    assert alligator_tws.parameters["jaw_period"] == 21
    assert alligator_candidate.parameters["logic_mode"] == (
        ALLIGATOR_LOGIC_MODE_CANDIDATE_F
    )
    assert alligator_candidate.parameters["trend_start_confirmation_bars"] == 4
    assert alligator_candidate.parameters["deferred_expiry_bars"] == 5
    assert alligator_candidate.parameters["opening_collapse_threshold"] == -0.700

    incomplete_binding_blocked = False
    try:
        WorkspaceIndicatorProfileBinding.from_profile(alligator_tws)
    except WorkspaceIndicatorProfileError:
        incomplete_binding_blocked = True
    assert incomplete_binding_blocked

    defaults = default_workspace_indicator_profile_bindings()
    assert set(defaults) == {"MACD", "ALLIGATOR"}
    legacy_default_binding = WorkspaceIndicatorProfileBinding.from_storage_dict(
        defaults["MACD"]
    )
    assert legacy_default_binding.profile_uid == MACD_PROFILE_UID_LGE_CLASSIC
    fresh_defaults = new_workspace_indicator_profile_bindings()
    assert (
        WorkspaceIndicatorProfileBinding.from_storage_dict(
            fresh_defaults["MACD"]
        ).profile_uid
        == MACD_PROFILE_UID_LGE_DEFAULT
    )
    defaults["FUTURE_INDICATOR"] = {"future_key": "preserved"}

    workspace = AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM000001",
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        parameters={
            "macd_signal_mode": "EXTENDED",
            "alligator_confirmation": "SAME_TIMEFRAME",
            "spread_limit": 0.00018,
            "warmup_bars": 25,
            "future_key": "preserved",
        },
    )
    assert workspace_indicator_profile_binding(
        workspace,
        WORKSPACE_INDICATOR_MACD,
    ).profile_uid == MACD_PROFILE_UID_LGE_DEFAULT
    workspace.set_indicator_profile_bindings(defaults)
    assert workspace.indicator_profile_bindings["FUTURE_INDICATOR"] == {
        "future_key": "preserved"
    }

    with TemporaryDirectory() as tmp_dir:
        repository = WorkspaceIndicatorProfileRepository(Path(tmp_dir))
        repository.ensure_storage()
        assert repository.path.exists()
        raw = json.loads(repository.path.read_text(encoding="utf-8"))
        assert raw == {"schema_version": 1, "profiles": []}

        user_profile = repository.duplicate_profile(
            MACD_PROFILE_UID_LGE_CLASSIC,
            name="MACD Test Profile",
        )
        assert not user_profile.built_in
        assert user_profile.revision == 1

        binding_v1 = WorkspaceIndicatorProfileBinding.from_profile(user_profile)
        bindings_v1 = merge_workspace_indicator_profile_binding(
            workspace.indicator_profile_bindings,
            binding_v1,
        )
        workspace.set_indicator_profile_bindings(bindings_v1)
        snapshot_v1 = workspace_indicator_profile_binding(
            workspace,
            WORKSPACE_INDICATOR_MACD,
        ).profile
        assert snapshot_v1.parameters["fast_period"] == 12

        updated = repository.update_profile(
            user_profile.profile_uid,
            name="MACD Test Profile",
            parameters={
                "source": "CLOSE",
                "fast_period": 8,
                "slow_period": 21,
                "signal_period": 5,
                "oscillator_ma_type": "EXPONENTIAL",
                "signal_ma_type": "EXPONENTIAL",
                "shift": 0,
            },
        )
        assert updated.revision == 2
        assert updated.parameters["fast_period"] == 8

        unchanged_snapshot = workspace_indicator_profile_binding(
            workspace,
            WORKSPACE_INDICATOR_MACD,
        ).profile
        assert unchanged_snapshot.revision == 1
        assert unchanged_snapshot.parameters["fast_period"] == 12

        binding_v2 = WorkspaceIndicatorProfileBinding.from_profile(updated)
        workspace.set_indicator_profile_bindings(
            merge_workspace_indicator_profile_binding(
                workspace.indicator_profile_bindings,
                binding_v2,
            )
        )
        assert workspace_indicator_profile_binding(
            workspace,
            WORKSPACE_INDICATOR_MACD,
        ).profile_revision == 2

        archived = repository.archive_profile(user_profile.profile_uid)
        assert archived.archived
        assert archived.revision == 3
        assert workspace_indicator_profile_binding(
            workspace,
            WORKSPACE_INDICATOR_MACD,
        ).profile_revision == 2

        built_in_edit_blocked = False
        try:
            repository.update_profile(
                MACD_PROFILE_UID_LGE_CLASSIC,
                name="bad",
                parameters=macd_lge.parameters,
            )
        except WorkspaceIndicatorProfileRepositoryError:
            built_in_edit_blocked = True
        assert built_in_edit_blocked

    storage = workspace.to_storage_dict()
    assert storage["schema_version"] == 5
    assert "indicator_profile_bindings" in storage
    restored = AlgorithmWorkspace.from_storage_dict(storage)
    assert workspace_indicator_profile_binding(
        restored,
        WORKSPACE_INDICATOR_MACD,
    ).profile_revision == 2
    assert restored.parameters["spread_limit"] == 0.00018
    assert restored.parameters["warmup_bars"] == 25
    assert restored.parameters["future_key"] == "preserved"
    assert restored.indicator_profile_bindings["FUTURE_INDICATOR"] == {
        "future_key": "preserved"
    }

    legacy_payload = dict(storage)
    legacy_payload["schema_version"] = 4
    legacy_payload.pop("indicator_profile_bindings")
    legacy_restored = AlgorithmWorkspace.from_storage_dict(legacy_payload)
    assert workspace_indicator_profile_binding(
        legacy_restored,
        WORKSPACE_INDICATOR_MACD,
    ).profile_uid == MACD_PROFILE_UID_LGE_CLASSIC

    print("Workspace Indicator Profile Model result")
    print("  built_in_profiles=8")
    print("  alligator_candidate_f_profile=True")
    print("  macd_editable_profile_system=True")
    print("  alligator_editable_profile_system=True")
    print("  incomplete_reference_profiles_not_bindable=True")
    print("  user_profile_revisioning=True")
    print("  built_in_templates_immutable=True")
    print("  archive_without_physical_delete=True")
    print("  workspace_profile_uid_revision_snapshot=True")
    print("  profile_edit_does_not_mutate_old_replay_snapshot=True")
    print("  fresh_workspace_macd_profile=8/17/5")
    print("  legacy_workspace_defaults_migrated=True")
    print("  legacy_spread_warmup_preserved=True")
    print("  future_keys_preserved=True")
    print("  broker_execution_attempted=False")
    print("WORKSPACE_INDICATOR_PROFILE_MODEL_CHECK=OK")


if __name__ == "__main__":
    main()
