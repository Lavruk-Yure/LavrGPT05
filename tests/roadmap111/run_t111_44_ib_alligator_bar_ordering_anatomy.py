# -*- coding: utf-8 -*-
"""T111-44 — IB Alligator Bar Ordering Anatomy — TEST_ONLY.

Лише AST та синтетичні завершені бари. Не імпортує production,
не створює брокерських запитів і не змінює робоче дерево.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLIGATOR = ROOT / "core" / "workspace_alligator.py"
BROKER = ROOT / "core" / "workspace_broker_market.py"
RUNTIME = ROOT / "core" / "workspace_runtime.py"
TEST_ONLY = True
BROKER_REQUESTS = 0
PRODUCTION_LOGIC_CHANGED = False


def method(tree: ast.Module, class_name: str, method_name: str) -> ast.FunctionDef:
    for cls in tree.body:
        if isinstance(cls, ast.ClassDef) and cls.name == class_name:
            for node in cls.body:
                if isinstance(node, ast.FunctionDef) and node.name == method_name:
                    return node
    raise AssertionError(f"missing {class_name}.{method_name}")


def source(node: ast.AST) -> str:
    return ast.unparse(node)


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)


def first_violation(bars: list[datetime]) -> tuple[int, str] | None:
    """TEST_ONLY класифікатор — не виправляє послідовність."""
    for index in range(1, len(bars)):
        if bars[index] <= bars[index - 1]:
            kind = "DUPLICATE" if bars[index] == bars[index - 1] else "BACKWARD"
            return index, kind
    return None


def main() -> int:
    a = ast.parse(ALLIGATOR.read_text(encoding="utf-8-sig"))
    b = ast.parse(BROKER.read_text(encoding="utf-8-sig"))
    r = ast.parse(RUNTIME.read_text(encoding="utf-8-sig"))
    filter_update = method(a, "WorkspaceAlligatorFilter", "on_market_event")
    history = method(b, "RuntimeEngineWorkspaceMarketProvider", "_load_warmup_events")
    live = method(b, "WorkspaceLiveBarAggregator", "update")
    accept = method(r, "WorkspaceRuntime", "_accept_market_event")
    start = method(r, "WorkspaceRuntime", "_complete_broker_start")
    dispatch = method(r, "WorkspaceRuntime", "_dispatch_market_event_to_algorithm")

    guard = source(filter_update)
    history_path = source(history)
    live_path = source(live)
    accept_path = source(accept)
    start_path = source(start)
    dispatch_path = source(dispatch)

    facts = {
        "alligator_rejects_equal_or_older_timestamp": (
            "event.timestamp <= self._last_timestamp" in guard
            and "Alligator bars must be strictly ordered and unique" in guard
        ),
        "warmup_uses_broker_returned_tail": "bars[-warmup_bars:]" in history_path,
        "warmup_has_no_sort_or_dedup": (
            "sorted(" not in history_path
            and ".sort(" not in history_path
            and "set(" not in history_path
        ),
        "live_rejects_stale_bucket": "STALE_BUCKET" in live_path,
        "live_emits_completed_previous_bucket": (
            "timestamp=self._bucket_timestamp" in live_path
            and "ROLLOVER_COMPLETED" in live_path
        ),
        "runtime_dispatches_to_algorithm": (
            "self._dispatch_market_event_to_algorithm(event)" in accept_path
            and "algorithm.on_market_event(event)" in dispatch_path
        ),
        "warmup_dispatches_in_original_order": (
            "for event in events:" in start_path
            and "BROKER_WARMUP" in start_path
        ),
    }
    for label, value in facts.items():
        check(value, label)

    t0 = datetime(2026, 10, 19, 3, 0, tzinfo=UTC)
    step = timedelta(minutes=15)
    ordered = [t0, t0 + step, t0 + 2 * step]
    duplicate = [t0, t0 + step, t0 + step]
    backward = [t0, t0 + 2 * step, t0 + step]
    overlap = [t0, t0 + step, t0 + step]
    clean_transition = [t0, t0 + step, t0 + 2 * step]
    cases = {
        "ordered_warmup_passes": first_violation(ordered) is None,
        "duplicate_warmup_detected": first_violation(duplicate) == (2, "DUPLICATE"),
        "backward_warmup_detected": first_violation(backward) == (2, "BACKWARD"),
        "warmup_live_overlap_detected": first_violation(overlap) == (2, "DUPLICATE"),
        "newer_live_bar_passes": first_violation(clean_transition) is None,
    }
    for label, value in cases.items():
        check(value, label)

    print("T111-44 TEST_ONLY")
    print("verdict=IB_ALLIGATOR_ORDERING_BOUNDARIES_IDENTIFIED")
    for label, value in {**facts, **cases}.items():
        print(f"{label}={value}")
    print("observed_server_root_cause=UNRESOLVED")
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print("broker_execution_attempted=False")
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
