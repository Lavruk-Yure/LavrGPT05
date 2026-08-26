# db_grid_window_logic_ord.py
# -*- coding: utf-8 -*-
"""
OrdersLogic — логіка таблиці orders (RoadMap37).

Правила:
- 1 таблиця = 1 логіка
- жодної універсальної grid_* логіки
- залежить тільки від customers (customer_id)
- payments/licenses не чіпаємо, але при delete перевіряємо зв'язки

Ключове:
- pending delete IDs + delete-only save
  (валідація НЕ має спрацьовувати при чистому видаленні)
- order_uid: LGE-YYYYMMDD-HHMM-XXXX (цифри)
- edition: PRO / PRO_PLUS (ввід може бути "PRO PLUS" -> нормалізуємо в PRO_PLUS)
- app_version: X.Y.Z
- fingerprint_sha256: 64 hex
"""

from __future__ import annotations

import base64
import json
import logging
import re
import secrets
from datetime import UTC, datetime

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from PySide6.QtCore import Qt
from PySide6.QtSql import QSqlQuery, QSqlTableModel
from PySide6.QtWidgets import QMessageBox, QTableView

from office.core import session_state
from office.core.datetime_utils import utc_now_str
from office.core.db_repo import DbRepo
from office.core.office_paths import (
    get_licenses_dir,
    get_office_dir,
    get_private_key_path,
)

logger = logging.getLogger(__name__)

_RE_APP_VER = re.compile(r"^\d+\.\d+\.\d+$")
_RE_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_RE_ORDER_UID = re.compile(r"^LGE-\d{8}-\d{4}-\d{4}$")

_ALLOWED_EDITIONS = {"PRO", "PRO+"}


class OrdersLogic:
    def __init__(self, host) -> None:
        self.host = host

        self._dirty = False

        # якщо є видалення — тримаємо список PK, щоб:
        # - не валідовати видалені рядки
        # - дозволити delete-only save без валідації
        self._pending_delete_ids: set[int] = set()

        self.model_orders: QSqlTableModel | None = None

        self._init_orders_model()
        self._configure_orders_view()
        self._bind_dirty_signals()

        # старт: якщо клієнта ще не вибрано — закриваємо таблицю
        self.apply_customer_filter(self.host.current_customer_id())

    # ------------------------------------------------------------------
    # Model
    # ------------------------------------------------------------------

    def _init_orders_model(self) -> None:
        if self.host.db is None:
            raise RuntimeError("DB is not initialized")

        m = QSqlTableModel(self.host, self.host.db)
        m.setTable("orders")
        m.setEditStrategy(QSqlTableModel.EditStrategy.OnManualSubmit)

        # без сортування і без фільтра на старті
        m.select()
        self.host.after_model_select(
            self.host.ui.tvOrders, self.host.model_orders, "orders"
        )

        self.model_orders = m
        self.host.model_orders = m
        self.host.ui.tvOrders.setModel(m)

    # ------------------------------------------------------------------
    # View
    # ------------------------------------------------------------------

    def _configure_orders_view(self) -> None:
        tv = self.host.ui.tvOrders
        tv.setEnabled(True)

        tv.setEditTriggers(QTableView.EditTrigger.DoubleClicked)
        tv.setTabKeyNavigation(True)
        tv.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        tv.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        tv.setAlternatingRowColors(True)

        tv.setSortingEnabled(False)  # увімкнемо пізніше, коли буде стабільно
        tv.horizontalHeader().setStretchLastSection(True)
        tv.verticalHeader().setVisible(False)

        m = self.model_orders
        if m is None:
            return

        self.host.set_widths(
            tv,
            m,
            {
                "id": 60,
                "order_uid": 220,
                "edition": 90,
                "app_version": 90,
                "payment_ref": 220,
                "fingerprint_sha256": 260,
                "created_utc": 170,
            },
        )

        self.host.set_readonly_id_column(tv, m)

        self.host.set_headers(
            m,
            {
                "id": "№",
                "order_uid": "Код замовлення",
                "edition": "Редакція",
                "app_version": "Версія",
                "payment_ref": "Платіж (Ref)",
                "fingerprint_sha256": "Відбиток (SHA256)",
                "created_utc": "Створено (UTC)",
            },
        )

        # id readonly
        col_id = m.fieldIndex("id")
        if col_id >= 0:
            tv.setItemDelegateForColumn(col_id, self.host.ro_delegate)

        # customer_id hidden
        col_cust = m.fieldIndex("customer_id")
        if col_cust >= 0:
            tv.setColumnHidden(col_cust, True)

        # created_utc delegate (editable OK)
        col_created = m.fieldIndex("created_utc")
        if col_created >= 0:
            tv.setItemDelegateForColumn(col_created, self.host.utc_delegate)

        self.update_nav_state()

    # ------------------------------------------------------------------
    # Master → Detail
    # ------------------------------------------------------------------

    def apply_customer_filter(self, customer_id: int | None) -> None:
        m = self.model_orders
        if m is None:
            return

        if not customer_id:
            m.setFilter("1=0")
        else:
            m.setFilter(f"customer_id = {customer_id}")

        m.select()
        self.host.after_model_select(
            self.host.ui.tvOrders, self.host.model_orders, "orders"
        )

        tv = self.host.ui.tvOrders
        if m.rowCount() > 0:
            tv.selectRow(0)

        # при зміні клієнта “pending delete” не переносимо
        self._pending_delete_ids.clear()
        self._set_dirty(False)

        self.update_nav_state()

    # ------------------------------------------------------------------
    # Dirty tracking
    # ------------------------------------------------------------------

    def _bind_dirty_signals(self) -> None:
        m = self.model_orders
        if m is None:
            return

        m.dataChanged.connect(lambda *_: self._set_dirty(True))
        m.rowsInserted.connect(lambda *_: self._set_dirty(True))
        m.rowsRemoved.connect(lambda *_: self._set_dirty(True))

        sm = self.host.ui.tvOrders.selectionModel()
        if sm is not None:
            sm.currentChanged.connect(lambda *_: self.update_nav_state())

    def _set_dirty(self, value: bool) -> None:
        self._dirty = value
        self.update_nav_state()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(self) -> None:
        m = self.model_orders
        if m is None:
            return

        cust_id = self.host.current_customer_id()
        if not cust_id:
            QMessageBox.warning(self.host, "Замовлення", "Спочатку виберіть клієнта.")
            return

        tv = self.host.ui.tvOrders
        tv.clearFocus()
        tv.setSortingEnabled(False)

        row = m.rowCount()
        if not m.insertRow(row):
            QMessageBox.warning(self.host, "Замовлення", "Не вдалося додати рядок.")
            return

        self._set_field(row, "customer_id", cust_id)
        self._set_field(row, "created_utc", utc_now_str())

        # фокус у order_uid
        col = m.fieldIndex("order_uid")
        if col >= 0:
            self._focus_cell(row, col)

        self._set_dirty(True)

    def delete(self) -> None:
        m = self.model_orders
        if m is None:
            return

        tv = self.host.ui.tvOrders
        idx = tv.currentIndex()
        if not idx.isValid():
            return

        row = idx.row()

        order_pk = self._get_int(row, "id")
        if not order_pk:
            return

        # 1) licenses: RESTRICT
        if self._has_license(order_pk):
            QMessageBox.warning(
                self.host,
                "Замовлення",
                "Неможливо видалити замовлення.\n\nІснує пов’язана ліцензія.",
            )
            return

        # 2) payments: SET NULL (можна, але попереджаємо)
        pay_cnt = self._payments_count(order_pk)
        if pay_cnt > 0:
            text = (
                f"Є пов’язані платежі: {pay_cnt}.\n\n"
                "При видаленні замовлення ці платежі будуть відв’язані "
                "(order_id стане порожнім).\n\n"
                "Продовжити?"
            )
            if not self._confirm(text):
                return
        else:
            if not self.host.confirm_delete("Замовлення"):
                return

        self._pending_delete_ids.add(order_pk)
        m.removeRow(row)
        self._set_dirty(True)

    def save(self) -> None:
        logger.debug("Orders.save() called: dirty=%s", self._dirty)

        m = self.model_orders
        if m is None:
            return

        tv = self.host.ui.tvOrders
        tv.clearFocus()
        tv.setSortingEnabled(False)

        delete_only = self._is_delete_only_change()

        current_id = self._current_selected_id()
        pending_order_uid = self._current_pending_order_uid()

        delete_pick_row = self._preferred_row_after_delete()

        # Нормалізація/валідація НЕ повинна спрацьовувати при чистому видаленні
        if not delete_only:
            try:
                self.host.normalize_model_utc_field(m, "created_utc")
            except ValueError as e:
                QMessageBox.warning(self.host, "Замовлення", str(e))
                return

            for row in range(m.rowCount()):
                if self._row_was_deleted(row):
                    continue

                if not self._req_order_uid(row):
                    return
                if not self._req_edition(row):
                    return

                app_version = self._str(row, "app_version")
                if not app_version or not _RE_APP_VER.fullmatch(app_version):
                    QMessageBox.warning(
                        self.host,
                        "Замовлення",
                        "app_version обов’язкове.\nФормат: X.Y.Z (наприклад 1.0.0).",
                    )
                    self._focus_field(row, "app_version")
                    return

                fp_raw = self._str(row, "fingerprint_sha256")
                fp = re.sub(r"\s+", "", fp_raw).lower()

                if not fp or not _RE_SHA256.fullmatch(fp):
                    QMessageBox.warning(
                        self.host,
                        "Замовлення",
                        "fingerprint_sha256 обов’язкове.\n"
                        f"Зараз: length={len(fp)}.\n"
                        "Має бути SHA-256 hex: рівно 64 символи (a-f,0-9).",
                    )
                    self._focus_field(row, "fingerprint_sha256")
                    return

                self._set_field(row, "fingerprint_sha256", fp)

        ok = m.submitAll()
        if not ok:
            err = m.lastError().text()
            logger.error("Orders SAVE failed: %s", err)

            # дружні повідомлення для частих випадків
            if "UNIQUE constraint failed: orders.order_uid" in err:
                QMessageBox.warning(
                    self.host,
                    "Замовлення",
                    "Не вдалося зберегти.\n\n"
                    "order_uid має бути унікальним.\n"
                    "Такий order_uid вже існує.",
                )
                return

            QMessageBox.warning(
                self.host, "Замовлення", f"Не вдалося зберегти.\n\n{err}"
            )
            return

        self._pending_delete_ids.clear()
        self._set_dirty(False)

        last_id = None
        db = self.host.db
        if db is not None:
            q = QSqlQuery(db)
            if q.exec("SELECT last_insert_rowid();") and q.next():
                try:
                    v = int(q.value(0))
                    if v > 0:
                        last_id = v
                except Exception:  # noqa
                    last_id = None

        self.refresh(
            select_id=last_id or current_id,
            select_order_uid=pending_order_uid,
            select_row_hint=delete_pick_row,
        )

    def cancel(self) -> None:
        m = self.model_orders
        if m is None:
            return
        m.revertAll()
        self._pending_delete_ids.clear()
        self._set_dirty(False)
        self.refresh()

    def refresh(
        self,
        select_id: int | None = None,
        select_order_uid: str = "",
        select_row_hint: int | None = None,
    ) -> None:
        m = self.model_orders
        if m is None:
            return

        tv = self.host.ui.tvOrders

        m.select()
        self.host.after_model_select(
            self.host.ui.tvOrders, self.host.model_orders, "orders"
        )

        selected = False

        if select_id:
            selected = self._select_row_by_id(tv, m, select_id)

        if (not selected) and select_order_uid:
            selected = self._select_row_by_order_uid(tv, m, select_order_uid)

        if (not selected) and select_row_hint is not None and m.rowCount() > 0:
            row = max(0, min(select_row_hint, m.rowCount() - 1))
            tv.selectRow(row)
            tv.scrollTo(m.index(row, 0))
            tv.setFocus()
            selected = True

        if (not selected) and m.rowCount() > 0:
            tv.selectRow(0)
            tv.scrollTo(m.index(0, 0))
            tv.setFocus()
        elif not selected:
            tv.clearSelection()

        self.update_nav_state()

    def issue_license(self) -> None:
        """Видати або перевидати ліцензію для поточного замовлення."""
        order_id = self._current_order_id()
        if not order_id:
            QMessageBox.warning(self.host, "Видача ліцензії", "Замовлення не вибране.")
            return

        allowed, required_price, paid_total = self._check_payment_sufficiency(order_id)

        if not allowed:
            if paid_total <= 0:
                text = (
                    "Немає оплати для цього замовлення.\n\n"
                    f"Потрібно: {required_price:.2f} USD\n"
                    f"Сплачено: {paid_total:.2f} USD"
                )
            else:
                deficit = required_price - paid_total
                text = (
                    "Недостатньо оплати для цього замовлення.\n\n"
                    f"Потрібно: {required_price:.2f} USD\n"
                    f"Сплачено: {paid_total:.2f} USD\n"
                    f"Не вистачає: {deficit:.2f} USD"
                )

            QMessageBox.warning(
                self.host,
                "Видача ліцензії",
                text,
            )
            return

        if paid_total > required_price + 1.0:
            overpay = paid_total - required_price

            reply = QMessageBox.question(
                self.host,
                "Видача ліцензії",
                f"Виявлено переплату.\n\n"
                f"Потрібно: {required_price:.2f} USD\n"
                f"Сплачено: {paid_total:.2f} USD\n"
                f"Переплата: {overpay:.2f} USD\n\n"
                "Видати ліцензію все одно?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

        existing_id = self._existing_license_id(order_id)
        if existing_id:
            reply = QMessageBox.question(
                self.host,
                "Видача ліцензії",
                "Ліцензія вже існує.\nПеревидати?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

            # беремо існуючий uid і шлях
            license_uid, license_rel_path = self._existing_license_data(order_id)
            if not license_uid or not license_rel_path:
                QMessageBox.warning(
                    self.host,
                    "Видача ліцензії",
                    "Не вдалося отримати існуючі дані ліцензії для перевидачі.",
                )
                return

            reissue = True
        else:
            license_uid = self._generate_license_uid()
            license_rel_path = f"licenses/{license_uid}.lic"
            reissue = False

        order_uid = self._current_order_field("order_uid")
        edition = self._current_order_field("edition")
        app_version = self._current_order_field("app_version")
        payment_ref = self._current_order_field("payment_ref")
        fingerprint = self._current_order_field("fingerprint_sha256")
        customer_email = self._customer_email_for_order(order_id)

        if not order_uid:
            QMessageBox.warning(
                self.host,
                "Видача ліцензії",
                "У замовленні відсутній order_uid.",
            )
            return

        if not edition:
            QMessageBox.warning(
                self.host,
                "Видача ліцензії",
                "У замовленні відсутній edition.",
            )
            return

        issued_utc = utc_now_str()

        try:
            self._write_license_file(
                license_uid=license_uid,
                license_rel_path=license_rel_path,
                order_uid=order_uid,
                edition=edition,
                issued_utc=issued_utc,
                customer_email=customer_email,
                fingerprint=fingerprint,
                app_version=app_version,
                payment_ref=payment_ref,
            )
            self._upsert_license_record(
                order_id=order_id,
                license_uid=license_uid,
                edition=edition,
                license_rel_path=license_rel_path,
                issued_utc=issued_utc,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Orders issue license failed: order_id=%s", order_id)
            QMessageBox.warning(
                self.host,
                "Видача ліцензії",
                f"Не вдалося видати ліцензію.\n\n{exc}",
            )
            self.update_nav_state()
            return

        logger.debug(
            "License issued from Orders: order_id=%s, order_uid=%s, "
            "license_uid=%s, path=%s",
            order_id,
            order_uid,
            license_uid,
            license_rel_path,
        )

        if getattr(self.host, "lic", None) is not None:
            self.host.lic.refresh(select_license_uid=license_uid)
        elif getattr(self.host, "model_licenses", None) is not None:
            self.host.model_licenses.select()

        msg = (
            "Ліцензію перевидано успішно." if reissue else "Ліцензію створено успішно."
        )

        QMessageBox.information(
            self.host,
            "Видача ліцензії",
            msg,
        )
        self.update_nav_state()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def first(self) -> None:
        self._nav_select(0)

    def last(self) -> None:
        m = self.model_orders
        if m is None:
            return
        self._nav_select(max(0, m.rowCount() - 1))

    def prev(self) -> None:
        tv = self.host.ui.tvOrders
        row = tv.currentIndex().row()
        self._nav_select(max(0, row - 1))

    def next(self) -> None:
        m = self.model_orders
        if m is None:
            return
        tv = self.host.ui.tvOrders
        row = tv.currentIndex().row()
        self._nav_select(min(m.rowCount() - 1, row + 1))

    def _nav_select(self, row: int) -> None:
        m = self.model_orders
        if m is None or m.rowCount() <= 0:
            return
        row = max(0, min(row, m.rowCount() - 1))
        self.host.ui.tvOrders.selectRow(row)
        self.update_nav_state()

    def update_nav_state(self) -> None:
        m = self.model_orders
        tv = self.host.ui.tvOrders

        has_rows = bool(m is not None and m.rowCount() > 0)
        cur_row = (
            tv.currentIndex().row() if has_rows and tv.currentIndex().isValid() else -1
        )

        self.host.ui.btnOrdFirst.setEnabled(has_rows and cur_row > 0)
        self.host.ui.btnOrdPrev.setEnabled(has_rows and cur_row > 0)
        self.host.ui.btnOrdNext.setEnabled(has_rows and cur_row < (m.rowCount() - 1))
        self.host.ui.btnOrdLast.setEnabled(has_rows and cur_row < (m.rowCount() - 1))

        dirty = self._dirty or self._model_has_dirty() or bool(self._pending_delete_ids)
        self.host.ui.btnOrdSave.setEnabled(dirty)
        self.host.ui.btnOrdCancel.setEnabled(dirty)

        has_customer = bool(self.host.current_customer_id())
        self.host.ui.btnOrdAdd.setEnabled(has_customer)
        self.host.ui.btnOrdDel.setEnabled(has_customer and has_rows)

        current_order_id = self._current_order_id()
        payment_sum = self._payments_sum_for_order(current_order_id or 0)
        btn_issue = getattr(self.host.ui, "btnOrdIssue", None)
        if btn_issue is not None:
            btn_issue.setEnabled(bool(current_order_id) and payment_sum > 0)

        self.host.ui.btnOrdRefresh.setEnabled(True)

        # logger.debug(
        #     "ORD NAV: dirty=%s model_dirty=%s save_enabled=%s",
        #     self._dirty,
        #     self._model_has_dirty() or bool(self._pending_delete_ids),
        #     self.host.ui.btnOrdSave.isEnabled(),
        # )

        self.host.set_nav_active(
            "Ord",
            {
                "First": self.host.ui.btnOrdFirst.isEnabled(),
                "Prev": self.host.ui.btnOrdPrev.isEnabled(),
                "Next": self.host.ui.btnOrdNext.isEnabled(),
                "Last": self.host.ui.btnOrdLast.isEnabled(),
                "Add": self.host.ui.btnOrdAdd.isEnabled(),
                "Del": self.host.ui.btnOrdDel.isEnabled(),
                "Save": self.host.ui.btnOrdSave.isEnabled(),
                "Cancel": self.host.ui.btnOrdCancel.isEnabled(),
                "Refresh": self.host.ui.btnOrdRefresh.isEnabled(),
            },
        )

        self.host.sync_button_states()

    def current_order_id(self) -> int:
        """Повернути id поточного замовлення або 0."""
        tv = self.host.ui.tvOrders
        model = getattr(self.host, "model_orders", None)
        if model is None:
            return 0

        idx = tv.currentIndex()
        if not idx.isValid():
            return 0

        row = idx.row()
        col_id = model.fieldIndex("id")
        if col_id < 0:
            return 0

        value = model.data(model.index(row, col_id))
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _count_by_order_id(self, table_name: str, order_id: int) -> int:
        """Повернути кількість записів у таблиці по order_id."""
        if order_id <= 0:
            return 0

        db = getattr(self.host, "db", None)
        if db is None:
            return 0

        q = QSqlQuery(db)
        q.prepare(f"SELECT count(*) FROM {table_name} WHERE order_id = ?")
        q.addBindValue(order_id)

        if not q.exec():
            logger.error(
                "Count query failed for %s, order_id=%s: %s",
                table_name,
                order_id,
                q.lastError().text(),
            )
            return 0

        if not q.next():
            return 0

        try:
            return int(q.value(0) or 0)
        except (TypeError, ValueError):
            return 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

    @staticmethod
    def _canonical_json_bytes(payload: dict) -> bytes:
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    @staticmethod
    def _generate_license_uid() -> str:
        dt_part = datetime.now(UTC).strftime("%Y%m%d-%H%M")
        rnd_part = secrets.token_hex(2).upper()
        return f"LGE-{dt_part}-{rnd_part}"

    @staticmethod
    def _build_license_rel_path(license_uid: str) -> str:
        return f"licenses/{(license_uid or '').strip()}.lic"

    @staticmethod
    def _confirm_reissue() -> bool:
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Видача ліцензії")
        box.setText("Ліцензія вже існує.\nПеревидати?")
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        box.setDefaultButton(QMessageBox.StandardButton.No)

        btn_yes = box.button(QMessageBox.StandardButton.Yes)
        if btn_yes is not None:
            btn_yes.setText("Так")

        btn_no = box.button(QMessageBox.StandardButton.No)
        if btn_no is not None:
            btn_no.setText("Ні")

        return box.exec() == QMessageBox.StandardButton.Yes

    @staticmethod
    def _load_private_key() -> Ed25519PrivateKey:
        private_key_path = get_private_key_path()
        if not private_key_path.exists():
            raise FileNotFoundError(f"Не знайдено приватний ключ: {private_key_path}")

        password = session_state.ADMIN_PASSWORD
        if not password:
            raise ValueError("Немає пароля сесії. Увійдіть в LGEOffice ще раз.")

        raw = private_key_path.read_bytes()
        private_key = serialization.load_pem_private_key(
            raw,
            password=password.encode("utf-8"),
        )
        if not isinstance(private_key, Ed25519PrivateKey):
            raise TypeError("Приватний ключ не є Ed25519")

        return private_key

    def _write_license_file(
        self,
        *,
        license_uid: str,
        license_rel_path: str,
        order_uid: str,
        edition: str,
        issued_utc: str,
        customer_email: str,
        fingerprint: str,
        app_version: str,
        payment_ref: str,
    ) -> None:
        payload = {
            "app_version": app_version,
            "customer_email": customer_email,
            "edition": edition,
            "fingerprint": fingerprint,
            "issued_utc": issued_utc,
            "license_uid": license_uid,
            "order_id": order_uid,
            "payment_ref": payment_ref,
            "product": "LGE",
        }

        payload_bytes = self._canonical_json_bytes(payload)
        private_key = self._load_private_key()
        signature_bytes = private_key.sign(payload_bytes)

        license_obj = {
            "payload_b64": self._b64url(payload_bytes),
            "signature_b64": self._b64url(signature_bytes),
        }

        licenses_dir = get_licenses_dir()
        licenses_dir.mkdir(parents=True, exist_ok=True)

        rel_path = (license_rel_path or "").replace("\\", "/").strip()
        if rel_path.startswith("licenses/"):
            rel_name = rel_path[len("licenses/") :]  # noqa
        else:
            rel_name = f"{license_uid}.lic"

        license_path = licenses_dir / rel_name
        license_path.write_text(
            json.dumps(license_obj, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _upsert_license_record(
        self,
        *,
        order_id: int,
        license_uid: str,
        edition: str,
        license_rel_path: str,
        issued_utc: str,
    ) -> None:
        query = QSqlQuery(self.host.db)
        query.prepare(
            """
            INSERT INTO licenses (
                order_id,
                license_uid,
                edition,
                license_rel_path,
                issued_utc
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(order_id) DO UPDATE SET
                license_uid = excluded.license_uid,
                edition = excluded.edition,
                license_rel_path = excluded.license_rel_path,
                issued_utc = excluded.issued_utc
            """
        )
        query.addBindValue(order_id)
        query.addBindValue(license_uid)
        query.addBindValue(edition)
        query.addBindValue(license_rel_path)
        query.addBindValue(issued_utc)

        if not query.exec():
            raise RuntimeError(query.lastError().text())

    def _customer_email_for_order(self, order_id: int) -> str:
        if order_id <= 0:
            return ""

        query = QSqlQuery(self.host.db)
        query.prepare(
            """
            SELECT c.email
            FROM orders o
            JOIN customers c ON c.id = o.customer_id
            WHERE o.id = ?
            LIMIT 1
            """
        )
        query.addBindValue(order_id)

        if not query.exec():
            logger.error(
                "Orders customer email query failed: %s",
                query.lastError().text(),
            )
            return ""

        if not query.next():
            return ""

        value = query.value(0)
        return str(value).strip() if value is not None else ""

    def _model_has_dirty(self) -> bool:
        m = self.model_orders
        if m is None:
            return False
        for r in range(m.rowCount()):
            for c in range(m.columnCount()):
                if m.isDirty(m.index(r, c)):
                    return True
        return False

    def _is_delete_only_change(self) -> bool:
        # delete-only = є pending delete, але немає жодних змін в існуючих рядках,
        # і немає нових вставок (у вставлених рядках id ще пустий).
        if not self._pending_delete_ids:
            return False

        m = self.model_orders
        if m is None:
            return False

        col_id = m.fieldIndex("id")
        if col_id < 0:
            return False

        for row in range(m.rowCount()):
            # якщо id пустий -> це insert, значить не delete-only
            v = m.data(m.index(row, col_id), Qt.ItemDataRole.EditRole)
            if v in (None, "", 0):
                return False

            # якщо будь-яке поле dirty -> не delete-only
            for col in range(m.columnCount()):
                if m.isDirty(m.index(row, col)):
                    return False

        return True

    def _row_was_deleted(self, row: int) -> bool:
        m = self.model_orders
        if m is None:
            return False
        order_pk = self._get_int(row, "id")
        if not order_pk:
            return False
        return order_pk in self._pending_delete_ids

    def _confirm(self, text: str) -> bool:
        box = QMessageBox(self.host)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Підтвердження")
        box.setText(text)
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        box.setDefaultButton(QMessageBox.StandardButton.No)

        btn_yes = box.button(QMessageBox.StandardButton.Yes)
        if btn_yes is not None:
            btn_yes.setText("Так")
        btn_no = box.button(QMessageBox.StandardButton.No)
        if btn_no is not None:
            btn_no.setText("Ні")

        return box.exec() == QMessageBox.StandardButton.Yes

    def _set_field(self, row: int, field: str, value) -> None:
        m = self.model_orders
        if m is None:
            return
        col = m.fieldIndex(field)
        if col >= 0:
            m.setData(m.index(row, col), value)

    def _str(self, row: int, field: str) -> str:
        m = self.model_orders
        if m is None:
            return ""
        col = m.fieldIndex(field)
        if col < 0:
            return ""
        v = m.data(m.index(row, col), Qt.ItemDataRole.EditRole)
        return (str(v) if v is not None else "").strip()

    def _focus_field(self, row: int, field: str) -> None:
        m = self.model_orders
        if m is None:
            return
        col = m.fieldIndex(field)
        if col >= 0:
            self._focus_cell(row, col)

    def _focus_cell(self, row: int, col: int) -> None:
        m = self.model_orders
        if m is None:
            return
        tv = self.host.ui.tvOrders
        idx = m.index(row, col)
        tv.setCurrentIndex(idx)
        tv.scrollTo(idx)
        tv.edit(idx)

    def _get_int(self, row: int, field: str) -> int | None:
        s = self._str(row, field)
        try:
            v = int(s)
            return v if v > 0 else None
        except Exception:  # noqa
            return None

    def _req_order_uid(self, row: int) -> bool:
        uid = self._str(row, "order_uid")
        if not uid:
            QMessageBox.warning(
                self.host,
                "Замовлення",
                "order_uid обов’язкове.\n"
                "Формат: LGE-YYYYMMDD-HHMM-XXXX (наприклад LGE-20260227-1900-1234).",
            )
            self._focus_field(row, "order_uid")
            return False

        uid_norm = uid.strip().upper()
        if not _RE_ORDER_UID.fullmatch(uid_norm):
            QMessageBox.warning(
                self.host,
                "Замовлення",
                "Невірний формат order_uid.\n\n"
                "Формат: LGE-YYYYMMDD-HHMM-XXXX (наприклад LGE-20260227-1900-1234).",
            )
            self._focus_field(row, "order_uid")
            return False

        self._set_field(row, "order_uid", uid_norm)
        return True

    def _req_edition(self, row: int) -> bool:
        ed = self._str(row, "edition")
        if not ed:
            QMessageBox.warning(self.host, "Замовлення", "edition обов’язкове.")
            self._focus_field(row, "edition")
            return False

        raw = ed.strip().upper()

        # приймаємо різні варіанти вводу

        # забороняємо "обрубки" типу PRO-, PRO_, PRO+
        # (PRO+ дозволяємо тільки якщо це саме PRO+ або PRO PLUS)
        if raw in {"PRO-", "PRO_", "PRO +"}:
            QMessageBox.warning(
                self.host,
                "Замовлення",
                "Невірне edition.\n\nДозволено: PRO або PRO+.",
            )
            self._focus_field(row, "edition")
            return False
        raw = raw.replace("-", " ").replace("_", " ")
        raw = " ".join(raw.split())  # прибрати зайві пробіли

        if raw in ("PRO",):
            ed_norm = "PRO"
        elif raw in ("PRO PLUS", "PRO+", "PRO +"):
            ed_norm = "PRO+"
        else:
            QMessageBox.warning(
                self.host,
                "Замовлення",
                "Невірне edition.\n\nДозволено: PRO або PRO+.",
            )
            self._focus_field(row, "edition")
            return False

        self._set_field(row, "edition", ed_norm)
        return True

    def _has_license(self, order_id: int) -> bool:
        if self.host.db is None:
            return False
        q = QSqlQuery(self.host.db)
        q.prepare("SELECT 1 FROM licenses WHERE order_id = ? LIMIT 1;")
        q.addBindValue(order_id)
        if not q.exec():
            logger.warning("licenses check failed: %s", q.lastError().text())
            return False
        return q.next()

    def _check_payment_sufficiency(self, order_id: int) -> tuple[bool, float, float]:
        """
        Перевірка достатності оплати.

        Returns:
            (allowed, required_price, paid_total)
        """

        repo = DbRepo(get_office_dir())
        repo.ensure_db()

        customer_id = self.host.current_customer_id()
        fingerprint = self._current_order_field("fingerprint_sha256")
        edition = self._current_order_field("edition")

        edition_db = "PRO_PLUS" if edition == "PRO+" else edition

        required_price = repo.get_required_amount_for_edition(
            customer_id=customer_id,
            fingerprint=fingerprint,
            target_edition=edition_db,
        )
        paid_total = self._payments_sum_for_order(order_id)

        if paid_total < required_price - 1.0:
            return False, required_price, paid_total

        return True, required_price, paid_total

    def _payments_count(self, order_id: int) -> int:
        if self.host.db is None:
            return 0
        q = QSqlQuery(self.host.db)
        q.prepare("SELECT COUNT(*) FROM payments WHERE order_id = ?;")
        q.addBindValue(order_id)
        if not q.exec():
            logger.warning("payments count failed: %s", q.lastError().text())
            return 0
        if q.next():
            try:
                return int(q.value(0))
            except Exception:  # noqa
                return 0
        return 0

    def _existing_license_id(self, order_id: int) -> int | None:
        """Повернути id наявної ліцензії для замовлення або None."""
        if order_id <= 0:
            return None

        query = QSqlQuery(self.host.db)
        query.prepare(
            """
            SELECT id
            FROM licenses
            WHERE order_id = ?
            LIMIT 1
            """
        )
        query.addBindValue(order_id)

        if not query.exec():
            logger.error(
                "Orders existing license query failed: %s",
                query.lastError().text(),
            )
            return None

        if not query.next():
            return None

        value = query.value(0)
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _existing_license_data(
        self, order_id: int
    ) -> tuple[str, str] | tuple[None, None]:
        query = QSqlQuery(self.host.db)
        query.prepare(
            """
            SELECT license_uid, license_rel_path
            FROM licenses
            WHERE order_id = ?
            LIMIT 1
            """
        )
        query.addBindValue(order_id)

        if not query.exec():
            logger.error(
                "Orders ISSUE LICENSE: existing license data query failed: %s",
                query.lastError().text(),
            )
            return None, None

        if not query.next():
            return None, None

        license_uid = str(query.value(0) or "").strip()
        license_rel_path = str(query.value(1) or "").strip()
        return license_uid, license_rel_path

    def _payments_sum_for_order(self, order_id: int) -> float:
        """Повернути суму оплат по замовленню."""
        if order_id <= 0:
            return 0.0

        query = QSqlQuery(self.host.db)
        query.prepare(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM payments
            WHERE order_id = ?
            """
        )
        query.addBindValue(order_id)

        if not query.exec():
            logger.error(
                "Orders payments sum query failed: %s",
                query.lastError().text(),
            )
            return 0.0

        if not query.next():
            return 0.0

        value = query.value(0)
        try:
            return float(value) if value is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _current_order_field(self, field_name: str) -> str:
        """Повернути текстове поле поточного замовлення."""
        model_orders: QSqlTableModel = getattr(self.host, "model_orders", None)
        tv_orders: QTableView = getattr(self.host.ui, "tvOrders", None)

        if model_orders is None or tv_orders is None:
            return ""

        index = tv_orders.currentIndex()
        if not index.isValid():
            return ""

        row = index.row()
        col = model_orders.fieldIndex(field_name)
        if col < 0:
            return ""

        value = model_orders.data(model_orders.index(row, col))
        return str(value).strip() if value is not None else ""

    def _current_selected_id(self) -> int | None:
        m = self.model_orders
        if m is None:
            return None

        tv = self.host.ui.tvOrders
        idx = tv.currentIndex()
        if not idx.isValid():
            return None

        col_id = m.fieldIndex("id")
        if col_id < 0:
            return None

        try:
            v = m.data(m.index(idx.row(), col_id))
            oid = int(v)
            return oid if oid > 0 else None
        except Exception:  # noqa
            return None

    def _current_pending_order_uid(self) -> str:
        m = self.model_orders
        if m is None:
            return ""

        tv = self.host.ui.tvOrders
        idx = tv.currentIndex()
        if not idx.isValid():
            return ""

        col_uid = m.fieldIndex("order_uid")
        if col_uid < 0:
            return ""

        return str(m.data(m.index(idx.row(), col_uid)) or "").strip()

    def _current_order_id(self) -> int | None:
        """Повернути id поточного замовлення або None."""
        model_orders: QSqlTableModel = getattr(self.host, "model_orders", None)
        tv_orders: QTableView = getattr(self.host.ui, "tvOrders", None)

        if model_orders is None or tv_orders is None:
            return None

        index = tv_orders.currentIndex()
        if not index.isValid():
            return None

        row = index.row()
        col_id = model_orders.fieldIndex("id")
        if col_id < 0:
            return None

        value = model_orders.data(model_orders.index(row, col_id))
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _preferred_row_after_delete(self) -> int | None:
        m = self.model_orders
        if m is None:
            return None

        tv = self.host.ui.tvOrders
        idx = tv.currentIndex()
        if not idx.isValid():
            return 0 if m.rowCount() > 0 else None

        row = idx.row()
        return max(0, row)

    @staticmethod
    def _select_row_by_id(tv: QTableView, m: QSqlTableModel, oid: int) -> bool:
        col_id = m.fieldIndex("id")
        if col_id < 0:
            return False

        for row in range(m.rowCount()):
            v = m.data(m.index(row, col_id))
            try:
                if int(v) == int(oid):
                    tv.selectRow(row)
                    tv.scrollTo(m.index(row, 0))
                    tv.setFocus()
                    return True
            except Exception:  # noqa
                continue
        return False

    @staticmethod
    def _select_row_by_order_uid(
        tv: QTableView, m: QSqlTableModel, order_uid: str
    ) -> bool:
        col_uid = m.fieldIndex("order_uid")
        if col_uid < 0:
            return False

        target = (order_uid or "").strip()
        if not target:
            return False

        for row in range(m.rowCount()):
            v = str(m.data(m.index(row, col_uid)) or "").strip()
            if v == target:
                tv.selectRow(row)
                tv.scrollTo(m.index(row, 0))
                tv.setFocus()
                return True
        return False
