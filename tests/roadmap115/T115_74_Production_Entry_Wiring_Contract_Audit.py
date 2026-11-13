# -*- coding: utf-8 -*-
"""RoadMap115 / T115-74 — production ENTRY wiring contract.

TEST_ONLY / SOURCE_ONLY. Статично перевірити фактичний ланцюг
UI factory -> Runtime -> MACD -> Alligator -> Candidate F ->
runtime guards -> virtual Replay execution.

AST-аудит не доводить динамічне виконання, parity або прибутковість.
Production, Replay-логіка і MD7 не змінюються.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCES = {
    "ui": "core/algorithm_workspace_area.py",
    "controller": "core/algorithm_workspace_controller.py",
    "factory": "core/workspace_algorithm.py",
    "alligator": "core/workspace_alligator.py",
    "macd": "core/workspace_macd.py",
    "runtime": "core/workspace_runtime.py",
    "execution": "core/workspace_replay_execution.py",
}
GUARDS = (
    "doc/LGE_Runtime_07.md",
    "tests/roadmap115/T115_73_Production_Entry_Wiring_Source_Discovery.py",
)


def _sha(path: Path) -> str:
    """Порахувати SHA256 без модифікації файлу."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _method(tree: ast.Module, owner: str, name: str) -> ast.FunctionDef:
    """Знайти метод за фактичним класом і назвою."""
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == owner:
            for member in node.body:
                if isinstance(member, ast.FunctionDef) and member.name == name:
                    return member
    raise AssertionError(f"METHOD_NOT_FOUND={owner}.{name}")


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    """Знайти функцію верхнього рівня."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"FUNCTION_NOT_FOUND={name}")


def _calls(node: ast.AST, name: str) -> list[int]:
    """Повернути номери викликів із зазначеним іменем."""
    lines: list[int] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Attribute) and func.attr == name:
            lines.append(child.lineno)
        elif isinstance(func, ast.Name) and func.id == name:
            lines.append(child.lineno)
    return sorted(lines)


def _identifiers(node: ast.AST) -> set[str]:
    """Зібрати посилання на символи, не виконуючи код."""
    result: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            result.add(child.id)
        elif isinstance(child, ast.Attribute):
            result.add(child.attr)
    return result


def _sequence(label: str, node: ast.AST, calls: tuple[str, ...]) -> None:
    """Перевірити за AST послідовність прямих викликів."""
    locations: list[int] = []
    for name in calls:
        found = _calls(node, name)
        assert found, f"CALL_NOT_FOUND={label}:{name}"
        locations.append(found[0])
    assert all(a < b for a, b in zip(locations, locations[1:])), (
        f"CALL_ORDER_MISMATCH={label}:{tuple(zip(calls, locations))}"
    )
    text = ";".join(f"{name}@{line}" for name, line in zip(calls, locations))
    print(f"CALL_ORDER|LABEL={label}|{text}|OK")


def main() -> None:
    """Перевірити саме наявний production wiring без імпорту runtime."""
    paths = {key: ROOT / value for key, value in SOURCES.items()}
    paths.update({f"guard_{i}": ROOT / name for i, name in enumerate(GUARDS)})
    assert all(path.is_file() for path in paths.values())
    before = {key: _sha(path) for key, path in paths.items()}
    trees = {
        key: ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for key, path in paths.items()
        if key in SOURCES
    }

    print("T115-74|TEST_ONLY|PRODUCTION_ENTRY_WIRING_CONTRACT_AUDIT")
    print("SOURCE=ACTUAL_LAVRGPT05_CORE")
    print("AST_ONLY=True|REPLAY_EXECUTED=False")

    ui_init = _method(trees["ui"], "AlgorithmWorkspaceArea", "__init__")
    factory = _function(trees["factory"], "create_registered_workspace_algorithm")
    controller = _method(
        trees["controller"], "AlgorithmWorkspaceController", "_build_workspace_runtime"
    )
    start = _method(trees["runtime"], "WorkspaceRuntime", "_start_algorithm")
    assert "create_registered_workspace_algorithm" in _identifiers(ui_init)
    assert "WorkspaceMacdAlligatorReplayAlgorithm" in _identifiers(factory)
    assert _calls(controller, "WorkspaceRuntime")
    assert "_algorithm_factory" in _identifiers(controller)
    assert "algorithm_factory" in _identifiers(start)
    print("UI_REGISTERED_FACTORY_TO_RUNTIME=OK")

    macd_on = _method(trees["macd"], "WorkspaceMacdSignalSource", "on_market_event")
    assert _calls(macd_on, "_proposal")
    alligator_on = _method(
        trees["alligator"], "WorkspaceMacdAlligatorReplayAlgorithm", "on_market_event"
    )
    _sequence("ALGORITHM", alligator_on, (
        "_base_signal_output", "_candidate_f_output"
    ))
    assert _calls(alligator_on, "_candidate_f_active")

    base = _method(
        trees["alligator"], "WorkspaceMacdAlligatorReplayAlgorithm", "_base_signal_output"
    )
    _sequence("MACD_ALLIGATOR", base, (
        "_update_alligator", "on_market_event", "evaluate"
    ))
    assert "WORKSPACE_SIGNAL_FILTER_REJECT" in _identifiers(base)

    candidate = _method(
        trees["alligator"], "WorkspaceMacdAlligatorReplayAlgorithm", "_candidate_f_output"
    )
    _sequence("CANDIDATE_F", candidate, (
        "_advance_armed_candidate", "_arm_from_base_proposals",
        "_apply_candidate_f_guards", "_apply_candidate_f_stochastic_gate"
    ))

    runtime_market = _method(trees["runtime"], "WorkspaceRuntime", "_accept_market_event")
    _sequence("SINGLE_TF_RUNTIME", runtime_market, (
        "_advance_replay_execution", "_dispatch_market_event_to_algorithm"
    ))
    multi = _method(trees["runtime"], "WorkspaceRuntime", "_accept_replay_session_event")
    _sequence("MULTI_RES_RUNTIME", multi, (
        "_accept_market_event", "_advance_replay_execution"
    ))
    assert "execution_events_for_index" in _identifiers(multi)

    dispatch = _method(
        trees["runtime"], "WorkspaceRuntime", "_dispatch_market_event_to_algorithm"
    )
    _sequence("PROPOSAL_DISPATCH", dispatch, (
        "on_market_event", "normalize_signal_output",
        "_candidate_f_execution_intent", "_record_signal"
    ))
    records = _method(trees["runtime"], "WorkspaceRuntime", "_record_signal")
    _sequence("RECORD_RISK_EXECUTION", records, (
        "can_form_signal", "_evaluate_signal_risk", "queue_signal"
    ))
    assert "WORKSPACE_SIGNAL_FILTER_ALLOW" in _identifiers(records)
    assert "accepted" in _identifiers(records)

    queue = _method(
        trees["execution"], "WorkspaceReplayExecutionEngine", "queue_signal"
    )
    execute = _method(
        trees["execution"], "WorkspaceReplayExecutionEngine", "on_market_event"
    )
    assert "expected_fill_at" in _identifiers(queue)
    assert "timedelta" in _identifiers(queue)
    assert "accepted" in _identifiers(queue)
    _sequence("NEXT_BAR_EXECUTION", execute, (
        "_expire_pending_order_gap", "_fill_pending_order"
    ))
    print("REPLAY_ACCEPTED_SIGNAL_NEXT_BAR_CONTRACT=OK")

    assert before == {key: _sha(path) for key, path in paths.items()}
    print("SOURCE_FILES_SHA_UNCHANGED=OK")
    print("SOURCE_CALL_ORDER_CONFIRMED=OK")
    print("DYNAMIC_PARITY_NOT_ESTABLISHED=True")
    print("NO_NEW_ENTRY_EXIT_OR_REENTRY_RULE=True")
    print("broker_requests=0|TEST_ONLY=True|SOURCE_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_74_PRODUCTION_ENTRY_WIRING_CONTRACT_AUDIT=OK")


if __name__ == "__main__":
    main()
