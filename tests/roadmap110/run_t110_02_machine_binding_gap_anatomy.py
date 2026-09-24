# -*- coding: utf-8 -*-
"""
T110-02 — Machine Binding Gap Anatomy — TEST_ONLY.

Перевіряє лише фактичний production source path:
- LicenseManager має machine binding та статус OTHER_MACHINE;
- OTHER_MACHINE повертається як fatal=False;
- login викликає compute_and_update();
- результат license check не використовується як startup gate;
- після перевірки login відкриває MainAppWindow.

Production-файли не імпортуються і не змінюються.
"""

from __future__ import annotations

import ast
from pathlib import Path

TEST_ONLY = True
BROKER_REQUESTS = 0
PRODUCTION_LOGIC_CHANGED = False

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LICENSE_MANAGER_PATH = PROJECT_ROOT / "core" / "license_manager.py"
LOGIN_LOGIC_PATH = PROJECT_ROOT / "core" / "login_logic.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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


def _has_call(node: ast.AST, suffix: str) -> bool:
    return any(
        isinstance(item, ast.Call) and _call_name(item).endswith(suffix)
        for item in ast.walk(node)
    )


def _compute_result_is_discarded(method: ast.FunctionDef) -> bool:
    for node in ast.walk(method):
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        if _call_name(node.value).endswith("LicenseManager.compute_and_update"):
            return True
    return False


def _literal_keyword(call: ast.Call, name: str):
    for keyword in call.keywords:
        if keyword.arg != name:
            continue
        if isinstance(keyword.value, ast.Constant):
            return keyword.value.value
    return object()


def _other_machine_return_is_nonfatal(
    source: str,
    method: ast.FunctionDef,
) -> bool:
    for node in ast.walk(method):
        if not isinstance(node, ast.If):
            continue

        segment = ast.get_source_segment(source, node) or ""
        if "ST_OTHER_MACHINE" not in segment:
            continue

        for item in ast.walk(node):
            if not isinstance(item, ast.Return):
                continue
            if not isinstance(item.value, ast.Call):
                continue
            if not _call_name(item.value).endswith("LicenseResult"):
                continue

            fatal = _literal_keyword(item.value, "fatal")
            fatal_reason = _literal_keyword(item.value, "fatal_reason")
            if fatal is False and fatal_reason is None:
                return True

    return False


def main() -> int:
    license_source = _read(LICENSE_MANAGER_PATH)
    login_source = _read(LOGIN_LOGIC_PATH)

    license_tree = ast.parse(license_source, filename=str(LICENSE_MANAGER_PATH))
    login_tree = ast.parse(login_source, filename=str(LOGIN_LOGIC_PATH))

    compute_method = _find_method(
        license_tree,
        "LicenseManager",
        "compute_and_update",
    )
    login_method = _find_method(
        login_tree,
        "LoginWindow",
        "_on_login_clicked",
    )

    login_segment = ast.get_source_segment(login_source, login_method) or ""

    checks = {
        "machine_id_candidates_present": _has_call(
            compute_method,
            "compute_machine_id_candidates",
        ),
        "other_machine_status_present": "ST_OTHER_MACHINE" in license_source,
        "other_machine_return_is_nonfatal": _other_machine_return_is_nonfatal(
            license_source,
            compute_method,
        ),
        "login_calls_license_check": _has_call(
            login_method,
            "LicenseManager.compute_and_update",
        ),
        "login_discards_license_result": _compute_result_is_discarded(login_method),
        "login_opens_main_after_check": _has_call(login_method, "self._open_main"),
        "login_has_no_other_machine_gate": "OTHER_MACHINE" not in login_segment,
    }

    print("T110-02 — Machine Binding Gap Anatomy — TEST_ONLY")
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
        print("boundary=ANATOMY_NOT_CONFIRMED")
        print(f"TEST_ONLY={TEST_ONLY}")
        print(f"broker_requests={BROKER_REQUESTS}")
        print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
        print("T110-02=RED")
        return 1

    print("machine_binding_detection=EXISTS")
    print("other_machine_status=NON_FATAL")
    print("login_license_result=DISCARDED")
    print("startup_gate_after_license_check=ABSENT")
    print("first_broken_boundary=LOGIN_STARTUP_ENFORCEMENT")
    print("verdict=TRANSFER_PROTECTION_DETECTED_BUT_NOT_ENFORCED_AT_LOGIN")
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
    print("T110-02=GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
