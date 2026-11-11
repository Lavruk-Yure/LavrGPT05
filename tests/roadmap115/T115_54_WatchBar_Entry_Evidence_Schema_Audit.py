# -*- coding: utf-8 -*-
"""RoadMap115 / T115-54: WatchBar entry evidence schema.

TEST_ONLY / DATA_ONLY.

Дослідження фактичних полів strict_state і boundary_state
із заморожених записів T115-32.

Перевіряємо:
- назви й типи внутрішніх полів WatchBar;
- заповненість полів;
- приклади скалярних значень;
- відмінності strict_state та boundary_state;
- strict_age_min та відповідність часу входу.

Інвентаризація НЕ доводить причинність значень.
Торгові правила, Replay, production і MD7 не змінюються.
"""

from __future__ import annotations

import hashlib
import math
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from importlib import import_module
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TEST_DIR = ROOT / "tests" / "roadmap115"

for directory in (ROOT, TEST_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

t47 = import_module("T115_47_Pre_Entry_Non_BE_Loss_Anatomy")

t53 = import_module("T115_53_Entry_Evidence_Inventory")

names_of = getattr(t53, "_names")

SCALAR_TYPES = (
    str,
    int,
    float,
    bool,
    datetime,
)


@dataclass(frozen=True, slots=True)
class SyntheticWatchBar:
    """Мінімальна структура для перевірки інвентаризації."""

    state: str
    age: int


def _sha(path: Path) -> str:
    """Обчислити SHA256 контрольного файлу."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for block in iter(
            lambda: stream.read(1048576),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def _synthetic() -> None:
    """Перевірити виявлення полів без торгових даних."""
    sample = SyntheticWatchBar(
        state="ACTIVE",
        age=15,
    )

    assert names_of(sample) == ("age", "state")
    assert getattr(sample, "state") == "ACTIVE"
    assert getattr(sample, "age") == 15

    print("SYNTHETIC_WATCHBAR_FIELD_DISCOVERY=OK")


def _schema_report(
    label: str,
    states: list[object],
) -> set[str]:
    """Показати схему та покриття внутрішніх полів."""
    assert len(states) == 333

    schemas = Counter(names_of(state) for state in states)

    all_fields = sorted({name for schema in schemas for name in schema})

    print(
        f"WATCHBAR_SCHEMA|LABEL={label}|"
        f"OBJECTS={len(states)}|"
        f"VARIANTS={len(schemas)}|"
        f"FIELDS={','.join(all_fields) or 'NONE'}"
    )

    for schema, count in sorted(schemas.items()):
        print(
            f"WATCHBAR_SCHEMA_VARIANT|LABEL={label}|"
            f"COUNT={count}|"
            f"FIELDS={','.join(schema) or 'NONE'}"
        )

    for field_name in all_fields:
        values = [
            getattr(state, field_name)
            for state in states
            if field_name in names_of(state)
        ]

        types = Counter(type(value).__name__ for value in values)

        scalar_values = [value for value in values if isinstance(value, SCALAR_TYPES)]

        unique_scalar = {(type(value).__name__, repr(value)) for value in scalar_values}

        examples: list[str] = []

        for value in scalar_values:
            example = repr(value)

            if example not in examples:
                examples.append(example[:70])

            if len(examples) == 3:
                break

        types_text = ",".join(
            f"{name}:{count}" for name, count in sorted(types.items())
        )

        print(
            f"WATCHBAR_FIELD|LABEL={label}|"
            f"NAME={field_name}|"
            f"PRESENT={len(values)}|"
            f"NONNULL={sum(value is not None for value in values)}|"
            f"TYPES={types_text}|"
            f"SCALAR_UNIQUE={len(unique_scalar)}|"
            f"EXAMPLES={';'.join(examples) or 'NA'}"
        )

    print(f"WATCHBAR_SCHEMA_RECONCILIATION={label}:OK")

    return set(all_fields)


def _pair_report(
    entries: list[Any],
    strict_fields: set[str],
    boundary_fields: set[str],
) -> None:
    """Порівняти лише прості значення двох WatchBar."""
    common = sorted(strict_fields & boundary_fields)

    print(
        "WATCHBAR_SCHEMA_COMPARISON|"
        f"COMMON_FIELDS={len(common)}|"
        f"STRICT_ONLY={','.join(sorted(strict_fields - boundary_fields)) or 'NONE'}|"
        f"BOUNDARY_ONLY={','.join(sorted(boundary_fields - strict_fields)) or 'NONE'}"
    )

    for field_name in common:
        comparable = 0
        different = 0

        for item in entries:
            strict = getattr(
                item.strict_state,
                field_name,
                None,
            )

            boundary = getattr(
                item.boundary_state,
                field_name,
                None,
            )

            if not (
                isinstance(strict, SCALAR_TYPES) and isinstance(boundary, SCALAR_TYPES)
            ):
                continue

            comparable += 1

            if strict != boundary:
                different += 1

        print(
            f"WATCHBAR_FIELD_PAIR|FIELD={field_name}|"
            f"COMPARABLE={comparable}|"
            f"DIFFERENT={different}|"
            f"SAME={comparable - different}"
        )

    print("WATCHBAR_PAIR_FIELD_COMPARISON=OK")


def main() -> None:
    """Виконати інвентаризацію без змін production."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        TEST_DIR / "T115_32_Cross_Period_M15_Entry_State_Audit.py",
        TEST_DIR / "T115_47_Pre_Entry_Non_BE_Loss_Anatomy.py",
        TEST_DIR / "T115_53_Entry_Evidence_Inventory.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-54|TEST_ONLY|" "WATCHBAR_ENTRY_EVIDENCE_SCHEMA_AUDIT")
    print("SOURCE=FROZEN_T115_32")
    print("FIELDS_CAUSAL_PROVENANCE=NOT_YET_VERIFIED")
    print("NO_ENTRY_RULE_CHANGE=True")

    _synthetic()

    windows = t47.load_windows()

    assert len(windows) == 4

    entries: list[Any] = []

    for window in windows:
        expected_count, expected_net, _, expected_open = t47.EXPECTED[window.name]

        assert len(window.entries) == expected_count
        assert window.open_end == expected_open

        net = math.fsum(float(item.trade.pips) - t47.COST for item in window.entries)

        assert math.isclose(
            net,
            expected_net,
            abs_tol=t47.EPS,
        )

        ages = [item.strict_age_min for item in window.entries]

        assert all(isinstance(age, int) for age in ages)

        entries.extend(window.entries)

        print(
            f"BASELINE_MATCH={window.name}:OK|"
            f"CLOSED={expected_count}|"
            f"NET040={net:+.2f}|"
            f"OPEN_END={window.open_end}"
        )

        print(
            f"STRICT_AGE|PERIOD={window.name}|"
            f"COUNT={len(ages)}|"
            f"MIN={min(ages)}|"
            f"MEDIAN={statistics.median(ages):.2f}|"
            f"MAX={max(ages)}"
        )

    assert len(entries) == 333

    strict_states = [item.strict_state for item in entries]

    boundary_states = [item.boundary_state for item in entries]

    assert all(
        type(state).__name__ == "WatchBar" for state in strict_states + boundary_states
    )

    strict_fields = _schema_report(
        "STRICT",
        strict_states,
    )

    boundary_fields = _schema_report(
        "BOUNDARY",
        boundary_states,
    )

    _pair_report(
        entries,
        strict_fields,
        boundary_fields,
    )

    time_matches = sum(item.entry_at == item.trade.entry_at for item in entries)

    class_matches = sum(item.strict_class == item.boundary_class for item in entries)

    print(
        f"ENTRY_TIME_MATCH|" f"SAME={time_matches}|" f"DIFFERENT={333 - time_matches}"
    )

    print(
        f"ENTRY_CLASS_MATCH|"
        f"SAME={class_matches}|"
        f"DIFFERENT={333 - class_matches}"
    )

    assert before == [_sha(path) for path in guarded]

    print("FOUR_PERIOD_BASELINE_RECONCILIATION=OK")
    print("WATCHBAR_ENTRY_EVIDENCE_INVENTORY=OK")
    print("SCHEMA_IS_NOT_CAUSAL_PROOF=True")
    print("FUTURE_OUTCOMES_NOT_USED_FOR_FILTERS=True")
    print("NO_NEW_ENTRY_FILTER=True")
    print("NO_REPLAY_CHANGE=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_54_WATCHBAR_ENTRY_EVIDENCE_SCHEMA_AUDIT=OK")


if __name__ == "__main__":
    main()
