# -*- coding: utf-8 -*-
"""T111-42 — Payment Instructions UI Anatomy — TEST_ONLY.

Лише AST/XML та локальна модель. Не імпортує Qt і не пише runtime-дані.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from xml.etree.ElementTree import parse as parse_xml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DIALOG = PROJECT_ROOT / "core" / "license_request_dialog.py"
APP_META = PROJECT_ROOT / "core" / "app_meta.py"
UI = PROJECT_ROOT / "ui" / "license_request_dialog.ui"
TEST_ONLY = True
BROKER_REQUESTS = 0
BROKER_EXECUTION_ATTEMPTED = False
EMAILS_SENT = 0
PRODUCTION_LOGIC_CHANGED = False
TEST_NOTICE = "ТЕСТОВІ РЕКВІЗИТИ — НЕ ОПЛАЧУВАТИ"


@dataclass
class _PreviewModel:
    """Кандидат UI-моделі виключно для тесту."""

    order_id: str = ""
    payment_text: str = ""

    def set_generated(self, order_id: str, payment_text: str) -> None:
        self.order_id = order_id
        self.payment_text = payment_text

    def preview(self, placeholder: bool) -> str | None:
        if not self.order_id or not self.payment_text:
            return None
        if placeholder:
            return f"{TEST_NOTICE}\n\n{self.payment_text}"
        return self.payment_text

    def copy_payment(self, placeholder: bool) -> str | None:
        """Не змінює системний clipboard; повертає текст для копії."""
        return self.preview(placeholder)


def _method(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name != "LicenseRequestDialog":
            continue
        for child in node.body:
            if isinstance(child, ast.FunctionDef) and child.name == name:
                return child
    raise AssertionError(f"Метод не знайдено: {name}")


def _calls(method: ast.FunctionDef, call_name: str) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == call_name
        for node in ast.walk(method)
    )


def _mentions(method: ast.FunctionDef, name: str) -> bool:
    return any(
        isinstance(node, ast.Name) and node.id == name for node in ast.walk(method)
    )


def _constant(tree: ast.Module, name: str) -> object:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            if isinstance(node.value, ast.Constant):
                return node.value.value
            raise AssertionError(f"Непідтримувана константа: {name}")
    raise AssertionError(f"Константу не знайдено: {name}")


def _check(value: bool, label: str) -> None:
    if not value:
        raise AssertionError(label)


def main() -> int:
    tree = ast.parse(DIALOG.read_text(encoding="utf-8-sig"))
    meta = ast.parse(APP_META.read_text(encoding="utf-8-sig"))
    widgets = {
        node.attrib["name"]
        for node in parse_xml(UI).iter("widget")
        if "name" in node.attrib
    }
    generate = _method(tree, "_on_generate")
    copy_email = _method(tree, "_on_copy_email")
    send_email = _method(tree, "_on_send_email")
    payment = _method(tree, "_make_payment_text")
    methods = {
        child.name
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "LicenseRequestDialog"
        for child in node.body
        if isinstance(child, ast.FunctionDef)
    }
    placeholder = _constant(meta, "PAYMENT_CARD_OR_IBAN") == "1111 2222 3333 4444"
    facts = {
        "existing_request_controls_present": {
            "btnGenerate",
            "btnCopyEmail",
            "btnSendEmail",
            "btnClose",
        }.issubset(widgets),
        "payment_text_generated": _calls(generate, "_make_payment_text"),
        "payment_text_saved_locally": (
            _calls(generate, "write_text") and _mentions(generate, "payment_path")
        ),
        "existing_email_copy_is_separate": (
            _calls(copy_email, "setText") and not _mentions(copy_email, "payment_text")
        ),
        "email_send_is_mailto_only": (
            _calls(send_email, "_mailto_open") and not _calls(send_email, "send")
        ),
        "payment_preview_control_missing": not any(
            "payment" in widget.lower() and widget.startswith("btn")
            for widget in widgets
        ),
        "payment_preview_handler_missing": not any(
            "payment" in name.lower()
            and ("preview" in name.lower() or "copy" in name.lower())
            for name in methods
        ),
        "current_account_is_test_placeholder": placeholder,
        "payment_generator_present": (
            _calls(payment, "get") and _mentions(payment, "order_id")
        ),
    }
    for label, value in facts.items():
        _check(value, label)

    model = _PreviewModel()
    before_generation_blocked = (
        model.preview(placeholder) is None and model.copy_payment(placeholder) is None
    )
    text_a = "ORDER_ID: LGE-TEST-A\n99.00 USD\nTEST DETAILS"
    model.set_generated("LGE-TEST-A", text_a)
    preview_a = model.preview(placeholder)
    candidate = {
        "preview_requires_generated_request": before_generation_blocked,
        "current_order_preview_valid": (
            preview_a is not None
            and "LGE-TEST-A" in preview_a
            and "99.00 USD" in preview_a
        ),
        "copy_matches_visible_payment_text": (
            model.copy_payment(placeholder) == preview_a
        ),
        "test_payment_warning_visible": (
            preview_a is not None and preview_a.startswith(TEST_NOTICE)
        ),
    }
    text_b = "ORDER_ID: LGE-TEST-B\n199.00 USD\nTEST DETAILS"
    model.set_generated("LGE-TEST-B", text_b)
    preview_b = model.preview(placeholder)
    candidate["old_order_not_reused"] = (
        preview_b is not None
        and "LGE-TEST-B" in preview_b
        and "LGE-TEST-A" not in preview_b
    )
    candidate["non_placeholder_preview_unchanged"] = model.preview(False) == text_b
    for label, value in candidate.items():
        _check(value, label)

    print("T111-42 TEST_ONLY")
    print("verdict=PAYMENT_INSTRUCTIONS_UI_GAP_AND_CANDIDATE_PROVEN")
    for label, value in {**facts, **candidate}.items():
        print(f"{label}={value}")
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(f"broker_execution_attempted={BROKER_EXECUTION_ATTEMPTED}")
    print(f"emails_sent={EMAILS_SENT}")
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
