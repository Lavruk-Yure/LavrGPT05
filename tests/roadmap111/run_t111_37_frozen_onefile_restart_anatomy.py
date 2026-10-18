# -*- coding: utf-8 -*-
"""
T111-37 — Frozen onefile restart anatomy — TEST_ONLY.

Мета:
- простежити ланцюг restart після успішної активації ліцензії;
- зафіксувати, що LGE.py запускає sys.executable повторно без
  frozen-aware аргументів і без PYINSTALLER_RESET_ENVIRONMENT;
- broker requests = 0;
- production не змінюється.
"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

SETTINGS_PAGE_LICENSE = PROJECT_ROOT / "core" / "settings_page_license.py"
SETTINGS_CENTER = PROJECT_ROOT / "core" / "settings_center.py"
MAIN_LOGIC = PROJECT_ROOT / "core" / "main_logic.py"
LGE = PROJECT_ROOT / "LGE.py"

TEST_ONLY = True
BROKER_REQUESTS = 0
BROKER_EXECUTION_ATTEMPTED = False
PRODUCTION_LOGIC_CHANGED = False


def _require(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(f"missing evidence: {label}")


def main() -> int:
    license_text = SETTINGS_PAGE_LICENSE.read_text(encoding="utf-8")
    center_text = SETTINGS_CENTER.read_text(encoding="utf-8")
    main_text = MAIN_LOGIC.read_text(encoding="utf-8")
    lge_text = LGE.read_text(encoding="utf-8")

    activation_requests_restart = all(
        needle in license_text
        for needle in (
            "license_activation_requires_restart(res.edition)",
            "QTimer.singleShot(0, self._request_restart_after_activation)",
            "callback = self._on_license_restart_requested",
        )
    )

    settings_center_routes_restart = all(
        needle in center_text
        for needle in (
            "def _on_license_restart_requested",
            '"request_application_restart"',
            "restart()",
        )
    )

    main_logic_sets_restart_property = all(
        needle in main_text
        for needle in (
            "def request_application_restart",
            'app.setProperty("lge_restart_requested", True)',
            "self.close()",
            "app.quit()",
        )
    )

    lge_restarts_sys_executable = all(
        needle in lge_text
        for needle in (
            'app.property("lge_restart_requested")',
            "QProcess.startDetached(",
            "sys.executable,",
            '[str(BASE_DIR / "LGE.py"), *sys.argv[1:]],',
            "str(BASE_DIR),",
        )
    )

    frozen_restart_branch_present = any(
        needle in lge_text
        for needle in (
            'getattr(sys, "frozen"',
            "getattr(sys, 'frozen'",
            "sys.frozen",
        )
    )

    pyinstaller_reset_environment_present = (
        "PYINSTALLER_RESET_ENVIRONMENT" in lge_text
    )

    _require(
        activation_requests_restart,
        "successful activation schedules application restart",
    )
    _require(
        settings_center_routes_restart,
        "settings center routes license restart to main window",
    )
    _require(
        main_logic_sets_restart_property,
        "main logic sets lge_restart_requested",
    )
    _require(
        lge_restarts_sys_executable,
        "LGE.py restarts sys.executable with source-script argument",
    )
    _require(
        not frozen_restart_branch_present,
        "frozen-aware restart branch is absent",
    )
    _require(
        not pyinstaller_reset_environment_present,
        "PYINSTALLER_RESET_ENVIRONMENT handling is absent",
    )

    print("T111-37 TEST_ONLY")
    print("verdict=FROZEN_ONEFILE_RESTART_ENVIRONMENT_BROKEN")
    print(f"activation_requests_restart={activation_requests_restart}")
    print(f"settings_center_routes_restart={settings_center_routes_restart}")
    print(
        "main_logic_sets_restart_property="
        f"{main_logic_sets_restart_property}"
    )
    print(f"lge_restarts_sys_executable={lge_restarts_sys_executable}")
    print(
        "frozen_restart_branch_present="
        f"{frozen_restart_branch_present}"
    )
    print(
        "pyinstaller_reset_environment_present="
        f"{pyinstaller_reset_environment_present}"
    )
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
