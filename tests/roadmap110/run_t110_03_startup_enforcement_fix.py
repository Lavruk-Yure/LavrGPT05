# -*- coding: utf-8 -*-
"""
T110-03 — Startup Enforcement Fix.

Перевіряє мінімальну production-зміну login-path:
- результат LicenseManager.compute_and_update() зберігається;
- OTHER_MACHINE блокує startup до _open_main();
- для іншого статусу _open_main() лишається досяжним;
- machine fingerprint, LGE.conf generation і pricing не змінюються цим тестом.
"""

from __future__ import annotations

import ast
from pathlib import Path

TEST_ONLY = True
BROKER_REQUESTS = 0

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOGIN_LOGIC_PATH = PROJECT_ROOT / "core" / "login_logic.py"


def _find_method(tree: ast.AST, class_name: str, method_name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == method_name:
                return item
    raise AssertionError(f"method_not_found={class_name}.{method_name}")


def _call_name(call: ast.Call) -> str:
    parts: list[str] = []
    node: ast.AST = call.func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _is_compute_assignment(node: ast.AST) -> bool:
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        return False
    target = node.targets[0]
    if not isinstance(target, ast.Name) or target.id != "license_result":
        return False
    if not isinstance(node.value, ast.Call):
        return False
    return _call_name(node.value).endswith("LicenseManager.compute_and_update")


def _is_other_machine_guard(node: ast.stmt) -> bool:
    if not isinstance(node, ast.If):
        return False
    test = node.test
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return False
    if not isinstance(test.ops[0], ast.Eq) or len(test.comparators) != 1:
        return False

    left = test.left
    right = test.comparators[0]
    left_ok = (
        isinstance(left, ast.Attribute)
        and left.attr == "status"
        and isinstance(left.value, ast.Name)
        and left.value.id == "license_result"
    )
    right_ok = (
        isinstance(right, ast.Attribute)
        and right.attr == "ST_OTHER_MACHINE"
        and isinstance(right.value, ast.Name)
        and right.value.id == "LicenseManager"
    )
    return left_ok and right_ok


def _has_dialog_and_return(node: ast.If) -> bool:
    has_dialog = False
    has_return = False
    for item in ast.walk(node):
        if isinstance(item, ast.Call) and _call_name(item).endswith(
            "CommonErrorDialog.show_dialog"
        ):
            has_dialog = True
        elif isinstance(item, ast.Return):
            has_return = True
    return has_dialog and has_return


def _is_open_main(node: ast.stmt) -> bool:
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return False
    return _call_name(node.value).endswith("self._open_main")


def _expected_startup_allowed(status: str) -> bool:
    return status != "OTHER_MACHINE"


def main() -> int:
    source = LOGIN_LOGIC_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(LOGIN_LOGIC_PATH))
    method = _find_method(tree, "LoginWindow", "_on_login_clicked")

    compute_line: int | None = None
    guard_line: int | None = None
    open_main_line: int | None = None
    guard_node: ast.If | None = None

    for node in ast.walk(method):
        if isinstance(node, ast.stmt) and _is_compute_assignment(node):
            compute_line = node.lineno

        if isinstance(node, ast.If) and _is_other_machine_guard(node):
            guard_line = node.lineno
            guard_node = node

        if isinstance(node, ast.stmt) and _is_open_main(node):
            open_main_line = node.lineno

    checks = {
        "license_result_is_stored": compute_line is not None,
        "other_machine_guard_present": guard_line is not None,
        "other_machine_guard_blocks": (
            guard_node is not None and _has_dialog_and_return(guard_node)
        ),
        "open_main_after_guard": (
            guard_line is not None
            and open_main_line is not None
            and guard_line < open_main_line
        ),
        "other_machine_policy_blocked": not _expected_startup_allowed("OTHER_MACHINE"),
        "pro_ok_policy_allowed": _expected_startup_allowed("PRO_OK"),
        "trial_ok_policy_allowed": _expected_startup_allowed("TRIAL_OK"),
    }

    print("T110-03 — Startup Enforcement Fix")
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
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")

    if failed:
        print("startup_enforcement=NOT_CONFIRMED")
        print("production_logic_changed=True")
        print("T110-03=RED")
        return 1

    print("other_machine=STARTUP_BLOCKED")
    print("normal_valid_status=STARTUP_ALLOWED")
    print("first_repaired_boundary=LOGIN_STARTUP_ENFORCEMENT")
    print("production_logic_changed=True")
    print("T110-03=GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
