# -*- coding: utf-8 -*-
"""RoadMap115 / T115-56: entry boundary source provenance.

TEST_ONLY / SOURCE_ONLY.

Витягує фрагменти фактичного T115-32 навколо
формування STRICT і BOUNDARY.

Це інспекція вихідного коду, а не доказ причинності.
Production, Replay та MD7 не змінюються.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SOURCE = ROOT / "tests" / "roadmap115" / "T115_32_Cross_Period_M15_Entry_State_Audit.py"

GUARDED = (
    SOURCE,
    ROOT / "core/workspace_alligator.py",
    ROOT / "core/workspace_indicator_profile.py",
    ROOT / "doc/LGE_Runtime_07.md",
)

ANCHORS = (
    "strict_state",
    "boundary_state",
    "strict_class",
    "boundary_class",
    "strict_age_min",
)

CONTEXT_BEFORE = 5
CONTEXT_AFTER = 7
MAX_EXCERPT_LINES = 300


def _sha(path: Path) -> str:
    """Обчислити SHA256 контрольного файлу."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _scope(tree: ast.AST, line_number: int) -> str:
    """Знайти найвужчу функцію або клас для рядка."""
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

        end = getattr(node, "end_lineno", None)

        if end is None:
            continue

        if node.lineno <= line_number <= end:
            matches.append(
                (
                    end - node.lineno,
                    node.name,
                )
            )

    if not matches:
        return "MODULE"

    return min(matches)[1]


def _context_spans(
    hits: list[int],
    total_lines: int,
) -> list[tuple[int, int]]:
    """Об'єднати фрагменти навколо знайдених рядків."""
    spans: list[list[int]] = []

    for number in hits:
        start = max(
            1,
            number - CONTEXT_BEFORE,
        )

        end = min(
            total_lines,
            number + CONTEXT_AFTER,
        )

        if spans and start <= spans[-1][1] + 1:
            spans[-1][1] = max(
                spans[-1][1],
                end,
            )
        else:
            spans.append([start, end])

    return [(start, end) for start, end in spans]


def main() -> None:
    """Показати джерела станів без запуску торгівлі."""
    assert all(path.is_file() for path in GUARDED)

    before = [_sha(path) for path in GUARDED]

    print("T115-56|TEST_ONLY|" "ENTRY_BOUNDARY_SOURCE_PROVENANCE")
    print("SOURCE=T115_32")
    print("REPLAY_EXECUTED=False")

    source = SOURCE.read_text(encoding="utf-8-sig")

    lines = source.splitlines()

    hits = [
        number
        for number, line in enumerate(
            lines,
            start=1,
        )
        if any(anchor in line for anchor in ANCHORS)
    ]

    assert hits
    assert any("strict_state" in lines[number - 1] for number in hits)
    boundary_symbol_found = any(
        "boundary_state" in lines[number - 1] for number in hits
    )

    print("BOUNDARY_STATE_LITERAL_FOUND=" f"{boundary_symbol_found}")

    spans = _context_spans(
        hits,
        len(lines),
    )

    printed = 0
    truncated = False

    for start, end in spans:
        if printed >= MAX_EXCERPT_LINES:
            truncated = True
            break

        print(f"SOURCE_EXCERPT|" f"START={start}|END={end}")

        for number in range(start, end + 1):
            if printed >= MAX_EXCERPT_LINES:
                truncated = True
                break

            print(f"SRC|{number:04d}|" f"{lines[number - 1]}")

            printed += 1

    print(f"SOURCE_EXCERPT_LINES={printed}|" f"TRUNCATED={truncated}")

    assert before == [_sha(path) for path in GUARDED]

    print("SOURCE_FILES_UNCHANGED=OK")
    print("SOURCE_ANCHORS_EXTRACTED=OK")
    print("EXECUTION_ORDER_NOT_YET_PROVEN=True")
    print("NO_ENTRY_RULE_CHANGE=True")
    print("broker_requests=0|TEST_ONLY=True|SOURCE_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_56_ENTRY_BOUNDARY_" "SOURCE_PROVENANCE=OK")


if __name__ == "__main__":
    main()
