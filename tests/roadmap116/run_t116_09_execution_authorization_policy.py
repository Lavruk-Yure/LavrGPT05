"""T116-09 · TEST_ONLY · контракт політики допуску до broker submission.

Нова політика моделюється окремо від production. Читаємо production лише
через AST: без імпорту LGE, створення RuntimeEngine, записів чи broker API.
Успішний pytest означає GREEN моделі, а НЕ справність production guard.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE_FILE = ROOT / "engine" / "runtime_engine.py"
SETTINGS_FILE = ROOT / "core" / "settings_page_trading.py"

MODES = ("OFF", "MANUAL", "SEMI", "AUTO", "INVALID")
# Джерело, режим контролю, незалежно підтверджено SEMI-дію.
REQUESTS = (
    ("MANUAL_UI", "MANUAL", False),
    ("WORKSPACE", "AUTO", False),
    ("WORKSPACE", "SEMI", False),
    ("WORKSPACE", "SEMI", True),
)

# Очікування для майбутнього guard. True для SEMI з підтвердженням
# означає лише контракт; підтверджений approval path ще не реалізований.
EXPECTED = {
    "OFF": (False, False, False, False),
    "MANUAL": (True, False, False, False),
    "SEMI": (True, False, False, True),
    "AUTO": (True, True, False, True),
    "INVALID": (False, False, False, False),
}


def authorize_model(
    global_mode: object,
    origin: str,
    control_mode: str,
    *,
    verified_semi_approval: bool = False,
) -> bool:
    """TEST_ONLY модель майбутнього fail-closed authorization boundary.

    verified_semi_approval — абстрактне підтвердження довіреним механізмом,
    а НЕ параметр, який можна безпосередньо взяти з UI або order intent.
    """
    if not isinstance(global_mode, str):
        return False
    if global_mode not in {"MANUAL", "SEMI", "AUTO"}:
        return False

    if origin == "MANUAL_UI" and control_mode == "MANUAL":
        return True
    if origin != "WORKSPACE":
        return False
    if control_mode == "AUTO":
        return global_mode == "AUTO" and not verified_semi_approval
    if control_mode == "SEMI":
        return global_mode in {"SEMI", "AUTO"} and verified_semi_approval
    return False


def read_method(path: Path, class_name: str, method_name: str) -> ast.FunctionDef:
    """Витягнути метод із вихідного файлу, не виконуючи production-код."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    target_class = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return next(
        node for node in target_class.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )


def mentions_mode(node: ast.AST) -> bool:
    """Виявити пряме звернення до execution_mode у перевіреному методі."""
    return any(
        isinstance(item, ast.Attribute) and item.attr == "execution_mode"
        or isinstance(item, ast.Constant) and item.value == "execution_mode"
        for item in ast.walk(node)
    )


def calls_setter(node: ast.AST) -> bool:
    """Знайти прямий виклик RuntimeEngine.set_execution_mode()."""
    for item in ast.walk(node):
        if not isinstance(item, ast.Call):
            continue
        func = item.func
        if isinstance(func, ast.Attribute) and func.attr == "set_execution_mode":
            return True
    return False


def test() -> None:
    print("T116-09 TEST_ONLY | execution authorization policy contract")

    # 5 глобальних режимів x 4 сценарії виклику.
    checked = 0
    for mode in MODES:
        actual = tuple(
            authorize_model(
                mode, origin, control,
                verified_semi_approval=approved,
            )
            for origin, control, approved in REQUESTS
        )
        assert actual == EXPECTED[mode], (mode, actual, EXPECTED[mode])
        print(f"policy={mode} manual={int(actual[0])} "
              f"wsp_auto={int(actual[1])} "
              f"wsp_semi_pending={int(actual[2])} "
              f"wsp_semi_verified={int(actual[3])}")
        checked += len(REQUESTS)

    # Без fail-open для None, порожнього, невідомого режиму та
    # невідомих джерел / невідповідних control_mode.
    for missing in (None, "", "auto", "INVALID", 42):
        assert not authorize_model(missing, "WORKSPACE", "AUTO")
    assert not authorize_model("AUTO", "UNKNOWN", "AUTO")
    assert not authorize_model("AUTO", "MANUAL_UI", "AUTO")
    assert not authorize_model("AUTO", "WORKSPACE", "MANUAL")
    assert not authorize_model(
        "AUTO", "WORKSPACE", "AUTO", verified_semi_approval=True
    )
    print(f"policy_matrix_cases={checked}")
    print("unknown_mode_and_origin_fail_closed=YES")
    print("semi_without_verified_approval_blocked=YES")

    # Контроль фактичного вихідного ZIP. Це НЕ виклик брокера.
    workspace = read_method(
        ENGINE_FILE, "RuntimeEngine", "submit_workspace_execution_plan"
    )
    manual = read_method(
        ENGINE_FILE, "RuntimeEngine", "place_manual_market_order"
    )
    manual_ib = read_method(
        ENGINE_FILE, "RuntimeEngine", "_place_manual_market_order_ib"
    )
    settings = read_method(
        SETTINGS_FILE, "SettingsPageTrading", "_apply_changes"
    )

    checks = {
        "production_workspace_mode_check": mentions_mode(workspace),
        "production_manual_ctrader_mode_check": mentions_mode(manual),
        "production_manual_ib_mode_check": mentions_mode(manual_ib),
        "production_settings_calls_setter": calls_setter(settings),
    }
    for name, present in checks.items():
        print(f"{name}={'YES' if present else 'NO'}")

    assert not any(checks.values()), (
        "Production уже змінився: повторно переглянь guard та контракт"
    )
    print("semi_approval_production_path=NOT_VERIFIED")
    print("broker_requests=0")
    print("database_writes=0")
    print("config_writes=0")
    print("production_changes=0")
    print("T116-09=GREEN_POLICY_MODEL_PRODUCTION_GUARDS_RED")


if __name__ == "__main__":
    test()
