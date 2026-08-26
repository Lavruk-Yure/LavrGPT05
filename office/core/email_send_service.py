# email_send_service.py
# -*- coding: utf-8 -*-
"""
email_send_service — відправка ліцензійного email з Preview + lock-check + audit.

Patch 29.2:
- Preview перед SMTP (EmailPreviewWindow)
- Блокування, якщо файл відкритий (msvcrt lock)
- Audit пишеться тільки після успішної відправки
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QDialog, QMessageBox, QWidget

try:
    from office.core.mail_settings import (
        SMTP_HOST,
        SMTP_PASSWORD,
        SMTP_PORT,
        SMTP_USER,
        validate_smtp_settings,
    )
except Exception:  # noqa
    # mail_settings.py — локальний файл у mail_settings.py - має бути в .gitignore.
    # Якщо його нема/зламаний,
    # SMTP відправляння має коректно повідомити користувача.
    SMTP_HOST = ""
    SMTP_PORT = 0
    SMTP_USER = ""
    SMTP_PASSWORD = ""

    def validate_smtp_settings() -> tuple[bool, str]:  # type: ignore
        return (
            False,
            "Немає mail_settings.py або він зламаний (office/core/mail_settings.py)",
        )


from office.core.db_repo import DbRepo
from office.core.email_preview_window_logic import EmailPreviewWindow
from office.core.file_lock import is_file_locked
from office.core.smtp_sender import send_license_email

logger = logging.getLogger(__name__)


def send_license_email_with_preview(
    *,
    parent: QWidget,
    repo: DbRepo,
    issue_result: Any,
    lang_text: str,
) -> bool:
    """
    Повертає True, якщо реально відправили.
    False, якщо користувач скасував/не відправили.
    """
    # 1) мова
    lang_norm = (lang_text or "").strip().lower()
    use_uk = "укр" in lang_norm or "uk" in lang_norm

    body_file: Path = (
        issue_result.email_uk_path if use_uk else issue_result.email_en_path
    )
    if not body_file.exists():
        QMessageBox.warning(
            parent, "LGE Office", f"Файл листа не знайдено:\n{body_file}"
        )
        return False

    # 2) preview
    preview = EmailPreviewWindow(
        body_file,
        parent,
        show_send_button=True,
    )
    result = preview.exec()
    if result != QDialog.DialogCode.Accepted:
        return False  # БЕЗ SMTP і БЕЗ audit

    # 3) lock-check
    if is_file_locked(body_file):
        QMessageBox.warning(
            parent,
            "LGE Office",
            "Файл листа відкритий у редакторі.\n"
            "Закрийте його та натисніть “Надіслати” ще раз.",
        )

        return False  # БЕЗ SMTP і БЕЗ audit

    # 4) read To / Subject / body
    try:
        to_email, subject, body = _parse_email_preview_file(body_file)
    except Exception as exc:
        QMessageBox.warning(
            parent,
            "LGE Office",
            f"Не можу прочитати файл:\n{body_file}\n\n{exc}",
        )
        return False

    if not to_email:
        QMessageBox.warning(
            parent,
            "LGE Office",
            "У preview-файлі не знайдено адресата (To).",
        )
        return False

    if not subject:
        QMessageBox.warning(
            parent,
            "LGE Office",
            "У preview-файлі не знайдено тему листа (Subject).",
        )
        return False

    # 5) SMTP
    ok, msg = validate_smtp_settings()
    if not ok:
        QMessageBox.warning(parent, "LGE Office", msg)
        return False

    try:
        send_license_email(
            smtp_host=SMTP_HOST,
            smtp_port=SMTP_PORT,
            smtp_user=SMTP_USER,
            smtp_password=SMTP_PASSWORD,
            to_email=to_email,
            subject=subject,
            body=body,
            attachment_path=issue_result.license_path_abs,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("SMTP send failed")
        QMessageBox.warning(parent, "LGE Office", f"Помилка SMTP:\n{exc}")
        return False

    # 6) audit ТІЛЬКИ ПІСЛЯ УСПІХУ
    order_id = str(issue_result.payload.get("order_id", "")).strip()
    lang_code = "uk" if use_uk else "en"
    repo.audit(
        "EMAIL_SENT",
        (
            f"order_id={order_id}; "
            f"to={to_email}; "
            f"lang={lang_code}; "
            f"smtp_from={SMTP_USER}; "
            f"body_file={body_file.name}; "
            f"license_file={issue_result.license_path_rel}"
        ),
    )

    return True


def _parse_email_preview_file(file_path: Path) -> tuple[str, str, str]:
    text = file_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    to_email = ""
    subject = ""
    body_lines: list[str] = []
    in_body = False

    for line in lines:
        if not in_body:
            if line.startswith("To:"):
                to_email = line[3:].strip()
                continue
            if line.startswith("Subject:"):
                subject = line[8:].strip()
                continue
            if line.strip() == "":
                in_body = True
                continue
        else:
            body_lines.append(line)

    body = "\n".join(body_lines).strip()
    return to_email, subject, body
