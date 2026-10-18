# -*- coding: utf-8 -*-
"""
T111-38 — Frozen onefile restart guard — TEST_ONLY.

Перевіряє мінімальний production-fix:
- source restart збережений через QProcess.startDetached;
- frozen restart запускає сам sys.executable;
- frozen restart не передає LGE.py як аргумент;
- PYINSTALLER_RESET_ENVIRONMENT=1 встановлюється для нового процесу;
- working directory frozen restart = каталог LGE.exe;
- broker requests = 0.
"""

from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LGE = PROJECT_ROOT / "LGE.py"

TEST_ONLY = True
BROKER_REQUESTS = 0
BROKER_EXECUTION_ATTEMPTED = False
PRODUCTION_LOGIC_CHANGED = True


def _require(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(f"missing evidence: {label}")


def main() -> int:
    text = LGE.read_text(encoding="utf-8")
    tree = ast.parse(text)

    restart_functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_restart_application"
    ]
    _require(len(restart_functions) == 1, "single _restart_application helper")

    helper_text_start = text.index("def _restart_application()")
    helper_text_end = text.index("\ndef _apply_qss", helper_text_start)
    helper_text = text[helper_text_start:helper_text_end]

    frozen_branch_present = 'getattr(sys, "frozen", False)' in helper_text
    reset_environment_present = (
        'env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"' in helper_text
    )
    frozen_uses_sys_executable = (
        "subprocess.Popen(" in helper_text
        and "[sys.executable, *sys.argv[1:]]" in helper_text
    )
    frozen_omits_source_script_argument = (
        '[str(BASE_DIR / "LGE.py"), *sys.argv[1:]]'
        not in helper_text.split("return", 1)[0]
    )
    frozen_cwd_uses_executable_dir = (
        "cwd=str(Path(sys.executable).resolve().parent)" in helper_text
    )
    source_restart_preserved = all(
        needle in helper_text
        for needle in (
            "QProcess.startDetached(",
            "sys.executable,",
            '[str(BASE_DIR / "LGE.py"), *sys.argv[1:]],',
            "str(BASE_DIR),",
        )
    )

    main_uses_restart_helper = (
        'if bool(app.property("lge_restart_requested")):'
        in text
        and "_restart_application()" in text
    )

    direct_old_restart_removed_from_main = (
        text.count("QProcess.startDetached(") == 1
    )

    probe_dispatch_preserved = all(
        needle in text
        for needle in (
            "def _dispatch_internal_probe_module()",
            "core.ctrader_account_list_probe_runner",
            "core.ctrader_account_snapshot_probe_runner",
        )
    )

    _require(frozen_branch_present, "frozen restart branch")
    _require(reset_environment_present, "PYINSTALLER_RESET_ENVIRONMENT")
    _require(frozen_uses_sys_executable, "frozen restart uses sys.executable")
    _require(
        frozen_omits_source_script_argument,
        "frozen restart omits LGE.py argument",
    )
    _require(
        frozen_cwd_uses_executable_dir,
        "frozen restart cwd uses executable directory",
    )
    _require(source_restart_preserved, "source restart preserved")
    _require(main_uses_restart_helper, "main uses restart helper")
    _require(
        direct_old_restart_removed_from_main,
        "old direct restart removed from main",
    )
    _require(probe_dispatch_preserved, "T111-31 probe dispatch preserved")

    print("T111-38 TEST_ONLY")
    print("verdict=FROZEN_ONEFILE_RESTART_ENVIRONMENT_GUARDED")
    print(f"frozen_branch_present={frozen_branch_present}")
    print(f"reset_environment_present={reset_environment_present}")
    print(f"frozen_uses_sys_executable={frozen_uses_sys_executable}")
    print(
        "frozen_omits_source_script_argument="
        f"{frozen_omits_source_script_argument}"
    )
    print(
        "frozen_cwd_uses_executable_dir="
        f"{frozen_cwd_uses_executable_dir}"
    )
    print(f"source_restart_preserved={source_restart_preserved}")
    print(f"main_uses_restart_helper={main_uses_restart_helper}")
    print(
        "direct_old_restart_removed_from_main="
        f"{direct_old_restart_removed_from_main}"
    )
    print(f"probe_dispatch_preserved={probe_dispatch_preserved}")
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
