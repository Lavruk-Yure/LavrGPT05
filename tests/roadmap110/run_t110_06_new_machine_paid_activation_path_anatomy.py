# -*- coding: utf-8 -*-
"""
T110-06 — New Machine Paid Activation Path Anatomy — TEST_ONLY.

Перевіряє фактичний production path без зміни production:
- новий conf стартує як FREE;
- license request використовує fingerprint поточної машини;
- Office payment gate передує видачі ліцензії;
- стара оплачена PRO на іншому fingerprint не дає upgrade-price новій машині;
- license payload містить fingerprint;
- activate_key() перевіряє machine binding до запису PRO у conf.

Це не тест зовнішньої банківської верифікації.
"""

from __future__ import annotations

import ast
import gc
import sqlite3
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from office.core.db_repo import DbRepo  # noqa: E402
from office.core.pricing import get_price_usd  # noqa: E402

TEST_ONLY = True
BROKER_REQUESTS = 0
PRODUCTION_LOGIC_CHANGED = False


def _source(rel_path: str) -> str:
    return (PROJECT_ROOT / rel_path).read_text(encoding="utf-8")


def _parse(rel_path: str) -> ast.Module:
    return ast.parse(_source(rel_path), filename=rel_path)


def _find_function(
    tree: ast.AST,
    name: str,
    *,
    class_name: str | None = None,
) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if class_name is None:
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
            continue

        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == name:
                return item

    raise AssertionError(f"function_not_found={class_name or ''}.{name}")


def _call_name(call: ast.Call) -> str:
    parts: list[str] = []
    node: ast.expr = call.func

    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value

    if isinstance(node, ast.Name):
        parts.append(node.id)

    return ".".join(reversed(parts))


def _call_lines(method: ast.FunctionDef, suffix: str) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(method):
        if isinstance(node, ast.Call) and _call_name(node).endswith(suffix):
            lines.append(node.lineno)
    return sorted(lines)


def _is_other_machine_return(node: ast.AST) -> bool:
    if not isinstance(node, ast.Return):
        return False
    if not isinstance(node.value, ast.Tuple) or len(node.value.elts) != 2:
        return False

    ok_value, message_value = node.value.elts
    return (
        isinstance(ok_value, ast.Constant)
        and ok_value.value is False
        and isinstance(message_value, ast.Constant)
        and message_value.value == "License belongs to another machine"
    )


def _is_license_conf_write(node: ast.AST) -> bool:
    if not isinstance(node, (ast.Assign, ast.AnnAssign)):
        return False

    targets: list[ast.expr] = []
    if isinstance(node, ast.Assign):
        targets.extend(node.targets)
    elif isinstance(node.target, ast.expr):
        targets.append(node.target)

    for target in targets:
        if not isinstance(target, ast.Subscript):
            continue
        if isinstance(target.value, ast.Name) and target.value.id == "lic":
            return True

    return False


def _activation_rejects_before_conf_write(method: ast.FunctionDef) -> bool:
    reject_lines = sorted(
        node.lineno
        for node in ast.walk(method)
        if _is_other_machine_return(node) and isinstance(node, ast.Return)
    )
    write_lines = sorted(
        node.lineno
        for node in ast.walk(method)
        if _is_license_conf_write(node) and isinstance(node, ast.stmt)
    )

    return bool(reject_lines and write_lines and reject_lines[0] < write_lines[0])


def _init_test_db(office_root: Path) -> None:
    schema_path = PROJECT_ROOT / "office" / "core" / "schema.sql"
    schema = schema_path.read_text(encoding="utf-8")
    conn = sqlite3.connect(office_root / "office.db")
    try:
        conn.executescript(schema)
        conn.commit()
    finally:
        conn.close()


def _same_customer_other_machine_requires_full_price() -> bool:
    pro_price = float(get_price_usd("PRO"))
    pro_plus_price = float(get_price_usd("PRO_PLUS"))

    with tempfile.TemporaryDirectory(prefix="t110_06_") as tmp:
        office_root = Path(tmp)
        _init_test_db(office_root)
        repo = DbRepo(office_root)

        customer_id = repo.upsert_customer("t11006@example.test")
        old_fp = "A" * 64
        new_fp = "B" * 64

        old_order_id = repo.upsert_order(
            order_id="T110-06-OLD",
            customer_id=customer_id,
            edition="PRO",
            app_version="1.0.1",
            payment_ref="T110-06-OLD",
            fingerprint=old_fp,
        )
        repo.insert_payment(
            order_id=old_order_id,
            provider="TEST_ONLY",
            external_ref="T110-06-OLD",
            amount=pro_price,
            currency="USD",
            paid_utc="2026-09-25 00:00",
            note="TEST_ONLY",
        )

        same_machine_required = repo.get_required_amount_for_edition(
            customer_id=customer_id,
            fingerprint=old_fp,
            target_edition="PRO_PLUS",
        )
        new_machine_required = repo.get_required_amount_for_edition(
            customer_id=customer_id,
            fingerprint=new_fp,
            target_edition="PRO_PLUS",
        )

        del repo
        gc.collect()

    return (
        same_machine_required < pro_plus_price
        and abs(new_machine_required - pro_plus_price) < 0.000001
    )


def main() -> int:
    config_source = _source("core/config_manager.py")
    request_source = _source("core/license_request_dialog.py")
    issuer_source = _source("office/core/license_issuer.py")
    repo_source = _source("office/core/db_repo.py")

    quick_tree = _parse("office/core/quick_issue_dialog.py")
    orders_tree = _parse("office/core/db_grid_window_logic_ord.py")
    manager_tree = _parse("core/license_manager.py")

    quick_click = _find_function(
        quick_tree,
        "_on_issue_clicked",
        class_name="QuickIssueDialog",
    )
    orders_issue = _find_function(
        orders_tree,
        "issue_license",
        class_name="OrdersLogic",
    )
    activate = _find_function(
        manager_tree,
        "activate_key",
        class_name="LicenseManager",
    )

    quick_validate_lines = _call_lines(quick_click, "self._validate_form")
    quick_process_lines = _call_lines(quick_click, "self._process_issue")

    orders_payment_lines = _call_lines(
        orders_issue,
        "self._check_payment_sufficiency",
    )
    orders_write_lines = _call_lines(orders_issue, "self._write_license_file")

    activate_candidate_lines = _call_lines(
        activate,
        "cls.compute_machine_id_candidates",
    )

    checks = {
        "new_conf_defaults_to_free": '"edition": "free"' in config_source,
        "request_uses_current_machine_fingerprint": (
            "LicenseManager.compute_machine_id()" in request_source
            and '"fingerprint_hash": fingerprint_hash' in request_source
        ),
        "request_uses_pricing_function": (
            "calculate_license_price(current_edition, edition)" in request_source
        ),
        "quick_issue_payment_validation_precedes_issue": (
            bool(quick_validate_lines)
            and bool(quick_process_lines)
            and min(quick_validate_lines) < min(quick_process_lines)
        ),
        "orders_payment_gate_precedes_license_write": (
            bool(orders_payment_lines)
            and bool(orders_write_lines)
            and min(orders_payment_lines) < min(orders_write_lines)
        ),
        "paid_pro_lookup_is_bound_to_fingerprint": (
            "AND fingerprint_sha256 = ?" in repo_source
            and "customer_id = ?" in repo_source
        ),
        "old_machine_payment_does_not_discount_new_machine": (
            _same_customer_other_machine_requires_full_price()
        ),
        "issued_payload_contains_fingerprint": (
            '"fingerprint": fingerprint' in issuer_source
        ),
        "activation_checks_machine_candidates": bool(activate_candidate_lines),
        "activation_rejects_other_machine_before_conf_write": (
            _activation_rejects_before_conf_write(activate)
        ),
    }

    print("T110-06 — New Machine Paid Activation Path Anatomy — TEST_ONLY")
    print()

    failed = 0
    for name, passed in checks.items():
        state = "PASS" if passed else "FAIL"
        print(f"{state} {name}={passed}")
        failed += 0 if passed else 1

    print()
    print(f"checks={len(checks)}")
    print(f"passed={len(checks) - failed}")
    print(f"failed={failed}")

    if failed:
        print("boundary=PAID_ACTIVATION_PATH_NOT_CONFIRMED")
        print(f"TEST_ONLY={TEST_ONLY}")
        print(f"broker_requests={BROKER_REQUESTS}")
        print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
        print("T110-06=RED")
        return 1

    print("new_machine_old_conf=BLOCKED_BY_T110_03")
    print("new_machine_old_payment=NOT_REUSED_ACROSS_FINGERPRINT")
    print("office_payment_gate=PRESENT")
    print("new_license_fingerprint_binding=PRESENT")
    print("activation_machine_gate=PRESENT")
    print("external_bank_verification=NOT_ASSERTED")
    print(
        "path=NEW_MACHINE->NEW_PAYMENT_RECORD->NEW_LICENSE->"
        "MACHINE_BOUND_ACTIVATION"
    )
    print("first_unverified_boundary=REAL_NEW_MACHINE_ISSUANCE_AND_ACTIVATION")
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
    print("T110-06=GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
