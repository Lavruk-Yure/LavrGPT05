# -*- coding: utf-8 -*-
"""
T111-34 — cTrader frozen probe entrypoint anatomy — TEST_ONLY.

Мета:
- довести, чому standalone LGE.exe відкриває друге Login-вікно;
- довести, чому account-list probe зависає до timeout;
- не виконувати broker requests;
- не змінювати production.
"""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DIALOG_PATH = PROJECT_ROOT / "core" / "ctrader_connection_dialog.py"
LGE_PATH = PROJECT_ROOT / "LGE.py"
BUILD_CONFIG_PATH = PROJECT_ROOT / "Конфігурація auto py to exe.json"

TEST_ONLY = True
BROKER_REQUESTS = 0
BROKER_EXECUTION_ATTEMPTED = False
PRODUCTION_LOGIC_CHANGED = False


def _require(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(f"missing evidence: {label}")


def main() -> int:
    dialog_text = DIALOG_PATH.read_text(encoding="utf-8")
    lge_text = LGE_PATH.read_text(encoding="utf-8")
    build_config = json.loads(
        BUILD_CONFIG_PATH.read_text(encoding="utf-8")
    )

    pyinstaller_options = {
        item.get("optionDest"): item.get("value")
        for item in build_config.get("pyinstallerOptions", [])
        if isinstance(item, dict)
    }

    pyinstaller_onefile = pyinstaller_options.get("onefile") is True
    pyinstaller_windowed = pyinstaller_options.get("console") is False

    list_probe_uses_sys_executable_m = all(
        needle in dialog_text
        for needle in (
            "sys.executable",
            '"-m"',
            '"core.ctrader_account_list_probe_runner"',
        )
    )

    snapshot_probe_uses_sys_executable_m = all(
        needle in dialog_text
        for needle in (
            "sys.executable",
            '"-m"',
            '"core.ctrader_account_snapshot_probe_runner"',
        )
    )

    lge_has_module_dispatch = any(
        needle in lge_text
        for needle in (
            'sys.argv[1] == "-m"',
            "sys.argv[1] == '-m'",
            '"core.ctrader_account_list_probe_runner" in sys.argv',
            '"core.ctrader_account_snapshot_probe_runner" in sys.argv',
        )
    )

    lge_starts_qapplication = "app = QApplication(sys.argv)" in lge_text

    frozen_command_reexecutes_main_exe = (
        pyinstaller_onefile
        and list_probe_uses_sys_executable_m
        and not lge_has_module_dispatch
        and lge_starts_qapplication
    )

    _require(pyinstaller_onefile, "PyInstaller onefile build")
    _require(pyinstaller_windowed, "PyInstaller windowed build")
    _require(
        list_probe_uses_sys_executable_m,
        "account-list probe uses sys.executable -m",
    )
    _require(
        snapshot_probe_uses_sys_executable_m,
        "snapshot probe uses sys.executable -m",
    )
    _require(
        not lge_has_module_dispatch,
        "LGE.py has no frozen -m module dispatch",
    )
    _require(
        frozen_command_reexecutes_main_exe,
        "frozen probe command re-enters main GUI executable",
    )

    verdict = "FROZEN_CTRADER_PROBE_ENTRYPOINT_BROKEN"

    print("T111-34 TEST_ONLY")
    print(f"verdict={verdict}")
    print(f"pyinstaller_onefile={pyinstaller_onefile}")
    print(f"pyinstaller_windowed={pyinstaller_windowed}")
    print(
        "account_list_uses_sys_executable_m="
        f"{list_probe_uses_sys_executable_m}"
    )
    print(
        "account_snapshot_uses_sys_executable_m="
        f"{snapshot_probe_uses_sys_executable_m}"
    )
    print(f"lge_has_module_dispatch={lge_has_module_dispatch}")
    print(f"lge_starts_qapplication={lge_starts_qapplication}")
    print(
        "frozen_command_reexecutes_main_exe="
        f"{frozen_command_reexecutes_main_exe}"
    )
    print("account_list_timeout_is_consistent_with_boundary=True")
    print("second_login_window_is_consistent_with_boundary=True")
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(
        "broker_execution_attempted="
        f"{BROKER_EXECUTION_ATTEMPTED}"
    )
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
