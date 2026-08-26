# payment_duplicate_confirm_logic.py
# -*- coding: utf-8 -*-
"""
payment_duplicate_confirm_logic — підтвердження додавання схожого платежу.

Показує реквізити знайдених схожих платежів і дає вибір:
- Додати ще раз
- Скасувати
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Type

from PySide6.QtWidgets import QDialog


def _load_ui_class() -> Type[Any]:
    """
    Завантажує перший знайдений клас Ui_* із модуля ui_payment_duplicate_confirm.py
    (назва залежить від objectName у .ui, тому не хардкодимо).
    """
    mod = __import__(
        "office.ui.ui_payment_duplicate_confirm",
        fromlist=["*"],
    )
    for name in dir(mod):
        if name.startswith("Ui_"):
            return getattr(mod, name)
    raise ImportError("No Ui_* class found in ui_payment_duplicate_confirm.py")


UiPaymentDuplicateConfirm = _load_ui_class()


def _text(x: Any) -> str:
    return str(x).strip() if x is not None else ""


def _money_from_minor(minor: Any) -> str:
    try:
        return f"{(Decimal(int(minor)) / Decimal(100)):.2f}"
    except Exception:  # noqa
        return "?"


def _rate_from_x10000(x10000: Any) -> str:
    try:
        return f"{(Decimal(int(x10000)) / Decimal(10000)):.4f}"
    except Exception:  # noqa

        return "?"


class PaymentDuplicateConfirmDialog(QDialog):
    def __init__(self, *, items: list[dict[str, Any]]) -> None:
        super().__init__()
        self.ui = UiPaymentDuplicateConfirm()
        self.ui.setupUi(self)

        self._accepted = False

        self.ui.plainDetails.setReadOnly(True)
        self.ui.plainDetails.setPlainText(self._format_items(items))

        self.ui.btnAddAnyway.clicked.connect(self._on_add)
        self.ui.btnCancel.clicked.connect(self._on_cancel)

    def _on_add(self) -> None:
        self._accepted = True
        self.accept()

    def _on_cancel(self) -> None:
        self._accepted = False
        self.reject()

    @property
    def accepted_by_user(self) -> bool:
        return self._accepted

    @staticmethod
    def _format_items(items: list[dict[str, Any]]) -> str:
        lines: list[str] = []

        for it in items:
            pid = it.get("id")

            # Нова схема: provider/external_ref/amount/currency/paid_utc/note
            if "provider" in it or "paid_utc" in it or "external_ref" in it:
                provider = _text(it.get("provider"))
                external_ref = _text(it.get("external_ref"))
                paid_utc = _text(it.get("paid_utc"))
                amount = _text(it.get("amount"))
                currency = _text(it.get("currency"))
                note = _text(it.get("note"))

                block = [
                    "------------------------------",
                    f"ID: {pid}",
                    f"Провайдер: {provider}",
                    f"External ref: {external_ref}",
                    f"Дата/час: {paid_utc}",
                    f"Сума: {amount} {currency}".rstrip(),
                ]
                if note:
                    block.append(f"Note: {note}")

                lines.append("\n".join(block))
                continue

            # Стара схема (якщо десь залишилась стара БД/дамп)
            bank = _text(it.get("bank"))
            event_local = _text(it.get("event_local"))
            op_amount = _money_from_minor(it.get("op_amount_minor"))
            op_cur = _text(it.get("op_currency"))
            card_amount = _money_from_minor(it.get("card_amount_minor"))
            card_cur = _text(it.get("card_currency"))
            fx = _rate_from_x10000(it.get("fx_rate_x10000"))
            note = _text(it.get("note"))

            block = [
                "------------------------------",
                f"ID: {pid}",
                f"Банк: {bank}",
                f"Дата/час: {event_local}",
                f"Операція: {op_amount} {op_cur}".rstrip(),
                f"Картка: {card_amount} {card_cur}".rstrip(),
                f"Курс: {fx}",
            ]
            if note:
                block.append(f"Note: {note}")

            lines.append("\n".join(block))

        return ("\n\n".join(lines)).strip() + ("\n" if lines else "")
