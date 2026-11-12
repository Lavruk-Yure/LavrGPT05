# -*- coding: utf-8 -*-
"""RoadMap115 / T115-60: H1 Engine entry decision anatomy.

TEST_ONLY / SOURCE_ONLY.

Показати повний вихідний код дослідницького Engine,
його методи та прямі посилання on_bar на функції проєкту.

Жодних торгових рішень не виконується.
Відповідність production окремо не припускається.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import sys
from importlib import import_module
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TEST_DIR = ROOT / "tests" / "roadmap115"

for directory in (ROOT, TEST_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))


def _sha(path: Path) -> str:
    """Обчислити SHA256 файлу."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _project_path(obj: Any) -> Path | None:
    """Знайти вихідний файл об'єкта всередині проєкту."""
    try:
        filename = inspect.getsourcefile(obj)
    except (OSError, TypeError):
        return None

    if not filename:
        return None

    path = Path(filename).resolve()

    if path.is_file() and path.is_relative_to(ROOT.resolve()):
        return path

    return None


def main() -> None:
    """Вивести реалізацію Engine для перевірки entry."""
    module = import_module("T115_15_Extended_Timeframe_Plateau_Audit")

    engine: Any = getattr(module, "Engine")
    on_bar: Any = getattr(engine, "on_bar")

    assert inspect.isclass(engine)
    assert inspect.isfunction(on_bar)

    source_path = _project_path(engine)
    assert source_path is not None

    relative = source_path.relative_to(ROOT.resolve())
    assert relative.parts[:2] == ("tests", "roadmap115")

    source_lines, first_line = inspect.getsourcelines(engine)
    source = "".join(source_lines)

    tree = ast.parse(source)

    class_nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Engine"
    ]

    assert len(class_nodes) == 1

    class_node = class_nodes[0]

    methods = [
        node
        for node in class_node.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    assert any(node.name == "on_bar" for node in methods)

    dependencies: list[tuple[str, Path]] = []

    for name in sorted(set(on_bar.__code__.co_names)):
        candidate = on_bar.__globals__.get(name)

        if not inspect.isfunction(candidate):
            continue

        path = _project_path(candidate)

        if path is not None:
            dependencies.append((name, path))

    guarded = {
        source_path,
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        TEST_DIR / "T115_59_H1_Entry_Decision_Source_Trace.py",
    }

    for _, path in dependencies:
        guarded.add(path)

    assert all(path.is_file() for path in guarded)

    before = {path: _sha(path) for path in guarded}

    print("T115-60|TEST_ONLY|" "H1_ENGINE_ENTRY_DECISION_ANATOMY")
    print("REPLAY_EXECUTED=False")
    print("ENGINE_IS_RESEARCH_IMPLEMENTATION=True")
    print("SOURCE_INSPECTION_ONLY=True")

    print(f"ENGINE_MODULE={engine.__module__}|" f"FILE={relative}")

    print(f"ENGINE_CLASS_LINES={len(source_lines)}|" f"METHOD_COUNT={len(methods)}")

    for node in methods:
        print(f"ENGINE_METHOD|NAME={node.name}|" f"LINE={first_line + node.lineno - 1}")

    for name, path in dependencies:
        print(
            f"ON_BAR_GLOBAL_REFERENCE|NAME={name}|"
            f"FILE={path.relative_to(ROOT.resolve())}"
        )

    print(
        f"ENGINE_SOURCE_BEGIN|"
        f"FIRST_LINE={first_line}|"
        f"LAST_LINE={first_line + len(source_lines) - 1}"
    )

    for offset, line in enumerate(source_lines):
        print(f"SRC|{first_line + offset:04d}|" f"{line.rstrip()}")

    print("ENGINE_SOURCE_END")

    after = {path: _sha(path) for path in guarded}

    assert before == after

    print("ENGINE_CLASS_SOURCE=OK")
    print("SOURCE_SHA_UNCHANGED=OK")
    print("ENTRY_DECISION_ORDER_REQUIRES_REVIEW=True")
    print("PRODUCTION_EQUIVALENCE_NOT_ASSERTED=True")
    print("NO_ENTRY_OR_EXIT_RULE_CHANGE=True")
    print("broker_requests=0|TEST_ONLY=True|SOURCE_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_60_H1_ENGINE_ENTRY_DECISION_ANATOMY=OK")


if __name__ == "__main__":
    main()
