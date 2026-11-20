"""T116-08 · TEST_ONLY · аудит режимів виконання та джерел ордерів.

Лише AST-читання коду. Немає імпортів LGE, мережі, БД та конфігурації.
PASS означає успішну діагностику наявних прогалин, а НЕ безпечний production.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "engine" / "runtime_engine.py"
CONTROLLER = ROOT / "core" / "algorithm_workspace_controller.py"
ORDERS_UI = ROOT / "core" / "orders_page.py"
SETTINGS = ROOT / "core" / "settings_page_trading.py"


def read_method(path: Path, class_name: str, method_name: str) -> ast.FunctionDef:
    """Повернути AST потрібного методу без імпорту production-модуля."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return next(
        node
        for node in cls.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )


def has_call(node: ast.AST, name: str) -> bool:
    """Перевірити виклик функції або методу за назвою."""
    for item in ast.walk(node):
        if not isinstance(item, ast.Call):
            continue

        func = item.func
        if isinstance(func, ast.Name) and func.id == name:
            return True

        if isinstance(func, ast.Attribute) and func.attr == name:
            return True

    return False


def reads_execution_mode(node: ast.AST) -> bool:
    """Чи читається execution_mode безпосередньо у методі."""
    return any(
        isinstance(item, ast.Attribute)
        and item.attr == "execution_mode"
        or isinstance(item, ast.Constant)
        and item.value == "execution_mode"
        for item in ast.walk(node)
    )


def text_literals(node: ast.AST) -> set[str]:
    return {
        item.value
        for item in ast.walk(node)
        if isinstance(item, ast.Constant) and isinstance(item.value, str)
    }


def count_setter_calls() -> int:
    """Порахувати виклики set_execution_mode у core та engine."""
    count = 0

    for folder in (ROOT / "core", ROOT / "engine"):
        for path in folder.rglob("*.py"):
            tree = ast.parse(
                path.read_text(encoding="utf-8"),
                filename=str(path),
            )

            for item in ast.walk(tree):
                if not isinstance(item, ast.Call):
                    continue

                func = item.func
                if isinstance(func, ast.Attribute):
                    if func.attr == "set_execution_mode":
                        count += 1

    return count


def test() -> None:
    print("T116-08 TEST_ONLY | execution authorization source audit")

    workspace_submit = read_method(
        ENGINE, "RuntimeEngine", "submit_workspace_execution_plan"
    )
    manual_submit = read_method(ENGINE, "RuntimeEngine", "place_manual_market_order")
    ib_manual = read_method(ENGINE, "RuntimeEngine", "_place_manual_market_order_ib")
    orders_click = read_method(ORDERS_UI, "OrdersPage", "_on_place_order_clicked")
    persist = read_method(
        CONTROLLER,
        "AlgorithmWorkspaceController",
        "_persist_workspace_trade_after_risk_allow",
    )
    auto = read_method(
        CONTROLLER,
        "AlgorithmWorkspaceController",
        "_submit_workspace_auto_after_same_call_flat",
    )
    apply = read_method(SETTINGS, "SettingsPageTrading", "_apply_changes")

    assert has_call(workspace_submit, "place_market_order")
    assert has_call(manual_submit, "place_market_order")
    assert has_call(manual_submit, "_place_manual_market_order_ib")
    assert has_call(ib_manual, "place_market_order")
    assert has_call(orders_click, "place_manual_market_order")
    assert "submit_workspace_execution_plan" in text_literals(auto)
    assert has_call(auto, "submit")
    assert "READY_FOR_SUBMISSION" in text_literals(persist)
    assert "PENDING_CONFIRMATION" in text_literals(persist)
    assert "READY_FOR_SUBMISSION" in text_literals(workspace_submit)

    workspace_mode_read = reads_execution_mode(workspace_submit)
    manual_mode_read = reads_execution_mode(manual_submit)
    ib_manual_mode_read = reads_execution_mode(ib_manual)
    apply_calls_setter = has_call(apply, "set_execution_mode")
    setter_calls = count_setter_calls()

    print(f"workspace_global_mode_checked={'YES' if workspace_mode_read else 'NO'}")
    print(f"manual_ctrader_global_mode_checked={'YES' if manual_mode_read else 'NO'}")
    print(f"manual_ib_global_mode_checked={'YES' if ib_manual_mode_read else 'NO'}")
    print(
        f"settings_apply_calls_runtime_setter={'YES' if apply_calls_setter else 'NO'}"
    )
    print(f"runtime_setter_call_sites={setter_calls}")
    print("workspace_auto_entry=READY_FOR_SUBMISSION")
    print("workspace_semi_entry=PENDING_CONFIRMATION")
    print("workspace_auto_submit_caller=FOUND")
    print("manual_ui_submit_caller=FOUND")
    print("semi_user_approval_path=NOT_CONFIRMED_BY_THIS_TEST")

    # Діагностика має відтворити наявні недоліки вихідного коду.
    # Після реального виправлення цей тест потрібно змінити на GREEN-guard тест.
    assert not workspace_mode_read, "Workspace guard уже змінено — переглянь аудит"
    assert not manual_mode_read, "Manual cTrader guard уже змінено — переглянь аудит"
    assert not ib_manual_mode_read, "Manual IB guard уже змінено — переглянь аудит"
    assert not apply_calls_setter, "GUI setter уже додано — переглянь аудит"
    assert setter_calls == 0, "Знайдено новий виклик setter — переглянь аудит"

    print("policy_status=NOT_IMPLEMENTED_OR_APPROVED")
    print("broker_requests=0")
    print("database_writes=0")
    print("config_writes=0")
    print("production_changes=0")
    print("T116-08=GREEN_DIAGNOSTIC_PRODUCTION_GUARDS_RED")


if __name__ == "__main__":
    test()
