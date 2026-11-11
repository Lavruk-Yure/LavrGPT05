# -*- coding: utf-8 -*-
"""RoadMap115 / T115-58: M15 state timestamp provenance.

TEST_ONLY / SOURCE_ONLY.

Показати фактичний код формування WatchBar
і перевірити походження його часової мітки.

Виводяться:
- _observe_m15;
- _snapshot;
- _category;
- WatchBar;
- прямі функціональні залежності _observe_m15.

Не виконує Replay та не змінює торгових правил.
Production і MD7 залишаються незмінними.
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


SOURCE_LIMIT = 400


def _sha(path: Path) -> str:
    """Обчислити SHA256 файлу."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1048576),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _source_path(obj: Any) -> Path | None:
    """Знайти вихідний файл Python-об'єкта."""
    try:
        filename = inspect.getsourcefile(obj)
    except (TypeError, OSError):
        return None

    if not filename:
        return None

    path = Path(filename).resolve()

    if not path.is_file():
        return None

    return path


def _project_function(obj: Any) -> bool:
    """Перевірити, що функція належить проєкту."""
    if not inspect.isfunction(obj):
        return False

    path = _source_path(obj)

    return path is not None and path.is_relative_to(ROOT.resolve())


def _dependencies(
    function: Any,
) -> list[tuple[str, Any]]:
    """Знайти прямі Python-функції, на які посилається код."""
    assert inspect.isfunction(function)

    found: list[tuple[str, Any]] = []
    seen: set[int] = set()

    for name in sorted(set(function.__code__.co_names)):
        candidate = function.__globals__.get(name)

        if not _project_function(candidate):
            continue

        if candidate is function:
            continue

        identity = id(candidate)

        if identity in seen:
            continue

        seen.add(identity)
        found.append((name, candidate))

    return found


def _display(
    label: str,
    obj: Any,
    remaining: int,
) -> int:
    """Показати вихідний код із реальними номерами рядків."""
    path = _source_path(obj)

    if path is None:
        print(f"SOURCE_UNAVAILABLE|NAME={label}")
        return 0

    try:
        lines, first_line = inspect.getsourcelines(obj)
    except (TypeError, OSError):
        print(f"SOURCE_UNAVAILABLE|NAME={label}")
        return 0

    relative = path.relative_to(ROOT.resolve())

    count = min(
        len(lines),
        max(0, remaining),
    )

    print(
        f"SOURCE_SYMBOL|NAME={label}|"
        f"FILE={relative}|"
        f"START={first_line}|"
        f"TOTAL_LINES={len(lines)}"
    )

    for offset, line in enumerate(lines[:count]):
        print(f"SRC|{first_line + offset:04d}|" f"{line.rstrip()}")

    print(
        f"SOURCE_END|NAME={label}|"
        f"PRINTED={count}|"
        f"TRUNCATED={count < len(lines)}"
    )

    return count


def main() -> None:
    """Показати M15 provenance без виконання Replay."""
    audit = import_module("T115_32_Cross_Period_M15_Entry_State_Audit")

    builder = getattr(audit, "_entries")
    observer = getattr(audit, "_observe_m15")

    assert inspect.isfunction(builder)
    assert inspect.isfunction(observer)

    snapshot = builder.__globals__.get("_snapshot")

    assert inspect.isfunction(snapshot)

    category = snapshot.__globals__.get("_category")
    watchbar = snapshot.__globals__.get("WatchBar")
    m15_span = snapshot.__globals__.get("M15_SPAN")

    assert inspect.isfunction(category)

    objects: list[tuple[str, Any]] = [
        ("_observe_m15", observer),
        ("_snapshot", snapshot),
        ("_category", category),
    ]

    if inspect.isclass(watchbar):
        objects.append(("WatchBar", watchbar))

    dependencies = _dependencies(observer)

    for name, function in dependencies:
        if function in (observer, snapshot, category):
            continue

        objects.append((f"_observe_m15_dependency:{name}", function))

    guarded = {
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        TEST_DIR / "T115_25_H1_Entry_M15_State_Anatomy.py",
        TEST_DIR / "T115_32_Cross_Period_M15_Entry_State_Audit.py",
        TEST_DIR / "T115_57_Entry_State_Construction_Source_Trace.py",
    }

    for _, obj in objects:
        path = _source_path(obj)

        if path is not None:
            guarded.add(path)

    assert all(path.is_file() for path in guarded)

    before = {path: _sha(path) for path in guarded}

    print("T115-58|TEST_ONLY|" "M15_STATE_TIMESTAMP_PROVENANCE")
    print("REPLAY_EXECUTED=False")
    print("SOURCE_INSPECTION_ONLY=True")

    print(f"OBSERVER_MODULE={observer.__module__}")
    print(f"SNAPSHOT_MODULE={snapshot.__module__}")
    print(f"CATEGORY_MODULE={category.__module__}")
    print(f"M15_SPAN={m15_span}")
    print(f"OBSERVER_DIRECT_DEPENDENCIES=" f"{len(dependencies)}")

    printed = 0

    for label, obj in objects:
        remaining = SOURCE_LIMIT - printed

        if remaining <= 0:
            print(f"SOURCE_SKIPPED|NAME={label}|" "REASON=SOURCE_LIMIT")
            continue

        printed += _display(
            label,
            obj,
            remaining,
        )

    assert printed > 0

    assert before == {path: _sha(path) for path in guarded}

    print(f"SOURCE_TOTAL_PRINTED={printed}|" f"LIMIT={SOURCE_LIMIT}")

    print("M15_OBSERVER_SOURCE_LOCATED=OK")
    print("ENTRY_SNAPSHOT_SOURCE_LOCATED=OK")
    print("SOURCE_FILES_UNCHANGED=OK")
    print("TIMESTAMP_SEMANTICS_REQUIRES_REVIEW=True")
    print("BOUNDARY_CAUSALITY_NOT_ASSUMED=True")
    print("NO_ENTRY_FILTER_CREATED=True")
    print("NO_REPLAY_CHANGE=True")
    print("broker_requests=0|" "TEST_ONLY=True|SOURCE_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_58_M15_STATE_TIMESTAMP_PROVENANCE=OK")


if __name__ == "__main__":
    main()
