# payment_add_dialog.py
# -*- coding: utf-8 -*-
"""
payment_add_dialog.py — новий діалог додавання платежу для DbGrid.

RoadMap43 / Patch 43.1:
- окремий новий діалог, старі payment_add* файли не чіпаємо;
- платіж може бути як прив’язаний до order_id, так і без order_id;
- на формі допускаємо UAH або USD;
- у БД надалі будемо писати amount тільки в USD;
- paid_utc працює в канонічному форматі YYYY-MM-DD HH:MM.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from PySide6.QtWidgets import QDialog, QMessageBox

from office.core.datetime_utils import (
    normalize_datetime_text,
    utc_now_str,
)
from office.ui.ui_payment_add_dialog import Ui_payment_add_dialog

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PaymentDialogResult:
    order_id: int | None
    provider: str
    external_ref: str
    amount_usd: Decimal
    currency_db: str
    paid_utc: str
    note: str


class PaymentAddDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        order_id: int | None = None,
        order_uid: str = "",
        external_ref: str = "",
    ) -> None:
        super().__init__(parent)

        self.ui = Ui_payment_add_dialog()
        self.ui.setupUi(self)

        self._order_id = order_id
        self._order_uid = (order_uid or "").strip()
        self._initial_external_ref = (external_ref or "").strip()
        self._result_data: PaymentDialogResult | None = None

        self._setup_ui()
        self._wire_ui()

        logger.debug(
            "PaymentAddDialog initialized: order_id=%s, order_uid=%s, external_ref=%s",
            self._order_id,
            self._order_uid,
            self._initial_external_ref,
        )

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    @property
    def result_data(self) -> PaymentDialogResult | None:
        return self._result_data

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        now_utc = utc_now_str()

        if self._order_id is not None:
            order_info = f"id={self._order_id}"
            if self._order_uid:
                order_info += f" | {self._order_uid}"
            self.ui.lblOrderInfoValue.setText(order_info)
        else:
            self.ui.lblOrderInfoValue.setText("Не прив’язано")

        self.ui.editPaidUtc.setText(now_utc)

        if self._initial_external_ref:
            self.ui.editExternalRef.setText(self._initial_external_ref)
        elif self._order_uid:
            self.ui.editExternalRef.setText(self._order_uid)

        self._update_fx_enabled()
        self._update_amount_preview()

    def _wire_ui(self) -> None:
        self.ui.comboCurrency.currentTextChanged.connect(self._on_currency_changed)
        self.ui.editAmount.textChanged.connect(self._update_amount_preview)
        self.ui.editFxRate.textChanged.connect(self._update_amount_preview)

        self.ui.btnOk.clicked.connect(self._on_ok)
        self.ui.btnCancel.clicked.connect(self.reject)

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def _on_currency_changed(self) -> None:
        self._update_fx_enabled()
        self._update_amount_preview()

    def _update_fx_enabled(self) -> None:
        currency = self._currency_text()
        is_uah = currency == "UAH"
        self.ui.editFxRate.setEnabled(is_uah)
        if not is_uah:
            self.ui.editFxRate.clear()

    def _update_amount_preview(self) -> None:
        try:
            amount_usd = self._calc_amount_usd()
            self.ui.lblAmountUsdValue.setText(f"{amount_usd:.2f} USD")
        except Exception:  # noqa
            self.ui.lblAmountUsdValue.setText("-")

    # ------------------------------------------------------------------
    # Parse / validate
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_text(text: str) -> str:
        return text.strip()

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
    def _parse_paid_utc(text: str) -> str:
        try:
            return normalize_datetime_text(text)
        except ValueError as exc:
            raise ValueError("Paid UTC має бути у форматі YYYY-MM-DD HH:MM.") from exc

    def _currency_text(self) -> str:
        return self.ui.comboCurrency.currentText().strip().upper()

    def _calc_amount_usd(self) -> Decimal:
        amount_raw = self._parse_decimal(
            self.ui.editAmount.text(),
            field_name="Operation Amount",
        )
        if amount_raw <= 0:
            raise ValueError("Operation Amount має бути > 0.")

        currency = self._currency_text()
        if currency not in ("UAH", "USD"):
            raise ValueError("Operation Currency має бути UAH або USD.")

        if currency == "USD":
            return amount_raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        fx_rate = self._parse_decimal(
            self.ui.editFxRate.text(),
            field_name="FX Rate",
        )
        if fx_rate <= 0:
            raise ValueError("FX Rate має бути > 0.")

        amount_usd = amount_raw / fx_rate
        return amount_usd.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _build_result(self) -> PaymentDialogResult:
        provider = self._clean_text(self.ui.comboBank.currentText())
        if not provider:
            raise ValueError("Bank обов’язковий.")

        external_ref = self._clean_text(self.ui.editExternalRef.text())
        if not external_ref:
            raise ValueError("External Ref обов’язковий.")

        paid_utc = self._parse_paid_utc(self.ui.editPaidUtc.text())
        amount_usd = self._calc_amount_usd()
        note = self.ui.editNote.toPlainText().strip()

        return PaymentDialogResult(
            order_id=self._order_id,
            provider=provider,
            external_ref=external_ref,
            amount_usd=amount_usd,
            currency_db="USD",
            paid_utc=paid_utc,
            note=note,
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_ok(self) -> None:
        try:
            self._result_data = self._build_result()
        except ValueError as exc:
            QMessageBox.warning(self, "Платіж", str(exc))
            return

        logger.debug("PaymentAddDialog accepted: %s", self._result_data)
        self.accept()
