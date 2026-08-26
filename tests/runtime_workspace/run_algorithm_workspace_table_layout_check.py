# run_algorithm_workspace_table_layout_check.py — статичний contract WSP таблиць
# -*- coding: utf-8 -*-
"""Статичний contract компактних Orders/Positions/Signals таблиць WSP.

Перевіряє кількість і widths колонок, stretch policy, горизонтальний scroll,
cell tooltips та приховування порожнього broker order ID. Після RoadMap99_04C
Positions має окремі Signal і Opened timestamps та розширену на одну колонку
структуру без втрати close-reason stretch.
"""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = PROJECT_ROOT / "core" / "algorithm_workspace_area.py"


def _literal_value(node: ast.expr) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Tuple):
        return tuple(_literal_value(item) for item in node.elts)
    if isinstance(node, ast.List):
        return [_literal_value(item) for item in node.elts]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _literal_value(node.operand)
        if isinstance(value, (int, float)):
            return -value
    raise ValueError(f"Unsupported literal node: {type(node).__name__}")


def _assignments(tree: ast.Module) -> dict[str, object]:
    values: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        try:
            values[target.id] = _literal_value(node.value)
        except ValueError:
            continue
    return values


def _method_source(source: str, tree: ast.Module, name: str) -> str:
    lines = source.splitlines()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != name:
            continue
        end_lineno = node.end_lineno
        if end_lineno is None:
            raise AssertionError(f"Method has no end line: {name}")
        return "\n".join(lines[node.lineno - 1 : end_lineno])  # noqa
    raise AssertionError(f"Method not found: {name}")


def main() -> None:
    source = SOURCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    values = _assignments(tree)

    order_widths = values["ORDER_TABLE_WIDTHS"]
    position_widths = values["POSITION_TABLE_WIDTHS"]
    signal_widths = values["SIGNAL_TABLE_WIDTHS"]
    assert isinstance(order_widths, tuple) and len(order_widths) == 12
    assert isinstance(position_widths, tuple) and len(position_widths) == 13
    assert isinstance(signal_widths, tuple) and len(signal_widths) == 11

    assert values["ORDER_TABLE_STRETCH_COLUMN"] == 9
    assert values["POSITION_TABLE_STRETCH_COLUMN"] == 12
    assert values["SIGNAL_TABLE_STRETCH_COLUMN"] == 10
    assert sum(signal_widths[:-1]) <= 1020

    configure_source = _method_source(
        source,
        tree,
        "_configure_snapshot_table",
    )
    row_source = _method_source(source, tree, "_set_table_row")
    order_source = _method_source(source, tree, "_populate_order_rows")

    assert "QHeaderView.ResizeMode.Stretch" in configure_source
    assert "QAbstractItemView.ScrollMode.ScrollPerPixel" in configure_source
    assert "setTextElideMode(Qt.TextElideMode.ElideRight)" in configure_source
    assert "item.setToolTip(text)" in row_source
    assert "table.setColumnHidden(1" in order_source
    assert "horizontalScrollBar().setValue(0)" in source

    print("Algorithm Workspace Table Layout result")
    print("  compact_fixed_columns=True")
    print("  signal_context_columns_readable=True")
    print("  signal_reason_column_stretches=True")
    print("  position_signal_entry_columns=True")
    print("  position_close_reason_stretches=True")
    print("  order_close_reason_column_stretches=True")
    print("  full_cell_text_available_in_tooltips=True")
    print("  replay_broker_order_id_hidden_when_empty=True")
    print("  first_population_scrolls_to_left=True")
    print("ALGORITHM_WORKSPACE_TABLE_LAYOUT_CHECK=OK")


if __name__ == "__main__":
    main()
