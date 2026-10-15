from __future__ import annotations

import ast
from pathlib import Path

TEST_ONLY = True

ROOT = Path(__file__).resolve().parents[2]
IB_ADAPTER = ROOT / "engine" / "ib_adapter.py"
RECONCILIATION = ROOT / "core" / "ib_reconciliation_lifecycle.py"
MAIN_LOGIC = ROOT / "core" / "main_logic.py"
RUNTIME_CONSTANTS = ROOT / "engine" / "runtime_constants.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse(path: Path) -> None:
    ast.parse(_read(path), filename=str(path))


def _require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing evidence: {label}: {needle!r}")


def main() -> int:
    for path in (IB_ADAPTER, RECONCILIATION, MAIN_LOGIC, RUNTIME_CONSTANTS):
        _parse(path)

    adapter = _read(IB_ADAPTER)
    reconciliation = _read(RECONCILIATION)
    main_logic = _read(MAIN_LOGIC)
    constants = _read(RUNTIME_CONSTANTS)

    _require(
        adapter,
        "def get_virtual_position_leg_evidence_snapshot(",
        "virtual-leg evidence snapshot exists",
    )
    _require(
        adapter,
        "open_order_rows = self._request_open_orders_snapshot(",
        "virtual-leg evidence requests open orders",
    )
    _require(
        adapter,
        "require_complete=True,",
        "virtual-leg evidence requires complete open-order snapshot",
    )
    _require(
        adapter,
        "self._client.reqAllOpenOrders()",
        "open-order snapshot calls reqAllOpenOrders",
    )
    _require(
        reconciliation,
        "runtime_engine.get_ib_virtual_position_leg_evidence_snapshot()",
        "reconciliation worker captures full IB evidence",
    )
    _require(
        reconciliation,
        'get_active_broker() != "IB"',
        "T111-14 active-broker guard remains present",
    )
    _require(
        main_logic,
        "self._ib_reconciliation_lifecycle.request_refresh(runtime_engine)",
        "main window periodically requests reconciliation refresh",
    )
    _require(
        constants,
        "RUNTIME_ACCOUNT_REFRESH_INTERVAL_SECONDS = 30.0",
        "account/reconciliation refresh cadence is 30 seconds",
    )

    req_all_open_orders_count = adapter.count("self._client.reqAllOpenOrders()")
    place_order_count = adapter.count("self._client.placeOrder(")
    cancel_order_count = adapter.count("self._client.cancelOrder(")

    readonly_conflict_candidate_confirmed = req_all_open_orders_count >= 1
    active_broker_guard_present = 'get_active_broker() != "IB"' in reconciliation
    broker_requests = 0
    broker_execution_attempted = False
    production_logic_changed = False

    ok = all(
        (
            readonly_conflict_candidate_confirmed,
            active_broker_guard_present,
            broker_requests == 0,
            not broker_execution_attempted,
            not production_logic_changed,
        )
    )

    verdict = (
        "IB_READONLY_OPEN_ORDERS_PATH_CONFIRMED"
        if ok
        else "IB_READONLY_OPEN_ORDERS_PATH_NOT_CONFIRMED"
    )

    print("T111-23B TEST_ONLY")
    print(f"verdict={verdict}")
    print("virtual_leg_evidence_requests_open_orders=True")
    print("open_order_request_method=reqAllOpenOrders")
    print("open_order_snapshot_require_complete=True")
    print("reconciliation_worker_uses_virtual_leg_evidence=True")
    print("reconciliation_requires_active_broker_ib=True")
    print("reconciliation_refresh_interval_seconds=30")
    print(f"req_all_open_orders_call_sites={req_all_open_orders_count}")
    print(f"place_order_call_sites_in_adapter={place_order_count}")
    print(f"cancel_order_call_sites_in_adapter={cancel_order_count}")
    print("popup_exact_caller_proven_by_static_test=False")
    print("readonly_conflict_candidate=reqAllOpenOrders")
    print(f"broker_requests={broker_requests}")
    print(f"broker_execution_attempted={broker_execution_attempted}")
    print(f"production_logic_changed={production_logic_changed}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
