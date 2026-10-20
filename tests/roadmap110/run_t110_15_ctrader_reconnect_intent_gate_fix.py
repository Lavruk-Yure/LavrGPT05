# -*- coding: utf-8 -*-
"""
T110-15 — cTrader Reconnect Intent Gate Fix — TEST_ONLY.

Перевіряє мінімальну production-правку після T110-14:
- broker-state handler читає auto_connect.ctrader із LGE.conf;
- cTrader reconnect-watch запускається лише за auto_connect.ctrader=True;
- startup AutoConnect gate для cTrader лишається без змін;
- IB reconnect gate не зачеплений.
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


def _find_method(
    source: str,
    class_name: str,
    method_name: str,
) -> ast.FunctionDef:
    tree = ast.parse(source)

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
    method = _find_method(source, class_name, method_name)
    return ast.get_source_segment(source, method) or ""


def main() -> int:
    broker_notify = _method_source(
        "core/main_logic.py",
        "MainAppWindow",
        "_notify_broker_state_changes",
    )
    startup_auto = _method_source(
        "core/main_logic.py",
        "MainAppWindow",
        "_startup_auto_connect",
    )

    ctrader_branch = broker_notify.split(
        'elif broker_name == "cTrader":',
        1,
    )[1]

    checks = {
        "ctrader_branch_reads_current_config": (
            'getattr(session_state, "CURRENT_CONFIG", None)' in ctrader_branch
        ),
        "ctrader_branch_defaults_intent_false": (
            "auto_ctrader = False" in ctrader_branch
        ),
        "ctrader_branch_reads_auto_connect_ctrader": (
            '.get("auto_connect", {})' in ctrader_branch
            and '.get("ctrader", False)' in ctrader_branch
        ),
        "ctrader_reconnect_watch_is_gated": (
            "if auto_ctrader:" in ctrader_branch
            and "runtime_engine.start_ctrader_reconnect_watch()" in ctrader_branch
            and ctrader_branch.index("if auto_ctrader:")
            < ctrader_branch.index(
                "runtime_engine.start_ctrader_reconnect_watch()"
            )
        ),
        "startup_ctrader_intent_gate_preserved": (
            'auto_ctrader = bool(auto_connect.get("ctrader", False))'
            in startup_auto
            and "if auto_ctrader:" in startup_auto
            and "self._startup_connect_ctrader(runtime_engine)" in startup_auto
        ),
        "ib_reconnect_intent_gate_preserved": (
            "auto_ib = False" in broker_notify
            and '.get("ib", False)' in broker_notify
            and "and auto_ib" in broker_notify
            and "runtime_engine.start_ib_reconnect_watch()" in broker_notify
        ),
    }

    print("T110-15 — cTrader Reconnect Intent Gate Fix — TEST_ONLY")
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
        print("boundary=CTRADER_RECONNECT_INTENT_GATE_FIX_NOT_CONFIRMED")
        print(f"TEST_ONLY={TEST_ONLY}")
        print(f"broker_requests={BROKER_REQUESTS}")
        print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
        print("T110-15=RED")
        return 1

    print("ctrader_reconnect_watch_intent_gate=PRESENT")
    print("auto_connect_false=NO_RECONNECT_WATCH")
    print("auto_connect_true=RECONNECT_WATCH_ALLOWED")
    print("ib_reconnect_gate=UNCHANGED")
    print("startup_ctrader_gate=UNCHANGED")
    print("first_repaired_boundary=CTRADER_BROKER_STATE_RECONNECT_INTENT_GATE")
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
    print("T110-15=GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
