# run_ib_open_order_snapshot_enrichment_check.py
"""
Synthetic IB open-order snapshot enrichment check.

RoadMap87:
- не підключається до TWS;
- не створює і не скасовує orders;
- перевіряє scalar snapshot;
- перевіряє ownership candidate;
- перевіряє optional Contract/Order objects.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_adapter import IBAdapter  # noqa: E402


def _require(
    condition: bool,
    message: str,
) -> None:
    """
    Перервати test зі зрозумілою причиною.
    """
    if not condition:
        raise AssertionError(message)


def _require_equal(
    actual: Any,
    expected: Any,
    message: str,
) -> None:
    """
    Перевірити точну рівність.
    """
    if actual != expected:
        raise AssertionError(f"{message}: expected={expected!r}, " f"actual={actual!r}")


def main() -> int:
    """
    Запустити synthetic snapshot enrichment check.
    """
    contract_101 = object()
    order_101 = object()

    contract_202 = object()
    order_202 = object()

    source_rows = [
        {
            "order_id": 101,
            "client_id": 1,
            "order_type": "STP",
            "aux_price": 1.1000,
        },
        {
            "order_id": 202,
            "client_id": 0,
            "order_type": "LMT",
            "lmt_price": 1.2000,
        },
    ]

    object_rows = {
        101: {
            "contract_object": contract_101,
            "order_object": order_101,
        },
        202: {
            "contract_object": contract_202,
            "order_object": order_202,
        },
    }

    try:
        scalar_snapshot = IBAdapter.build_open_order_snapshot_rows(
            open_orders=source_rows,
            open_order_objects=object_rows,
            current_client_id=1,
            include_objects=False,
        )

        print("Scalar snapshot")
        print(f"  rows={scalar_snapshot}")

        _require_equal(
            len(scalar_snapshot),
            2,
            "Scalar snapshot row count",
        )
        _require_equal(
            scalar_snapshot[0]["same_client_id"],
            True,
            "Order 101 same client id",
        )
        _require_equal(
            scalar_snapshot[1]["same_client_id"],
            False,
            "Order 202 same client id",
        )
        _require(
            "contract_object" not in scalar_snapshot[0],
            "Scalar snapshot leaked Contract object",
        )
        _require(
            "order_object" not in scalar_snapshot[0],
            "Scalar snapshot leaked Order object",
        )

        _require(
            "same_client_id" not in source_rows[0],
            "Source row was mutated",
        )

        print("  result=OK")
        print()

        object_snapshot = IBAdapter.build_open_order_snapshot_rows(
            open_orders=source_rows,
            open_order_objects=object_rows,
            current_client_id=1,
            include_objects=True,
        )

        print("Object snapshot")
        print("  order_ids=" f"{[row['order_id'] for row in object_snapshot]}")

        _require(
            object_snapshot[0]["contract_object"] is contract_101,
            "Order 101 Contract object identity mismatch",
        )
        _require(
            object_snapshot[0]["order_object"] is order_101,
            "Order 101 Order object identity mismatch",
        )
        _require(
            object_snapshot[1]["contract_object"] is contract_202,
            "Order 202 Contract object identity mismatch",
        )
        _require(
            object_snapshot[1]["order_object"] is order_202,
            "Order 202 Order object identity mismatch",
        )

        print("  result=OK")
        print()

        empty_snapshot = IBAdapter.build_open_order_snapshot_rows(
            open_orders=[],
            open_order_objects={},
            current_client_id=1,
            include_objects=True,
        )

        _require_equal(
            empty_snapshot,
            [],
            "Empty snapshot",
        )

        print("Empty snapshot")
        print("  result=OK")
        print()

    except AssertionError as exc:
        print("IB_OPEN_ORDER_SNAPSHOT_ENRICHMENT_CHECK=FAILED")
        print(f"reason={exc}")
        return 1

    print("IB_OPEN_ORDER_SNAPSHOT_ENRICHMENT_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
