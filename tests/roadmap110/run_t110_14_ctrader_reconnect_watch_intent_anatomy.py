# -*- coding: utf-8 -*-
"""
T110-14 — cTrader Reconnect Watch Intent Anatomy — TEST_ONLY.

Перевіряє фактичний production path без production-змін:
- cTrader account_mode зберігається та читається з LGE.conf;
- новий conf має auto_connect.ctrader=False;
- Startup AutoConnect запускає cTrader тільки за auto_connect.ctrader=True;
- broker-state notification для cTrader стартує reconnect-watch без такої перевірки;
- CTraderSessionManager.reconnect() не може reconnect без попередньо
  встановленого active_account_mode.

Ціль — локалізувати причину:
"cTrader reconnect requested but account_mode is empty."
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
    source = _source(rel_path)
    return ast.parse(source, filename=rel_path)


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


def _method_source(
    rel_path: str,
    class_name: str,
    method_name: str,
) -> str:
    source = _source(rel_path)
    tree = ast.parse(source, filename=rel_path)
    method = _find_method(tree, class_name, method_name)
    return ast.get_source_segment(source, method) or ""


def main() -> int:
    dialog_save = _method_source(
        "core/ctrader_connection_dialog.py",
        "CTraderConnectionDialog",
        "_save_to_conf",
    )
    dialog_load = _method_source(
        "core/ctrader_connection_dialog.py",
        "CTraderConnectionDialog",
        "_load_from_conf",
    )
    startup_auto = _method_source(
        "core/main_logic.py",
        "MainAppWindow",
        "_startup_auto_connect",
    )
    broker_notify = _method_source(
        "core/main_logic.py",
        "MainAppWindow",
        "_notify_broker_state_changes",
    )
    session_reconnect = _method_source(
        "engine/ctrader_session_manager.py",
        "CTraderSessionManager",
        "reconnect",
    )
    session_prepare = _method_source(
        "engine/ctrader_session_manager.py",
        "CTraderSessionManager",
        "prepare_startup_connection",
    )
    config_source = _source("core/config_manager.py")

    checks = {
        "dialog_saves_ctrader_account_mode": (
            "conf_obj.set(" in dialog_save
            and '"ctrader"' in dialog_save
            and '"account_mode"' in dialog_save
            and "self.ui.comboAccountMode.currentData()" in dialog_save
        ),
        "dialog_loads_ctrader_account_mode": (
            'conf_obj.get("ctrader", "account_mode", "DEMO")' in dialog_load
        ),
        "new_conf_ctrader_auto_connect_defaults_false": (
            '"ctrader": False' in config_source
        ),
        "startup_reads_ctrader_auto_connect_intent": (
            'auto_ctrader = bool(auto_connect.get("ctrader", False))' in startup_auto
        ),
        "startup_ctrader_connect_is_gated_by_intent": (
            "if auto_ctrader:" in startup_auto
            and "self._startup_connect_ctrader(runtime_engine)" in startup_auto
        ),
        "session_prepare_sets_active_account_mode": (
            "self._active_account_mode = normalized_mode" in session_prepare
        ),
        "session_reconnect_requires_active_account_mode": (
            "account_mode = self._active_account_mode" in session_reconnect
            and "if not account_mode:" in session_reconnect
            and 'LOGGER.warning("cTrader reconnect requested'
            ' but account_mode is empty.")' in session_reconnect
        ),
        "ib_reconnect_watch_checks_auto_connect": (
            "auto_ib = bool(" in broker_notify
            and '.get("ib", False)' in broker_notify
            and "and auto_ib" in broker_notify
            and "runtime_engine.start_ib_reconnect_watch()" in broker_notify
        ),
        "ctrader_reconnect_watch_is_started_on_disconnect": (
            'elif broker_name == "cTrader":' in broker_notify
            and "runtime_engine.start_ctrader_reconnect_watch()" in broker_notify
        ),
        "ctrader_reconnect_watch_lacks_auto_connect_gate": (
            "auto_ctrader" not in broker_notify
        ),
    }

    print("T110-14 — cTrader Reconnect Watch Intent Anatomy — TEST_ONLY")
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
        print("boundary=CTRADER_RECONNECT_WATCH_INTENT_ANATOMY_NOT_CONFIRMED")
        print(f"TEST_ONLY={TEST_ONLY}")
        print(f"broker_requests={BROKER_REQUESTS}")
        print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
        print("T110-14=RED")
        return 1

    print("ctrader_gui_account_mode_persistence=OK")
    print("ctrader_startup_autoconnect_intent_gate=EXISTS")
    print("ctrader_reconnect_watch_intent_gate=ABSENT")
    print("session_reconnect_without_prior_mode=RETURNS_NONE")
    print("first_broken_boundary=CTRADER_BROKER_STATE_RECONNECT_INTENT_GATE")
    print(
        "verdict=DISCONNECTED_STATE_STARTS_CTRADER_RECONNECT_WATCH_"
        "WHEN_AUTO_CONNECT_IS_FALSE"
    )
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
    print("T110-14=GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
