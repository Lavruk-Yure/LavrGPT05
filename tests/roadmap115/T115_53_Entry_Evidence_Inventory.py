# -*- coding: utf-8 -*-
"""RoadMap115 / T115-53: entry evidence inventory.

TEST_ONLY / DATA_ONLY.

Інвентаризація фактичної структури записів T115-32:
- поля entry audit record;
- поля baseline trade;
- наявність та типи значень;
- кількість M15 strict classes;
- точна звірка чотирьох baseline.

Назва поля сама по собі НЕ підтверджує,
що його значення було причинно доступне при вході.

Ніякого аналізу outcome для створення сигналу.
Ніяких змін production, MD7 або Replay.
"""

from __future__ import annotations

import hashlib
import math
import sys
from collections import Counter
from dataclasses import fields, is_dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if str(ROOT / "tests" / "roadmap115") not in sys.path:
    sys.path.insert(
        0,
        str(ROOT / "tests" / "roadmap115"),
    )

t47 = import_module("T115_47_Pre_Entry_Non_BE_Loss_Anatomy")


def _sha(path: Path) -> str:
    """Контроль вмісту опорних файлів."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1048576),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _names(obj: object) -> tuple[str, ...]:
    """Отримати оголошені публічні поля об'єкта."""
    if is_dataclass(obj):
        dataclass_names = [
            field.name
            for field in fields(cast(Any, obj))
            if not field.name.startswith("_")
        ]

        return tuple(sorted(dataclass_names))

    dictionary = getattr(obj, "__dict__", None)

    if isinstance(dictionary, dict):
        return tuple(sorted(name for name in dictionary if not name.startswith("_")))

    slot_names: set[str] = set()

    for cls in type(obj).__mro__:
        slots = getattr(cls, "__slots__", ())

        if isinstance(slots, str):
            slots = (slots,)

        for name in slots:
            if not name.startswith("_"):
                slot_names.add(name)

    return tuple(sorted(slot_names))


def _inventory(
    label: str,
    objects: list[object],
) -> None:
    """Показати схему, покриття та типи без значень."""
    assert objects

    schema_counts = Counter(_names(obj) for obj in objects)

    print(
        f"OBJECT_SCHEMA|LABEL={label}|"
        f"OBJECTS={len(objects)}|"
        f"VARIANTS={len(schema_counts)}"
    )

    for schema, count in sorted(schema_counts.items()):
        names = ",".join(schema) if schema else "NONE"

        print(f"SCHEMA_VARIANT|LABEL={label}|" f"COUNT={count}|FIELDS={names}")

    all_names = sorted({name for schema in schema_counts for name in schema})

    for name in all_names:
        present = 0
        nonnull = 0
        types: Counter[str] = Counter()

        for obj in objects:
            if name not in _names(obj):
                continue

            present += 1

            value = getattr(obj, name)

            if value is not None:
                nonnull += 1

            types[type(value).__name__] += 1

        assert nonnull <= present <= len(objects)

        type_summary = ",".join(
            f"{type_name}:{count}" for type_name, count in sorted(types.items())
        )

        print(
            f"FIELD_INVENTORY|LABEL={label}|"
            f"FIELD={name}|"
            f"PRESENT={present}|"
            f"NONNULL={nonnull}|"
            f"TYPES={type_summary}"
        )

    print(f"FIELD_INVENTORY_RECONCILIATION={label}:OK")


def main() -> None:
    """Перевірити фактичні структури без торгових змін."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROOT / "tests/roadmap115/" "T115_32_Cross_Period_M15_Entry_State_Audit.py",
        ROOT / "tests/roadmap115/" "T115_47_Pre_Entry_Non_BE_Loss_Anatomy.py",
        ROOT / "tests/roadmap115/" "T115_52_H1_Body_Conditional_Rank_Audit.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-53|TEST_ONLY|ENTRY_EVIDENCE_INVENTORY")
    print("SOURCE=FROZEN_T115_32")
    print("PROVENANCE_FOR_NEW_FIELDS=UNVERIFIED")
    print("NO_ENTRY_RULE_CHANGE=True")

    windows = t47.load_windows()

    assert len(windows) == 4

    entries: list[object] = []
    trades: list[object] = []
    classes: Counter[str] = Counter()

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

        for item in window.entries:
            assert item.trade.direction in (t47.BUY, t47.SELL)
            assert item.trade.entry_at is not None

            entries.append(item)
            trades.append(item.trade)

            cls = str(item.strict_class) if item.strict_class is not None else "MISSING"

            classes[cls] += 1

        print(
            f"BASELINE_MATCH={window.name}:OK|"
            f"TRADES={expected_count}|"
            f"NET040={net:+.2f}|"
            f"OPEN_END={window.open_end}"
        )

    assert len(entries) == 333
    assert len(trades) == 333
    assert sum(classes.values()) == 333

    _inventory("ENTRY_AUDIT", entries)
    _inventory("BASELINE_TRADE", trades)

    for name, count in sorted(classes.items()):
        print(f"STRICT_CLASS|NAME={name}|" f"COUNT={count}")

    assert before == [_sha(path) for path in guarded]

    print("FOUR_PERIOD_BASELINE_RECONCILIATION=OK")
    print("ENTRY_EVIDENCE_SCHEMA_INVENTORY=OK")
    print("FIELD_NAMES_ARE_NOT_CAUSAL_PROOF=True")
    print("EXIT_FIELDS_NOT_USED_FOR_ENTRY_DECISIONS=True")
    print("NO_NEW_FILTER=True|NO_REPLAY_CHANGE=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_53_ENTRY_EVIDENCE_INVENTORY=OK")


if __name__ == "__main__":
    main()
