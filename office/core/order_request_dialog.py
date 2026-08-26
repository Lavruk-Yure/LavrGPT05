# order_request_dialog.py
# -*- coding: utf-8 -*-
"""
OrderRequestDialog — створення запиту/замовлення ліцензії для LGEOffice.

Поточний робочий алгоритм (RoadMap42):
- стартує навіть з порожньої БД;
- бере ORDER_ID з форми;
- шукає customer по email;
- якщо customer не існує — створює;
- якщо order з таким ORDER_ID уже існує — НЕ створює дублікат
  (бо orders.order_uid у схемі UNIQUE), а переводить selection на існуючий запис;
- якщо order не існує — створює його і робить активним.
"""

from __future__ import annotations

import hashlib
import logging
import re

from PySide6.QtCore import Qt
from PySide6.QtSql import QSqlQuery, QSqlTableModel
from PySide6.QtWidgets import QDialog, QMessageBox

from office.core.datetime_utils import utc_now_str
from office.ui.ui_order_request import Ui_OrderRequestDialog

logger = logging.getLogger(__name__)

ROLE_EDIT = Qt.ItemDataRole.EditRole

_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_RE_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_RE_APP_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_RE_ORDER_UID = re.compile(r"^LGE-\d{8}-\d{4}-[A-Z0-9]{4,}$")

_ALLOWED_EDITIONS = {"PRO", "PRO+"}
_MAX_NAME_LEN = 120
_MAX_NOTE_LEN = 1000
_MAX_PAYMENT_REF_LEN = 255
_MAX_ORDER_UID_LEN = 64


def _now_utc_str() -> str:
    """Повернути UTC у канонічному форматі для БД."""
    return utc_now_str()


def _norm_email(value: str) -> str:
    """Нормалізувати email."""
    return (value or "").strip().lower()


def _sha256_hex(value: str) -> str:
    """SHA256 hex для довільного рядка."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class OrderRequestDialog(QDialog):
    """Модальне вікно створення замовлення."""

    def __init__(self, host, *, customer_id: int = 0) -> None:
        super().__init__(host)
        self.host = host
        self.customer_id = int(customer_id or 0)

        self.ui = Ui_OrderRequestDialog()
        self.ui.setupUi(self)

        self.created_customer_id: int = 0
        self.created_customer_email: str = ""
        self.created_order_uid: str = ""

        self._bind()
        self._apply_defaults()

        logger.debug(
            "OrderRequestDialog init: customer_id=%s",
            self.customer_id,
        )

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _bind(self) -> None:
        self.ui.buttonBox.accepted.connect(self._on_ok)
        self.ui.buttonBox.rejected.connect(self.reject)

        for w in (
            self.ui.leEmail,
            self.ui.leRef,
            self.ui.leAppVersion,
            self.ui.lePaymentRef,
            self.ui.leFingerprint,
            self.ui.leName,
        ):
            w.returnPressed.connect(self._on_ok)

    def _apply_defaults(self) -> None:
        self.ui.leEmail.setReadOnly(False)
        self.ui.leRef.setReadOnly(False)

        self.ui.leRef.setFocus()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_row_by_field(
        model: QSqlTableModel,
        field_name: str,
        value,
        *,
        casefold_text: bool = False,
    ) -> int:
        col = model.fieldIndex(field_name)
        if col < 0:
            return -1

        for row in range(model.rowCount()):
            cell = model.data(model.index(row, col), ROLE_EDIT)
            if casefold_text:
                left = str(cell or "").strip().lower()
                right = str(value or "").strip().lower()
                if left == right:
                    return row
            else:
                if cell == value:
                    return row
        return -1

    @staticmethod
    def _int_field(model: QSqlTableModel, row: int, field_name: str) -> int:
        col = model.fieldIndex(field_name)
        if col < 0 or row < 0:
            return 0
        value = model.data(model.index(row, col), ROLE_EDIT)
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _set_field(
        model: QSqlTableModel,
        row: int,
        field_name: str,
        value,
    ) -> None:
        col = model.fieldIndex(field_name)
        if col >= 0:
            model.setData(model.index(row, col), value, ROLE_EDIT)

    def _validate_form(
        self,
    ) -> tuple[bool, str, str, str, str, str, str, str, str]:
        """
        Перевірити форму.

        Повертає:
        ok,
        customer_email,
        order_uid,
        edition,
        app_version,
        payment_ref,
        fingerprint_db,
        name,
        note
        """
        try:
            customer_email = self._req_customer_email()
            order_uid = self._req_order_uid()
            edition = self._req_edition()
            app_version = self._req_app_version()
            payment_ref = self._req_payment_ref(order_uid)
            fingerprint_db = self._req_fingerprint()
            name = self._opt_name()
            note = self._opt_note()
        except ValueError as exc:
            self._msg_invalid(str(exc))
            return False, "", "", "", "", "", "", "", ""

        return (
            True,
            customer_email,
            order_uid,
            edition,
            app_version,
            payment_ref,
            fingerprint_db,
            name,
            note,
        )

    def _ensure_customer(
        self,
        model_customers: QSqlTableModel,
        customer_email: str,
        name: str,
        note: str,
    ) -> int:
        """Знайти customer по email або створити/оновити."""
        row = self._find_row_by_field(
            model_customers,
            "email",
            customer_email,
            casefold_text=True,
        )
        if row >= 0:
            # Оновити дані існуючого customer
            self._set_field(model_customers, row, "name", name)

            col_note = model_customers.fieldIndex("note")
            if col_note >= 0:
                self._set_field(model_customers, row, "note", note)

            if model_customers.isDirty():
                if not model_customers.submitAll():
                    err = model_customers.lastError().text()
                    logger.error("Customers update submitAll failed: %s", err)
                    model_customers.revertAll()
                    raise RuntimeError(f"Не вдалося оновити customer.\n\n{err}")
                model_customers.select()

            customer_id = self._int_field(model_customers, row, "id")
            logger.debug(
                "OrderRequestDialog: customer found email=%s id=%s",
                customer_email,
                customer_id,
            )
            return customer_id

        row = model_customers.rowCount()
        if not model_customers.insertRow(row):
            raise RuntimeError("Не вдалося вставити рядок customers.")

        self._set_field(model_customers, row, "id", None)
        self._set_field(model_customers, row, "email", customer_email)
        self._set_field(model_customers, row, "name", name)

        col_note = model_customers.fieldIndex("note")
        if col_note >= 0:
            self._set_field(model_customers, row, "note", note)

        self._set_field(model_customers, row, "created_utc", _now_utc_str())

        if not model_customers.submitAll():
            err = model_customers.lastError().text()
            logger.error("Customers submitAll failed: %s", err)
            model_customers.revertAll()
            raise RuntimeError(f"Не вдалося зберегти customer.\n\n{err}")

        model_customers.select()

        row = self._find_row_by_field(
            model_customers,
            "email",
            customer_email,
            casefold_text=True,
        )
        if row < 0:
            raise RuntimeError("Customer збережено, але повторно не знайдено.")

        customer_id = self._int_field(model_customers, row, "id")
        logger.debug(
            "OrderRequestDialog: customer created email=%s id=%s",
            customer_email,
            customer_id,
        )
        return customer_id

    def _order_row_by_uid(
        self,
        model_orders: QSqlTableModel,
        order_uid: str,
    ) -> int:
        return self._find_row_by_field(
            model_orders,
            "order_uid",
            order_uid,
            casefold_text=False,
        )

    def _create_order(
        self,
        model_orders: QSqlTableModel,
        *,
        customer_id: int,
        order_uid: str,
        edition: str,
        app_version: str,
        payment_ref: str,
        fingerprint_db: str,
    ) -> None:
        row = model_orders.rowCount()
        if not model_orders.insertRow(row):
            raise RuntimeError("Не вдалося вставити рядок orders.")

        self._set_field(model_orders, row, "id", None)
        self._set_field(model_orders, row, "customer_id", customer_id)
        self._set_field(model_orders, row, "order_uid", order_uid)
        self._set_field(model_orders, row, "edition", edition)
        self._set_field(model_orders, row, "app_version", app_version)
        self._set_field(model_orders, row, "payment_ref", payment_ref)
        self._set_field(model_orders, row, "fingerprint_sha256", fingerprint_db)
        self._set_field(model_orders, row, "created_utc", _now_utc_str())

        if not model_orders.submitAll():
            err = model_orders.lastError().text()
            logger.error("Orders submitAll failed: %s", err)
            model_orders.revertAll()
            raise RuntimeError(f"Не вдалося зберегти замовлення.\n\n{err}")

        logger.debug(
            "OrderRequestDialog: order created uid=%s customer_id=%s",
            order_uid,
            customer_id,
        )

    def _select_customer_in_host(self, customer_email: str) -> None:
        m = getattr(self.host, "model_customers", None)
        tv = self.host.ui.tvCustomers
        if m is None:
            return

        m.select()
        row = self._find_row_by_field(m, "email", customer_email, casefold_text=True)
        if row >= 0:
            tv.selectRow(row)
            tv.scrollTo(m.index(row, 0))
            tv.setFocus()

    def _select_order_in_host(self, customer_id: int, order_uid: str) -> None:
        ord_logic = getattr(self.host, "ord", None)
        if ord_logic is not None:
            ord_logic.apply_customer_filter(customer_id)
            ord_logic.refresh(select_order_uid=order_uid)
            return

        m = getattr(self.host, "model_orders", None)
        tv = self.host.ui.tvOrders
        if m is None:
            return

        m.setFilter(f"customer_id = {customer_id}")
        m.select()

        row = self._order_row_by_uid(m, order_uid)
        if row >= 0:
            tv.selectRow(row)
            tv.scrollTo(m.index(row, 0))
            tv.setFocus()

    # ------------------------------------------------------------------
    # OK
    # ------------------------------------------------------------------
    def _on_ok(self) -> None:
        model_customers: QSqlTableModel = getattr(self.host, "model_customers", None)
        model_orders: QSqlTableModel = getattr(self.host, "model_orders", None)

        if model_customers is None or model_orders is None:
            QMessageBox.warning(
                self,
                "Замовлення",
                "Моделі customers/orders не знайдено.",
            )
            return

        (
            ok,
            customer_email,
            order_uid,
            edition,
            app_version,
            payment_ref,
            fingerprint_db,
            name,
            note,
        ) = self._validate_form()

        if not ok:
            return

        logger.debug(
            "OrderRequestDialog OK: customer=%s order_uid=%s",
            customer_email,
            order_uid,
        )

        try:
            customer_id = self._ensure_customer(
                model_customers,
                customer_email,
                name,
                note,
            )
        except RuntimeError as exc:
            QMessageBox.warning(self, "Замовлення", str(exc))
            return

        model_orders.select()
        existing_order_id, existing_customer_id = self._db_order_info_by_uid(order_uid)

        if existing_order_id > 0:
            QMessageBox.information(
                self,
                "Замовлення",
                "Замовлення з таким ORDER_ID уже існує.\n\n"
                "Новий запис створено не буде.\n"
                "Буде активовано існуючий запис.",
            )

            self.created_customer_id = existing_customer_id
            self.created_customer_email = customer_email
            self.created_order_uid = order_uid

            self._select_customer_in_host(customer_email)
            self._select_order_in_host(existing_customer_id, order_uid)
            self.accept()
            return

        dup_pay_row = self._find_order_row_by_payment_ref(model_orders, payment_ref)
        if dup_pay_row >= 0:
            QMessageBox.warning(
                self,
                "Замовлення",
                "Замовлення з таким Payment reference уже існує.\n\n"
                "Створення дубля заблоковано.",
            )
            return

        dup_fp_row = self._find_order_row_by_fingerprint(model_orders, fingerprint_db)
        if dup_fp_row >= 0:
            QMessageBox.warning(
                self,
                "Замовлення",
                "Замовлення з таким Fingerprint уже існує.\n\n"
                "Створення дубля заблоковано.",
            )
            return

        try:
            self._create_order(
                model_orders,
                customer_id=customer_id,
                order_uid=order_uid,
                edition=edition,
                app_version=app_version,
                payment_ref=payment_ref,
                fingerprint_db=fingerprint_db,
            )
        except RuntimeError as exc:
            QMessageBox.warning(self, "Замовлення", str(exc))
            return

        self.created_customer_id = customer_id
        self.created_customer_email = customer_email
        self.created_order_uid = order_uid

        self._select_customer_in_host(customer_email)
        self._select_order_in_host(customer_id, order_uid)

        logger.debug(
            "OrderRequestDialog success: customer_id=%s order_uid=%s",
            self.created_customer_id,
            self.created_order_uid,
        )
        self.accept()

    def _req_customer_email(self) -> str:
        value = _norm_email(self.ui.leEmail.text())
        if not value:
            raise ValueError("Customer email порожній.")
        if " " in value:
            raise ValueError("Customer email не може містити пробіли.")
        if not _RE_EMAIL.match(value):
            raise ValueError("Customer email має невірний формат.")
        return value

    def _req_order_uid(self) -> str:
        value = str(self.ui.leRef.text() or "").strip()
        if not value:
            raise ValueError("ORDER_ID порожній.")
        if "\n" in value or "\r" in value:
            raise ValueError("ORDER_ID не може містити переноси рядка.")
        if len(value) > _MAX_ORDER_UID_LEN:
            raise ValueError("ORDER_ID занадто довгий.")
        if not _RE_ORDER_UID.match(value):
            raise ValueError(
                "ORDER_ID має невірний формат.\n\n"
                "Очікується щось на кшталт:\n"
                "LGE-20260215-1236-5904"
            )
        return value

    def _req_edition(self) -> str:
        value = str(self.ui.cbEdition.currentText() or "").strip().upper()
        if value not in _ALLOWED_EDITIONS:
            raise ValueError("Невірна редакція. Дозволено: PRO або PRO+.")
        return value

    def _req_app_version(self) -> str:
        value = str(self.ui.leAppVersion.text() or "").strip()
        if not value:
            raise ValueError("App version порожня.")
        if "\n" in value or "\r" in value:
            raise ValueError("App version не може містити переноси рядка.")
        if not _RE_APP_VERSION.match(value):
            raise ValueError(
                "App version має невірний формат.\n\n" "Очікується формат: 1.0.0"
            )
        return value

    def _req_payment_ref(self, order_uid: str) -> str:
        value = str(self.ui.lePaymentRef.text() or "").strip()
        if not value:
            raise ValueError("Payment reference порожній.")
        if "\n" in value or "\r" in value:
            raise ValueError("Payment reference не може містити переноси рядка.")
        if len(value) > _MAX_PAYMENT_REF_LEN:
            raise ValueError("Payment reference занадто довгий.")
        if order_uid not in value:
            raise ValueError(
                "Payment reference має містити ORDER_ID.\n\n"
                "Це захист від помилкового вводу."
            )
        return value

    def _req_fingerprint(self) -> str:
        value = str(self.ui.leFingerprint.text() or "").strip().lower()
        if not value:
            raise ValueError("Fingerprint порожній.")

        if not _RE_SHA256.match(value):
            raise ValueError(
                "Fingerprint має бути SHA256 hex довжиною 64 символи.\n\n"
                f"Зараз введено: {len(value)} символів."
            )

        return value

    def _opt_note(self) -> str:
        value = str(self.ui.pteNote.toPlainText() or "").strip()
        if len(value) > _MAX_NOTE_LEN:
            raise ValueError("Примітка занадто довга.")
        return value

    def _find_order_row_by_payment_ref(
        self,
        model_orders: QSqlTableModel,
        payment_ref: str,
    ) -> int:
        return self._find_row_by_field(
            model_orders,
            "payment_ref",
            payment_ref,
            casefold_text=False,
        )

    def _find_order_row_by_fingerprint(
        self,
        model_orders: QSqlTableModel,
        fingerprint_db: str,
    ) -> int:
        return self._find_row_by_field(
            model_orders,
            "fingerprint_sha256",
            fingerprint_db,
            casefold_text=False,
        )

    def _opt_name(self) -> str:
        value = str(self.ui.leName.text() or "").strip()
        if "\n" in value or "\r" in value:
            raise ValueError("ПІБ не може містити переноси рядка.")
        if len(value) > _MAX_NAME_LEN:
            raise ValueError("ПІБ занадто довгий.")
        return value

    def _msg_invalid(self, text: str) -> None:
        QMessageBox.warning(self, "Замовлення", text)

    def _db_order_info_by_uid(self, order_uid: str) -> tuple[int, int]:
        """
        Повернути (order_id, customer_id) для order_uid.
        Якщо не знайдено — (0, 0).
        """
        db = getattr(self.host, "db", None)
        if db is None:
            return 0, 0

        q = QSqlQuery(db)
        q.prepare(
            """
            SELECT id, customer_id
            FROM orders
            WHERE order_uid = ?
            LIMIT 1
            """
        )
        q.addBindValue(order_uid)

        if not q.exec():
            logger.error(
                "Order lookup by uid failed: %s",
                q.lastError().text(),
            )
            return 0, 0

        if not q.next():
            return 0, 0

        try:
            order_id = int(q.value(0) or 0)
        except (TypeError, ValueError):
            order_id = 0

        try:
            customer_id = int(q.value(1) or 0)
        except (TypeError, ValueError):
            customer_id = 0

        return order_id, customer_id
