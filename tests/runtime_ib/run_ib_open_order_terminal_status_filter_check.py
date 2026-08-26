"""Filter terminal IB order statuses from current open-order evidence."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_adapter import IBAdapter  # noqa: E402


def main() -> int:
    source_rows = [
        {"order_id": 101, "client_id": 1, "status": "Submitted"},
        {"order_id": 102, "client_id": 0, "status": "PreSubmitted"},
        {"order_id": 103, "client_id": 0, "status": "PendingCancel"},
        {"order_id": 201, "client_id": 0, "status": "Cancelled"},
        {"order_id": 202, "client_id": 0, "status": "ApiCancelled"},
        {"order_id": 203, "client_id": 0, "status": "Inactive"},
        {"order_id": 204, "client_id": 0, "status": "Filled"},
    ]

    snapshot = IBAdapter.build_open_order_snapshot_rows(
        open_orders=source_rows,
        open_order_objects={},
        current_client_id=1,
        include_objects=False,
    )
    order_ids = [int(row["order_id"]) for row in snapshot]

    if order_ids != [101, 102, 103]:
        raise AssertionError(f"Active open-order ids differ: {order_ids}")

    if snapshot[0]["same_client_id"] is not True:
        raise AssertionError("Current-client ownership candidate differs")

    if any(row["same_client_id"] for row in snapshot[1:]):
        raise AssertionError("Foreign-client ownership candidate differs")

    if any("same_client_id" in row for row in source_rows):
        raise AssertionError("Source rows were mutated")

    print("IB open-order terminal status filter result")
    print("  active_statuses=Submitted,PreSubmitted,PendingCancel")
    print("  terminal_statuses=Cancelled,ApiCancelled,Inactive,Filled")
    print("  terminal_rows_filtered=4")
    print("  pending_cancel_kept_active=True")
    print("  broker_requests=0")
    print("IB_OPEN_ORDER_TERMINAL_STATUS_FILTER_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
