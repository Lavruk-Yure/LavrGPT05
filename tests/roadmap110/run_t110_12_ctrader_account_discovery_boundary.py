# -*- coding: utf-8 -*-
"""
T110-12 — cTrader Account Discovery Boundary — TEST_ONLY.

Перевіряє фактичний production path без production-змін:
- OAuth зберігає token state;
- після OAuth викликається _on_test_connection();
- _on_test_connection() одразу йде в RuntimeEngine connect;
- RuntimeEngine adapter factory вимагає account_id з LGE.conf;
- account-list probe без RuntimeEngine уже існує;
- цей probe не викликається з _on_test_connection();
- account_id записується в conf лише якщо combo вже має currentData().

Ціль — підтвердити замкнену межу account discovery на новій машині.
"""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

TEST_ONLY = True
BROKER_REQUESTS = 0
PRODUCTION_LOGIC_CHANGED = False


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


def _find_function(tree: ast.AST, function_name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return node

    raise AssertionError(f"function_not_found={function_name}")


def _call_name(call: ast.Call) -> str:
    parts: list[str] = []
    node: ast.expr = call.func

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


def _save_account_id_is_conditional(
    save_method: ast.FunctionDef,
    dialog_source: str,
) -> bool:
    for node in ast.walk(save_method):
        if not isinstance(node, ast.If):
            continue

        if_node: ast.If = node
        segment = ast.get_source_segment(dialog_source, if_node) or ""

        if (
            "account_data" in segment
            and 'conf_obj.set("ctrader", "account_id", account_data)' in segment
        ):
            return True

    return False


def main() -> int:
    dialog_source = _source("core/ctrader_connection_dialog.py")
    oauth_source = _source("core/ctrader_oauth_flow.py")
    main_source = _source("core/main_logic.py")
    probe_source = _source("core/ctrader_account_list_probe.py")
    runner_source = _source("core/ctrader_account_list_probe_runner.py")

    dialog_tree = _parse("core/ctrader_connection_dialog.py")
    oauth_tree = _parse("core/ctrader_oauth_flow.py")
    main_tree = _parse("core/main_logic.py")

    oauth_click = _find_method(
        dialog_tree,
        "CTraderConnectionDialog",
        "_on_ctrader_oauth_clicked",
    )
    test_connection = _find_method(
        dialog_tree,
        "CTraderConnectionDialog",
        "_on_test_connection",
    )
    save_to_conf = _find_method(
        dialog_tree,
        "CTraderConnectionDialog",
        "_save_to_conf",
    )
    account_probe = _find_method(
        dialog_tree,
        "CTraderConnectionDialog",
        "_run_account_list_probe_subprocess",
    )
    create_adapter = _find_function(
        main_tree,
        "_create_ctrader_adapter_from_config",
    )
    oauth_run = _find_method(
        oauth_tree,
        "CTraderOAuthFlow",
        "run",
    )

    create_adapter_source = ast.get_source_segment(main_source, create_adapter) or ""

    checks = {
        "oauth_saves_token_state": (
            _has_call(oauth_run, "self._save_result") and "tokens.json" in oauth_source
        ),
        "oauth_calls_test_connection_after_success": (
            _has_call(oauth_click, "self._on_test_connection")
        ),
        "test_connection_calls_runtime_demo_or_live": (
            _has_call(test_connection, "self._runtime_engine.connect_ctrader_demo")
            or _has_call(test_connection, "self._runtime_engine.connect_ctrader_live")
        ),
        "runtime_adapter_requires_account_id_from_conf": (
            'conf_obj.get("ctrader", "account_id", "")' in create_adapter_source
            and 'raise RuntimeError("cTrader Account ID не задано в LGE.conf")'
            in create_adapter_source
            and "CTraderAdapter.from_credentials" in create_adapter_source
        ),
        "account_list_probe_exists": (
            "_run_account_list_probe_subprocess" in dialog_source
            and "core.ctrader_account_list_probe_runner" in dialog_source
            and "ProtoOAGetAccountListByAccessTokenReq" in probe_source
            and "refresh_if_needed()" in runner_source
        ),
        "account_list_probe_not_used_by_test_connection": (
            not _has_call(
                test_connection,
                "self._run_account_list_probe_subprocess",
            )
        ),
        "account_id_saved_only_after_combo_has_data": (
            _save_account_id_is_conditional(
                save_to_conf,
                dialog_source,
            )
        ),
        "account_probe_can_run_without_runtime_engine": (
            "Не запускає RuntimeEngine." in probe_source
            and not _has_call(
                account_probe,
                "self._runtime_engine.connect_ctrader_demo",
            )
            and not _has_call(
                account_probe,
                "self._runtime_engine.connect_ctrader_live",
            )
        ),
    }

    print("T110-12 — cTrader Account Discovery Boundary — TEST_ONLY")
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
        print("boundary=ACCOUNT_DISCOVERY_ANATOMY_NOT_CONFIRMED")
        print(f"TEST_ONLY={TEST_ONLY}")
        print(f"broker_requests={BROKER_REQUESTS}")
        print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
        print("T110-12=RED")
        return 1

    print("oauth_state=OK")
    print("account_list_probe=EXISTS_WITHOUT_RUNTIME_ENGINE")
    print("oauth_success_next_step=RUNTIME_CONNECT")
    print("runtime_connect_requires_saved_account_id=True")
    print("account_id_save_depends_on_loaded_combo=True")
    print("account_probe_used_before_runtime_connect=False")
    print("first_broken_boundary=CTRADER_ACCOUNT_DISCOVERY_ORDER")
    print("verdict=ACCOUNT_DISCOVERY_EXISTS_BUT_IS_BYPASSED_BEFORE_RUNTIME_CONNECT")
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
    print("T110-12=GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
