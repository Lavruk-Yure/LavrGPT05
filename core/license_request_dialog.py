# license_request_dialog.py
# -*- coding: utf-8 -*-
"""
LicenseRequestDialog — діалог отримання ліцензії (RoadMap22).

Правила:
- У .ui тільки ключі в квадратних дужках.
- Переклад UI робить core.ui_translator.UITranslator.
- У licenses/requests має бути лише 1 активна заявка:
  перед генерацією показуємо overwrite-діалог.
- Кнопки:
  - Generate request — формує файли
  - Copy email text — копіює в буфер
  - Send email — відкриває поштовий клієнт (mailto), без авто-відправки
"""

from __future__ import annotations

import json
import logging
import secrets
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core import app_meta, session_state
from core.app_meta import calculate_license_price
from core.app_paths import BASE_DIR
from core.license_manager import LicenseManager
from core.ui_translator import UITranslator
from ui.ui_license_request_dialog import Ui_LicenseRequestDialog

DEBUG_LICENSE_REQUEST = False

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.NullHandler())


def log_cp(name: str, **kw: Any) -> None:
    """Debug checkpoints (вмикається DEBUG_LICENSE_REQUEST)."""
    if not DEBUG_LICENSE_REQUEST:
        return
    msg = f"[LICENSE_REQUEST:{name}] " + ", ".join(f"{k}={v!r}" for k, v in kw.items())
    print(msg)


def _now_utc_iso() -> str:
    """Поточний UTC у компактному ISO без мікросекунд."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _make_order_id() -> str:
    """Сформувати ORDER_ID у форматі LGE-YYYYMMDD-HHMM-XXXX."""
    local = datetime.now().strftime("%Y%m%d-%H%M")
    tail = secrets.token_hex(2).upper()
    return f"LGE-{local}-{tail}"


def _ensure_requests_dir() -> Path:
    """Створити каталог licenses/requests за потреби."""
    path_requests = BASE_DIR / "licenses" / "requests"
    path_requests.mkdir(parents=True, exist_ok=True)
    return path_requests


def _safe_str(value: object) -> str:
    """Безпечно привести значення до обрізаного рядка."""
    return value.strip() if isinstance(value, str) else ""


class LicenseOverwriteDialog(QDialog):
    """
    Діалог підтвердження overwrite.

    Перший пріоритет — UI-версія
    (ui/ui_license_request_overwrite_dialog.py).
    Якщо її немає — робимо мінімальний fallback QDialog програмно.
    """

    def __init__(self, parent: QWidget | None, lang_mgr) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._lang_mgr = lang_mgr
        self._chk_also_delete_payment = None

        ui_loaded = self._try_setup_ui()
        if not ui_loaded:
            self._setup_fallback_ui()

        UITranslator(self._lang_mgr).apply(self)

    def _try_setup_ui(self) -> bool:
        """Спробувати підняти готовий .ui-згенерований діалог."""
        try:
            from ui.ui_license_request_overwrite_dialog import (  # type: ignore
                Ui_LicenseOverwriteDialog,
            )
        except Exception:  # noqa
            return False

        overwrite_ui = Ui_LicenseOverwriteDialog()
        overwrite_ui.setupUi(self)

        self._chk_also_delete_payment = getattr(
            overwrite_ui, "chkAlsoDeletePayment", None
        )

        btn_overwrite = getattr(overwrite_ui, "btnOverwrite", None)
        btn_cancel = getattr(overwrite_ui, "btnCancel", None)

        if btn_overwrite is not None:
            btn_overwrite.clicked.connect(self.accept)
        if btn_cancel is not None:
            btn_cancel.clicked.connect(self.reject)

        return True

    def _setup_fallback_ui(self) -> None:
        """Fallback-версія діалогу без залежності від ui_*.py."""
        self.setObjectName("LicenseOverwriteDialog")

        layout = QVBoxLayout(self)

        lbl_header = QLabel("[LicenseOverwriteDialog.lblHeader]")
        lbl_header.setObjectName("lblHeader")
        layout.addWidget(lbl_header)

        lbl_details = QLabel("[LicenseOverwriteDialog.lblDetails]")
        lbl_details.setObjectName("lblDetails")
        lbl_details.setWordWrap(True)
        layout.addWidget(lbl_details)

        from PySide6.QtWidgets import QCheckBox

        chk_also_delete_payment = QCheckBox(
            "[LicenseOverwriteDialog.chkAlsoDeletePayment]"
        )
        chk_also_delete_payment.setObjectName("chkAlsoDeletePayment")
        chk_also_delete_payment.setChecked(True)
        self._chk_also_delete_payment = chk_also_delete_payment
        layout.addWidget(chk_also_delete_payment)

        from PySide6.QtWidgets import QHBoxLayout, QSpacerItem

        row = QHBoxLayout()
        row.addItem(QSpacerItem(10, 10))

        btn_overwrite = QPushButton("[LicenseOverwriteDialog.btnOverwrite]")
        btn_overwrite.setObjectName("btnOverwrite")
        btn_overwrite.clicked.connect(self.accept)
        row.addWidget(btn_overwrite)

        btn_cancel = QPushButton("[LicenseOverwriteDialog.btnCancel]")
        btn_cancel.setObjectName("btnCancel")
        btn_cancel.clicked.connect(self.reject)
        row.addWidget(btn_cancel)

        layout.addLayout(row)

    def also_delete_payment(self) -> bool:
        """Чи треба також видаляти payment_instructions_*.txt."""
        chk = self._chk_also_delete_payment
        return bool(getattr(chk, "isChecked", lambda: True)())


class LicenseRequestDialog(QDialog):
    """Основний діалог генерації license request та інструкції оплати."""

    def __init__(self, parent: QWidget | None, lang_mgr) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._lang_mgr = lang_mgr

        self.ui = Ui_LicenseRequestDialog()
        self.ui.setupUi(self)

        UITranslator(self._lang_mgr).apply(self)

        self.ui.comboEdition.blockSignals(True)
        try:
            self.ui.comboEdition.clear()
            self.ui.comboEdition.addItem("PRO", "PRO")
            self.ui.comboEdition.addItem("PRO_PLUS", "PRO_PLUS")
            self.ui.comboEdition.setCurrentIndex(0)
        finally:
            self.ui.comboEdition.blockSignals(False)

        self.ui.comboEdition.currentIndexChanged.connect(self._sync_price)
        self.ui.btnGenerate.clicked.connect(self._on_generate)
        self.ui.btnCopyEmail.clicked.connect(self._on_copy_email)
        self.ui.btnClose.clicked.connect(self.close)

        if hasattr(self.ui, "btnSendEmail"):
            self.ui.btnSendEmail.clicked.connect(self._on_send_email)

        self._last_order_id: str | None = None
        self._last_subject: str = ""
        self._last_body: str = ""

        self._prefill_customer_email()
        self._sync_price()

    # --------------------------
    # Helpers
    # --------------------------

    def _set_status(self, key: str) -> None:
        """Поставити статусний текст у lblStatus."""
        if hasattr(self.ui, "lblStatus"):
            self.ui.lblStatus.setText(self._lang_mgr.tr(key, key))

    def _prefill_customer_email(self) -> None:
        """Підставити email з поточного config, якщо поле ще порожнє."""
        if session_state.CURRENT_CONFIG is None:
            return
        try:
            conf = session_state.CURRENT_CONFIG.to_dict()
        except Exception:  # noqa
            return
        email = conf.get("email")
        email = email.strip() if isinstance(email, str) else ""
        if email and not self.ui.editEmail.text().strip():
            self.ui.editEmail.setText(email)

    def _current_license_edition(self) -> str:  # noqa
        """Повернути поточну редакцію ліцензії з конфіга."""
        if session_state.CURRENT_CONFIG is None:
            return "free"

        try:
            conf = session_state.CURRENT_CONFIG.to_dict()
        except Exception:  # noqa
            return "free"

        lic = conf.get("license", {}) if isinstance(conf, dict) else {}
        return str(lic.get("edition") or "free").lower()

    def _sync_price(self) -> None:
        """Оновити підпис ціни відповідно до вибраної редакції."""
        target_edition = str(self.ui.comboEdition.currentData() or "PRO")
        current_edition = self._current_license_edition()

        price = calculate_license_price(current_edition, target_edition)
        currency = str(app_meta.CURRENCY)

        self.ui.lblPriceValue.setText(f"{price:.2f} {currency}")

    def _validate(self) -> bool:
        """Мінімальна валідація перед генерацією заявки."""
        email = self.ui.editEmail.text().strip()
        if not email:
            self._set_status("LicenseRequestDialog.msgEmailRequired")
            return False

        if not self.ui.chkConsent.isChecked():
            self._set_status("LicenseRequestDialog.msgConsentRequired")
            return False

        try:
            fingerprint_hash = LicenseManager.compute_machine_id()
        except Exception:  # noqa
            logger.exception("Failed to compute fingerprint_hash (machine_id)")
            fingerprint_hash = ""

        if not fingerprint_hash.strip():
            self._set_status("LicenseRequestDialog.msgFingerprintRequired")
            return False

        return True

    @staticmethod
    def _find_existing_requests(req_dir: Path) -> tuple[list[Path], list[Path]]:
        """Знайти request_*.json і payment_instructions_*.txt."""
        req_json = sorted(req_dir.glob("request_*.json"))
        pay_txt = sorted(req_dir.glob("payment_instructions_*.txt"))
        return req_json, pay_txt

    def _confirm_overwrite(self, req_dir: Path) -> bool:
        """Показати overwrite-діалог. True — дозволено перезапис."""
        dlg = LicenseOverwriteDialog(self, self._lang_mgr)
        dlg.setWindowTitle(
            self._lang_mgr.tr(
                "LicenseOverwriteDialog.windowTitle", "Request already exists"
            )
        )
        result = dlg.exec()
        if result != QDialog.DialogCode.Accepted:
            return False

        req_json, pay_txt = self._find_existing_requests(req_dir)

        for path_item in req_json:
            try:
                path_item.unlink(missing_ok=True)
            except Exception:  # noqa
                logger.exception("Failed to delete %s", path_item)

        if dlg.also_delete_payment():
            for path_item in pay_txt:
                try:
                    path_item.unlink(missing_ok=True)
                except Exception:  # noqa
                    logger.exception("Failed to delete %s", path_item)

        return True

    def _make_request_payload(self, order_id: str) -> dict:
        """Зібрати payload для request_*.json."""
        edition = str(self.ui.comboEdition.currentData() or "PRO")
        email = self.ui.editEmail.text().strip()

        current_edition = self._current_license_edition()
        amount = calculate_license_price(current_edition, edition)

        currency = str(app_meta.CURRENCY)
        version = str(app_meta.VERSION)

        try:
            fingerprint_hash = LicenseManager.compute_machine_id().strip()
            if fingerprint_hash.upper().startswith("SHA256:"):
                fingerprint_hash = fingerprint_hash.split(":", 1)[1].strip()
        except Exception:  # noqa
            logger.exception("Failed to compute fingerprint_hash (machine_id)")
            fingerprint_hash = ""

        return {
            "schema": "LGE_LICENSE_REQUEST_V1",
            "order_id": order_id,
            "created_utc": _now_utc_iso(),
            "app": str(app_meta.APP_NAME),
            "version": version,
            "requested_edition": edition,
            "pricing": {
                "currency": currency,
                "amount": float(amount),
                "current_edition": current_edition,
                "target_edition": edition,
                "is_upgrade": current_edition == "pro" and edition == "PRO_PLUS",
            },
            "customer": {
                "email": email,
                "display_name": "",
            },
            "device": {
                "fingerprint_hash": fingerprint_hash,
                "os": "Windows",
            },
            "notes": {
                "ui_language": _safe_str(
                    getattr(self._lang_mgr, "current_language", "")
                ),
                "comment": "Generated by LGE",
            },
        }

    def _make_payment_text(self, order_id: str, payload: dict) -> str:
        """
        Побудувати інструкцію оплати:
        поточна мова + EN.
        """
        lang_cur = _safe_str(getattr(self._lang_mgr, "current_language", "")) or "en"
        lang_en = "en"

        edition = str(payload.get("requested_edition", "PRO"))
        price = float(payload.get("pricing", {}).get("amount", 0.0))
        currency = str(payload.get("pricing", {}).get("currency", "USD"))
        version = str(payload.get("version", "0.0.0"))

        seller_name = str(app_meta.SELLER_NAME)
        seller_country = str(app_meta.SELLER_COUNTRY)
        seller_email = str(app_meta.SELLER_SALES_EMAIL)
        pay_method = str(app_meta.PAYMENT_METHOD_TITLE)
        pay_recipient = str(app_meta.PAYMENT_RECIPIENT)
        pay_card_iban = str(app_meta.PAYMENT_CARD_OR_IBAN)
        pay_bank = str(app_meta.PAYMENT_BANK_NAME)
        pay_swift = str(app_meta.PAYMENT_SWIFT)
        ref_prefix = str(app_meta.PAYMENT_REFERENCE_PREFIX)

        ref = f"{ref_prefix} {order_id}"
        date_utc = _now_utc_iso()

        strings = getattr(self._lang_mgr, "_strings", {}) or {}
        fallback = getattr(self._lang_mgr, "_fallback", {}) or {}

        def resolve_for(lang_code: str, key: str) -> str:
            entry = strings.get(key)
            if isinstance(entry, dict):
                value = entry.get(lang_code)
                if isinstance(value, str) and value.strip():
                    return value

            fb = fallback.get(key)
            if isinstance(fb, dict):
                value = fb.get(lang_code)
                if isinstance(value, str) and value.strip():
                    return value

                value_en = fb.get("en")
                if isinstance(value_en, str) and value_en.strip():
                    return value_en

            return key

        def block(lang_code: str) -> str:
            def r(key: str) -> str:
                return resolve_for(lang_code, key)

            title = r("LicenseRequestDialog.payTitle")
            k_order = r("LicenseRequestDialog.payOrderId")
            k_date = r("LicenseRequestDialog.payDateUtc")
            k_product = r("LicenseRequestDialog.payProduct")
            k_license = r("LicenseRequestDialog.payLicense")
            k_amount = r("LicenseRequestDialog.payAmount")
            k_method = r("LicenseRequestDialog.payMethod")
            k_seller = r("LicenseRequestDialog.paySellerDetails")
            k_recipient = r("LicenseRequestDialog.payRecipient")
            k_card = r("LicenseRequestDialog.payCardIban")
            k_bank = r("LicenseRequestDialog.payBank")
            k_country = r("LicenseRequestDialog.payCountry")
            k_contact = r("LicenseRequestDialog.payContact")
            k_ref_title = r("LicenseRequestDialog.payReferenceTitle")
            k_after = r("LicenseRequestDialog.payAfterPayment")
            k_after_1 = r("LicenseRequestDialog.payAfterPaymentLine1")
            k_after_2 = r("LicenseRequestDialog.payAfterPaymentLine2")
            k_terms = r("LicenseRequestDialog.payTerms")
            k_terms_1 = r("LicenseRequestDialog.payTermsLine1")
            k_terms_2 = r("LicenseRequestDialog.payTermsLine2")

            lines = [
                "========================",
                f"LGE — {title}",
                f"{k_order} {order_id}",
                f"{k_date} {date_utc}",
                "========================",
                "",
                f"1) {k_product} LGE v{version}",
                f"2) {k_license} {edition}",
                f"3) {k_amount} {price:.2f} {currency}",
                f"4) {k_method} {pay_method}",
                "",
                f"{k_seller}",
                f"- {k_recipient} {pay_recipient or seller_name}",
                f"- {k_card} {pay_card_iban}",
                f"- {k_bank} {pay_bank}",
            ]

            if pay_swift:
                lines.append(f"- SWIFT: {pay_swift}")
            if seller_country:
                lines.append(f"- {k_country} {seller_country}")
            if seller_email:
                lines.append(f"- {k_contact} {seller_email}")

            lines += [
                "",
                f"{k_ref_title}",
                ref,
                "",
                f"{k_after}",
                f"- {k_after_1} LGE License Request {order_id}",
                f"- {k_after_2}",
                "",
                f"{k_terms}",
                f"- {k_terms_1}",
                f"- {k_terms_2}",
            ]
            return "\n".join(lines)

        cur_block = block(lang_cur)
        if lang_cur == lang_en:
            return cur_block
        return cur_block + "\n\n\n" + block(lang_en)

    @staticmethod
    def _make_email(
        *,
        order_id: str,
        edition: str,
        customer_email: str,
        app_version: str,
        fingerprint: str,
        recipient_email: str,
        price: float,
        currency: str,
        is_upgrade: bool,
        lang: str,
    ) -> tuple[str, str]:
        """Побудувати subject/body для листа продавцю."""
        is_uk = (lang or "").lower().startswith("uk")

        subject = f"LGE License Request {order_id}"

        license_title = edition
        if is_upgrade:
            license_title = "PRO → PRO_PLUS (upgrade)"

        if is_uk:
            body = (
                "Доброго дня,\n\n"
                "Будь ласка, видайте ліцензію для LGE.\n\n"
                f"Email отримувача: {recipient_email}\n\n"
                f"ORDER_ID: {order_id}\n"
                f"Редакція: {license_title}\n"
                f"Ціна: {price:.2f} {currency}\n"
                f"Email клієнта: {customer_email}\n"
                f"Версія програми: {app_version}\n\n"
                "Платіжне посилання:\n"
                f"LGE {order_id}\n\n"
                f"Fingerprint: {fingerprint}\n\n"
                "Дякую."
            )
            return subject, body

        body = (
            "Hello,\n\n"
            "Please issue a license for LGE.\n\n"
            f"Recipient email: {recipient_email}\n\n"
            f"ORDER_ID: {order_id}\n"
            f"Edition: {license_title}\n"
            f"Price: {price:.2f} {currency}\n"
            f"Customer email: {customer_email}\n"
            f"App version: {app_version}\n\n"
            "Payment reference:\n"
            f"LGE {order_id}\n\n"
            f"Fingerprint: {fingerprint}\n\n"
            "Thank you."
        )
        return subject, body

    @staticmethod
    def _mailto_open(to_email: str, subject: str, body: str) -> bool:
        """Відкрити mailto: у системному поштовому клієнті."""
        to_email = _safe_str(to_email)
        subject = _safe_str(subject)
        body = body if isinstance(body, str) else ""

        if not to_email or not subject:
            return False

        q_subject = urllib.parse.quote(subject)
        q_body = urllib.parse.quote(body)
        url = f"mailto:{to_email}?subject={q_subject}&body={q_body}"
        return QDesktopServices.openUrl(QUrl(url))

    # --------------------------
    # Actions
    # --------------------------
    def _on_generate(self) -> None:
        """Згенерувати request JSON та payment instructions."""
        if not self._validate():
            return

        if session_state.CURRENT_CONFIG is None:
            self._set_status("LicenseRequestDialog.msgGenerateFirst")
            return

        req_dir = _ensure_requests_dir()
        req_json, _pay_txt = LicenseRequestDialog._find_existing_requests(req_dir)

        if req_json:
            if not self._confirm_overwrite(req_dir):
                return

        order_id = _make_order_id()
        payload = self._make_request_payload(order_id)

        request_path = req_dir / f"request_{order_id}.json"
        payment_path = req_dir / f"payment_instructions_{order_id}.txt"

        request_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        payment_text = self._make_payment_text(order_id, payload)
        payment_path.write_text(payment_text, encoding="utf-8")

        lang = _safe_str(getattr(self._lang_mgr, "current_language", "")) or "en"

        edition = str(payload.get("requested_edition", "PRO"))
        customer_email = str(payload.get("customer", {}).get("email", ""))
        app_version = str(payload.get("version", "0.0.0"))
        fingerprint = str(payload.get("device", {}).get("fingerprint_hash", ""))
        recipient_email = _safe_str(app_meta.SELLER_SALES_EMAIL)
        pricing = payload.get("pricing", {})
        price = float(pricing.get("amount", 0.0))
        currency = str(pricing.get("currency", app_meta.CURRENCY))
        is_upgrade = bool(pricing.get("is_upgrade", False))

        subject, body = self._make_email(
            order_id=order_id,
            edition=edition,
            customer_email=customer_email,
            app_version=app_version,
            fingerprint=fingerprint,
            recipient_email=recipient_email,
            price=price,
            currency=currency,
            is_upgrade=is_upgrade,
            lang=lang,
        )

        self._last_order_id = order_id
        self._last_subject = subject
        self._last_body = body

        self._set_status("LicenseRequestDialog.msgRequestGenerated")
        log_cp(
            "generated",
            order_id=order_id,
            request=str(request_path),
            payment=str(payment_path),
        )

    def _on_copy_email(self) -> None:
        """Скопіювати email-текст у буфер."""
        if not self._last_order_id or not self._last_subject:
            self._set_status("LicenseRequestDialog.msgGenerateFirst")
            return

        text = f"Subject: {self._last_subject}\n\n{self._last_body}"
        QApplication.clipboard().setText(text)
        self._set_status("LicenseRequestDialog.msgEmailCopied")

    def _on_send_email(self) -> None:
        """Відкрити системний mailto для підготовленого листа."""
        if not self._last_order_id or not self._last_subject:
            self._set_status("LicenseRequestDialog.msgGenerateFirst")
            return

        seller_to = _safe_str(app_meta.SELLER_SALES_EMAIL)
        opened = self._mailto_open(seller_to, self._last_subject, self._last_body)

        if opened:
            self._set_status("LicenseRequestDialog.msgEmailCopiedAndOpened")
        else:
            self._set_status("LicenseRequestDialog.msgEmailCopied")
