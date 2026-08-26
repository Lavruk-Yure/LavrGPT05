# db_grid_window_logic_cust.py
# -*- coding: utf-8 -*-
"""
CustomersLogic — логіка таблиці customers (CUST ONLY / RoadMap35).
"""

from __future__ import annotations

import logging
import re

from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtSql import QSqlError, QSqlQuery, QSqlTableModel
from PySide6.QtWidgets import QMessageBox, QTableView

from office.core.datetime_utils import utc_now_str

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DATE_HM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}$")
_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class CustomersLogic:
    def __init__(self, host) -> None:
        self.host = host
        logger.debug("CustomersLogic: init host=%s", type(self.host).__name__)
        self._dirty = False
        self._filter_active = False

        m = getattr(self.host, "model_customers", None)
        if m is not None:
            m.dataChanged.connect(self._on_dirty)
            m.rowsInserted.connect(self._on_dirty)
            m.rowsRemoved.connect(self._on_dirty)

    def add(self) -> None:
        m = getattr(self.host, "model_customers", None)
        if m is None:
            return

        tv = self.host.ui.tvCustomers

        row = m.rowCount()
        ok = m.insertRow(row)

        logger.debug("CustomersLogic.add(): insertRow(%s) -> %s", row, ok)

        if not ok:
            err = m.lastError().text()
            logger.error("Customers ADD failed: %s", err)
            return

        col_id = m.fieldIndex("id")
        if col_id >= 0:
            idx_id = m.index(row, col_id)
            m.setData(idx_id, None)

        tv.selectRow(row)

        col_email = m.fieldIndex("email")
        if col_email >= 0:
            idx_email = m.index(row, col_email)
            tv.setCurrentIndex(idx_email)
            tv.scrollTo(idx_email)
            tv.edit(idx_email)

        self._dirty = True
        self.update_nav_state()

    def _current_source_row(self) -> int:
        tv = self.host.ui.tvCustomers
        idx = tv.currentIndex()
        if not idx.isValid():
            return -1

        vm = tv.model()
        if isinstance(vm, QSortFilterProxyModel):
            idx = vm.mapToSource(idx)
        return idx.row()

    def delete(self) -> None:
        m = getattr(self.host, "model_customers", None)
        tv = self.host.ui.tvCustomers
        if m is None:
            return

        idx = tv.currentIndex()
        if not idx.isValid():
            return

        if not self.host.confirm_delete("Клієнта"):
            return

        row = idx.row()
        if not m.removeRow(row):
            logger.error("DEL: removeRow failed: %s", m.lastError().text())
            return

        rows = m.rowCount()
        if rows > 0:
            tv.selectRow(min(row, rows - 1))
        else:
            tv.clearSelection()

        self._dirty = True
        self.update_nav_state()

    def save(self) -> None:
        m = getattr(self.host, "model_customers", None)
        if m is None:
            return
        tv = self.host.ui.tvCustomers

        tv.clearFocus()
        tv.setSortingEnabled(False)

        col_email = m.fieldIndex("email")
        if col_email >= 0:
            for r in range(m.rowCount()):
                val = m.data(m.index(r, col_email))
                if not self._is_valid_email(val):
                    tv = self.host.ui.tvCustomers
                    idx = m.index(r, col_email)
                    tv.setCurrentIndex(idx)
                    tv.scrollTo(idx)
                    tv.setFocus()
                    tv.edit(idx)
                    QMessageBox.warning(self.host, "Клієнти", "Невірний Email.")
                    return

        col_created = m.fieldIndex("created_utc")
        if col_created >= 0:
            for r in range(m.rowCount()):
                idx_created = m.index(r, col_created)
                val = m.data(idx_created, Qt.ItemDataRole.EditRole)

                if val in (None, ""):
                    m.setData(idx_created, self._now_utc_str())
                else:
                    m.setData(idx_created, self._normalize_date(val))

        # AUTOINCREMENT fix:
        # QSqlTableModel інколи тримає id=0 для нового рядка і намагається вставити 0.

        col_id = m.fieldIndex("id")
        if col_id >= 0:
            for row in range(m.rowCount()):
                idx_id = m.index(row, col_id)
                v = m.data(idx_id, Qt.ItemDataRole.EditRole)

                if v in (None, "", 0, "0"):
                    m.setData(idx_id, None)

        current_id = self.host.current_customer_id()

        pending_email = ""
        if col_email >= 0:
            idx = tv.currentIndex()
            if idx.isValid():
                try:
                    pending_email = str(
                        m.data(m.index(idx.row(), col_email), Qt.ItemDataRole.EditRole)
                        or ""
                    ).strip()
                except Exception:  # noqa
                    pending_email = ""

        ok = m.submitAll()

        if not ok:
            err_text = m.lastError().text()
            logger.error("Customers SAVE failed: %s", err_text)

            if "FOREIGN KEY constraint failed" in err_text:
                QMessageBox.warning(
                    self.host,
                    "Клієнти",
                    "Неможливо видалити клієнта.\n\n"
                    "Існують пов’язані замовлення.\n"
                    "Спочатку видаліть замовлення.",
                )
            elif "UNIQUE constraint failed: customers.email" in err_text:
                QMessageBox.warning(
                    self.host,
                    "Клієнти",
                    "Такий Email уже існує.\n\nВкажіть інший Email.",
                )
            else:
                QMessageBox.warning(
                    self.host,
                    "Клієнти",
                    "Не вдалося зберегти зміни.\n\n" + err_text,
                )

            m.revertAll()
            m.select()
            self._dirty = False

            self._sorting_restore()

            self.update_nav_state()
            return

        # SUCCESS
        self._dirty = False

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

        m.select()

        col_id = m.fieldIndex("id")
        if col_id >= 0:
            tv.sortByColumn(col_id, Qt.SortOrder.AscendingOrder)

        self._sorting_restore()
        tv.horizontalHeader().setSortIndicatorShown(True)

        selected = False
        if last_id:
            selected = self._select_row_by_id(tv, m, last_id)

        if (not selected) and pending_email:
            selected = self._select_row_by_email(tv, m, pending_email)

        if (not selected) and current_id:
            selected = self._select_row_by_id(tv, m, current_id)

        if (not selected) and m.rowCount() > 0:
            tv.selectRow(0)
        elif not selected:
            tv.clearSelection()

        self.update_nav_state()

    @staticmethod
    def _now_utc_str() -> str:

        return utc_now_str()

    @staticmethod
    def _select_row_by_id(tv: QTableView, m: QSqlTableModel, cid: int) -> bool:
        col_id = m.fieldIndex("id")
        if col_id < 0:
            return False

        for row in range(m.rowCount()):
            v = m.data(m.index(row, col_id))
            try:
                if int(v) == int(cid):
                    tv.selectRow(row)
                    tv.scrollTo(m.index(row, 0))
                    tv.setFocus()
                    return True
            except Exception:  # noqa
                continue
        return False

    def select_row_by_email(self, email: str) -> None:
        """Виділити рядок customers по email."""
        m_cust = getattr(self.host, "model_customers", None)
        tv = self.host.ui.tvCustomers
        if m_cust is None:
            return

        email_norm = (email or "").strip().lower()
        if not email_norm:
            return

        col_email = m_cust.fieldIndex("email")
        if col_email < 0:
            return

        for row in range(m_cust.rowCount()):
            value = m_cust.data(m_cust.index(row, col_email))
            if str(value or "").strip().lower() == email_norm:
                tv.clearSelection()
                tv.selectRow(row)
                tv.setCurrentIndex(m_cust.index(row, 0))
                tv.scrollTo(m_cust.index(row, 0))
                return

    @staticmethod
    def _select_row_by_email(tv: QTableView, m: QSqlTableModel, email: str) -> bool:
        col_email = m.fieldIndex("email")
        if col_email < 0:
            return False

        target = (email or "").strip().lower()
        if not target:
            return False

        for row in range(m.rowCount()):
            v = m.data(m.index(row, col_email))
            if (str(v or "").strip().lower()) == target:
                tv.selectRow(row)
                tv.scrollTo(m.index(row, 0))
                tv.setFocus()
                return True
        return False

    def cancel(self) -> None:
        m = getattr(self.host, "model_customers", None)
        if m is None:
            return

        tv = self.host.ui.tvCustomers
        tv.clearFocus()

        m.revertAll()
        self._dirty = False

        self.refresh()

        self._sorting_restore()

        self.update_nav_state()

    def refresh(self) -> None:
        m = getattr(self.host, "model_customers", None)
        tv = self.host.ui.tvCustomers
        if m is None:
            return

        # 1) запам'ятати поточний id (через source)
        col_id = m.fieldIndex("id")
        cur_id = None

        if col_id >= 0:
            view_idx = tv.currentIndex()
            if view_idx.isValid():
                src_idx = self._map_to_source(tv, view_idx)
                if src_idx.isValid():
                    cur_id = m.data(m.index(src_idx.row(), col_id))

        # 2) select
        m.select()

        self.host.after_model_select(
            self.host.ui.tvCustomers,
            self.host.model_customers,
            "customers",
        )

        # 3) відновити вибір по id
        if col_id >= 0 and cur_id is not None:
            target_row = -1
            for r in range(m.rowCount()):
                if m.data(m.index(r, col_id)) == cur_id:
                    target_row = r
                    break

            if target_row >= 0:
                src_pick = m.index(target_row, 0)
                view_pick = self._map_from_source(tv, src_pick)
                tv.setCurrentIndex(view_pick)
                tv.selectRow(view_pick.row())
                return

        # fallback
        if m.rowCount() > 0:
            tv.selectRow(0)

    # ---------------- NAV ----------------

    def update_nav_state(self) -> None:
        tv = self.host.ui.tvCustomers
        m = getattr(self.host, "model_customers", None)

        if m is None:
            self.host.set_nav_active(
                "Cust",
                {
                    "First": False,
                    "Prev": False,
                    "Next": False,
                    "Last": False,
                    "Add": True,
                    "Del": False,
                    "Save": False,
                    "Cancel": False,
                    "Refresh": True,
                },
            )
            return

        rows = m.rowCount()
        has_rows = rows > 0
        idx = tv.currentIndex()
        has_sel = idx.isValid()
        row = idx.row() if has_sel else -1

        active = {
            "First": has_rows and row > 0,
            "Prev": has_rows and row > 0,
            "Next": has_rows and 0 <= row < rows - 1,
            "Last": has_rows and 0 <= row < rows - 1,
            "Add": True,
            "Del": has_sel,
            "Save": self._dirty,
            "Cancel": self._dirty,
            "Refresh": True,
        }

        self.host.set_nav_active("Cust", active)

        btn = getattr(self.host.ui, "btnCustOrderRequest", None)
        if btn is not None:
            btn.setEnabled(not self._dirty)
            self.host.set_button_state(btn, btn.isEnabled())

    def first(self) -> None:
        m = getattr(self.host, "model_customers", None)
        if m is None or m.rowCount() <= 0:
            return
        self.host.ui.tvCustomers.selectRow(0)
        self.update_nav_state()

    def last(self) -> None:
        m = getattr(self.host, "model_customers", None)
        if m is None:
            return
        last_row = m.rowCount() - 1
        if last_row < 0:
            return
        self.host.ui.tvCustomers.selectRow(last_row)
        self.update_nav_state()

    def prev(self) -> None:
        m = getattr(self.host, "model_customers", None)
        if m is None or m.rowCount() <= 0:
            return
        tv = self.host.ui.tvCustomers
        cur = tv.currentIndex()
        row = cur.row() if cur.isValid() else 0
        row = max(0, row - 1)
        tv.selectRow(row)
        self.update_nav_state()

    def next(self) -> None:
        m = getattr(self.host, "model_customers", None)
        if m is None:
            return
        rc = m.rowCount()
        if rc <= 0:
            return
        tv = self.host.ui.tvCustomers
        cur = tv.currentIndex()
        row = cur.row() if cur.isValid() else 0
        row = min(rc - 1, row + 1)
        tv.selectRow(row)
        self.update_nav_state()

    # ---------------- FILTERS ----------------
    def filter_action(self) -> None:
        if self._filter_active:
            self.filter_reset()
        else:
            self.filter_apply()

    def filter_apply(self) -> None:
        m = getattr(self.host, "model_customers", None)
        if m is None:
            return

        email_raw = self.host.ui.editCustFilterEmail.text()
        name_raw = self.host.ui.editCustFilterName.text()
        created_idx = self.host.ui.comboCustFilterCreated.currentIndex()

        cond: list[str] = []

        email = self.host.sql_like(email_raw)
        if email:
            cond.append(f"ifnull(email,'') LIKE '%{email}%' COLLATE NOCASE")

        name = self.host.sql_like(name_raw)
        if name:
            cond.append(f"ifnull(name,'') LIKE '%{name}%' COLLATE NOCASE")

        created_expr = "replace(substr(created_utc, 1, 19), 'T', ' ')"
        if created_idx == 1:
            cond.append(f"{created_expr} >= datetime('now','-7 days')")
        elif created_idx == 2:
            cond.append(f"{created_expr} >= datetime('now','-1 month')")
        elif created_idx == 3:
            cond.append(f"{created_expr} >= datetime('now','-1 year')")

        sql = " AND ".join(cond)
        logger.debug("customers sql filter=%r", sql)

        m.setFilter(sql)
        m.select()

        tv = self.host.ui.tvCustomers
        if m.rowCount() > 0:
            idx0 = tv.model().index(0, 0)
            tv.setCurrentIndex(idx0)
            tv.selectRow(0)
        else:
            tv.clearSelection()

        self._filter_active = bool(cond)
        self.update_filter_action_button()
        self.update_nav_state()

    def filter_reset(self) -> None:
        m = getattr(self.host, "model_customers", None)
        if m is None:
            return

        self.host.ui.editCustFilterEmail.clear()
        self.host.ui.editCustFilterName.clear()
        self.host.ui.comboCustFilterCreated.setCurrentIndex(0)

        m.setFilter("")
        m.select()
        if m.rowCount() > 0:
            self.host.ui.tvCustomers.selectRow(0)

        self._filter_active = False
        self.update_filter_action_button()
        self.update_nav_state()

    def update_filter_action_button(self) -> None:
        btn = self.host.ui.btnCustFilterAction

        email_text = self.host.ui.editCustFilterEmail.text().strip()
        name_text = self.host.ui.editCustFilterName.text().strip()
        created_idx = self.host.ui.comboCustFilterCreated.currentIndex()

        has_input = bool(email_text or name_text or created_idx != 0)

        if self._filter_active:
            btn.setEnabled(True)
            btn.setToolTip("Скинути фільтр")
            btn.setProperty("mode", "reset")
        else:
            btn.setEnabled(has_input)
            btn.setToolTip("Застосувати фільтр")
            btn.setProperty("mode", "apply")

        btn.style().unpolish(btn)
        btn.style().polish(btn)
        btn.update()

    @staticmethod
    def _is_valid_email(val) -> bool:
        s = (str(val) if val is not None else "").strip()
        if not s:
            return False
        return bool(_EMAIL_RE.match(s))

    def _on_dirty(self, *_: object) -> None:
        self._dirty = True
        self.update_nav_state()

    def _col(self, field_name: str) -> int:
        m = getattr(self.host, "model_customers", None)
        if m is None:
            return -1
        return m.fieldIndex(field_name)

    def _show_db_error(self, title: str, err: QSqlError) -> None:
        QMessageBox.critical(self.host, title, err.text())

    @staticmethod
    def _normalize_date(value) -> str:
        if value in (None, ""):
            return ""

        # QDateTime / Qt-типи
        if hasattr(value, "toString"):
            try:
                text = value.toString("yyyy-MM-dd HH:mm")
                if text:
                    return text
            except Exception:  # noqa
                pass

        # Python datetime
        if hasattr(value, "strftime"):
            try:
                return value.strftime("%Y-%m-%d %H:%M")
            except Exception:  # noqa
                pass

        s = str(value).strip()
        if not s:
            return ""

        # уніфікація розділювачів дати
        s = s.replace("_", "-")
        s = s.replace("T", " ")

        # UTC suffix
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"

        # ISO parse
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(s)
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:  # noqa
            pass

        # fallback
        if "." in s:
            s = s.split(".", 1)[0]

        if "+" in s:
            s = s.split("+", 1)[0]

        s = " ".join(s.split())

        if len(s) >= 16:
            s = s[:16]

        return s

    def _map_to_source(self, tv, view_index: QModelIndex) -> QModelIndex:  # noqa
        vm = tv.model()
        if isinstance(vm, QSortFilterProxyModel):
            return vm.mapToSource(view_index)
        return view_index

    def _map_from_source(self, tv, src_index: QModelIndex) -> QModelIndex:  # noqa
        vm = tv.model()
        if isinstance(vm, QSortFilterProxyModel):
            return vm.mapFromSource(src_index)
        return src_index

    def _sorting_off(self) -> None:
        tv = self.host.ui.tvCustomers
        self._sorting_was = tv.isSortingEnabled()
        if self._sorting_was:
            tv.setSortingEnabled(False)

    def _sorting_restore(self) -> None:
        tv = self.host.ui.tvCustomers
        if self._dirty:
            tv.setSortingEnabled(False)
            tv.horizontalHeader().setSortIndicatorShown(False)
        else:
            tv.setSortingEnabled(True)
            tv.horizontalHeader().setSortIndicatorShown(True)

    def _sorting_on(self) -> None:
        tv = self.host.ui.tvCustomers
        if not self._dirty:
            tv.setSortingEnabled(True)
            tv.horizontalHeader().setSortIndicatorShown(True)

    def is_dirty(self) -> bool:
        return bool(self._dirty)
