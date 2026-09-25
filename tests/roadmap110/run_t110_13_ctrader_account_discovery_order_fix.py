# -*- coding: utf-8 -*-
"""
T110-13 — cTrader Account Discovery Order Fix.

Перевіряє мінімальний production fix без broker requests:
- за відсутності account_id Connect спочатку запускає account-list probe;
- отримані рахунки завантажуються в combo;
- ця гілка завершується до RuntimeEngine connect;
- коли account_id вже вибраний, поточні GUI settings зберігаються в LGE.conf;
- лише після save виконується RuntimeEngine connect;
- OAuth як і раніше переходить у _on_test_connection(), але цей шлях тепер безпечний.
"""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

TEST_ONLY = True
BROKER_REQUESTS = 0
PRODUCTION_LOGIC_CHANGED = True


def _source(rel_path: str) -> str:
    return (PROJECT_ROOT / rel_path).read_text(encoding="utf-8")


def _parse(rel_path: str) -> ast.Module:
    return ast.parse(_source(rel_path), filename=rel_path)


def _find_method(
    tree: ast.AST,
    class_name: str,
    method_name: str,
) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue

        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == method_name:
                return item

    raise AssertionError(f"method_not_found={class_name}.{method_name}")


def _call_name(call: ast.Call) -> str:
    parts: list[str] = []
    node: ast.expr = call.func

    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value

    if isinstance(node, ast.Name):
        parts.append(node.id)

    return ".".join(reversed(parts))


def _call_lines(node: ast.AST, suffix: str) -> list[int]:
    return sorted(
        item.lineno
        for item in ast.walk(node)
        if isinstance(item, ast.Call) and _call_name(item).endswith(suffix)
    )


def _has_return(node: ast.AST) -> bool:
    return any(isinstance(item, ast.Return) for item in ast.walk(node))


def _find_account_missing_branch(method: ast.FunctionDef) -> ast.If | None:
    for node in ast.walk(method):
        if not isinstance(node, ast.If):
            continue

        if_node: ast.If = node
        segment = (
            ast.get_source_segment(
                _source("core/ctrader_connection_dialog.py"),
                if_node,
            )
            or ""
        )

        if "if not account_id:" in segment:
            return if_node

    return None


def main() -> int:
    tree = _parse("core/ctrader_connection_dialog.py")

    test_connection = _find_method(
        tree,
        "CTraderConnectionDialog",
        "_on_test_connection",
    )
    oauth_click = _find_method(
        tree,
        "CTraderConnectionDialog",
        "_on_ctrader_oauth_clicked",
    )

    missing_branch = _find_account_missing_branch(test_connection)

    probe_lines = _call_lines(
        test_connection,
        "self._run_account_list_probe_subprocess",
    )
    load_lines = _call_lines(test_connection, "self._load_accounts_to_combo")
    save_lines = _call_lines(test_connection, "self._save_to_conf")
    demo_lines = _call_lines(
        test_connection,
        "self._runtime_engine.connect_ctrader_demo",
    )
    live_lines = _call_lines(
        test_connection,
        "self._runtime_engine.connect_ctrader_live",
    )
    runtime_lines = sorted(demo_lines + live_lines)

    branch_probe_lines = (
        _call_lines(missing_branch, "self._run_account_list_probe_subprocess")
        if missing_branch is not None
        else []
    )
    branch_load_lines = (
        _call_lines(missing_branch, "self._load_accounts_to_combo")
        if missing_branch is not None
        else []
    )
    branch_runtime_lines = (
        sorted(
            _call_lines(missing_branch, "self._runtime_engine.connect_ctrader_demo")
            + _call_lines(missing_branch, "self._runtime_engine.connect_ctrader_live")
        )
        if missing_branch is not None
        else []
    )

    source = _source("core/ctrader_connection_dialog.py")
    method_segment = ast.get_source_segment(source, test_connection) or ""

    checks = {
        "account_id_is_read_from_combo": (
            'account_id = str(self.ui.comboAccountId.currentData() or "").strip()'
            in method_segment
        ),
        "missing_account_branch_present": missing_branch is not None,
        "missing_account_branch_runs_probe": bool(branch_probe_lines),
        "missing_account_branch_loads_combo": bool(branch_load_lines),
        "missing_account_branch_returns_before_runtime": (
            missing_branch is not None
            and _has_return(missing_branch)
            and not branch_runtime_lines
        ),
        "save_occurs_before_runtime_connect": (
            bool(save_lines)
            and bool(runtime_lines)
            and min(save_lines) < min(runtime_lines)
        ),
        "runtime_connect_still_present": bool(runtime_lines),
        "oauth_still_enters_safe_test_connection_path": bool(
            _call_lines(oauth_click, "self._on_test_connection")
        ),
        "probe_precedes_first_runtime_connect": (
            bool(probe_lines)
            and bool(runtime_lines)
            and min(probe_lines) < min(runtime_lines)
        ),
        "combo_load_precedes_first_runtime_connect": (
            bool(load_lines)
            and bool(runtime_lines)
            and min(load_lines) < min(runtime_lines)
        ),
    }

    print("T110-13 — cTrader Account Discovery Order Fix")
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
        print("boundary=CTRADER_ACCOUNT_DISCOVERY_ORDER_NOT_REPAIRED")
        print(f"TEST_ONLY={TEST_ONLY}")
        print(f"broker_requests={BROKER_REQUESTS}")
        print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
        print("T110-13=RED")
        return 1

    print("missing_account_id=ACCOUNT_LIST_PROBE_FIRST")
    print("account_list_loaded_before_runtime_connect=True")
    print("selected_account_saved_before_runtime_connect=True")
    print("oauth_path=SAFE_FOR_NEW_MACHINE")
    print("first_repaired_boundary=CTRADER_ACCOUNT_DISCOVERY_ORDER")
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
    print("T110-13=GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
