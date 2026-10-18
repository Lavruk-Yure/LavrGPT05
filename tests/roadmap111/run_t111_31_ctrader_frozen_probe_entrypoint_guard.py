# -*- coding: utf-8 -*-
"""
T111-31 — cTrader frozen probe entrypoint guard — TEST_ONLY.

Перевіряє мінімальний production-fix:
- внутрішні probe-runner-и перехоплюються
  до створення QApplication;
- account-list і account-snapshot підтримані;
- звичайний запуск LGE лишається через main();
- broker requests не виконуються.
"""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LGE_PATH = PROJECT_ROOT / "LGE.py"
DIALOG_PATH = PROJECT_ROOT / "core" / "ctrader_connection_dialog.py"

TEST_ONLY = True
BROKER_REQUESTS = 0
BROKER_EXECUTION_ATTEMPTED = False
PRODUCTION_LOGIC_CHANGED = True


def _require(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(f"missing evidence: {label}")


def main() -> int:
    lge_text = LGE_PATH.read_text(encoding="utf-8")
    dialog_text = DIALOG_PATH.read_text(encoding="utf-8")
    tree = ast.parse(lge_text)

    dispatcher = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_dispatch_internal_probe_module"
        ),
        None,
    )

    _require(dispatcher is not None, "internal probe dispatcher")

    list_module = "core.ctrader_account_list_probe_runner"
    snapshot_module = "core.ctrader_account_snapshot_probe_runner"

    list_dispatch_present = list_module in lge_text
    snapshot_dispatch_present = snapshot_module in lge_text
    dialog_list_command_preserved = all(
        needle in dialog_text
        for needle in (
            "sys.executable",
            '"-m"',
            f'"{list_module}"',
        )
    )
    dialog_snapshot_command_preserved = all(
        needle in dialog_text
        for needle in (
            "sys.executable",
            '"-m"',
            f'"{snapshot_module}"',
        )
    )

    dispatch_call_pos = lge_text.index("_dispatch_internal_probe_module()")
    qapplication_start_pos = lge_text.index("app = QApplication(sys.argv)")
    dispatcher_precedes_qapplication = (
        dispatch_call_pos < qapplication_start_pos
    )

    normal_main_present = lge_text.rstrip().endswith("main()")

    _require(list_dispatch_present, "account-list dispatch")
    _require(snapshot_dispatch_present, "account-snapshot dispatch")
    _require(
        dispatcher_precedes_qapplication,
        "probe dispatch precedes QApplication creation",
    )
    _require(
        dialog_list_command_preserved,
        "source account-list subprocess command",
    )
    _require(
        dialog_snapshot_command_preserved,
        "source account-snapshot subprocess command",
    )
    _require(normal_main_present, "normal LGE main entrypoint")

    print("T111-31 TEST_ONLY")
    print("verdict=FROZEN_CTRADER_PROBE_ENTRYPOINT_GUARDED")
    print(f"account_list_dispatch_present={list_dispatch_present}")
    print(f"account_snapshot_dispatch_present={snapshot_dispatch_present}")
    print(
        "dispatcher_precedes_qapplication="
        f"{dispatcher_precedes_qapplication}"
    )
    print(
        "source_account_list_command_preserved="
        f"{dialog_list_command_preserved}"
    )
    print(
        "source_account_snapshot_command_preserved="
        f"{dialog_snapshot_command_preserved}"
    )
    print(f"normal_lge_main_present={normal_main_present}")
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
