# db_grid_window_logic_pay.py
# -*- coding: utf-8 -*-
"""\
PaymentsLogic — логіка таблиці payments (RoadMap39 / Payments).

Master-detail:
orders (id) -> payments.order_id (NULL allowed, FK SET NULL)

У DbGrid показуємо платежі ТІЛЬКИ для поточного order_id.

Ключове:
- paid_utc: формат YYYY-MM-DD HH:MM (UTC).
- Валідація запускається ТІЛЬКИ для рядків на збереження (insert/modify),
  не для чистого видалення.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtSql import QSqlQuery, QSqlTableModel
from PySide6.QtWidgets import (
    QDialog,
    QHeaderView,
    QItemDelegate,
    QLineEdit,
    QMessageBox,
    QTableView,
)

from office.core.pay_duplicate_confirm_dialog import PayDuplicateConfirmDialog
from office.core.payment_add_dialog import PaymentAddDialog


class _AmountLineEditDelegate(QItemDelegate):
    def createEditor(self, parent, option, index):
        ed = QLineEdit(parent)

        ed.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        v = QDoubleValidator(ed)
        v.setNotation(QDoubleValidator.Notation.StandardNotation)
        v.setDecimals(2)
        v.setBottom(0.0)

        ed.setValidator(v)
        return ed


logger = logging.getLogger(__name__)


class PaymentsLogic:
    def __init__(self, host) -> None:
        self.host = host

        self._dirty = False
        self._pending_delete_ids: set[int] = set()

        self.model_payments: QSqlTableModel | None = None

        self._init_payments_model()
        self._configure_payments_view()
        self._bind_dirty_signals()

        self.apply_order_filter(self.host.current_order_id())

    # ------------------------------------------------------------------
    # Model
    # ------------------------------------------------------------------

    def _init_payments_model(self) -> None:
        if self.host.db is None:
            raise RuntimeError("DB is not initialized")

        m = QSqlTableModel(self.host, self.host.db)
        m.setTable("payments")
        m.setEditStrategy(QSqlTableModel.EditStrategy.OnManualSubmit)
        m.select()
        self.host.after_model_select(
            self.host.ui.tvPayments, self.host.model_payments, "payments"
        )

        self.model_payments = m
        self.host.model_payments = m
        self.host.ui.tvPayments.setModel(m)

    # ------------------------------------------------------------------
    # View
    # ------------------------------------------------------------------

    def _configure_payments_view(self) -> None:
        tv = self.host.ui.tvPayments
        tv.setEnabled(True)

        tv.setEditTriggers(QTableView.EditTrigger.DoubleClicked)
        tv.setTabKeyNavigation(True)
        tv.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        tv.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        tv.setAlternatingRowColors(True)

        tv.setSortingEnabled(False)
        tv.horizontalHeader().setStretchLastSection(True)
        tv.verticalHeader().setVisible(False)

        m = self.model_payments
        if m is None:
            return

        self.host.set_widths(
            tv,
            m,
            {
                "id": 60,
                "provider": 90,
                "external_ref": 220,
                "amount": 90,
                "currency": 70,
                "paid_utc": 140,
                "note": 180,
            },
        )

        self.host.set_readonly_id_column(tv, m)

        self.host.set_headers(
            m,
            {
                "id": "№",
                "order_id": "Order ID",
                "provider": "Банк",
                "external_ref": "Код замовлення",
                "amount": "Сума",
                "currency": "Валюта",
                "paid_utc": "Оплачено (UTC)",
                "note": "Примітка",
            },
        )
        # Ширина/resize
        hdr = tv.horizontalHeader()

        col_ref = self.model_payments.fieldIndex("external_ref")
        if col_ref >= 0:
            tv.setColumnWidth(col_ref, 260)  # мінімум
            hdr.setSectionResizeMode(col_ref, QHeaderView.ResizeMode.Stretch)

        col_note = self.model_payments.fieldIndex("note")
        if col_note >= 0:
            tv.setColumnWidth(col_note, 220)
            hdr.setSectionResizeMode(col_note, QHeaderView.ResizeMode.Interactive)

        for fld in ("provider", "amount", "currency", "paid_utc"):
            c = self.model_payments.fieldIndex(fld)
            if c >= 0:
                hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)

        for fld in ("external_ref", "note"):
            c = self.model_payments.fieldIndex(fld)
            if c >= 0:
                hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.Interactive)

        col_amount = self.model_payments.fieldIndex("amount")
        if col_amount >= 0:
            tv.setItemDelegateForColumn(col_amount, _AmountLineEditDelegate(tv))

        # id readonly
        col_id = m.fieldIndex("id")
        if col_id >= 0:
            tv.setItemDelegateForColumn(col_id, self.host.ro_delegate)

        # order_id hidden (master)
        col_order = m.fieldIndex("order_id")
        if col_order >= 0:
            tv.setColumnHidden(col_order, True)

        # paid_utc delegate
        col_paid = m.fieldIndex("paid_utc")
        if col_paid >= 0:
            tv.setItemDelegateForColumn(col_paid, self.host.utc_delegate)

        self.update_nav_state()

    # ------------------------------------------------------------------
    # Dirty tracking
    # ------------------------------------------------------------------

    def _bind_dirty_signals(self) -> None:
        m = self.model_payments
        if m is None:
            return

        m.dataChanged.connect(lambda *_: self._set_dirty(True))
        m.rowsInserted.connect(lambda *_: self._set_dirty(True))
        m.rowsRemoved.connect(lambda *_: self._set_dirty(True))

        sm = self.host.ui.tvPayments.selectionModel()
        if sm is not None:
            sm.currentChanged.connect(lambda *_: self.update_nav_state())

        self.update_nav_state()

    def _set_dirty(self, value: bool) -> None:
        self._dirty = bool(value)
        self.update_nav_state()

    # ------------------------------------------------------------------
    # Filter
    # ------------------------------------------------------------------

    def apply_order_filter(self, order_id: int | None) -> None:
        m = self.model_payments
        if m is None:
            return

        if not order_id:
            m.setFilter("1=0")
        else:
            m.setFilter(f"order_id = {int(order_id)}")

        m.select()
        self.host.after_model_select(
            self.host.ui.tvPayments, self.host.model_payments, "payments"
        )

        tv = self.host.ui.tvPayments
        if m.rowCount() > 0:
            tv.selectRow(0)
        else:
            tv.clearSelection()

        self.update_nav_state()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(self) -> None:
        m = self.model_payments
        if m is None:
            return

        order_id = self.host.current_order_id()
        if not order_id:
            QMessageBox.warning(self.host, "Платежі", "Спочатку виберіть замовлення.")
            return

        order_uid = self._current_order_uid()

        if self._dirty or self._model_has_dirty() or self._pending_delete_ids:
            QMessageBox.warning(
                self.host,
                "Платежі",
                "Є незбережені зміни. Спочатку натисніть «Зберегти» або «Відміна».",
            )
            return

        row = m.rowCount()
        m.insertRow(row)

        self._set_field(row, "order_id", int(order_id))
        self._set_field(row, "external_ref", order_uid)
        self._set_field(row, "provider", "a-банк")
        self._set_field(row, "currency", "USD")
        self._set_field(row, "amount", 0)
        self._set_field(row, "paid_utc", datetime.now(UTC).strftime("%Y-%m-%d %H:%M"))

        tv = self.host.ui.tvPayments
        tv.selectRow(row)

        self._focus_field(row, "external_ref")

        self._set_dirty(True)

    def delete(self) -> None:
        m = self.model_payments
        if m is None:
            return

        tv = self.host.ui.tvPayments
        idx = tv.currentIndex()
        if not idx.isValid():
            return

        if not self.host.confirm_delete("Платіж"):
            return

        row = idx.row()

        pay_id = self._get_int(row, "id")
        if pay_id:
            self._pending_delete_ids.add(pay_id)

        m.removeRow(row)
        self._set_dirty(True)

    def save(self) -> bool:
        m = self.model_payments
        if m is None:
            return True

        tv = self.host.ui.tvPayments
        tv.clearFocus()

        current_id = self._current_selected_id()
        pending_ref = self._current_pending_external_ref()
        row_hint = self._preferred_row_after_delete()

        try:
            # paid_utc: normalize only dirty cells
            self.host.normalize_model_utc_field(m, "paid_utc")

            # validate only rows to be saved (insert/modify)
            for row in range(m.rowCount()):
                if self._row_was_deleted(row):
                    continue

                if not self._row_needs_validation(row):
                    continue

                if not self._req_paid_utc(row):
                    return False
                if not self._req_order_ref(row):
                    return False
                if not self._req_amount(row):
                    return False
                self._normalize_currency(row)
                self._normalize_provider(row)

        except ValueError as e:
            QMessageBox.warning(self.host, "Платежі", str(e))
            return False

        ok = m.submitAll()

        if ok:
            self._dirty = False
            self._pending_delete_ids.clear()

            last_id = None
            db = self.host.db
            if db is not None:
                from PySide6.QtSql import QSqlQuery

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
                select_external_ref=pending_ref,
                select_row_hint=row_hint,
            )
            return True

        err_text = m.lastError().text()
        logger.error("Payments SAVE failed: %s", err_text)
        QMessageBox.warning(
            self.host,
            "Платежі",
            "Не вдалося зберегти зміни.\n\n" + err_text,
        )
        return False

    def cancel(self) -> None:
        m = self.model_payments
        if m is None:
            return

        m.revertAll()
        self._dirty = False
        self._pending_delete_ids.clear()
        self.update_nav_state()

    def refresh(
        self,
        select_id: int | None = None,
        select_external_ref: str = "",
        select_row_hint: int | None = None,
    ) -> None:
        self.apply_order_filter(self.host.current_order_id())

        m = self.model_payments
        if m is None:
            return

        tv = self.host.ui.tvPayments

        selected = False

        if select_id:
            selected = self._select_row_by_id(tv, m, select_id)

        if (not selected) and select_external_ref:
            selected = self._select_row_by_external_ref(tv, m, select_external_ref)

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

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def first(self) -> None:
        self._nav_select(0)

    def last(self) -> None:
        m = self.model_payments
        if m is None:
            return
        self._nav_select(max(0, m.rowCount() - 1))

    def prev(self) -> None:
        tv = self.host.ui.tvPayments
        row = tv.currentIndex().row()
        self._nav_select(max(0, row - 1))

    def next(self) -> None:
        m = self.model_payments
        if m is None:
            return
        tv = self.host.ui.tvPayments
        row = tv.currentIndex().row()
        self._nav_select(min(m.rowCount() - 1, row + 1))

    def _nav_select(self, row: int) -> None:
        m = self.model_payments
        if m is None or m.rowCount() <= 0:
            return
        row = max(0, min(row, m.rowCount() - 1))
        self.host.ui.tvPayments.selectRow(row)
        self.update_nav_state()

    def update_nav_state(self) -> None:
        m = self.model_payments
        tv = self.host.ui.tvPayments

        has_rows = bool(m is not None and m.rowCount() > 0)
        cur_row = (
            tv.currentIndex().row() if has_rows and tv.currentIndex().isValid() else -1
        )

        self.host.ui.btnPayFirst.setEnabled(has_rows and cur_row > 0)
        self.host.ui.btnPayPrev.setEnabled(has_rows and cur_row > 0)
        self.host.ui.btnPayNext.setEnabled(has_rows and cur_row < (m.rowCount() - 1))
        self.host.ui.btnPayLast.setEnabled(has_rows and cur_row < (m.rowCount() - 1))

        dirty = self._dirty or self._model_has_dirty() or bool(self._pending_delete_ids)
        self.host.ui.btnPaySave.setEnabled(dirty)
        self.host.ui.btnPayCancel.setEnabled(dirty)

        has_order = bool(self.host.current_order_id())
        self.host.ui.btnPayAdd.setEnabled(has_order and not dirty)
        self.host.ui.btnPayDel.setEnabled(has_rows)
        self.host.ui.btnPayRefresh.setEnabled(True)

        self.host.set_nav_active(
            "Pay",
            {
                "First": self.host.ui.btnPayFirst.isEnabled(),
                "Prev": self.host.ui.btnPayPrev.isEnabled(),
                "Next": self.host.ui.btnPayNext.isEnabled(),
                "Last": self.host.ui.btnPayLast.isEnabled(),
                "Add": self.host.ui.btnPayAdd.isEnabled(),
                "Del": self.host.ui.btnPayDel.isEnabled(),
                "Save": self.host.ui.btnPaySave.isEnabled(),
                "Cancel": self.host.ui.btnPayCancel.isEnabled(),
                "Refresh": self.host.ui.btnPayRefresh.isEnabled(),
            },
        )

        self.host.sync_button_states()

        btn_link = getattr(self.host.ui, "btnPayLinkToOrder", None)
        if btn_link is not None:
            chk_unlinked = getattr(self.host.ui, "chkPayUnlinked", None)
            show_unlinked = bool(chk_unlinked is not None and chk_unlinked.isChecked())
            has_order = bool(self.host.current_order_id())
            has_unlinked_payment = self._selected_payment_is_unlinked()
            dirty = (
                self._dirty or self._model_has_dirty() or bool(self._pending_delete_ids)
            )

            btn_link.setEnabled(
                show_unlinked and has_order and has_unlinked_payment and not dirty
            )

        if getattr(self.host, "ord", None) is not None:
            self.host.ord.update_nav_state()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _model_has_dirty(self) -> bool:
        m = self.model_payments
        if m is None:
            return False
        for row in range(m.rowCount()):
            for col in range(m.columnCount()):
                if m.isDirty(m.index(row, col)):
                    return True
        return False

    def _row_was_deleted(self, row: int) -> bool:
        pay_pk = self._get_int(row, "id")
        if not pay_pk:
            return False
        return pay_pk in self._pending_delete_ids

    def _row_needs_validation(self, row: int) -> bool:
        m = self.model_payments
        if m is None:
            return False
        for col in range(m.columnCount()):
            if m.isDirty(m.index(row, col)):
                return True
        return False

    def _str(self, row: int, field: str) -> str:
        m = self.model_payments
        if m is None:
            return ""
        col = m.fieldIndex(field)
        if col < 0:
            return ""
        v = m.data(m.index(row, col), Qt.ItemDataRole.EditRole)
        return str(v) if v is not None else ""

    def _get_int(self, row: int, field: str) -> int | None:
        s = self._str(row, field).strip()
        if not s:
            return None
        try:
            v = int(s)
            return v if v > 0 else None
        except Exception:  # noqa
            return None

    def _set_field(self, row: int, field: str, value) -> None:
        m = self.model_payments
        if m is None:
            return
        col = m.fieldIndex(field)
        if col >= 0:
            m.setData(m.index(row, col), value)

    def _focus_field(self, row: int, field: str) -> None:
        m = self.model_payments
        if m is None:
            return
        tv = self.host.ui.tvPayments
        col = m.fieldIndex(field)
        if col < 0:
            return
        idx = m.index(row, col)
        tv.setCurrentIndex(idx)
        tv.scrollTo(idx)
        tv.edit(idx)

    def _req_paid_utc(self, row: int) -> bool:
        s = self._str(row, "paid_utc").strip()
        if not s:
            QMessageBox.warning(self.host, "Платежі", "paid_utc — обов’язкове поле.")
            self._focus_field(row, "paid_utc")
            return False
        return True

    def _req_amount(self, row: int) -> bool:
        raw = self._str(row, "amount").strip().replace(",", ".")
        if not raw:
            raw = "0"
        try:
            v = float(raw)
        except Exception:  # noqa
            QMessageBox.warning(self.host, "Платежі", "Невірна сума (amount).")
            self._focus_field(row, "amount")
            return False

        if v <= 0:
            QMessageBox.warning(self.host, "Платежі", "Сума (amount) має бути > 0.")
            self._focus_field(row, "amount")
            return False

        self._set_field(row, "amount", v)
        return True

    def _normalize_currency(self, row: int) -> None:
        cur = self._str(row, "currency").strip().upper()
        if not cur:
            cur = "USD"
        if len(cur) > 8:
            cur = cur[:8]
        self._set_field(row, "currency", cur)

    def _normalize_provider(self, row: int) -> None:
        p = self._str(row, "provider").strip().lower()
        if not p:
            p = "a-банк"
        if len(p) > 32:
            p = p[:32]
        self._set_field(row, "provider", p)

    def _current_order_uid(self) -> str:
        m_ord = getattr(self.host, "model_orders", None)
        if m_ord is None:
            return ""

        tv_ord = self.host.ui.tvOrders
        idx = tv_ord.currentIndex()
        if not idx.isValid():
            return ""

        col_uid = m_ord.fieldIndex("order_uid")
        if col_uid < 0:
            return ""

        return str(m_ord.data(m_ord.index(idx.row(), col_uid)) or "").strip()

    def _req_order_ref(self, row: int) -> bool:
        order_id = self._get_int(row, "order_id")
        if not order_id:
            QMessageBox.warning(self.host, "Платежі", "Потрібно вибрати замовлення.")
            self._focus_field(row, "external_ref")
            return False

        ext = self._str(row, "external_ref").strip()
        if not ext:
            QMessageBox.warning(
                self.host,
                "Платежі",
                "Код замовлення — обов’язкове поле.",
            )
            self._focus_field(row, "external_ref")
            return False

        return True

    def _current_selected_id(self) -> int | None:
        m = self.model_payments
        if m is None:
            return None

        tv = self.host.ui.tvPayments
        idx = tv.currentIndex()
        if not idx.isValid():
            return None

        col_id = m.fieldIndex("id")
        if col_id < 0:
            return None

        try:
            v = m.data(m.index(idx.row(), col_id))
            pid = int(v)
            return pid if pid > 0 else None
        except Exception:  # noqa
            return None

    def _current_pending_external_ref(self) -> str:
        m = self.model_payments
        if m is None:
            return ""

        tv = self.host.ui.tvPayments
        idx = tv.currentIndex()
        if not idx.isValid():
            return ""

        col_ref = m.fieldIndex("external_ref")
        if col_ref < 0:
            return ""

        return str(m.data(m.index(idx.row(), col_ref)) or "").strip()

    def _preferred_row_after_delete(self) -> int | None:
        m = self.model_payments
        if m is None:
            return None

        tv = self.host.ui.tvPayments
        idx = tv.currentIndex()
        if not idx.isValid():
            return 0 if m.rowCount() > 0 else None

        return max(0, idx.row())

    @staticmethod
    def _select_row_by_id(tv: QTableView, m: QSqlTableModel, pid: int) -> bool:
        col_id = m.fieldIndex("id")
        if col_id < 0:
            return False

        for row in range(m.rowCount()):
            v = m.data(m.index(row, col_id))
            try:
                if int(v) == int(pid):
                    tv.selectRow(row)
                    tv.scrollTo(m.index(row, 0))
                    tv.setFocus()
                    return True
            except Exception:  # noqa
                continue
        return False

    @staticmethod
    def _select_row_by_external_ref(
        tv: QTableView, m: QSqlTableModel, external_ref: str
    ) -> bool:
        col_ref = m.fieldIndex("external_ref")
        if col_ref < 0:
            return False

        target = (external_ref or "").strip()
        if not target:
            return False

        for row in range(m.rowCount()):
            v = str(m.data(m.index(row, col_ref)) or "").strip()
            if v == target:
                tv.selectRow(row)
                tv.scrollTo(m.index(row, 0))
                tv.setFocus()
                return True
        return False

    # ---------------------------------------------------------------
    # ---------- Підключення payment_add_dialog.ui ------------------
    # ---------------------------------------------------------------
    def _current_payment_id(self) -> int | None:
        """Повернути id поточного платежу або None."""
        model_payments: QSqlTableModel = getattr(self.host, "model_payments", None)
        tv_payments: QTableView = getattr(self.host.ui, "tvPayments", None)

        if model_payments is None or tv_payments is None:
            return None

        index = tv_payments.currentIndex()
        if not index.isValid():
            return None

        row = index.row()
        col_id = model_payments.fieldIndex("id")
        if col_id < 0:
            return None

        value = model_payments.data(model_payments.index(row, col_id))
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _selected_payment_is_unlinked(self) -> bool:
        """True, якщо вибраний платіж має order_id IS NULL."""
        model_payments: QSqlTableModel = getattr(self.host, "model_payments", None)
        tv_payments: QTableView = getattr(self.host.ui, "tvPayments", None)

        if model_payments is None or tv_payments is None:
            return False

        index = tv_payments.currentIndex()
        if not index.isValid():
            return False

        row = index.row()
        col_order_id = model_payments.fieldIndex("order_id")
        if col_order_id < 0:
            return False

        value = model_payments.data(model_payments.index(row, col_order_id))
        return value in (None, "", 0, "0")

    def _current_order_id(self) -> int | None:
        """Повернути id поточного order або None."""
        model_orders: QSqlTableModel = getattr(self.host, "model_orders", None)
        tv_orders: QTableView = getattr(self.host.ui, "tvOrders", None)

        if model_orders is None or tv_orders is None:
            return None

        index: QModelIndex = tv_orders.currentIndex()
        if not index.isValid():
            return None

        row = index.row()
        id_col = model_orders.fieldIndex("id")
        if id_col < 0:
            return None

        value = model_orders.data(model_orders.index(row, id_col))
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _find_payment_duplicate(
        self,
        *,
        order_id: int | None,
        provider: str,
        external_ref: str,
        amount_usd: Decimal,
    ) -> dict | None:
        """
        Знайти дубль платежу і повернути його дані або None.

        Логіка:
        - якщо order_id є: шукаємо по order_id, provider, external_ref, amount, paid_utc
        - якщо order_id нема: шукаємо серед order_id IS NULL
        """
        db = self.host.db
        query = QSqlQuery(db)

        amount_str = f"{amount_usd:.2f}"

        if order_id is None:
            sql = """
                SELECT id, order_id, provider, external_ref, amount, currency
                        FROM payments
                        WHERE order_id IS NULL
                          AND provider = ?
                          AND external_ref = ?
                          AND ROUND(amount, 2) = ROUND(CAST(? AS REAL), 2)
                        LIMIT 1
            """
            query.prepare(sql)
            query.addBindValue(provider)
            query.addBindValue(external_ref)
            query.addBindValue(amount_str)
        else:
            sql = """
                SELECT id, order_id, provider, external_ref, amount, currency
                        FROM payments
                        WHERE order_id = ?
                          AND provider = ?
                          AND external_ref = ?
                          AND ROUND(amount, 2) = ROUND(CAST(? AS REAL), 2)
                        LIMIT 1
            """
            query.prepare(sql)
            query.addBindValue(order_id)
            query.addBindValue(provider)
            query.addBindValue(external_ref)
            query.addBindValue(amount_str)

        if not query.exec():
            err = query.lastError().text()
            logger.error("Payments duplicate lookup failed: %s", err)
            QMessageBox.warning(
                self.host,
                "Платежі",
                f"Не вдалося перевірити дубль платежу.\n\n{err}",
            )
            return {"error": err}

        if not query.next():
            return None

        return {
            "id": query.value(0),
            "order_id": query.value(1),
            "provider": query.value(2),
            "external_ref": query.value(3),
            "amount": query.value(4),
            "currency": query.value(5),
        }

    def _insert_payment(
        self,
        *,
        order_id: int | None,
        provider: str,
        external_ref: str,
        amount_usd: Decimal,
        paid_utc: str,
        note: str,
    ) -> int | None:
        """Вставити платіж і повернути new payment id."""
        db = self.host.db
        query = QSqlQuery(db)

        sql = """
            INSERT INTO payments (
                order_id,
                provider,
                external_ref,
                amount,
                currency,
                paid_utc,
                note
            )
            VALUES (?, ?, ?, ?, 'USD', ?, ?)
        """
        query.prepare(sql)

        if order_id is None:
            query.addBindValue(None)
        else:
            query.addBindValue(order_id)

        query.addBindValue(provider)
        query.addBindValue(external_ref)
        query.addBindValue(float(amount_usd))
        query.addBindValue(paid_utc)
        query.addBindValue(note)

        if not query.exec():
            err = query.lastError().text()
            logging.getLogger(__name__).error("Payments INSERT failed: %s", err)
            QMessageBox.warning(
                self.host,
                "Платежі",
                f"Не вдалося зберегти платіж.\n\n{err}",
            )
            return None

        value = query.lastInsertId()
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _select_payment_row_by_id(self, payment_id: int) -> None:
        """Після refresh вибрати рядок платежу по id."""
        model_payments: QSqlTableModel = getattr(self.host, "model_payments", None)
        tv_payments: QTableView = getattr(self.host.ui, "tvPayments", None)

        if model_payments is None or tv_payments is None:
            return

        id_col = model_payments.fieldIndex("id")
        if id_col < 0:
            return

        for row in range(model_payments.rowCount()):
            value = model_payments.data(model_payments.index(row, id_col))
            try:
                if int(value) == payment_id:
                    tv_payments.selectRow(row)
                    tv_payments.setCurrentIndex(model_payments.index(row, 0))
                    return
            except (TypeError, ValueError):
                continue

    def _on_pay_add_dialog(self) -> None:
        """Відкрити діалог додавання платежу та вставити запис у payments."""
        order_id = self._current_order_id()
        order_uid = self._current_order_uid()

        dlg = PaymentAddDialog(
            self.host,
            order_id=order_id,
            order_uid=order_uid,
            external_ref=order_uid,
        )

        if dlg.exec() != dlg.DialogCode.Accepted:
            return

        data = dlg.result_data
        if data is None:
            QMessageBox.warning(
                self.host,
                "Платежі",
                "Діалог не повернув дані платежу.",
            )
            return

        duplicate = self._find_payment_duplicate(
            order_id=data.order_id,
            provider=data.provider,
            external_ref=data.external_ref,
            amount_usd=data.amount_usd,
        )

        if duplicate:
            if duplicate.get("error"):
                return

            dlg = PayDuplicateConfirmDialog(duplicate, self.host)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

        payment_id = self._insert_payment(
            order_id=data.order_id,
            provider=data.provider,
            external_ref=data.external_ref,
            amount_usd=data.amount_usd,
            paid_utc=data.paid_utc,
            note=data.note,
        )
        if payment_id is None:
            return

        model_payments: QSqlTableModel = getattr(self.host, "model_payments", None)
        if model_payments is not None:
            model_payments.select()

        self._select_payment_row_by_id(payment_id)

    def open_add_dialog(self) -> None:
        """Публічний вхід для відкриття діалогу додавання платежу."""
        self._on_pay_add_dialog()

    def link_selected_payment_to_order(self) -> None:
        """Прив'язати вибраний неприв'язаний платіж до поточного замовлення."""
        payment_id = self._current_payment_id()
        order_id = self.host.current_order_id()

        if payment_id is None or order_id is None:
            return

        if not self._selected_payment_is_unlinked():
            return

        chk_unlinked = getattr(self.host.ui, "chkPayUnlinked", None)
        if chk_unlinked is None or not chk_unlinked.isChecked():
            return

        db = self.host.db
        query = QSqlQuery(db)
        query.prepare(
            """
            UPDATE payments
            SET order_id = ?
            WHERE id = ?
            """
        )
        query.addBindValue(order_id)
        query.addBindValue(payment_id)

        if not query.exec():
            err = query.lastError().text()
            logger.error("Payments link to order failed: %s", err)
            QMessageBox.warning(
                self.host,
                "Платежі",
                f"Не вдалося прив'язати платіж до замовлення.\n\n{err}",
            )
            return

        if chk_unlinked is not None:
            chk_unlinked.blockSignals(True)
            chk_unlinked.setChecked(False)
            chk_unlinked.blockSignals(False)

        model_payments: QSqlTableModel = getattr(self.host, "model_payments", None)
        if model_payments is not None:
            model_payments.setFilter(f"order_id = {order_id}")
            model_payments.select()

        tv_payments = getattr(self.host.ui, "tvPayments", None)
        if tv_payments is not None and model_payments is not None:
            id_col = model_payments.fieldIndex("id")
            if id_col >= 0:
                for row in range(model_payments.rowCount()):
                    value = model_payments.data(model_payments.index(row, id_col))
                    try:
                        if int(value) == payment_id:
                            tv_payments.selectRow(row)
                            tv_payments.setCurrentIndex(model_payments.index(row, 0))
                            break
                    except (TypeError, ValueError):
                        continue

        self.update_nav_state()

    def on_unlinked_toggled(self, checked: bool) -> None:
        """Перемкнути фільтр Payments: поточне замовлення / неприв'язані платежі."""
        model_payments: QSqlTableModel = getattr(self.host, "model_payments", None)
        if model_payments is None:
            return

        if checked:
            model_payments.setFilter("order_id IS NULL")
        else:
            order_id = self.host.current_order_id()
            show_unlinked = (
                hasattr(self.host.ui, "chkPayUnlinked")
                and self.host.ui.chkPayUnlinked.isChecked()
            )

            if show_unlinked:
                self.model_payments.setFilter("order_id IS NULL")
            else:
                if order_id:
                    self.model_payments.setFilter(f"order_id = {order_id}")
                else:
                    self.model_payments.setFilter("1=0")

        model_payments.select()

        tv_payments = getattr(self.host.ui, "tvPayments", None)
        if tv_payments is not None and model_payments.rowCount() > 0:
            tv_payments.selectRow(0)

        self.update_nav_state()
