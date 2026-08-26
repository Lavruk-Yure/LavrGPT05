# db_repo.py
# -*- coding: utf-8 -*-
"""
db_repo — репозиторій SQLite для LGEOffice.

Факти:
- Працюємо по реальній схемі office/core/schema.sql.
- Ніякого SQL з UI.
- audit_log вимкнено / не використовується.

Таблиці:
- customers: (id, email, name, note, created_utc)
- orders: (id, order_uid, customer_id, edition, app_version, payment_ref,
  fingerprint_sha256, created_utc)
- payments: (id, order_id NULL, provider, external_ref, amount,
  currency, paid_utc, note)
- licenses: (id, order_id UNIQUE, license_uid, license_rel_path,
  edition, issued_utc, sent_utc)
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from office.core.datetime_utils import utc_now_str
from office.core.db import connect, get_db_path, init_db
from office.core.pricing import get_price_usd

logger = logging.getLogger(__name__)


def _now_utc_iso() -> str:
    """Повернути UTC у канонічному форматі YYYY-MM-DD HH:MM."""
    return utc_now_str()


def _norm_str(x: object) -> str:
    return x.strip() if isinstance(x, str) else ""


@dataclass(frozen=True)
class CustomerRow:
    id: int
    email: str
    name: str
    note: str
    created_utc: str


@dataclass(frozen=True)
class OrderRow:
    id: int
    order_uid: str
    customer_id: int
    edition: str
    app_version: str
    payment_ref: str
    fingerprint_sha256: str
    created_utc: str


@dataclass(frozen=True)
class PaymentRow:
    id: int
    order_id: Optional[int]
    provider: str
    external_ref: str
    amount: float
    currency: str
    paid_utc: str
    note: str


@dataclass(frozen=True)
class LicenseRow:
    id: int
    order_id: int
    license_uid: str
    license_rel_path: str
    edition: str
    issued_utc: str
    sent_utc: str


class DbRepo:
    """
    Репозиторій для office.db.
    Всі методи працюють через sqlite3 і повертають прості структури.
    """

    def __init__(self, office_root: Path) -> None:
        self._office_root = office_root
        self._db_path = get_db_path(office_root)

    @property
    def db_path(self) -> Path:
        return self._db_path

    def ensure_db(self) -> Path:
        return init_db(self._office_root)

    def _open(self) -> sqlite3.Connection:
        return connect(self._db_path)

    # -------------------------
    # Audit
    # -------------------------
    @staticmethod
    def audit(
        event_type: str,
        details: str = "",
        *,
        entity_type: str = "",
        entity_id: str = "",
        created_utc: Optional[str] = None,
    ) -> int:
        logger.debug(
            "AUDIT DISABLED: %s | %s | %s | %s | created_utc=%s",
            event_type,
            entity_type,
            entity_id,
            details,
            created_utc or "",
        )
        return 0

    # -------------------------
    # Customers
    # -------------------------
    def upsert_customer(self, email: str, *, name: str = "") -> int:
        email_norm = _norm_str(email).lower()
        if email_norm.startswith("email:"):
            email_norm = email_norm.replace("email:", "", 1).strip()

        name_norm = _norm_str(name)
        if not email_norm:
            raise ValueError("customer email is required")

        created_utc = _now_utc_iso()

        sql_insert = """
        INSERT INTO customers (email, name, created_utc)
        VALUES (?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
            name=excluded.name
        """
        sql_select = "SELECT id FROM customers WHERE email = ?"

        with self._open() as conn:
            conn.execute(sql_insert, (email_norm, name_norm, created_utc))
            row = conn.execute(sql_select, (email_norm,)).fetchone()
            conn.commit()

        if row is None or row[0] is None:
            raise RuntimeError("failed to upsert customer")

        customer_id = int(row[0])
        self.audit(
            "UPSERT_CUSTOMER",
            f"email={email_norm}; name={name_norm}",
            entity_type="customer",
            entity_id=str(customer_id),
        )
        return customer_id

    def get_customer_id_by_email(self, email: str) -> Optional[int]:
        email_norm = _norm_str(email).lower()
        if not email_norm:
            return None
        sql = "SELECT id FROM customers WHERE email = ? LIMIT 1"
        with self._open() as conn:
            row = conn.execute(sql, (email_norm,)).fetchone()
        return int(row[0]) if row and row[0] is not None else None

    def list_customers(self) -> list[CustomerRow]:
        sql = (
            "SELECT id, email, name, note, created_utc "
            "FROM "
            "customers ORDER BY id DESC"
        )
        with self._open() as conn:
            rows = conn.execute(sql).fetchall()
        return [
            CustomerRow(int(r[0]), str(r[1]), str(r[2]), str(r[3]), str(r[4]))
            for r in rows
        ]

    # -------------------------
    # Orders
    # -------------------------
    def upsert_order(
        self,
        *,
        # залишаємо ім'я параметра як в існуючому UI, але пишемо в order_uid
        order_id: str,
        customer_id: int,
        edition: str,
        app_version: str = "",
        payment_ref: str = "",
        fingerprint: str = "",
        created_utc: Optional[str] = None,
    ) -> int:
        order_uid = _norm_str(order_id)
        edition_norm = _norm_str(edition)
        app_version_norm = _norm_str(app_version)
        payment_ref_norm = _norm_str(payment_ref)
        fingerprint_sha256 = _norm_str(fingerprint)

        if not order_uid:
            raise ValueError("order_id is required")
        if customer_id <= 0:
            raise ValueError("customer_id must be > 0")
        if not edition_norm:
            raise ValueError("edition is required")
        if created_utc is None:
            created_utc = _now_utc_iso()

        sql = """
        INSERT INTO orders (
            order_uid, customer_id, edition, app_version,
            payment_ref, fingerprint_sha256, created_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(order_uid) DO UPDATE SET
            customer_id=excluded.customer_id,
            edition=excluded.edition,
            app_version=excluded.app_version,
            payment_ref=excluded.payment_ref,
            fingerprint_sha256=excluded.fingerprint_sha256
        """
        sql_select = "SELECT id FROM orders WHERE order_uid = ?"

        with self._open() as conn:
            conn.execute(
                sql,
                (
                    order_uid,
                    int(customer_id),
                    edition_norm,
                    app_version_norm,
                    payment_ref_norm,
                    fingerprint_sha256,
                    created_utc,
                ),
            )
            row = conn.execute(sql_select, (order_uid,)).fetchone()
            conn.commit()

        if row is None or row[0] is None:
            raise RuntimeError("failed to upsert order")

        order_row_id = int(row[0])
        self.audit(
            "UPSERT_ORDER",
            f"order_uid={order_uid}; customer_id={customer_id}; edition={edition_norm}",
            entity_type="order",
            entity_id=str(order_row_id),
        )
        return order_row_id

    def get_order_row_id(self, order_uid: str) -> Optional[int]:
        order_uid = _norm_str(order_uid)
        if not order_uid:
            return None
        sql = "SELECT id FROM orders WHERE order_uid = ? LIMIT 1"
        with self._open() as conn:
            row = conn.execute(sql, (order_uid,)).fetchone()
        return int(row[0]) if row and row[0] is not None else None

    def list_orders(self, customer_id: int) -> list[OrderRow]:
        if customer_id <= 0:
            return []
        sql = """
        SELECT id, order_uid, customer_id, edition, app_version,
               payment_ref, fingerprint_sha256, created_utc
        FROM orders
        WHERE customer_id = ?
        ORDER BY id DESC
        """
        with self._open() as conn:
            rows = conn.execute(sql, (int(customer_id),)).fetchall()

        return [
            OrderRow(
                id=int(r[0]),
                order_uid=str(r[1]),
                customer_id=int(r[2]),
                edition=str(r[3]),
                app_version=str(r[4]),
                payment_ref=str(r[5]),
                fingerprint_sha256=str(r[6]),
                created_utc=str(r[7]),
            )
            for r in rows
        ]

    # -------------------------
    # Payments
    # -------------------------
    def insert_payment(
        self,
        *,
        provider: str,
        external_ref: str,
        amount: float,
        currency: str,
        paid_utc: str,
        note: str = "",
        order_id: Optional[int] = None,
    ) -> int:
        provider_norm = _norm_str(provider)
        external_ref_norm = _norm_str(external_ref)
        currency_norm = _norm_str(currency).upper() or "USD"
        paid_utc_norm = _norm_str(paid_utc)
        note_norm = _norm_str(note)

        if not provider_norm:
            raise ValueError("provider is required")
        if not paid_utc_norm:
            raise ValueError("paid_utc is required (ISO або інший стабільний формат)")
        if currency_norm not in {"UAH", "USD", "EUR"}:
            # якщо хочеш — розширимо, але без сміття
            raise ValueError("currency must be UAH/USD/EUR")
        if amount == 0:
            raise ValueError("amount cannot be 0")

        sql = """
        INSERT INTO payments (order_id, provider, external_ref,
                              amount, currency, paid_utc, note)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        with self._open() as conn:
            cur = conn.execute(
                sql,
                (
                    int(order_id) if order_id is not None else None,
                    provider_norm,
                    external_ref_norm,
                    float(amount),
                    currency_norm,
                    paid_utc_norm,
                    note_norm,
                ),
            )
            conn.commit()
            payment_id = int(cur.lastrowid or 0)

        self.audit(
            "INSERT_PAYMENT",
            f"provider={provider_norm}; external_ref={external_ref_norm}; "
            f"amount={amount}; {currency_norm}",
            entity_type="payment",
            entity_id=str(payment_id),
        )
        return payment_id

    def list_payments(
        self, *, order_id: Optional[int] = None, unassigned: bool = False
    ) -> list[PaymentRow]:
        if unassigned:
            sql = """
            SELECT id, order_id, provider, external_ref,
                   amount, currency, paid_utc, note
            FROM payments
            WHERE order_id IS NULL
            ORDER BY id DESC
            """
            params: tuple[object, ...] = ()
        elif order_id is None:
            sql = """
            SELECT id, order_id, provider, external_ref, amount,
                   currency, paid_utc, note
            FROM payments
            ORDER BY id DESC
            """
            params = ()
        else:
            sql = """
            SELECT id, order_id, provider, external_ref, amount,
                   currency, paid_utc, note
            FROM payments
            WHERE order_id = ?
            ORDER BY id DESC
            """
            params = (int(order_id),)

        with self._open() as conn:
            rows = conn.execute(sql, params).fetchall()

        out: list[PaymentRow] = []
        for r in rows:
            out.append(
                PaymentRow(
                    id=int(r[0]),
                    order_id=int(r[1]) if r[1] is not None else None,
                    provider=str(r[2]),
                    external_ref=str(r[3]),
                    amount=float(r[4]),
                    currency=str(r[5]),
                    paid_utc=str(r[6]),
                    note=str(r[7]),
                )
            )
        return out

    def assign_payment_to_order(self, *, payment_id: int, order_id: int) -> None:
        if payment_id <= 0:
            raise ValueError("payment_id must be > 0")
        if order_id <= 0:
            raise ValueError("order_id must be > 0")

        with self._open() as conn:
            old = conn.execute(
                "SELECT order_id FROM payments WHERE id = ? LIMIT 1",
                (int(payment_id),),
            ).fetchone()
            old_order_id = int(old[0]) if old and old[0] is not None else None

            conn.execute(
                "UPDATE payments SET order_id = ? WHERE id = ?",
                (int(order_id), int(payment_id)),
            )
            conn.commit()

        self.audit(
            "PAYMENT_ASSIGNED",
            f"payment_id={payment_id}; order_id={order_id}; "
            f"old_order_id={old_order_id}",
            entity_type="payment",
            entity_id=str(payment_id),
        )

    def find_unassigned_payments_for_order_uid(
        self,
        *,
        order_uid: str,
        limit: int = 20,
    ) -> list[PaymentRow]:
        """Знаходить платежі без прив'язки (order_id IS NULL)
        по збігу order_uid у external_ref/note."""

        order_uid_norm = _norm_str(order_uid)
        if not order_uid_norm:
            return []

        pat = f"%{order_uid_norm}%"
        sql = """
        SELECT id, order_id, provider, external_ref, amount, currency, paid_utc, note
        FROM payments
        WHERE order_id IS NULL
          AND (
                external_ref LIKE ?
             OR note LIKE ?
          )
        ORDER BY id DESC
        LIMIT ?
        """
        with self._open() as conn:
            rows = conn.execute(sql, (pat, pat, int(limit))).fetchall()

        out: list[PaymentRow] = []
        for r in rows:
            out.append(
                PaymentRow(
                    id=int(r[0]),
                    order_id=None,
                    provider=str(r[2]),
                    external_ref=str(r[3]),
                    amount=float(r[4]),
                    currency=str(r[5]),
                    paid_utc=str(r[6]),
                    note=str(r[7]),
                )
            )
        return out

    def attach_payments_for_order_uid(
        self,
        *,
        order_uid: str,
        order_id: int,
        limit: int = 20,
    ) -> int:
        """Автоприв'язує платежі до order_id за збігом order_uid у external_ref/note.

        Повертає кількість прив'язаних платежів.
        """

        if order_id <= 0:
            raise ValueError("order_id must be > 0")

        items = self.find_unassigned_payments_for_order_uid(
            order_uid=order_uid, limit=limit
        )
        n = 0
        for it in items:
            self.assign_payment_to_order(payment_id=int(it.id), order_id=int(order_id))
            n += 1
        return n

    def get_payments_summary_by_currency(self, *, order_id: int) -> dict[str, float]:
        """Повертає суми платежів по валюті для конкретного orders.id."""

        if order_id <= 0:
            return {}

        sql = """
        SELECT currency, COALESCE(SUM(amount), 0)
        FROM payments
        WHERE order_id = ?
        GROUP BY currency
        """
        with self._open() as conn:
            rows = conn.execute(sql, (int(order_id),)).fetchall()

        out: dict[str, float] = {}
        for cur, total in rows:
            cur_norm = _norm_str(cur)
            if cur_norm:
                out[cur_norm.upper()] = float(total or 0)
        return out

    def unassign_payment(self, *, payment_id: int) -> None:
        if payment_id <= 0:
            raise ValueError("payment_id must be > 0")

        with self._open() as conn:
            old = conn.execute(
                "SELECT order_id FROM payments WHERE id = ? LIMIT 1",
                (int(payment_id),),
            ).fetchone()
            old_order_id = int(old[0]) if old and old[0] is not None else None

            conn.execute(
                "UPDATE payments SET order_id = NULL WHERE id = ?", (int(payment_id),)
            )
            conn.commit()

        self.audit(
            "PAYMENT_UNASSIGNED",
            f"payment_id={payment_id}; old_order_id={old_order_id}",
            entity_type="payment",
            entity_id=str(payment_id),
        )

    # -------------------------
    # Licenses
    # -------------------------
    def get_license_by_order(self, order_id: int) -> Optional[LicenseRow]:
        if order_id <= 0:
            return None
        sql = """
        SELECT
            id,
            order_id,
            license_uid,
            license_rel_path,
            edition,
            issued_utc,
            sent_utc
        FROM licenses
        WHERE order_id = ?
        LIMIT 1
        """
        with self._open() as conn:
            row = conn.execute(sql, (int(order_id),)).fetchone()

        if not row:
            return None
        return LicenseRow(
            id=int(row[0]),
            order_id=int(row[1]),
            license_uid=str(row[2]),
            license_rel_path=str(row[3]),
            edition=str(row[4]),
            issued_utc=str(row[5]),
            sent_utc=str(row[6] or ""),
        )

    def has_license_for_order_row_id(self, order_id: int) -> bool:
        return self.get_license_by_order(order_id) is not None

    def insert_license(
        self,
        *,
        order_id: int,
        license_uid: str,
        license_rel_path: str,
        edition: str,
        issued_utc: Optional[str] = None,
    ) -> int:
        if order_id <= 0:
            raise ValueError("order_id must be > 0")

        license_uid_norm = _norm_str(license_uid)
        license_rel_path_norm = _norm_str(license_rel_path)
        edition_norm = _norm_str(edition)

        if not license_uid_norm:
            raise ValueError("license_uid is required")
        if not license_rel_path_norm:
            raise ValueError("license_rel_path is required")
        if not edition_norm:
            raise ValueError("edition is required")
        sql = """
        INSERT INTO licenses (order_id, license_uid,
                              license_rel_path, edition, issued_utc)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(order_id) DO UPDATE SET
            license_uid=excluded.license_uid,
            license_rel_path=excluded.license_rel_path,
            edition=excluded.edition
        """

        with self._open() as conn:
            conn.execute(
                sql,
                (
                    int(order_id),
                    license_uid_norm,
                    license_rel_path_norm,
                    edition_norm,
                    issued_utc,
                ),
            )
            row = conn.execute(
                "SELECT id FROM licenses WHERE order_id = ? LIMIT 1",
                (int(order_id),),
            ).fetchone()
            conn.commit()

        if row is None or row[0] is None:
            raise RuntimeError("failed to insert license")

        lic_id = int(row[0])

        self.audit(
            "UPSERT_LICENSE",
            f"order_id={order_id}; license_uid={license_uid_norm}; "
            f"path={license_rel_path_norm}; edition={edition_norm}",
            entity_type="license",
            entity_id=str(lic_id),
        )
        return lic_id

    def set_license_sent_utc(self, *, license_uid: str, sent_utc: str) -> None:
        """Оновити sent_utc у licenses для вказаного license_uid."""
        license_uid_norm = _norm_str(license_uid)
        sent_utc_norm = _norm_str(sent_utc)

        if not license_uid_norm:
            raise ValueError("license_uid is required")
        if not sent_utc_norm:
            raise ValueError("sent_utc is required")

        with self._open() as conn:
            conn.execute(
                """
                UPDATE licenses
                SET sent_utc = ?
                WHERE license_uid = ?
                """,
                (sent_utc_norm, license_uid_norm),
            )
            conn.commit()

    def get_customer_by_email(self, email: str) -> dict[str, str] | None:
        """Повернути клієнта за email або None."""
        sql = """
        SELECT id, email, name, note
        FROM customers
        WHERE lower(email) = lower(?)
        LIMIT 1
        """

        with self._open() as conn:
            row = conn.execute(sql, (email,)).fetchone()

        if not row:
            return None

        return {
            "id": str(row[0]),
            "email": str(row[1] or ""),
            "name": str(row[2] or ""),
            "note": str(row[3] or ""),
        }

    def get_order_by_uid(self, order_uid: str) -> dict | None:
        sql = """
        SELECT id, order_uid
        FROM orders
        WHERE order_uid = ?
        LIMIT 1
        """

        with self._open() as conn:
            row = conn.execute(sql, (order_uid,)).fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "order_uid": row[1],
        }

    def set_license_issued_utc(self, *, license_uid: str, issued_utc: str) -> None:
        """Оновити issued_utc у licenses для вказаного license_uid."""
        license_uid_norm = _norm_str(license_uid)
        issued_utc_norm = _norm_str(issued_utc)

        if not license_uid_norm:
            raise ValueError("license_uid is required")
        if not issued_utc_norm:
            raise ValueError("issued_utc is required")

        with self._open() as conn:
            conn.execute(
                """
                UPDATE licenses
                SET issued_utc = ?
                WHERE license_uid = ?
                """,
                (issued_utc_norm, license_uid_norm),
            )
            conn.commit()

    def find_paid_pro_order(
        self,
        *,
        customer_id: int,
        fingerprint: str,
        required_pro_price: float,
        tolerance: float = 0.50,
    ) -> int | None:
        """
        Знайти оплачений order редакції PRO для цього клієнта і fingerprint.
        Повертає order.id або None.
        """
        sql = """
        SELECT id
        FROM orders
        WHERE customer_id = ?
          AND edition = 'PRO'
          AND fingerprint_sha256 = ?
        ORDER BY id DESC
        """

        with self._open() as conn:
            rows = conn.execute(
                sql,
                (
                    int(customer_id),
                    str(fingerprint),
                ),
            ).fetchall()

        for row in rows:
            try:
                order_id = int(row[0])
            except (TypeError, ValueError):
                continue

            total_paid = self.get_total_paid_for_order(order_id)
            if total_paid + tolerance >= required_pro_price:
                return order_id

        return None

    def get_total_paid_for_order(self, order_id: int) -> float:
        """Повернути суму всіх платежів по замовленню."""
        sql = """
        SELECT COALESCE(SUM(amount), 0)
        FROM payments
        WHERE order_id = ?
        """
        with self._open() as conn:
            row = conn.execute(sql, (int(order_id),)).fetchone()

        if not row:
            return 0.0

        try:
            return float(row[0] or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def get_required_amount_for_edition(
        self,
        *,
        customer_id: int,
        fingerprint: str,
        target_edition: str,
    ) -> float:
        """
        Повернути потрібну суму для видачі/апгрейду ліцензії.
        Підтримує апгрейд PRO -> PRO+.
        """
        target_price = float(get_price_usd(target_edition))

        if target_edition != "PRO_PLUS":
            return target_price

        pro_price = float(get_price_usd("PRO"))

        pro_order_id = self.find_paid_pro_order(
            customer_id=customer_id,
            fingerprint=fingerprint,
            required_pro_price=pro_price,
        )

        if not pro_order_id:
            return target_price

        paid_for_pro = self.get_total_paid_for_order(pro_order_id)
        required = target_price - paid_for_pro

        return max(required, 0.0)
