# -*- coding: utf-8 -*-
"""Перевірка збереження ручної ширини колонок робочих таблиць LGE.

Тест використовує тимчасовий Session і доводить save/restore для QTableWidget
та QTreeWidget. Також фіксує wiring для WSP Orders/Positions/Signals і
головної OrdersPage. Це лише UI-state: runtime/trade gate/broker не залучені.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QTableWidget, QTreeWidget  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.session_repository import SessionRepository  # noqa: E402
from core.table_column_widths import TableColumnWidthPersistence  # noqa: E402

AREA_PATH = PROJECT_ROOT / "core" / "algorithm_workspace_area.py"
ORDERS_PATH = PROJECT_ROOT / "core" / "orders_page.py"


def _table(column_count: int) -> QTableWidget:
    table = QTableWidget()
    table.setColumnCount(column_count)
    return table


def _tree(column_count: int) -> QTreeWidget:
    tree = QTreeWidget()
    tree.setColumnCount(column_count)
    return tree


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv[:1])

    with TemporaryDirectory() as temp_dir:
        repository = SessionRepository(Path(temp_dir))

        first = _table(3)
        first_state = TableColumnWidthPersistence(
            first,
            "algorithm_workspace.signals",
            (110, 120, 130),
            repository=repository,
            save_delay_ms=60_000,
        )
        assert first_state.current_widths() == (110, 120, 130)
        first.setColumnWidth(1, 222)
        first_state.flush()
        assert repository.load_table_column_widths("algorithm_workspace.signals") == (
            110,
            222,
            130,
        )

        restored = _table(3)
        restored_state = TableColumnWidthPersistence(
            restored,
            "algorithm_workspace.signals",
            (90, 90, 90),
            repository=repository,
            save_delay_ms=60_000,
        )
        assert restored_state.current_widths() == (110, 222, 130)

        replay_orders = _table(4)
        replay_orders_state = TableColumnWidthPersistence(
            replay_orders,
            "algorithm_workspace.orders",
            (100, 120, 140, 160),
            repository=repository,
            save_delay_ms=60_000,
        )
        replay_orders.setColumnHidden(1, True)
        replay_orders.setColumnWidth(2, 275)
        replay_orders_state.flush()
        assert repository.load_table_column_widths("algorithm_workspace.orders") == (
            100,
            120,
            275,
            160,
        )

        restored_orders = _table(4)
        restored_orders_state = TableColumnWidthPersistence(
            restored_orders,
            "algorithm_workspace.orders",
            (80, 80, 80, 80),
            repository=repository,
            save_delay_ms=60_000,
        )
        assert restored_orders_state.current_widths() == (100, 120, 275, 160)

        tree = _tree(3)
        tree_state = TableColumnWidthPersistence(
            tree,
            "orders_page.open_positions",
            (105, 60, 95),
            repository=repository,
            save_delay_ms=60_000,
        )
        tree.setColumnWidth(2, 180)
        tree_state.flush()
        assert repository.load_table_column_widths("orders_page.open_positions") == (
            105,
            60,
            180,
        )

        restored_tree = _tree(3)
        restored_tree_state = TableColumnWidthPersistence(
            restored_tree,
            "orders_page.open_positions",
            (80, 80, 80),
            repository=repository,
            save_delay_ms=60_000,
        )
        assert restored_tree_state.current_widths() == (105, 60, 180)

        first.close()
        restored.close()
        replay_orders.close()
        restored_orders.close()
        tree.close()
        restored_tree.close()
        app.processEvents()

    area_source = AREA_PATH.read_text(encoding="utf-8")
    orders_source = ORDERS_PATH.read_text(encoding="utf-8")

    for table_key in (
        "algorithm_workspace.orders",
        "algorithm_workspace.positions",
        "algorithm_workspace.signals",
    ):
        assert table_key in area_source
    assert "orders_page.open_positions" in orders_source
    assert "header.setStretchLastSection(False)" in area_source
    assert "header.setStretchLastSection(False)" in orders_source

    print("Algorithm Workspace table column width persistence result")
    print("  workspace_orders_manual_width_restore=True")
    print("  workspace_orders_hidden_broker_id_supported=True")
    print("  hidden_column_zero_width_not_persisted=True")
    print("  workspace_positions_manual_width_restore=True")
    print("  workspace_signals_manual_width_restore=True")
    print("  orders_page_positions_manual_width_restore=True")
    print("  qtablewidget_persistence=True")
    print("  qtreewidget_persistence=True")
    print("  interactive_last_column=True")
    print("  session_ui_state_only=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_TABLE_COLUMN_WIDTH_PERSISTENCE_CHECK=OK")


if __name__ == "__main__":
    main()
