# license_email_builder.py
# -*- coding: utf-8 -*-
"""
Єдине місце формування теми та тіла ліцензійного листа.

RoadMap47 / Patch 47.1:
- прибирає дублювання з license_issuer.py
- використовується з db_grid_window_logic.py
- далі буде використаний з Quick Issue
"""

from __future__ import annotations

from pathlib import Path


def build_license_email_subject(language: str, order_uid: str) -> str:
    """Побудувати тему листа."""
    if (language or "").strip().lower() == "uk":
        return f"LGE ліцензія — {order_uid}"
    return f"LGE License — {order_uid}"


def build_license_email_body(
    *,
    language: str,
    customer_name: str,
    office_email: str,
    order_uid: str,
    edition: str,
    app_version: str,
    payment_ref: str,
    fingerprint: str,
) -> str:
    """Побудувати тіло листа."""
    lang = (language or "").strip().lower()
    customer_name = (customer_name or "").strip()
    fingerprint = (fingerprint or "").strip()

    if lang == "uk":
        greeting = f"Вітаю, {customer_name}." if customer_name else "Добрий день!"
        return (
            f"{greeting}\n\n"
            "Дякуємо за оплату.\n\n"
            "У вкладенні — файл вашої ліцензії LGE (.lic).\n\n"
            f"ORDER_ID: {order_uid}\n"
            f"Edition: {edition}\n"
            f"App version: {app_version}\n"
            f"Payment reference: {payment_ref}\n\n"
            "Ліцензія прив'язана до вашого пристрою.\n\n"
            f"Fingerprint:\n{fingerprint}\n\n"
            "ІНСТРУКЦІЯ З АКТИВАЦІЇ ЛІЦЕНЗІЇ\n\n"
            "Варіант А — використання файлу (рекомендовано)\n"
            "1. Помістіть вкладений файл (*.lic) в папку:\n"
            "   licenses\n"
            "   яка знаходиться поруч із програмою LGE.\n\n"
            "2. Запустіть програму LGE.\n"
            "3. Відкрийте:\n"
            "   Налаштування → Ліцензія\n"
            "4. У полі 'Ліцензійний ключ' введіть:\n"
            "   назву файлу ліцензії\n"
            "5. Натисніть:\n"
            "   Активувати\n\n"
            "Варіант Б — вставка ключа вручну\n"
            "1. Відкрийте файл (*.lic) як текстовий файл.\n"
            "2. Скопіюйте весь текст.\n"
            "3. Вставте його у поле 'Ліцензійний ключ'.\n"
            "4. Натисніть Активувати.\n\n"
            f"Якщо виникнуть питання, звертайтесь: {office_email}\n\n"
            "З повагою,\n"
            "LGE Support"
        )

    greeting = f"Hello, {customer_name}." if customer_name else "Hello."
    return (
        f"{greeting}\n\n"
        "Thank you for your payment.\n\n"
        "Attached is your LGE license file (.lic).\n\n"
        f"ORDER_ID: {order_uid}\n"
        f"Edition: {edition}\n"
        f"App version: {app_version}\n"
        f"Payment reference: {payment_ref}\n\n"
        "The license is bound to your device.\n\n"
        f"Fingerprint:\n{fingerprint}\n\n"
        "LICENSE ACTIVATION INSTRUCTIONS\n\n"
        "Option A — using the file (recommended)\n"
        "1. Place the attached file (*.lic) into the folder:\n"
        "   licenses\n"
        "   located next to the LGE program.\n\n"
        "2. Start LGE.\n"
        "3. Open:\n"
        "   Settings → License\n"
        "4. Enter the license file name.\n"
        "5. Click Activate.\n\n"
        "Option B — manual key insertion\n"
        "1. Open the file (*.lic) as a text file.\n"
        "2. Copy the entire text.\n"
        "3. Paste it into the License key field.\n"
        "4. Click Activate.\n\n"
        f"If you have any questions, contact us at: {office_email}\n\n"
        "Best regards,\n"
        "LGE Support"
    )


def write_license_email_file(
    *,
    file_path: Path,
    customer_email: str,
    subject: str,
    body: str,
) -> None:
    """Записати preview-файл листа у звичному форматі To/Subject/body."""
    file_path.write_text(
        f"To: {customer_email}\nSubject: {subject}\n\n{body}",
        encoding="utf-8",
    )
