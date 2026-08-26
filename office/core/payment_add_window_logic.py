# payment_add_window_logic.py
# -*- coding: utf-8 -*-
"""
payment_add_window_logic — діалог ручного додавання платежу в LGEOffice.

RoadMap48 canon:
- діалог має parent;
- order_id може бути порожнім -> у БД піде order_id=NULL;
- на формі можна вводити UAH або USD;
- у БД amount пишеться ТІЛЬКИ в USD (REAL);
- у БД currency пишеться ТІЛЬКИ 'USD';
- paid_utc зберігається тільки у форматі YYYY-MM-DD HH:MM;
- payment_ref та order_uid, за потреби, дублюються в note для зручності пошуку;
- перед збереженням показуємо попередження про можливий дублікат.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from PySide6.QtWidgets import QDialog, QMessageBox

from office.core.datetime_utils import normalize_datetime_text
from office.core.db_repo import DbRepo
from office.core.office_paths import get_office_dir
from office.core.payment_duplicate_confirm_logic import PaymentDuplicateConfirmDialog

try:
    from office.ui.ui_payment_add import Ui_payment_add  # type: ignore
except ImportError:  # pragma: no cover
    from office.ui.ui_payment_add import Ui_Dialog as Ui_payment_add  # type: ignore


logger = logging.getLogger(__name__)


class PaymentAddWindow(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.ui = Ui_payment_add()
        self.ui.setupUi(self)

        self._syncing = False

        self._repo = DbRepo(get_office_dir())
        self._repo.ensure_db()

        self._wire_ui()
        self._init_ui()

        logger.debug("PaymentAddWindow initialized. parent=%s", type(parent).__name__)

    # ------------------------------------------------------------------
    # UI / helpers
    # ------------------------------------------------------------------
    def _wire_ui(self) -> None:
        self.ui.btnOk.clicked.connect(self._on_save)
        self.ui.btnCancel.clicked.connect(self.reject)

        if hasattr(self.ui, "editOrderId") and hasattr(self.ui, "editPaymentRef"):
            self.ui.editOrderId.textChanged.connect(self._on_order_id_changed)

        if hasattr(self.ui, "comboCurrency"):
            self.ui.comboCurrency.currentIndexChanged.connect(self._on_currency_changed)

        if hasattr(self.ui, "editFxRate"):
            self.ui.editFxRate.textChanged.connect(self._recalc)

        if hasattr(self.ui, "edit_card_amount"):
            self.ui.edit_card_amount.textChanged.connect(self._recalc)

        if hasattr(self.ui, "edit_op_amount"):
            self.ui.edit_op_amount.textChanged.connect(self._recalc)

    def _init_ui(self) -> None:
        if hasattr(self.ui, "comboBank") and self.ui.comboBank.count() == 0:
            self.ui.comboBank.addItem("A-Банк", "A-Банк")
            self.ui.comboBank.addItem("ПриватБанк", "ПриватБанк")
            self.ui.comboBank.addItem("Mono", "Mono")

        if hasattr(self.ui, "comboCurrency") and self.ui.comboCurrency.count() == 0:
            self.ui.comboCurrency.addItem("UAH", "UAH")
            self.ui.comboCurrency.addItem("USD", "USD")

        if hasattr(self.ui, "editPaidUtc") and not self.ui.editPaidUtc.text().strip():
            self.ui.editPaidUtc.setText(datetime.now(UTC).strftime("%Y-%m-%d %H:%M"))

        if (
            hasattr(self.ui, "editPaidUtc")
            and not self.ui.editPaidUtc.placeholderText()
        ):
            self.ui.editPaidUtc.setPlaceholderText("2026-03-25 10:30")

        if hasattr(self.ui, "editFxRate") and not self.ui.editFxRate.placeholderText():
            self.ui.editFxRate.setPlaceholderText("43.0900 або 43.09")

        if (
            hasattr(self.ui, "edit_card_amount")
            and not self.ui.edit_card_amount.placeholderText()
        ):
            self.ui.edit_card_amount.setPlaceholderText("4300.00")

        if (
            hasattr(self.ui, "edit_op_amount")
            and not self.ui.edit_op_amount.placeholderText()
        ):
            self.ui.edit_op_amount.setPlaceholderText("100.00")

        self._on_currency_changed()

    @staticmethod
    def _get_text(value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    def _warn(self, text: str) -> None:
        QMessageBox.warning(self, "LGE Office", text)

    def _info(self, text: str) -> None:
        QMessageBox.information(self, "LGE Office", text)

    def _ask_yes_no(self, title: str, text: str) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        box.setDefaultButton(QMessageBox.StandardButton.No)

        btn_yes = box.button(QMessageBox.StandardButton.Yes)
        if btn_yes:
            btn_yes.setText("Так")

        btn_no = box.button(QMessageBox.StandardButton.No)
        if btn_no:
            btn_no.setText("Ні")

        return box.exec() == QMessageBox.StandardButton.Yes

    # ------------------------------------------------------------------
    # Parse / normalize
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_decimal(text: str, *, field_name: str) -> Decimal:
        s = text.strip().replace(" ", "").replace(",", ".")
        if not s:
            raise ValueError(f"Поле '{field_name}' обов’язкове.")

        try:
            value = Decimal(s)
        except InvalidOperation as exc:
            raise ValueError(f"Поле '{field_name}' має невірний формат.") from exc

        return value

    @staticmethod
    def _parse_amount_positive(text: str, *, field_name: str) -> Decimal:
        value = PaymentAddWindow._parse_decimal(text, field_name=field_name)
        if value <= 0:
            raise ValueError(f"Поле '{field_name}' має бути > 0.")
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _parse_fx_rate(text: str) -> Decimal:
        rate = PaymentAddWindow._parse_decimal(text, field_name="FX Rate")
        if rate <= 0:
            raise ValueError("FX Rate має бути > 0.")
        return rate.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _parse_paid_utc(text: str) -> str:
        try:
            return normalize_datetime_text(text)
        except ValueError as exc:
            raise ValueError(
                "Невірний формат дати. "
                "Приклад: 2026-03-25 10:30 або 25.03.2026 10:30."
            ) from exc

    def _currency_text(self) -> str:
        if not hasattr(self.ui, "comboCurrency"):
            return "UAH"
        return self._get_text(self.ui.comboCurrency.currentText()).upper() or "UAH"

    def _calc_amounts(self) -> tuple[str, Decimal, Decimal | None, Decimal | None]:
        """
        Повертає:
        - currency_input: 'UAH' або 'USD'
        - amount_usd: Decimal
        - amount_uah: Decimal | None
        - fx_rate: Decimal | None
        """
        currency_input = self._currency_text()
        if currency_input not in {"UAH", "USD"}:
            raise ValueError("Валюта має бути UAH або USD.")

        if currency_input == "USD":
            usd_text = (
                self._get_text(self.ui.edit_op_amount.text())
                if hasattr(self.ui, "edit_op_amount")
                else ""
            )
            amount_usd = self._parse_amount_positive(
                usd_text,
                field_name="Сума (дол)",
            )
            return currency_input, amount_usd, None, None

        uah_text = (
            self._get_text(self.ui.edit_card_amount.text())
            if hasattr(self.ui, "edit_card_amount")
            else ""
        )
        fx_text = (
            self._get_text(self.ui.editFxRate.text())
            if hasattr(self.ui, "editFxRate")
            else ""
        )

        amount_uah = self._parse_amount_positive(
            uah_text,
            field_name="Сума (грн)",
        )
        fx_rate = self._parse_fx_rate(fx_text)

        amount_usd = (amount_uah / fx_rate).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        if amount_usd <= 0:
            raise ValueError("Розрахована сума в USD має бути > 0.")

        return currency_input, amount_usd, amount_uah, fx_rate

    # ------------------------------------------------------------------
    # Recalc / currency UI
    # ------------------------------------------------------------------
    def _recalc(self) -> None:
        if self._syncing:
            return

        currency_input = self._currency_text()
        self._syncing = True
        try:
            if currency_input == "UAH":
                uah_text = (
                    self._get_text(self.ui.edit_card_amount.text())
                    if hasattr(self.ui, "edit_card_amount")
                    else ""
                )
                fx_text = (
                    self._get_text(self.ui.editFxRate.text())
                    if hasattr(self.ui, "editFxRate")
                    else ""
                )

                if not uah_text or not fx_text:
                    if hasattr(self.ui, "edit_op_amount"):
                        self.ui.edit_op_amount.clear()
                    return

                amount_uah = self._parse_amount_positive(
                    uah_text,
                    field_name="Сума (грн)",
                )
                fx_rate = self._parse_fx_rate(fx_text)
                amount_usd = (amount_uah / fx_rate).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )

                if hasattr(self.ui, "edit_op_amount"):
                    self.ui.edit_op_amount.setText(f"{amount_usd:.2f}")
                return

            usd_text = (
                self._get_text(self.ui.edit_op_amount.text())
                if hasattr(self.ui, "edit_op_amount")
                else ""
            )
            fx_text = (
                self._get_text(self.ui.editFxRate.text())
                if hasattr(self.ui, "editFxRate")
                else ""
            )

            if not usd_text:
                if hasattr(self.ui, "edit_card_amount"):
                    self.ui.edit_card_amount.clear()
                return

            amount_usd = self._parse_amount_positive(
                usd_text,
                field_name="Сума (дол)",
            )

            if not fx_text:
                if hasattr(self.ui, "edit_card_amount"):
                    self.ui.edit_card_amount.clear()
                return

            fx_rate = self._parse_fx_rate(fx_text)
            amount_uah = (amount_usd * fx_rate).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

            if hasattr(self.ui, "edit_card_amount"):
                self.ui.edit_card_amount.setText(f"{amount_uah:.2f}")
        except Exception:  # noqa
            if currency_input == "UAH":
                if hasattr(self.ui, "edit_op_amount"):
                    self.ui.edit_op_amount.clear()
            else:
                if hasattr(self.ui, "edit_card_amount"):
                    self.ui.edit_card_amount.clear()
        finally:
            self._syncing = False

    def _on_currency_changed(self) -> None:
        currency_input = self._currency_text()
        is_uah = currency_input == "UAH"
        is_usd = currency_input == "USD"

        self._syncing = True
        try:
            if hasattr(self.ui, "editFxRate"):
                self.ui.editFxRate.setEnabled(is_uah)

            if hasattr(self.ui, "edit_card_amount"):
                self.ui.edit_card_amount.setEnabled(is_uah)
                if is_usd:
                    self.ui.edit_card_amount.clear()

            if hasattr(self.ui, "edit_op_amount"):
                self.ui.edit_op_amount.setEnabled(is_usd)
                if is_uah:
                    self.ui.edit_op_amount.clear()
        finally:
            self._syncing = False

        self._recalc()

    # ------------------------------------------------------------------
    # Duplicate checks
    # ------------------------------------------------------------------
    def _find_similar_payments(
        self,
        *,
        bank: str,
        amount_usd: Decimal,
        paid_utc: str,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        """
        Евристика дубля:
        provider + amount(USD) + дата YYYY-MM-DD.
        """
        sql = """
        SELECT
            id,
            order_id,
            provider,
            external_ref,
            amount,
            currency,
            paid_utc,
            note
        FROM payments
        WHERE provider = ?
          AND currency = 'USD'
          AND amount = ?
          AND substr(paid_utc, 1, 10) = substr(?, 1, 10)
        ORDER BY id DESC
        LIMIT ?
        """

        with sqlite3.connect(self._repo.db_path) as conn:
            rows = conn.execute(
                sql,
                (
                    bank,
                    float(amount_usd),
                    paid_utc,
                    int(limit),
                ),
            ).fetchall()

        result: list[dict[str, object]] = []
        for row in rows:
            result.append(
                {
                    "id": row[0],
                    "order_id": row[1],
                    "provider": row[2],
                    "external_ref": row[3],
                    "amount": row[4],
                    "currency": row[5],
                    "paid_utc": row[6],
                    "note": row[7],
                }
            )
        return result

    def _find_similar_by_note(
        self,
        *,
        bank: str,
        order_uid: str,
        payment_ref: str,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        patterns: list[str] = []
        if order_uid.strip():
            patterns.append(f"%order_id={order_uid.strip()}%")
        if payment_ref.strip():
            patterns.append(f"%ref={payment_ref.strip()}%")

        if not patterns:
            return []

        where_parts: list[str] = []
        params: list[object] = [bank]

        for pattern in patterns:
            where_parts.append("external_ref LIKE ?")
            params.append(pattern)
            where_parts.append("note LIKE ?")
            params.append(pattern)

        sql = f"""
        SELECT
            id,
            order_id,
            provider,
            external_ref,
            amount,
            currency,
            paid_utc,
            note
        FROM payments
        WHERE provider = ?
          AND ({' OR '.join(where_parts)})
        ORDER BY id DESC
        LIMIT ?
        """

        params.append(int(limit))

        with sqlite3.connect(self._repo.db_path) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()

        result: list[dict[str, object]] = []
        for row in rows:
            result.append(
                {
                    "id": row[0],
                    "order_id": row[1],
                    "provider": row[2],
                    "external_ref": row[3],
                    "amount": row[4],
                    "currency": row[5],
                    "paid_utc": row[6],
                    "note": row[7],
                }
            )
        return result

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _on_save(self) -> None:
        try:
            bank = (
                self._get_text(self.ui.comboBank.currentText())
                if hasattr(self.ui, "comboBank")
                else ""
            )
            if not bank:
                self._warn("Банк обов’язковий.")
                return

            order_uid = (
                self._get_text(self.ui.editOrderId.text())
                if hasattr(self.ui, "editOrderId")
                else ""
            )
            order_row_id = self._repo.get_order_row_id(order_uid) if order_uid else None

            payment_ref = (
                self._get_text(self.ui.editPaymentRef.text())
                if hasattr(self.ui, "editPaymentRef")
                else ""
            )

            note_user = (
                self._get_text(self.ui.editNote.toPlainText())
                if hasattr(self.ui, "editNote")
                else ""
            )

            paid_utc_text = (
                self._get_text(self.ui.editPaidUtc.text())
                if hasattr(self.ui, "editPaidUtc")
                else ""
            )
            paid_utc_db = self._parse_paid_utc(paid_utc_text)

            (
                currency_input,
                amount_usd,
                amount_uah,
                fx_rate,
            ) = self._calc_amounts()

            meta_bits: list[str] = []
            if payment_ref:
                meta_bits.append(f"ref={payment_ref}")
            if order_uid:
                meta_bits.append(f"order_id={order_uid}")

            note_db = note_user.strip()
            if meta_bits:
                meta = "; ".join(meta_bits)
                note_db = (meta + ("\n" + note_db if note_db else "")).strip()

            similar_1 = self._find_similar_payments(
                bank=bank,
                amount_usd=amount_usd,
                paid_utc=paid_utc_db,
            )

            similar_2 = self._find_similar_by_note(
                bank=bank,
                order_uid=order_uid,
                payment_ref=payment_ref,
            )

            merged: list[dict[str, object]] = []
            seen_ids: set[int] = set()
            for item in similar_2 + similar_1:
                payment_id = int(item.get("id", 0) or 0)
                if payment_id and payment_id not in seen_ids:
                    seen_ids.add(payment_id)
                    merged.append(item)

            if merged:
                dlg = PaymentDuplicateConfirmDialog(items=merged)
                dlg.exec()
                if not dlg.accepted_by_user:
                    logger.debug("Payment save cancelled by duplicate confirm dialog.")
                    return

            payment_id = self._repo.insert_payment(
                provider=bank,
                external_ref=payment_ref,
                amount=float(amount_usd),
                currency="USD",
                paid_utc=paid_utc_db,
                note=note_db,
                order_id=order_row_id,
            )

            logger.debug(
                "Payment saved: id=%s, order_row_id=%s, order_uid=%s, "
                "currency_input=%s, amount_usd=%s, paid_utc=%s",
                payment_id,
                order_row_id,
                order_uid,
                currency_input,
                amount_usd,
                paid_utc_db,
            )

            if currency_input == "USD":
                message = (
                    f"Платіж збережено. ID: {payment_id}\n"
                    f"Записано в БД: {amount_usd:.2f} USD"
                )
            else:
                fx_text = f"{fx_rate:.4f}" if fx_rate is not None else "-"
                uah_text = f"{amount_uah:.2f}" if amount_uah is not None else "-"
                message = (
                    f"Платіж збережено. ID: {payment_id}\n"
                    f"Введено: {uah_text} UAH\n"
                    f"Записано в БД: {amount_usd:.2f} USD\n"
                    f"Курс: {fx_text}"
                )

            self._info(message)
            self.accept()

        except ValueError as exc:
            self._warn(str(exc))
        except sqlite3.Error as exc:
            logger.exception("SQLite error in PaymentAddWindow")
            self._warn(f"Помилка БД: {exc}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error in PaymentAddWindow")
            self._warn(f"Помилка: {exc}")

    def _on_order_id_changed(self, text: str) -> None:
        order_uid = text.strip()
        if not order_uid:
            return

        if (
            hasattr(self.ui, "editPaymentRef")
            and not self.ui.editPaymentRef.text().strip()
        ):
            self.ui.editPaymentRef.setText(f"LGE {order_uid}")
