# db_grid_window_logic.py
# -*- coding: utf-8 -*-
"""
DbGridWindow — головне вікно DbGrid (RoadMap39).

Стабільний master-detail:
customers -> orders -> (payments, licenses)

Ключове:
- DB connection + PRAGMA
- shared helpers: confirm_delete, sql_like, normalize_model_utc_field
- окремі модулі логіки: CustomersLogic / OrdersLogic / PaymentsLogic / LicensesLogic
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtSql import QSqlDatabase, QSqlQuery, QSqlTableModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHeaderView,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QStyledItemDelegate,
    QTableView,
)

from office.core.datetime_utils import utc_now_str
from office.core.db_grid_window_logic_cust import CustomersLogic
from office.core.db_grid_window_logic_lic import LicensesLogic
from office.core.db_grid_window_logic_ord import OrdersLogic
from office.core.db_grid_window_logic_pay import PaymentsLogic
from office.core.db_repo import DbRepo
from office.core.email_send_service import send_license_email_with_preview
from office.core.license_email_builder import (
    build_license_email_body,
    build_license_email_subject,
    write_license_email_file,
)
from office.core.mail_settings import OFFICE_EMAIL_INBOX
from office.core.office_paths import get_licenses_dir, get_office_dir
from office.core.order_request_dialog import OrderRequestDialog
from office.ui.ui_db_grid import Ui_DbGridWindow

logger = logging.getLogger(__name__)

_DT_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DT_MIN_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}$")


class ReadOnlyDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):  # noqa: N802 (Qt naming)
        return None


class UtcShortDelegate(QStyledItemDelegate):
    def displayText(self, value, locale):  # noqa: N802 (Qt naming)
        if not value:
            return ""
        try:
            dt = datetime.fromisoformat(str(value))
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:  # noqa
            return str(value)


class DbGridWindow(QDialog):
    """CUST ONLY window."""

    def __init__(self, db_path: str, parent=None) -> None:
        super().__init__(parent)

        self.model_customers: QSqlTableModel | None = None
        self.model_orders = None
        self.model_payments = None
        self.model_licenses = None

        self._db_path = db_path
        self._conn_name = f"office_grid_{uuid4().hex}"
        self._db: QSqlDatabase | None = None

        self.ui = Ui_DbGridWindow()
        self.ui.setupUi(self)

        # Оформлення іконок

        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )

        self._apply_nav_icons()
        self._apply_button_roles()
        self._apply_nav_tooltips()

        self.ui.btnClose.setToolTip("Закрити")
        self.ui.btnClose.clicked.connect(self.close)

        self._ro_delegate = ReadOnlyDelegate(self)
        self._utc_delegate = UtcShortDelegate(self)

        # public aliases for OrdersLogic (RoadMap37)
        self.ro_delegate = self._ro_delegate
        self.utc_delegate = self._utc_delegate
        self.set_widths = self._set_widths
        self.set_headers = self._set_headers

        self._init_db()
        self._init_customers_model()
        self.cust = CustomersLogic(self)

        self.ord = OrdersLogic(self)
        self.pay = PaymentsLogic(self)
        self.lic = LicensesLogic(self)

        self._configure_customers_view()
        self.configure_table_view(self.ui.tvOrders)
        self.configure_table_view(self.ui.tvPayments)
        self.configure_table_view(self.ui.tvLicenses)

        self._bind_customers_buttons()
        self._bind_orders_buttons()
        self._bind_payments_buttons()
        self._bind_licenses_buttons()

        self.refresh_customers()
        self._on_customer_changed()  # щоб одразу підхопити orders по першому клієнту
        self._on_order_changed()  # payments+licenses по першому order

    # ---------------------------------------------------------------------
    # DB
    # ---------------------------------------------------------------------

    @property
    def db(self) -> QSqlDatabase | None:
        return self._db

    def _init_db(self) -> None:
        db = QSqlDatabase.addDatabase("QSQLITE", self._conn_name)
        db.setDatabaseName(self._db_path)

        if not db.open():
            raise RuntimeError(f"Cannot open DB: {db.lastError().text()}")

        self._db = db

        self._exec_pragma("foreign_keys", "ON")
        self._exec_pragma("journal_mode", "WAL")
        self._exec_pragma("synchronous", "NORMAL")
        self._exec_pragma("busy_timeout", "5000")

    def _exec_pragma(self, key: str, value: str) -> None:
        if self._db is None:
            return
        q = QSqlQuery(self._db)
        sql = f"PRAGMA {key}={value};"
        ok = q.exec(sql)
        if ok:
            logger.debug("PRAGMA ok: %s", sql)
        else:
            logger.warning("PRAGMA failed: %s | %s", sql, q.lastError().text())

    # ---------------------------------------------------------------------
    # Customers model + view
    # ---------------------------------------------------------------------
    def _init_customers_model(self) -> None:
        if self._db is None:
            raise RuntimeError("DB is not initialized")

        m = QSqlTableModel(self, self._db)
        m.setTable("customers")
        m.setEditStrategy(QSqlTableModel.EditStrategy.OnManualSubmit)

        col_id = m.fieldIndex("id")
        if col_id >= 0:
            m.setSort(col_id, Qt.SortOrder.AscendingOrder)
        m.select()

        self._set_headers(
            m,
            {
                "id": "№",
                "email": "Email",
                "name": "ПІБ",
                "note": "Примітка",
                "created_utc": "Створено (UTC)",
            },
        )

        self.model_customers = m
        self.ui.tvCustomers.setModel(m)

        self.ui.tvCustomers.sortByColumn(col_id, Qt.SortOrder.AscendingOrder)

        logger.debug("tvCustomers model=%s", type(self.ui.tvCustomers.model()).__name__)

    def _configure_customers_view(self) -> None:
        tv = self.ui.tvCustomers
        self._configure_table_view(tv)

        m = self.model_customers
        if m is not None:
            self._set_widths(
                tv,
                m,
                {"id": 60, "email": 220, "name": 240, "note": 260, "created_utc": 170},
            )
            self.set_readonly_id_column(tv, m)

    def _bind_payments_buttons(self) -> None:
        self.ui.btnPayAdd.clicked.connect(self.pay.add)
        if hasattr(self.ui, "btnPayAddDialog"):
            self.ui.btnPayAddDialog.clicked.connect(self.pay.open_add_dialog)
        if hasattr(self.ui, "btnPayLinkToOrder"):
            self.ui.btnPayLinkToOrder.clicked.connect(
                self.pay.link_selected_payment_to_order
            )
        if hasattr(self.ui, "chkPayUnlinked"):
            self.ui.chkPayUnlinked.toggled.connect(self.pay.on_unlinked_toggled)

        self.ui.btnPayDel.clicked.connect(self.pay.delete)
        self.ui.btnPaySave.clicked.connect(self.pay.save)
        self.ui.btnPayCancel.clicked.connect(self.pay.cancel)
        self.ui.btnPayRefresh.clicked.connect(self.pay.refresh)

        self.ui.btnPayFirst.clicked.connect(self.pay.first)
        self.ui.btnPayPrev.clicked.connect(self.pay.prev)
        self.ui.btnPayNext.clicked.connect(self.pay.next)
        self.ui.btnPayLast.clicked.connect(self.pay.last)

    def _bind_orders_buttons(self) -> None:
        self.ui.btnOrdAdd.clicked.connect(self.ord.add)
        self.ui.btnOrdDel.clicked.connect(self.ord.delete)
        self.ui.btnOrdSave.clicked.connect(self.ord.save)
        self.ui.btnOrdCancel.clicked.connect(self.ord.cancel)
        self.ui.btnOrdRefresh.clicked.connect(self.ord.refresh)
        if hasattr(self.ui, "btnOrdIssue"):
            self.ui.btnOrdIssue.clicked.connect(self.ord.issue_license)

        self.ui.btnOrdFirst.clicked.connect(self.ord.first)
        self.ui.btnOrdPrev.clicked.connect(self.ord.prev)
        self.ui.btnOrdNext.clicked.connect(self.ord.next)
        self.ui.btnOrdLast.clicked.connect(self.ord.last)

        sm = self.ui.tvOrders.selectionModel()
        if sm is not None:
            sm.currentChanged.connect(lambda _cur, _prev: self._on_order_changed())

    def _bind_licenses_buttons(self) -> None:
        self.ui.btnLicAdd.clicked.connect(self.lic.add)
        self.ui.btnLicDel.clicked.connect(self.lic.delete)
        self.ui.btnLicSave.clicked.connect(self.lic.save)
        self.ui.btnLicCancel.clicked.connect(self.lic.cancel)
        self.ui.btnLicRefresh.clicked.connect(self.lic.refresh)
        if hasattr(self.ui, "btnLicEmail"):
            self.ui.btnLicEmail.clicked.connect(self._on_lic_email)

        self.ui.btnLicFirst.clicked.connect(self.lic.first)
        self.ui.btnLicPrev.clicked.connect(self.lic.prev)
        self.ui.btnLicNext.clicked.connect(self.lic.next)
        self.ui.btnLicLast.clicked.connect(self.lic.last)

    def _bind_customers_buttons(self) -> None:
        self.ui.btnCustAdd.clicked.connect(self.cust.add)
        self.ui.btnCustDel.clicked.connect(self.cust.delete)
        self.ui.btnCustSave.clicked.connect(self.cust.save)
        self.ui.btnCustCancel.clicked.connect(self.cust.cancel)
        self.ui.btnCustRefresh.clicked.connect(self.cust.refresh)
        if hasattr(self.ui, "btnCustOrderRequest"):
            self.ui.btnCustOrderRequest.clicked.connect(self._on_cust_order_request)

        self.ui.btnCustFirst.clicked.connect(self.cust.first)
        self.ui.btnCustPrev.clicked.connect(self.cust.prev)
        self.ui.btnCustNext.clicked.connect(self.cust.next)
        self.ui.btnCustLast.clicked.connect(self.cust.last)

        self.ui.btnCustFilterAction.clicked.connect(self.cust.filter_action)

        self.ui.editCustFilterEmail.textChanged.connect(
            self.cust.update_filter_action_button
        )
        self.ui.editCustFilterName.textChanged.connect(
            self.cust.update_filter_action_button
        )
        self.ui.comboCustFilterCreated.currentIndexChanged.connect(
            self.cust.update_filter_action_button
        )
        self.ui.editCustFilterEmail.returnPressed.connect(self.cust.filter_apply)
        self.ui.editCustFilterName.returnPressed.connect(self.cust.filter_apply)

        sm = self.ui.tvCustomers.selectionModel()
        if sm is not None:
            sm.currentChanged.connect(lambda _cur, _prev: self.cust.update_nav_state())
            sm.currentChanged.connect(lambda _cur, _prev: self._on_customer_changed())

        self.cust.update_filter_action_button()

        logger.debug("_bind_customers_buttons END")

    def _on_customer_changed(self) -> None:
        cust_id = self.current_customer_id()

        if getattr(self, "ord", None) is not None:
            self.ord.apply_customer_filter(cust_id)

        # Важливо: спочатку вибір рядка в Orders
        if (
            getattr(self, "model_orders", None) is not None
            and self.model_orders.rowCount() > 0
        ):
            self.ui.tvOrders.selectRow(0)
        else:
            # якщо orders порожні - знімаємо фільтр licenses
            if getattr(self, "lic", None) is not None:
                self.lic.apply_order_filter(None)
            return

        # Тепер уже licenses по актуальному selection
        self._on_order_changed()

    def _on_order_changed(self) -> None:
        order_id = self.current_order_id()
        if getattr(self, "pay", None) is not None:
            self.pay.apply_order_filter(order_id)
        if getattr(self, "lic", None) is not None:
            self.lic.apply_order_filter(order_id)
        if getattr(self, "ord", None) is not None:
            self.ord.update_nav_state()

    def current_customer_id(self) -> int | None:
        m = getattr(self, "model_customers", None)
        if m is None:
            return None

        idx = self.ui.tvCustomers.currentIndex()
        if not idx.isValid():
            return None

        row = idx.row()
        col_id = m.fieldIndex("id")
        if col_id < 0:
            return None

        v = m.data(m.index(row, col_id))
        try:
            cid = int(v)
            return cid if cid > 0 else None
        except Exception:  # noqa
            return None

    def current_order_id(self) -> int | None:
        m = getattr(self, "model_orders", None)
        if m is None:
            return None

        idx = self.ui.tvOrders.currentIndex()
        if not idx.isValid():
            return None

        row = idx.row()
        col_id = m.fieldIndex("id")
        if col_id < 0:
            return None

        v = m.data(m.index(row, col_id))
        try:
            oid = int(v)
            return oid if oid > 0 else None
        except Exception:  # noqa
            return None

    # ---------------------------------------------------------------------
    # Оформлення кнопок
    # ---------------------------------------------------------------------
    def set_button_state(self, button, is_active: bool) -> None:
        self._set_button_state(button, is_active)

    @staticmethod
    def _set_button_state(btn: QPushButton, is_active: bool) -> None:
        # enabled
        btn.setEnabled(bool(is_active))

        # style state
        btn.setProperty("state", "active" if is_active else "inactive")
        btn.style().unpolish(btn)
        btn.style().polish(btn)
        btn.update()

    def set_nav_active(self, prefix: str, active: dict[str, bool]) -> None:
        for suffix, is_active in active.items():
            btn = getattr(self.ui, f"btn{prefix}{suffix}", None)
            if isinstance(btn, QPushButton):
                btn.setEnabled(is_active)
                self._set_button_state(btn, is_active)

    @staticmethod
    def _make_nav_icon(base_name: str) -> QIcon:
        icon = QIcon()
        icon.addFile(f":/office/icons/nav/{base_name}.png", mode=QIcon.Mode.Normal)
        icon.addFile(
            f":/office/icons/nav/{base_name}_hover.png", mode=QIcon.Mode.Active
        )
        icon.addFile(
            f":/office/icons/nav/{base_name}_disabled.png",
            mode=QIcon.Mode.Disabled,
        )
        return icon

    def _apply_nav_icons(self) -> None:
        m = self._make_nav_icon

        # Customers
        self.ui.btnCustFirst.setIcon(m("nav_first"))
        self.ui.btnCustPrev.setIcon(m("nav_prev"))
        self.ui.btnCustNext.setIcon(m("nav_next"))
        self.ui.btnCustLast.setIcon(m("nav_last"))
        self.ui.btnCustAdd.setIcon(m("nav_add"))
        self.ui.btnCustDel.setIcon(m("nav_delete"))
        self.ui.btnCustSave.setIcon(m("nav_save"))
        self.ui.btnCustCancel.setIcon(m("nav_cancel"))
        self.ui.btnCustRefresh.setIcon(m("nav_refresh"))

        # Orders
        self.ui.btnOrdFirst.setIcon(m("nav_first"))
        self.ui.btnOrdPrev.setIcon(m("nav_prev"))
        self.ui.btnOrdNext.setIcon(m("nav_next"))
        self.ui.btnOrdLast.setIcon(m("nav_last"))
        self.ui.btnOrdAdd.setIcon(m("nav_add"))
        self.ui.btnOrdDel.setIcon(m("nav_delete"))
        self.ui.btnOrdSave.setIcon(m("nav_save"))
        self.ui.btnOrdCancel.setIcon(m("nav_cancel"))
        self.ui.btnOrdRefresh.setIcon(m("nav_refresh"))

        # Payments
        self.ui.btnPayFirst.setIcon(m("nav_first"))
        self.ui.btnPayPrev.setIcon(m("nav_prev"))
        self.ui.btnPayNext.setIcon(m("nav_next"))
        self.ui.btnPayLast.setIcon(m("nav_last"))
        self.ui.btnPayAdd.setIcon(m("nav_add"))
        self.ui.btnPayDel.setIcon(m("nav_delete"))
        self.ui.btnPaySave.setIcon(m("nav_save"))
        self.ui.btnPayCancel.setIcon(m("nav_cancel"))
        self.ui.btnPayRefresh.setIcon(m("nav_refresh"))

        # Licenses
        self.ui.btnLicFirst.setIcon(m("nav_first"))
        self.ui.btnLicPrev.setIcon(m("nav_prev"))
        self.ui.btnLicNext.setIcon(m("nav_next"))
        self.ui.btnLicLast.setIcon(m("nav_last"))
        self.ui.btnLicAdd.setIcon(m("nav_add"))
        self.ui.btnLicDel.setIcon(m("nav_delete"))
        self.ui.btnLicSave.setIcon(m("nav_save"))
        self.ui.btnLicCancel.setIcon(m("nav_cancel"))
        self.ui.btnLicRefresh.setIcon(m("nav_refresh"))

        # --- Office buttons (RoadMap39) ---
        # Стоять у навігаторах, але не є стандартними кнопками навігації.
        # Важливо: resources.qrc має prefix="/office",
        # тому шлях починається з :/office/...
        if hasattr(self.ui, "btnCustOrderRequest"):
            self.ui.btnCustOrderRequest.setIcon(
                QIcon(":/office/icons/bisnes_push/add_order_default.png")
            )
        if hasattr(self.ui, "btnOrdIssue"):
            self.ui.btnOrdIssue.setIcon(
                QIcon(":/office/icons/bisnes_push/generate_license_default.png")
            )
        if hasattr(self.ui, "btnPayAddDialog"):
            self.ui.btnPayAddDialog.setIcon(
                QIcon(":/office/icons/bisnes_push/add_payment_default.png")
            )
        if hasattr(self.ui, "btnPayLinkToOrder"):
            self.ui.btnPayLinkToOrder.setIcon(
                QIcon(":/office/icons/bisnes_push/payment_from_order_default.png")
            )
        if hasattr(self.ui, "btnLicEmail"):
            self.ui.btnLicEmail.setIcon(
                QIcon(":/office/icons/bisnes_push/send_email_default.png")
            )

    def _apply_nav_tooltips(self) -> None:
        tips = {
            # Customers
            "btnCustFirst": "Перейти до першого запису",
            "btnCustPrev": "Попередній запис",
            "btnCustNext": "Наступний запис",
            "btnCustLast": "Перейти до останнього запису",
            "btnCustAdd": "Додати нового клієнта",
            "btnCustDel": "Видалити вибраного клієнта (потрібно Save)",
            "btnCustSave": "Зберегти зміни",
            "btnCustCancel": "Скасувати незбережені зміни",
            "btnCustRefresh": "Оновити таблицю",
            "btnCustOrderRequest": "Замовлення ліцензії (через форму)",
            # Orders
            "btnOrdFirst": "Перейти до першого замовлення",
            "btnOrdPrev": "Попереднє замовлення",
            "btnOrdNext": "Наступне замовлення",
            "btnOrdLast": "Перейти до останнього замовлення",
            "btnOrdAdd": "Додати нове замовлення",
            "btnOrdDel": "Видалити вибране замовлення (потрібно Save)",
            "btnOrdSave": "Зберегти зміни",
            "btnOrdCancel": "Скасувати незбережені зміни",
            "btnOrdRefresh": "Оновити таблицю",
            "btnOrdIssue": "Видати ліцензію для вибраного замовлення",
            # Payments
            "btnPayFirst": "Перейти до першого платежу",
            "btnPayPrev": "Попередній платіж",
            "btnPayNext": "Наступний платіж",
            "btnPayLast": "Перейти до останнього платежу",
            "btnPayAdd": "Додати новий платіж",
            "btnPayDel": "Видалити вибраний платіж (потрібно Save)",
            "btnPaySave": "Зберегти зміни",
            "btnPayCancel": "Скасувати незбережені зміни",
            "btnPayRefresh": "Оновити таблицю",
            "btnPayAddDialog": "Додати платіж (через форму)",
            "btnPayLinkToOrder": "Прив'язати платіж до замовлення",
            # Licenses
            "btnLicFirst": "Перейти до першої ліцензії",
            "btnLicPrev": "Попередня ліцензія",
            "btnLicNext": "Наступна ліцензія",
            "btnLicLast": "Перейти до останньої ліцензії",
            "btnLicAdd": "Додати нову ліцензію",
            "btnLicDel": "Видалити вибрану ліцензію (потрібно Save)",
            "btnLicSave": "Зберегти зміни",
            "btnLicCancel": "Скасувати незбережені зміни",
            "btnLicRefresh": "Оновити таблицю",
            "btnLicEmail": "Надіслати e-mail",
        }

        for name, text in tips.items():
            w = getattr(self.ui, name, None)
            if w is not None:
                w.setToolTip(text)

    def confirm_delete(self, what: str) -> bool:
        text = (
            f"Ви хочете видалити саме цей запис ({what})?\n\n"
            "Видалення буде виконано після натискання «Зберегти».\n"
            "Для відміни натисніть «Відміна»."
        )

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Підтвердження видалення")
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

    @staticmethod
    def sql_like(s: str) -> str:
        s = (s or "").strip()
        s = s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return s

    def grid_add(self, model: QSqlTableModel, tv: QTableView) -> int:
        row = model.rowCount()
        model.insertRow(row)
        tv.selectRow(row)

        # default created_utc for customers
        if model is self.model_customers:
            self._set_now_utc(model, row, "created_utc")

        # focus email
        col_email = model.fieldIndex("email")
        if col_email >= 0:
            self._focus_edit_cell(tv, model, row, col_email)

        return row

    @staticmethod
    def grid_delete(model: QSqlTableModel, tv: QTableView) -> None:
        idx = tv.currentIndex()
        if not idx.isValid():
            return
        model.removeRow(idx.row())

    def grid_save(self, model: QSqlTableModel, tv: QTableView, title: str) -> bool:
        # зафіксувати редагування клітинки
        tv.clearFocus()

        ok = model.submitAll()
        if ok:
            return True

        err = model.lastError().text()
        logger.error("GRID_SAVE ERROR (%s): %s", title, err)
        QMessageBox.warning(
            self,
            "LGE Office",
            f"Не вдалося зберегти зміни ({title}).\n\n{err}",
        )
        return False

    @staticmethod
    def grid_cancel(model: QSqlTableModel) -> None:
        model.revertAll()

    @staticmethod
    def grid_refresh(model: QSqlTableModel) -> None:
        model.select()

    def refresh_customers(self) -> None:
        if self.model_customers is None:
            return

        self.model_customers.select()

        if self.model_customers.rowCount() > 0:
            self.ui.tvCustomers.selectRow(0)

        self.cust.update_nav_state()

        self.after_model_select(self.ui.tvCustomers, self.model_customers, "customers")

    @staticmethod
    def normalize_model_utc_field(model: QSqlTableModel, field: str) -> None:
        col = model.fieldIndex(field)
        if col < 0:
            return

        for row in range(model.rowCount()):
            idx = model.index(row, col)
            if not model.isDirty(idx):
                continue

            raw = model.data(idx, Qt.ItemDataRole.EditRole)
            s = (str(raw) if raw is not None else "").strip()

            if not s:
                continue

            if _DT_DATE_RE.match(s):
                s = f"{s} 00:00"
            if _DT_MIN_RE.match(s):
                model.setData(idx, s)
                continue

            raise ValueError(
                "Невірний формат дати/часу. Дозволено: YYYY-MM-DD або YYYY-MM-DD HH:MM"
            )

    @staticmethod
    def _set_now_utc(model: QSqlTableModel, row: int, field: str) -> None:
        col = model.fieldIndex(field)
        if col >= 0:
            model.setData(model.index(row, col), datetime.now(UTC).isoformat())

    @staticmethod
    def _focus_edit_cell(
        tv: QTableView, model: QSqlTableModel, row: int, col: int
    ) -> None:
        idx = model.index(row, col)
        tv.setCurrentIndex(idx)
        tv.scrollTo(idx)
        tv.edit(idx)

    @staticmethod
    def _set_headers(model: QSqlTableModel, mapping: dict[str, str]) -> None:
        for col_name, title in mapping.items():
            col = model.fieldIndex(col_name)
            if col >= 0:
                model.setHeaderData(col, Qt.Orientation.Horizontal, title)

    @staticmethod
    def _set_widths(
        tv: QTableView, model: QSqlTableModel, widths: dict[str, int]
    ) -> None:
        for col_name, w in widths.items():
            col = model.fieldIndex(col_name)
            if col >= 0:
                tv.setColumnWidth(col, w)

    @staticmethod
    def configure_table_view(tv: QTableView) -> None:
        tv.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
        tv.setTabKeyNavigation(True)
        tv.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tv.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        tv.verticalHeader().setVisible(False)

        tv.horizontalHeader().setStretchLastSection(False)
        tv.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        tv.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        tv.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def _configure_table_view(self, tv: QTableView) -> None:
        self.configure_table_view(tv)

    @staticmethod
    def after_model_select(
        tv: QTableView,
        model: QSqlTableModel,
        table_key: str,
        delay_ms: int = 50,
    ) -> None:
        """
        Підгонка колонок під 4 таблиці: customers/orders/payments/licenses.
        - resizeColumnsToContents()
        - clamp min/max (по колонках і дефолт)
        - 1 колонка Stretch (по пріоритету)
        """
        # Налаштування по таблицях: field_name -> (min, max)
        per_table_limits: dict[str, dict[str, tuple[int, int]]] = {
            "customers": {
                "id": (60, 70),
                "email": (180, 320),
                "name": (140, 320),
                "note": (140, 360),
                "created_utc": (140, 190),
            },
            "orders": {
                "id": (60, 70),
                "order_code": (180, 360),
                "edition": (70, 120),
                "app_version": (70, 120),
                "payment_ref": (120, 220),
                "fingerprint": (160, 220),
                "created_utc": (140, 190),
            },
            "payments": {
                "id": (60, 70),
                "provider": (120, 220),
                "order_code": (180, 360),
                "amount": (70, 110),
                "currency": (60, 90),
                "paid_utc": (140, 190),
                "payment_ref": (160, 260),
            },
            "licenses": {
                "id": (60, 70),
                "uid": (160, 260),
                "license_rel_path": (200, 420),
                "edition": (70, 120),
                "issued_utc": (140, 190),
            },
        }

        # Яка колонка має бути Stretch (заповнює простір)
        stretch_priority: dict[str, tuple[str, ...]] = {
            "customers": ("email", "name", "note"),
            "orders": ("order_code", "payment_ref", "fingerprint"),
            "payments": ("order_code", "payment_ref", "provider"),
            "licenses": ("license_rel_path", "uid"),
        }

        def _do() -> None:
            if model is None:
                return

            hdr = tv.horizontalHeader()
            hdr.setStretchLastSection(False)

            tv.resizeColumnsToContents()

            # дефолтні межі, якщо колонка не описана
            default_min = 70
            default_max = 300

            limits = per_table_limits.get(table_key, {})
            field_index = getattr(model, "fieldIndex", None)

            # clamp по всіх колонках
            for c in range(model.columnCount()):
                col_min, col_max = default_min, default_max

                if callable(field_index):
                    # визначаємо field name для цієї колонки, якщо можемо
                    # QSqlTableModel має record()/fieldName,
                    # але простіше: пробігаємо limits
                    for fname, (mn, mx) in limits.items():
                        try:
                            idx = int(model.fieldIndex(fname))
                        except Exception:  # noqa
                            idx = -1
                        if idx == c:
                            col_min, col_max = mn, mx
                            break

                w = tv.columnWidth(c)
                if w < col_min:
                    tv.setColumnWidth(c, col_min)
                elif w > col_max:
                    tv.setColumnWidth(c, col_max)

            # Stretch колонка
            hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            stretch_col = -1

            if callable(field_index):
                for fname in stretch_priority.get(table_key, ()):
                    try:
                        idx = int(model.fieldIndex(fname))
                    except Exception:  # noqa
                        idx = -1
                    if idx >= 0:
                        stretch_col = idx
                        break

            if stretch_col < 0:
                stretch_col = 1 if model.columnCount() > 1 else 0

            hdr.setSectionResizeMode(stretch_col, QHeaderView.ResizeMode.Stretch)

        QTimer.singleShot(delay_ms, _do)

    @staticmethod
    def set_readonly_id_column(tv: QTableView, model: QSqlTableModel) -> None:
        col_id = model.fieldIndex("id")
        if col_id >= 0:
            tv.setItemDelegateForColumn(col_id, ReadOnlyDelegate())

    # Office кнопки (поки без складної логіки)
    # ---------------------------------------------------------------------
    def _on_cust_order_request(self) -> None:
        dlg = OrderRequestDialog(self, customer_id=0)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        email = getattr(dlg, "created_customer_email", "").strip().lower()
        cust_id = getattr(dlg, "created_customer_id", 0)
        order_uid = getattr(dlg, "created_order_uid", "").strip()

        if getattr(self, "cust", None) is not None:
            self.cust.refresh()

        if getattr(self, "ord", None) is not None:
            self.ord.apply_customer_filter(cust_id if cust_id > 0 else None)
            self.ord.refresh(select_order_uid=order_uid)
        else:
            self.model_orders.select()

        # ВАЖЛИВО: customer перевиділити ОСТАННІМ кроком
        if getattr(self, "cust", None) is not None and email:
            self.cust.select_row_by_email(email)

    def _on_lic_email(self):
        """Надіслати email із поточною ліцензією через preview + SMTP."""
        order_id = self._current_license_order_id()
        if not order_id:
            QMessageBox.warning(self, "Ліцензії", "Ліцензію не вибрано.")
            return

        license_uid = self._current_license_field("license_uid")
        license_rel_path = self._current_license_field("license_rel_path")
        edition = self._current_license_field("edition")

        if not license_uid:
            QMessageBox.warning(self, "Ліцензії", "У ліцензії відсутній UID.")
            return

        if not license_rel_path:
            QMessageBox.warning(self, "Ліцензії", "У ліцензії відсутній шлях до файлу.")
            return

        try:
            ctx = self._get_order_email_context(order_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self,
                "Ліцензії",
                f"Не вдалося отримати дані замовлення.\n\n{exc}",
            )
            return

        customer_email = ctx["customer_email"]
        customer_name = ctx["customer_name"]
        order_uid = ctx["order_uid"]
        app_version = ctx["app_version"]
        payment_ref = ctx["payment_ref"]
        fingerprint = ctx["fingerprint"]

        if not customer_email:
            QMessageBox.warning(self, "Ліцензії", "Email клієнта не знайдено.")
            return

        licenses_dir = get_licenses_dir()
        rel_name = license_rel_path.replace("\\", "/").split("/")[-1]
        license_path = licenses_dir / rel_name

        if not license_path.exists():
            QMessageBox.warning(
                self,
                "Ліцензії",
                f"Файл ліцензії не знайдено:\n{license_path}",
            )
            return

        language = self._ask_email_language()
        if language is None:
            return

        subject = build_license_email_subject(language, order_uid)
        office_email = OFFICE_EMAIL_INBOX

        body = build_license_email_body(
            language=language,
            customer_name=customer_name,
            office_email=office_email,
            order_uid=order_uid,
            edition=edition,
            app_version=app_version,
            payment_ref=payment_ref,
            fingerprint=fingerprint,
        )

        suffix = "uk" if language == "uk" else "en"
        body_file = licenses_dir / f"{license_uid}_email_{suffix}.txt"

        try:
            write_license_email_file(
                file_path=body_file,
                customer_email=customer_email,
                subject=subject,
                body=body,
            )
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Ліцензії",
                f"Не вдалося записати файл листа.\n\n{exc}",
            )
            return

        issue_result = SimpleNamespace(
            payload={
                "customer_email": customer_email,
                "order_id": order_uid,
                "license_uid": license_uid,
                "payment_ref": payment_ref,
            },
            email_subject=subject,
            license_path_abs=license_path,
            license_path_rel=license_rel_path,
            email_uk_path=licenses_dir / f"{license_uid}_email_uk.txt",
            email_en_path=licenses_dir / f"{license_uid}_email_en.txt",
        )

        # Щоб сервіс відкрив саме потрібний файл preview
        if language == "uk":
            issue_result.email_uk_path = body_file
        else:
            issue_result.email_en_path = body_file

        repo = DbRepo(get_office_dir())
        repo.ensure_db()

        sent = send_license_email_with_preview(
            parent=self,
            repo=repo,
            issue_result=issue_result,
            lang_text="uk" if language == "uk" else "en",
        )
        if sent:
            sent_utc = utc_now_str()

            try:
                repo.set_license_sent_utc(
                    license_uid=license_uid,
                    sent_utc=sent_utc,
                )
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(
                    self,
                    "Ліцензії",
                    f"Email відправлено, але не вдалося записати sent_utc.\n\n{exc}",
                )
            else:
                if getattr(self, "lic", None) is not None:
                    self.lic.refresh(select_license_uid=license_uid)
                elif getattr(self, "model_licenses", None) is not None:
                    self.model_licenses.select()

                QMessageBox.information(
                    self,
                    "Ліцензії",
                    "Email успішно відправлено через SMTP.",
                )

        # Далі тут підключимо preview + send service

    # ---------------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        try:
            if self._db is not None:
                self._db.close()
        finally:
            self._db = None
            QSqlDatabase.removeDatabase(self._conn_name)
            logger.debug("DB connection removed: %s", self._conn_name)

        super().closeEvent(event)

    # --------------------------------------
    # Зміна кольору активних офісних кнопок
    # --------------------------------------

    def sync_button_states(self) -> None:
        """Оновити dynamic property state для кнопок з role=office/business."""
        for b in self.findChildren(QPushButton):
            role = b.property("role")
            if role in ("office", "business"):
                self._set_button_state(b, b.isEnabled())

    def _apply_button_roles(self) -> None:
        """
        RoadMap39
        Розділення кнопок на ролі:
        office  – навігаційні
        business – бізнес дії
        """

        office_buttons = (
            "btnCustFirst",
            "btnCustPrev",
            "btnCustNext",
            "btnCustLast",
            "btnCustAdd",
            "btnCustDel",
            "btnCustSave",
            "btnCustCancel",
            "btnCustRefresh",
            "btnOrdFirst",
            "btnOrdPrev",
            "btnOrdNext",
            "btnOrdLast",
            "btnOrdAdd",
            "btnOrdDel",
            "btnOrdSave",
            "btnOrdCancel",
            "btnOrdRefresh",
            "btnPayFirst",
            "btnPayPrev",
            "btnPayNext",
            "btnPayLast",
            "btnPayAdd",
            "btnPayDel",
            "btnPaySave",
            "btnPayCancel",
            "btnPayRefresh",
            "btnLicFirst",
            "btnLicPrev",
            "btnLicNext",
            "btnLicLast",
            "btnLicAdd",
            "btnLicDel",
            "btnLicSave",
            "btnLicCancel",
            "btnLicRefresh",
        )

        business_buttons = (
            "btnCustOrderRequest",
            "btnOrdIssue",
            "btnPayAddDialog",
            "btnPayLinkToOrder",
            "btnLicEmail",
        )

        for name in office_buttons:
            b = getattr(self.ui, name, None)
            if isinstance(b, QPushButton):
                b.setProperty("role", "office")
                b.style().unpolish(b)
                b.style().polish(b)
                b.update()

        for name in business_buttons:
            b = getattr(self.ui, name, None)
            if isinstance(b, QPushButton):
                b.setProperty("role", "business")
                b.style().unpolish(b)
                b.style().polish(b)
                b.update()

        self.sync_button_states()

    # ------------------------------------------------------
    # -----------------helpers for email--------------------
    # ------------------------------------------------------
    def _current_license_field(self, field_name: str) -> str:
        """Повернути значення поля поточного рядка licenses."""
        model = getattr(self, "model_licenses", None)
        tv = getattr(self.ui, "tvLicenses", None)
        if model is None or tv is None:
            return ""

        idx = tv.currentIndex()
        if not idx.isValid():
            return ""

        row = idx.row()
        col = model.fieldIndex(field_name)
        if col < 0:
            return ""

        value = model.data(model.index(row, col))
        return str(value or "").strip()

    def _current_license_order_id(self) -> int | None:
        """Повернути order_id поточної ліцензії."""
        raw = self._current_license_field("order_id")
        if not raw:
            return None

        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    def _get_order_email_context(self, order_id: int) -> dict:
        """Зібрати email-контекст по order_id із orders + customers."""
        query = QSqlQuery(self._db)
        query.prepare(
            """
            SELECT
                o.order_uid,
                o.app_version,
                o.payment_ref,
                o.edition,
                o.fingerprint_sha256,
                c.email,
                c.name
            FROM orders o
            LEFT JOIN customers c ON c.id = o.customer_id
            WHERE o.id = ?
            LIMIT 1
            """
        )
        query.addBindValue(order_id)

        if not query.exec():
            raise RuntimeError(query.lastError().text())

        if not query.next():
            raise RuntimeError(f"Не знайдено order для id={order_id}")

        return {
            "order_uid": str(query.value(0) or "").strip(),
            "app_version": str(query.value(1) or "").strip(),
            "payment_ref": str(query.value(2) or "").strip(),
            "edition": str(query.value(3) or "").strip(),
            "fingerprint": str(query.value(4) or "").strip(),
            "customer_email": str(query.value(5) or "").strip(),
            "customer_name": str(query.value(6) or "").strip(),
        }

    def _ask_email_language(self) -> str | None:
        """Повернути 'uk', 'en' або None."""
        items = ["Українська", "English"]
        choice, ok = QInputDialog.getItem(
            self,
            "Мова листа",
            "Оберіть мову листа:",
            items,
            0,
            False,
        )
        if not ok:
            return None

        if choice == "Українська":
            return "uk"
        if choice == "English":
            return "en"
        return None
