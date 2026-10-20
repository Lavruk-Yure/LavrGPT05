# -*- coding: utf-8 -*-
"""T110-17 — RoadMap110 Canonical Closure Audit — TEST_ONLY."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

TEST_ONLY = True
BROKER_REQUESTS = 0
PRODUCTION_LOGIC_CHANGED = False


def _source(rel_path: str) -> str:
    return (PROJECT_ROOT / rel_path).read_text(encoding="utf-8")


def _trial_days() -> int | None:
    tree = ast.parse(_source("core/app_meta.py"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(t, ast.Name) and t.id == "TRIAL_DAYS" for t in node.targets
        ):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, int):
            return node.value.value
    return None


def main() -> int:
    login = _source("core/login_logic.py")
    license_manager = _source("core/license_manager.py")
    main_logic = _source("core/main_logic.py")
    dialog = _source("core/ctrader_connection_dialog.py")
    md7 = _source("doc/LGE_Runtime_07.md")

    other_machine_pos = login.find("LicenseManager.ST_OTHER_MACHINE")
    open_main_pos = login.find("self._open_main()", other_machine_pos)

    ctrader_branch = main_logic.split('elif broker_name == "cTrader":', 1)[1]

    checks = {
        "other_machine_blocks_before_main_window": (
            0 <= other_machine_pos < open_main_pos
            and "LoginWindow.errorOtherMachine" in login
            and "return" in login[other_machine_pos:open_main_pos]
        ),
        "trial_duration_is_180_days": _trial_days() == 180,
        "no_license_and_trial_manual_allowed_auto_blocked": (
            "if status in (cls.ST_TRIAL_OK, cls.ST_NO_LICENSE):" in license_manager
            and "live_manual = True" in license_manager
            and "live_semi = False" in license_manager
            and "auto_demo = False" in license_manager
            and "auto_full = False" in license_manager
        ),
        "ctrader_runtime_credentials_come_from_lge_conf": (
            'conf_obj.get("ctrader", "client_id", "")' in main_logic
            and 'conf_obj.get("ctrader", "client_secret", "")' in main_logic
            and 'conf_obj.get("ctrader", "account_id", "")' in main_logic
            and "CTraderAdapter.from_credentials(" in main_logic
        ),
        "ctrader_account_discovery_precedes_runtime_connect": (
            "if not account_id:" in dialog
            and "self._run_account_list_probe_subprocess(" in dialog
            and "self._load_accounts_to_combo(accounts)" in dialog
            and dialog.index("if not account_id:")
            < dialog.index("self._runtime_engine.connect_ctrader_demo")
        ),
        "ctrader_selected_settings_saved_before_runtime_connect": (
            "self._save_to_conf()" in dialog
            and dialog.index("self._save_to_conf()")
            < dialog.index("self._runtime_engine.connect_ctrader_demo")
        ),
        "manual_connect_sets_auto_connect_true": (
            "self._set_ctrader_auto_connect(True)" in dialog
        ),
        "explicit_disconnect_sets_auto_connect_false": (
            "self._set_ctrader_auto_connect(False)" in dialog
        ),
        "startup_ctrader_respects_auto_connect_intent": (
            'auto_ctrader = bool(auto_connect.get("ctrader", False))' in main_logic
            and "if auto_ctrader:" in main_logic
            and "self._startup_connect_ctrader(runtime_engine)" in main_logic
        ),
        "runtime_reconnect_watch_respects_auto_connect_intent": (
            "auto_ctrader = False" in ctrader_branch
            and '.get("ctrader", False)' in ctrader_branch
            and "if auto_ctrader:" in ctrader_branch
            and "runtime_engine.start_ctrader_reconnect_watch()" in ctrader_branch
            and ctrader_branch.index("if auto_ctrader:")
            < ctrader_branch.index("runtime_engine.start_ctrader_reconnect_watch()")
        ),
        "ib_reconnect_gate_preserved": (
            "and auto_ib" in main_logic
            and "runtime_engine.start_ib_reconnect_watch()" in main_logic
        ),
        "md7_contains_roadmap110_canonical_contract": (
            "# 30. RoadMap110" in md7
            and "machine-bound" in md7
            and "auto_connect.ctrader=False" in md7
            and "LAVR-SRV" in md7
            and "canonical closure audit" in md7
        ),
    }

    print("T110-17 — RoadMap110 Canonical Closure Audit — TEST_ONLY")
    print()

    failed = 0
    for name, passed in checks.items():
        state = "PASS" if passed else "FAIL"
        print(f"{state} {name}={passed}")
        failed += 0 if passed else 1

    print()
    print(f"checks={len(checks)}")
    print(f"passed={len(checks) - failed}")
    print(f"failed={failed}")

    if failed:
        print("boundary=ROADMAP110_CANONICAL_CLOSURE_NOT_CONFIRMED")
        print(f"TEST_ONLY={TEST_ONLY}")
        print(f"broker_requests={BROKER_REQUESTS}")
        print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
        print("T110-17=RED")
        return 1

    print("machine_binding_contract=CLOSED")
    print("free_trial_capability_contract=CLOSED")
    print("ctrader_local_config_contract=CLOSED")
    print("ctrader_account_discovery_contract=CLOSED")
    print("ctrader_reconnect_intent_contract=CLOSED")
    print("md7_canonical_coverage=CONFIRMED")
    print("roadmap110_verdict=CANONICAL_CLOSURE_GREEN")
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
    print("T110-17=GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
