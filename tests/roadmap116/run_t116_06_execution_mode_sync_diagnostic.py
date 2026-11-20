"""T116-06 · TEST_ONLY · діагностика синхронізації режиму GUI та RuntimeEngine.

Читає лише Python-код. Виконує три методи у підставному середовищі.
Не відкриває LGE.conf, БД, брокерські сесії та не записує файлів.
"""

from __future__ import annotations

import ast
import copy
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SETTINGS_FILE = ROOT / "core" / "settings_page_trading.py"
MAIN_FILE = ROOT / "core" / "main_logic.py"


def isolated_method(
    path: Path,
    class_name: str,
    method_name: str,
    env: dict[str, Any] | None = None,
) -> Callable[..., Any]:
    """Витягнути тільки заданий метод без імпорту GUI або RuntimeEngine."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    target = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    method = next(
        node
        for node in target.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == method_name
    )
    method = copy.deepcopy(method)
    method.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    namespace = {} if env is None else dict(env)
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[method_name]


def check_case(before: str, selected: str) -> bool:
    """Імітувати натискання Apply без диска й без реального Qt-вікна."""
    conf = {
        "engine": {
            "broker": "CTRADER",
            "account_mode": "DEMO",
            "execution_mode": before,
        }
    }
    config = SimpleNamespace(to_dict=lambda: conf)
    fake_engine = SimpleNamespace(context=SimpleNamespace(execution_mode=before))
    session = SimpleNamespace(
        CURRENT_CONFIG=config,
        CURRENT_RUNTIME_ENGINE=fake_engine,
    )

    status_method = isolated_method(
        MAIN_FILE,
        "MainAppWindow",
        "_statusbar_orders_text",
        {"session_state": session},
    )
    notify_method = isolated_method(
        SETTINGS_FILE,
        "SettingsPageTrading",
        "_notify_main_window",
    )
    apply_method = isolated_method(
        SETTINGS_FILE,
        "SettingsPageTrading",
        "_apply_changes",
    )

    main = SimpleNamespace(
        _lang_mgr=SimpleNamespace(tr=lambda _key, fallback: fallback),
        status_text="",
    )

    def update_statusbar() -> None:
        main.status_text = status_method(main)[0]

    main.update_statusbar = update_statusbar
    dialog_window = SimpleNamespace(parent=lambda: main)
    settings = SimpleNamespace(
        _snapshot={},
        current_values=lambda: {
            "broker": "CTRADER",
            "account_mode": "DEMO",
            "execution_mode": selected,
        },
        window=lambda: dialog_window,
    )

    def fake_save(values: dict[str, str]) -> bool:
        conf["engine"].update(values)
        return True

    settings._save_to_conf = fake_save
    settings._notify_main_window = lambda: notify_method(settings)

    assert apply_method(settings) is True

    gui_mode = conf["engine"]["execution_mode"]
    runtime_mode = fake_engine.context.execution_mode

    print(f"case={before}_TO_{selected} gui={gui_mode} runtime={runtime_mode}")

    assert gui_mode == selected
    assert main.status_text.endswith(selected)
    return gui_mode != runtime_mode


def test() -> None:
    print("T116-06 TEST_ONLY | execution-mode config/runtime synchronization")

    drift_off = check_case("AUTO", "OFF")
    drift_auto = check_case("OFF", "AUTO")

    assert drift_off and drift_auto, "Дрейф не відтворено — повторно перевір код"

    print("statusbar_matches_config=YES")
    print("runtime_follows_gui_changes=NO")
    print("real_broker_requests=0")
    print("database_writes=0")
    print("config_writes=0")
    print("production_changes=0")
    print("T116-06=RED_RUNTIME_MODE_SYNC_REPRODUCED")


if __name__ == "__main__":
    test()
