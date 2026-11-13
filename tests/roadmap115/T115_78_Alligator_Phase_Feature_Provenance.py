# -*- coding: utf-8 -*-
"""RoadMap115 / T115-78: Alligator phase feature provenance.

TEST_ONLY / SOURCE_ONLY.

Знайти фактичні місця використання ENDING та трьох
ознак із T115-77 у production-коді.

Статичний аудит: не виконує Replay і не доводить
математичну незалежність ознак.

Production, Replay та MD7 не змінюються.
"""

from __future__ import annotations

import ast
import hashlib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SOURCE_FILES = (
    "core/workspace_alligator.py",
    "core/workspace_signal.py",
)

TOKENS = (
    "ALLIGATOR_REGIME_PHASE_ENDING",
    "normalized_slope",
    "normalized_opening",
    "active_age",
)

MAX_EXCERPTS_PER_TOKEN = 12


def _sha(path: Path) -> str:
    """Обчислити SHA256 файлу."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _scope(tree: ast.AST, line_number: int) -> str:
    """Знайти найвужчу функцію або клас для рядка."""
    candidates: list[tuple[int, str]] = []

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
            candidates.append((end - node.lineno, node.name))

    if not candidates:
        return "MODULE"

    return min(candidates)[1]


def _selected_hits(hits: list[int]) -> list[int]:
    """Вибрати початок і кінець знайдених посилань."""
    if len(hits) <= MAX_EXCERPTS_PER_TOKEN:
        return hits

    half = MAX_EXCERPTS_PER_TOKEN // 2

    return sorted(set(hits[:half] + hits[-half:]))


def main() -> None:
    """Знайти визначення та використання фазових ознак."""
    paths = [ROOT / relative for relative in SOURCE_FILES]

    md7 = ROOT / "doc/LGE_Runtime_07.md"

    guarded = paths + [md7]

    assert all(path.is_file() for path in guarded)

    before = {path: _sha(path) for path in guarded}

    print("T115-78|TEST_ONLY|" "ALLIGATOR_PHASE_FEATURE_PROVENANCE")
    print("REPLAY_EXECUTED=False")
    print("SOURCE_INSPECTION_ONLY=True")
    print("FEATURE_INDEPENDENCE_NOT_ASSUMED=True")

    totals: Counter[str] = Counter()

    for path in paths:
        relative = path.relative_to(ROOT)
        content = path.read_text(encoding="utf-8-sig")
        lines = content.splitlines()
        tree = ast.parse(content, filename=str(path))

        print(f"SOURCE_FILE|FILE={relative}|" f"LINES={len(lines)}|AST_PARSE=OK")

        for token in TOKENS:
            hits = [
                number for number, line in enumerate(lines, start=1) if token in line
            ]

            totals[token] += len(hits)

            print(
                f"FEATURE_REFERENCE_COUNT|"
                f"FILE={relative}|"
                f"FEATURE={token}|COUNT={len(hits)}"
            )

            scopes = Counter(_scope(tree, number) for number in hits)

            for scope, count in sorted(scopes.items()):
                print(
                    f"FEATURE_SCOPE|FILE={relative}|"
                    f"FEATURE={token}|"
                    f"SCOPE={scope}|COUNT={count}"
                )

            for number in _selected_hits(hits):
                print(
                    f"FEATURE_SOURCE|FILE={relative}|"
                    f"FEATURE={token}|LINE={number}|"
                    f"SCOPE={_scope(tree, number)}"
                )

                start = max(1, number - 2)
                end = min(len(lines), number + 2)

                for source_number in range(start, end + 1):
                    print(
                        f"SRC|{source_number:04d}|"
                        f"{lines[source_number - 1].rstrip()}"
                    )

                print("FEATURE_SOURCE_END")

    for token in TOKENS:
        print(f"POOLED_FEATURE_REFERENCES|" f"FEATURE={token}|COUNT={totals[token]}")

    assert totals["ALLIGATOR_REGIME_PHASE_ENDING"] > 0

    assert before == {path: _sha(path) for path in guarded}

    print("SOURCE_AST_PARSE=OK")
    print("ENDING_PHASE_SOURCE_LOCATED=OK")
    print("SOURCE_FILES_SHA_UNCHANGED=OK")
    print("STATIC_REFERENCES_ARE_NOT_CAUSAL_PROOF=True")
    print("NO_NEW_ENTRY_OR_EXIT_RULE=True")
    print("broker_requests=0|TEST_ONLY=True|SOURCE_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_78_ALLIGATOR_PHASE_FEATURE_PROVENANCE=OK")


if __name__ == "__main__":
    main()
