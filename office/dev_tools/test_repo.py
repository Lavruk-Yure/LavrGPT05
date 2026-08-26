# test_repo.py
# -*- coding: utf-8 -*-
"""
test_repo — швидка перевірка DbRepo (Patch 26.2).

Запуск:
  D:/LavrGPT/venv313/Scripts/python.exe # noqa
  D:/LavrGPT/LavrGPT05/office/dev_tools/test_repo.py
"""

from __future__ import annotations

import logging
from pathlib import Path

from office.core.db_repo import DbRepo
from office.core.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def main() -> int:
    setup_logging()
    office_root = Path(__file__).resolve().parent.parent

    repo = DbRepo(office_root)
    db_path = repo.ensure_db()
    logger.info("DB: %s", db_path)

    email = "lavrhome@gmail.com"
    customer_id = repo.upsert_customer(email, name="")
    logger.info("customer_id=%s", customer_id)

    order_id = "LGE-20260202-1324-DBF8"
    payment_ref = f"LGE {order_id}"
    fingerprint = "8308ba7bc77b966499cd4ab060c37809be8740c47d300d6ad392ca5239e12b8d"

    row_id = repo.upsert_order(
        order_id=order_id,
        customer_id=customer_id,
        edition="PRO",
        app_version="1.0.0",
        payment_ref=payment_ref,
        fingerprint=fingerprint,
    )
    logger.info("order_row_id=%s", row_id)

    print("✅ Repo OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
