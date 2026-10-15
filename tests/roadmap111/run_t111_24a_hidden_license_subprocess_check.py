# -*- coding: utf-8 -*-
"""T111-24A TEST_ONLY: перевірка прихованих license subprocess у Windows."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "core" / "license_manager.py"


def _function_node(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Function not found: {name}")


def _has_hidden_kwargs_expansion(node: ast.FunctionDef) -> bool:
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        if not isinstance(call.func, ast.Attribute):
            continue
        if call.func.attr != "run":
            continue
        for keyword in call.keywords:
            if keyword.arg is not None:
                continue
            value = keyword.value
            if not isinstance(value, ast.Call):
                continue
            if (
                isinstance(value.func, ast.Name)
                and value.func.id == "_hidden_subprocess_kwargs"
            ):
                return True
    return False


def main() -> int:
    source = SOURCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    hidden_helper = _function_node(tree, "_hidden_subprocess_kwargs")
    machine_guid = _function_node(tree, "_read_machine_guid")
    system_uuid = _function_node(tree, "_read_system_uuid")

    helper_source = ast.get_source_segment(source, hidden_helper) or ""
    machine_guid_source = ast.get_source_segment(source, machine_guid) or ""
    system_uuid_source = ast.get_source_segment(source, system_uuid) or ""

    helper_uses_windows_guard = 'os.name != "nt"' in helper_source
    helper_uses_create_no_window = "subprocess.CREATE_NO_WINDOW" in helper_source
    reg_hidden_window = _has_hidden_kwargs_expansion(machine_guid)
    powershell_hidden_window = _has_hidden_kwargs_expansion(system_uuid)

    machine_guid_command_preserved = all(
        token in machine_guid_source
        for token in (
            '"reg"',
            '"query"',
            'r"HKLM\\SOFTWARE\\Microsoft\\Cryptography"',
            '"MachineGuid"',
        )
    )
    system_uuid_command_preserved = all(
        token in system_uuid_source
        for token in (
            '"powershell"',
            '"-NoProfile"',
            "Get-CimInstance Win32_ComputerSystemProduct",
        )
    )
    machine_id_formula_preserved = (
        'raw = f"LGE|v1|{mg}|{su}|{cls._SALT}"' in source
        and 'hashlib.sha256(raw.encode("utf-8")).hexdigest()' in source
    )

    assert helper_uses_windows_guard
    assert helper_uses_create_no_window
    assert reg_hidden_window
    assert powershell_hidden_window
    assert machine_guid_command_preserved
    assert system_uuid_command_preserved
    assert machine_id_formula_preserved

    print("T111-24A TEST_ONLY")
    print("verdict=LICENSE_SUBPROCESS_WINDOWS_HIDDEN")
    print(f"windows_guard_present={helper_uses_windows_guard}")
    print(f"create_no_window_present={helper_uses_create_no_window}")
    print(f"reg_hidden_window={reg_hidden_window}")
    print(f"powershell_hidden_window={powershell_hidden_window}")
    print(f"machine_guid_command_preserved={machine_guid_command_preserved}")
    print(f"system_uuid_command_preserved={system_uuid_command_preserved}")
    print(f"machine_id_formula_preserved={machine_id_formula_preserved}")
    print("broker_requests=0")
    print("broker_execution_attempted=False")
    print("production_logic_changed=True")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
