"""run_t107_12_positions_reconciled_tooltip_anatomy_check.py — T107-12.

TEST_ONLY anatomy regression відтворює вузький Positions pipeline старого
``run_algorithm_workspace_area_check.py`` через реальні
``AlgorithmWorkspaceArea`` і ``WorkspacePositionSnapshot``. Runner подає одну
WSP-owned IB position із technical reconciliation state ``RECONCILED``, читає
фактичний item колонки 11, поточну Status column та underlying immutable
snapshot і класифікує розбіжність як production UI defect, stale assertion або
іншу причину.

Перевірка не запускає WSP runtime, broker network, Replay execution, Candidate F
або MDI layout actions. Вона не змінює production, старий area-check, Session
користувача, MD7 чи localization і завершується anatomy marker ``OK`` після
друку factual evidence незалежно від класифікації.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_DATA_MODE_REPLAY,
)
from core.algorithm_workspace_area import (  # noqa: E402
    POSITION_TABLE_COLUMNS,
    AlgorithmWorkspaceArea,
    AlgorithmWorkspaceWindow,
)
from core.algorithm_workspace_controller import (  # noqa: E402
    AlgorithmWorkspaceController,
)
from core.session_repository import SessionRepository  # noqa: E402

TEST_ID = "T107-12"
MODE = "RM107_T107_12_POSITIONS_RECONCILED_TOOLTIP_ANATOMY_TEST_ONLY"
LEGACY_ASSERTION_COLUMN = 11
RECONCILED = "RECONCILED"


def _process_events(app: QApplication) -> None:
    """Дати Qt завершити production snapshot-to-table refresh."""
    app.processEvents()
    app.processEvents()


def _column_index(translation_key: str) -> int:
    """Знайти поточний індекс Positions column за production schema key."""
    for index, (key, _fallback) in enumerate(POSITION_TABLE_COLUMNS):
        if key == translation_key:
            return index
    raise AssertionError(f"Positions column is missing: {translation_key}")


def _single_line(text: str) -> str:
    """Зберегти повний tooltip в одному machine-readable output рядку."""
    return (
        str(text)
        .replace("—", "\\u2014")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )


def main() -> None:
    """Відтворити старий column-11 assertion і класифікувати його anatomy."""
    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory() as temp_dir:
        repository = SessionRepository(Path(temp_dir) / "Session")
        controller = AlgorithmWorkspaceController(repository)
        area = AlgorithmWorkspaceArea(controller=controller)
        area.resize(1280, 820)
        area.show()
        _process_events(app)

        workspace = area.create_workspace(
            broker="IB",
            account_id="DUM513747",
            account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
            symbol="EURUSD",
            timeframe="M15",
            algorithm="RailAlgorithm",
            data_mode=WORKSPACE_DATA_MODE_REPLAY,
        )
        _process_events(app)
        window = area.workspace_window(workspace.workspace_uid)
        if not isinstance(window, AlgorithmWorkspaceWindow):
            raise AssertionError("production WSP client widget was not created")

        owned_snapshot = area.set_workspace_owned_snapshots(
            workspace.workspace_uid,
            order_rows=[],
            position_rows=[
                {
                    "workspace_uid": workspace.workspace_uid,
                    "broker": "IB",
                    "account_id": "DUM513747",
                    "symbol": "EURUSD",
                    "position_id": "POSITION-1",
                    "broker_position_id": "IB:DUM513747:EURUSD:LEG-1",
                    "side": "BUY",
                    "volume": 1000,
                    "entry_price": 1.1380,
                    "current_price": 1.1389,
                    "current_profit": 69.0,
                    "peak_profit": 100.0,
                    "stop_loss": 1.1350,
                    "take_profit": 1.1440,
                    "opened_at": "2026-07-25T08:00:00Z",
                    "reconciliation_status": RECONCILED,
                }
            ],
        )
        _process_events(app)

        position_row_count = window.tbl_positions.rowCount()
        if position_row_count != 1 or len(owned_snapshot.positions) != 1:
            raise AssertionError("single production position row was not populated")

        legacy_item = window.tbl_positions.item(0, LEGACY_ASSERTION_COLUMN)
        if legacy_item is None:
            raise AssertionError("legacy assertion cell was not populated")
        status_column = _column_index("AlgorithmWorkspaceWindow.colStatus")
        closed_at_column = _column_index("AlgorithmWorkspaceWindow.colClosedAt")
        status_item = window.tbl_positions.item(0, status_column)
        if status_item is None:
            raise AssertionError("current Status cell was not populated")

        position = owned_snapshot.positions[0]
        status_cell_text = legacy_item.text()
        status_cell_tooltip = legacy_item.toolTip()
        current_status_cell_text = status_item.text()
        current_status_cell_tooltip = status_item.toolTip()
        underlying_reconciliation_state = position.reconciliation_status
        underlying_state_is_reconciled = (
            underlying_reconciliation_state == RECONCILED
        )
        tooltip_contains_reconciled = RECONCILED in status_cell_tooltip
        current_status_tooltip_contains_reconciled = (
            RECONCILED in current_status_cell_tooltip
        )
        legacy_column_is_closed_at = (
            LEGACY_ASSERTION_COLUMN == closed_at_column
        )
        ui_matches_current_production_state = bool(
            position.active
            and underlying_state_is_reconciled
            and current_status_cell_text.strip()
            and current_status_tooltip_contains_reconciled
            and legacy_column_is_closed_at
        )
        old_area_assertion_currently_valid = tooltip_contains_reconciled

        if (
            underlying_state_is_reconciled
            and not current_status_tooltip_contains_reconciled
        ):
            failure_classification = "PRODUCTION_UI_DEFECT"
        elif (
            ui_matches_current_production_state
            and not old_area_assertion_currently_valid
        ):
            failure_classification = "STALE_TEST_ASSERTION"
        else:
            failure_classification = "OTHER"

        area.hide()
        area.deleteLater()
        _process_events(app)

    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print(f"position_row_count={position_row_count}")
    print(f"legacy_assertion_column={LEGACY_ASSERTION_COLUMN}")
    print(f"legacy_column_is_closed_at={legacy_column_is_closed_at}")
    print(f"current_status_column={status_column}")
    print(f"status_cell_text={_single_line(status_cell_text)}")
    print(f"status_cell_tooltip={_single_line(status_cell_tooltip)}")
    print(f"current_status_cell_text={_single_line(current_status_cell_text)}")
    print(
        "current_status_cell_tooltip="
        f"{_single_line(current_status_cell_tooltip)}"
    )
    print(f"underlying_reconciliation_state={underlying_reconciliation_state}")
    print(f"underlying_position_active={position.active}")
    print(f"underlying_state_is_reconciled={underlying_state_is_reconciled}")
    print(f"tooltip_contains_reconciled={tooltip_contains_reconciled}")
    print(
        "current_status_tooltip_contains_reconciled="
        f"{current_status_tooltip_contains_reconciled}"
    )
    print(
        "ui_matches_current_production_state="
        f"{ui_matches_current_production_state}"
    )
    print(
        "old_area_assertion_currently_valid="
        f"{old_area_assertion_currently_valid}"
    )
    print(f"failure_classification={failure_classification}")
    print("broker_requests=0")
    print("broker_execution_attempted=False")
    print("production_logic_changed=False")
    print("T107_12_POSITIONS_RECONCILED_TOOLTIP_ANATOMY=OK")


if __name__ == "__main__":
    main()
