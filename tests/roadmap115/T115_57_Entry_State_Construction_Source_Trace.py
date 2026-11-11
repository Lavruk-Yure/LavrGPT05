# -*- coding: utf-8 -*-
"""RoadMap115 / T115-57: entry-state source trace.

TEST_ONLY / SOURCE_ONLY.

Знаходить фактичне визначення _entries, EntryState
та безпосередньо викликаних функцій проєкту.

Не виконує Replay, не оцінює угоди й не створює
правил входу. Результат потребує перевірки причинності.

Production та MD7 не змінюються.
"""

from __future__ import annotations

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

MODULE_NAME = "T115_32_Cross_Period_M15_Entry_State_Audit"

MAX_SOURCE_LINES = 400


def _sha(path: Path) -> str:
    """Обчислити контрольний SHA256."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1048576),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _source_path(obj: Any) -> Path | None:
    """Отримати шлях до вихідного файлу Python."""
    try:
        filename = inspect.getsourcefile(obj)
    except (OSError, TypeError):
        return None

    if not filename:
        return None

    path = Path(filename).resolve()

    if not path.is_file():
        return None

    return path


def _project_function(obj: object) -> bool:
    """Вибрати тільки функції фактичного проєкту."""
    if not inspect.isfunction(obj):
        return False

    path = _source_path(obj)

    return path is not None and path.is_relative_to(ROOT.resolve())


def _discover(
    builder: object,
) -> list[tuple[str, object]]:
    """Знайти прямі залежності реалізації _entries."""
    if not inspect.isfunction(builder):
        raise TypeError("_entries must be a Python function")

    result: list[tuple[str, object]] = []
    seen: set[int] = set()

    namespace = builder.__globals__

    for name in sorted(set(builder.__code__.co_names)):
        candidate = namespace.get(name)

        if not _project_function(candidate):
            continue

        if candidate is builder:
            continue

        if id(candidate) in seen:
            continue

        seen.add(id(candidate))

        result.append((name, candidate))

    return result


def _display(
    label: str,
    obj: Any,
    remaining: int,
) -> int:
    """Вивести код з номерами оригінальних рядків."""
    path = _source_path(obj)

    if path is None:
        print(f"SOURCE_NOT_AVAILABLE|SYMBOL={label}")
        return 0

    try:
        lines, start = inspect.getsourcelines(obj)
    except (OSError, TypeError):
        print(f"SOURCE_NOT_AVAILABLE|SYMBOL={label}")
        return 0

    try:
        relative = path.relative_to(ROOT.resolve())
    except ValueError:
        relative = path

    print(
        f"SOURCE_SYMBOL|NAME={label}|"
        f"FILE={relative}|"
        f"START={start}|"
        f"LINES={len(lines)}"
    )

    count = min(
        len(lines),
        max(0, remaining),
    )

    for offset in range(count):
        number = start + offset

        print(f"SRC|{number:04d}|" f"{lines[offset].rstrip()}")

    print(
        f"SOURCE_SYMBOL_END|NAME={label}|"
        f"PRINTED={count}|"
        f"TRUNCATED={count < len(lines)}"
    )

    return count


def main() -> None:
    """Показати фактичний ланцюг формування записів."""
    audit = import_module(MODULE_NAME)

    builder = getattr(audit, "_entries")

    assert inspect.isfunction(builder)

    dependencies = _discover(builder)

    objects: list[tuple[str, object]] = [
        ("_entries", builder),
    ]

    for name, obj in dependencies:
        objects.append((f"_entries_dependency:{name}", obj))

    loader = getattr(audit, "_load_windows", None)

    if inspect.isfunction(loader):
        objects.append(("_load_windows", loader))

    guarded = {
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        TEST_DIR / "T115_32_Cross_Period_M15_Entry_State_Audit.py",
    }

    for _, obj in objects:
        path = _source_path(obj)

        if path is not None:
            guarded.add(path)

    assert all(path.is_file() for path in guarded)

    before = {path: _sha(path) for path in guarded}

    print("T115-57|TEST_ONLY|" "ENTRY_STATE_CONSTRUCTION_SOURCE_TRACE")
    print("SOURCE=ACTUAL_IMPORTED_PYTHON_OBJECTS")
    print("REPLAY_EXECUTED=False")
    print("ENTRY_GATE_SIMULATED=False")

    print(f"ENTRY_BUILDER_MODULE={builder.__module__}")

    print(f"DIRECT_PROJECT_DEPENDENCIES=" f"{len(dependencies)}")

    printed = 0

    for label, obj in objects:
        remaining = MAX_SOURCE_LINES - printed

        if remaining <= 0:
            print(f"SOURCE_SKIPPED|NAME={label}|" "REASON=OUTPUT_LIMIT")
            continue

        printed += _display(
            label,
            obj,
            remaining,
        )

    assert before == {path: _sha(path) for path in guarded}

    print(f"SOURCE_TOTAL_PRINTED={printed}|" f"LIMIT={MAX_SOURCE_LINES}")

    print("ACTUAL_ENTRY_BUILDER_LOCATED=OK")
    print("SOURCE_FILES_UNCHANGED=OK")
    print("EXECUTION_ORDER_REQUIRES_REVIEW=True")
    print("BOUNDARY_CAUSALITY_NOT_YET_PROVEN=True")
    print("NO_TRADING_RULE_CHANGE=True")
    print("broker_requests=0|TEST_ONLY=True|SOURCE_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_57_ENTRY_STATE_" "CONSTRUCTION_SOURCE_TRACE=OK")


if __name__ == "__main__":
    main()
