# -*- coding: utf-8 -*-
"""T111-45 — IB Alligator Server Evidence readiness — TEST_ONLY.

Без брокерських запитів, Qt, імпорту production чи зміни робочих файлів.
Діагностує лише передану послідовність timestamp, не виправляє бари.
"""

from __future__ import annotations

import argparse
import ast
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "core" / "workspace_runtime.py"
BROKER = ROOT / "core" / "workspace_broker_market.py"
ALLIGATOR = ROOT / "core" / "workspace_alligator.py"
TEST_ONLY = True
BROKER_REQUESTS = 0
BROKER_EXECUTION_ATTEMPTED = False
PRODUCTION_LOGIC_CHANGED = False


def method(path: Path, class_name: str, name: str) -> ast.FunctionDef:
    """Знайти метод у чинному коді без його виконання."""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == name:
                    return child
    raise AssertionError(f"Method not found: {class_name}.{name}")


def timestamp(value: str) -> datetime:
    """Нормалізувати ISO timestamp до UTC, без округлення."""
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    result = datetime.fromisoformat(raw)
    if result.tzinfo is None:
        raise ValueError("Timestamp must include a UTC offset")
    return result.astimezone(UTC)


def inspect_sequence(data: dict) -> dict:
    """Знайти перше порушення окремо в warm-up та на межі live."""
    warmup = [timestamp(value) for value in data["warmup"]]
    live = [timestamp(value) for value in data.get("live_completed", [])]
    if not warmup:
        raise ValueError("At least one warm-up timestamp is required")
    previous = None
    for index, current in enumerate(warmup):
        if previous is not None and current <= previous:
            return {
                "boundary": "WARMUP_INTERNAL",
                "reason": "DUPLICATE" if current == previous else "BACKWARD",
                "index": index,
                "previous_timestamp": previous.isoformat(),
                "current_timestamp": current.isoformat(),
            }
        previous = current
    for index, current in enumerate(live):
        if current <= previous:
            return {
                "boundary": "WARMUP_TO_LIVE" if index == 0 else "LIVE_INTERNAL",
                "reason": "DUPLICATE" if current == previous else "BACKWARD",
                "index": index,
                "previous_timestamp": previous.isoformat(),
                "current_timestamp": current.isoformat(),
            }
        previous = current
    return {"boundary": "NONE", "reason": "ORDERED"}


def check(value: bool, label: str) -> None:
    if not value:
        raise AssertionError(label)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence",
        type=Path,
        help="Необов'язковий JSON із timestamp, скопійований із сервера",
    )
    args = parser.parse_args()

    alligator = ast.unparse(
        method(ALLIGATOR, "WorkspaceAlligatorFilter", "on_market_event")
    )
    warmup = ast.unparse(
        method(BROKER, "RuntimeEngineWorkspaceMarketProvider", "_load_warmup_events")
    )
    start = ast.unparse(
        method(RUNTIME, "WorkspaceRuntime", "_complete_broker_start")
    )
    facts = {
        "alligator_requires_strict_timestamp_order": (
            "event.timestamp <= self._last_timestamp" in alligator
        ),
        "warmup_preserves_broker_tail_order": "bars[-warmup_bars:]" in warmup,
        "warmup_logs_only_edge_timestamps": (
            "first_timestamp=events[0].timestamp.isoformat()" in start
            and "last_timestamp=events[-1].timestamp.isoformat()" in start
        ),
        "warmup_dispatches_original_event_order": "for event in events:" in start,
    }
    for label, passed in facts.items():
        check(passed, label)

    base = datetime(2026, 10, 19, 3, 0, tzinfo=UTC)
    d = timedelta(minutes=15)
    t0, t1, t2 = [(base + d * n).isoformat() for n in range(3)]
    tests = {
        "duplicate_warmup_pinpointed": inspect_sequence(
            {"warmup": [t0, t1, t1]}
        )["boundary"] == "WARMUP_INTERNAL",
        "backward_warmup_pinpointed": inspect_sequence(
            {"warmup": [t0, t2, t1]}
        )["reason"] == "BACKWARD",
        "warmup_live_overlap_pinpointed": inspect_sequence(
            {"warmup": [t0, t1], "live_completed": [t1]}
        )["boundary"] == "WARMUP_TO_LIVE",
        "later_live_duplicate_pinpointed": inspect_sequence(
            {"warmup": [t0], "live_completed": [t1, t1]}
        )["boundary"] == "LIVE_INTERNAL",
        "ordered_sequence_accepted": inspect_sequence(
            {"warmup": [t0, t1], "live_completed": [t2]}
        )["boundary"] == "NONE",
        "timezone_equivalent_duplicate_detected": inspect_sequence(
            {"warmup": ["2026-10-19T03:00:00+00:00", "2026-10-19T06:00:00+03:00"]}
        )["reason"] == "DUPLICATE",
    }
    for label, passed in tests.items():
        check(passed, label)

    print("T111-45 TEST_ONLY")
    print("verdict=SERVER_EVIDENCE_DETECTOR_READY")
    for label, passed in {**facts, **tests}.items():
        print(f"{label}={passed}")
    if args.evidence:
        data = json.loads(args.evidence.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError("Evidence must be a JSON object")
        result = inspect_sequence(data)
        print("observed_input=EXTERNAL_EVIDENCE_NOT_VERIFIED")
        for name, value in result.items():
            print(f"evidence_{name}={value}")
    else:
        print("observed_server_root_cause=UNRESOLVED")
        print("server_evidence_available=False")
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(f"broker_execution_attempted={BROKER_EXECUTION_ATTEMPTED}")
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
