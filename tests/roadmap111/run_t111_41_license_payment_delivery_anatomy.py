# -*- coding: utf-8 -*-
"""T111-41 — License Payment Delivery Anatomy — TEST_ONLY.

Статично досліджує платіжні реквізити, Proforma, лист продавцю
та відсутність автоматичного передавання інструкції клієнту.
Не відкриває GUI, не пише файлів заявки та не надсилає пошти.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REQUEST_DIALOG = PROJECT_ROOT / "core" / "license_request_dialog.py"
APP_META = PROJECT_ROOT / "core" / "app_meta.py"

TEST_ONLY = True
BROKER_REQUESTS = 0
BROKER_EXECUTION_ATTEMPTED = False
EMAILS_SENT = 0
PRODUCTION_LOGIC_CHANGED = False


def _method(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            if node.name != "LicenseRequestDialog":
                continue
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == name:
                    return child
    raise AssertionError(f"Метод не знайдено: {name}")


def _attributes(method: ast.FunctionDef) -> set[str]:
    return {node.attr for node in ast.walk(method) if isinstance(node, ast.Attribute)}


def _constant(tree: ast.Module, name: str) -> Any:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets
            ):
                if isinstance(node.value, ast.Constant):
                    return node.value.value
                raise AssertionError(f"Неочікуваний тип константи: {name}")
    raise AssertionError(f"Константу не знайдено: {name}")


def _sample_email(method: ast.FunctionDef) -> tuple[str, str]:
    source = ast.unparse(method)
    namespace: dict[str, Any] = {}
    exec(compile(source, "<TEST_ONLY>", "exec"), namespace)
    return namespace["_make_email"](
        order_id="LGE-TEST-ORDER",
        edition="PRO",
        customer_email="customer@example.invalid",
        app_version="1.0.1",
        fingerprint="TEST_FINGERPRINT",
        recipient_email="seller@example.invalid",
        price=99.0,
        currency="USD",
        is_upgrade=False,
        lang="uk",
    )


def main() -> int:
    request_tree = ast.parse(REQUEST_DIALOG.read_text(encoding="utf-8-sig"))
    meta_tree = ast.parse(APP_META.read_text(encoding="utf-8-sig"))
    generate = ast.unparse(_method(request_tree, "_on_generate"))
    payment_method = _method(request_tree, "_make_payment_text")
    copy_email = ast.unparse(_method(request_tree, "_on_copy_email"))
    send_email = ast.unparse(_method(request_tree, "_on_send_email"))
    mailto = ast.unparse(_method(request_tree, "_mailto_open"))
    subject, body = _sample_email(_method(request_tree, "_make_email"))

    card_iban = _constant(meta_tree, "PAYMENT_CARD_OR_IBAN")
    seller_email = _constant(meta_tree, "SELLER_SALES_EMAIL")
    payment_attrs = _attributes(payment_method)

    facts = {
        "request_json_saved_locally": ("request_path.write_text" in generate),
        "payment_proforma_saved_locally": (
            "payment_path.write_text" in generate
            and "self._make_payment_text" in generate
        ),
        "payment_fields_from_app_meta": all(
            key in payment_attrs
            for key in (
                "PAYMENT_RECIPIENT",
                "PAYMENT_CARD_OR_IBAN",
                "PAYMENT_BANK_NAME",
                "PAYMENT_REFERENCE_PREFIX",
            )
        ),
        "payment_details_static_in_source": (
            isinstance(card_iban, str) and bool(card_iban.strip())
        ),
        "payment_details_look_placeholder": (card_iban == "1111 2222 3333 4444"),
        "seller_recipient_from_app_meta": (
            "SELLER_SALES_EMAIL" in send_email and isinstance(seller_email, str)
        ),
        "email_has_order_price_and_fingerprint": (
            "LGE-TEST-ORDER" in subject
            and "LGE-TEST-ORDER" in body
            and "99.00 USD" in body
            and "TEST_FINGERPRINT" in body
        ),
        "email_payment_label_without_url": (
            "Платіжне посилання:" in body and "://" not in body
        ),
        "copy_action_copies_only_email": (
            "_last_body" in copy_email
            and "setText" in copy_email
            and "payment_path" not in copy_email
        ),
        "send_action_opens_mailto_to_seller": (
            "_mailto_open(seller_to" in send_email
            and "SELLER_SALES_EMAIL" in send_email
            and "mailto:" in mailto
        ),
        "send_action_does_not_attach_proforma": (
            "payment_path" not in send_email
            and "payment_instructions" not in send_email
            and "payment_path" not in mailto
        ),
        "no_customer_payment_delivery_in_dialog": (
            "_mailto_open" not in generate and "customer_email" not in send_email
        ),
    }

    print("T111-41 TEST_ONLY")
    for label, value in facts.items():
        print(f"{label}={value}")
        if not value:
            raise AssertionError(f"Не підтверджено: {label}")
    print("verdict=LICENSE_PAYMENT_DELIVERY_GAP_CONFIRMED")
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(f"broker_execution_attempted={BROKER_EXECUTION_ATTEMPTED}")
    print(f"emails_sent={EMAILS_SENT}")
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
