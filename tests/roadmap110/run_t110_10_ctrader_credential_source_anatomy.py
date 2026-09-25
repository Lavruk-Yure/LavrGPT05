# -*- coding: utf-8 -*-
"""
T110-10 — cTrader Credential Source Anatomy — TEST_ONLY.

Перевіряє фактичний production path без broker requests:
- GUI зберігає client_id/client_secret у LGE.conf;
- OAuth бере credentials з GUI-полів;
- Runtime session створює adapter через CTraderAdapter.from_env();
- from_env() вимагає CTRADER_* із environment.
"""

from __future__ import annotations

import ast
from pathlib import Path

TEST_ONLY = True
BROKER_REQUESTS = 0
PRODUCTION_LOGIC_CHANGED = False

PROJECT_ROOT = Path(__file__).resolve().parents[2]


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


def _segment(source: str, node: ast.AST) -> str:
    return ast.get_source_segment(source, node) or ""


def main() -> int:
    dialog_path = "core/ctrader_connection_dialog.py"
    session_path = "engine/ctrader_session_manager.py"
    adapter_path = "engine/ctrader_adapter.py"

    dialog_source = _source(dialog_path)
    session_source = _source(session_path)
    adapter_source = _source(adapter_path)

    dialog_tree = _parse(dialog_path)
    session_tree = _parse(session_path)
    adapter_tree = _parse(adapter_path)

    save_method = _find_method(
        dialog_tree,
        "CTraderConnectionDialog",
        "_save_to_conf",
    )
    oauth_method = _find_method(
        dialog_tree,
        "CTraderConnectionDialog",
        "_on_ctrader_oauth_clicked",
    )
    session_connect = _find_method(
        session_tree,
        "CTraderSessionManager",
        "_connect",
    )
    adapter_from_env = _find_method(
        adapter_tree,
        "CTraderAdapter",
        "from_env",
    )

    save_text = _segment(dialog_source, save_method)
    oauth_text = _segment(dialog_source, oauth_method)
    runtime_text = _segment(session_source, session_connect)
    env_text = _segment(adapter_source, adapter_from_env)

    checks = {
        "gui_saves_client_id_to_conf": (
            'conf_obj.set("ctrader", "client_id"' in save_text
        ),
        "gui_saves_client_secret_to_conf": (
            '"client_secret"' in save_text
            and "editClientSecret.text().strip()" in save_text
        ),
        "gui_persists_conf": "ConfigManager(ROOT_CONF_PATH).save" in save_text,
        "oauth_uses_gui_client_id": (
            "client_id=self.ui.editClientId.text().strip()" in oauth_text
        ),
        "oauth_uses_gui_client_secret": (
            "client_secret=self.ui.editClientSecret.text().strip()" in oauth_text
        ),
        "runtime_uses_adapter_from_env": (
            "CTraderAdapter.from_env(" in runtime_text
        ),
        "runtime_does_not_pass_conf_credentials": (
            "client_id=" not in runtime_text
            and "client_secret=" not in runtime_text
        ),
        "adapter_requires_env_client_id": (
            '_get_env_required("CTRADER_CLIENT_ID")' in env_text
        ),
        "adapter_requires_env_client_secret": (
            '_get_env_required("CTRADER_CLIENT_SECRET")' in env_text
        ),
        "adapter_requires_env_account_id": (
            '_get_env_required("CTRADER_ACCOUNT_ID")' in env_text
        ),
    }

    print("T110-10 — cTrader Credential Source Anatomy — TEST_ONLY")
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
        print("T110-10=RED")
        return 1

    print("gui_credentials_source=LGE_CONF")
    print("oauth_credentials_source=GUI_FIELDS_BACKED_BY_LGE_CONF")
    print("runtime_adapter_factory=CTraderAdapter.from_env")
    print("runtime_credentials_source=ENVIRONMENT")
    print("required_env=CTRADER_CLIENT_ID,CTRADER_CLIENT_SECRET,CTRADER_ACCOUNT_ID")
    print("first_broken_boundary=CTRADER_RUNTIME_CREDENTIAL_SOURCE")
    print("verdict=GUI_AND_OAUTH_USE_CONFIG_BUT_RUNTIME_REQUIRES_ENV")
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
    print("T110-10=GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
