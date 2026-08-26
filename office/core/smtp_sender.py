# smtp_sender.py
# -*- coding: utf-8 -*-
"""
smtp_sender — відправка ліцензійного листа через Gmail SMTP.

- Використовує App Password
- Підтримує вкладення (.lic)
- Без Outlook, без mailto
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path


def send_license_email(
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    to_email: str,
    subject: str,
    body: str,
    attachment_path: Path,
) -> None:
    msg = EmailMessage()
    msg["From"] = smtp_user
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    if attachment_path.exists():
        with open(attachment_path, "rb") as f:
            file_data = f.read()
            file_name = attachment_path.name

        msg.add_attachment(
            file_data,
            maintype="application",
            subtype="octet-stream",
            filename=file_name,
        )

    with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
