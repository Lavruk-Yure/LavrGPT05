# -*- coding: utf-8 -*-
"""T111-39 v5 — IB Read-Only Workspace Pre-Start Request Anatomy — TEST_ONLY."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FILES = {
    "runtime": PROJECT_ROOT / "core" / "workspace_runtime.py",
    "market": PROJECT_ROOT / "core" / "workspace_broker_market.py",
    "engine": PROJECT_ROOT / "engine" / "runtime_engine.py",
    "service": PROJECT_ROOT / "engine" / "services" / "ib_runtime_service.py",
    "session": PROJECT_ROOT / "engine" / "ib_session_manager.py",
    "adapter": PROJECT_ROOT / "engine" / "ib_adapter.py",
    "reconciliation": PROJECT_ROOT / "core" / "ib_reconciliation_lifecycle.py",
}

TEST_ONLY = True
BROKER_REQUESTS = 0
BROKER_EXECUTION_ATTEMPTED = False
PRODUCTION_LOGIC_CHANGED = False


def _read(name: str) -> str:
    return FILES[name].read_text(encoding="utf-8")


def _method_source(text: str, class_name: str, method_name: str) -> str:
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)

    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for child in node.body:
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if child.name == method_name:
                return "".join(lines[child.lineno - 1 : child.end_lineno])  # noqa

    raise AssertionError(f"method not found: {class_name}.{method_name}")


def _require(value: bool, label: str) -> None:
    if not value:
        raise AssertionError(label)


def main() -> int:
    runtime = _read("runtime")
    market = _read("market")
    engine = _read("engine")
    service = _read("service")
    session = _read("session")
    adapter = _read("adapter")
    reconciliation = _read("reconciliation")

    runtime_guard = _method_source(
        runtime,
        "WorkspaceRuntime",
        "_refresh_execution_safety",
    )
    market_guard = _method_source(
        market,
        "RuntimeEngineWorkspaceMarketProvider",
        "get_workspace_execution_safety",
    )
    engine_guard = _method_source(
        engine,
        "RuntimeEngine",
        "refresh_ib_fx_external_exposure_guard",
    )
    service_evidence = _method_source(
        service,
        "IBRuntimeService",
        "get_virtual_position_leg_evidence_snapshot",
    )
    session_evidence = _method_source(
        session,
        "IBSessionManager",
        "get_virtual_position_leg_evidence_snapshot",
    )
    adapter_evidence = _method_source(
        adapter,
        "IBAdapter",
        "get_virtual_position_leg_evidence_snapshot",
    )
    open_orders = _method_source(
        adapter,
        "IBAdapter",
        "_request_open_orders_snapshot",
    )
    recon_request = _method_source(
        reconciliation,
        "IBReconciliationLifecycleBridge",
        "request_refresh",
    )

    facts = {
        "workspace_runtime_calls_safety_provider": (
            "provider.get_workspace_execution_safety(" in runtime_guard
        ),
        "provider_calls_external_guard": (
            "refresh_ib_fx_external_exposure_guard(" in market_guard
        ),
        "workspace_guard_refresh_seconds_10": (
            "WORKSPACE_EXECUTION_SAFETY_REFRESH_SECONDS = 10.0" in market
        ),
        "provider_uses_cached_cadence": (
            "WORKSPACE_EXECUTION_SAFETY_REFRESH_SECONDS" in market_guard
            and "return cached" in market_guard
        ),
        "engine_calls_full_ib_evidence": (
            "service.get_virtual_position_leg_evidence_snapshot()" in engine_guard
        ),
        "engine_guard_has_execution_mode_off_guard": (
            "execution_mode" in engine_guard or "orders are OFF" in engine_guard
        ),
        "service_routes_to_session": (
            "self._session_manager.get_virtual_position_leg_evidence_snapshot()"
            in service_evidence
        ),
        "session_routes_to_adapter": (
            "adapter.get_virtual_position_leg_evidence_snapshot()" in session_evidence
        ),
        "adapter_requests_open_orders": (
            "self._request_open_orders_snapshot(" in adapter_evidence
            and "require_complete=True" in adapter_evidence
        ),
        "open_orders_calls_req_all_open_orders": (
            "self._client.reqAllOpenOrders()" in open_orders
        ),
        "t111_24b_guard_present": (
            "_execution_mode_allows_background_refresh" in recon_request
            and "IB reconciliation disabled while orders are OFF" in recon_request
        ),
        "t111_24b_guard_scope_is_reconciliation_only": (
            "refresh_ib_fx_external_exposure_guard" not in recon_request
            and "get_workspace_execution_safety" not in recon_request
        ),
    }

    expected_true = (
        "workspace_runtime_calls_safety_provider",
        "provider_calls_external_guard",
        "workspace_guard_refresh_seconds_10",
        "provider_uses_cached_cadence",
        "engine_calls_full_ib_evidence",
        "service_routes_to_session",
        "session_routes_to_adapter",
        "adapter_requests_open_orders",
        "open_orders_calls_req_all_open_orders",
        "t111_24b_guard_present",
        "t111_24b_guard_scope_is_reconciliation_only",
    )

    for key in expected_true:
        _require(facts[key], key)

    _require(
        not facts["engine_guard_has_execution_mode_off_guard"],
        "engine_guard_has_execution_mode_off_guard",
    )

    print("T111-39 TEST_ONLY")
    print("verdict=IB_WORKSPACE_SAFETY_PATH_BYPASSES_ORDERS_OFF_GUARD")
    for key, value in facts.items():
        print(f"{key}={value}")
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(f"broker_execution_attempted={BROKER_EXECUTION_ATTEMPTED}")
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
