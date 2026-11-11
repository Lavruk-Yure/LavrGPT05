# -*- coding: utf-8 -*-
"""RoadMap115 / T115-59: H1 entry decision source trace.

TEST_ONLY / SOURCE_ONLY.

Показує фактичний код H1 Replay та його прямі
залежності для вибору наступної production-умови
в окремому дослідницькому тесті.

Replay не виконується. Production і MD7 не змінюються.
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

MAX_SOURCE_LINES = 400

TARGETS = (
    "_trace_h1",
    "_run_tf",
    "_profile",
)


def _sha(path: Path) -> str:
    """Обчислити контрольний SHA256."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_path(obj: Any) -> Path | None:
    """Знайти вихідний файл об'єкта проєкту."""
    try:
        filename = inspect.getsourcefile(obj)
    except (OSError, TypeError):
        return None

    if not filename:
        return None

    path = Path(filename).resolve()

    if not path.is_file():
        return None

    if not path.is_relative_to(ROOT.resolve()):
        return None

    return path


def _dependencies(function: Any) -> list[tuple[str, Any]]:
    """Зібрати прямі залежності без виконання функції."""
    result: list[tuple[str, Any]] = []

    for name in sorted(set(function.__code__.co_names)):
        candidate = function.__globals__.get(name)

        if not (inspect.isfunction(candidate) or inspect.isclass(candidate)):
            continue

        if _source_path(candidate) is None:
            continue

        if candidate is function:
            continue

        result.append((name, candidate))

    return result


def _display(
    name: str,
    function: Any,
    remaining: int,
) -> int:
    """Вивести джерело з оригінальними номерами рядків."""
    path = _source_path(function)

    assert path is not None

    lines, start = inspect.getsourcelines(function)

    count = min(len(lines), remaining)

    print(
        f"H1_SOURCE|NAME={name}|"
        f"FILE={path.relative_to(ROOT)}|"
        f"START={start}|"
        f"TOTAL_LINES={len(lines)}|"
        f"PRINTED={count}"
    )

    for offset, line in enumerate(lines[:count]):
        print(f"SRC|{start + offset:04d}|" f"{line.rstrip()}")

    print(f"H1_SOURCE_END|NAME={name}|" f"TRUNCATED={count < len(lines)}")

    return count


def main() -> None:
    """Перевірити джерело H1 entry без виконання Replay."""
    audit = import_module("T115_32_Cross_Period_M15_Entry_State_Audit")

    loader = getattr(audit, "_load_windows")

    assert inspect.isfunction(loader)

    namespace = loader.__globals__

    functions: list[tuple[str, Any]] = []

    for name in TARGETS:
        function = namespace.get(name)

        assert inspect.isfunction(function), f"H1_SOURCE_NOT_FOUND={name}"

        functions.append((name, function))

    guarded = {
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        TEST_DIR / "T115_32_Cross_Period_M15_Entry_State_Audit.py",
    }

    for _, function in functions:
        path = _source_path(function)
        assert path is not None
        guarded.add(path)

    assert all(path.is_file() for path in guarded)

    before = {path: _sha(path) for path in guarded}

    print("T115-59|TEST_ONLY|" "H1_ENTRY_DECISION_SOURCE_TRACE")
    print("REPLAY_EXECUTED=False")
    print("M15_SHADOW_NOT_ASSUMED_AS_ENTRY_GATE=True")

    printed = 0

    for name, function in functions:
        print(f"H1_FUNCTION|NAME={name}|" f"MODULE={function.__module__}")

        for dependency_name, dependency in _dependencies(function):
            path = _source_path(dependency)
            assert path is not None

            print(
                f"H1_DIRECT_DEPENDENCY|PARENT={name}|"
                f"NAME={dependency_name}|"
                f"FILE={path.relative_to(ROOT)}"
            )

        remaining = MAX_SOURCE_LINES - printed

        if remaining <= 0:
            print(f"H1_SOURCE_SKIPPED|NAME={name}|" "REASON=OUTPUT_LIMIT")
            continue

        printed += _display(
            name,
            function,
            remaining,
        )

    assert before == {path: _sha(path) for path in guarded}

    print(f"H1_SOURCE_TOTAL_PRINTED={printed}|" f"LIMIT={MAX_SOURCE_LINES}")

    print("H1_ENTRY_SOURCE_FUNCTIONS_LOCATED=OK")
    print("SOURCE_FILES_UNCHANGED=OK")
    print("ENTRY_DECISION_ORDER_REQUIRES_REVIEW=True")
    print("NO_ENTRY_OR_EXIT_RULE_CHANGE=True")
    print("broker_requests=0|TEST_ONLY=True|SOURCE_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_59_H1_ENTRY_DECISION_SOURCE_TRACE=OK")


if __name__ == "__main__":
    main()
