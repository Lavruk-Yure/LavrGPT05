# -*- coding: utf-8 -*-
"""T110-11 — cTrader Runtime Credential Source Fix — TEST_ONLY."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

TEST_ONLY = True
BROKER_REQUESTS = 0
PRODUCTION_LOGIC_CHANGED = True


def _source(rel_path: str) -> str:
    return (PROJECT_ROOT / rel_path).read_text(encoding="utf-8")


def _function_source(rel_path: str, function_name: str) -> str:
    source = _source(rel_path)
    tree = ast.parse(source, filename=rel_path)

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return ast.get_source_segment(source, node) or ""

    raise AssertionError(f"function_not_found={function_name}")


def _method_source(rel_path: str, class_name: str, method_name: str) -> str:
    source = _source(rel_path)
    tree = ast.parse(source, filename=rel_path)

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == method_name:
                return ast.get_source_segment(source, item) or ""

    raise AssertionError(f"method_not_found={class_name}.{method_name}")


def main() -> int:
    main_source = _source("core/main_logic.py")
    dialog_source = _source("core/ctrader_connection_dialog.py")
    service_source = _source("engine/services/ctrader_runtime_service.py")
    session_source = _source("engine/ctrader_session_manager.py")
    adapter_source = _source("engine/ctrader_adapter.py")

    config_factory = _function_source(
        "core/main_logic.py",
        "_create_ctrader_adapter_from_config",
    )
    session_connect = _method_source(
        "engine/ctrader_session_manager.py",
        "CTraderSessionManager",
        "_connect",
    )
    adapter_from_env = _method_source(
        "engine/ctrader_adapter.py",
        "CTraderAdapter",
        "from_env",
    )
    adapter_from_credentials = _method_source(
        "engine/ctrader_adapter.py",
        "CTraderAdapter",
        "from_credentials",
    )

    checks = {
        "runtime_factory_reads_conf_client_id": (
            'conf_obj.get("ctrader", "client_id"' in config_factory
        ),
        "runtime_factory_reads_conf_client_secret": (
            'conf_obj.get("ctrader", "client_secret"' in config_factory
        ),
        "runtime_factory_reads_conf_account_id": (
            'conf_obj.get("ctrader", "account_id"' in config_factory
        ),
        "runtime_factory_uses_explicit_credentials": (
            "CTraderAdapter.from_credentials(" in config_factory
        ),
        "runtime_service_receives_config_factory": (
            "adapter_factory=_create_ctrader_adapter_from_config" in main_source
        ),
        "service_forwards_adapter_factory": (
            "CTraderSessionManager(" in service_source
            and "adapter_factory=adapter_factory" in service_source
        ),
        "session_connect_uses_injected_factory": (
            "self._adapter_factory(normalized_mode)" in session_connect
        ),
        "session_connect_no_longer_calls_from_env": (
            "CTraderAdapter.from_env" not in session_connect
        ),
        "from_env_back_compat_preserved": (
            'CTRADER_CLIENT_ID' in adapter_from_env
            and "return cls.from_credentials(" in adapter_from_env
        ),
        "explicit_adapter_source_uses_values_not_env": (
            "_get_env_required" not in adapter_from_credentials
            and "client_id=normalized_client_id" in adapter_from_credentials
            and "client_secret=normalized_client_secret" in adapter_from_credentials
        ),
        "oauth_path_unchanged": (
            "run_ctrader_oauth_flow(" in dialog_source
            and "client_id=self.ui.editClientId.text().strip()" in dialog_source
            and "client_secret=self.ui.editClientSecret.text().strip()" in dialog_source
        ),
        "environment_symbols_remain_non_gui_only": (
            "CTRADER_CLIENT_ID" in adapter_source
            and "CTraderAdapter.from_env" not in session_connect
        ),
        "session_has_adapter_factory_contract": (
            "adapter_factory" in session_source
            and "self._adapter_factory" in session_source
        ),
    }

    print("T110-11 — cTrader Runtime Credential Source Fix")
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
        print("boundary=CTRADER_RUNTIME_CREDENTIAL_SOURCE_NOT_REPAIRED")
        print(f"TEST_ONLY={TEST_ONLY}")
        print(f"broker_requests={BROKER_REQUESTS}")
        print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
        print("T110-11=RED")
        return 1

    print("runtime_credentials_source=LGE_CONF")
    print("runtime_account_source=LGE_CONF_SELECTED_ACCOUNT")
    print("environment_not_required_for_gui_runtime=True")
    print("from_env_back_compat=PRESERVED")
    print("oauth_path_unchanged=True")
    print("first_repaired_boundary=CTRADER_RUNTIME_CREDENTIAL_SOURCE")
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
    print("T110-11=GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
