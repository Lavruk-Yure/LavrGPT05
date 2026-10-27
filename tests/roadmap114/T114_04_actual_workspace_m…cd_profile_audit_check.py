"""T114-04 — read-only аудит збережених MACD-профілів EURUSD M15.

TEST_ONLY: лише Session JSON; без запуску брокера або зміни production.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SESSION = ROOT / "Session"


def load_module(name: str):
    """Завантажити модулі LGE без статичних імпортів після sys.path."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    return importlib.import_module(name)


def digest(value: bytes) -> str:
    """Незалежний від порядку перевірок SHA256."""
    return hashlib.sha256(value).hexdigest()


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def diff_keys(left: dict, right: dict, prefix: str = "") -> list[str]:
    """Знайти точні поля відмінностей між двома конфігураціями."""
    result = []
    for key in sorted(left.keys() | right.keys()):
        a, b = left.get(key), right.get(key)
        name = f"{prefix}{key}"
        if isinstance(a, dict) and isinstance(b, dict):
            result += diff_keys(a, b, name + ".")
        elif a != b:
            result.append(name)
    return result


def config_from_workspace(workspace, runtime_class, macd_class):
    """Відтворити тільки MACD-конфігурацію штатним кодом LGE."""
    context = runtime_class.from_workspace(workspace)
    source = macd_class.from_runtime_context(context, workspace.parameters)
    profile = asdict(source.runtime_profile)
    profile.pop("profile_name")
    gates = {
        "enabled": source.enabled,
        "mode": source.mode,
        "min_prominence": source.extremum_min_prominence,
        "min_distance": source.extremum_to_cross_min_distance,
        "min_angle": source.cross_min_angle_degrees,
        "angle_model": source.angle_model,
        "min_abc_angle": source.cross_min_abc_angle_degrees,
        "abc_scale": source.abc_indicator_value_scale,
    }
    other_stored = {
        key: workspace.parameters.get(key)
        for key in ("alligator_filter_enabled", "alligator_confirmation", "warmup_bars")
    }
    return (
        context,
        source,
        {"profile": profile, "macd_gates": gates, "other_stored": other_stored},
    )


def main():
    """Перевірити persisted snapshots; live volatile state не підміняти."""
    manifest_path = SESSION / "session.json"
    if not manifest_path.is_file():
        print("T114-04|STATUS=INSUFFICIENT_DATA|reason=NO_SESSION_JSON")
        return
    repo_class = load_module("core.session_repository").SessionRepository
    runtime_class = load_module("core.workspace_runtime").WorkspaceRuntimeContext
    macd_class = load_module("core.workspace_macd").WorkspaceMacdSignalSource
    repo = repo_class(session_dir=SESSION)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    order = manifest["workspace_order"]
    assert isinstance(order, list) and len(order) == len(set(order))
    files = [manifest_path] + list((SESSION / "workspaces").glob("*.json"))
    catalog = SESSION / "indicator_profiles.json"
    if catalog.is_file():
        files.append(catalog)
    original = {path: digest(path.read_bytes()) for path in files}
    records = []
    print("T114-04|EURUSD|M15|PERSISTED_MACD_PROFILE_AUDIT")
    print("mode=TEST_ONLY|source=SESSION_JSON|broker_requests=0")
    print(
        f"manifest_workspaces={len(order)}|"
        f"workspace_files={len(files) - 1 - int(catalog.is_file())}"
    )
    for uid in order:
        path = repo.workspace_path(uid)
        if not path.is_file():
            print(f"MISSING_WORKSPACE_FILE|uid:{uid}")
            continue
        stored = json.loads(path.read_text(encoding="utf-8-sig"))
        if stored.get("symbol") != "EURUSD" or stored.get("timeframe") != "M15":
            continue
        if stored.get("broker") not in {"CTRADER", "IB", "IBKR"}:
            continue
        assert "MACD" in stored.get("indicator_profile_bindings", {})
        workspace = repo.load_workspace(uid)
        context, source, config = config_from_workspace(
            workspace, runtime_class, macd_class
        )
        binding = stored["indicator_profile_bindings"]["MACD"]
        assert binding["profile_uid"] == source.profile_uid
        assert binding["profile_revision"] == source.profile_revision
        assert binding["resolved_profile_snapshot"]["parameters"] == {
            "source": source.runtime_profile.source,
            "fast_period": source.runtime_profile.fast_period,
            "slow_period": source.runtime_profile.slow_period,
            "signal_period": source.runtime_profile.signal_period,
            "oscillator_ma_type": source.runtime_profile.oscillator_ma_type,
            "signal_ma_type": source.runtime_profile.signal_ma_type,
            "shift": source.runtime_profile.shift,
        }
        records.append((workspace, config))
        fingerprint = digest(canonical(config).encode("utf-8"))[:16]
        print(
            f"workspace|broker:{workspace.broker}|uid:{uid}|"
            f"data_mode:{workspace.data_mode}|algorithm:{workspace.algorithm}|"
            f"config_sha16:{fingerprint}"
        )
        print(f"profile={canonical(config['profile'])}")
        print(f"macd_gates={canonical(config['macd_gates'])}")
        print(f"other_stored={canonical(config['other_stored'])}")
        print(
            f"simulated_restore={context.restored_from_session}|"
            f"processed_bars:{context.warmup_bars_processed}|"
            "live_runtime_state=NOT_AVAILABLE"
        )
    cts = [(w, c) for w, c in records if w.broker == "CTRADER"]
    ibs = [(w, c) for w, c in records if w.broker in {"IB", "IBKR"}]
    pairs = 0
    for ct, ct_config in cts:
        for ib, ib_config in ibs:
            if ct.algorithm != ib.algorithm:
                continue
            pairs += 1
            differences = diff_keys(ct_config, ib_config)
            print(
                f"pair|ct:{ct.workspace_uid}|ib:{ib.workspace_uid}|"
                f"matching:{not differences}|"
                f"different_fields:{','.join(differences) if differences else 'NONE'}"
            )
    assert all(
        digest(path.read_bytes()) == expected for path, expected in original.items()
    )
    print(f"cross_broker_pair_count={pairs}")
    print("comparison=RECORDED" if pairs else "comparison=NOT_VERIFIED_NO_IB_WSP")
    print("actual_post_restart_runtime_state=NOT_VERIFIED")
    print("files_unchanged=True|broker_requests=0|production_changed=False")
    print("T114_04_PERSISTED_PROFILE_AUDIT=OK")


if __name__ == "__main__":
    main()
