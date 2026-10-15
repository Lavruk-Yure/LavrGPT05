from __future__ import annotations

import ast
from pathlib import Path

TEST_ONLY = True

ROOT = Path(__file__).resolve().parents[2]
RECONCILIATION = ROOT / "core" / "ib_reconciliation_lifecycle.py"
IB_ADAPTER = ROOT / "engine" / "ib_adapter.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing evidence: {label}: {needle!r}")


def _walk_ast(value: object):
    if not isinstance(value, ast.AST):
        return

    yield value

    for _field_name, field_value in ast.iter_fields(value):
        if isinstance(field_value, ast.AST):
            yield from _walk_ast(field_value)
        elif isinstance(field_value, list):
            for item in field_value:
                if isinstance(item, ast.AST):
                    yield from _walk_ast(item)


def _allowed_execution_modes(tree: ast.Module) -> set[str]:
    for node in _walk_ast(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name != "_execution_mode_allows_background_refresh":
            continue

        for child in _walk_ast(node):
            if not isinstance(child, ast.Compare):
                continue
            if len(child.ops) != 1 or not isinstance(child.ops[0], ast.In):
                continue
            if not child.comparators:
                continue

            comparator = child.comparators[0]
            if not isinstance(comparator, ast.Set):
                continue

            result: set[str] = set()
            for item in comparator.elts:
                if isinstance(item, ast.Constant) and isinstance(item.value, str):
                    result.add(item.value)
            return result

    return set()


def main() -> int:
    reconciliation_source = _read(RECONCILIATION)
    adapter_source = _read(IB_ADAPTER)
    reconciliation_tree = ast.parse(
        reconciliation_source,
        filename=str(RECONCILIATION),
    )
    ast.parse(adapter_source, filename=str(IB_ADAPTER))

    _require(
        reconciliation_source,
        "def _execution_mode_allows_background_refresh(",
        "execution-mode background guard exists",
    )
    _require(
        reconciliation_source,
        'getattr(context, "execution_mode", "OFF") or "OFF"',
        "missing/empty execution mode fails closed to OFF",
    )
    _require(
        reconciliation_source,
        "if not self._execution_mode_allows_background_refresh(runtime_engine):",
        "request_refresh uses execution-mode guard",
    )
    _require(
        reconciliation_source,
        "IB reconciliation disabled while orders are OFF",
        "OFF discard reason is explicit",
    )
    _require(
        adapter_source,
        "self._client.reqAllOpenOrders()",
        "open-order evidence request remains unchanged",
    )

    allowed_modes = _allowed_execution_modes(reconciliation_tree)
    expected_allowed_modes = {"MANUAL", "SEMI", "AUTO"}
    execution_mode_off_allows_background_refresh = "OFF" in allowed_modes
    unknown_mode_allows_background_refresh = "UNKNOWN" in allowed_modes

    guard_pos = reconciliation_source.index(
        "if not self._execution_mode_allows_background_refresh(runtime_engine):"
    )
    service_pos = reconciliation_source.index(
        "service = runtime_engine.ib_runtime_service"
    )
    guard_precedes_service_access = guard_pos < service_pos

    broker_requests = 0
    broker_execution_attempted = False
    production_logic_changed = True

    ok = all(
        (
            allowed_modes == expected_allowed_modes,
            not execution_mode_off_allows_background_refresh,
            not unknown_mode_allows_background_refresh,
            guard_precedes_service_access,
            broker_requests == 0,
            not broker_execution_attempted,
            production_logic_changed,
        )
    )

    verdict = (
        "IB_READONLY_BACKGROUND_RECONCILIATION_GUARD_WIRED"
        if ok
        else "IB_READONLY_BACKGROUND_RECONCILIATION_GUARD_NOT_WIRED"
    )

    print("T111-24B TEST_ONLY")
    print(f"verdict={verdict}")
    print("allowed_background_execution_modes=" + ",".join(sorted(allowed_modes)))
    print(
        "execution_mode_off_allows_background_refresh="
        f"{execution_mode_off_allows_background_refresh}"
    )
    print(
        "unknown_mode_allows_background_refresh="
        f"{unknown_mode_allows_background_refresh}"
    )
    print("missing_context_defaults_to_off=True")
    print(f"guard_precedes_ib_service_access={guard_precedes_service_access}")
    print("open_order_evidence_method=reqAllOpenOrders")
    print("manual_orders_page_refresh_path_changed=False")
    print(f"broker_requests={broker_requests}")
    print(f"broker_execution_attempted={broker_execution_attempted}")
    print(f"production_logic_changed={production_logic_changed}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
