# db_grid_window_logic_lic.py
# -*- coding: utf-8 -*-
"""
LicensesLogic — логіка таблиці licenses (RoadMap38).

Master-detail:
orders (id) -> licenses.order_id (UNIQUE 1:1)

Ключове:
- 1 замовлення = 0/1 ліцензія (order_id UNIQUE) — другу ліцензію блокуємо на Add.
- Валідація запускається ТІЛЬКИ для рядків на збереження (insert/modify),
  не для чистого видалення.
- issued_utc: формат як в інших місцях: YYYY-MM-DD HH:MM.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtSql import QSqlQuery, QSqlTableModel
from PySide6.QtWidgets import QMessageBox, QTableView

logger = logging.getLogger(__name__)

_ALLOWED_EDITIONS = {"PRO", "PRO+"}


class LicensesLogic:
    def __init__(self, host) -> None:
        self.host = host

        self._dirty = False
        self._pending_delete_ids: set[int] = set()

        self.model_licenses: QSqlTableModel | None = None

        self._init_licenses_model()
        self._configure_licenses_view()
        self._bind_dirty_signals()

        self.apply_order_filter(self.host.current_order_id())

    # ------------------------------------------------------------------
    # Model
    # ------------------------------------------------------------------

    def _init_licenses_model(self) -> None:
        if self.host.db is None:
            raise RuntimeError("DB is not initialized")

        m = QSqlTableModel(self.host, self.host.db)
        m.setTable("licenses")
        m.setEditStrategy(QSqlTableModel.EditStrategy.OnManualSubmit)
        m.select()
        self.host.after_model_select(
            self.host.ui.tvLicenses, self.host.model_licenses, "licenses"
        )

        self.model_licenses = m
        self.host.model_licenses = m
        self.host.ui.tvLicenses.setModel(m)

    # ------------------------------------------------------------------
    # View
    # ------------------------------------------------------------------

    def _configure_licenses_view(self) -> None:
        tv = self.host.ui.tvLicenses
        tv.setEnabled(True)

        tv.setEditTriggers(QTableView.EditTrigger.DoubleClicked)
        tv.setTabKeyNavigation(True)
        tv.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        tv.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        tv.setAlternatingRowColors(True)

        tv.setSortingEnabled(False)
        tv.horizontalHeader().setStretchLastSection(True)
        tv.verticalHeader().setVisible(False)

        m = self.model_licenses
        if m is None:
            return

        self.host.set_widths(
            tv,
            m,
            {
                "id": 60,
                "license_uid": 240,
                "license_rel_path": 260,
                "edition": 90,
                "issued_utc": 170,
                "sent_utc": 170,
            },
        )

        self.host.set_readonly_id_column(tv, m)

        self.host.set_headers(
            m,
            {
                "id": "№",
                "order_id": "Order ID",
                "license_uid": "UID",
                "license_rel_path": "Файл",
                "edition": "Редакція",
                "issued_utc": "Видано (UTC)",
                "sent_utc": "Надіслано (UTC)",
            },
        )

        # id readonly
        col_id = m.fieldIndex("id")
        if col_id >= 0:
            tv.setItemDelegateForColumn(col_id, self.host.ro_delegate)

        # order_id hidden (master)
        col_order = m.fieldIndex("order_id")
        if col_order >= 0:
            tv.setColumnHidden(col_order, True)

        # issued_utc delegate
        col_issued = m.fieldIndex("issued_utc")
        if col_issued >= 0:
            tv.setItemDelegateForColumn(col_issued, self.host.utc_delegate)

        # sent_utc readonly
        col_sent = m.fieldIndex("sent_utc")
        if col_sent >= 0:
            tv.setItemDelegateForColumn(col_sent, self.host.ro_delegate)

        self.update_nav_state()

    # ------------------------------------------------------------------
    # Master → Detail
    # ------------------------------------------------------------------

    def apply_order_filter(self, order_id: int | None) -> None:
        m = self.model_licenses
        if m is None:
            return

        if not order_id:
            m.setFilter("1=0")
        else:
            m.setFilter(f"order_id = {order_id}")

        m.select()
        self.host.after_model_select(
            self.host.ui.tvLicenses, self.host.model_licenses, "licenses"
        )

        self.host.ui.tvLicenses.clearSelection()
        self.host.ui.tvLicenses.selectionModel().clearCurrentIndex()
        self.host.ui.tvLicenses.viewport().update()

        tv = self.host.ui.tvLicenses
        if m.rowCount() > 0:
            tv.selectRow(0)

        self._pending_delete_ids.clear()
        self._set_dirty(False)
        self.update_nav_state()

    # ------------------------------------------------------------------
    # Dirty tracking
    # ------------------------------------------------------------------

    def _bind_dirty_signals(self) -> None:
        m = self.model_licenses
        if m is None:
            return

        m.dataChanged.connect(lambda *_: self._set_dirty(True))
        m.rowsInserted.connect(lambda *_: self._set_dirty(True))
        m.rowsRemoved.connect(lambda *_: self._set_dirty(True))

        sm = self.host.ui.tvLicenses.selectionModel()
        if sm is not None:
            sm.currentChanged.connect(lambda *_: self.update_nav_state())

    def _set_dirty(self, value: bool) -> None:
        self._dirty = value
        self.update_nav_state()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(self) -> None:
        m = self.model_licenses
        if m is None:
            return

        order_id = self.host.current_order_id()
        if not order_id:
            QMessageBox.warning(self.host, "Ліцензії", "Спочатку виберіть замовлення.")
            return

        if self._order_has_license(order_id):
            QMessageBox.warning(
                self.host,
                "Ліцензії",
                "Для цього замовлення вже існує ліцензія.\n\n"
                "Друга ліцензія заборонена (1:1).",
            )
            return

        if self._dirty or self._model_has_dirty() or self._pending_delete_ids:
            QMessageBox.warning(
                self.host,
                "Ліцензії",
                "Є незбережені зміни. Спочатку натисніть «Зберегти» або «Відміна».",
            )
            return

        row = m.rowCount()
        m.insertRow(row)

        license_uid = uuid4().hex
        self._set_field(row, "order_id", int(order_id))
        self._set_field(row, "license_uid", license_uid)
        self._set_field(row, "edition", self._get_order_edition(order_id))
        self._set_field(row, "issued_utc", datetime.now(UTC).strftime("%Y-%m-%d %H:%M"))
        self._set_field(row, "sent_utc", "")
        self._set_field(row, "license_rel_path", self._build_license_path(license_uid))

        tv = self.host.ui.tvLicenses
        tv.selectRow(row)
        self._focus_field(row, "edition")

        self._set_dirty(True)

    @staticmethod
    def _build_license_path(license_uid: str) -> str:
        uid = (license_uid or "").strip()
        if not uid:
            return ""
        return f"licenses/{uid}.lic"

    def _get_order_edition(self, order_id: int | None) -> str:
        if not order_id or order_id <= 0:
            return ""

        db = self.host.db
        q = QSqlQuery(db)
        q.prepare("SELECT edition FROM orders WHERE id = ?")
        q.addBindValue(int(order_id))

        if not q.exec():
            logger.warning("orders edition query failed: %s", q.lastError().text())
            return ""

        if not q.next():
            return ""

        v = q.value(0)
        return (str(v) if v is not None else "").strip()

    def delete(self) -> None:
        m = self.model_licenses
        if m is None:
            return

        tv = self.host.ui.tvLicenses
        idx = tv.currentIndex()
        if not idx.isValid():
            return

        lic_uid = self._str(idx.row(), "license_uid")
        what = lic_uid or "Ліцензію"

        if not self.host.confirm_delete(what):
            return

        row = idx.row()
        lic_id = self._get_int(row, "id")
        if lic_id:
            self._pending_delete_ids.add(lic_id)

        m.removeRow(row)
        self._set_dirty(True)

    def save(self) -> None:
        logger.debug("Licenses.save() called: dirty=%s", self._dirty)

        m = self.model_licenses
        if m is None:
            return

        tv = self.host.ui.tvLicenses
        tv.clearFocus()

        current_id = self._current_selected_id()
        pending_uid = self._current_pending_uid()
        row_hint = self._preferred_row_after_delete()

        tv.setSortingEnabled(False)

        delete_only = self._is_delete_only_change()

        if not delete_only:
            try:
                self.host.normalize_model_utc_field(m, "issued_utc")
            except ValueError as e:
                QMessageBox.warning(self.host, "Ліцензії", str(e))
                return

            for row in range(m.rowCount()):
                if self._row_was_deleted(row):
                    continue

                if not self._req_edition(row):
                    return

                uid = self._str(row, "license_uid")
                if not uid:
                    QMessageBox.warning(
                        self.host, "Ліцензії", "license_uid обов’язкове поле."
                    )
                    self._focus_field(row, "license_uid")
                    return

                rel_path = self._str(row, "license_rel_path")
                if not rel_path:
                    QMessageBox.warning(
                        self.host, "Ліцензії", "license_rel_path обов’язкове поле."
                    )
                    self._focus_field(row, "license_rel_path")
                    return

                issued = self._str(row, "issued_utc")
                if not issued:
                    QMessageBox.warning(
                        self.host, "Ліцензії", "issued_utc обов’язкове поле."
                    )
                    self._focus_field(row, "issued_utc")
                    return

                sent = self._str(row, "sent_utc")
                if not sent:
                    self._set_field(row, "sent_utc", "")

        ok = m.submitAll()
        if not ok:
            err = m.lastError().text()
            logger.error("Licenses SAVE failed: %s", err)

            if "UNIQUE constraint failed: licenses.order_id" in err:
                QMessageBox.warning(
                    self.host,
                    "Ліцензії",
                    "Не вдалося зберегти.\n\n"
                    "Для цього замовлення вже існує ліцензія (1:1).",
                )
                return

            if "UNIQUE constraint failed: licenses.license_uid" in err:
                QMessageBox.warning(
                    self.host,
                    "Ліцензії",
                    "Не вдалося зберегти.\n\nlicense_uid має бути унікальним.",
                )
                return

            QMessageBox.warning(self.host, "Ліцензії", f"Не вдалося зберегти.\n\n{err}")
            return

        self._dirty = False
        self._pending_delete_ids.clear()

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
            select_license_uid=pending_uid,
            select_row_hint=row_hint,
        )
        return

    def cancel(self) -> None:
        m = self.model_licenses
        if m is None:
            return
        m.revertAll()
        self._pending_delete_ids.clear()
        self._set_dirty(False)
        self.refresh()

    def refresh(
        self,
        select_id: int | None = None,
        select_license_uid: str | None = None,
        select_row_hint: int | None = None,
    ) -> None:
        m = self.model_licenses
        tv = self.host.ui.tvLicenses
        if m is None:
            return

        current_order_id = self._current_master_order_id()

        m.select()
        self.host.after_model_select(tv, self.host.model_licenses, "licenses")

        # 1. пріоритет — явно заданий license_uid
        if select_license_uid:
            if self.select_by_license_uid(select_license_uid):
                self.update_nav_state()
                return

        # 2. далі — явно заданий id
        if select_id:
            if self._select_row_by_id(tv, m, select_id):
                self.update_nav_state()
                return

        # 3. далі — рядок для поточного order_id
        if current_order_id:
            self.select_by_order_id(current_order_id)
            if tv.currentIndex().isValid():
                self.update_nav_state()
                return

        # 4. далі — підказка рядка після delete
        if select_row_hint is not None and m.rowCount() > 0:
            row = max(0, min(select_row_hint, m.rowCount() - 1))
            tv.selectRow(row)
            self.update_nav_state()
            return

        # 5. fallback — перший рядок
        if m.rowCount() > 0 and not tv.currentIndex().isValid():
            tv.selectRow(0)

        self.update_nav_state()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def first(self) -> None:
        self._nav_select(0)

    def last(self) -> None:
        m = self.model_licenses
        if m is None:
            return
        self._nav_select(max(0, m.rowCount() - 1))

    def prev(self) -> None:
        tv = self.host.ui.tvLicenses
        row = tv.currentIndex().row()
        self._nav_select(max(0, row - 1))

    def next(self) -> None:
        m = self.model_licenses
        if m is None:
            return
        tv = self.host.ui.tvLicenses
        row = tv.currentIndex().row()
        self._nav_select(min(m.rowCount() - 1, row + 1))

    def _nav_select(self, row: int) -> None:
        m = self.model_licenses
        if m is None or m.rowCount() <= 0:
            return
        row = max(0, min(row, m.rowCount() - 1))
        self.host.ui.tvLicenses.selectRow(row)
        self.update_nav_state()

    def update_nav_state(self) -> None:
        m = self.model_licenses
        tv = self.host.ui.tvLicenses

        has_rows = bool(m is not None and m.rowCount() > 0)
        cur_row = (
            tv.currentIndex().row() if has_rows and tv.currentIndex().isValid() else -1
        )

        self.host.ui.btnLicFirst.setEnabled(has_rows and cur_row > 0)
        self.host.ui.btnLicPrev.setEnabled(has_rows and cur_row > 0)
        self.host.ui.btnLicNext.setEnabled(has_rows and cur_row < (m.rowCount() - 1))
        self.host.ui.btnLicLast.setEnabled(has_rows and cur_row < (m.rowCount() - 1))

        dirty = self._dirty or self._model_has_dirty() or bool(self._pending_delete_ids)
        self.host.ui.btnLicSave.setEnabled(dirty)
        self.host.ui.btnLicCancel.setEnabled(dirty)

        has_order = bool(self.host.current_order_id())
        can_add = (
            has_order
            and not dirty
            and not self._order_has_license(self.host.current_order_id())
        )

        self.host.ui.btnLicAdd.setEnabled(can_add)
        self.host.ui.btnLicDel.setEnabled(has_rows)
        self.host.ui.btnLicRefresh.setEnabled(True)

        self.host.set_nav_active(
            "Lic",
            {
                "First": self.host.ui.btnLicFirst.isEnabled(),
                "Prev": self.host.ui.btnLicPrev.isEnabled(),
                "Next": self.host.ui.btnLicNext.isEnabled(),
                "Last": self.host.ui.btnLicLast.isEnabled(),
                "Add": self.host.ui.btnLicAdd.isEnabled(),
                "Del": self.host.ui.btnLicDel.isEnabled(),
                "Save": self.host.ui.btnLicSave.isEnabled(),
                "Cancel": self.host.ui.btnLicCancel.isEnabled(),
                "Refresh": self.host.ui.btnLicRefresh.isEnabled(),
            },
        )

        self.host.sync_button_states()

        if hasattr(self.host.ui, "btnLicEmail"):
            self.host.ui.btnLicEmail.setEnabled(has_rows and not dirty)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _model_has_dirty(self) -> bool:
        m = self.model_licenses
        if m is None:
            return False
        for row in range(m.rowCount()):
            for col in range(m.columnCount()):
                if m.isDirty(m.index(row, col)):
                    return True
        return False

    def _is_delete_only_change(self) -> bool:
        if not self._pending_delete_ids:
            return False

        m = self.model_licenses
        if m is None:
            return False

        col_id = m.fieldIndex("id")
        if col_id < 0:
            return False

        for row in range(m.rowCount()):
            v = m.data(m.index(row, col_id), Qt.ItemDataRole.EditRole)
            if v in (None, "", 0):
                return False

            for col in range(m.columnCount()):
                if m.isDirty(m.index(row, col)):
                    return False

        return True

    def _row_was_deleted(self, row: int) -> bool:
        lic_pk = self._get_int(row, "id")
        if not lic_pk:
            return False
        return lic_pk in self._pending_delete_ids

    def _order_has_license(self, order_id: int | None) -> bool:
        if not order_id:
            return False

        # 1) якщо в таблиці вже видно рядок — точно є
        m = self.model_licenses
        if m is not None and m.rowCount() > 0:
            return True

        # 2) якщо ми щойно видалили та ще не зберегли —
        #    забороняємо заміну в тому ж submit
        if self._pending_delete_ids:
            return True

        # 3) підстраховка через DB
        if self.host.db is None:
            return False

        q = QSqlQuery(self.host.db)
        q.prepare("SELECT 1 FROM licenses WHERE order_id = :oid LIMIT 1")
        q.bindValue(":oid", int(order_id))
        if not q.exec():
            logger.warning("License exists check failed: %s", q.lastError().text())
            return False
        return q.next()

    def _current_order_uid(self) -> str | None:
        m = getattr(self.host, "model_orders", None)
        if m is None:
            return None
        idx = self.host.ui.tvOrders.currentIndex()
        if not idx.isValid():
            return None

        row = idx.row()
        col_uid = m.fieldIndex("order_uid")
        if col_uid < 0:
            return None
        v = m.data(m.index(row, col_uid), Qt.ItemDataRole.EditRole)
        s = (str(v) if v is not None else "").strip()
        return s or None

    def _set_field(self, row: int, field: str, value) -> None:
        m = self.model_licenses
        if m is None:
            return
        col = m.fieldIndex(field)
        if col >= 0:
            m.setData(m.index(row, col), value)

    def _str(self, row: int, field: str) -> str:
        m = self.model_licenses
        if m is None:
            return ""
        col = m.fieldIndex(field)
        if col < 0:
            return ""
        v = m.data(m.index(row, col), Qt.ItemDataRole.EditRole)
        return (str(v) if v is not None else "").strip()

    def _get_int(self, row: int, field: str) -> int | None:
        s = self._str(row, field)
        try:
            v = int(s)
            return v if v > 0 else None
        except Exception:  # noqa
            return None

    def _focus_field(self, row: int, field: str) -> None:
        m = self.model_licenses
        if m is None:
            return
        col = m.fieldIndex(field)
        if col >= 0:
            self._focus_cell(row, col)

    def _focus_cell(self, row: int, col: int) -> None:
        m = self.model_licenses
        if m is None:
            return
        tv = self.host.ui.tvLicenses
        idx = m.index(row, col)
        tv.setCurrentIndex(idx)
        tv.scrollTo(idx)
        tv.edit(idx)

    def _req_edition(self, row: int) -> bool:
        ed_raw = self._str(row, "edition")
        s = ed_raw.strip().upper().replace(" ", "")
        s = s.replace("_", "")

        if not s:
            QMessageBox.warning(self.host, "Ліцензії", "Edition — обов’язкове поле.")
            self._focus_field(row, "edition")
            return False

        # Нормалізація "pro", "Pro+", "pro plus", "PROPLUS" -> PRO/PRO+
        if s in {"PRO", "PRO+"}:
            ed = s
        else:
            s2 = s.replace("+", "")
            if s2 == "PROPLUS":
                ed = "PRO+"
            else:
                ed = s  # як ввели після чистки

        self._set_field(row, "edition", ed)
        return True

    def _current_selected_id(self) -> int | None:
        m = self.model_licenses
        if m is None:
            return None

        tv = self.host.ui.tvLicenses
        idx = tv.currentIndex()
        if not idx.isValid():
            return None

        col_id = m.fieldIndex("id")
        if col_id < 0:
            return None

        try:
            v = m.data(m.index(idx.row(), col_id))
            lid = int(v)
            return lid if lid > 0 else None
        except Exception:  # noqa
            return None

    def _current_pending_uid(self) -> str:
        m = self.model_licenses
        if m is None:
            return ""

        tv = self.host.ui.tvLicenses
        idx = tv.currentIndex()
        if not idx.isValid():
            return ""

        col_uid = m.fieldIndex("license_uid")
        if col_uid < 0:
            return ""

        return str(m.data(m.index(idx.row(), col_uid)) or "").strip()

    def _preferred_row_after_delete(self) -> int | None:
        m = self.model_licenses
        if m is None:
            return None

        tv = self.host.ui.tvLicenses
        idx = tv.currentIndex()
        if not idx.isValid():
            return 0 if m.rowCount() > 0 else None

        return max(0, idx.row())

    @staticmethod
    def _select_row_by_id(tv: QTableView, m: QSqlTableModel, lid: int) -> bool:
        col_id = m.fieldIndex("id")
        if col_id < 0:
            return False

        for row in range(m.rowCount()):
            v = m.data(m.index(row, col_id))
            try:
                if int(v) == int(lid):
                    tv.selectRow(row)
                    tv.scrollTo(m.index(row, 0))
                    tv.setFocus()
                    return True
            except Exception:  # noqa
                continue
        return False

    @staticmethod
    def _select_row_by_uid(tv: QTableView, m: QSqlTableModel, license_uid: str) -> bool:
        col_uid = m.fieldIndex("license_uid")
        if col_uid < 0:
            return False

        target = (license_uid or "").strip()
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

    def select_by_order_id(self, order_id: int) -> None:
        m = self.host.model_licenses
        tv = self.host.ui.tvLicenses
        col = m.fieldIndex("order_id")
        if col < 0:
            return

        for row in range(m.rowCount()):
            value = m.data(m.index(row, col))
            try:
                if int(value or 0) == int(order_id):
                    tv.selectRow(row)
                    return
            except (TypeError, ValueError):
                continue

    def _current_master_order_id(self) -> int | None:
        """Повернути поточний order_id з таблиці Orders."""
        m = getattr(self.host, "model_orders", None)
        tv = self.host.ui.tvOrders
        if m is None:
            return None

        idx = tv.currentIndex()
        if not idx.isValid():
            return None

        col_id = m.fieldIndex("id")
        if col_id < 0:
            return None

        try:
            value = m.data(m.index(idx.row(), col_id), Qt.ItemDataRole.EditRole)
            oid = int(value)
            return oid if oid > 0 else None
        except Exception:  # noqa
            return None

    def select_by_license_uid(self, license_uid: str) -> bool:
        m = self.model_licenses
        if m is None:
            return False
        tv = self.host.ui.tvLicenses
        return self._select_row_by_uid(tv, m, license_uid)
