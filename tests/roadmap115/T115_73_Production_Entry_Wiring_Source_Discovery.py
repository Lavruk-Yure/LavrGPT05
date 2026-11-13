# -*- coding: utf-8 -*-
"""RoadMap115 / T115-73: production ENTRY wiring discovery.

TEST_ONLY / SOURCE_ONLY.

Знайти production-кандидатів для фактичного
ланцюга Alligator -> market event -> ENTRY.

Пошук статичний. Збіг символів не доводить,
що відповідний код виконується у production.

Replay і торгові рішення не виконуються.
Production та MD7 не змінюються.
"""

from __future__ import annotations

import ast
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

EXCLUDED = {
    ".git",
    ".idea",
    ".venv",
    "__pycache__",
    "build",
    "data",
    "dist",
    "doc",
    "logs",
    "node_modules",
    "tests",
    "venv",
    "venv313",
}

MAX_BYTES = 2_000_000
MAX_CANDIDATES = 15


@dataclass(slots=True)
class SourceMatch:
    """Статичні посилання в одному Python-модулі."""

    path: Path
    lines: list[str]
    tree: ast.AST
    alligator: set[int]
    entry: set[int]
    event: set[int]

    def score(self) -> int:
        """Ранжувати кандидата лише для огляду коду."""
        return (
            100 * int(bool(self.alligator and self.entry))
            + 40 * int(bool(self.alligator and self.event))
            + 20 * int(bool(self.entry and self.event))
            + min(len(self.alligator), 10)
        )


def _sha(path: Path) -> str:
    """Обчислити контрольний SHA256."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sources() -> list[Path]:
    """Зібрати Python-файли без дослідницьких тестів."""
    paths: list[Path] = []

    for directory, dirs, files in os.walk(ROOT):
        dirs[:] = sorted(name for name in dirs if name not in EXCLUDED)

        for filename in sorted(files):
            if filename.endswith(".py"):
                paths.append(Path(directory) / filename)

    return sorted(paths)


def _match(path: Path) -> SourceMatch | None:
    """Знайти символи в AST без виконання модуля."""
    if path.stat().st_size > MAX_BYTES:
        return None

    content = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(content, filename=str(path))

    indicators: set[int] = set()
    entries: set[int] = set()
    events: set[int] = set()

    for node in ast.walk(tree):
        symbol: str | None = None

        if isinstance(node, ast.Name):
            symbol = node.id
        elif isinstance(node, ast.Attribute):
            symbol = node.attr
        elif isinstance(node, ast.Constant):
            if node.value in ("ENTRY", "EXIT"):
                symbol = str(node.value)

        if symbol is None:
            continue

        line = getattr(node, "lineno", None)

        if line is None:
            continue

        low = symbol.lower()

        if "alligator" in low or low in {
            "regime_phase",
            "regime",
            "confirmation_mode",
        }:
            indicators.add(line)

        if "entry" in low or low in {
            "open_position",
            "trade_decision",
            "pending_action",
        }:
            entries.add(line)

        if low in {
            "on_market_event",
            "on_bar",
            "available_at",
            "workspacemarketevent",
        }:
            events.add(line)

    if not indicators and not (entries and events):
        return None

    return SourceMatch(
        path=path,
        lines=content.splitlines(),
        tree=tree,
        alligator=indicators,
        entry=entries,
        event=events,
    )


def _scope(tree: ast.AST, line: int) -> str:
    """Визначити найвужчий клас або функцію."""
    matches: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
            ),
        ):
            continue

        last = getattr(node, "end_lineno", None)

        if last is not None and node.lineno <= line <= last:
            matches.append((last - node.lineno, node.name))

    return min(matches)[1] if matches else "MODULE"


def main() -> None:
    """Вивести кандидати production ENTRY wiring."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
    )

    assert all(path.is_file() for path in guarded)
    before = [_sha(path) for path in guarded]

    print("T115-73|TEST_ONLY|" "PRODUCTION_ENTRY_WIRING_SOURCE_DISCOVERY")
    print("REPLAY_EXECUTED=False")
    print("SOURCE_DISCOVERY_IS_NOT_EXECUTION_PROOF=True")

    paths = _sources()
    matches: list[SourceMatch] = []
    parse_errors = 0
    too_large = 0

    for path in paths:
        try:
            record = _match(path)
        except (SyntaxError, UnicodeError) as error:
            parse_errors += 1
            print(
                f"SOURCE_PARSE_SKIPPED|"
                f"FILE={path.relative_to(ROOT)}|"
                f"ERROR={type(error).__name__}"
            )
            continue

        if record is None:
            if path.stat().st_size > MAX_BYTES:
                too_large += 1
            continue

        matches.append(record)

    matches.sort(
        key=lambda candidate: (
            -candidate.score(),
            str(candidate.path),
        )
    )

    assert any(record.path.name == "workspace_alligator.py" for record in matches)

    print(
        f"SOURCE_INVENTORY|FILES={len(paths)}|"
        f"CANDIDATES={len(matches)}|"
        f"PARSE_SKIPPED={parse_errors}|"
        f"OVERSIZED_SKIPPED={too_large}"
    )

    for record in matches[:MAX_CANDIDATES]:
        relative = record.path.relative_to(ROOT)

        print(
            f"SOURCE_CANDIDATE|FILE={relative}|"
            f"SCORE={record.score()}|"
            f"ALLIGATOR_REFS={len(record.alligator)}|"
            f"ENTRY_REFS={len(record.entry)}|"
            f"EVENT_REFS={len(record.event)}"
        )

        chosen = sorted(
            set(
                sorted(record.alligator)[:3]
                + sorted(record.entry)[:3]
                + sorted(record.event)[:3]
            )
        )

        for number in chosen:
            text = record.lines[number - 1].strip()

            print(
                f"SRC|FILE={relative}|LINE={number}|"
                f"SCOPE={_scope(record.tree, number)}|"
                f"TEXT={text[:200]}"
            )

    assert before == [_sha(path) for path in guarded]

    print("PRODUCTION_SOURCE_CANDIDATES_IDENTIFIED=OK")
    print("GUARDED_SOURCE_SHA_UNCHANGED=OK")
    print("ACTUAL_CALL_PATH_REQUIRES_VERIFICATION=True")
    print("NO_ENTRY_EXIT_REENTRY_RULE_CHANGE=True")
    print("broker_requests=0|TEST_ONLY=True|SOURCE_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_73_PRODUCTION_ENTRY_WIRING_SOURCE_DISCOVERY=OK")


if __name__ == "__main__":
    main()
