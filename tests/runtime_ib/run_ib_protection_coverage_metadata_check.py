# run_ib_protection_coverage_metadata_check.py
"""
Synthetic IB protection coverage metadata check.

RoadMap87:
- не підключається до TWS;
- перевіряє order_id та broker objects;
- перевіряє multiple-order operational ambiguity.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_adapter import IBAdapter  # noqa: E402


def _require(
    condition: bool,
    message: str,
) -> None:
    """
    Перервати test із зрозумілою причиною.
    """
    if not condition:
        raise AssertionError(message)


def main() -> int:
    """
    Запустити synthetic coverage metadata check.
    """
    contract_object = object()
    order_object = object()

    try:
        # noinspection PyProtectedMember
        single_row = IBAdapter._pick_sl_tp_coverage_row(
            candidates=[
                {
                    "price": 1.1000,
                    "quantity": 1000.0,
                    "order_id": 101,
                    "client_id": 1,
                    "perm_id": 5001,
                    "same_client_id": True,
                    "contract_object": contract_object,
                    "order_object": order_object,
                }
            ],
            position_volume=1000.0,
        )

        _require(single_row is not None, "Single row missing")
        _require(
            single_row["partial"] is False,
            "Single full coverage marked partial",
        )
        _require(
            single_row["ambiguous"] is False,
            "Single full coverage marked ambiguous",
        )
        _require(
            single_row["operational_ambiguous"] is False,
            "Single order marked operationally ambiguous",
        )
        _require(
            single_row["order_id"] == 101,
            "Single order_id mismatch",
        )
        _require(
            single_row["same_client_id"] is True,
            "Single ownership candidate mismatch",
        )
        _require(
            single_row["contract_object"] is contract_object,
            "Contract object identity mismatch",
        )
        _require(
            single_row["order_object"] is order_object,
            "Order object identity mismatch",
        )

        print("Single full coverage")
        print(f"  row={single_row}")
        print("  result=OK")
        print()

        # noinspection PyProtectedMember
        multiple_row = IBAdapter._pick_sl_tp_coverage_row(
            candidates=[
                {
                    "price": 1.1000,
                    "quantity": 500.0,
                    "order_id": 201,
                    "same_client_id": True,
                },
                {
                    "price": 1.1000,
                    "quantity": 500.0,
                    "order_id": 202,
                    "same_client_id": True,
                },
            ],
            position_volume=1000.0,
        )

        _require(
            multiple_row is not None,
            "Multiple row missing",
        )
        _require(
            multiple_row["partial"] is False,
            "Multiple full coverage marked partial",
        )
        _require(
            multiple_row["ambiguous"] is False,
            "Same-price orders marked price ambiguous",
        )
        _require(
            multiple_row["operational_ambiguous"] is True,
            "Multiple orders not operationally ambiguous",
        )
        _require(
            multiple_row["order_ids"] == [201, 202],
            "Multiple order_ids mismatch",
        )

        print("Multiple same-price orders")
        print(f"  row={multiple_row}")
        print("  result=OK")
        print()

        # noinspection PyProtectedMember
        partial_row = IBAdapter._pick_sl_tp_coverage_row(
            candidates=[
                {
                    "price": 1.1000,
                    "quantity": 500.0,
                    "order_id": 301,
                    "same_client_id": True,
                }
            ],
            position_volume=1000.0,
        )

        _require(partial_row is not None, "Partial row missing")
        _require(
            partial_row["partial"] is True,
            "Partial coverage was not detected",
        )

        print("Partial coverage")
        print(f"  row={partial_row}")
        print("  result=OK")
        print()

    except AssertionError as exc:
        print("IB_PROTECTION_COVERAGE_METADATA_CHECK=FAILED")
        print(f"reason={exc}")
        return 1

    print("IB_PROTECTION_COVERAGE_METADATA_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
