# quick_issue_dialog.py
# -*- coding: utf-8 -*-
"""
QuickIssueDialog — діалог швидкої видачі ліцензії.

RoadMap46 / Patch 46.5:
- значення за замовчуванням
- автопошук клієнта по email
- валідація форми
- без запису в БД (тільки підготовка)
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from PySide6.QtWidgets import QDialog, QMessageBox

from office.core import session_state
from office.core.datetime_utils import normalize_datetime_text, utc_now_str
from office.core.db_repo import DbRepo
from office.core.email_send_service import send_license_email_with_preview
from office.core.license_issuer import issue_license_files
from office.core.mail_settings import OFFICE_EMAIL_INBOX
from office.core.office_paths import get_office_dir
from office.core.pricing import get_price_usd
from office.ui.ui_quick_issue_dialog import Ui_QuickIssueDialog

logger = logging.getLogger(__name__)


class QuickIssueDialog(QDialog):
    """Діалог швидкої видачі ліцензії."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.ui = Ui_QuickIssueDialog()
        self.ui.setupUi(self)

        self._last_issue_result = None
        self._last_customer_email = ""
        self._last_customer_name = ""
        self._last_order_id = ""
        self._last_edition = ""
        self._last_app_version = ""
        self._last_payment_ref = ""
        self._last_fingerprint = ""

        self._repo = DbRepo(get_office_dir())
        self._repo.ensure_db()

        logger.debug("QuickIssueDialog init started.")

        self._setup_defaults()
        self._bind_signals()

        self.ui.btnPreviewEmail.setVisible(False)
        self.ui.btnSendEmail.setVisible(False)

        logger.debug("QuickIssueDialog init finished.")

    def _setup_defaults(self) -> None:
        """Заповнити поля значеннями за замовчуванням."""
        logger.debug("QuickIssueDialog _setup_defaults started.")

        self.ui.editCurrency.setText("USD")
        self.ui.editCurrency.setReadOnly(True)
        self.ui.lblCustomerStatus.setText("Статус: —")
        self.ui.editPaidUtc.setText(self._now_text())

        if self.ui.cmbEdition.count() == 0:
            self.ui.cmbEdition.addItem("PRO")
            self.ui.cmbEdition.addItem("PRO+")

        # --- buttons initial state ---
        self.ui.btnPreviewEmail.setVisible(False)
        self.ui.btnSendEmail.setVisible(False)

        logger.debug(
            "QuickIssueDialog defaults set: currency=%s, paid_utc=%s",
            self.ui.editCurrency.text(),
            self.ui.editPaidUtc.text(),
        )

    def _bind_signals(self) -> None:
        """Під'єднати сигнали кнопок і полів."""
        logger.debug("QuickIssueDialog _bind_signals started.")

        self.ui.btnCancel.clicked.connect(self.reject)
        self.ui.btnIssue.clicked.connect(self._on_issue_clicked)
        self.ui.btnPreviewEmail.clicked.connect(self._on_preview_email)
        self.ui.editEmail.editingFinished.connect(self._on_email_ready)
        self.ui.btnSendEmail.clicked.connect(self._on_send_email)

        logger.debug("QuickIssueDialog _bind_signals finished.")

    def _on_email_ready(self) -> None:
        """Пошук клієнта по email і автопідстановка полів."""
        email = self._norm(self.ui.editEmail.text()).lower()
        logger.debug("QuickIssueDialog _on_email_ready: email=%s", email)

        if not email:
            self.ui.lblCustomerStatus.setText("Статус: —")
            return

        if not self._is_valid_email(email):
            self.ui.lblCustomerStatus.setText("Статус: некоректний email")
            return

        customer = self._find_customer_by_email(email)
        if customer is None:
            self.ui.lblCustomerStatus.setText("Статус: Новий клієнт")
            return

        self.ui.editCustomerName.setText(customer["name"])
        self.ui.txtCustomerNote.setPlainText(customer["note"])
        self.ui.lblCustomerStatus.setText("Статус: Клієнта знайдено")

        self.ui.btnPreviewEmail.setVisible(False)
        self.ui.btnSendEmail.setVisible(False)

    def _on_issue_clicked(self) -> None:
        """Перевірити форму. Запис у БД буде на наступному кроці."""
        logger.debug("QuickIssueDialog _on_issue_clicked called.")

        ok, error_text = self._validate_form()
        if not ok:
            QMessageBox.warning(self, "Швидка видача ліцензії", error_text)
            return

        # --- NEW ---
        order_id = self._norm(self.ui.editOrderId.text())

        existing_order = self._repo.get_order_by_uid(order_id)
        if existing_order is not None:
            QMessageBox.warning(
                self,
                "Швидка видача ліцензії",
                "Замовлення вже існує.\n\n"
                "Можливі дії:\n"
                "- переглянути/змінити оплату\n"
                "- перевидати ліцензію\n\n"
                "Використовуйте Редактор дій і таблиць",
            )
            return

        if not self._check_overpayment_confirm():
            return

        self._process_issue()

    def _process_issue(self) -> None:
        """Створення customer → order → payment → license."""
        logger.debug("QuickIssueDialog _process_issue started.")

        self.ui.btnPreviewEmail.setVisible(False)
        self.ui.btnSendEmail.setVisible(False)
        self._last_issue_result = None

        email = self._norm(self.ui.editEmail.text()).lower()
        name = self._norm(self.ui.editCustomerName.text())
        note = self._norm(self.ui.txtCustomerNote.toPlainText())

        order_uid = self._norm(self.ui.editOrderId.text())
        edition = self._norm(self.ui.cmbEdition.currentText())
        app_version = self._norm(self.ui.editAppVersion.text())
        fingerprint = self._norm(self.ui.txtFingerprint.toPlainText())
        payment_ref = self._norm(self.ui.editPaymentRef.text())

        bank = self._norm(self.ui.editBank.text())
        amount = float(self._norm(self.ui.editAmount.text()).replace(",", "."))
        currency = self._norm(self.ui.editCurrency.text()).upper()
        paid_utc_raw = self._norm(self.ui.editPaidUtc.text())
        paid_utc = normalize_datetime_text(paid_utc_raw)
        payment_note = self._norm(self.ui.txtPaymentNote.toPlainText())

        try:
            # 1. CUSTOMER
            customer_id = self._repo.upsert_customer(
                email=email,
                name=name,
            )
            logger.debug("Customer upserted: id=%s", customer_id)

            # note поки не пишемо — поточний DbRepo цього не підтримує
            if note:
                logger.debug("Customer note is ignored for now: %s", note)

            # 2. ORDER
            order_id = self._repo.upsert_order(
                order_id=order_uid,
                customer_id=customer_id,
                edition=edition,
                app_version=app_version,
                payment_ref=payment_ref,
                fingerprint=fingerprint,
            )
            logger.debug("Order upserted: id=%s", order_id)

            # 3. PAYMENT
            self._repo.insert_payment(
                order_id=order_id,
                provider=bank,
                amount=amount,
                currency=currency,
                paid_utc=paid_utc,
                external_ref=payment_ref,
                note=payment_note,
            )
            logger.debug("Payment inserted.")

            # 4. LICENSE
            edition_db = self._edition_db()

            admin_password = session_state.ADMIN_PASSWORD
            if not admin_password:
                QMessageBox.warning(
                    self,
                    "Швидка видача ліцензії",
                    "Немає пароля сесії. Увійдіть в LGEOffice ще раз.",
                )
                return

            office_dir = get_office_dir()
            res = issue_license_files(
                office_dir=office_dir,
                order_id=order_uid,
                edition=edition_db,
                customer_email=email,
                customer_name=name,
                fingerprint=fingerprint,
                app_version=app_version,
                payment_ref=payment_ref,
                office_email=OFFICE_EMAIL_INBOX,
                admin_password=admin_password,
            )

            self._last_issue_result = res
            self._last_customer_email = email
            self._last_customer_name = name
            self._last_order_id = order_uid
            self._last_edition = edition
            self._last_app_version = app_version
            self._last_payment_ref = payment_ref
            self._last_fingerprint = fingerprint

            license_uid = str(res.payload.get("license_uid") or "").strip()
            if not license_uid:
                raise ValueError("license_uid не сформовано")

            issued_utc = utc_now_str()

            self._repo.insert_license(
                order_id=order_id,
                license_uid=license_uid,
                license_rel_path=res.license_path_rel,
                edition=edition_db,
                issued_utc=issued_utc,
            )

            logger.debug(
                "License file created: %s | rel=%s",
                res.license_path_abs,
                res.license_path_rel,
            )

        except Exception as exc:
            logger.exception("QuickIssueDialog process failed: %s", exc)
            QMessageBox.critical(
                self,
                "Швидка видача ліцензії",
                f"Помилка запису в БД:\n{exc}",
            )
            return

        QMessageBox.information(
            self,
            "Швидка видача ліцензії",
            "Ліцензію успішно створено.\n\n"
            f"Файл ліцензії: {res.license_path_abs.name}",
        )

        self.ui.lblCustomerStatus.setText(
            "Статус: Ліцензію створено. Файл .lic сформовано. "
            "Оберіть мову листа для preview/send."
        )

        # --- show email actions ---
        self.ui.btnPreviewEmail.setVisible(True)
        self.ui.btnSendEmail.setVisible(True)

    def _validate_form(self) -> tuple[bool, str]:
        """Повна валідація форми перед записом у БД."""
        email = self._norm(self.ui.editEmail.text())
        order_id = self._norm(self.ui.editOrderId.text())
        edition = self._norm(self.ui.cmbEdition.currentText())
        app_version = self._norm(self.ui.editAppVersion.text())
        fingerprint = self._norm(self.ui.txtFingerprint.toPlainText())
        bank = self._norm(self.ui.editBank.text())
        amount_text = self._norm(self.ui.editAmount.text())
        currency = self._norm(self.ui.editCurrency.text()).upper()
        paid_utc = self._norm(self.ui.editPaidUtc.text())
        payment_ref = self._norm(self.ui.editPaymentRef.text())

        logger.debug(
            "QuickIssueDialog validate: email=%s, order_id=%s, edition=%s, "
            "app_version=%s, bank=%s, currency=%s, paid_utc=%s, payment_ref=%s",
            email,
            order_id,
            edition,
            app_version,
            bank,
            currency,
            paid_utc,
            payment_ref,
        )

        if not email:
            return False, "Email обов’язковий."
        if not self._is_valid_email(email):
            return False, "Email має некоректний формат."

        if not order_id:
            return False, "ORDER_ID обов’язковий."

        if not edition:
            return False, "Редакція обов’язкова."
        if edition not in {"PRO", "PRO+"}:
            return False, "Редакція має бути PRO або PRO+."

        if not app_version:
            return False, "Версія обов’язкова."

        if not re.fullmatch(r"\d+\.\d+\.\d+", app_version):
            return False, "Версія має бути у форматі 1.0.0"

        if not fingerprint:
            return False, "Fingerprint обов’язковий."

        if len(fingerprint) != 64:
            return (
                False,
                "Fingerprint має містити 64 символи SHA256.\n"
                f"Зараз введено: {len(fingerprint)}.",
            )

        if not re.fullmatch(r"[0-9a-fA-F]{64}", fingerprint):
            return False, "Fingerprint має містити рівно 64 hex-символи SHA256."

        if not bank:
            return False, "Банк обов’язковий."

        if not amount_text:
            return False, "Сума обов’язкова."

        amount_text_norm = amount_text.replace(",", ".")
        try:
            amount = float(amount_text_norm)
        except ValueError:
            return False, "Сума має бути числом."

        required_usd = self._get_required_amount_usd()

        tolerance = 0.50

        if amount + tolerance < required_usd:
            return (
                False,
                "Недостатня сума оплати.\n"
                f"Потрібно: {required_usd:.2f} USD\n"
                f"Введено: {amount:.2f} USD\n"
                f"Допуск: ±{tolerance:.2f} USD",
            )

        if amount <= 0:
            return False, "Сума має бути більшою за 0."

        if currency != "USD":
            return False, "Валюта має бути USD."

        if not paid_utc:
            return False, "Дата/час платежу обов’язкові."

        try:
            normalize_datetime_text(paid_utc)
        except ValueError:
            return (
                False,
                "Дата/час платежу мають бути у форматі YYYY-MM-DD HH:MM.",
            )

        if not payment_ref:
            return False, "Payment reference обов’язковий."

        return True, ""

    def _check_overpayment_confirm(self) -> bool:
        """Попередити про завелику суму і спитати підтвердження."""
        amount_text = self._norm(self.ui.editAmount.text()).replace(",", ".")

        try:
            amount = float(amount_text)
        except ValueError:
            return True  # це вже ловить _validate_form()

        required_usd = self._get_required_amount_usd()
        tolerance = 0.50

        if amount <= required_usd + tolerance:
            return True

        answer = QMessageBox.question(
            self,
            "Швидка видача ліцензії",
            "Сума оплати більша за очікувану.\n\n"
            f"Потрібно: {required_usd:.2f} USD\n"
            f"Введено: {amount:.2f} USD\n\n"
            "Перевірте, чи не мала бути обрана інша редакція "
            "або чи це не переплата.\n\n"
            "Продовжити створення ліцензії?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        return answer == QMessageBox.StandardButton.Yes

    def _edition_db(self) -> str:
        ed = self._norm(self.ui.cmbEdition.currentText()).upper()
        if ed == "PRO+":
            return "PRO_PLUS"
        return ed

    def _find_customer_by_email(self, email: str) -> dict[str, str] | None:
        """Знайти клієнта по email."""
        try:
            return self._repo.get_customer_by_email(email)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Customer lookup failed: %s", exc)
            self.ui.lblCustomerStatus.setText("Статус: Помилка пошуку")
            return None

    @staticmethod
    def _norm(text: str) -> str:
        return text.strip()

    @staticmethod
    def _is_valid_email(email: str) -> bool:
        pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
        return bool(re.match(pattern, email))

    @staticmethod
    def _is_valid_paid_utc(text: str) -> bool:
        try:
            normalize_datetime_text(text)
            return True
        except ValueError:
            return False

    @staticmethod
    def _now_text() -> str:
        """Повернути поточний час у форматі YYYY-MM-DD HH:MM."""
        return utc_now_str()

    def _selected_email_language(self) -> str:
        """Повернути вибрану мову листа: uk або en."""
        return str(self.ui.cmbEmailLanguage.currentText() or "UK").strip().lower()

    def _on_preview_email(self) -> None:
        """Відкрити preview листа для останньої створеної ліцензії."""
        res = getattr(self, "_last_issue_result", None)
        if res is None:
            QMessageBox.warning(
                self,
                "Швидка видача ліцензії",
                "Спочатку створіть ліцензію.",
            )
            return

        language = self._selected_email_language()
        email_file = res.email_uk_path if language == "uk" else res.email_en_path

        if not email_file.exists():
            QMessageBox.warning(
                self,
                "Швидка видача ліцензії",
                f"Файл листа не знайдено:\n{email_file}",
            )
            return

        try:
            from office.core.email_preview_window_logic import EmailPreviewWindow
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Швидка видача ліцензії",
                f"Не вдалося відкрити вікно preview.\n\n{exc}",
            )
            return

        dlg = EmailPreviewWindow(
            email_file,
            self,
            show_send_button=False,
        )
        dlg.exec()

        self.ui.lblCustomerStatus.setText(
            "Статус: Виконано preview листа. "
            "Можна перевірити текст перед відправкою."
        )

    def _on_send_email(self) -> None:
        """Надіслати лист для останньої створеної ліцензії."""
        res = getattr(self, "_last_issue_result", None)

        if res is None:
            QMessageBox.warning(
                self,
                "Швидка видача ліцензії",
                "Спочатку створіть ліцензію.",
            )
            return

        language = self._selected_email_language()

        try:
            success = send_license_email_with_preview(
                parent=self,
                repo=self._repo,
                issue_result=res,
                lang_text=language,
            )

        except Exception as exc:
            logger.exception("QuickIssue send failed: %s", exc)

            QMessageBox.critical(
                self,
                "Швидка видача ліцензії",
                f"Помилка відправки листа:\n{exc}",
            )
            return

        if not success:
            self.ui.lblCustomerStatus.setText(
                "Статус: Відправку скасовано або сталася помилка."
            )
            return

        # запис sent_utc тільки після SUCCESS

        try:
            license_uid = str(res.payload.get("license_uid") or "").strip()

            if not license_uid:
                raise ValueError("license_uid не знайдено")

            sent_utc = datetime.now().strftime("%Y-%m-%d %H:%M")

            self._repo.set_license_sent_utc(
                license_uid=license_uid,
                sent_utc=sent_utc,
            )

            logger.info(
                "EMAIL_SENT | license_uid=%s | sent_utc=%s",
                license_uid,
                sent_utc,
            )

        except Exception as exc:
            logger.exception(
                "Failed to write sent_utc: %s",
                exc,
            )

            QMessageBox.warning(
                self,
                "Швидка видача ліцензії",
                "Лист надіслано, але не вдалося записати sent_utc.",
            )

            return

        self.ui.lblCustomerStatus.setText("Статус: Лист успішно надіслано.")

        QMessageBox.information(
            self,
            "Швидка видача ліцензії",
            "Лист успішно надіслано.",
        )

    def _get_required_amount_usd(self) -> float:
        email = self._norm(self.ui.editEmail.text()).lower()
        fingerprint = self._norm(self.ui.txtFingerprint.toPlainText())
        edition_db = self._edition_db()

        customer = self._repo.get_customer_by_email(email)
        if not customer:
            return float(get_price_usd(edition_db))

        try:
            customer_id = int(customer["id"])
        except (KeyError, TypeError, ValueError):
            return float(get_price_usd(edition_db))

        return self._repo.get_required_amount_for_edition(
            customer_id=customer_id,
            fingerprint=fingerprint,
            target_edition=edition_db,
        )
