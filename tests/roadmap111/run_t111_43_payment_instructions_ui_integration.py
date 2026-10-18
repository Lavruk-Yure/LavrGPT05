# -*- coding: utf-8 -*-
"""T111-43 — канонічна інтеграція платіжної інструкції, TEST_ONLY.

Тест виконує методи з AST на безпечних локальних заглушках.
Не запускає застосунок, не відкриває GUI, не надсилає листів і не
змінює файлів робочого дерева.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
DIALOG = ROOT / "core" / "license_request_dialog.py"
POLICY = ROOT / "core" / "translation_policy.py"
FALLBACK = ROOT / "lang" / "strings_fallback.json"
UI_REQUEST = ROOT / "ui" / "license_request_dialog.ui"
UI_PREVIEW = ROOT / "ui" / "license_payment_preview_dialog.ui"
GEN_REQUEST = ROOT / "ui" / "ui_license_request_dialog.py"
GEN_PREVIEW = ROOT / "ui" / "ui_license_payment_preview_dialog.py"

TEST_ONLY = True
BROKER_REQUESTS = 0
EMAILS_SENT = 0
PRODUCTION_LOGIC_CHANGED = True
TRADING_LOGIC_CHANGED = False


def _assert(value: bool, label: str) -> None:
    if not value:
        raise AssertionError(label)


def _method(tree: ast.Module, cls: str, name: str) -> ast.FunctionDef:
    for item in tree.body:
        if isinstance(item, ast.ClassDef) and item.name == cls:
            for child in item.body:
                if isinstance(child, ast.FunctionDef) and child.name == name:
                    return child
    raise AssertionError(f"Метод відсутній: {cls}.{name}")


def _get_callable(tree: ast.Module, cls: str, name: str, env: dict):
    method = _method(tree, cls, name)
    body: list[ast.stmt] = [method]
    wrapper = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(wrapper)
    result = dict(env)
    exec(compile(wrapper, "<T111-43_AST>", "exec"), result)
    return result[name]


def _ui_widgets(path: Path) -> dict[str, str]:
    tree = ElementTree.parse(path)
    return {
        element.attrib["name"]: element.attrib["class"]
        for element in tree.iter("widget")
        if "name" in element.attrib
    }


def _read_canonical_translations(
    tree: ast.Module,
) -> dict[str, dict[str, str]]:
    """Прочитати 8 канонічних перекладів без імпорту production-модулів."""
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign):
            continue
        if not isinstance(node.target, ast.Name):
            continue
        if node.target.id != "CENTRAL_TRANSLATION_OVERRIDES":
            continue
        if not isinstance(node.value, ast.Dict):
            break

        result: dict[str, dict[str, str]] = {}
        for key_node, value_node in zip(node.value.keys, node.value.values):
            if not isinstance(key_node, ast.Constant):
                continue
            if not isinstance(key_node.value, str):
                continue
            key = key_node.value
            if not key.startswith(
                ("LicenseRequestDialog.", "LicensePaymentPreviewDialog.")
            ):
                continue
            if not isinstance(value_node, ast.Dict):
                continue
            translations: dict[str, str] = {}
            for lang_node, text_node in zip(value_node.keys, value_node.values):
                if not isinstance(lang_node, ast.Constant):
                    continue
                if not isinstance(text_node, ast.Constant):
                    continue
                if not isinstance(lang_node.value, str):
                    continue
                if not isinstance(text_node.value, str):
                    continue
                translations[lang_node.value] = text_node.value
            result[key] = translations
        return result
    raise AssertionError("Не знайдено CENTRAL_TRANSLATION_OVERRIDES")


class _Clipboard:
    def __init__(self) -> None:
        self.value: str | None = None

    def set_text(self, text: str) -> None:
        self.value = text

    def __getattr__(self, attribute_name: str):
        if attribute_name == "setText":
            return self.set_text
        raise AttributeError(attribute_name)


def main() -> int:
    source = DIALOG.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    policy_tree = ast.parse(POLICY.read_text(encoding="utf-8-sig"))
    ast.parse(GEN_REQUEST.read_text(encoding="utf-8-sig"))
    ast.parse(GEN_PREVIEW.read_text(encoding="utf-8-sig"))

    main_widgets = _ui_widgets(UI_REQUEST)
    preview_widgets = _ui_widgets(UI_PREVIEW)
    required_main = {
        "btnGenerate": "QPushButton",
        "btnCopyEmail": "QPushButton",
        "btnSendEmail": "QPushButton",
        "btnViewPayment": "QPushButton",
        "btnCopyPayment": "QPushButton",
    }
    required_preview = {
        "lblTestWarning": "QLabel",
        "txtPayment": "QPlainTextEdit",
        "btnCopy": "QPushButton",
        "btnClose": "QPushButton",
    }
    _assert(
        all(main_widgets.get(key) == value for key, value in required_main.items()),
        "Canonical request .ui controls absent",
    )
    _assert(
        all(
            preview_widgets.get(key) == value for key, value in required_preview.items()
        ),
        "Canonical payment preview .ui controls absent",
    )

    for name in required_main:
        _assert(name in GEN_REQUEST.read_text(encoding="utf-8"), name)
    for name in required_preview:
        _assert(name in GEN_PREVIEW.read_text(encoding="utf-8"), name)

    payment_xml = ElementTree.parse(UI_PREVIEW)
    read_only = payment_xml.find(
        './/widget[@name="txtPayment"]/property[@name="readOnly"]/bool'
    )
    _assert(read_only is not None and read_only.text == "true", "Read only")

    fallback = json.loads(FALLBACK.read_text(encoding="utf-8"))
    canonical = _read_canonical_translations(policy_tree)
    translation_keys = (
        "LicenseRequestDialog.btnViewPayment",
        "LicenseRequestDialog.btnCopyPayment",
        "LicenseRequestDialog.msgPaymentCopied",
        "LicensePaymentPreviewDialog.windowTitle",
        "LicensePaymentPreviewDialog.lblTestWarning",
        "LicensePaymentPreviewDialog.btnCopy",
        "LicensePaymentPreviewDialog.btnClose",
        "LicensePaymentPreviewDialog.msgCopied",
    )
    for key in translation_keys:
        _assert(key in canonical, f"Missing canonical translation {key}")
        for language in ("uk", "en", "de", "fr", "pl"):
            _assert(
                bool(canonical[key].get(language)),
                f"Missing canonical {language} for {key}",
            )
        _assert(
            fallback.get(key) == canonical[key],
            f"Regenerate lang/strings_fallback.json: {key}",
        )

    # Метод із production AST тестуємо на заглушках, без Qt.
    clipboard = _Clipboard()
    app = SimpleNamespace(clipboard=lambda: clipboard)
    meta = SimpleNamespace(PAYMENT_CARD_OR_IBAN="1111 2222 3333 4444")
    notice = canonical["LicensePaymentPreviewDialog.lblTestWarning"]["uk"]
    lang = SimpleNamespace(tr=lambda key, fallback_text: notice)
    env = {"QApplication": app, "app_meta": meta}
    test_check = _get_callable(
        tree, "LicenseRequestDialog", "_test_payment_details", env
    )
    copy = _get_callable(
        tree,
        "LicenseRequestDialog",
        "_on_copy_payment",
        {**env},
    )
    status = []
    owner = SimpleNamespace(
        _last_order_id="LGE-TEST-43",
        _last_payment_text="ORDER_ID: LGE-TEST-43\n99.00 USD",
        _lang_mgr=lang,
        _set_status=status.append,
        _test_payment_details=lambda: test_check(owner),
    )
    _assert(test_check(owner), "Placeholder detection failed")
    copy(owner)
    expected = f"{notice}\n\n{getattr(owner, '_last_payment_text')}"
    _assert(clipboard.value == expected, "Warning was not copied")
    _assert(
        status == ["LicenseRequestDialog.msgPaymentCopied"],
        "Clipboard confirmation missing",
    )

    clipboard.value = None
    meta.PAYMENT_CARD_OR_IBAN = "LIVE_TEST_IBAN_EXAMPLE"
    setattr(owner, "_last_payment_text", "ORDER_ID: LGE-TEST-43\n99.00 USD")
    _assert(not test_check(owner), "Non-placeholder detection failed")
    copy(owner)
    _assert(
        clipboard.value == getattr(owner, "_last_payment_text"),
        "Unmodified payment text expected for non-placeholder",
    )

    # Перегляд Proforma відкриває діалог без генерації нової заявки.
    opened = []

    class _Preview:
        def __init__(
            self, parent, preview_language, payment_text, test_payment
        ) -> None:
            _ = preview_language
            self.opened = opened
            self.opened.append((parent, payment_text, test_payment))

        def exec(self) -> None:
            self.opened.append("shown")

    view = _get_callable(
        tree,
        "LicenseRequestDialog",
        "_on_view_payment",
        {"LicensePaymentPreviewDialog": _Preview},
    )
    view(owner)
    _assert(len(opened) == 2, "Payment preview not opened")
    _assert(opened[0][1] == getattr(owner, "_last_payment_text"), "Wrong preview text")
    _assert(opened[0][2] is False, "Wrong live-preview warning")

    # У самому діалозі кнопка Copy має копіювати й видиме попередження.
    preview_copy = _get_callable(
        tree,
        "LicensePaymentPreviewDialog",
        "_on_copy",
        {"QApplication": app},
    )
    notice_flag = SimpleNamespace(isVisible=lambda: True, text=lambda: notice)
    copied_status = []
    preview_owner = SimpleNamespace(
        ui=SimpleNamespace(
            txtPayment=SimpleNamespace(toPlainText=lambda: "ORDER_ID: TEST-43"),
            lblTestWarning=notice_flag,
            lblStatus=SimpleNamespace(setText=copied_status.append),
        ),
        _lang_mgr=lang,
    )
    preview_copy(preview_owner)
    _assert(
        clipboard.value == f"{notice}\n\nORDER_ID: TEST-43",
        "Preview copied without visible warning",
    )
    _assert(bool(copied_status), "Preview copy success not shown")

    setattr(owner, "_last_order_id", None)
    clipboard.value = None
    copy(owner)
    _assert(clipboard.value is None, "Copy before generation not blocked")
    _assert(
        status[-1] == "LicenseRequestDialog.msgGenerateFirst",
        "Missing generate-first status",
    )

    # Відновлення вже створеної Proforma без перезапису робочих файлів.
    restore = _method(tree, "LicenseRequestDialog", "_restore_existing_payment")
    restore_source = ast.unparse(restore)
    _assert("fingerprint_hash" in restore_source, "Machine binding not checked")
    _assert("saved_email" in restore_source, "Customer email not checked")
    _assert("payment_instructions_" in restore_source, "Payment file not paired")

    class _Machine:
        @staticmethod
        def compute_machine_id() -> str:
            return "TEST_MACHINE_43"

    with TemporaryDirectory(prefix="t11143_") as temp_dir:
        base = Path(temp_dir)
        requests = base / "licenses" / "requests"
        requests.mkdir(parents=True)
        test_order = "LGE-TEST-43"
        request = requests / f"request_{test_order}.json"
        payment = requests / f"payment_instructions_{test_order}.txt"
        payload = {
            "order_id": test_order,
            "customer": {"email": "customer@example.invalid"},
            "device": {"fingerprint_hash": "TEST_MACHINE_43"},
        }
        request.write_text(json.dumps(payload), encoding="utf-8")
        payment.write_text(f"ORDER_ID: {test_order}", encoding="utf-8")

        restoration = _get_callable(
            tree,
            "LicenseRequestDialog",
            "_restore_existing_payment",
            {
                "BASE_DIR": base,
                "LicenseManager": _Machine,
                "json": json,
                "_safe_str": lambda value: (
                    value.strip() if isinstance(value, str) else ""
                ),
            },
        )

        class _Button:
            def __init__(self) -> None:
                self.enabled = False

            def set_enabled(self, value: bool) -> None:
                self.enabled = value

            def __getattr__(self, attribute_name: str):
                if attribute_name == "setEnabled":
                    return self.set_enabled
                raise AttributeError(attribute_name)

        class _Email:
            @staticmethod
            def text() -> str:
                return "customer@example.invalid"

        state = SimpleNamespace(
            ui=SimpleNamespace(
                editEmail=_Email(),
                btnViewPayment=_Button(),
                btnCopyPayment=_Button(),
            ),
            _last_order_id=None,
            _last_payment_text="",
            _find_existing_requests=lambda req: (
                sorted(req.glob("request_*.json")),
                [],
            ),
        )
        restoration(state)
        _assert(getattr(state, "_last_order_id") == test_order, "Valid restore failed")
        _assert(state.ui.btnViewPayment.enabled, "View disabled after restore")
        _assert(state.ui.btnCopyPayment.enabled, "Copy disabled after restore")

        # Чужий fingerprint не дає відновити попередню Proforma.
        payload["device"]["fingerprint_hash"] = "FOREIGN_MACHINE"
        request.write_text(json.dumps(payload), encoding="utf-8")
        foreign = SimpleNamespace(
            ui=SimpleNamespace(
                editEmail=_Email(),
                btnViewPayment=_Button(),
                btnCopyPayment=_Button(),
            ),
            _last_order_id=None,
            _last_payment_text="",
            _find_existing_requests=getattr(state, "_find_existing_requests"),
        )
        restoration(foreign)
        _assert(getattr(foreign, "_last_order_id") is None, "Foreign request restored")
        _assert(not foreign.ui.btnViewPayment.enabled, "Foreign request enabled")

    original = ast.parse(source)
    generate = _method(original, "LicenseRequestDialog", "_on_generate")
    ctor = _method(original, "LicenseRequestDialog", "__init__")
    _assert(
        "self._last_payment_text = payment_text" in ast.unparse(generate),
        "Payment cache not set after generation",
    )
    _assert(
        "self.ui.btnViewPayment.setEnabled(False)" in ast.unparse(ctor),
        "Preview available before generation",
    )
    _assert(
        "self.ui.btnViewPayment.setEnabled(True)" in ast.unparse(generate),
        "Preview not enabled after generation",
    )
    _assert(
        "self.ui.btnCopyPayment.setEnabled(True)" in ast.unparse(generate),
        "Copy not enabled after generation",
    )

    print("T111-43 TEST_ONLY")
    print("verdict=CANONICAL_PAYMENT_INSTRUCTIONS_UI_INTEGRATION_GREEN")
    print("canonical_translation_policy_verified=True")
    print("generated_fallback_matches_policy=True")
    for label in (
        "main_ui_controls_present",
        "preview_ui_controls_present",
        "generated_ui_matches_designer",
        "payment_preview_is_read_only",
        "translations_uk_en_present",
        "placeholder_warning_copied",
        "non_placeholder_copy_unchanged",
        "copy_before_generation_blocked",
        "buttons_enabled_after_generation",
        "existing_request_restored_only_for_matching_machine",
        "preview_dialog_opened_without_request_regeneration",
        "preview_copy_includes_visible_warning",
    ):
        print(f"{label}=True")
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(f"emails_sent={EMAILS_SENT}")
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
    print(f"trading_logic_changed={TRADING_LOGIC_CHANGED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
