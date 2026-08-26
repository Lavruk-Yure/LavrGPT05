# db_report_service.py
# -*- coding: utf-8 -*-
"""
db_report_service.py — службовий TXT-звіт по БД LGEOffice.

Формує журнальний snapshot стану бази:
1. неприв'язані оплати
2. ієрархічна структура:
   клієнт -> замовлення -> оплати / ліцензії

Формат орієнтований на:
- читання з екрана
- друк на A4
- архівування у TXT
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LINE_WIDTH = 140
LINE_CHAR = "—"

INDENT_ORDER = "      "
INDENT_CHILD = "            "


def export_db_report(db_path: Path) -> Path:
    """Сформувати TXT-звіт по БД та повернути шлях до файлу."""
    logger.debug("DB report export started: db_path=%s", db_path)

    if not db_path.exists():
        raise FileNotFoundError(f"Базу даних не знайдено: {db_path}")

    office_dir = db_path.parent
    reports_dir = office_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    now_utc = datetime.now(UTC)
    file_name = f"db_report_{now_utc.strftime('%Y%m%d_%H%M')}.txt"
    report_path = reports_dir / file_name

    logger.debug("DB report target path: %s", report_path)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        with report_path.open("w", encoding="utf-8", newline="\n") as fh:
            _write_header(fh, now_utc)
            _write_unlinked_payments_section(conn, fh)
            _write_database_structure_section(conn, fh)

    logger.debug("DB report export finished: %s", report_path)
    return report_path


def _write_header(fh: Any, now_utc: datetime) -> None:
    """Записати шапку звіту."""
    fh.write("LGE Office — Звіт по базі даних\n")
    fh.write(f"Дата: {now_utc.strftime('%Y-%m-%d')}\n")
    fh.write(f"Час: {now_utc.strftime('%H:%M UTC')}\n")
    fh.write("\n")
    _write_line(fh)
    fh.write("\n")


def _write_unlinked_payments_section(conn: sqlite3.Connection, fh: Any) -> None:
    """Записати розділ неприв'язаних оплат."""
    logger.debug("Writing section 1: unlinked payments")

    rows = conn.execute(
        """
        SELECT id, provider, amount, currency, paid_utc, note
                FROM payments
                WHERE order_id IS NULL
                ORDER BY id
        """
    ).fetchall()

    fh.write("РОЗДІЛ 1. НЕПРИВ’ЯЗАНІ ОПЛАТИ\n")
    _write_line(fh)

    headers = ["ID", "Банк", "Сума", "Валюта", "Сплачено UTC", "Примітка"]
    widths = [4, 18, 10, 8, 16, 70]

    fh.write(_make_row(headers, widths) + "\n")
    _write_line(fh)

    payment_count = 0
    total_usd = 0.0

    if rows:
        for row in rows:
            amount_value = _to_float(row["amount"])
            currency_value = _safe(row["currency"]).upper()

            if currency_value == "USD":
                total_usd += amount_value

            amount_text = _format_amount_cell(row["amount"], widths[2])

            _write_wrapped_row(
                fh=fh,
                values=[
                    row["id"],
                    row["provider"],
                    amount_text,
                    row["currency"],
                    _fmt_datetime(row["paid_utc"]),
                    row["note"],
                ],
                widths=widths,
                wrap_indices=[5],
                prefix="",
            )
            payment_count += 1
    else:
        fh.write("Немає неприв’язаних оплат.\n")

    fh.write("\n")
    fh.write(f"Всього оплат: {payment_count}\n")
    fh.write(f"На суму: {total_usd:.2f} USD\n")
    fh.write("\n")


def _write_database_structure_section(conn: sqlite3.Connection, fh: Any) -> None:
    """Записати ієрархічний розділ структури бази."""
    logger.debug("Writing section 2: database structure")

    customers = conn.execute(
        """
        SELECT id, email, name, note
        FROM customers
        ORDER BY id
        """
    ).fetchall()

    orders = conn.execute(
        """
        SELECT id, customer_id, order_uid, edition, app_version
        FROM orders
        ORDER BY id
        """
    ).fetchall()

    payments = conn.execute(
        """
        SELECT id, order_id, provider, amount, currency, paid_utc, note
                FROM payments
                WHERE order_id IS NOT NULL
                ORDER BY id
        """
    ).fetchall()

    licenses = conn.execute(
        """
        SELECT id, order_id, license_uid, license_rel_path, issued_utc, sent_utc
        FROM licenses
        ORDER BY id
        """
    ).fetchall()

    orders_by_customer: dict[int, list[sqlite3.Row]] = {}
    for row in orders:
        orders_by_customer.setdefault(int(row["customer_id"]), []).append(row)

    payments_by_order: dict[int, list[sqlite3.Row]] = {}
    for row in payments:
        payments_by_order.setdefault(int(row["order_id"]), []).append(row)

    licenses_by_order: dict[int, list[sqlite3.Row]] = {}
    for row in licenses:
        licenses_by_order.setdefault(int(row["order_id"]), []).append(row)

    fh.write("РОЗДІЛ 2. СТРУКТУРА БАЗИ\n")
    _write_line(fh)
    fh.write("\n")
    fh.write("КЛІЄНТИ\n")
    _write_line(fh)

    if not customers:
        fh.write("Немає клієнтів.\n\n")
    else:
        for customer in customers:
            customer_id = int(customer["id"])
            _write_customer_block(
                fh=fh,
                customer=customer,
                orders=orders_by_customer.get(customer_id, []),
                payments_by_order=payments_by_order,
                licenses_by_order=licenses_by_order,
            )

    total_payment_count = len(payments)
    total_payment_usd = 0.0
    for row in payments:
        if _safe(row["currency"]).upper() == "USD":
            total_payment_usd += _to_float(row["amount"])

    issued_count = len(licenses)
    sent_count = sum(1 for row in licenses if _safe(row["sent_utc"]).strip())

    fh.write("ПІДСУМКИ РОЗДІЛУ 2\n")
    fh.write("—" * 40 + "\n")
    fh.write(f"Клієнтів: {len(customers)}\n")
    fh.write(f"Замовлень: {len(orders)}\n")
    fh.write(f"Оплат: {total_payment_count}\n")
    fh.write(f"На суму: {total_payment_usd:.2f} USD\n")
    fh.write(f"Видано ліцензій: {issued_count}\n")
    fh.write(f"Надіслано ліцензій: {sent_count}\n")
    fh.write("\n")


def _write_customer_block(
    fh: Any,
    customer: sqlite3.Row,
    orders: list[sqlite3.Row],
    payments_by_order: dict[int, list[sqlite3.Row]],
    licenses_by_order: dict[int, list[sqlite3.Row]],
) -> None:
    """Записати блок одного клієнта з усіма його замовленнями."""
    customer_headers = ["Клієнт", "Email", "Ім’я", "Примітка"]
    customer_widths = [6, 34, 18, 68]

    fh.write(_make_row(customer_headers, customer_widths) + "\n")
    _write_line(fh)

    _write_wrapped_row(
        fh=fh,
        values=[
            customer["id"],
            customer["email"],
            customer["name"],
            customer["note"],
        ],
        widths=customer_widths,
        wrap_indices=[2, 3],
        prefix="",
    )

    _write_line(fh)

    for order in orders:
        order_id = int(order["id"])
        _write_order_block(
            fh=fh,
            order=order,
            payments=payments_by_order.get(order_id, []),
            licenses=licenses_by_order.get(order_id, []),
        )

    fh.write("\n")


def _write_order_block(
    fh: Any,
    order: sqlite3.Row,
    payments: list[sqlite3.Row],
    licenses: list[sqlite3.Row],
) -> None:
    """Записати блок одного замовлення."""
    order_headers = ["Замовлення", "Клієнт ID", "UID", "Редакція", "Версія"]
    order_widths = [10, 10, 28, 14, 10]

    fh.write(INDENT_ORDER + "|" + _make_row(order_headers, order_widths) + "\n")
    fh.write(INDENT_ORDER + _line_text(LINE_WIDTH - len(INDENT_ORDER)) + "\n")
    fh.write(
        INDENT_ORDER
        + "|"
        + _make_row(
            [
                order["id"],
                order["customer_id"],
                order["order_uid"],
                order["edition"],
                order["app_version"],
            ],
            order_widths,
        )
        + "\n"
    )
    fh.write(INDENT_ORDER + _line_text(LINE_WIDTH - len(INDENT_ORDER)) + "\n")

    if payments:
        _write_payments_subblock(fh, payments)

    if licenses:
        _write_licenses_subblock(fh, licenses)


def _write_payments_subblock(fh: Any, payments: list[sqlite3.Row]) -> None:
    """Записати підблок оплат конкретного замовлення."""
    payment_headers = [
        "Оплати",
        "Замовл. ID",
        "Банк",
        "Сума",
        "Валюта",
        "Сплачено UTC",
        "Примітка",
    ]
    payment_widths = [10, 10, 16, 10, 8, 16, 36]

    fh.write(INDENT_CHILD + "|" + _make_row(payment_headers, payment_widths) + "\n")
    fh.write(INDENT_CHILD + _line_text(LINE_WIDTH - len(INDENT_CHILD)) + "\n")

    for payment in payments:
        amount_text = _format_amount_cell(payment["amount"], payment_widths[3])

        _write_wrapped_row(
            fh=fh,
            values=[
                payment["id"],
                payment["order_id"],
                payment["provider"],
                amount_text,
                payment["currency"],
                _fmt_datetime(payment["paid_utc"]),
                payment["note"],
            ],
            widths=payment_widths,
            wrap_indices=[6],
            prefix=INDENT_CHILD + "|",
        )

    fh.write(INDENT_CHILD + _line_text(LINE_WIDTH - len(INDENT_CHILD)) + "\n")


def _write_licenses_subblock(fh: Any, licenses: list[sqlite3.Row]) -> None:
    """Записати підблок ліцензій конкретного замовлення."""
    license_headers = [
        "Ліцензія",
        "Замовл. ID",
        "UID",
        "Файл",
        "Видано UTC",
        "Надіслано UTC",
    ]
    license_widths = [10, 10, 22, 36, 16, 16]

    fh.write(INDENT_CHILD + "|" + _make_row(license_headers, license_widths) + "\n")
    fh.write(INDENT_CHILD + _line_text(LINE_WIDTH - len(INDENT_CHILD)) + "\n")

    for license_row in licenses:
        fh.write(
            INDENT_CHILD
            + "|"
            + _make_row(
                [
                    license_row["id"],
                    license_row["order_id"],
                    license_row["license_uid"],
                    license_row["license_rel_path"],
                    _fmt_datetime(license_row["issued_utc"]),
                    _fmt_datetime(license_row["sent_utc"]),
                ],
                license_widths,
            )
            + "\n"
        )

    fh.write(INDENT_CHILD + _line_text(LINE_WIDTH - len(INDENT_CHILD)) + "\n")


def _write_wrapped_row(
    fh: Any,
    values: list[Any],
    widths: list[int],
    wrap_indices: list[int],
    prefix: str = "",
) -> None:
    """
    Записати рядок таблиці з переносом вибраних довгих полів.
    Перенесення робиться синхронно по рядках.
    """
    prepared = [_safe(v).replace("\n", " ").replace("\r", " ").strip() for v in values]

    wrapped_columns: dict[int, list[str]] = {}
    max_lines = 1

    for idx, (value, width) in enumerate(zip(prepared, widths, strict=False)):
        if idx in wrap_indices:
            parts = _wrap_text(value, width)
        else:
            parts = [value[:width]]
        if not parts:
            parts = [""]
        wrapped_columns[idx] = parts
        max_lines = max(max_lines, len(parts))

    for line_idx in range(max_lines):
        line_values: list[str] = []
        for idx in range(len(values)):
            parts = wrapped_columns[idx]
            line_values.append(parts[line_idx] if line_idx < len(parts) else "")
        fh.write(prefix + _make_row(line_values, widths) + "\n")


def _wrap_text(text: str, width: int) -> list[str]:
    """Розбити текст на частини фіксованої ширини."""
    text = _safe(text).strip()
    if not text:
        return [""]

    parts: list[str] = []
    while text:
        parts.append(text[:width])
        text = text[width:]
    return parts


def _make_row(values: list[Any], widths: list[int]) -> str:
    """Сформувати один табличний рядок."""
    cells = []
    for value, width in zip(values, widths, strict=False):
        cells.append(_format_cell(value, width))
    return " | ".join(cells)


def _format_cell(value: Any, width: int) -> str:
    """Форматувати значення під задану ширину."""
    text = _safe(value).replace("\n", " ").replace("\r", " ").strip()

    if len(text) > width:
        text = text[:width]

    return text.ljust(width)


def _write_line(fh: Any) -> None:
    """Записати повну горизонтальну лінію."""
    fh.write(_line_text(LINE_WIDTH) + "\n")


def _line_text(width: int) -> str:
    """Отримати рядок-лінію заданої ширини."""
    return LINE_CHAR * max(width, 1)


def _fmt_amount(value: Any) -> str:
    """Формат суми для звіту: 2 десяткових."""
    if value is None:
        return ""

    try:
        return f"{float(value):.2f}"
    except Exception:  # noqa
        return str(value)


def _fmt_datetime(value: Any) -> str:
    """Нормалізувати дату/час до компактного формату для звіту."""
    text = _safe(value).strip()
    if not text:
        return ""

    text = text.replace("T", " ")

    if len(text) >= 16 and text[4] == "-" and text[7] == "-":
        date_part = text[:10]
        time_part = text[11:16] if len(text) >= 16 else ""
        try:
            dt = datetime.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H:%M")
            return dt.strftime("%d.%m.%Y %H:%M")
        except ValueError:
            return text[:16]

    return text[:16]


def _to_float(value: Any) -> float:
    """Безпечне перетворення значення у float."""
    if value is None:
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace(",", ".")
    if not text:
        return 0.0

    try:
        return float(text)
    except ValueError:
        return 0.0


def _safe(value: Any) -> str:
    """Безпечне строкове представлення значення."""
    if value is None:
        return ""
    return str(value)


def _format_amount_cell(value: Any, width: int) -> str:
    """Комірка для сум — праве вирівнювання."""
    text = _fmt_amount(value)
    if len(text) > width:
        text = text[:width]
    return text.rjust(width)
