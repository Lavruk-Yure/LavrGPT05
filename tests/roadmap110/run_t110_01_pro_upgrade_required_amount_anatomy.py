# -*- coding: utf-8 -*-
"""T110-01 — factual anatomy поточної ціни апгрейду PRO -> PRO+. TEST_ONLY."""

from __future__ import annotations

import gc
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from office.core.db_repo import DbRepo  # noqa: E402
from office.core.pricing import get_price_usd  # noqa: E402

TEST_ONLY = True
BROKER_REQUESTS = 0
PRODUCTION_LOGIC_CHANGED = False

PAYMENT_TOLERANCE_USD = 0.50
BELOW_THRESHOLD_DELTA_USD = 0.01
SMALL_OVERPAYMENT_USD = 0.50
LARGE_OVERPAYMENT_USD = 21.00


@dataclass(frozen=True)
class Case:
    name: str
    customer_matches: bool
    fingerprint_matches: bool
    paid_for_pro: float | None
    expected_current: float


def _init_test_db(office_root: Path) -> None:
    schema_path = PROJECT_ROOT / "office" / "core" / "schema.sql"
    schema = schema_path.read_text(encoding="utf-8")
    db_path = office_root / "office.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(schema)
        conn.commit()
    finally:
        conn.close()


def _add_pro_order_with_payment(
    repo: DbRepo,
    *,
    customer_id: int,
    fingerprint: str,
    amount: float | None,
    order_uid: str,
) -> None:
    order_id = repo.upsert_order(
        order_id=order_uid,
        customer_id=customer_id,
        edition="PRO",
        fingerprint=fingerprint,
    )
    if amount is None:
        return

    repo.insert_payment(
        provider="TEST_ONLY",
        external_ref=f"PAY-{order_uid}",
        amount=amount,
        currency="USD",
        paid_utc="2026-09-24 00:00",
        order_id=order_id,
    )


def main() -> int:
    pro_price = float(get_price_usd("PRO"))
    pro_plus_price = float(get_price_usd("PRO_PLUS"))
    fixed_upgrade_price = pro_plus_price - pro_price

    threshold_payment = pro_price - PAYMENT_TOLERANCE_USD
    below_threshold_payment = threshold_payment - BELOW_THRESHOLD_DELTA_USD
    small_overpayment = pro_price + SMALL_OVERPAYMENT_USD
    large_overpayment = pro_price + LARGE_OVERPAYMENT_USD

    cases = (
        Case("NO_PRO", True, True, None, pro_plus_price),
        Case("OTHER_CUSTOMER", False, True, pro_price, pro_plus_price),
        Case("OTHER_FINGERPRINT", True, False, pro_price, pro_plus_price),
        Case("BELOW_THRESHOLD", True, True, below_threshold_payment, pro_plus_price),
        Case(
            "AT_THRESHOLD",
            True,
            True,
            threshold_payment,
            pro_plus_price - threshold_payment,
        ),
        Case("EXACT_PRO_PRICE", True, True, pro_price, fixed_upgrade_price),
        Case(
            "SMALL_OVERPAYMENT",
            True,
            True,
            small_overpayment,
            pro_plus_price - small_overpayment,
        ),
        Case(
            "LARGE_OVERPAYMENT",
            True,
            True,
            large_overpayment,
            max(pro_plus_price - large_overpayment, 0.0),
        ),
    )

    passed = 0
    failed = 0

    print("T110-01 — PRO->PRO+ Required Amount Anatomy — TEST_ONLY")
    print(f"pro_price_from_pricing={pro_price:.2f}")
    print(f"pro_plus_price_from_pricing={pro_plus_price:.2f}")
    print(f"fixed_upgrade_price_from_pricing={fixed_upgrade_price:.2f}")
    print(f"payment_tolerance_test_boundary={PAYMENT_TOLERANCE_USD:.2f}")
    print()

    for index, case in enumerate(cases, start=1):
        with tempfile.TemporaryDirectory(prefix="t110_01_") as tmp:
            office_root = Path(tmp)
            _init_test_db(office_root)
            repo = DbRepo(office_root)

            target_customer_id = repo.upsert_customer("target@example.test")
            other_customer_id = repo.upsert_customer("other@example.test")
            target_fingerprint = "FP-TARGET"
            other_fingerprint = "FP-OTHER"

            if case.paid_for_pro is not None:
                _add_pro_order_with_payment(
                    repo,
                    customer_id=(
                        target_customer_id
                        if case.customer_matches
                        else other_customer_id
                    ),
                    fingerprint=(
                        target_fingerprint
                        if case.fingerprint_matches
                        else other_fingerprint
                    ),
                    amount=case.paid_for_pro,
                    order_uid=f"T110-01-{index:02d}",
                )

            actual = repo.get_required_amount_for_edition(
                customer_id=target_customer_id,
                fingerprint=target_fingerprint,
                target_edition="PRO_PLUS",
            )

            # TEST_ONLY: Windows має відпустити всі короткоживучі SQLite handles
            # до того, як TemporaryDirectory спробує видалити office.db.
            del repo
            gc.collect()

            ok = abs(actual - case.expected_current) < 0.000001
            status = "PASS" if ok else "FAIL"
            paid_text = (
                "NONE" if case.paid_for_pro is None else f"{case.paid_for_pro:.2f}"
            )
            print(
                f"{status} {case.name}: paid={paid_text} "
                f"actual={actual:.2f} expected_current={case.expected_current:.2f}"
            )
            if ok:
                passed += 1
            else:
                failed += 1

    print()
    print(f"cases={len(cases)}")
    print(f"passed={passed}")
    print(f"failed={failed}")
    print("current_formula_after_paid_PRO=" "price(PRO_PLUS)-actual_total_paid_for_PRO")
    print("roadmap47_rule=" "price(PRO_PLUS)-price(PRO)=" f"{fixed_upgrade_price:.2f}")
    print("boundary=CURRENT_IMPLEMENTATION_DIFFERS_FROM_FIXED_UPGRADE_PRICE_RULE")
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
    print("T110-01=GREEN" if failed == 0 else "T110-01=RED")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
